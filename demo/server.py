"""显伴 · 小光 — HTTP server (stdlib only).

Run:  python server.py [port]        (default 8765; production uses 18765)
Env:  MODELFLARE_API_KEY (required for real replies), MANIFEST_DATA (optional)

Every /api/* route except /api/auth/* and /api/health requires a session
cookie. The user's id is taken from that session only; there is no way to
pass a user id in a request.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from core import admin, agent, auth, llm, metrics, onboarding, report, scenes, scheduler
from core.api import VERSION, ApiError
from core.store import Store
from core.util import PUBLIC, ROOT, clip, dumps, iso, load_dotenv

load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

COOKIE = "xg_session"
MAX_BODY = 64 * 1024
try:
    PROXY_HOPS = max(1, int(os.environ.get("MANIFEST_PROXY_HOPS") or 1))   # 我们前面有几层自己的反向代理（见 Handler._ip）
except ValueError:
    PROXY_HOPS = 1
BIG_BODY = {"/api/photo": 6 * 1024 * 1024}   # 瞬间的照片：压过的大图 ≤3MB + 小图，base64 之后大约 4.6MB
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("audio/mpeg", ".mp3")

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
        """限流用的来访地址。X-Forwarded-For 最前面那几段是来访者自己能写的，不能信：
        只有请求是从本机的反向代理（nginx）进来的才看这个头，而且从右往左数——最右边一段是离我们最近的那层代理填的。
        前面还有一层 CDN 时，把 MANIFEST_PROXY_HOPS 设成 2。"""
        peer = self.client_address[0]
        hops = [x.strip() for x in (self.headers.get("X-Forwarded-For") or "").split(",") if x.strip()]
        if not hops or peer not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return peer
        return hops[-min(PROXY_HOPS, len(hops))]

    def _token(self, name: str = COOKIE) -> str | None:
        c = cookies.SimpleCookie()
        try:
            c.load(self.headers.get("Cookie") or "")
        except cookies.CookieError:
            return None
        return c[name].value if name in c else None

    def _admin_cookie(self, token: str | None) -> str:
        attrs = "; Path=/; HttpOnly; SameSite=Strict" + ("; Secure" if self._secure() else "")
        if token is None:
            return f"{admin.COOKIE}=; Max-Age=0" + attrs
        return f"{admin.COOKIE}={token}; Max-Age={admin.TOKEN_HOURS * 3600}" + attrs

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
        self._body_read = True
        n = int(self.headers.get("Content-Length") or 0)
        if n > BIG_BODY.get(urlparse(self.path).path, MAX_BODY):
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
        t0 = time.time()
        self._body_read = False
        metrics.reset_user()
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
                ms = int((time.time() - t0) * 1000)
                metrics.bump("req")
                metrics.bump("req_ms", ms)
                if ms > 1000:
                    metrics.bump("req_slow")
        except (ApiError, auth.AuthError) as e:
            # 没登录、来源不对这类在读请求体之前就拒绝的：体还留在连接里，会把同一条连接上的下一个请求弄坏，所以这次就关掉连接
            unread = method != "GET" and not getattr(self, "_body_read", False) and int(self.headers.get("Content-Length") or 0) > 0
            if unread:
                self.close_connection = True
            self._json(e.status, {"error": getattr(e, "message", None) or str(e)}, {"Connection": "close"} if unread else None)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._json(500, {"error": "服务器出错了"})
            except Exception:
                pass

    def _same_etag(self, etag: str) -> bool:
        """浏览器带来的 If-None-Match 里有没有这一版。前面的 nginx 压缩时会把它改成弱校验（W/"…"），也算。"""
        given = self.headers.get("If-None-Match") or ""
        return any(x.strip().removeprefix("W/") == etag for x in given.split(","))

    def _not_modified(self, etag: str, cache: str):
        """文件没变：只回 304，不带内容。"""
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache)
        self.end_headers()

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        elif path in ("/admin", "/admin/"):
            path = "/admin.html"
        if path == "/js/buildings/all.js":   # 建筑素材库：服务器把目录拼成一个模块（core/town.py）
            from core import town
            data = town.bundle_js()
            etag = '"b-%s"' % hashlib.md5(data).hexdigest()[:16]
            if self._same_etag(etag):
                return self._not_modified(etag, "no-cache")
            self._headers(200, "text/javascript; charset=utf-8", len(data), {"Cache-Control": "no-cache", "ETag": etag})
            self.end_headers()
            self.wfile.write(data)
            return
        f = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC.resolve() not in f.parents or not f.is_file():
            raise ApiError(404, "not found")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        cache = "no-cache" if f.suffix in (".html", ".js", ".css") else "public, max-age=86400"
        # 页面、脚本、样式每次打开都要问一遍有没有新版本（no-cache）。带上 ETag，没变就只回一个 304：
        # 不然每次打开都把七十多个文件、一兆左右的内容重新下一遍，手机上尤其慢。
        info = f.stat()
        etag = '"%x-%x"' % (info.st_mtime_ns, info.st_size)
        rng = (self.headers.get("Range") or "").strip()
        if not rng and self._same_etag(etag):
            return self._not_modified(etag, cache)
        data = f.read_bytes()
        extra = {"Cache-Control": cache, "Accept-Ranges": "bytes", "ETag": etag}
        if f.suffix == ".html":
            extra.update({"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})
        # 按段取（冥想的背景音乐）：iPhone 的 Safari 放音频一定要服务器支持 Range，否则放不出来
        if rng.startswith("bytes=") and "," not in rng:
            a, _, b = rng[6:].partition("-")
            size = len(data)
            try:
                start, end = (size - int(b), size - 1) if a == "" else (int(a), min(size - 1, int(b)) if b else size - 1)
            except ValueError:
                start, end = 0, size - 1
            start = max(0, start)
            if start >= size or start > end:
                self._headers(416, ctype, 0, {"Content-Range": f"bytes */{size}"})
                self.end_headers()
                return
            data = data[start:end + 1]
            self._headers(206, ctype, len(data), {**extra, "Content-Range": f"bytes {start}-{end}/{size}"})
            self.end_headers()
            self.wfile.write(data)
            return
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
        gone = False

        def emit(event, data):
            nonlocal gone
            if gone:
                return   # client left: keep going so the reply (and tool results) still get saved
            try:
                self.wfile.write(f"event: {event}\ndata: {dumps(data)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                gone = True

        try:
            with Store(u["id"]) as st, metrics.chat_span():
                for event, data in agent.chat(st, text, topic=clip(str(body.get("topic") or ""), 40)):
                    emit(event, data)
        except Exception:
            # 响应头已经发出去了，这时再回一个 500 的 JSON 只会把流弄坏：照流的格式说一声出错，正常收尾
            traceback.print_exc()
            emit("error", {"message": "server"})


from routes import ROUTES  # noqa: E402


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128  # 默认只排 5 个，同一瞬间来的连接多了会被拒


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8765))
    host = os.environ.get("HOST", "127.0.0.1")
    auth.db()
    if os.environ.get("MANIFEST_SCHEDULER", "1") != "0":
        scheduler.start_background()
    srv = Server((host, port), Handler)
    print(f"显伴 v{VERSION} · http://{host}:{port}  model={llm.config()['model']}  key={'yes' if llm.api_key() else 'NO (replies will fail)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
