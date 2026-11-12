"""从 TA 的计划和记录里，找出「现在值得提一句」的事。

小光聊天时（放在每轮的上下文里）、主动消息、到点的 AI 例行任务都用同一份清单，
所以提醒的内容永远来自真实数据：哪个里程碑快到了、哪个习惯这周跟不上了、哪一步放了很久……
每条带 prio（3 最要紧）和一个 hint，告诉小光可以给 TA 什么样的小选择。
"""
from __future__ import annotations

from datetime import date, timedelta

from . import journey
from .util import clip, now, parse_iso


def _md(day: str) -> str:
    return f"{int(day[5:7])}月{int(day[8:10])}日"


def _streak(days: list[str], today: date) -> int:
    have = set(days)
    d = today if today.isoformat() in have else today - timedelta(days=1)
    n = 0
    while d.isoformat() in have:
        n += 1
        d -= timedelta(days=1)
    return n


def attention(st, ref=None, limit: int = 6) -> list[dict]:
    ref = ref or now()
    today = ref.date()
    out: list[dict] = []

    def add(prio: int, kind: str, text: str, hint: str = ""):
        out.append({"prio": prio, "kind": kind, "text": text, "hint": hint})

    if journey.is_resting(st, today.isoformat()):
        return [{"prio": 3, "kind": "rest", "text": "今天是 TA 的偷懒日", "hint": "什么都别催，陪着就好"}]
    if journey.is_resting(st, (today - timedelta(days=1)).isoformat()):
        add(2, "after_rest", "昨天是偷懒日，今天是歇完回来的第一天", "问问歇得怎么样，再从一件很小的事开始")

    ws = journey.wishes(st)
    live = {w["id"]: w for w in ws}
    ms = [m for m in journey.milestones(st) if m["wish_id"] in live]
    hs = journey.habits(st)

    for m in ms:
        if m["status"] == "done" or not m["due_day"]:
            continue
        d = (date.fromisoformat(m["due_day"]) - today).days
        if d < 0:
            add(3, "milestone_overdue", f"里程碑「{m['title']}」原定 {_md(m['due_day'])}，已经过了 {-d} 天还没标到达",
                "问问到了没有：到了就帮 TA 标上；没到就一起把日子往后挪")
        elif d <= 3:
            add(3, "milestone_due", f"里程碑「{m['title']}」{_md(m['due_day'])} 到期（{'就是今天' if d == 0 else f'还有 {d} 天'}）",
                "问问进展，需要的话拆一个今天就能做的小步")

    for w in ws:
        d = (date.fromisoformat(w["target_day"]) - today).days
        if d < 0:
            add(2, "wish_overdue", f"愿望「{w['title']}」计划 {_md(w['target_day'])} 实现，已经过了 {-d} 天",
                "可以一起看看这段路走到了哪儿，或者把计划日子往后挪")
        elif d <= 7:
            add(2, "wish_due", f"愿望「{w['title']}」计划 {_md(w['target_day'])} 实现，还剩 {d} 天", "陪 TA 看看还差什么")
        if not any(m["wish_id"] == w["id"] for m in ms) and not any(h["wish_id"] == w["id"] for h in hs):
            add(1, "no_path", f"愿望「{w['title']}」还没有里程碑和习惯", "问 TA 要不要一起把这条路拆一拆")
        started = date.fromisoformat(w["started"][:10])
        last = st.c.execute("SELECT MAX(day) FROM moment WHERE wish_id=?", (w["id"],)).fetchone()[0]
        if (today - started).days >= 10 and (not last or (today - date.fromisoformat(last)).days >= 14):
            add(1, "quiet_wish", f"愿望「{w['title']}」" + ("还没留下过瞬间" if not last else f"上一次留下瞬间是 {_md(last)}"),
                "聊到相关的事时，问一句要不要留在轨迹上")

    days_left = 7 - today.weekday()          # 含今天
    for h in hs:
        if h["skipped"]:
            continue
        streak = _streak(h["days"], today)
        if h["freq"] == "daily":
            if not h["today"] and ref.hour >= 17:
                add(2, "habit_today", f"今天还没打卡「{h['title']}」（每天）" + (f"，已经连着 {streak} 天了" if streak >= 2 else ""),
                    "问一句今天做了没：做了就帮 TA 打卡，太累就问要不要今天先跳过")
            elif streak >= 3:
                add(1, "streak", f"「{h['title']}」已经连着 {streak} 天了", "真心夸一句，说具体")
            continue
        left = h["need"] - h["week"]
        if left <= 0:
            add(1, "habit_week_done", f"「{h['title']}」这周的 {h['need']} 次已经做满了", "夸一句")
        elif left > days_left:
            add(2, "habit_behind", f"「{h['title']}」每周 {h['need']} 次，这周做了 {h['week']} 次，只剩 {days_left} 天，做满有点难了",
                "别催；问要不要这周先少做一次，或者把频率调低一点")
        elif today.weekday() >= 3 and not h["today"]:
            add(2, "habit_week", f"「{h['title']}」这周做了 {h['week']}/{h['need']} 次，还剩 {days_left} 天",
                "轻轻问一句今天要不要做一次")

    first = ws[0]["id"] if ws else ""
    for w in ws:   # 一段小步走完了，还没想下一步：小光可以主动问一句（不催）
        mine = [x for x in st.steps(200) if (x.get("wish_id") or first) == w["id"] and x["status"] in ("todo", "done")]
        if mine and not any(x["status"] == "todo" for x in mine):
            add(1, "steps_cleared", f"愿望「{w['title']}」的 {len(mine)} 个小步都做完了，还没有下一步",
                "聊到这个愿望时夸一句，问一次要不要一起想想接下来的一两个小步；TA 说之后再说，这几天就别再提")

    for s_ in st.steps(60):
        if s_["status"] != "todo" or (s_.get("wish_id") and s_["wish_id"] not in live):
            continue
        plan = journey.planned_day(s_, today.isoformat())
        if plan == today.isoformat():
            add(2, "planned_today", f"小步「{clip(s_['title'], 20)}」是 TA 自己安排在今天的",
                "聊到计划时可以轻轻提一句，做不做都行；TA 说今天不想做，就帮 TA 换一天")
            continue
        if plan:   # 安排在以后的：还没到日子，不催
            continue
        made = parse_iso(s_["created_at"])
        age = (today - made.date()).days if made else 0
        if age >= 7:
            add(1, "old_step", f"小步「{clip(s_['title'], 20)}」放了 {age} 天还没做",
                "问问还想不想做：想做就再拆小一点，不想做就先放一放")

    out.sort(key=lambda x: -x["prio"])
    return out[:limit]


def as_text(items: list[dict]) -> str:
    return "\n".join(f"- {x['text']}" + (f"（可以：{x['hint']}）" if x["hint"] else "") for x in items)
