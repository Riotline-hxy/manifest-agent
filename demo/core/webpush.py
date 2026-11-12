"""Web Push（网页关着也能推到手机）。只用标准库。

做法：推一条「空」消息（RFC 8030，不带内容）。手机被叫醒后，service worker 用登录 cookie
来 /api/push/latest 取最新那句话再显示。这样
  - 服务端只需要 VAPID 签名（RFC 8292，ES256 = ECDSA P-256 + SHA-256），不用做内容加密；
  - 消息原文不经过谷歌 / 苹果的推送服务器。

VAPID 密钥第一次用时生成，存在 data/vapid.json（跟用户数据一起备份，部署不会换掉它；
换了密钥，所有人的订阅都会失效）。订阅存在 data/push.db：endpoint → uid。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .util import DATA, iso

SUBJECT = os.environ.get("MANIFEST_PUSH_SUBJECT") or "https://manifest.noryx.cn"
TTL = 6 * 3600          # 手机离线超过 6 小时，这条就不补发了
TIMEOUT = 10
MAX_FAILS = 5           # 连续失败这么多次（非 404/410）也删掉

# ---- P-256 -------------------------------------------------------------------
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return x3, (lam * (x1 - x3) - y1) % P


def _mul(k: int, pt=G):
    out = None
    while k:
        if k & 1:
            out = _add(out, pt)
        pt = _add(pt, pt)
        k >>= 1
    return out


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _pub_bytes(d: int) -> bytes:
    x, y = _mul(d)
    return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


def sign(d: int, msg: bytes) -> bytes:
    """ECDSA P-256 / SHA-256, JOSE form (r || s, 64 bytes)."""
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    while True:
        k = secrets.randbelow(N - 1) + 1
        r = _mul(k)[0] % N
        if not r:
            continue
        s = pow(k, -1, N) * (e + r * d) % N
        if s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


# ---- keys --------------------------------------------------------------------
_key_lock = threading.Lock()
_keys: dict | None = None


def keys() -> dict:
    """{"d": int, "pub": base64url(65-byte uncompressed point)}"""
    global _keys
    with _key_lock:
        if _keys is None:
            f = DATA / "vapid.json"
            if f.is_file():
                raw = json.loads(f.read_text())
                d = int(raw["d"], 16)
            else:
                DATA.mkdir(parents=True, exist_ok=True)
                d = secrets.randbelow(N - 1) + 1
                f.write_text(json.dumps({"d": format(d, "064x"), "created_at": iso()}))
                try:
                    os.chmod(f, 0o600)
                except OSError:
                    pass
            _keys = {"d": d, "pub": b64u(_pub_bytes(d))}
        return _keys


def vapid_header(endpoint: str) -> str:
    u = urlparse(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SUBJECT},
                           separators=(",", ":")).encode())
    k = keys()
    jwt = f"{head}.{body}.{b64u(sign(k['d'], f'{head}.{body}'.encode()))}"
    return f"vapid t={jwt}, k={k['pub']}"


# ---- subscriptions -----------------------------------------------------------
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DATA / "push.db", check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("""CREATE TABLE IF NOT EXISTS sub(
            endpoint TEXT PRIMARY KEY, uid TEXT NOT NULL, p256dh TEXT, auth TEXT, ua TEXT,
            created_at TEXT, last_ok_at TEXT, fails INTEGER DEFAULT 0)""")
        _conn.execute("CREATE INDEX IF NOT EXISTS sub_uid ON sub(uid)")
    return _conn


def reset_for_tests() -> None:
    global _conn, _keys
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
    _keys = None


# 订阅地址是前端传来的。不限制的话，任何登录用户都能让服务器定时去敲一个任意的 https 地址（还会跟着跳转，可能跳进内网）。
# 所以只认各家浏览器真正的推送服务；以后遇到新的，在 .env 里用 MANIFEST_PUSH_HOSTS=a.com,b.com 加。
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com",                 # Chrome / Edge / 安卓上的大多数浏览器
              "push.services.mozilla.com",                                    # Firefox
              "push.apple.com",                                               # Safari（iOS 16.4+ / macOS）
              "notify.windows.com",                                           # 旧版 Edge
              ) + tuple(h.strip().lower() for h in (os.environ.get("MANIFEST_PUSH_HOSTS") or "").split(",") if h.strip())
MAX_DEVICES = 10        # 一个人最多留这么多台设备的订阅，再多就顶掉最早的


def _valid_endpoint(ep: str) -> bool:
    try:
        u = urlparse(ep)
        host, port = (u.hostname or "").lower(), u.port
    except ValueError:
        return False
    return (u.scheme == "https" and len(ep) <= 1000 and port in (None, 443)
            and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS))


def subscribe(uid: str, sub: dict, ua: str = "") -> None:
    ep = str((sub or {}).get("endpoint") or "")
    if not _valid_endpoint(ep):
        raise ValueError("订阅信息不对")
    k = (sub or {}).get("keys") or {}
    k = k if isinstance(k, dict) else {}
    with _lock:
        # 同一台设备换了账号登录：endpoint 归新账号
        _db().execute("""INSERT INTO sub(endpoint, uid, p256dh, auth, ua, created_at, fails) VALUES(?,?,?,?,?,?,0)
            ON CONFLICT(endpoint) DO UPDATE SET uid=excluded.uid, p256dh=excluded.p256dh, auth=excluded.auth,
            ua=excluded.ua, fails=0""", (ep, uid, str(k.get("p256dh") or "")[:200], str(k.get("auth") or "")[:100],
                                         (ua or "")[:200], iso()))
        _db().execute("DELETE FROM sub WHERE uid=? AND endpoint NOT IN "
                      "(SELECT endpoint FROM sub WHERE uid=? ORDER BY created_at DESC, rowid DESC LIMIT ?)", (uid, uid, MAX_DEVICES))


def unsubscribe(uid: str, endpoint: str) -> None:
    with _lock:
        _db().execute("DELETE FROM sub WHERE endpoint=? AND uid=?", (endpoint, uid))


def forget_user(uid: str) -> None:
    with _lock:
        _db().execute("DELETE FROM sub WHERE uid=?", (uid,))


def subs(uid: str) -> list[dict]:
    with _lock:
        return [dict(r) for r in _db().execute("SELECT * FROM sub WHERE uid=?", (uid,))]


def counts() -> dict[str, int]:
    with _lock:
        return {r[0]: r[1] for r in _db().execute("SELECT uid, COUNT(*) FROM sub GROUP BY uid")}


# ---- send --------------------------------------------------------------------
def _post(endpoint: str, headers: dict) -> int:
    req = urllib.request.Request(endpoint, data=b"", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def send(endpoint: str, ttl: int = TTL, urgency: str = "normal") -> int:
    return _post(endpoint, {"TTL": str(ttl), "Urgency": urgency, "Content-Length": "0",
                            "Authorization": vapid_header(endpoint)})


def notify(uid: str, ttl: int = TTL, urgency: str = "normal") -> dict:
    """叫醒这个人的所有设备。返回 {"sent": n, "failed": n, "removed": n}。从不抛异常。"""
    out = {"sent": 0, "failed": 0, "removed": 0}
    try:
        targets = subs(uid)
    except sqlite3.Error:
        return out
    for s in targets:
        code = send(s["endpoint"], ttl, urgency)
        with _lock:
            if 200 <= code < 300:
                out["sent"] += 1
                _db().execute("UPDATE sub SET last_ok_at=?, fails=0 WHERE endpoint=?", (iso(), s["endpoint"]))
            elif code in (404, 410) or s["fails"] + 1 >= MAX_FAILS:
                out["removed"] += 1
                _db().execute("DELETE FROM sub WHERE endpoint=?", (s["endpoint"],))
            else:
                out["failed"] += 1
                _db().execute("UPDATE sub SET fails=fails+1 WHERE endpoint=?", (s["endpoint"],))
        if not 200 <= code < 300:
            print(f"[push] {uid} {urlparse(s['endpoint']).netloc} -> {code}", file=sys.stderr)
    return out


def notify_async(uid: str, **kw) -> None:
    """不阻塞调用方（调度线程 / 请求）；没有订阅时连线程都不开。"""
    try:
        if not subs(uid):
            return
    except sqlite3.Error:
        return
    threading.Thread(target=notify, args=(uid,), kwargs=kw, daemon=True).start()
