"""「聊聊现在的你」：简单说说现在的自己，小光给出今天就能开始的第一小步，带 TA 一起往好里走。

界面在 public/js/tune.js：对话样子的全屏层，小光问一句，插图卡片放在小光的话下面，点一张变成 TA 说的话。
走的还是点子场景那一套（core/scenes.py，review=True）：答题时什么都不写；答完那一下调一次模型，拿「看到的你」
和两个第一小步（存在 profile.relearn_end 里，保存时不再调）；结束页勾选的才存。

四题：state 最近的状态 / dir 想在哪儿看到一点进步 / energy 现在能拿出多少劲 / accomp 这一路怎么陪你。
存到哪：
  第一小步 → 蜕变计划的小步（今天）；方向不是已有的愿望时，小光起的新愿望名（TA 勾了才建）；
  最近的状态 → 一条近况记忆（再做一次就更新那一条）；陪你的方式 → 陪伴偏好（「推我一把」顺带把中断时改成轻轻提醒）；
  还有什么想让我先知道的 → 一条记忆。
"""
from __future__ import annotations

from . import journey, llm
from .store import Store
from .util import clip, now

# 选项的 ill 是前端 tune.js 里的插图名
STEPS = [
    {"key": "state", "q": "最近的你，更像哪一种？", "short": "最近", "opts": [
        {"v": "busy", "label": "忙忙碌碌", "hint": "事情一件接一件", "ill": "busy", "react": "最近事情不少呀。"},
        {"v": "steady", "label": "按自己的节奏", "hint": "和平时差不多", "ill": "steady", "react": "有自己的节奏，挺好。"},
        {"v": "change", "label": "正在变化", "hint": "有些事不一样了", "ill": "change", "react": "变化的时候，正好重新开始。"},
        {"v": "slow", "label": "想慢下来", "hint": "有点累了", "ill": "slow", "react": "好，那我们不着急。"}]},
    {"key": "dir", "q": "接下来，最想在哪儿看到一点进步？", "short": "想变好的", "opts": [
        {"v": "body", "label": "作息和身体", "hint": "睡好、动起来", "ill": "body", "react": "身体顾好了，别的都轻松一点。"},
        {"v": "study", "label": "学习和工作", "hint": "做得进去、做得完", "ill": "study", "react": "好，我们找个好下手的地方。"},
        {"v": "mood", "label": "心情和状态", "hint": "少点焦虑、多点轻松", "ill": "mood", "react": "好，先让自己舒服一点。"},
        {"v": "people", "label": "和人相处", "hint": "敢开口、多联系", "ill": "people", "react": "好，从一句话开始就行。"}]},
    {"key": "energy", "q": "现在，你能拿出多少劲？", "short": "劲头", "opts": [
        {"v": "seed", "label": "一点点就好", "hint": "两分钟就够", "ill": "pot1", "react": "那就从很小的一步开始。"},
        {"v": "sprout", "label": "每天一小会", "hint": "十分钟左右", "ill": "pot2", "react": "好，每天一小会，刚刚好。"},
        {"v": "more", "label": "可以多一点", "hint": "半小时左右", "ill": "pot3", "react": "好，那我们来点实在的。"}]},
    {"key": "accomp", "q": "这一路，我怎么陪你比较好？", "short": "陪你的方式", "opts": [
        {"v": "listen", "label": "先听我说", "hint": "不急着给建议", "ill": "listen", "react": "好，你说的时候我先听着。"},
        {"v": "untangle", "label": "陪我理一理", "hint": "乱的时候一起捋", "ill": "untangle", "react": "好，乱的时候我们一起捋。"},
        {"v": "push", "label": "推我一把", "hint": "给办法，也提醒我", "ill": "push", "react": "好，该推的时候我会推你一下。"},
        {"v": "cheer", "label": "给我打打气", "hint": "说说我做到了什么", "ill": "cheer", "react": "好，你做到的事我都会说给你听。"}]},
]
# 「陪你的方式」→ 陪伴偏好里存的说法（和设置里一样，是 scenes.CHAT_STYLES 里「你」的那种说法，小光的提示按它找做法）
CHAT = {"listen": "多听你说，不急着给建议", "untangle": "和你一起把事情想清楚", "push": "帮你想想具体可以怎么做",
        "cheer": "给你一些鼓励和信心"}
