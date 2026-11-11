"""小光的定时任务（例行任务 / 提醒）。

和每个用户自己的 SQLite 分开，所有用户的任务放在一张中心表里（data/tasks.db），
按 (enabled, run_at) 建索引：调度线程每 30 秒只做一次「有没有到点的」查询，
用户再多也只是一条索引查询；到点的任务才去打开那个用户的库。

两种任务：
  - remind：到点发一句提醒，不调模型，零成本；
  - ai：到点让小光按 TA 的情况写一句（每天早上的鼓励、每周日的复盘邀请），每次一次模型调用。
重复方式：once（一次）/ daily（每天）/ weekdays（工作日）/ weekly（每周几，days="1,3,5"，周一=1）。
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta

from .util import DATA, clip, iso, new_id, now, parse_iso, TZ

MAX_PER_USER = 20
REPEATS = ("once", "daily", "weekdays", "weekly")
WEEK = "一二三四五六日"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DATA / "tasks.db", check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS task(
              id TEXT PRIMARY KEY, uid TEXT, title TEXT, kind TEXT, message TEXT,
              repeat TEXT, days TEXT, time TEXT, run_at TEXT, enabled INTEGER DEFAULT 1,
              source TEXT, created_at TEXT, last_run_at TEXT, runs INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS task_due ON task(enabled, run_at);
            CREATE INDEX IF NOT EXISTS task_uid ON task(uid);
        """)
    return _conn


def reset_for_tests() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None


# ---------------------------------------------------------------- 时间 ----

def _hm(t: str) -> tuple[int, int]:
    try:
        h, m = (int(x) for x in str(t).strip().split(":")[:2])
    except (TypeError, ValueError):
        raise ValueError("时间格式要像 21:30")
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("时间不对")
    return h, m


def _clock(t) -> str:
    """校验并写成 HH:MM（「9:5」「 21:30 」都收成一样的写法，显示出来才整齐）。"""
    h, m = _hm(t)
    return f"{h:02d}:{m:02d}"


def _days(days) -> list[int]:
    if isinstance(days, str):
        days = [x for x in days.replace("，", ",").split(",") if x.strip()]
    elif isinstance(days, (int, float)):       # 模型有时只给一个数字（「每周三」→ 3）
        days = [int(days)]
    elif not isinstance(days, (list, tuple, set)):
        days = []
    out = sorted({int(x) for x in days if str(x).strip().isdigit() and 1 <= int(x) <= 7})
    return out


def next_run(t: dict, after: datetime) -> datetime | None:
    """这个任务在 after 之后的下一次运行时间；一次性任务跑过就没有下一次。"""
    if t["repeat"] == "once":
        at = parse_iso(t["run_at"])
        return at if at and at > after and not t.get("last_run_at") else None
    h, m = _hm(t["time"])
    days = _days(t.get("days") or "")
    for k in range(0, 8):
        d = (after + timedelta(days=k)).replace(hour=h, minute=m, second=0, microsecond=0)
        if d <= after:
            continue
        wd = d.isoweekday()
        if t["repeat"] == "weekdays" and wd > 5:
            continue
        if t["repeat"] == "weekly" and days and wd not in days:
            continue
        return d
    return None


def describe(t: dict) -> str:
    if t["repeat"] == "once":
        at = parse_iso(t["run_at"])
        if not at:
            return "一次"
        today = now().date()
        day = "今天" if at.date() == today else "明天" if at.date() == today + timedelta(days=1) else f"{at.month}月{at.day}日"
        return f"{day} {at:%H:%M} · 一次"
    if t["repeat"] == "daily":
        return f"每天 {t['time']}"
    if t["repeat"] == "weekdays":
        return f"工作日 {t['time']}"
    ds = _days(t.get("days") or "")
    return ("每周" + "、".join("周" + WEEK[d - 1] for d in ds) if ds else "每周") + f" {t['time']}"


def public(t: dict) -> dict:
    d = {k: t[k] for k in ("id", "title", "kind", "message", "repeat", "days", "time", "run_at", "enabled", "source", "last_run_at", "runs")}
    d["enabled"] = bool(d["enabled"])
    d["when"] = describe(t)
    return d


# ---------------------------------------------------------------- 增删改 ----

