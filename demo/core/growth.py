"""成长系统：经验账本、等级、宠物分化、全功能徽章、每日任务。

规则（与 v0.3 讨论稿一致，全部由后端计算，模型只能读）：
  - 经验按「来源 + 引用」记账：同一件事不重复计分。
  - 每日总上限 120；行动 / 好消息 / 显化练习 / 签到 每类 30。
  - 宠物是独立养成对象，与小光（聊天形象）无关。

宠物路线：光蛋 →(100) 团子 →(310) 分化 →(650) 成年。
分化时看「你更常做哪类事」：行动多 → 焰尾狐；好消息多 → 花角鹿；练习多 → 云鲸；
三类都不偏科 → 隐藏形态 星灵。分化之前，后两段只显示剪影，但亲和度一直可见——
用户看得清「往哪走」，又保留揭晓的惊喜。
"""
from __future__ import annotations

from .util import day_key, iso, now

DAILY_CAP = 120
SOURCE_CAP = 30
LEVEL_XP = 40

SOURCES = {
    "action": {"label": "行动", "cap": SOURCE_CAP, "amount": 10, "hint": "完成一小步", "quest": "完成 1 个小步"},
    "good": {"label": "好消息", "cap": SOURCE_CAP, "amount": 6, "hint": "记下一件好事", "quest": "记下 1 条好消息"},
    "practice": {"label": "练习", "cap": SOURCE_CAP, "amount": 12, "hint": "场景 / 冥想 / 感恩", "quest": "做 1 次显化练习"},
    "checkin": {"label": "陪伴", "cap": SOURCE_CAP, "amount": 8, "hint": "每天来聊一次", "quest": "和小光聊一句"},
}

AT = {"egg": 0, "baby": 100, "young": 310, "adult": 650}

BRANCHES = {
    "fox": {"name": "焰尾狐", "young": "小焰", "source": "action", "color": "#f2a541",
            "tag": "说到做到的行动派", "line": "尾巴尖的火苗，是你一次次真的去做了。"},
    "deer": {"name": "花角鹿", "young": "花苞", "source": "good", "color": "#f08bb0",
             "tag": "会看见生活的记录者", "line": "每记下一件好事，角上就开一朵花。"},
    "whale": {"name": "云鲸", "young": "云朵", "source": "practice", "color": "#8fc7e8",
              "tag": "向内走的练习者", "line": "安静下来的时候，它就浮起来了。"},
    "star": {"name": "星灵", "young": "星点", "source": "", "color": "#a99bff", "secret": True,
             "tag": "隐藏形态 · 样样都没落下", "line": "行动、记录、练习都没偏废，才会遇见它。"},
}

AFFINITY = ("action", "good", "practice")


# ---------------------------------------------------------------- ledger ----

def _rows_today(st) -> list[dict]:
    return [dict(r) for r in st.c.execute("SELECT * FROM xp WHERE day=? ORDER BY created_at DESC", (day_key(),))]


def total_xp(st) -> int:
    return int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM xp").fetchone()[0])


def by_source_total(st) -> dict:
    out = {k: 0 for k in SOURCES}
    for r in st.c.execute("SELECT source, SUM(amount) AS n FROM xp GROUP BY source"):
        out[r["source"]] = int(r["n"] or 0)
    return out


def award(st, source: str, ref: str = "", note: str = "", amount: int | None = None) -> dict:
    """Credit XP under the caps; idempotent per (source, ref). The returned
    dict tells the truth either way (amount 0 + capped / duplicate)."""
    if source not in SOURCES:
        return {"ok": False, "reason": "unknown source"}
    amount = SOURCES[source]["amount"] if amount is None else max(0, int(amount))
    if ref:
        dup = st.c.execute("SELECT * FROM xp WHERE source=? AND ref=?", (source, ref)).fetchone()
        if dup:
            return {"ok": True, "duplicate": True, "amount": 0, "note": "这件事已经计过分了", "row": dict(dup)}
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
    cur = st.c.execute(
        "INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
        (day_key(), source, allowed, ref or "", note, iso()))
    row = dict(st.c.execute("SELECT * FROM xp WHERE rowid=?", (cur.lastrowid,)).fetchone())
    total = total_xp(st)
    st.set_profile({"xp": total})
    _maybe_branch(st, total)
    return {"ok": True, "amount": allowed, "row": row, "today": used_all + allowed, "cap": DAILY_CAP,
            "partial": amount > allowed, "total": total}


# ------------------------------------------------------------- pet logic ----