ENERGY_HOW = {"seed": "一点点就好（两分钟就够）", "sprout": "每天一小会（十分钟左右）", "more": "可以多一点（半小时左右）"}
EXTRA = {"q": "还有什么想让我先知道的？", "ph": "可以不写。比如：最近在备考，晚上 11 点以后别找我"}
MARK = "最近的状态："
LLM_TIMEOUT = 20

PROMPT = """你是「{name}」，TA 的朋友，陪 TA 一点点变成想成为的人。{tone}
TA 刚在「聊聊现在的你」里简单说了说现在的自己，想从这里开始，看到一点进步。下面是 TA 选的。

做三件事：
1. see：一句话说出你看到的现在的 TA，不超过 34 字，对 TA 说（用「你」），把 TA 的状态和想变好的方向连起来，像朋友随口一说。
2. steps：两个今天就能开始的第一小步，都冲着 TA 想变好的方向，大小照 TA 现在的劲头：
   - 一点点就好：两分钟内能做完，几乎不费劲；
   - 每天一小会：十分钟左右；
   - 可以多一点：半小时左右，今天就能开始。
   两个都按这个大小来：选了「可以多一点」，就别给「念一句」「一分钟」这种很小的动作。
   TA 最近很忙，就挑不占时间的；想慢下来，就挑让人放松的做法。
   每个 title 不超过 14 字，具体到一个动作（像「今晚 12 点前把手机放远」）；why 不超过 24 字，说为什么先从这一步开始。两个要不一样。
3. wish：方向不是 TA 已有的愿望时，给这个方向起一个愿望名（不超过 8 字，像「睡得早一点」「少一点焦虑」）；是已有的愿望就留空。

不说教，不喊口号，不用「不是……而是……」、破折号，不说「加油」「你一定可以」「旅程」「蜕变」。
只输出 JSON：{{"see":"","steps":[{{"title":"","why":""}},{{"title":"","why":""}}],"wish":""}}"""

# 模型不在时的第一小步：按方向和劲头挑，说得通用一点
FALLBACK = {
    "wish": {"seed": ("为「{w}」做两分钟", "先让它今天出现一下"), "sprout": ("为「{w}」做十分钟", "每天一小会，最容易接着来"),
             "more": ("为「{w}」留出半小时", "今天认真往前推一次")},
    "body": {"seed": ("今晚早十分钟放下手机", "睡好了，别的都轻松一点"), "sprout": ("饭后慢慢走十分钟", "动一动，身体先松下来"),
             "more": ("今晚十一点前躺下", "先把睡眠拉回来")},
    "study": {"seed": ("写下明天最要紧的一件事", "先知道从哪下手"), "sprout": ("手机放远，专心做十分钟", "先练一次坐得住"),
              "more": ("留出半小时只做一件事", "认真推进一次")},
    "mood": {"seed": ("慢慢深呼吸十次", "先让身体松一点"), "sprout": ("睡前写三行今天的小事", "写下来，心里轻一点"),
             "more": ("出门走半小时，不看手机", "换个环境，脑子缓一缓")},
    "people": {"seed": ("给一个朋友发句问候", "联系一下，关系就热一点"), "sprout": ("和一个人好好聊十分钟", "从一次真聊开始"),
               "more": ("约一个朋友见一面", "见面比消息近得多")},
}
FALLBACK_WISH = {"body": "睡好一点", "study": "做事更专注", "mood": "多一点轻松", "people": "敢开口多联系"}
FALLBACK_SEE = "好，我们就从这里开始。"


def _opt(key: str, v: str, wish: dict | None = None) -> dict | None:
    if key == "dir" and v == "wish":
        return {"v": "wish", "label": clip(wish["title"], 10), "hint": "接着你的愿望", "ill": "wish", "react": "好，接着往前走。"} if wish else None
    step = next(s for s in STEPS if s["key"] == key)
    return next((o for o in step["opts"] if o["v"] == v), None)


