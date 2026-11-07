"""按天累计的运行计数，给管理后台看：请求量与耗时、对话并发、模型调用与 token、首页体验漏斗；
另外按用户记模型 token（user_counter），以后商用计费 / 给用户看用量时直接用。

只记数字，不记任何用户内容。计数先攒在内存里，每 10 秒写一次 data/metrics.db，
所以进程重启最多丢 10 秒的数。

「这次模型调用算谁的」：Store(uid) 打开时把 uid 压到当前线程上（push_user），关闭时弹出。
所有模型调用都在某个 with Store(uid) 里、同一个线程上发生，所以 llm 不用改调用方就能记到人头上。
"""
from __future__ import annotations

import sqlite3
import threading
import time

from .util import DATA, day_key

FLUSH_SECONDS = 10

_lock = threading.Lock()
_buf: dict[tuple[str, str], int] = {}
_ubuf: dict[tuple[str, str, str], int] = {}
_local = threading.local()
_peaks: dict[tuple[str, str], int] = {}
_last_flush = time.time()
_conn: sqlite3.Connection | None = None
inflight = 0  # 正在进行的对话（SSE）数


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DATA / "metrics.db", check_same_thread=False, isolation_level=None)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("CREATE TABLE IF NOT EXISTS counter(day TEXT, k TEXT, n INTEGER, PRIMARY KEY(day, k))")
        _conn.execute("CREATE TABLE IF NOT EXISTS user_counter(day TEXT, uid TEXT, k TEXT, n INTEGER, PRIMARY KEY(day, uid, k))")
        _conn.execute("CREATE INDEX IF NOT EXISTS user_counter_uid ON user_counter(uid, day)")
    return _conn


def reset_for_tests() -> None:
    global _conn, inflight
    with _lock:
        _buf.clear()
        _ubuf.clear()
        _peaks.clear()
        inflight = 0
        if _conn is not None:
            _conn.close()
        _conn = None


def bump(k: str, n: int = 1) -> None:
    if not n:
        return
    key = (day_key(), k)
    with _lock:
        _buf[key] = _buf.get(key, 0) + int(n)
    _maybe_flush()


# ---- 当前线程在替谁干活（栈：同一个人的 Store 嵌套打开再关掉，外层仍然算这个人） ----
def _stack() -> list:
    st = getattr(_local, "stack", None)
    if st is None:
        st = _local.stack = []
    return st


def push_user(uid: str) -> None:
    _stack().append(uid)


def pop_user(uid: str) -> None:
    st = _stack()
    for i in range(len(st) - 1, -1, -1):
        if st[i] == uid:
            del st[i]
            return


def reset_user() -> None:
    _local.stack = []


def current_user() -> str | None:
    st = _stack()
    return st[-1] if st else None


def bump_user(uid: str, k: str, n: int = 1) -> None:
    if not n or not uid:
        return
    key = (day_key(), uid, k)
    with _lock:
        _ubuf[key] = _ubuf.get(key, 0) + int(n)
    _maybe_flush()


def peak(k: str, v: int) -> None:
    key = (day_key(), k)
    with _lock:
        if v > _peaks.get(key, 0):
            _peaks[key] = v
    _maybe_flush()


def _maybe_flush() -> None:
    if time.time() - _last_flush >= FLUSH_SECONDS:
        flush()


def flush() -> None:
    global _last_flush
    with _lock:
        buf, ubuf, peaks = dict(_buf), dict(_ubuf), dict(_peaks)
        _buf.clear()
        _ubuf.clear()
        _peaks.clear()
        _last_flush = time.time()
        if not buf and not ubuf and not peaks:
            return
        c = _db()
        c.execute("BEGIN")
        for (day, k), n in buf.items():
            c.execute("INSERT INTO counter(day, k, n) VALUES(?,?,?) ON CONFLICT(day, k) DO UPDATE SET n = n + excluded.n",
                      (day, k, n))
        for (day, uid, k), n in ubuf.items():
            c.execute("INSERT INTO user_counter(day, uid, k, n) VALUES(?,?,?,?) "
                      "ON CONFLICT(day, uid, k) DO UPDATE SET n = n + excluded.n", (day, uid, k, n))
        for (day, k), n in peaks.items():
            c.execute("INSERT INTO counter(day, k, n) VALUES(?,?,?) ON CONFLICT(day, k) DO UPDATE SET n = MAX(n, excluded.n)",
                      (day, k, n))
        c.execute("COMMIT")


def since(first_day: str) -> dict[str, dict[str, int]]:
    """{day: {k: n}} for days >= first_day."""
    flush()
    out: dict[str, dict[str, int]] = {}
    with _lock:
        for day, k, n in _db().execute("SELECT day, k, n FROM counter WHERE day >= ?", (first_day,)):
            out.setdefault(day, {})[k] = n
    return out


def user_totals(first_day: str = "") -> dict[str, dict[str, int]]:
    """{uid: {k: n}} summed over days >= first_day."""
    flush()
    out: dict[str, dict[str, int]] = {}
    with _lock:
        for uid, k, n in _db().execute("SELECT uid, k, SUM(n) FROM user_counter WHERE day >= ? GROUP BY uid, k",
                                       (first_day,)):
            out.setdefault(uid, {})[k] = n
    return out


def user_days(uid: str, first_day: str = "") -> dict[str, dict[str, int]]:
    """{day: {k: n}} for one user."""
    flush()
    out: dict[str, dict[str, int]] = {}
    with _lock:
        for day, k, n in _db().execute("SELECT day, k, n FROM user_counter WHERE uid = ? AND day >= ?", (uid, first_day)):
            out.setdefault(day, {})[k] = n
    return out


def forget_user(uid: str) -> None:
    flush()
    with _lock:
        _db().execute("DELETE FROM user_counter WHERE uid = ?", (uid,))


class chat_span:
    """with chat_span(): ... —— 对话并发、次数、耗时。"""

    def __enter__(self):
        global inflight
        with _lock:
            inflight += 1
            now_in = inflight
        peak("chat_peak", now_in)
        self.t0 = time.time()
        return self

    def __exit__(self, *a):
        global inflight
        with _lock:
            inflight -= 1
        bump("chat")
        bump("chat_ms", int((time.time() - self.t0) * 1000))
