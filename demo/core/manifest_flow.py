"""「显化你的愿望」（scene id 沿用 seven_steps_lite）：按显化七步，一步一屏，小光每一步都接着 TA 的回答说。

新的愿望走完整七步，已有的愿望从第 2 步开始（坚定信念）：
  1 清晰愿景：随口说想要什么 → 小光给两个更具体的版本（spec）→ 闭眼想象它实现了，那一刻的感觉 → 那一刻的画面（vision）
  2 消除怀疑：心里那个「我做不到」的声音 → 小光接住，给两句对着它的肯定语（doubt）→ 挑一句
  3 调整行为：如果你已经是实现了它的人，今天会做什么 → 小光给两件（act），TA 挑了再接一句（act_say）
  4 克服考验：最近想将就、想退回去的时候 → 接住，给两句「下次它出现时，我会……」（test）→ 挑一句
  5 无条件感恩：什么让你觉得有幸 / 一句「我必须……」→ 改写成「我有幸能……」（thanks）
  6 嫉妒变动力：看到活成你想要样子的人，你心里…… → 这说明你真正想要什么，可以向 TA 学的一件事（envy）
  7 信任：想到它什么时候会来，你心里…… → 分开「今天能做的」和「交给时间的」，两句心急时对自己说的话（trust）→ 挑一句
走完：小光写一张小纸条，把 TA 说的那个声音、挑的那句话、今天要做的事串起来，最后一句落在自爱（close），配一张显化卡。
每一步都调一次模型（不思考，约 2 秒），TA 自己写的也一样接着说。问题和分支在前端 public/js/flows.js，流程在 core/flows.py。
存（勾了的才存）：新愿望 + 那一刻的样子 → 蜕变计划；肯定语 → 小光的记忆；今天去做的事 → 今天的小步；
感恩 → 小光的记忆（练习不会自动加「瞬间」，瞬间只由 TA 自己留）；那个怀疑和考验 → 记忆（默认不勾）；每天早上提醒念一遍肯定语（默认不勾）。
"""
from __future__ import annotations

import re
from datetime import date

from . import journey, llm, tasks
from .store import Store
from .util import clip, now

TITLE = "显化你的愿望"
LLM_TIMEOUT = 20
PICKS = 3
FEELS = {"light": "轻松", "proud": "骄傲", "calm": "平静", "steadyfeel": "踏实", "happy": "开心"}
DOUBTS = {"worth": "我不配", "able": "我能力不够", "late": "已经太晚了", "others": "怕别人怎么看", "none": "没有这种声音"}
TESTS = {"settle": "想将就一下", "old": "旧习惯又回来了", "cold": "有人泼冷水", "none": "最近没有"}
ENVY = {"sour": "有点酸", "admire": "很羡慕", "learn": "想向 TA 学", "none": "没有这样的人"}
TRUST = {"rush": "很急，想快点看到", "fear": "怕它一直不来", "calm": "能慢慢等"}
STAGES = ["清晰愿景", "消除怀疑", "调整行为", "克服考验", "无条件感恩", "嫉妒变动力", "信任"]
REMIND_AT = "08:00"

RULES = ("用平常话，不说「宇宙」「振动频率」「吸引力法则」「能量」这类玄的词；不说教，不喊口号，不用「不是……而是……」、破折号，"
         "不说「加油」「你一定可以」「值得被」「勇敢」「旅程」「蜕变」；不复述 TA 刚说的原话。")
WHO = "你是「{name}」，TA 的朋友，陪 TA 用显化的方法一点点靠近想要的生活。{tone}"

