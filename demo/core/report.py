"""蜕变报告（14 / 30 天）。

会议要的是「惊喜感」，不是统计表。做法：先用确定性规则从真实记录里算出
故事节点和一条惊喜句（creative §D），再让模型只在这些已核实的事实上写信。
每个节点都带 sources，界面可以逐条核对——这样「不是流水账」和「不编造」
可以同时成立。数据不足时报告 empty，不给假故事。
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from . import llm
from .store import Store
from .util import clip, now, parse_iso, tokens

THEME_WORDS = ["朋友", "室友", "家人", "妈妈", "爸爸", "同学", "老师", "写作", "读书", "运动", "跑步", "早起", "睡觉",
               "英语", "画画", "音乐", "做饭", "散步", "猫", "狗", "天气", "阳光", "咖啡", "奶茶", "课", "考试", "作业", "表达"]

PERIODS = (14, 30)


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


def build(store: Store, days: int = 14, with_letter: bool = True) -> dict:
    days = 30 if int(days) >= 30 else 14
    p = store.profile()
    since = now() - timedelta(days=days)

    def recent(xs, key):
        return [x for x in xs if (parse_iso(x.get(key)) or since) >= since]

    recs = recent(store.records(500), "created_at")
    good = [r for r in recs if r["type"] == "good"]
    rest = [r for r in recs if r["type"] == "rest"]
    finds = [r for r in recs if r["type"] == "find"]
    done = [s for s in store.steps() if s["status"] == "done"
            and (parse_iso(s.get("done_at")) or since) >= since]
    growth_rows = [dict(r) for r in store.c.execute(
        "SELECT * FROM xp WHERE created_at >= ?", (since.isoformat(timespec="seconds"),))]
    xp_sum = sum(int(r["amount"]) for r in growth_rows)
    rest_days = {r["day"] for r in rest}

    nodes = []          # 故事节点，每条带可核对来源
    surprise = None
    w = theme_word([r["text"] for r in good])
    if len(good) >= 3 and w:
        surprise = f"你记下的好消息里，「{w}」出现得最多。也许它比你以为的更重要。"
    elif rest and done:
        surprise = f"这段时间你给自己放了 {len(rest_days)} 天假，可小步还是完成了 {len(done)} 个。慢下来并没有让你停下。"
    elif p.get("intent_why") and done:
        surprise = f"第一天你说，想要它是因为「{clip(p['intent_why'], 24)}」。现在，你已经做了「{clip(done[0]['title'], 18)}」。"
    elif good:
        surprise = f"最早的一条好消息是「{clip(good[-1]['text'], 24)}」。那时候你可能没想到，会一直记下去。"

    if p.get("intent_primary"):
        nodes.append({"kind": "start", "label": "起点", "title": p["intent_primary"],
                      "text": (p.get("intent_why") or "这是你一开始想靠近的东西。"),
                      "sources": [{"type": "profile", "text": "建档时的回答"}]})
    if good:
        first = good[-1]
        nodes.append({"kind": "good", "label": "第一条好消息", "title": clip(first["text"], 40),
                      "text": first["day"], "sources": [{"type": "record", "id": first["id"], "text": first["text"]}]})
    if done:
        nodes.append({"kind": "action", "label": "真实做过的事", "title": f"完成了 {len(done)} 个小步",
                      "text": "、".join(clip(s["title"], 16) for s in done[:3]),
                      "sources": [{"type": "step", "id": s["id"], "text": s["title"]} for s in done[:4]]})
    if rest_days:
        nodes.append({"kind": "rest", "label": "慢下来的日子", "title": f"{len(rest_days)} 天",
                      "text": "这些天你没有完成任何事，也没有被扣掉什么。",
                      "sources": [{"type": "record", "text": "偷懒日记录"}]})
    if len(good) >= 2 and w:
        nodes.append({"kind": "theme", "label": "反复出现的词", "title": w,
                      "text": "它在你写下的好事里出现了不止一次。",
                      "sources": [{"type": "record", "id": r["id"], "text": r["text"]} for r in good[:5]]})

    facts = {
        "days": days, "name": p.get("nickname") or "", "agent": p.get("agent_name") or "小光",
        "intent": p.get("intent_primary") or "", "why": p.get("intent_why") or "",
        "good": len(good), "rest": len(rest_days), "done": len(done), "finds": len(finds),
        "xp": xp_sum,
        "good_samples": [clip(r["text"], 30) for r in good[:4]],
        "done_samples": [clip(s["title"], 24) for s in done[:4]],
        "first_traits": p.get("traits") or [],
        "surprise": surprise,
    }

    letter = None
    if with_letter and (good or done):
        out = llm.complete_json([
            {"role": "system", "content": (
                "你是显化陪伴 agent，要给用户写一段蜕变回顾。只使用给出的事实，不要编造任何事件或数字。"
                "要求：90–150 字，第二人称，温暖但克制，不用感叹号堆砌；先说一个具体的变化，再引用一条好消息或完成的小步；"
                "最后一句指向下一阶段，但不布置任务。另给一个 ≤12 字的标题。只输出 JSON：{\"title\":\"...\",\"letter\":\"...\"}")},
            {"role": "user", "content": str(facts)},
        ], timeout=30)
        if out and out.get("letter"):
            letter = {"title": clip(out.get("title") or "", 20), "text": clip(out["letter"], 300)}

    if not letter:
        if good or done:
            body = (f"这 {days} 天里，你收集了 {len(good)} 条好消息，完成了 {len(done)} 个小步"
                    + (f"，也给自己放了 {len(rest_days)} 天假" if rest_days else "") + "。")
            if surprise:
                body += surprise
            body += "下一段不用更快，保持这样就好。"
            letter = {"title": f"这 {days} 天的你", "text": body}
        else:
            letter = None

    days_in = store.counts()["days"]
    return {"period": days, "narrative": letter, "nodes": nodes, "facts": facts,
            "surprise": surprise, "empty": not (good or done or finds),
            "ready": days_in >= days, "days_in": days_in,
            "xp": xp_sum, "cover": "report-cover",
            "periods": [{"days": d, "ready": days_in >= d, "label": f"{d} 天"} for d in PERIODS]}
