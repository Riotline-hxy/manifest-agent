"""我的空间 →「了解你」：把记忆收成六个大类、一句话的「小光眼中的你」，和几条算出来的「小光的发现」。

六个大类是固定的，不会越分越多。每条记忆在哪一类：
  1. memory.cat 有值就用它（夜里整理时模型归的类，或者 TA 自己挪过的）；
  2. 没有就按记忆的 kind 和字面猜（cat_of），保证老数据也有地方放。
记忆一条不少：所有 active 的记忆都在某一类里；待确认的猜测单独放在「发现」下面。

「发现」全部由代码按真实记录统计，到了门槛才出结论；小光不自由发挥。
TA 点了「不太像」的发现不再出现（profile.insight_fb）。
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from .util import clip, loads, now, parse_iso

CATS = [
    {"id": "effort", "name": "在努力", "icon": "flag", "color": "var(--c-orange)",
     "why": "你想靠近的样子和正在做的事。小光陪你定计划、提醒你时，会照这些来。"},
    {"id": "people", "name": "在意的人", "icon": "heart", "color": "var(--c-pink)",
     "why": "你生活里重要的人和小动物。聊到他们时，小光会记得是谁。"},
    {"id": "likes", "name": "喜好和习惯", "icon": "star", "color": "var(--c-lemon)",
     "why": "小光推荐吃的、帮你安排时间时，会照这些来。"},
    {"id": "self", "name": "关于你自己", "icon": "user", "color": "var(--c-violet)",
     "why": "你的处境、你对自己的认识。"},
    {"id": "recent", "name": "最近发生的事", "icon": "clock", "color": "var(--c-mint)",
     "why": "带日期的事。小光会在合适的时候提起，过一阵子就不常提了。"},
    {"id": "rules", "name": "相处的小规矩", "icon": "shield", "color": "var(--c-sky)",
     "why": "你希望小光怎么陪你、哪些话题别碰。小光会一直遵守。"},
]
CAT_IDS = [c["id"] for c in CATS]
PEOPLE = re.compile(r"室友|妈妈|爸爸|父母|爸妈|哥哥|姐姐|弟弟|妹妹|奶奶|爷爷|外婆|外公|朋友|同学|同事|老师|男朋友|女朋友|对象|老公|老婆|孩子|儿子|女儿|"
                    r"猫|狗|宠物|叫[一-龥]{1,3}[，,。]|的生日")


CLOSE = re.compile(r"室友|妈妈|爸爸|父母|爸妈|哥哥|姐姐|弟弟|妹妹|奶奶|爷爷|外婆|外公|男朋友|女朋友|对象|老公|老婆|孩子|儿子|女儿|猫|狗|宠物|的生日")


def cat_of(m: dict) -> str:
    if m.get("cat") in CAT_IDS:
        return m["cat"]
    kind, text = m.get("kind") or "", m.get("text") or ""
    if kind == "boundary":
        return "rules"
    if PEOPLE.search(text) and (kind != "event" or CLOSE.search(text)):   # 事件里随口提到「朋友」不算，和亲近的人有关才算
        return "people"
    return {"intent": "effort", "preference": "likes", "event": "recent", "good_news": "recent"}.get(kind, "self")


SRC = {"confirmed": "你确认过", "onboarding": "建档时", "chat:explicit": "你让我记的", "digest": "夜里整理",
       "scene:relearn": "调整现有计划", "scene:seven_steps_lite": "显化你的愿望"}


def _src(s: str) -> str:
    return SRC.get(s or "", "练习里" if (s or "").startswith("scene") else "聊天里")


def about(st) -> list[dict]:
    """六个大类，每类里是这个人全部的 active 记忆（新的在前），加上设置里的边界和陪伴偏好（只读，去设置改）。"""
    p = st.profile()
    revs: dict[str, str] = {}
    for r in st.c.execute("SELECT memory_id, old_text, reason FROM memory_rev WHERE new_text != '' ORDER BY at"):
        revs.setdefault(r["memory_id"], r["old_text"])       # 最早的说法
    groups = {c: [] for c in CAT_IDS}
    for m in st.memories(statuses=("active",), limit=400):
        groups[cat_of(m)].append({"id": m["id"], "text": m["text"], "src": _src(m["source"]),
                                  "day": (m["updated_at"] or m["created_at"] or "")[:10], "was": revs.get(m["id"], "")})
    for b in [x for x in (p.get("boundaries") or []) if x and x != "无"]:
        if any(b in i["text"] for i in groups["rules"]):
            continue      # 建档时已经记成一条记忆了，不重复列
        groups["rules"].insert(0, {"id": "", "text": b, "src": "你定的边界 · 在设置里改", "fixed": True})
    return [{**c, "items": groups[c["id"]]} for c in CATS]


def portrait(st) -> dict:
    """「小光眼中的你」那一句。夜里整理写；TA 改过就用 TA 的。认识不满 7 天，或者记得的事不到 5 件，用一句固定的话。"""
    p = st.profile()
    pt = p.get("portrait") or {}
    days = st.counts().get("days", 1)
    if pt.get("text") and (pt.get("by") == "user" or days >= 7):
        return {"text": pt["text"], "by": pt.get("by") or "digest", "days": days}
    intent = (p.get("intent_primary") or "").strip()
    head = f"我们才认识 {days} 天。" if days < 7 else f"我们认识 {days} 天了。"
    return {"text": head + (f"你想靠近「{intent}」，" if intent else "") + "别的，我还在慢慢认识你。",
            "by": "early", "days": days}


# ---- 小光的发现 ------------------------------------------------------------------

WD = "一二三四五六日"


def _part(hour: int) -> str:
    return "早上" if hour < 12 else "下午" if hour < 18 else "晚上"


def _energy(st, ref) -> dict:
    since = (ref - timedelta(days=28)).date().isoformat()
    stamps = [r[0] for r in st.c.execute("SELECT created_at FROM habit_log WHERE day>=?", (since,))]
    stamps += [r[0] for r in st.c.execute("SELECT done_at FROM step WHERE status='done' AND done_at>=?", (since,))]
    ts = [t for t in (parse_iso(s) for s in stamps if s) if t]
    need = 12
    base = {"id": "energy", "icon": "sun", "color": "var(--c-orange)", "q": "一周中，我什么时候最有劲？",
            "have": len(ts), "need": need, "unit": "次打卡或完成小步"}
    if len(ts) < need:
        return base
    wd = Counter(t.weekday() for t in ts)
    top, n = wd.most_common(1)[0]
    if n < max(3, 1.5 * (len(ts) - n) / 6):     # 最多的那天要明显比别的天多，不然不下结论
        return {**base, "flat": True, "a": "你每天都差不多，没有特别偏哪一天", "src": f"来自 {len(ts)} 次打卡和小步",
                "chart": [wd.get(i, 0) for i in range(7)]}
    part = Counter(_part(t.hour) for t in ts if t.weekday() == top).most_common(1)[0][0]
    return {**base, "a": f"周{WD[top]}{part}，是你一周里最有劲的时候", "src": f"来自 {len(ts)} 次打卡和小步",
            "chart": [wd.get(i, 0) for i in range(7)],
            "evidence": [f"最近 4 周 {len(ts)} 次里，{n} 次在周{WD[top]}", f"其他日子平均 {round((len(ts) - n) / 6, 1)} 次",
                         f"可以试试：把难一点的事放在周{WD[top]}{part}"]}


def _block(st) -> dict:
    said = []
    for r in st.c.execute("SELECT data FROM kick_memory ORDER BY created_at DESC LIMIT 30"):
        d = loads(r["data"] or "", {}) or {}
        b = ((d.get("answers") or {}).get("block") or "").strip()
        if b:
            said.append(b)
    base = {"id": "block", "icon": "bolt", "color": "var(--c-coral)", "q": "卡住我的，通常是什么？",
            "have": len(said), "need": 3, "unit": "次两分钟启动（拆更准）"}
    if len(said) < 3:
        return base
    top, n = Counter(said).most_common(1)[0]
    if n < 2:
        return {**base, "have": 2}     # 每次都不一样：还说不出规律
    return {**base, "a": f"卡住你的，多半是「{clip(top, 10)}」", "src": f"来自 {len(said)} 次两分钟启动",
            "evidence": [f"{len(said)} 次里有 {n} 次你说卡在「{top}」"] +
                        [f"也说过：{x}" for x, _ in Counter(said).most_common(3)[1:]]}


def _old_steps(st) -> dict:
    rows = [dict(r) for r in st.c.execute("SELECT title, created_at, done_at FROM step WHERE status='done' AND done_at!=''")]
    late = []
    for r in rows:
        a, b = parse_iso(r["created_at"]), parse_iso(r["done_at"])
        if a and b and (b - a).days >= 3:
            late.append((r["title"], (b - a).days))
    base = {"id": "late", "icon": "leaf", "color": "var(--c-mint)", "q": "放了很久的事，最后会做完吗？",
            "have": len(late), "need": 3, "unit": "个放过 3 天以上又做完的小步"}
    if len(late) < 3:
        return base
    late.sort(key=lambda x: -x[1])
    return {**base, "a": f"放了好几天的小步，你最后做完了 {len(late)} 个", "src": f"来自 {len(rows)} 个做完的小步",
            "evidence": [f"「{clip(t, 14)}」放了 {d} 天才做" for t, d in late[:3]] + ["放着不等于放弃，你会回来做的"]}


def _good_time(st) -> dict:
    rows = [r[0] for r in st.c.execute("SELECT created_at FROM record WHERE type='good'")]
    ts = [t for t in (parse_iso(s) for s in rows) if t]
    base = {"id": "goodtime", "icon": "star", "color": "var(--c-lemon)", "q": "我通常在什么时候记下开心的事？",
            "have": len(ts), "need": 10, "unit": "件开心的小事"}
    if len(ts) < 10:
        return base
    part, n = Counter(_part(t.hour) for t in ts).most_common(1)[0]
    return {**base, "a": f"你多半在{part}记下开心的事", "src": f"来自 {len(ts)} 件小确幸",
            "evidence": [f"{len(ts)} 件里有 {n} 件是{part}记的", "那个时候来找小光聊聊，也许最合适"]}


def _keep(st, ref) -> dict:
    from . import journey      # 避免循环引用
    hs = [h for h in journey.habits(st) if (parse_iso(h.get("created_at") or "") or ref) <= ref - timedelta(days=21)]
    base = {"id": "keep", "icon": "check", "color": "var(--c-sky)", "q": "我说过要坚持的，坚持得怎么样？",
            "have": 0, "need": 1, "unit": "周把一个习惯做满"}
    if not hs:
        return base
    lines, best = [], None
    for h in hs[:4]:
        need = 5 if h["freq"] == "daily" else int(h.get("per_week") or 3)    # 每天的习惯：一周做到 5 天就算做到
        ok = 0
        for w in range(3):
            end = (ref - timedelta(days=ref.weekday() + 7 * w)).date()
            start = end - timedelta(days=7)
            n = st.c.execute("SELECT COUNT(*) FROM habit_log WHERE habit_id=? AND day>? AND day<=?",
                             (h["id"], start.isoformat(), end.isoformat())).fetchone()[0]
            ok += n >= need
        lines.append(f"「{clip(h['title'], 12)}」过去 3 周有 {ok} 周做到了")
        if best is None or ok > best[1]:
            best = (h["title"], ok)
    if not best or best[1] == 0:     # 一周都没做满：不拿来下结论（不做让人难受的「发现」），先算在积累里
        return base
    return {**base, "have": 1, "a": f"「{clip(best[0], 8)}」过去 3 周有 {best[1]} 周做到了", "src": f"来自 {len(hs)} 个习惯",
            "evidence": lines}


def insights(st) -> list[dict]:
    ref = now()
    fb = st.profile().get("insight_fb") or {}
    out = []
    for f in (_energy(st, ref), _block(st), _old_steps(st), _good_time(st), _keep(st, ref)):
        if fb.get(f["id"]) == "no" and f.get("a"):
            continue
        f["fb"] = fb.get(f["id"], "")
        f["ready"] = bool(f.get("a"))
        if not f["ready"]:
            f["left"] = max(1, f["need"] - f["have"])
        out.append(f)
    out.sort(key=lambda f: not f["ready"])
    return out