def affinity(st) -> list[dict]:
    tot = by_source_total(st)
    s = sum(tot[k] for k in AFFINITY) or 1
    return [{"id": k, "label": SOURCES[k]["label"], "xp": tot[k], "share": round(tot[k] / s, 3),
             "branch": next(b for b, v in BRANCHES.items() if v["source"] == k)} for k in AFFINITY]


def leaning(aff: list[dict]) -> str:
    shares = [a["share"] for a in aff]
    if sum(a["xp"] for a in aff) and max(shares) < 0.42 and min(shares) >= 0.24:
        return "star"
    top = max(aff, key=lambda a: (a["share"], a["id"] == "action"))
    return top["branch"]


def _maybe_branch(st, total: int) -> None:
    """The branch is decided once, the moment the pet reaches 310 XP."""
    p = st.profile()
    if total >= AT["young"] and not p.get("pet_branch"):
        b = leaning(affinity(st))
        st.set_profile({"pet_branch": b, "pet_branch_at": iso()})
        st.log("growth", f"小芽分化成了「{BRANCHES[b]['young']}」（{BRANCHES[b]['name']}幼体）")


def stage_of(total: int, branch: str) -> dict:
    b = BRANCHES.get(branch) or {}
    if total >= AT["adult"] and b:
        return {"key": f"{branch}-2", "tier": 3, "name": b["name"], "art": f"pet-{branch}-2", "line": b["line"]}
    if total >= AT["young"] and b:
        return {"key": f"{branch}-1", "tier": 2, "name": b["young"], "art": f"pet-{branch}-1",
                "line": "还小，但已经看得出你是哪一种人了。"}
    if total >= AT["baby"]:
        return {"key": "baby", "tier": 1, "name": "团子", "art": "pet-baby", "line": "破壳了，正在悄悄长大。"}
    return {"key": "egg", "tier": 0, "name": "光蛋", "art": "pet-egg", "line": "里面有一点光，在等第一件事发生。"}


def level_of(total: int) -> dict:
    lv = total // LEVEL_XP + 1
    into = total % LEVEL_XP
    return {"lv": lv, "into": into, "need": LEVEL_XP, "pct": round(into / LEVEL_XP, 3)}


def tree(total: int, branch: str, lean: str) -> list[dict]:
    """Nodes for the evolution map. Unreached forms are silhouettes; the secret
    branch stays a question mark until someone actually becomes it."""
    def st_(at):
        return "done" if total >= at else "locked"
    nodes = [
        {"id": "egg", "name": "光蛋", "at": 0, "art": "pet-egg", "state": "done", "col": 0},
        {"id": "baby", "name": "团子", "at": AT["baby"], "art": "pet-baby", "state": st_(AT["baby"]), "col": 1},
    ]
    for b, v in BRANCHES.items():
        chosen = branch == b
        hidden = v.get("secret") and not chosen
        for tier, at in ((1, AT["young"]), (2, AT["adult"])):
            state = "done" if chosen and total >= at else "locked"
            if branch and not chosen:
                state = "closed"   # another branch was taken
            nodes.append({"id": f"{b}-{tier}", "branch": b, "tier": tier, "at": at, "col": 1 + tier,
                          "name": ("？？？" if hidden else (v["young"] if tier == 1 else v["name"])),
                          "art": f"pet-{b}-{tier}", "state": state, "hidden": bool(hidden),
                          "silhouette": state in ("locked", "closed"),
                          "leaning": (not branch and lean == b)})
    reached = [n for n in nodes if n["state"] == "done"]
    if reached:
        reached[-1]["current"] = True
    return nodes


