"""按天累计的运行计数，给管理后台看：请求量与耗时、对话并发、模型调用与 token、首页体验漏斗。

只记数字，不记任何用户内容。计数先攒在内存里，每 10 秒写一次 data/metrics.db，
所以进程重启最多丢 10 秒的数。
"""
from __future__ import annotations

import sqlite3
import threading
import time

from .util import DATA, day_key

FLUSH_SECONDS = 10

_lock = threading.Lock()
_buf: dict[tuple[str, str], int] = {}
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
    return _conn


def reset_for_tests() -> None:
    global _conn, inflight
    with _lock:
        _buf.clear()
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
        buf, peaks = dict(_buf), dict(_peaks)
        _buf.clear()
        _peaks.clear()
        _last_flush = time.time()
        if not buf and not peaks:
            return
        c = _db()
        c.execute("BEGIN")
        for (day, k), n in buf.items():
            c.execute("INSERT INTO counter(day, k, n) VALUES(?,?,?) ON CONFLICT(day, k) DO UPDATE SET n = n + excluded.n",
                      (day, k, n))
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
