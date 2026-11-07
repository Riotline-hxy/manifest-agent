"""「许个愿」（scene id 沿用 seven_steps_lite）：许一个新愿，或者给已有的愿望再添点信心。管「信」，不加小步、不改计划。

问题和卡片在前端 public/js/flows.js；这里给 TA 自己的记录（ctx）、答完那一下的结尾（调一次模型）、怎么存。
- 新的愿望：哪一块 → 具体想要 → 那一天（实现时的画面）→ 未来的你说。结尾一张愿望卡：愿望名、那一天、未来的你说的话。
  存：新愿望（那一天写进 vision_text），未来的你说的话作为这个愿望轨迹上的第一个瞬间。
- 已有的愿望：看看走过的路（不提问）→ 最有感觉的一刻 → 现在心里 → 留一句话。结尾一张卡：走过的、那一刻、留给自己的话。
  存：轨迹上一个瞬间（带上现在的心情）。
小光的话不复述卡片上的内容，只说自己真心的一句。流程本身在 core/flows.py。
"""
from __future__ import annotations

from datetime import date

from . import journey, llm
from .store import Store
from .util import clip, now

TITLE = "许个愿"
LLM_TIMEOUT = 20
PICKS = 3             # 开场最多列几个已有的愿望
AREA_CAT = {"body": "body", "study": "wealth", "people": "relation", "mood": "calm", "life": "freedom"}
HEART = {"still": "还是很想要", "more": "更想要了", "far": "有点远了", "unsure": "说不清"}
RULES = "不说教，不喊口号，不用「不是……而是……」、破折号，不说「加油」「你一定可以」「旅程」「蜕变」「宇宙」「值得被」「勇敢」。"

NEW = """你是「{name}」，TA 的朋友，陪 TA 一点点变成想成为的人。{tone}
TA 刚在「许个愿」里许下一个新愿望，这些会做成一张愿望卡，放在 TA 的蜕变计划里。
做三件事：
1. title：愿望名，不超过 12 字，用 TA 自己的说法。
2. day：「那一天」的样子：一句现在时的画面，用「我」，不超过 32 字。把 TA 选的那个画面写得具体、有温度，像日记里随手写的一句。
3. say：你看到这个愿望时，真心的一句话，不超过 24 字。别复述愿望和画面（卡片上都有），像朋友顺口一说。
""" + RULES + """
只输出 JSON：{{"title":"","day":"","say":""}}"""

KEEP = """你是「{name}」，TA 的朋友，陪 TA 一点点变成想成为的人。{tone}
TA 刚给一个已经在做的愿望添了点信心。下面是 TA 的记录和刚才的选择，这些会做成一张卡片给 TA 看。
say：你真心想对 TA 说的一句话，不超过 30 字。别把 TA 选的那一刻、TA 写给自己的话再念一遍（卡片上都有）；
说你注意到的、或者你此刻的感受，接住 TA 现在对这个愿望的心情。像朋友，不像总结。
""" + RULES + """
只输出 JSON：{{"say":""}}"""

# 模型不在时的那句话
FALLBACK_NEW = "记下了，这个愿望我陪你一起看着。"
FALLBACK_KEEP = {"still": "那就接着走，我一直在。", "more": "更想要了，我也跟着高兴。",
                 "far": "远一点也没关系，它一直在那儿等你。", "unsure": "说不清也没关系，我们慢慢看。"}


def _md(day: str) -> str:
    try:
        d = date.fromisoformat(str(day)[:10])
        return f"{d.month}月{d.day}日"
    except ValueError:
        return ""