# 每一步一段提示词（docs/显化与调整/gen.py 里试过的同一套）
P = {
    "spec": """
显化第一步是「清晰你的愿景」：越具体越有力量。TA 刚说了一个还比较笼统的愿望。
1. say：接住 TA，一句，不超过 24 字。
2. opts：两个更具体的版本，每个不超过 22 字，补上 TA 可能在意的细节（数量、时间、地点、样子），两个侧重不同，都用 TA 的口吻。
只输出 JSON：{{"say":"","opts":["",""]}}""",
    "vision": """
还是第一步「清晰你的愿景」。TA 闭上眼，想象这个愿望已经实现了，选了那一刻的感觉。
1. vision：那一刻的画面，一句现在时，用「我」开头，不超过 36 字，写出具体的场景和这种感觉，像日记里的一句。
2. say：你看到这个画面时的一句话，不超过 22 字，别复述画面。
只输出 JSON：{{"vision":"","say":""}}""",
    "doubt": """
显化第二步是「消除恐惧与怀疑」：人会被「我不配」「我做不到」这种声音拖住。TA 刚说了心里冒出来的那个声音。
1. say：接住它，一句，不超过 30 字。说出这个声音很常见、它从哪来，不急着反驳。
2. opts：两句对着这个声音的肯定语，每句用「我」开头、不超过 16 字，可信、不夸张，像能每天对自己说的话，两句不一样。
TA 说没有这种声音时，say 夸一句 TA 的笃定，opts 给两句帮 TA 守住这份笃定的话。
只输出 JSON：{{"say":"","opts":["",""]}}""",
    "act": """
显化第三步是「调整你的行为」：显化不是许愿，是行动；假装你已经是实现了它的人，做那个人今天会做的事。
opts：两件今天就能做的小事，每件不超过 16 字，具体到动作，比 TA 平时稍微走出舒适区一点点，但不吓人，两件不一样。
只输出 JSON：{{"opts":["",""]}}""",
    "act_say": """
还是第三步「调整你的行为」。TA 挑了今天要做的一件小事。
say：一句，不超过 24 字，让 TA 觉得做这件事时，自己已经有点像实现了愿望的那个人。
只输出 JSON：{{"say":""}}""",
    "test": """
显化第四步是「克服考验」：往前走的时候，总会出现让人想将就、想退回去的时刻。TA 刚说了最近遇到的。
1. say：接住 TA，一句，不超过 28 字。不评判、不表现失望，想将就是人之常情。
2. opts：两句「下次它出现时，我会……」，每句不超过 24 字（含「下次它出现时，我会」），给一个具体、做得到的应对，两句不一样。
TA 说没有时，say 说一句不用硬找，opts 给两句为以后准备的应对。
只输出 JSON：{{"say":"","opts":["",""]}}""",
    "thanks": """
显化第五步是「无条件的感恩」：对未来有期待，对现在有感激；一个小技巧是把「我必须」换成「我有幸能」。TA 刚写了一句。
1. line：把它写成一句感恩，用「我有幸能」开头，不超过 22 字。TA 写的本来就是感激的事，就顺着写。
2. say：一句，不超过 22 字，说说这样换一下之后的感觉。
只输出 JSON：{{"line":"","say":""}}""",
    "envy": """
显化第六步是「把嫉妒变成动力」：看到别人过上了自己想要的样子，心里发酸是正常的；这份酸其实在告诉你，你真正想要什么。TA 刚说了看到那个人时的感觉。
1. say：一句，不超过 40 字。先接住这份感觉，再点出它说明 TA 真正想要的是什么，最后落到「TA 能做到，你也可以」的意思（用你自己的话）。
2. learn：可以向那个人学的一件具体的事，不超过 16 字。
TA 说没有这样的人时，say 说一句也很好，learn 给一个可以去找找的榜样方向。
只输出 JSON：{{"say":"","learn":""}}""",
    "trust": """
显化第七步是「信任」：显化不是控制；越急越不安，该做的做了，剩下的交给时间，它会在合适的时候来。TA 刚说了想到「它什么时候会来」时的心情。
1. say：接住这份心情，不超过 40 字。把「你今天能做的」（就是 TA 选的那件小事）和「可以交给时间的」分开说，让 TA 松一口气；不催，不保证结果。
2. opts：两句心急时可以对自己说的话，用「我」开头，不超过 16 字，平实、可信，两句不一样。
TA 说能慢慢等时，say 顺着这份从容说，opts 给两句帮 TA 一直这样从容的话。
只输出 JSON：{{"say":"","opts":["",""]}}""",
    "close": """
显化七步都走完了。下面是 TA 这一路说的、选的。
1. letter：你写给 TA 的一小段话，2～3 句，不超过 90 字。用上 TA 这一路的具体内容：心里那个声音、TA 挑的那句话、今天要做的那件小事，
   串成 TA 自己的一段路（心里怕什么，打算怎么对自己说，今天往哪走一步）。像朋友写的小纸条，有温度、有细节；不总结、不列清单、不喊口号。
2. love：最后一句，提醒 TA 好好爱自己，不超过 20 字，对 TA 说（用「你」），和 letter 不重复。
只输出 JSON：{{"letter":"","love":""}}""",
}
NEED = {"spec": ("say", "opts"), "vision": ("vision", "say"), "doubt": ("say", "opts"), "act": ("opts",), "act_say": ("say",),
        "test": ("say", "opts"), "thanks": ("line", "say"), "envy": ("say", "learn"), "trust": ("say", "opts"), "close": ("letter", "love")}