def add(uid: str, title: str, *, kind: str = "remind", message: str = "", repeat: str = "once",
        time: str = "", days=None, in_minutes=None, date: str = "", source: str = "chat") -> dict:
    title = clip((title or "").strip(), 30)
    if not title:
        raise ValueError("写一下要提醒什么")
    if kind not in ("remind", "ai"):
        kind = "remind"
    if repeat not in REPEATS:
        repeat = "once"
    with _lock:
        n = db().execute("SELECT COUNT(*) FROM task WHERE uid=? AND enabled=1", (uid,)).fetchone()[0]
    if n >= MAX_PER_USER:
        raise ValueError(f"最多同时开着 {MAX_PER_USER} 个例行任务，可以先关掉几个")
    ref = now()
    run_at = None
    if repeat == "once":
        if in_minutes not in (None, ""):
            try:
                mins = int(float(in_minutes))
            except (TypeError, ValueError):
                raise ValueError("几分钟后？")
            if not (1 <= mins <= 60 * 24 * 30):
                raise ValueError("只能定 1 分钟到 30 天以内的提醒")
            run_at = (ref + timedelta(minutes=mins)).replace(microsecond=0)
            time = f"{run_at:%H:%M}"
        else:
            h, m = _hm(time)
            if date:
                try:
                    d = datetime.fromisoformat(str(date)[:10]).replace(tzinfo=TZ)
                except ValueError:
                    raise ValueError("日期不对")
                run_at = d.replace(hour=h, minute=m)
            else:
                run_at = ref.replace(hour=h, minute=m, second=0, microsecond=0)
                if run_at <= ref:
                    run_at += timedelta(days=1)
            if run_at <= ref:
                raise ValueError("这个时间已经过去了")
            time = f"{h:02d}:{m:02d}"
    else:
        time = _clock(time)
    t = {"id": new_id("t"), "uid": uid, "title": title, "kind": kind, "message": clip(message or "", 200),
         "repeat": repeat, "days": ",".join(str(x) for x in _days(days)), "time": time, "run_at": "",
         "enabled": 1, "source": source, "created_at": iso(), "last_run_at": "", "runs": 0}
    if run_at is None:
        nr = next_run(t, ref)
        run_at = nr
    t["run_at"] = iso(run_at)
    with _lock:
        db().execute("INSERT INTO task(id, uid, title, kind, message, repeat, days, time, run_at, enabled, source, created_at, last_run_at, runs) "
                     "VALUES(:id,:uid,:title,:kind,:message,:repeat,:days,:time,:run_at,:enabled,:source,:created_at,:last_run_at,:runs)", t)
    return public(t)


def get(uid: str, tid: str) -> dict | None:
    with _lock:
        r = db().execute("SELECT * FROM task WHERE id=? AND uid=?", (tid, uid)).fetchone()
    return dict(r) if r else None


def list_for(uid: str) -> list[dict]:
    with _lock:
        rows = [dict(r) for r in db().execute("SELECT * FROM task WHERE uid=? ORDER BY enabled DESC, run_at", (uid,))]
    # 跑完的一次性提醒只留最近 5 条
    done_once = [r for r in rows if r["repeat"] == "once" and not r["enabled"]][5:]
    return [public(r) for r in rows if r not in done_once]


def set_enabled(uid: str, tid: str, on: bool) -> dict | None:
    t = get(uid, tid)
    if not t:
        return None
    run_at = t["run_at"]
    if on:
        if t["repeat"] == "once" and t["last_run_at"]:
            raise ValueError("这个一次性提醒已经响过了，可以新建一个")
        nr = next_run(t, now())
        if not nr:
            raise ValueError("这个时间已经过去了")
        run_at = iso(nr)
    with _lock:
        db().execute("UPDATE task SET enabled=?, run_at=? WHERE id=?", (1 if on else 0, run_at, tid))
    return public(get(uid, tid))


def edit(uid: str, tid: str, patch: dict) -> dict | None:
    t = get(uid, tid)
    if not t:
        return None
    if patch.get("title"):
        t["title"] = clip(str(patch["title"]).strip(), 30)
    if "message" in patch:
        t["message"] = clip(str(patch["message"] or ""), 200)
    if patch.get("repeat") in REPEATS and patch["repeat"] != "once":
        t["repeat"] = patch["repeat"]
    if patch.get("time"):
        t["time"] = _clock(patch["time"])
    if "days" in patch:
        t["days"] = ",".join(str(x) for x in _days(patch["days"]))
    if t["repeat"] != "once":
        nr = next_run(t, now())
        t["run_at"] = iso(nr) if nr else t["run_at"]
    with _lock:
        db().execute("UPDATE task SET title=?, message=?, repeat=?, time=?, days=?, run_at=? WHERE id=?",
                     (t["title"], t["message"], t["repeat"], t["time"], t["days"], t["run_at"], tid))
    return public(get(uid, tid))


def delete(uid: str, tid: str) -> bool:
    with _lock:
        return db().execute("DELETE FROM task WHERE id=? AND uid=?", (tid, uid)).rowcount > 0


def delete_all(uid: str) -> int:
    with _lock:
        return db().execute("DELETE FROM task WHERE uid=?", (uid,)).rowcount


def find(uid: str, text: str) -> dict | None:
    t = (text or "").strip()
    if not t:
        return None
    for r in list_for(uid):
        if r["enabled"] and (t in r["title"] or r["title"] in t):
            return r
    return None


# ---------------------------------------------------------------- 到点执行 ----

def due(ref: datetime | None = None, limit: int = 200) -> list[dict]:
    ref = ref or now()
    with _lock:
        return [dict(r) for r in db().execute(
            "SELECT * FROM task WHERE enabled=1 AND run_at<=? ORDER BY run_at LIMIT ?", (iso(ref), limit))]


def mark_ran(t: dict, ref: datetime | None = None) -> None:
    ref = ref or now()
    t = {**t, "last_run_at": iso(ref)}
    nr = None if t["repeat"] == "once" else next_run(t, ref)
    with _lock:
        db().execute("UPDATE task SET last_run_at=?, runs=runs+1, run_at=?, enabled=? WHERE id=?",
                     (iso(ref), iso(nr) if nr else t["run_at"], 1 if nr else 0, t["id"]))
