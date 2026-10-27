"""Accounts and sessions.

user_id is only ever derived from a server-side session looked up by an
HttpOnly cookie, never accepted from the client. Passwords use PBKDF2-SHA256
(stdlib; 200k iterations). Session tokens are random 32-byte values; only
their SHA-256 is stored, so a leaked auth.db can't be replayed as cookies.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from datetime import timedelta

from .util import DATA, iso, now, parse_iso

SESSION_DAYS = 30
PBKDF2_ITER = 200_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_一-鿿]{2,20}$")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DATA / "auth.db", check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
              id TEXT PRIMARY KEY,
              username TEXT UNIQUE COLLATE NOCASE,
              pw_hash TEXT,
              kind TEXT NOT NULL DEFAULT 'member',   -- member | guest
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions(
              token_hash TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
            """
        )
    return _conn


def reset_for_tests() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None
    _attempts.clear()


# ---- password hashing ------------------------------------------------------

def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    try:
        algo, it, salt, want = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), want)
    except (ValueError, TypeError):
        return False


# ---- login rate limit (per key: ip or username) ------------------------------

_attempts: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 8, 600


def too_many(key: str) -> bool:
    t = time.time()
    xs = [x for x in _attempts.get(key, []) if t - x < WINDOW]
    _attempts[key] = xs
    return len(xs) >= MAX_FAILS


def note_fail(key: str) -> None:
    _attempts.setdefault(key, []).append(time.time())


# ---- users -----------------------------------------------------------------

class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _new_uid() -> str:
    return "u_" + secrets.token_hex(8)


def register(username: str, password: str) -> dict:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError("用户名需 2–20 位，可用中文、字母、数字或下划线")
    if len(password or "") < 6:
        raise AuthError("密码至少 6 位")
    uid = _new_uid()
    with _lock:
        try:
            db().execute(
                "INSERT INTO users(id, username, pw_hash, kind, created_at) VALUES(?,?,?,?,?)",
                (uid, username, hash_password(password), "member", iso()),
            )
        except sqlite3.IntegrityError:
            raise AuthError("这个用户名已被使用", 409)
    return {"id": uid, "username": username, "kind": "member"}


def create_guest() -> dict:
    uid = _new_uid()
    with _lock:
        db().execute("INSERT INTO users(id, username, pw_hash, kind, created_at) VALUES(?,?,?,?,?)",
                     (uid, None, None, "guest", iso()))
    return {"id": uid, "username": None, "kind": "guest"}


def claim_guest(uid: str, username: str, password: str) -> dict:
    """Turn the current guest into a member, keeping all their data."""
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError("用户名需 2–20 位，可用中文、字母、数字或下划线")
    if len(password or "") < 6:
        raise AuthError("密码至少 6 位")
    with _lock:
        row = db().execute("SELECT kind FROM users WHERE id=?", (uid,)).fetchone()
        if not row or row["kind"] != "guest":
            raise AuthError("当前账号不是体验账号", 400)
        try:
            db().execute("UPDATE users SET username=?, pw_hash=?, kind='member' WHERE id=?",
                         (username, hash_password(password), uid))
        except sqlite3.IntegrityError:
            raise AuthError("这个用户名已被使用", 409)
    return {"id": uid, "username": username, "kind": "member"}


def login(username: str, password: str, ip: str) -> dict:
    key_u, key_ip = "u:" + (username or "").lower(), "ip:" + ip
    if too_many(key_u) or too_many(key_ip):
        raise AuthError("尝试次数太多，请 10 分钟后再试", 429)
    row = db().execute("SELECT id, username, pw_hash, kind FROM users WHERE username=?",
                       ((username or "").strip(),)).fetchone()
    if not row or not verify_password(password or "", row["pw_hash"]):
        note_fail(key_u); note_fail(key_ip)
        raise AuthError("用户名或密码不对", 401)
    return {"id": row["id"], "username": row["username"], "kind": row["kind"]}


def get_user(uid: str) -> dict | None:
    row = db().execute("SELECT id, username, kind, created_at FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


# ---- sessions --------------------------------------------------------------

def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(uid: str) -> str:
    token = secrets.token_urlsafe(32)
    exp = now() + timedelta(days=SESSION_DAYS)
    with _lock:
        db().execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES(?,?,?,?)",
                     (_h(token), uid, iso(), iso(exp)))
    return token


def session_user(token: str | None) -> dict | None:
    if not token or len(token) > 200:
        return None
    row = db().execute(
        "SELECT u.id, u.username, u.kind, u.created_at, s.expires_at FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token_hash=?", (_h(token),)).fetchone()
    if not row:
        return None
    exp = parse_iso(row["expires_at"])
    if exp is None or exp < now():
        end_session(token)
        return None
    return {"id": row["id"], "username": row["username"], "kind": row["kind"], "created_at": row["created_at"]}


def end_session(token: str | None) -> None:
    if token:
        with _lock:
            db().execute("DELETE FROM sessions WHERE token_hash=?", (_h(token),))


def all_user_ids() -> list[str]:
    return [r["id"] for r in db().execute("SELECT id FROM users")]
