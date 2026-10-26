"""成长系统：经验账本、每日上限、宠物进化。

设计约束（来自 10-22 会议 + v0.3 讨论稿）：
  - 经验值由后端按「来源 + 日期」记账，模型无权临时加分。
  - 每日总上限 120；行动 / 好消息 / 显化练习 / 签到 每类 30。
  - 同一件事拆成多条记录不重复加分：账本按 (source, ref) 去重，
    并且每类在当天封顶后不再累加。
  - 宠物是独立养成对象，不等于小光的聊天形象。
"""
from __future__ import annotations

from .util import day_key, now

DAILY_CAP = 120
SOURCE_CAP = 30

SOURCES = {
    "action": {"label": "行动", "cap": SOURCE_CAP, "amount": 10, "hint": "完成一小步"},
    "good": {"label": "好消息", "cap": SOURCE_CAP, "amount": 6, "hint": "记下一件好事"},
    "practice": {"label": "显化练习", "cap": SOURCE_CAP, "amount": 12, "hint": "场景 / 冥想 / 感恩"},
    "checkin": {"label": "签到", "cap": SOURCE_CAP, "amount": 8, "hint": "每天来聊一次"},
}

# 形态节点。at 为累计经验；420 处必须选择分支。
STAGES = [
    {"id": "seed", "name": "种子", "at": 0, "art": "stage0",
     "line": "一颗还没决定长成什么的种子。"},
    {"id": "tadpole", "name": "游星", "at": 80, "art": "stage1",
     "line": "第一次朝着一个方向游。"},
    {"id": "turtle", "name": "雏龟", "at": 200, "art": "stage2",
     "line": "慢，但甲壳已经硬了。"},
    {"id": "branch", "name": "化形", "at": 360, "branch": True, "art": "stage2",
     "line": "走到这里，你要选一条路。"},
    {"id": "adult", "name": "成年", "at": 700, "art": "",
     "line": "它长成了你选的那一种。"},
]

BRANCHES = {
    "qinglong": {"name": "青龙", "juvenile": "qinglong_juvenile", "adult": "qinglong_adult",
                 "tag": "行动与开阔", "line": "从水里起来，顺着云走。"},
    "jiuwei": {"name": "九尾", "juvenile": "jiuwei_juvenile", "adult": "jiuwei_adult",
               "tag": "感受与关系", "line": "尾巴会一条一条长出来。"},
    "baize": {"name": "白泽", "juvenile": "baize_juvenile", "adult": "baize_adult",
              "tag": "理解与表达", "line": "知道得越多，越安静。"},
}

BADGES = [
    ("first_step", "第一步", "完成第一小步"),
    ("seven_steps", "七次落地", "累计完成 7 个小步"),
    ("good_5", "会看见", "记下 5 条好消息"),
    ("practice_3", "练过三次", "完成 3 次显化练习"),
    ("week_one", "满七天", "陪伴满 7 天"),
    ("branch_chosen", "化形", "为宠物选择分支"),
]


def _rows_today(st) -> list[dict]:
    return [dict(r) for r in st.c.execute(
        "SELECT * FROM xp WHERE day=? ORDER BY created_at DESC", (day_key(),))]


def state(st) -> dict:
    """What the client renders, and what the model may quote. Pure read."""
    total = int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM xp").fetchone()[0])
    today_rows = _rows_today(st)
    by_source = {k: 0 for k in SOURCES}
    for r in today_rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + int(r["amount"])
    today_total = sum(by_source.values())
    p = st.profile()

    branch_id = p.get("pet_branch") or ""
    stage = STAGES[0]
    for s in STAGES:
        if total >= s["at"]:
            stage = s
    next_stage = next((s for s in STAGES if s["at"] > total), None)

    if stage["id"] == "branch" and not branch_id:
        art, stage_name, line = stage["art"], "化形", "四种可能停在原地——先选一种。"
    elif branch_id and total >= 360:
        b = BRANCHES.get(branch_id) or BRANCHES["qinglong"]
        stage_name = "幼年·" + b["name"]
        line = b["line"]
        art = b["juvenile"]
        if total >= 700:
            stage_name, art = "成年·" + b["name"], b["adult"]
        next_stage = None if total >= 700 else {"id": "adult", "name": "成年", "at": 700}
    else:
        art, stage_name, line = stage["art"], stage["name"], stage["line"]

    return {
        "total": total,
        "today": {"total": today_total, "cap": DAILY_CAP, "by_source": by_source},
        "sources": [{"id": k, **v, "used": by_source.get(k, 0)} for k, v in SOURCES.items()],
        "stage": {"id": stage["id"], "name": stage_name, "art": art, "line": line},
        "next": next_stage,
        "to_next": max(0, next_stage["at"] - total) if next_stage else 0,
        "needs_branch": bool(stage["id"] == "branch" and not branch_id),
        "branch": branch_id,
        "branch_name": (BRANCHES.get(branch_id) or {}).get("name", ""),
        "branches": [{"id": k, **v} for k, v in BRANCHES.items()],
        "pet_name": p.get("pet_name") or "小芽",
        "badges": badges(st, total),
        "ledger": _recent(st, 24),
    }