def state(st, consume: bool = True) -> dict:
    """Pure-ish read for the client and the model. Two side effects, both
    one-shot: a newly reached form is reported once as `evolved`, newly earned
    badges once as `badges_new` — that's what drives the celebration UI."""
    total = total_xp(st)
    _maybe_branch(st, total)
    p = st.profile()
    branch = p.get("pet_branch") or ""
    aff = affinity(st)
    lean = branch or leaning(aff)
    stg = stage_of(total, branch)
    rows = _rows_today(st)
    by_src = {k: 0 for k in SOURCES}
    for r in rows:
        by_src[r["source"]] = by_src.get(r["source"], 0) + int(r["amount"])
    nxt = next(((k, v) for k, v in (("baby", AT["baby"]), ("young", AT["young"]), ("adult", AT["adult"]))
                if total < v), None)

    evolved = None
    seen = p.get("pet_stage_seen") or ""
    if seen and seen != stg["key"]:
        evolved = {"from": seen, "to": stg["key"], "name": stg["name"], "art": stg["art"],
                   "branch": branch, "branch_name": (BRANCHES.get(branch) or {}).get("name", ""),
                   "tag": (BRANCHES.get(branch) or {}).get("tag", "")}
    if consume and seen != stg["key"]:
        st.set_profile({"pet_stage_seen": stg["key"]})
    if not consume:
        evolved = None

    blist, new_badges = badges(st, total=total, stage=stg, persist=consume)
    quests = [{"id": k, "label": v["quest"], "got": by_src[k], "need": v["amount"],
               "done": by_src[k] >= min(v["amount"], v["cap"])} for k, v in SOURCES.items()]

    return {
        "total": total,
        "level": level_of(total),
        "today": {"total": sum(by_src.values()), "cap": DAILY_CAP, "by_source": by_src},
        "sources": [{"id": k, **v, "used": by_src.get(k, 0)} for k, v in SOURCES.items()],
        "quests": quests,
        "quests_done": sum(q["done"] for q in quests),
        "stage": stg,
        "next": ({"id": nxt[0], "at": nxt[1], "name": {"baby": "团子", "young": "分化", "adult": "成年"}[nxt[0]]}
                 if nxt else None),
        "to_next": (nxt[1] - total) if nxt else 0,
        "prev_at": max([v for v in AT.values() if v <= total] or [0]),
        "branch": branch,
        "branch_info": ({"id": branch, **BRANCHES[branch]} if branch else None),
        "leaning": lean,
        "leaning_info": {"id": lean, **BRANCHES[lean]} if not branch else None,
        "affinity": aff,
        "tree": tree(total, branch, lean),
        "branches": [{"id": k, **({**v, "name": "？？？", "young": "？？？", "tag": "隐藏形态"} if v.get("secret") and branch != k else v)}
                     for k, v in BRANCHES.items()],
        "pet_name": p.get("pet_name") or "小芽",
        "badges": blist,
        "badges_new": new_badges,
        "evolved": evolved,
        "ledger": _recent(st, 30),
    }


