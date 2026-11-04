"""成长系统：经验（长期成长）· 金币（建造小镇的建材）· 每日任务。数值的来龙去脉见 docs/成长数值设计.md。

规则全部由后端计算，前端和小光只能读：
  - 经验按「来源 + 引用」记账，同一件事不重复计分。真实的事每天最多 120；行动 / 记录 / 练习 / 陪伴 每类 30。
    每日任务另给一点经验（最多 38），不占上面的 120。
  - 等级只升不降：前几级很快，往后每级多 15 经验，到 500 为止（满额大约三天一级）。
    老账号按旧算法到过的等级记成「保底」，换算法也不会掉级。
    等级决定小镇的土地有多大、能建哪些东西（town.py）。
  - 金币跟着真实做成的事走：完成小步、习惯打卡、到达里程碑、记好消息或瞬间、做完练习，每类每天有上限。
    和小光聊天只给经验、不给金币，免得为了金币刷聊天。
  - 每日任务每天四件：一件固定（行动），三件从任务池里按天轮换，只挑这个人用得上的；做了真实的事就自动完成、
    自动发经验和金币，每天 0 点换新，一天只发一次。它们和愿望里的小步是两套东西，换新不会碰小步。
  - 第一次做成一件真实的事，送一份「第一份建材」，正好够盖第一栋小木屋。
  - 休息不扣任何东西。偷懒日里每日任务的行动类先暂停，不挡全勤奖励。
  - 发经验、发金币、结算每日任务在同一个事务里完成；按 ref 去重，重复请求不会多发。
旧的宠物进化和徽章已经下架；旧数据（badge 表、pet_* 画像）原样留在库里，不再读。
"""
from __future__ import annotations

import random

from .util import day_key, iso