def render(store: Store, st: dict) -> dict:
    """给前端的一题：方向那题，有愿望就把现在的愿望放第一个（顶掉「和人相处」）。"""
    if st.get("key") == "dir":
        w = journey.current(store)
        if w:
            st["opts"] = [_opt("dir", "wish", w)] + st["opts"][:3]
    if st.get("index") == 0:
        st["intro"] = "说说现在的你，我们从这里开始。"
    return st


def replies(step: dict) -> dict:
    out = {o["v"]: o["react"] for o in step["opts"]}
    if step["key"] == "dir":
        out["wish"] = "好，接着往前走。"
    return out


def norm(step: dict, v) -> str:
    """只收选项里有的值（方向题多一个 wish）；别的当作跳过。"""
    ok = {o["v"] for o in step["opts"]} | ({"wish"} if step["key"] == "dir" else set())
    return v if isinstance(v, str) and v in ok else ""


def _answers(a: list) -> dict:
    return {s["key"]: (a[i] if i < len(a) else "") for i, s in enumerate(STEPS)}


def ending(store: Store, answers: list) -> dict:
    """调一次模型：{see, steps: [{title, why}] × 2, wish}。模型不在就按方向和劲头给一条通用的路。"""
    from .scenes import TONE
    p = store.profile()
    a = _answers(answers)
    w = journey.current(store)
    d = a["dir"] if a["dir"] and (a["dir"] != "wish" or w) else ("wish" if w else "body")
    e = a["energy"] or "seed"
    st, dr = _opt("state", a["state"]), _opt("dir", d, w)
    wishes = [x["title"] for x in journey.wishes(store)][:4]
    user = "\n".join([
        f"TA 的称呼：{p.get('nickname') or '（没填）'}",
        "TA 已有的愿望：" + ("、".join(f"「{t}」" for t in wishes) + (f"（现在主要在做「{w['title']}」）" if w else "") if wishes else "（还没有）"),
        f"最近的状态：{st['label'] + '，' + st['hint'] if st else '（没选）'}",
        f"想变好的方向：{'接着已有的愿望「' + w['title'] + '」' if d == 'wish' else dr['label'] + '（' + dr['hint'] + '）'}",
        f"现在的劲头：{ENERGY_HOW[e]}",
    ])
    system = PROMPT.format(name=p.get("agent_name") or "小光", tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    out = llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                            timeout=LLM_TIMEOUT, reasoning="none") or {}   # TA 在等：不思考
    steps = []
    for x in out.get("steps") or []:
        if isinstance(x, dict) and str(x.get("title") or "").strip():
            steps.append({"title": clip(str(x["title"]).strip().rstrip("。"), 16), "why": clip(str(x.get("why") or "").strip(), 30)})
    see = clip(str(out.get("see") or "").strip(), 50)
    wish = "" if d == "wish" else clip(str(out.get("wish") or "").strip().strip("「」"), 10)
    by_model = len(steps) >= 2 and bool(see)
    if not by_model:
        t, why = FALLBACK[d][e]
        alt = FALLBACK[d]["seed" if e != "seed" else "sprout"]
        steps = [{"title": t.format(w=clip(w["title"], 8) if w else ""), "why": why},
                 {"title": alt[0].format(w=clip(w["title"], 8) if w else ""), "why": alt[1]}]
        see = FALLBACK_SEE
    if d != "wish" and not wish:
        wish = FALLBACK_WISH.get(d, "")
    return {"see": see, "steps": steps[:2], "dir": d, "wish": wish, "wish_id": w["id"] if (w and d == "wish") else "",
            "by_model": by_model}