def _recent(st, limit: int = 30) -> list[dict]:
    rows = [dict(r) for r in st.c.execute("SELECT * FROM xp ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))]
    for r in rows:
        r["label"] = SOURCES.get(r["source"], {}).get("label", "经验")
    return rows


# ---------------------------------------------------------------- badges ----

# (id, name, how, category, icon, metric, need, hidden)
BADGES = [
    ("talk_1", "第一句话", "和小光说第一句话", "对话", "chat", "user_msgs", 1, False),
    ("talk_30", "话匣子", "和小光聊满 30 句", "对话", "chat", "user_msgs", 30, False),
    ("remember_1", "记住我", "第一次让小光记住一件事", "记忆", "memory", "explicit_mem", 1, False),
    ("fix_1", "说清楚", "确认、否定或修改一条记忆", "记忆", "memory", "memory_fix", 1, False),
    ("digest_1", "被好好整理", "第一次日终整理", "记忆", "moon", "digests", 1, False),
    ("step_1", "第一步", "完成第一个小步", "计划", "flag", "steps_done", 1, False),
    ("step_7", "七次落地", "累计完成 7 个小步", "计划", "flag", "steps_done", 7, False),
    ("step_30", "习惯成形", "累计完成 30 个小步", "计划", "flag", "steps_done", 30, False),
    ("good_1", "第一颗星", "记下第一条好消息", "好消息", "star", "good", 1, False),
    ("good_10", "收集星星", "记下 10 条好消息", "好消息", "star", "good", 10, False),
    ("good_30", "星罐满了", "记下 30 条好消息", "好消息", "star", "good", 30, False),
    ("rest_1", "休息也算", "第一次给自己放一天假", "陪伴", "moon", "rest", 1, False),
    ("comeback", "回来了", "休息之后，又完成了一小步", "陪伴", "sun", "comeback", 1, False),
    ("days_7", "一周", "陪伴满 7 天", "陪伴", "sun", "days", 7, False),
    ("days_14", "半个月", "陪伴满 14 天", "陪伴", "sun", "days", 14, False),
    ("days_30", "一个月", "陪伴满 30 天", "陪伴", "sun", "days", 30, False),
    ("practice_1", "静下来", "完成一次显化练习", "练习", "lotus", "practices", 1, False),
    ("practice_5", "练习者", "完成 5 次显化练习", "练习", "lotus", "practices", 5, False),
    ("relearn", "重新认识", "完成「重新认识我」", "练习", "compass", "relearn", 1, False),
    ("explorer", "都试过了", "完成 4 种不同的引导场景", "练习", "compass", "scene_kinds", 4, False),
    ("read_1", "开卷", "在心灵学堂读一篇文章", "学堂", "book", "reads", 1, False),
    ("read_5", "求知", "在心灵学堂读 5 篇文章", "学堂", "book", "reads", 5, False),
    ("report_1", "回头看", "打开一次蜕变报告", "报告", "report", "report_open", 1, False),
    ("hatch", "破壳", "小芽孵化成团子", "成长", "egg", "tier", 1, False),
    ("branch", "分化", "小芽长出了自己的样子", "成长", "egg", "tier", 2, False),
    ("adult", "长大了", "小芽长成成年形态", "成长", "egg", "tier", 3, False),
    ("secret", "隐藏形态", "遇见星灵", "成长", "spark", "star_branch", 1, True),
]

CATEGORY_ORDER = ["对话", "计划", "好消息", "练习", "记忆", "学堂", "报告", "陪伴", "成长"]


def metrics(st, total: int | None = None, stage: dict | None = None) -> dict:
    q = lambda sql, *a: int(st.c.execute(sql, a).fetchone()[0] or 0)
    p = st.profile()
    rest_days = [r[0] for r in st.c.execute("SELECT DISTINCT day FROM record WHERE type='rest' ORDER BY day")]
    comeback = 0
    if rest_days:
        comeback = q("SELECT COUNT(*) FROM step WHERE status='done' AND substr(done_at,1,10) > ?", rest_days[0])
    stg = stage or stage_of(total if total is not None else total_xp(st), p.get("pet_branch") or "")
    return {
        "user_msgs": q("SELECT COUNT(*) FROM msg WHERE role='user'"),
        "explicit_mem": q("SELECT COUNT(*) FROM memory WHERE source='chat:explicit'"),
        "memory_fix": st.stat("memory_fix"),
        "digests": q("SELECT COUNT(*) FROM digest"),
        "steps_done": q("SELECT COUNT(*) FROM step WHERE status='done'"),
        "good": q("SELECT COUNT(*) FROM record WHERE type='good'"),
        "rest": len(rest_days),
        "comeback": 1 if comeback else 0,
        "days": int(st.counts()["days"]),
        "practices": q("SELECT COUNT(*) FROM scene_run WHERE status='done'"),
        "relearn": q("SELECT COUNT(*) FROM scene_run WHERE status='done' AND scene='relearn'"),
        "scene_kinds": q("SELECT COUNT(DISTINCT scene) FROM scene_run WHERE status='done'"),
        "reads": q("SELECT COUNT(*) FROM article_read"),
        "report_open": st.stat("report_open"),
        "tier": stg["tier"],
        "star_branch": 1 if p.get("pet_branch") == "star" else 0,
    }


def badges(st, total: int | None = None, stage: dict | None = None, persist: bool = True) -> tuple[list[dict], list[dict]]:
    m = metrics(st, total, stage)
    have = {r["id"]: r["at"] for r in st.c.execute("SELECT id, at FROM badge")}
    out, new = [], []
    for bid, name, how, cat, icon, metric, need, hidden in BADGES:
        got = min(m.get(metric, 0), need)
        earned = m.get(metric, 0) >= need
        at = have.get(bid)
        if earned and not at and persist:
            at = iso()
            st.c.execute("INSERT OR IGNORE INTO badge(id, at) VALUES(?,?)", (bid, at))
            new.append({"id": bid, "name": name, "how": how, "cat": cat, "icon": icon})
        out.append({"id": bid, "name": ("？？？" if hidden and not earned else name),
                    "how": ("继续走下去，会遇见的" if hidden and not earned else how),
                    "cat": cat, "icon": icon, "got": got, "need": need,
                    "earned": earned, "at": at or "", "hidden": hidden and not earned})
    out.sort(key=lambda b: (CATEGORY_ORDER.index(b["cat"]), b["need"]))
    return out, new


def rules_text() -> str:
    return ("经验规则：完成一小步 +10（行动），记一条好消息 +6，完成一次显化练习 +12，"
            "每天第一次来聊 +8（陪伴）。四类每类每天最多 30，每天总共最多 120；同一件事不重复计分。"
            f"每 {LEVEL_XP} 经验升一级。宠物小芽：100 经验孵化成团子，310 经验分化——"
            "行动最多长成焰尾狐，好消息最多长成花角鹿，练习最多长成云鲸，三样都不偏科会遇见一个隐藏形态；"
            "650 经验长成成年形态。分化方向在 310 那一刻决定，之前可以在成长页看到自己现在更偏向哪一边。"
            "隐藏形态的名字不要提前透露。")