# 模型不在时：每一步都还能往下走
FALLBACK = {
    "spec": {"say": "好，我们把它说得再具体一点。", "opts": []},
    "vision": {"vision": "", "say": "这个画面，记在心里。"},
    "doubt": {"say": "这个声音很多人都有，先让它待在那儿。", "opts": ["我可以一点点来", "我已经在路上了"]},
    "act": {"opts": ["今天为它做两分钟", "把第一步写下来"]},
    "act_say": {"say": "做这件事的时候，你已经在往那儿走了。"},
    "test": {"say": "想退回去的时候，人人都有。", "opts": ["下次它出现时，我会先停一下", "下次它出现时，我会想想为什么开始"]},
    "thanks": {"line": "", "say": "这样换个说法，心里会轻一点。"},
    "envy": {"say": "这份感觉在告诉你，你真正想要什么。TA 能做到，你也可以。", "learn": ""},
    "trust": {"say": "今天能做的你会去做，剩下的交给时间。", "opts": ["我先做好今天这一件", "它会在合适的时候来"]},
    "close": {"letter": "七步走完了，你今天把这个愿望看得更清楚了。", "love": "记得对自己好一点。"},
}


def _md(day: str) -> str:
    try:
        d = date.fromisoformat(str(day)[:10])
        return f"{d.month}月{d.day}日"
    except ValueError:
        return ""


def ctx(store: Store, wish_id: str = "") -> dict:
    ws = journey.wishes(store)
    cur = journey.current(store) if ws else None
    ws.sort(key=lambda w: (w["id"] != wish_id, w["id"] != (cur or {}).get("id")))
    return {"wishes": [{"id": w["id"], "title": w["title"], "vision": w.get("vision_text") or ""} for w in ws[:PICKS]],
            "full": len(ws) >= journey.MAX_ACTIVE, "max": journey.MAX_ACTIVE,
            "feels": FEELS, "doubts": DOUBTS, "tests": TESTS, "envy": ENVY, "trust": TRUST}


TEXT_KEYS = ("want", "spec", "vision", "feel", "doubt", "aff", "act", "test", "plan", "thanks", "thanks_line", "envy", "learn",
             "trust", "letgo")


def clean(store: Store, a: dict) -> dict:
    """前端送来的答案：已有的愿望要还在；文字都截短（选项送的是它的说法）。"""
    pick = clip(str(a.get("pick") or "").strip(), 40)
    out = {"pick": pick}
    for k in TEXT_KEYS:
        out[k] = clip(str(a.get(k) or "").strip(), 60)
    if pick != "new":
        w = journey.get_wish(store, pick)
        if not w or w.get("archived"):
            raise ValueError("这个愿望找不到了")
        out["title"], out["vision"] = w["title"], w.get("vision_text") or ""
    else:
        # 愿望名：用 TA 的说法，去掉「我想」「希望」这种开头（「我想在例会上主动发言」→「在例会上主动发言」）
        out["title"] = clip(re.sub(r"^(我想要|我想|我希望|我要|希望|想要|想)", "", out["spec"] or out["want"]).strip("，。 ") or out["want"], 30)
    return out


def _context(a: dict, nick: str) -> str:
    lines = [f"TA 的称呼：{nick}", f"愿望：「{a['title'] or a['want'] or '（还没说）'}」"]
    if a["vision"]:
        lines.append(f"那一刻的样子：{a['vision']}")
    return "\n".join(lines)


def _ask(store: Store, kind: str, user: str) -> dict:
    from .scenes import TONE
    p = store.profile()
    system = (WHO + P[kind] + "\n" + RULES).format(name=p.get("agent_name") or "小光",
                                                  tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    for _ in range(2):
        out = llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                timeout=LLM_TIMEOUT, reasoning="none") or {}   # TA 在等：不思考
        if all(out.get(k) for k in NEED[kind]):
            return _tidy(out)
    return {}


