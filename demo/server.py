"""显伴 · 小光 — HTTP server (stdlib only).

Run:  python server.py [port]        (default 8765; production uses 18765)
Env:  MODELFLARE_API_KEY (required for real replies), MANIFEST_DATA (optional)

Every /api/* route except /api/auth/* and /api/health requires a session
cookie. The user's id is taken from that session only; there is no way to
pass a user id in a request.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import traceback
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from core import agent, auth, llm, onboarding, report, scenes, scheduler
from core.api import VERSION, ApiError
from core.store import Store
from core.util import PUBLIC, ROOT, clip, dumps, iso, load_dotenv

load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

COOKIE = "xg_session"
MAX_BODY = 64 * 1024
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = "xianban/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if args and "/api/" in str(args[0]):
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---- helpers -------------------------------------------------------------
    def _secure(self) -> bool:
        return self.headers.get("X-Forwarded-Proto") == "https"

    def _ip(self) -> str:
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def _token(self) -> str | None:
        c = cookies.SimpleCookie()
        try:
            c.load(self.headers.get("Cookie") or "")
        except cookies.CookieError:
            return None
        return c[COOKIE].value if COOKIE in c else None

    def _set_cookie(self, token: str | None) -> str:
        attrs = "; Path=/; HttpOnly; SameSite=Lax" + ("; Secure" if self._secure() else "")
        if token is None:
            return f"{COOKIE}=; Max-Age=0" + attrs
        return f"{COOKIE}={token}; Max-Age={auth.SESSION_DAYS * 86400}" + attrs

    def _headers(self, status: int, ctype: str, length: int | None = None, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)

    def _json(self, status: int, obj, extra: dict | None = None):
        body = dumps(obj).encode()
        self._headers(status, "application/json; charset=utf-8", len(body), {"Cache-Control": "no-store", **(extra or {})})
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ApiError(413, "内容太长")
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        try:
            v = json.loads(raw)
        except ValueError:
            raise ApiError(400, "JSON 格式不对")
        if not isinstance(v, dict):
            raise ApiError(400, "JSON 需要是对象")
        return v

    def _check_origin(self):
        """CSRF defence on top of SameSite=Lax: a state-changing request must
        come from our own origin (or carry no Origin, e.g. curl/tests)."""
        origin = self.headers.get("Origin")
        if not origin:
            return
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        if urlparse(origin).netloc != host:
            raise ApiError(403, "来源不允许")

    def _user(self) -> dict:
        u = auth.session_user(self._token())
        if not u:
            raise ApiError(401, "请先登录")
        return u

    # ---- dispatch --------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str):
        url = urlparse(self.path)
        path = url.path
        try:
            if not path.startswith("/api/"):
                if method != "GET":
                    raise ApiError(405, "method not allowed")
                return self._static(path)
            if method != "GET":
                self._check_origin()
            entry = ROUTES.get((method, path))
            if entry is None:
                raise ApiError(404, "not found")
            fn, needs_auth = entry
            user = self._user() if needs_auth else None
            body = self._body() if method == "POST" else {}
            out = fn(self, user, body, parse_qs(url.query))
            if out is not None:
                self._json(*out)
        except ApiError as e:
            self._json(e.status, {"error": e.message})
        except auth.AuthError as e:
            self._json(e.status, {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._json(500, {"error": "服务器出错了"})
            except Exception:
                pass

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        f = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC.resolve() not in f.parents or not f.is_file():
            raise ApiError(404, "not found")
        data = f.read_bytes()
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        cache = "no-cache" if f.suffix in (".html", ".js", ".css") else "public, max-age=86400"
        extra = {"Cache-Control": cache}
        if f.suffix == ".html":
            extra.update({"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})
        self._headers(200, ctype, len(data), extra)
        self.end_headers()
        self.wfile.write(data)

    # ---- SSE chat --------------------------------------------------------------
    def sse_chat(self, u: dict, body: dict):
        text = clip(str(body.get("text") or ""), 2000).strip()
        if not text:
            raise ApiError(400, "说点什么吧")
        self._headers(200, "text/event-stream; charset=utf-8", None,
                      {"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "close"})
        self.end_headers()
        self.close_connection = True
        with Store(u["id"]) as st:
            for event, data in agent.chat(st, text):
                try:
                    self.wfile.write(f"event: {event}\ndata: {dumps(data)}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return  # client left; the turn is still saved


from routes import ROUTES  # noqa: E402


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8765))
    host = os.environ.get("HOST", "127.0.0.1")
    auth.db()
    if os.environ.get("MANIFEST_SCHEDULER", "1") != "0":
        scheduler.start_background()
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    print(f"显伴 v{VERSION} · http://{host}:{port}  model={llm.config()['model']}  key={'yes' if llm.api_key() else 'NO (replies will fail)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
