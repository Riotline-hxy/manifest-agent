"""管理后台：只读的用户情况与运行统计。

登录：服务器 .env 里的 MANIFEST_ADMIN_KEY。登录后发一个 12 小时有效的签名 cookie
（xg_admin），不进用户账号体系；换掉 key 就让所有后台登录失效。没配 key 时后台整个关闭。

看得到：账号、建档时选的方向、各类数量、按天的活跃与消息数、操作记录（activity）。
看不到：对话原文、记忆原文、密码。读用户库一律只读打开。
能改的只有一件事：删除用户（账号、会话、数据文件夹、例行任务、用量计数，全部删掉，不能恢复）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import platform
import shutil
import sqlite3
import sys
import threading
import time
from datetime import timedelta

from . import auth, growth, metrics, tasks
from .api import VERSION
from .util import DATA, day_key, loads, now, parse_iso

COOKIE = "xg_admin"
TOKEN_HOURS = 12
BACKGROUND = "kind NOT IN ('proactive', 'task') AND NOT (kind = 'memory' AND text LIKE '整理了%')"
PROFILE_KEYS = ("agent_name", "intent_primary", "intent_why", "persona", "theme", "care_style", "proactive", "onboarded")
STARTED = time.time()



# ---- auth -------------------------------------------------------------------

def key() -> str:
    return os.environ.get("MANIFEST_ADMIN_KEY") or ""


def check_key(given: str) -> bool:
    k = key()
    return bool(k) and hmac.compare_digest(str(given or "").encode(), k.encode())


def _sig(exp: int) -> str:
    return hmac.new(key().encode(), f"admin:{exp}".encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = int(time.time()) + TOKEN_HOURS * 3600
    return f"{exp}.{_sig(exp)}"


def check_token(tok: str | None) -> bool:
    if not key() or not tok or "." not in tok:
        return False
    exp, sig = tok.split(".", 1)
    return exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, _sig(int(exp)))


# ---- per-user scan ----------------------------------------------------------

def _ro(path):
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _dir_bytes(d) -> int:
    try:
        return sum(f.stat().st_size for f in d.iterdir() if f.is_file())
    except OSError:
        return 0


def _scan(user: dict) -> dict:
    row = {"id": user["id"], "username": user["username"], "kind": user["kind"], "created_at": user["created_at"],
           "profile": {}, "msgs": 0, "msg_days": {}, "active_days": [], "last_active": "", "steps": 0, "steps_done": 0,
           "good": 0, "memories": 0, "habits": 0, "xp": 0, "level": 1, "bytes": 0}
    d = DATA / "u" / user["id"]
    f = d / "mind.db"
    if not f.is_file():
        return row
    row["bytes"] = _dir_bytes(d)
    try:
        c = _ro(f)
    except sqlite3.Error:
        return row
    try:
        q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
        prof = {r["k"]: loads(r["v"], r["v"]) for r in c.execute("SELECT k, v FROM profile")}
        row["profile"] = {k: prof.get(k) for k in PROFILE_KEYS}
        days = {r[0]: r[1] for r in c.execute(
            "SELECT substr(created_at, 1, 10), COUNT(*) FROM msg WHERE role = 'user' GROUP BY 1")}
        act = {r[0] for r in c.execute(f"SELECT DISTINCT substr(at, 1, 10) FROM activity WHERE {BACKGROUND}")}
        row["msg_days"] = days
        row["msgs"] = sum(days.values())
        row["active_days"] = sorted(set(days) | act)
        row["last_active"] = max(q("SELECT COALESCE(MAX(created_at), '') FROM msg WHERE role = 'user'"),
                                 q(f"SELECT COALESCE(MAX(at), '') FROM activity WHERE {BACKGROUND}"))
        row["steps"] = q("SELECT COUNT(*) FROM step")
        row["steps_done"] = q("SELECT COUNT(*) FROM step WHERE status = 'done'")
        row["good"] = q("SELECT COUNT(*) FROM record WHERE type = 'good'")
        row["memories"] = q("SELECT COUNT(*) FROM memory WHERE status = 'active'")
        row["habits"] = q("SELECT COUNT(*) FROM habit WHERE archived = 0")
        row["xp"] = q("SELECT COALESCE(SUM(amount), 0) FROM xp")
        row["level"] = growth.level_of(row["xp"])["lv"]
    except sqlite3.Error:
        pass
    finally:
        c.close()
    return row


def _rows() -> list[dict]:
    """每次现扫（100 个用户在服务器上约 0.15 秒）：缓存会让删除确认里的数量和实际对不上。"""
    users = [dict(r) for r in auth.db().execute("SELECT id, username, kind, created_at FROM users")]
    return [_scan(u) for u in users]


TOKEN_KEYS = ("llm_calls", "llm_tokens", "llm_tokens_in", "llm_tokens_out", "llm_tokens_cached", "llm_tokens_chat", "llm_tokens_bg")


def _tok(t: dict | None) -> dict:
    t = t or {}
    return {k.replace("llm_", ""): t.get(k, 0) for k in TOKEN_KEYS}


def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("msg_days", "active_days")} | {"days_active": len(r["active_days"])}


def _label(r: dict) -> str:
    return r["username"] or f"体验账号 {r['id'][2:8]}"


# ---- views ------------------------------------------------------------------

def _days(n: int) -> list[str]:
    today = now().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _proc_rss_mb() -> float | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


def _system(today: dict) -> dict:
    disk = shutil.disk_usage(DATA)
    data_bytes = 0
    for p in DATA.rglob("*"):
        try:
            if p.is_file():
                data_bytes += p.stat().st_size
        except OSError:
            pass
    req = today.get("req", 0)
    chats = today.get("chat", 0)
    return {
        "version": VERSION, "python": platform.python_version(), "platform": sys.platform,
        "uptime_s": int(time.time() - STARTED), "rss_mb": _proc_rss_mb(),
        "load": list(os.getloadavg()) if hasattr(os, "getloadavg") else None, "cpus": os.cpu_count(),
        "data_mb": round(data_bytes / 1048576, 1), "disk_free_gb": round(disk.free / 1073741824, 1),
        "threads": threading.active_count(), "chat_now": metrics.inflight,
        "req_today": req, "req_avg_ms": round(today.get("req_ms", 0) / req) if req else None,
        "req_slow_today": today.get("req_slow", 0),
        "chat_today": chats, "chat_avg_s": round(today.get("chat_ms", 0) / chats / 1000, 1) if chats else None,
        "chat_peak_today": today.get("chat_peak", 0),
    }


def overview(days: int = 30) -> dict:
    days = max(7, min(int(days or 30), 90))
    rows = _rows()
    span = _days(days)
    first = span[0]
    m = metrics.since(first)
    today = day_key()
    by_day = {d: {"day": d, "new_member": 0, "new_guest": 0, "active": 0, "msgs": 0} for d in span}
    for r in rows:
        d = (r["created_at"] or "")[:10]
        if d in by_day:
            by_day[d]["new_member" if r["kind"] == "member" else "new_guest"] += 1
        if r["kind"] != "member":  # 旧的体验账号带 15 天示例数据，算进来会虚高
            continue
        for d in r["active_days"]:
            if d in by_day:
                by_day[d]["active"] += 1
        for d, n in r["msg_days"].items():
            if d in by_day:
                by_day[d]["msgs"] += n
    for d in span:
        mm = m.get(d, {})
        by_day[d].update(tokens=mm.get("llm_tokens", 0), cached=mm.get("llm_tokens_cached", 0), llm_calls=mm.get("llm_calls", 0), llm_err=mm.get("llm_err", 0),
                         req=mm.get("req", 0), chat=mm.get("chat", 0))

    members = [r for r in rows if r["kind"] == "member"]

    def active_within(n):
        cut = _days(n)[0]
        return sum(1 for r in members if any(d >= cut for d in r["active_days"]))

    funnel_keys = [("trial_start", "开始体验"), ("trial_step", "拿到一小步"), ("trial_signup", "注册并带走"), ("onboard", "完成建档")]
    totals = {k: sum(m.get(d, {}).get(k, 0) for d in span) for k, _ in funnel_keys}
    return {
        "today": today, "days": days,
        "users": {
            "total": len(rows), "members": len(members), "guests": len(rows) - len(members),
            "onboarded": sum(1 for r in members if r["profile"].get("onboarded")),
            "returning": sum(1 for r in members if len(r["active_days"]) >= 2),
        },
        "active": {"today": active_within(1), "week": active_within(7), "month": active_within(30)},
        "msgs_today": by_day[today]["msgs"],
        "series": [by_day[d] for d in span],
        "funnel": [{"k": k, "label": label, "n": totals[k]} for k, label in funnel_keys],
        "intents": _top([r["profile"].get("intent_primary") for r in members if r["profile"].get("intent_primary")]),
        "top_tokens": _top_tokens(rows, first),
        "model": {"calls": sum(by_day[d]["llm_calls"] for d in span), "tokens": sum(by_day[d]["tokens"] for d in span),
                  "cached": sum(by_day[d]["cached"] for d in span),
                  "errors": sum(by_day[d]["llm_err"] for d in span)},
        "system": _system(m.get(today, {})),
    }


def _top(values: list[str], n: int = 8) -> list[dict]:
    counts: dict[str, int] = {}
    for v in values:
        counts[str(v)] = counts.get(str(v), 0) + 1
    return [{"label": k, "n": c} for k, c in sorted(counts.items(), key=lambda x: -x[1])[:n]]


def _top_tokens(rows: list[dict], first: str, n: int = 8) -> list[dict]:
    names = {r["id"]: _label(r) for r in rows}
    tot = metrics.user_totals(first)
    ranked = sorted(((uid, t.get("llm_tokens", 0)) for uid, t in tot.items() if uid in names), key=lambda x: -x[1])
    return [{"label": names[uid], "id": uid, "n": v} for uid, v in ranked[:n] if v]


def users() -> list[dict]:
    rows = sorted(_rows(), key=lambda r: r["last_active"] or r["created_at"] or "", reverse=True)
    all_time = metrics.user_totals("")
    month = metrics.user_totals(_days(30)[0])
    return [_public(r) | {"tokens": all_time.get(r["id"], {}).get("llm_tokens", 0),
                          "tokens_30d": month.get(r["id"], {}).get("llm_tokens", 0),
                          "calls_30d": month.get(r["id"], {}).get("llm_calls", 0)} for r in rows]


def user(uid: str) -> dict | None:
    u = auth.get_user(uid)
    if not u:
        return None
    r = _scan(u)
    span = _days(30)
    act, f = [], DATA / "u" / uid / "mind.db"
    if f.is_file():
        c = _ro(f)
        try:
            act = [dict(x) for x in c.execute("SELECT kind, text, at FROM activity ORDER BY at DESC LIMIT 40")]
        except sqlite3.Error:
            pass
        finally:
            c.close()
    sessions = auth.db().execute("SELECT COUNT(*) FROM sessions WHERE user_id = ? AND expires_at > ?",
                                 (uid, now().isoformat(timespec="seconds"))).fetchone()[0]
    first = parse_iso(r["active_days"][0] + "T00:00:00") if r["active_days"] else None
    tdays = metrics.user_days(uid, span[0])
    return {**_public(r), "sessions": sessions, "first_active": first.date().isoformat() if first else "",
            "series": [{"day": d, "msgs": r["msg_days"].get(d, 0), "active": d in r["active_days"],
                        **{f"t_{k}": v for k, v in _tok(tdays.get(d)).items()}} for d in span],
            "tokens": {"all": _tok(metrics.user_totals("").get(uid)), "d30": _tok(metrics.user_totals(span[0]).get(uid))},
            "activity": act}


# ---- 删除 -------------------------------------------------------------------

def delete_user(uid: str) -> bool:
    """不可恢复。账号与会话先删，之后的请求立刻登不上；再删数据文件夹和其他痕迹。"""
    from .store import UID_RE
    if not UID_RE.match(uid or ""):
        return False
    if not auth.delete_user(uid):
        return False
    tasks.delete_all(uid)
    metrics.forget_user(uid)
    shutil.rmtree(DATA / "u" / uid, ignore_errors=True)
    print(f"[admin] deleted user {uid}", file=sys.stderr)
    return True


def guest_ids() -> list[str]:
    return [r["id"] for r in auth.db().execute("SELECT id FROM users WHERE kind = 'guest'")]