def _tidy(x):
    """模型偶尔还是会写破折号：换成逗号。"""
    if isinstance(x, str):
        return x.replace("——", "，").replace("—", "，").replace("，，", "，")
    if isinstance(x, list):
        return [_tidy(v) for v in x]
    if isinstance(x, dict):
        return {k: _tidy(v) for k, v in x.items()}
    return x


def _strs(xs, n: int) -> list[str]:
    out = []
    for x in xs or []:
        t = clip(str(x or "").strip().strip("「」"), n)
        if t and t not in out:
            out.append(t)
    return out[:2]


def step(store: Store, kind: str, a: dict) -> dict:
    """某一步答完：调一次模型，接着 TA 的回答说，给出这一步的收获。"""
    if kind not in P or kind == "close":
        raise ValueError("不认识的一步")
    nick = store.profile().get("nickname") or "（没填）"
    base = _context(a, nick)
    user = {
        "spec": f"TA 的称呼：{nick}\nTA 说想要：{a['want'] or '（没说）'}",
        "vision": f"TA 的称呼：{nick}\n愿望：{a['spec'] or a['want']}\n想象它实现时，那一刻的感觉：{a['feel'] or '（没选）'}",
        "doubt": f"{base}\n想到它，TA 心里冒出来的声音：{a['doubt'] or '（没说）'}",
        "act": base,
        "act_say": f"{base}\nTA 今天要做的事：{a['act']}",
        "test": f"{base}\n最近让 TA 想将就、想退回去的：{a['test'] or '（没说）'}",
        "thanks": f"{base}\nTA 写的：{a['thanks'] or '（没写）'}",
        "envy": f"{base}\n看到已经过上 TA 想要的样子的那个人，TA 心里：{a['envy'] or '（没说）'}",
        "trust": f"{base}\nTA 今天要做的小事：{a['act'] or '（还没定）'}\n想到它什么时候会来，TA 心里：{a['trust'] or '（没说）'}",
    }[kind]
    out = _ask(store, kind, user)
    fb = FALLBACK[kind]
    res = {}
    for k in NEED[kind]:
        if k == "opts":
            res[k] = _strs(out.get("opts"), 24) if len(_strs(out.get("opts"), 24)) >= 2 else list(fb["opts"])
        else:
            res[k] = clip(str(out.get(k) or "").strip(), 60) or fb.get(k, "")
    if kind == "thanks" and not res["line"]:
        t = a["thanks"]
        res["line"] = ("我有幸能" + t[3:]) if t.startswith("我必须") else (t if t.startswith("我有幸能") else "")
    res["by_model"] = bool(out)
    return res


def ending(store: Store, a: dict) -> dict:
    """走完：小光的小纸条（调一次模型）+ 显化卡 + 会存的东西。"""
    nick = store.profile().get("nickname") or "（没填）"
    out = _ask(store, "close", "\n".join(filter(None, [
        _context(a, nick), a["doubt"] and f"心里那个声音：{a['doubt']}", a["aff"] and f"TA 挑的那句话：{a['aff']}",
        a["act"] and f"今天要做的小事：{a['act']}", a["plan"] and f"最近的考验，TA 的打算：{a['plan']}",
        a["thanks_line"] and f"TA 的感恩：{a['thanks_line']}", a["trust"] and f"想到它什么时候会来：{a['trust']}",
        a["letgo"] and f"心急时对自己说：{a['letgo']}"])))
    letter = clip(str(out.get("letter") or "").strip(), 140) or FALLBACK["close"]["letter"]
    love = clip(str(out.get("love") or "").strip(), 40) or FALLBACK["close"]["love"]
    new = a["pick"] == "new"
    # 卡片上一步一行：第几步、哪一步、一个小标签、TA 的那句
    lines = [(n, em, t) for n, em, t in (
        (1, "那一刻", a["vision"]), (2, "对自己说", a["aff"]), (3, "今天去做", a["act"]),
        (4, "下次它出现", a["plan"].replace("下次它出现时，", "").replace("下次它出现时", "")),
        (5, "我有幸能", a["thanks_line"].replace("我有幸能", "", 1)), (6, "可以学的", a["learn"]), (7, "交给时间", a["letgo"])) if t]
    keeps = []
    if new:
        k = {"key": "wish", "html": "把愿望和那一刻的样子放进蜕变计划", "to": "蜕变计划"}
        if len(journey.wishes(store)) >= journey.MAX_ACTIVE:
            k.update(off=True, note=f"愿望已经有 {journey.MAX_ACTIVE} 个了，先在蜕变计划里收起一个")
        keeps.append(k)
    if a["aff"]:
        keeps.append({"key": "aff", "html": f"「{a['aff']}」让小光记着", "to": "记忆"})
    if a["act"]:
        keeps.append({"key": "act", "html": f"「{a['act']}」放进今天的小步", "to": "今天"})
    if a["thanks_line"]:
        keeps.append({"key": "thanks", "html": f"「{a['thanks_line']}」让小光记着", "to": "记忆"})
    if a["doubt"] or a["test"]:
        keeps.append({"key": "mind", "html": "那个怀疑和最近的考验，让小光记着", "to": "记忆", "on": False})
    if a["aff"]:
        keeps.append({"key": "remind", "html": f"每天 {REMIND_AT} 提醒我念一遍这句话", "to": "例行任务", "on": False})
    steps = 7 if new else 6
    return {"say": "", "letter": letter, "intro": f"这是你今天走过的{'七' if steps == 7 else '六'}步，收好它：",
            "card": {"small": "我的显化卡", "title": a["title"] or "我的愿望", "date": f"{now().month}月{now().day}日", "steps": steps,
                     "lines": [{"n": n, "stage": STAGES[n - 1], "em": em, "text": t} for n, em, t in lines], "vow": love},
            "keeps": keeps, "acts": ["save"] + (["now"] if a["act"] else []), "now": a["act"], "by_model": bool(out)}