def _recent(st, limit: int = 24) -> list[dict]:
    rows = [dict(r) for r in st.c.execute(
        "SELECT * FROM xp ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))]
    for r in rows:
        r["label"] = SOURCES.get(r["source"], {}).get("label", "经验")
    return rows


def award(st, source: str, ref: str = "", note: str = "", amount: int | None = None) -> dict:
    """Credit XP under the caps. Idempotent per (source, ref).

    Returns the ledger row plus how the cap acted, so the UI and the model can
    both say the truth: 「+10」 or 「今天这一类已经满了」.
    """
    if source not in SOURCES:
        return {"ok": False, "reason": "unknown source"}
    amount = SOURCES[source]["amount"] if amount is None else max(0, int(amount))
    if ref:
        dup = st.c.execute("SELECT * FROM xp WHERE source=? AND ref=?", (source, ref)).fetchone()
        if dup:
            return {"ok": True, "duplicate": True, "amount": 0, "note": "这件事已经计过分了",
                    "row": dict(dup)}

    rows = _rows_today(st)
    used_src = sum(int(r["amount"]) for r in rows if r["source"] == source)
    used_all = sum(int(r["amount"]) for r in rows)
    allowed = min(amount, SOURCES[source]["cap"] - used_src, DAILY_CAP - used_all)
    if allowed <= 0:
        return {"ok": True, "capped": True, "amount": 0,
                "note": ("今天的总经验已经到 120 了" if used_all >= DAILY_CAP
                         else f"今天「{SOURCES[source]['label']}」的 30 已经满了"),
                "today": used_all}
    if amount > allowed:
        note = (note + f"（今日这类剩 {allowed}）").strip()

    t = now().isoformat(timespec="seconds")
    cur = st.c.execute(
        "INSERT INTO xp(id, day, source, amount, ref, note, created_at) "
        "VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
        (day_key(), source, allowed, ref or "", note, t))
    row = dict(st.c.execute("SELECT * FROM xp WHERE rowid=?", (cur.lastrowid,)).fetchone())
    st.set_profile({"xp": int(st.profile().get("xp") or 0) + allowed})
    return {"ok": True, "amount": allowed, "row": row,
            "today": used_all + allowed, "cap": DAILY_CAP, "partial": amount > allowed}


def set_branch(st, branch_id: str) -> dict:
    if branch_id not in BRANCHES:
        return {"ok": False, "reason": "没有这个分支"}
    total = int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM xp").fetchone()[0])
    if total < 360:
        return {"ok": False, "reason": "经验还不够，到 360 才能化形", "need": 360 - total}
    st.set_profile({"pet_branch": branch_id})
    st.log("growth", "宠物选择了分支：" + BRANCHES[branch_id]["name"])
    return {"ok": True, "branch": branch_id}


def badges(st, total: int | None = None) -> list[dict]:
    done_steps = int(st.c.execute("SELECT COUNT(*) FROM step WHERE status='done'").fetchone()[0])
    good = int(st.c.execute("SELECT COUNT(*) FROM record WHERE type='good'").fetchone()[0])
    practices = int(st.c.execute("SELECT COUNT(*) FROM scene_run WHERE status='done'").fetchone()[0])
    days = int(st.counts()["days"])
    earned = {
        "first_step": done_steps >= 1,
        "seven_steps": done_steps >= 7,
        "good_5": good >= 5,
        "practice_3": practices >= 3,
        "week_one": days >= 7,
        "branch_chosen": bool(st.profile().get("pet_branch")),
    }
    return [{"id": i, "name": n, "how": h, "earned": bool(earned.get(i))} for i, n, h in BADGES]


def rules_text() -> str:
    return ("经验规则：完成一小步 +10（行动），记一条好消息 +6，完成一次显化练习 +12，"
            "每天第一次来聊 +8（签到）。四类每类每天最多 30，每天总共最多 120；"
            "同一件事不会重复计分。累计 80 到「游星」，200 到「雏龟」，"
            "360 可以化形选分支（青龙 / 九尾 / 白泽），700 长成成年形态。")