DAILY_CAP = 120
SOURCE_CAP = 30
LEVEL_BASE, LEVEL_STEP, LEVEL_CAP = 40, 15, 500   # 从 Lv n 升到 n+1 要 40 + 15×(n-1) 经验，最多 500（满额大约三天）
_UNCAPPED = -(-(LEVEL_CAP - LEVEL_BASE) // LEVEL_STEP)  # 前 31 级还没到 500

SOURCES = {
    "action": {"label": "行动", "cap": SOURCE_CAP, "amount": 10, "hint": "完成小步、习惯打卡或到达里程碑"},
    "good": {"label": "记录", "cap": SOURCE_CAP, "amount": 6, "hint": "小确幸、内心戏或计划里的瞬间"},
    "practice": {"label": "练习", "cap": SOURCE_CAP, "amount": 12, "hint": "场景 / 冥想 / 感恩"},
    "checkin": {"label": "陪伴", "cap": SOURCE_CAP, "amount": 8, "hint": "每天来聊一次"},
}

# 金币价目表。发经验的地方都用这几种 ref 前缀（routes / agent），金币按前缀算，这里是唯一的一份。
# 没列出的前缀（每天来聊的 day:）不给金币。
COIN_EVENTS = {
    "step": ("action", 10),      # 完成一个小步
    "habit": ("action", 8),      # 习惯打卡
    "ms": ("milestone", 30),     # 到达里程碑
    "rec": ("record", 4),        # 小确幸 / 内心戏
    "moment": ("record", 5),     # 轨迹上的瞬间
    "scene": ("practice", 10),   # 做完一次练习
}
COIN_CAP = {"action": 40, "milestone": 60, "record": 12, "practice": 20}   # 每类每天最多
COIN_LABEL = {"action": "行动", "milestone": "里程碑", "record": "记录", "practice": "练习"}
FIRST_GIFT = 40                 # = 小木屋的价钱

# ---- 每日任务池：slot 决定它坐哪一格；needs 是「用得上才出现」；act 表示偷懒日暂停 ----
DAILY = {
    "act": {"slot": "core", "label": "完成 1 个小步或打一次卡", "hint": "愿望里的小步、习惯、里程碑都算", "xp": 5, "coins": 10, "go": "plan", "act": True},
    "good": {"slot": "record", "label": "记下一件小确幸", "hint": "今天让你嘴角上扬的一件小事", "xp": 5, "coins": 8, "go": "goodnews"},
    "meme": {"slot": "record", "label": "记一段内心戏", "hint": "脑子里冒出来的想法、吐槽都算", "xp": 5, "coins": 8, "go": "goodnews"},
    "moment": {"slot": "record", "label": "在愿望的轨迹上留下一个瞬间", "hint": "为愿望做了什么、当时什么感受", "xp": 5, "coins": 8, "go": "plan", "needs": "wish"},
    "pick": {"slot": "explore", "label": "做今天推荐的练习", "hint": "点子页最上面那张", "xp": 8, "coins": 12, "go": "ideas", "weight": 3},
    "practice": {"slot": "explore", "label": "做 1 次练习", "hint": "冥想、感恩、聊聊愿望，挑一个", "xp": 8, "coins": 12, "go": "ideas"},
    "read": {"slot": "explore", "label": "在心灵学堂读一篇", "hint": "挑一篇还没读过的", "xp": 8, "coins": 12, "go": "academy", "needs": "unread"},
    "plan": {"slot": "explore", "label": "给愿望想一个新的小步", "hint": "自己加，或者让小光帮你想", "xp": 8, "coins": 12, "go": "plan", "needs": "few_steps", "weight": 3},
    "reflect": {"slot": "explore", "label": "写一段阶段回望", "hint": "蜕变计划里的「阶段回望」", "xp": 8, "coins": 12, "go": "plan", "needs": "moments"},
    "act3": {"slot": "stretch", "label": "今天做到 3 件行动", "hint": "小步、打卡、里程碑加起来", "xp": 10, "coins": 18, "go": "plan", "act": True},
    "record2": {"slot": "stretch", "label": "记下 2 件好事", "hint": "小确幸、内心戏、瞬间都算", "xp": 10, "coins": 18, "go": "goodnews"},
    "wish2": {"slot": "stretch", "label": "在 2 个愿望上都往前走一步", "hint": "两个愿望各做一件", "xp": 10, "coins": 18, "go": "plan", "act": True, "needs": "wishes2"},
    "habit2": {"slot": "stretch", "label": "给 2 个不同的习惯打卡", "hint": "习惯在蜕变计划的「今天」里", "xp": 10, "coins": 18, "go": "plan", "act": True, "needs": "habits2"},
}
SLOTS = ("core", "record", "explore", "stretch")
DAILY_BONUS = {"xp": 10, "coins": 20}


# ---------------------------------------------------------------- 经验和等级 ----

def _rows_today(st) -> list[dict]:
    return [dict(r) for r in st.c.execute("SELECT * FROM xp WHERE day=? ORDER BY created_at DESC", (day_key(),))]


def total_xp(st) -> int:
    return int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM xp").fetchone()[0])


def level_cost(lv: int) -> int:
    return min(LEVEL_CAP, LEVEL_BASE + LEVEL_STEP * (lv - 1))


def xp_for_level(lv: int) -> int:
    """到 Lv lv 一共要多少经验。"""
    n = max(0, lv - 1)
    m = min(n, _UNCAPPED)
    return LEVEL_BASE * m + LEVEL_STEP * m * (m - 1) // 2 + (n - m) * LEVEL_CAP


def level_of(total: int, floor: int = 1) -> dict:
    lv = 1
    while xp_for_level(lv + 1) <= total:
        lv += 1
    lv = max(lv, int(floor or 1))          # 老账号的保底等级
    need = level_cost(lv)
    into = max(0, total - xp_for_level(lv))
    return {"lv": lv, "into": into, "need": need, "to_next": xp_for_level(lv + 1) - total, "pct": round(min(1, into / need), 3)}


def level(st) -> dict:
    return level_of(total_xp(st), int(st.profile().get("level_floor") or 1))


# ---------------------------------------------------------------- 金币 ----

def coins(st) -> int:
    return int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM coin").fetchone()[0])


def _coin(st, kind: str, amount: int, ref: str, note: str) -> int:
    """记一笔金币（在 st.tx() 里调用）。ref 相同的只记一次，返回这次真记上的数。"""
    if ref and st.c.execute("SELECT 1 FROM coin WHERE ref=?", (ref,)).fetchone():
        return 0
    st.c.execute("INSERT INTO coin(id, day, kind, amount, ref, note, created_at) "
                 "VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)", (day_key(), kind, int(amount), ref or "", note, iso()))
    return int(amount)


def add_coins(st, kind: str, amount: int, ref: str, note: str) -> int:
    with st.tx():
        return _coin(st, kind, amount, ref, note)


def spend(st, amount: int, ref: str, note: str) -> bool:
    """扣金币（在 st.tx() 里调用）。余额不够就抛 ValueError；同一个 ref 已经扣过返回 False。"""
    if st.c.execute("SELECT 1 FROM coin WHERE ref=?", (ref,)).fetchone():
        return False
    have = coins(st)
    if have < amount:
        raise ValueError(f"金币还差 {amount - have}")
    _coin(st, "buy", -int(amount), ref, note)
    return True


def _event_coins(st, ref: str, note: str) -> tuple[int, str]:
    kind, base = COIN_EVENTS.get((ref or "").split(":", 1)[0], (None, 0))
    if not kind:
        return 0, ""
    used = int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM coin WHERE day=? AND kind=?", (day_key(), kind)).fetchone()[0])
    n = max(0, min(base, COIN_CAP[kind] - used))
    if not n:
        return 0, f"今天「{COIN_LABEL[kind]}」的金币已经满了"
    return _coin(st, kind, n, ref, note), ""


def _first_gift(st) -> int:
    """第一次做成一件真实的事：送够盖第一栋小木屋的建材。老账号开镇时已经换过金币，不再送。"""
    if st.c.execute("SELECT 1 FROM coin WHERE kind IN ('first','migrate') LIMIT 1").fetchone():
        return 0
    return _coin(st, "first", FIRST_GIFT, "first", "第一份建材")


# ---------------------------------------------------------------- 每日任务 ----

def _facts(st, day: str) -> dict:
    """今天真实发生、真记上经验的事（重复的、撤销又重做的都不算）。"""
    rows = [dict(r) for r in st.c.execute("SELECT source, ref FROM xp WHERE day=? AND amount>0 AND source!='daily'", (day,))]
    act = [r["ref"] for r in rows if r["source"] == "action"]
    good = [r["ref"] for r in rows if r["source"] == "good"]
    first = st.c.execute("SELECT id FROM wish WHERE archived=0 ORDER BY sort, created_at LIMIT 1").fetchone()
    first = first[0] if first else ""
    wishes = set()
    for ref in act:
        kind, _, rest = ref.partition(":")
        oid = rest.split(":")[0]
        table = {"step": "step", "habit": "habit", "ms": "milestone"}.get(kind)
        if table:
            r = st.c.execute(f"SELECT wish_id FROM {table} WHERE id=?", (oid,)).fetchone()
            wishes.add((r[0] if r else "") or first)
    types = []
    for ref in good:
        if ref.startswith("moment:"):
            types.append("moment")
        elif ref.startswith("rec:"):
            r = st.c.execute("SELECT type FROM record WHERE id=?", (ref[4:],)).fetchone()
            types.append(r[0] if r else "good")
    scenes = []
    for r in rows:
        if r["source"] == "practice" and r["ref"].startswith("scene:"):
            s = st.c.execute("SELECT scene FROM scene_run WHERE id=?", (r["ref"][6:],)).fetchone()
            scenes.append(s[0] if s else "")
    like = day + "%"
    return {
        "act": len(act), "wishes": len(wishes - {""}),
        "habits": len({ref.split(":")[1] for ref in act if ref.startswith("habit:")}),
        "good": types.count("good"), "meme": types.count("meme"), "moment": types.count("moment"), "records": len(types),
        "practice": len(scenes), "scenes": scenes,
        "read": st.c.execute("SELECT COUNT(*) FROM article_read WHERE at LIKE ?", (like,)).fetchone()[0],
        "steps_added": st.c.execute("SELECT COUNT(*) FROM step WHERE created_at LIKE ?", (like,)).fetchone()[0],
        "reflect": st.c.execute("SELECT COUNT(*) FROM reflection WHERE created_at LIKE ?", (like,)).fetchone()[0],
    }


def _done(tid: str, f: dict, scene: str) -> bool:
    return {
        "act": f["act"] >= 1, "good": f["good"] >= 1, "meme": f["meme"] >= 1, "moment": f["moment"] >= 1,
        "pick": scene in f["scenes"], "practice": f["practice"] >= 1, "read": f["read"] >= 1,
        "plan": f["steps_added"] >= 1, "reflect": f["reflect"] >= 1,
        "act3": f["act"] >= 3, "record2": f["records"] >= 2, "wish2": f["wishes"] >= 2, "habit2": f["habits"] >= 2,
    }.get(tid, False)


def _eligible(st) -> set:
    """这个人现在用得上哪些任务：没有习惯就不出「两个习惯」，没有愿望就不出「瞬间」……"""
    wishes = [r[0] for r in st.c.execute("SELECT id FROM wish WHERE archived=0")]
    habits = st.c.execute("SELECT COUNT(*) FROM habit WHERE archived=0 AND wish_id IN (SELECT id FROM wish WHERE archived=0)").fetchone()[0]
    first = wishes[0] if wishes else ""
    few = any(st.c.execute("SELECT COUNT(*) FROM step WHERE status='todo' AND (wish_id=? OR (?=? AND (wish_id='' OR wish_id IS NULL)))",
                           (w, w, first)).fetchone()[0] <= 1 for w in wishes)
    moments = st.c.execute("SELECT MAX(n) FROM (SELECT COUNT(*) n FROM moment GROUP BY wish_id)").fetchone()[0] or 0
    from . import academy
    unread = len({a["id"] for a in academy.catalog()} - st.read_ids())
    have = {"wish": bool(wishes), "wishes2": len(wishes) >= 2, "habits2": habits >= 2, "few_steps": few,
            "moments": moments >= 3, "unread": unread > 0}
    return {k for k, v in DAILY.items() if not v.get("needs") or have.get(v["needs"])}


def _pick(st, day: str) -> dict:
    """今天的四件事 + 今天推荐的练习。每天第一次用到时定下来存好，当天不会变（加了习惯、做完推荐的练习也不变）。"""
    p = st.profile()
    cur = p.get("daily_pick") or {}
    from .scenes import SCENES
    if cur.get("day") == day and all(t in DAILY for t in cur.get("ids", [])) and cur.get("scene") in SCENES:
        return cur
    if cur.get("day") == day and all(t in DAILY for t in cur.get("ids", [])):
        # 今天推荐的练习下架了（说清想要的）：只换练习，今天的四件事不动
        out = {**cur, "scene": random.Random(f"{st.uid}:{day}:scene").choice(list(SCENES))}
        st.set_profile({"daily_pick": out})
        return out
    rnd = random.Random(f"{st.uid}:{day}")
    ok = _eligible(st)
    yesterday = set(cur.get("ids") or [])
    ids = []
    for slot in SLOTS:
        pool = [k for k, v in DAILY.items() if v["slot"] == slot and k in ok]
        fresh = [k for k in pool if k not in yesterday] or pool      # 尽量别和昨天一样
        ids.append(rnd.choices(fresh, weights=[DAILY[k].get("weight", 1) for k in fresh])[0])
    done = {r[0] for r in st.c.execute("SELECT DISTINCT scene FROM scene_run WHERE status='done'")}
    scenes = [s for s in SCENES if s not in done] or list(SCENES)
    scenes = [s for s in scenes if s != cur.get("scene")] or scenes
    out = {"day": day, "ids": ids, "scene": rnd.choice(scenes)}
    st.set_profile({"daily_pick": out})
    return out


def _daily(st, day: str) -> tuple[list[dict], dict, dict]:
    pick = _pick(st, day)
    f = _facts(st, day)
    resting = bool(st.c.execute("SELECT 1 FROM record WHERE type='rest' AND day=?", (day,)).fetchone())
    paid = {r[0] for r in st.c.execute("SELECT ref FROM coin WHERE ref LIKE ?", (f"daily:{day}:%",))}
    from .scenes import SCENES
    tasks = []
    for tid in pick["ids"]:
        t = {**DAILY[tid], "id": tid}
        if tid == "pick":
            t["label"] = f"做今天推荐的练习：{SCENES[pick['scene']]['title']}"
        done = _done(tid, f, pick["scene"])
        tasks.append({**t, "done": done, "rest": bool(t.get("act")) and resting and not done, "paid": f"daily:{day}:{tid}" in paid})
    bonus = {**DAILY_BONUS, "done": all(t["done"] or t["rest"] for t in tasks), "paid": f"daily:{day}:all" in paid}
    return tasks, bonus, pick


def _pay(st, day: str, key: str, xp: int, coins_: int, note: str) -> bool:
    ref = f"daily:{day}:{key}"
    if not _coin(st, "daily", coins_, ref, note):
        return False
    st.c.execute("INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
                 (day, "daily", xp, ref, note, iso()))
    return True


def _settle_daily(st) -> list[dict]:
    day = day_key()
    tasks, bonus, _ = _daily(st, day)
    new = []
    for t in tasks:
        if t["done"] and not t["paid"] and _pay(st, day, t["id"], t["xp"], t["coins"], "每日任务：" + t["label"]):
            new.append({"id": t["id"], "label": t["label"], "xp": t["xp"], "coins": t["coins"]})
    if bonus["done"] and not bonus["paid"] and _pay(st, day, "all", bonus["xp"], bonus["coins"], "每日任务四件都做到了"):
        new.append({"id": "all", "label": "四件都做到了", "xp": bonus["xp"], "coins": bonus["coins"]})
        st.log("daily", "今天的每日任务四件都做到了")
    if new:
        st.set_profile({"xp": total_xp(st)})
    return new


def settle_daily(st) -> list[dict]:
    with st.tx():
        return _settle_daily(st)


# ---------------------------------------------------------------- 发奖励 ----

def award(st, source: str, ref: str = "", note: str = "", amount: int | None = None, coins: bool = True) -> dict:
    """一件真实的事发生了：记经验（限额 + 去重）、按价目表发金币、结算每日任务，一个事务里做完。
    返回的字典照实说：amount 是这件事的经验，coins 是这次一共到手的金币，daily 是顺带完成的每日任务。"""
    if source not in SOURCES:
        return {"ok": False, "reason": "unknown source"}
    from . import town
    town.ensure(st)   # 老账号第一次走到这里：先把过去的经验换成建材，免得这一笔被算两遍
    amount = SOURCES[source]["amount"] if amount is None else max(0, int(amount))
    base_note = note
    with st.tx():
        if ref:
            dup = st.c.execute("SELECT * FROM xp WHERE source=? AND ref=?", (source, ref)).fetchone()
            if dup:
                return {"ok": True, "duplicate": True, "amount": 0, "coins": 0, "note": "这件事已经计过分了", "row": dict(dup)}
        rows = [r for r in _rows_today(st) if r["source"] in SOURCES]
        used_src = sum(int(r["amount"]) for r in rows if r["source"] == source)
        used_all = sum(int(r["amount"]) for r in rows)
        allowed = min(amount, SOURCES[source]["cap"] - used_src, DAILY_CAP - used_all)
        out: dict = {"ok": True, "amount": 0}
        if allowed <= 0:
            out.update(capped=True, today=used_all,
                       note=("今天的总经验已经到 120 了" if used_all >= DAILY_CAP else f"今天「{SOURCES[source]['label']}」的 30 已经满了"))
        else:
            if amount > allowed:
                note = (note + f"（今日这类剩 {allowed}）").strip()
            cur = st.c.execute(
                "INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
                (day_key(), source, allowed, ref or "", note, iso()))
            row = dict(st.c.execute("SELECT * FROM xp WHERE rowid=?", (cur.lastrowid,)).fetchone())
            total = total_xp(st)
            st.set_profile({"xp": total})
            out.update(amount=allowed, row=row, today=used_all + allowed, cap=DAILY_CAP, partial=amount > allowed, total=total)
        if coins:
            got, cnote = _event_coins(st, ref, base_note)
            first = _first_gift(st) if (ref or "").split(":", 1)[0] in COIN_EVENTS else 0
            daily = _settle_daily(st)
            out.update(coins=got + first + sum(d["coins"] for d in daily), coin_event=got, first_gift=first, daily=daily,
                       daily_xp=sum(d["xp"] for d in daily))
            out["amount_total"] = out["amount"] + out["daily_xp"]
            if cnote:
                out["coin_note"] = cnote
            if (ref or "").startswith("ms:"):
                gift = town.gift_monument(st, ref, base_note.replace("到达：", ""))
                if gift:
                    out["gift"] = gift
        else:
            out["coins"] = 0
    return out


# ---------------------------------------------------------------- 账本 ----

LEDGER_LABEL = {**{k: v["label"] for k, v in SOURCES.items()}, "daily": "每日任务", "admin": "后台调整"}


def ledger(st, limit: int = 40) -> list[dict]:
    """经验和金币合成一本账：同一件事（同一个 ref）只占一行，旁边写它带来的经验和金币。"""
    rows, by_ref = [], {}
    for r in st.c.execute("SELECT * FROM xp ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit * 2,)):
        e = {"at": r["created_at"], "note": r["note"] or LEDGER_LABEL.get(r["source"], "经验"),
             "kind": r["source"], "xp": int(r["amount"]), "coins": 0}
        rows.append(e)
        if r["ref"]:
            by_ref[r["ref"]] = e
    for r in st.c.execute("SELECT * FROM coin ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit * 2,)):
        if r["ref"] in by_ref:
            by_ref[r["ref"]]["coins"] += int(r["amount"])
            continue
        rows.append({"at": r["created_at"], "note": r["note"], "kind": r["kind"], "xp": 0, "coins": int(r["amount"])})
    rows.sort(key=lambda e: e["at"], reverse=True)
    return rows[:limit]


def day_totals(st, days: int = 14) -> dict:
    """每天拿到的经验和金币（给「动态」按天的小结用）。"""
    out: dict = {}
    for r in st.c.execute("SELECT day, SUM(amount) FROM xp GROUP BY day ORDER BY day DESC LIMIT ?", (days,)):
        out.setdefault(r[0], {"xp": 0, "coins": 0})["xp"] = int(r[1] or 0)
    for r in st.c.execute("SELECT day, SUM(amount) FROM coin WHERE amount>0 AND kind NOT IN ('migrate','test','admin') GROUP BY day ORDER BY day DESC LIMIT ?", (days,)):
        out.setdefault(r[0], {"xp": 0, "coins": 0})["coins"] = int(r[1] or 0)
    return out


# ---------------------------------------------------------------- 给前端和小光 ----

def rules() -> dict:
    """「怎么算的」：前端的规则说明直接用这份，和后端算的永远一致。"""
    from . import town
    return {
        "xp": [{"label": v["label"], "hint": v["hint"], "each": v["amount"], "cap": v["cap"]} for v in SOURCES.values()],
        "xp_cap": DAILY_CAP,
        "coins": [{"label": label, "each": each, "cap": COIN_CAP[kind]} for label, (kind, each) in
                  (("完成小步", COIN_EVENTS["step"]), ("习惯打卡", COIN_EVENTS["habit"]), ("到达里程碑", COIN_EVENTS["ms"]),
                   ("好消息", COIN_EVENTS["rec"]), ("瞬间", COIN_EVENTS["moment"]), ("做完练习", COIN_EVENTS["scene"]))],
        "first_gift": FIRST_GIFT,
        "daily_max": rules_max(),
        "levels": [{"lv": lv, "xp": xp_for_level(lv)} for lv in (2, 5, 10, 20, 30, 40)],
        "level_base": LEVEL_BASE, "level_step": LEVEL_STEP, "level_cap": LEVEL_CAP,
        "unlocks": town.unlock_table(),
    }


def state(st, consume: bool = True) -> dict:
    """前端和小光读的成长状态。consume=True 时顺手结算每日任务，并把「升级了」这个一次性标记交给前端庆祝。"""
    from . import town
    town.ensure(st)
    if consume:
        settle_daily(st)
    total = total_xp(st)
    p = st.profile()
    by_src = {k: 0 for k in SOURCES} | {"daily": 0}
    for r in _rows_today(st):
        by_src[r["source"]] = by_src.get(r["source"], 0) + int(r["amount"])
    lvl = level_of(total, int(p.get("level_floor") or 1))
    level_up = None
    seen = int(p.get("town_seen_level") or 0)
    if seen and lvl["lv"] > seen and consume:
        level_up = town.level_gain(seen, lvl["lv"])
        st.set_profile({"town_seen_level": lvl["lv"]})
        st.log("town", f"小镇升到了 Lv{lvl['lv']}" + (f"，解锁了{'、'.join(i['name'] for i in level_up['unlocks'])}" if level_up["unlocks"] else ""))
    with st.tx():
        tasks, bonus, pick = _daily(st, day_key())
    from .scenes import SCENES
    return {
        "total": total,
        "level": lvl,
        "today": {"total": sum(by_src.values()), "cap": DAILY_CAP, "by_source": by_src,
                  "events": sum(v for k, v in by_src.items() if k in SOURCES)},
        "sources": [{"id": k, **v, "used": by_src.get(k, 0)} for k, v in SOURCES.items()],
        "coins": coins(st),
        "coins_today": int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM coin WHERE day=? AND amount>0 AND kind NOT IN ('migrate','test','admin')",
                                        (day_key(),)).fetchone()[0]),
        "daily": {"day": day_key(), "tasks": tasks, "bonus": bonus,
                  "done": sum(1 for t in tasks if t["done"] or t["rest"]), "of": len(tasks),
                  "max": {"xp": sum(t["xp"] for t in tasks) + bonus["xp"], "coins": sum(t["coins"] for t in tasks) + bonus["coins"]},
                  "got": {"xp": sum(t["xp"] for t in tasks if t["paid"]) + (bonus["xp"] if bonus["paid"] else 0),
                          "coins": sum(t["coins"] for t in tasks if t["paid"]) + (bonus["coins"] if bonus["paid"] else 0)},
                  "pick": pick["scene"], "pick_title": SCENES[pick["scene"]]["title"]},
        "level_up": level_up,
        "ledger": ledger(st, 40),
        "day_totals": day_totals(st),
        "rules": rules(),
    }


def rules_text() -> str:
    from . import town
    pool = "、".join(v["label"] for k, v in DAILY.items() if v["slot"] != "core")
    return ("经验：完成一小步、习惯打卡或到达里程碑 +10（行动），记一件小确幸、一段内心戏或在蜕变计划里留下一个瞬间 +6，"
            "完成一次显化练习 +12，每天第一次来聊 +8（陪伴）。四类每类每天最多 30，真实的事每天最多 120；同一件事不重复计分。"
            f"等级只升不降：从 Lv n 升到 n+1 要 {LEVEL_BASE} + {LEVEL_STEP}×(n-1) 经验，最多 {LEVEL_CAP}（每天拿满大约三天一级）；老用户以前到过的等级保底。"
            "金币：完成小步 +10、习惯打卡 +8、到达里程碑 +30、好消息 +4、瞬间 +5、做完练习 +10，每类每天有上限；"
            f"和你聊天只加经验、不加金币。第一次做成一件真实的事送 {FIRST_GIFT} 金币，正好够盖第一栋小木屋。"
            "每日任务每天 0 点换一批，一共四件：固定一件「完成 1 个小步或打一次卡」（+5 经验 +10 金币），另外三件按天轮换"
            f"（{pool}），每件 +5～10 经验、+8～18 金币，四件都做到再 +{DAILY_BONUS['xp']} 经验 +{DAILY_BONUS['coins']} 金币，"
            f"一天最多 +{rules_max()['xp']} 经验、+{rules_max()['coins']} 金币。做了就自动完成、自动发；偷懒日里行动类先暂停，不挡全勤。"
            "点子页的「今日推荐」是每天推荐的一个练习：做任何练习都是 +12 经验 +10 金币，赶上每日任务里有它就再多一份。"
            "每日任务和愿望里的小步是两回事：小步不会过期，也不会被刷新。"
            "我的小镇：等级解锁新的建筑和更大的土地，金币用来买；建筑不会坏、不会因为中断消失，可以挪位置、收进仓库，都不花钱。"
            "到达里程碑会送一块刻着它名字的纪念碑。" + town.unlock_text()
            + "以前的宠物小芽和徽章已经下架，原来的经验一分没少，变成了小镇的等级；老用户过去的经验还按一半换成了金币。"
            "TA 问起小芽，就照实、温柔地说它的位置现在是 TA 的小镇。")


def rules_max() -> dict:
    return {"xp": sum(max(v["xp"] for v in DAILY.values() if v["slot"] == s) for s in SLOTS) + DAILY_BONUS["xp"],
            "coins": sum(max(v["coins"] for v in DAILY.values() if v["slot"] == s) for s in SLOTS) + DAILY_BONUS["coins"]}
