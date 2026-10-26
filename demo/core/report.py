"""蜕变报告 (10 / 30 days). Meeting asked for surprise, not a pile of known
numbers. The surprise line follows creative spec §D, then the model may
rewrite the whole letter in 小光's voice from those verified facts only.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from . import llm
from .store import Store
from .util import clip, now, parse_iso, tokens

THEME_WORDS = ["朋友", "室友", "家人", "妈妈", "爸爸", "同学", "老师", "写作", "读书", "运动", "跑步", "早起", "睡觉",
               "英语", "画画", "音乐", "做饭", "散步", "猫", "狗", "天气", "阳光", "咖啡", "奶茶", "课", "考试", "作业", "表达"]


def theme_word(texts: list[str]) -> str | None:
    c = Counter()
    for t in texts:
        for w in THEME_WORDS:
            if w in t:
                c[w] += 1
    if c:
        w, n = c.most_common(1)[0]
        return w if n >= 2 else None
    c = Counter(tok for t in texts for tok in tokens(t) if len(tok) == 2)
    common = [w for w, n in c.most_common(5) if n >= 2]
    return common[0] if common else None


def build(store: Store, days: int = 10) -> dict:
    p = store.profile()
    since = now() - timedelta(days=days)

    def recent(xs, key):
        return [x for x in xs if (parse_iso(x.get(key)) or since) >= since]

    recs = recent(store.records(500), "created_at")
    good = [r for r in recs if r["type"] == "good"]
    rest = [r for r in recs if r["type"] == "rest"]
    finds = [r for r in recs if r["type"] == "find"]
    steps = store.steps()
    done = [s for s in steps if s["status"] == "done" and (parse_iso(s.get("done_at")) or since) >= since]
    confirmed = [m for m in store.memories(statuses=("active",), limit=50)
                 if m["source"] in ("confirmed",) or m["kind"] == "insight"][:3]

    # surprise line (creative §D)
    surprise = None
    w = theme_word([r["text"] for r in good])
    rest_days = {r["day"] for r in rest}
    done_on_rest_window = [s for s in done if s.get("done_at") and s["done_at"][:10] not in rest_days]
    if len(good) >= 3 and w:
        surprise = f"你记下的好消息里，「{w}」出现得最多。也许它比你以为的更重要。"
    elif rest and done_on_rest_window:
        surprise = f"这段时间你给自己放了 {len(rest_days)} 天假，可小步还是完成了 {len(done)} 个。慢下来并没有让你停下。"
    elif p.get("intent_why") and done:
        surprise = f"第一天你说，想要它是因为「{clip(p['intent_why'], 24)}」。现在，你已经做了「{clip(done[0]['title'], 18)}」。"
    elif good:
        surprise = f"最早的一条好消息是「{clip(good[-1]['text'], 24)}」。那时候你可能没想到，会一直记下去。"

    facts = {
        "days": days, "name": p.get("nickname") or "", "agent": p.get("agent_name") or "小光",
        "intent": p.get("intent_primary") or "", "why": p.get("intent_why") or "",
        "good": len(good), "rest": len(rest_days), "done": len(done), "finds": len(finds),
        "good_samples": [clip(r["text"], 30) for r in good[:4]],
        "done_samples": [clip(s["title"], 24) for s in done[:4]],
        "insights": [clip(m["text"], 40) for m in confirmed],
        "first_traits": p.get("traits") or [],
        "surprise": surprise, "xp": p.get("xp") or 0,
    }
    letter = None
    if good or done:
        out = llm.complete_json([
            {"role": "system", "content": (
                "你是显化陪伴 agent，要给用户写一段蜕变回顾。只使用给出的事实，不要编造任何事件或数字。"
                "要求：80–140 字，第二人称，温暖但克制，不用感叹号堆砌；先说一个具体的变化，再引用一条好消息或完成的小步；"
                "最后一句指向下一阶段，但不布置任务。另给一个 ≤14 字的标题。只输出 JSON：{\"title\":\"...\",\"letter\":\"...\"}")},
            {"role": "user", "content": str(facts)},
        ], timeout=30)
        if out and out.get("letter"):
            letter = {"title": clip(out.get("title") or "", 20), "text": clip(out["letter"], 260)}
    if not letter:
        if good or done:
            letter = {"title": f"这 {days} 天的你",
                      "text": f"这 {days} 天里，你收集了 {len(good)} 条好消息，完成了 {len(done)} 个小步"
                              + (f"，也给自己放了 {len(rest_days)} 天假" if rest_days else "") + "。" + (surprise or "")}
        else:
            letter = None
    return {"facts": facts, "letter": letter, "empty": not (good or done or finds)}