def _stats(store: Store, w: dict) -> dict:
    """一个愿望走过的路：几天、做完几个小步、打卡几次、留下几个瞬间，再摘一句 TA 自己写过的话。"""
    c = store.c
    try:
        days = max(1, (now().date() - date.fromisoformat(w["started"][:10])).days + 1)
    except (TypeError, ValueError):
        days = 1
    steps = c.execute("SELECT COUNT(*) FROM step WHERE wish_id=? AND status='done'", (w["id"],)).fetchone()[0]
    checks = c.execute("SELECT COUNT(*) FROM habit_log WHERE habit_id IN (SELECT id FROM habit WHERE wish_id=?)", (w["id"],)).fetchone()[0]
    mine = [m for m in journey.moments(store, w["id"], limit=40) if m["source"] in ("user", "chat")]
    quote = clip(mine[0]["text"], 40) if mine else ""
    # 最有感觉的一刻：最近做完的小步和留下的瞬间，按日子排，最多三个
    picks = [{"label": clip(m["text"], 30), "hint": f"你留下的瞬间 · {_md(m['day'])}", "icon": "heart", "day": m["day"]} for m in mine[:3]]
    for s in c.execute("SELECT title, done_at FROM step WHERE wish_id=? AND status='done' ORDER BY done_at DESC LIMIT 3", (w["id"],)):
        picks.append({"label": clip(s["title"], 30), "hint": f"做完的小步 · {_md(s['done_at'] or '')}", "icon": "check", "day": (s["done_at"] or "")[:10]})
    picks.sort(key=lambda x: x["day"], reverse=True)
    count = c.execute("SELECT COUNT(*) FROM moment WHERE wish_id=?", (w["id"],)).fetchone()[0]
    return {"days": days, "steps": steps, "checks": checks, "moments": count, "quote": quote,
            "vision": w.get("vision_text") or "", "picks": [{k: v for k, v in p.items() if k != "day"} for p in picks[:3]]}


def ctx(store: Store, wish_id: str = "") -> dict:
    ws = journey.wishes(store)
    cur = journey.current(store) if ws else None
    ws.sort(key=lambda w: (w["id"] != wish_id, w["id"] != (cur or {}).get("id")))
    return {"wishes": [{"id": w["id"], "title": w["title"], **_stats(store, w)} for w in ws[:PICKS]],
            "full": len(ws) >= journey.MAX_ACTIVE, "max": journey.MAX_ACTIVE}


def clean(store: Store, a: dict) -> dict:
    """前端送来的答案：只收认得的字段，文字都截短。"""
    s = lambda k, n=40: clip(str(a.get(k) or "").strip(), n)   # noqa: E731
    pick = s("pick")
    if pick != "new":
        w = journey.get_wish(store, pick)
        if not w or w.get("archived"):
            raise ValueError("这个愿望找不到了")
        return {"pick": pick, "moment": s("moment", 60), "heart": a.get("heart") if a.get("heart") in HEART else "",
                "onward": s("onward", 30)}
    want = s("want", 30)
    if not want:
        raise ValueError("先说说你想要的")
    return {"pick": "new", "area": a.get("area") if a.get("area") in AREA_CAT else "", "area_label": s("area_label", 20),
            "want": want, "day": s("day", 40), "words": s("words", 30)}


def _ask(store: Store, system: str, user: str) -> dict:
    from .scenes import TONE
    p = store.profile()
    system = system.format(name=p.get("agent_name") or "小光", tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    return llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             timeout=LLM_TIMEOUT, reasoning="none") or {}   # TA 在等：不思考