def save(store: Store, a: dict, end: dict, keys: set) -> dict:
    wrote, wish, step_ = [], None, None
    if a["pick"] != "new":
        wish = journey.get_wish(store, a["pick"])
    elif "wish" in keys:
        title = a["title"] or a["want"]
        hit = next((w for w in journey.wishes(store) if journey.is_dup(title, [w["title"]])), None)
        wish = hit or journey.add_wish(store, title, journey.guess_category(title + a["want"]), vision_text=a["vision"], scene=TITLE)
        wrote.append({"type": "wish", "label": "我的愿望", "text": wish["title"], "where": "蜕变计划"})
    if "aff" in keys and a["aff"]:
        store.add_memory(f"想对自己说的一句话：「{a['aff']}」" + (f"（关于「{wish['title']}」）" if wish else ""), "insight", "scene:seven_steps_lite")
        wrote.append({"type": "memory", "label": "对自己说", "text": a["aff"], "where": "记忆"})
    if "act" in keys and a["act"]:
        step_ = store.add_step(clip(a["act"], 40), why="显化你的愿望 · 调整行为", wish=wish["title"] if wish else "",
                               wish_id=wish["id"] if wish else "")
        wrote.append({"type": "step", "label": "今天去做", "text": step_["title"], "where": "今天"})
    if "thanks" in keys and a["thanks_line"]:
        store.add_memory(f"感恩：{a['thanks_line']}", "event", "scene:seven_steps_lite")
        wrote.append({"type": "memory", "label": "感恩", "text": a["thanks_line"], "where": "记忆"})
    if "mind" in keys and (a["doubt"] or a["test"]):
        about = f"想到「{a['title']}」时" if a["title"] else "想到愿望时"
        bits = [f"{about}，心里会冒出「{a['doubt']}」" if a["doubt"] else "", f"最近的考验：{a['test']}" if a["test"] else ""]
        store.add_memory("；".join(b for b in bits if b), "insight", "scene:seven_steps_lite")
        wrote.append({"type": "memory", "label": "怀疑和考验", "text": a["doubt"] or a["test"], "where": "记忆"})
    if "remind" in keys and a["aff"]:
        tasks.add(store.uid, clip(f"念一遍：{a['aff']}", 30), kind="remind", repeat="daily", time=REMIND_AT, source="scene")
        wrote.append({"type": "task", "label": "提醒", "text": f"每天 {REMIND_AT}", "where": "例行任务"})
    if not wrote:
        return {"reply": "", "wrote": [], "step": None}
    store.log("journey", f"显化你的愿望：{a['title']}")
    reply = f"「{a['title']}」的显化卡收好了。" + (f"今天就去做「{step_['title']}」吧。" if step_ else "")
    return {"reply": reply, "wrote": wrote, "step": {"id": step_["id"], "title": step_["title"]} if step_ else None,
            "wish_id": wish["id"] if wish else ""}