def review(store: Store, run_id: str, answers: list) -> dict:
    """结束页：小光看到的你、两个第一小步、会存下的东西。模型的结果按这次 run 缓存，保存时不再调。"""
    cache = store.profile().get("relearn_end") or {}
    end = cache if cache.get("run") == run_id and cache.get("steps") else {**ending(store, answers), "run": run_id}
    if end is not cache:
        store.set_profile({"relearn_end": end})
    a = _answers(answers)
    items = [{"key": "step", "title": "第一小步", "text": end["steps"][0]["title"], "choices": end["steps"], "to": "蜕变计划 · 今天"}]
    if end["dir"] != "wish" and end["wish"]:
        it = {"key": "wish", "title": "新的愿望", "text": end["wish"], "new": True, "to": "蜕变计划"}
        if len(journey.wishes(store)) >= journey.MAX_ACTIVE:
            it.update(off=True, note=f"愿望已经有 {journey.MAX_ACTIVE} 个了，先在蜕变计划里收起一个")
        items.append(it)
    st = _opt("state", a["state"])
    if st:
        items.append({"key": "state", "title": "最近", "text": st["label"], "to": "记忆"})
    ac = _opt("accomp", a["accomp"])
    if ac:
        items.append({"key": "accomp", "title": "陪你的方式", "text": ac["label"], "to": "设置"})
    w = journey.current(store)
    return {"kind": "tune", "say": end["see"], "items": items, "extra": EXTRA,
            "wish": w["title"] if (w and end["dir"] == "wish") else ""}


def save(store: Store, run_id: str, answers: list, chosen: list, extra: str = "") -> dict:
    rv = review(store, run_id, answers)
    allowed = {it["key"]: it for it in rv["items"] if not it.get("off")}
    picks = {}
    for it in chosen[:8]:
        k = str((it or {}).get("key") or "")
        if k in allowed:
            picks[k] = str(it.get("text") or "").strip()
    extra = clip((extra or "").strip(), 200)
    if not picks and not extra:
        raise ValueError("还没有选中要保存的内容")
    end = store.profile().get("relearn_end") or {}
    a = _answers(answers)
    wrote, step = [], None
    target = end.get("wish_id") or ""
    if "wish" in picks:
        name = end.get("wish") or allowed["wish"]["text"]
        hit = next((w for w in journey.wishes(store) if journey.is_dup(name, [w["title"]])), None)
        made = hit or journey.add_wish(store, name, journey.guess_category(name))
        target = made["id"]
        if not hit:
            wrote.append({"type": "wish", "label": "新的愿望", "text": made["title"], "where": "蜕变计划"})
    if "step" in picks:
        choice = next((c for c in end.get("steps", []) if c["title"] == picks["step"]), end["steps"][0])
        step = store.add_step(choice["title"], choice["why"], wish_id=target)
        store.log("plan", "聊聊现在的你：第一小步「" + choice["title"] + "」")
        wrote.append({"type": "step", "label": "第一小步", "text": choice["title"], "where": "蜕变计划"})
    if "state" in picks:
        o = _opt("state", a["state"])
        t = now()
        text = f"{t.month}月{t.day}日说，{MARK}{o['label']}（{o['hint']}）"
        old = store.c.execute("SELECT id FROM memory WHERE source='scene:relearn' AND status!='archived' AND text LIKE ? "
                              "ORDER BY created_at DESC LIMIT 1", (f"%{MARK}%",)).fetchone()
        if old:
            store.update_memory(old["id"], text=text, status="active", reason="scene:relearn")
        else:
            store.add_memory(text, "event", "scene:relearn")
        wrote.append({"type": "memory", "label": "最近", "text": o["label"], "where": "记忆"})
    if "accomp" in picks:
        patch = {"chat_style": CHAT[a["accomp"]]}
        if a["accomp"] == "push":
            patch["care_style"] = "nudge"
        store.set_profile(patch)
        wrote.append({"type": "profile", "label": "陪你的方式", "text": _opt("accomp", a["accomp"])["label"], "where": "陪伴偏好"})
    if extra:
        store.add_memory("想让小光知道：" + extra, "insight", "scene:relearn")
        wrote.append({"type": "memory", "label": "想让我知道的", "text": extra, "where": "记忆"})
    store.set_profile({"relearn_end": {}})
    reply = rv["say"] + (f"\n\n「{step['title']}」放进今天的计划了。" if step else "")
    return {"reply": reply, "wrote": wrote, "step": {"id": step["id"], "title": step["title"]} if step else None}