def ending(store: Store, a: dict) -> dict:
    """答完那一下：调一次模型写小光的一句话（新愿望还要愿望名和那一天的画面），配一张卡片和会存下的东西。"""
    nick = store.profile().get("nickname") or "（没填）"
    if a["pick"] == "new":
        out = _ask(store, NEW, f"TA 的称呼：{nick}\n想变好的一块：{a['area_label'] or '（没选）'}\nTA 想要的：{a['want']}\n"
                               f"它实现的那一天，TA 选的画面：{a['day'] or '（没选）'}")
        title = clip(str(out.get("title") or "").strip().strip("「」"), 12) or clip(a["want"], 12)
        day = clip(str(out.get("day") or "").strip(), 40) or (f"我{a['day']}。" if a["day"] else "")
        say = clip(str(out.get("say") or "").strip(), 40) or FALLBACK_NEW
        keep = {"key": "wish", "html": "把这张愿望卡放进蜕变计划", "to": "蜕变计划"}
        if len(journey.wishes(store)) >= journey.MAX_ACTIVE:
            keep.update(off=True, note=f"愿望已经有 {journey.MAX_ACTIVE} 个了，先在蜕变计划里收起一个")
        lines = ([{"em": "那一天", "text": day}] if day else [])
        return {"say": say, "card": {"small": "我的愿望", "title": title, "lines": lines,
                                     "vow": a["words"], "vow_em": "未来的你说" if a["words"] else ""},
                "keeps": [keep], "acts": ["save", "land"], "land": "给它定第一件事", "title": title, "day": day,
                "by_model": bool(out.get("say"))}
    w = journey.get_wish(store, a["pick"])
    st = _stats(store, w)
    walked = f"{st['days']} 天 · {st['steps']} 个小步 · 打卡 {st['checks']} 次"
    out = _ask(store, KEEP, f"TA 的称呼：{nick}\n愿望：「{w['title']}」，走了 {st['days']} 天：做完 {st['steps']} 个小步，"
                            f"打卡 {st['checks']} 次，留下 {st['moments']} 个瞬间\n这一路最有感觉的一刻：{a['moment'] or '（没选）'}\n"
                            f"现在想起这个愿望，TA 心里：{HEART.get(a['heart'], '（没选）')}")
    say = clip(str(out.get("say") or "").strip(), 44) or FALLBACK_KEEP.get(a["heart"] or "still")
    lines = [{"em": "走过的", "text": walked}] + ([{"em": "最有感觉的一刻", "text": a["moment"]}] if a["moment"] else [])
    return {"say": say, "card": {"small": "给愿望添了点信心", "title": w["title"], "lines": lines, "vow": a["onward"], "vow_em": ""},
            "keeps": [{"key": "moment", "html": "把这张卡留在愿望的轨迹上", "to": "蜕变计划"}],
            "acts": ["save", "land"], "land": "让它落地", "by_model": bool(out.get("say"))}


def save(store: Store, a: dict, end: dict, keys: set) -> dict:
    wrote, wish_id = [], ""
    if a["pick"] == "new":
        if "wish" in keys:
            hit = next((w for w in journey.wishes(store) if journey.is_dup(end["title"], [w["title"]])), None)
            cat = journey.guess_category(a["want"])
            w = hit or journey.add_wish(store, end["title"], cat if cat != "other" else AREA_CAT.get(a["area"], "other"),
                                        vision_text=end.get("day") or "", scene=TITLE)
            wish_id = w["id"]
            if a["words"]:
                journey.add_moment(store, w["id"], f"未来的我说：「{a['words']}」", feeling="许下这个愿望", source="scene")
            wrote.append({"type": "wish", "label": "我的愿望", "text": w["title"], "where": "蜕变计划"})
        reply = f"「{end['title']}」放进蜕变计划了，那一天的样子也在上面。" if wrote else ""
        return {"reply": reply, "wrote": wrote, "wish_id": wish_id}
    w = journey.get_wish(store, a["pick"])
    if "moment" in keys:
        bits = [f"回头看了看走过的路，最有感觉的是「{a['moment']}」。" if a["moment"] else "回头看了看走过的路。"]
        if a["onward"]:
            bits.append(f"留给自己：「{a['onward']}」")
        journey.add_moment(store, w["id"], "".join(bits), feeling=HEART.get(a["heart"], ""), source="scene")
        wrote.append({"type": "moment", "label": "给愿望添了点信心", "text": a["onward"] or a["moment"] or w["title"],
                      "where": f"「{w['title']}」的轨迹"})
    reply = f"留在「{w['title']}」的轨迹上了。" if wrote else ""
    return {"reply": reply, "wrote": wrote, "wish_id": w["id"]}
