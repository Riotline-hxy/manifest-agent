"""点子里的引导场景：一题一题问（界面在 public/js/lesson.js），这里管进度和写回。

两种结束方式：
- 答完就写（gratitude）：最后一题答完，直接写进好消息和记忆；
- 先确认再存（review=True：「聊聊你的愿望」「聊聊现在的你」「遇见更好的自己」）：答题时什么都不写，也不进聊天记录。
  「聊聊你的愿望」的结束页把能留下的内容列成卡片，用户勾选、可以改，点「保存选中的内容」才写（save）；
  「聊聊现在的你」的问题、结束页（看到的你 + 第一小步）和存法在 core/relearn.py，界面是 public/js/tune.js；
  冥想的结束页问一句「有没有什么让你想记住」：记下感受 / 和小光聊聊 / 直接结束。
  不保存就把这次的回答清掉（discard）。练习经验在答完时就给，存不存都算。

题目字段：q 问题，hint 气泡里的小字；chips 选项；ask {选项: 占位}：选了它才出输入框，答案是输入的文字；
ph 一直显示的输入框；after 选项放在输入框下面；multi / max 多选；none 算作「没想好」的选项；
replies {选项: 小光的回应}、reply_any 选了就回应、reply_unknown 回答「不知道」时的回应；
foot 「显化七步」那行小字里点亮第几个；cta 没有选项、只有一个按钮的页（按钮上的字）；
breath 这一页放一颗慢慢呼吸的光；glow 回应时那颗光变暖、亮起来。
场景上的 calm：冥想的节奏，选了就往下走、不能跳过，问题一行一行慢慢出来；music 背景音乐。
"""
from __future__ import annotations

import re

from . import journey, llm, relearn
from .store import Store
from .util import clip, now

SKIP = "（跳过）"
SEVEN = ["澄清", "信念", "感受", "行动", "感恩", "释放", "见证"]
KEEP_WISH, NEW_WISH = "是的，还是这个愿望", "我想换一个愿望"
OTHER = "其他，我想自己说"
# 自己写的「不知道」「没想好」：和点「暂时不知道」一样，不生成卡片
UNKNOWN = re.compile(r"(暂时|现在|还|也|真的)*(不知道|不清楚|没想好|想不到|想不出|不确定|说不清楚?|说不准|说不好|没有|无|没|不晓得)"
                     r"[呀啊吧呢哦诶欸～~。.!！…]*")

# 「希望我怎么陪你」：选项原文 → (结束页和设置里显示的说法, 写给小光看的做法)
CHAT_STYLES = {
    "多听我说，不急着给建议": ("多听你说，不急着给建议", "多听 TA 说，先接住，不急着给建议"),
    "和我一起把事情想清楚": ("和你一起把事情想清楚", "陪 TA 一起把事情一点点理清楚"),
    "帮我想想具体可以怎么做": ("帮你想想具体可以怎么做", "帮 TA 想具体能怎么做，给一两个马上能开始的办法"),
    "给我一些鼓励和信心": ("给你一些鼓励和信心", "多给 TA 一些鼓励和信心，用具体的观察，不说空话"),
    "不固定，到时候再说": ("不固定，到时候再说", "不固定，看 TA 当时的状态来"),
}
CHAT_HOW = {shown: how for shown, how in CHAT_STYLES.values()}
REMIND = ["每天", "每周几次", "每周一次", "暂时不需要提醒"]

# 「遇见更好的自己」：选项原文 → 结束后小光开口时用的短说法
PLACE = {"在温暖安静的家里": "温暖安静的家里", "在阳光下，享受户外的空气": "阳光下的户外",
         "在喜欢的城市，自由地走走": "喜欢的城市里", "在一个让我有成就感的地方": "一个让你有成就感的地方",
         "其他，我有自己的画面": "自己的画面里"}
FUTURE_SELF = {"更自信，敢于表达自己的想法": "更自信", "更平静，不再总是担心": "更平静", "更自由，能选择喜欢的生活": "更自由",
               "更有力量，愿意尝试新事物": "更有力量", "被爱包围，也懂得爱自己": "被爱包围"}
# 那束光带来的感受 → 在心里对自己说的话
LIGHT = {"勇气": "我可以带着一点点勇气，尝试我想做的事。", "平静": "我可以慢下来，找到自己的节奏。",
         "爱与陪伴": "我值得被爱，也可以温柔地照顾自己。", "自信": "我正在慢慢相信自己。",
         "对生活的期待": "我愿意发现生活中正在发生的美好。"}
FEEL = [{"key": "write", "label": "我想记下刚才的感受"}, {"key": "talk", "label": "我想和你聊聊"},
        {"key": "end", "label": "先不记录，结束"}]
ENERGY = ["早上", "下午", "晚上", "不太固定"]

SCENES = {
    "relearn": {
        "title": "聊聊现在的你", "minutes": 2, "stage": "近况", "icon": "compass", "review": True, "kind": "tune",
        "desc": "说说现在的你，我们从一个今天就能做的小步开始。",
        # 界面在 public/js/tune.js（对话样子），问题、存法在 core/relearn.py
        "steps": [{**s, "replies": relearn.replies(s)} for s in relearn.STEPS],
    },
    "gratitude": {
        "title": "三分钟感恩", "minutes": 3, "stage": "感恩",
        "desc": "找三件已经发生的好事，小到一杯热水也算。",
        "steps": [
            {"q": "今天已经发生的、哪怕很小的一件好事？", "ph": "比如：食堂的菜今天很好吃"},
            {"q": "再来一件：跟人有关的。", "ph": "谁让你轻松了一点？"},
            {"q": "再来一件：跟自己有关的。", "ph": "你做到了什么？"},
        ],
    },
    "meditation": {
        "title": "冥想体验：遇见更好的自己", "minutes": 3, "stage": "冥想", "review": True, "calm": True,
        "music": "/audio/meditation.mp3",
        "desc": "花几分钟放松一下，想象你期待的生活。",
        "steps": [
            {"key": "relax", "breath": True, "cta": "准备好了",
             "q": "找一个舒服的姿势。\n轻轻吸一口气，再慢慢呼出来。\n这一刻，你可以先放下手里的事。"},
            {"key": "place", "q": "现在，想象一年后的某一天。\n那时的你，正待在一个让自己舒服的地方。\n你希望自己在哪里？",
             "chips": list(PLACE)},
            {"key": "self", "q": "在这个地方，你看到了未来的自己。\n你最希望那时的自己是什么样的？",
             "chips": list(FUTURE_SELF), "reply_any": "那是你期待成为的样子。\n我们一起再看看，那时的你过着怎样的生活。"},
            {"key": "joy", "q": "想象一下，未来的你刚刚经历了一件让自己开心的事。\n你希望是什么？",
             "chips": ["勇敢做了一件以前不敢做的事", "完成了一件自己一直期待的事", "有人理解我、支持我",
                       "拥有了一段轻松自在的时间", "我有自己的想象"]},
            {"key": "light", "glow": True,
             "q": "想象一束温暖的光，轻轻来到你的身边。\n它带来了你此刻需要的感受。\n你希望它带来什么？",
             "chips": list(LIGHT), "replies": {k: f"你选择了{k}。\n现在，试着在心里对自己说：\n{v}" for k, v in LIGHT.items()}},
            {"key": "back", "breath": True, "cta": "我准备好了",
             "q": "再轻轻呼吸一次。\n感受一下你的身体，也留意身边的声音。\n等你准备好了，慢慢睁开眼睛，或者抬起目光。\n欢迎回来。"},
        ],
    },
    "seven_steps_lite": {
        "title": "聊聊你的愿望", "minutes": 2, "stage": "七步", "review": True,
        "desc": "我们一起聊聊，你最近想实现的愿望吧～",
        "steps": [
            {"key": "wish", "foot": 0},   # 有没有愿望，问法不同：见 _render_step
            {"key": "belief", "foot": 1, "q": "想到这个愿望，你觉得自己有机会实现它吗？",
             "chips": ["我觉得有可能", "有一点期待，但也不太确定", "现在还不太相信", "说不清楚"],
             "replies": {"现在还不太相信": "没关系，不用现在就相信。我们可以慢慢聊。",
                         "说不清楚": "没关系，不用现在就相信。我们可以慢慢聊。"}},
            {"key": "feel", "foot": 2, "q": "想象一下，如果愿望实现了，你会是什么心情？",
             "chips": ["开心", "放松", "安心", "有成就感", OTHER, "暂时想不到"],
             "ask": {OTHER: "写下那种心情"}, "none": ["暂时想不到"]},
            {"key": "try", "foot": 3, "q": "为了这个愿望，接下来你想做些什么？",
             "ph": "不用很具体，想到什么就写什么。", "chips": ["暂时不知道"], "after": True,
             "none": ["暂时不知道"], "reply_unknown": "没关系，还没想好也可以。"},
            {"key": "have", "foot": 4, "q": "为了这个愿望，你觉得自己已经有什么可以依靠的？",
             "ph": "比如：一段经验、一项能力，或愿意支持你的人。"},
            {"key": "worry", "foot": 5, "q": "在这件事上，有没有什么想法让你觉得有压力？",
             "ph": "比如：我觉得自己必须一次就做好。"},
            {"key": "say", "foot": 6, "q": "聊完这些，你现在最想对自己说什么？",
             "chips": ["我愿意先试一试", "我可以慢慢来", "我想再给自己一点信心", "写一句自己的话", "现在还想不到"],
             "ask": {"写一句自己的话": "写给自己的一句话"}, "none": ["现在还想不到"]},
        ],
    },
}

SERVER_ONLY = ("replies", "reply_any", "reply_unknown", "none")


def catalog() -> list[dict]:
    return [{"id": k, "title": v["title"], "minutes": v["minutes"], "stage": v["stage"], "desc": v["desc"],
             "icon": v.get("icon", ""), "music": v.get("music", ""), "steps": len(v["steps"])} for k, v in SCENES.items()]


def is_review(sid: str) -> bool:
    return bool(SCENES.get(sid, {}).get("review"))


def _render_step(store: Store, scene_id: str, i: int) -> dict:
    sc = SCENES[scene_id]
    st = {k: v for k, v in sc["steps"][i].items() if k not in SERVER_ONLY}
    if scene_id == "seven_steps_lite" and st.get("key") == "wish":
        w = journey.current(store)
        if w:
            st.update(q=f"你之前写下的愿望是「{w['title']}」。现在，你最想实现的愿望还是这个吗？",
                      chips=[KEEP_WISH, NEW_WISH], ask={NEW_WISH: "写下你最近想实现的愿望"})
        else:
            st.update(q="你最近有什么想实现的愿望？", ph="写下你最近想实现的愿望")
    st["q"] = st.get("q", "").replace("{intent}", store.profile().get("intent_primary") or "想成为的自己")
    st["index"], st["total"] = i, len(sc["steps"])
    if scene_id == "relearn":
        st = relearn.render(store, st)
    if sc.get("review"):
        st["optional"], st["plain"] = not sc.get("calm"), True
    if sc.get("calm"):        # 冥想：选了就往下走
        st["calm"] = True
        if st.get("chips"):
            st["auto"] = True
    if "foot" in st:
        st["foot"] = {"label": "显化七步", "words": SEVEN, "at": st["foot"]}
    return st


def start(store: Store, scene_id: str) -> dict:
    if scene_id not in SCENES:
        raise KeyError(scene_id)
    run = store.start_scene(scene_id)
    store.log("scene", f"开始灵感场景「{SCENES[scene_id]['title']}」")
    return {"run": run, "scene": {"id": scene_id, "title": SCENES[scene_id]["title"]},
            "step": _render_step(store, scene_id, 0)}


def resume(store: Store, run_id: str) -> dict:
    run = store.get_scene(run_id)
    if not run or run["status"] != "open":
        raise KeyError(run_id)
    sid = run["scene"]
    return {"run": run, "scene": {"id": sid, "title": SCENES[sid]["title"]},
            "step": _render_step(store, sid, len(run["answers"]))}


def _norm(value, review: bool):
    """答案：一段文字，或者多选的一组；先确认再存的场景里，跳过记成空字符串。"""
    if isinstance(value, list):
        out = [clip(str(x).strip(), 60) for x in value if str(x).strip() and str(x).strip() not in (OTHER, SKIP)][:8]
        return out if out or not review else ""
    text = clip(str(value or "").strip(), 300)
    return "" if review and text in ("", SKIP) else text


def _blank(step: dict, v) -> bool:
    """跳过、选了「没想好」、或者自己写了「不知道」：这一题不生成卡片。"""
    if not v:
        return True
    if isinstance(v, list):
        return False
    return v in step.get("none", ()) or bool(UNKNOWN.fullmatch(v.strip()))


def _reply(step: dict, v) -> str:
    if not v:
        return ""
    if isinstance(v, list):
        return step.get("reply_any", "")
    if v in step.get("replies", {}):
        return step["replies"][v]
    if step.get("reply_unknown") and _blank(step, v):
        return step["reply_unknown"]
    return step.get("reply_any", "")


def answer(store: Store, run_id: str, value) -> dict:
    run = store.get_scene(run_id)
    if not run or run["status"] != "open":
        raise KeyError(run_id)
    sid = run["scene"]
    sc = SCENES[sid]
    steps = sc["steps"]
    step = steps[len(run["answers"])]
    v = _norm(value, sc.get("review", False))
    if sid == "relearn":
        v = relearn.norm(step, v)
    answers = list(run["answers"]) + [v]
    reply = _reply(step, v) if sc.get("review") else ""
    if len(answers) < len(steps):
        store.update_scene(run_id, len(answers), answers)
        out = {"done": False, "step": _render_step(store, sid, len(answers))}
        if reply:
            out["reply"] = reply
            if step.get("glow"):
                out["glow"] = True
        return out
    store.update_scene(run_id, len(answers), answers, "done")
    if sc.get("review"):
        store.log("scene", f"做完「{sc['title']}」")
        return {"done": True, "review": review(store, sid, answers, run_id)}
    wrote = finish(store, sid, answers)
    store.log("scene", f"完成「{sc['title']}」，" + "、".join(w["label"] for w in wrote))
    return {"done": True, "wrote": wrote, "summary": summary(sid, answers)}


# ---------------------------------------------------------------- 结束页：这次聊到的 ----

def _by_key(sid: str, a: list) -> dict:
    return {s["key"]: (a[i] if i < len(a) else "") for i, s in enumerate(SCENES[sid]["steps"])}


def _step(sid: str, key: str) -> dict:
    return next(s for s in SCENES[sid]["steps"] if s.get("key") == key)


def _has(sid: str, by: dict, key: str) -> bool:
    return not _blank(_step(sid, key), by.get(key))


def _seven_target(store: Store, wish_ans: str) -> tuple[dict | None, str]:
    """第 1 题指向哪个愿望：(已有的愿望, 新愿望的名字)。写的和已有的某个愿望是同一个，就算已有的。"""
    ws = journey.wishes(store)
    cur = journey.current(store) if ws else None
    if not wish_ans or wish_ans in (KEEP_WISH, NEW_WISH) or _blank(_step("seven_steps_lite", "wish"), wish_ans):
        return cur, ""
    hit = next((w for w in ws if journey.is_dup(wish_ans, [w["title"]])), None)
    return (hit, "") if hit else (cur, clip(wish_ans, 30))


def review(store: Store, sid: str, a: list, run_id: str = "") -> dict:
    if sid == "relearn":     # 小光看到的你 + 两个第一小步（core/relearn.py）
        return relearn.review(store, run_id, a)
    by = _by_key(sid, a)
    items = []
    if sid == "meditation":
        return {"kind": "feel", "say": "刚刚的几分钟里，有没有什么让你想记住？", "choices": FEEL,
                "ph": "写下刚才的感受，一句也好", "to": "会记在「好消息」里"}
    if sid == "seven_steps_lite":
        target, new = _seven_target(store, by["wish"])
        if _has(sid, by, "try"):
            items.append({"key": "try", "title": "我想试试", "text": by["try"], "to": "小步"})
        if new:
            it = {"key": "wish", "title": "新的愿望", "text": new, "to": "蜕变计划"}
            if len(journey.wishes(store)) >= journey.MAX_ACTIVE:
                it.update(off=True, note=f"愿望已经有 {journey.MAX_ACTIVE} 个了，先在蜕变计划里收起一个，才放得进新的")
            items.append(it)
        if _has(sid, by, "say"):
            items.append({"key": "say", "title": "我想对自己说", "text": by["say"], "to": "轨迹" if (target or new) else "记忆"})
        if _has(sid, by, "worry"):
            items.append({"key": "worry", "title": "我注意到的压力", "text": by["worry"], "to": "记忆"})
        say = ("聊完啦～这是你接下来想尝试的事：" if _has(sid, by, "try")
               else "聊完啦～接下来做什么，还可以再想一想。" if items else "聊完啦～谢谢你愿意和我一起想一想。")
        return {"say": say, "heading": "这次聊到的", "items": items, "extra": None}

    raise KeyError(sid)


# ---------------------------------------------------------------- 保存 / 不保存 ----

def save(store: Store, run_id: str, chosen: list, extra: str = "", talk: bool = False) -> dict:
    """只写用户勾选的；文字用用户改过的版本。写完把这次的回答清掉，同一次不能存两遍。
    冥想：extra 是用户写下的感受（记成一颗小确幸）；talk=True 是「我想和你聊聊」，小光带着刚才的画面先开口。"""
    run = store.get_scene(run_id)
    if not run or run["status"] != "done" or not is_review(run["scene"]):
        raise KeyError(run_id)
    if not run["answers"]:
        raise ValueError("这次聊到的已经处理过了")
    sid = run["scene"]
    if sid == "meditation":
        out = _meditation_talk(run["answers"]) if talk else _meditation_note(store, extra)
    elif sid == "relearn":
        out = relearn.save(store, run_id, run["answers"], chosen, extra)
    else:
        allowed = {it["key"]: it for it in review(store, sid, run["answers"])["items"] if not it.get("off")}
        picks = {}
        for it in chosen[:10]:
            k = str((it or {}).get("key") or "")
            if k in allowed:
                picks[k] = clip(str(it.get("text") or "").strip(), 60) or allowed[k]["text"]
        if not picks:
            raise ValueError("还没有选中要保存的内容")
        out = _save_seven(store, run["answers"], picks)
    store.update_scene(run_id, run["step"], [], "done")
    if out["reply"]:
        store.add_msg("assistant", out["reply"], {"scene": sid, "scene_done": True, "wrote": [w["label"] for w in out["wrote"]]})
    store.log("scene", f"保存了「{SCENES[sid]['title']}」里聊到的 {len(out['wrote'])} 项")
    return out


def discard(store: Store, run_id: str) -> None:
    """「返回对话」或者中途关掉：这次的回答不留。"""
    run = store.get_scene(run_id)
    if run and is_review(run["scene"]) and run["answers"]:
        store.update_scene(run_id, run["step"], [], "done" if run["status"] == "done" else "abandoned")


def _save_seven(store: Store, answers: list, picks: dict) -> dict:
    target, _ = _seven_target(store, _by_key("seven_steps_lite", answers)["wish"])
    wrote, made = [], None
    if "wish" in picks:
        hit = next((w for w in journey.wishes(store) if journey.is_dup(picks["wish"], [w["title"]])), None)
        if hit:
            target = hit
        else:
            made = target = journey.add_wish(store, picks["wish"], journey.guess_category(picks["wish"]))
            wrote.append({"type": "wish", "label": "新的愿望", "text": made["title"], "where": "蜕变计划"})
    step = None
    if "try" in picks:
        title = clip(picks["try"], 40)
        have = (journey.existing_titles(store, target["id"])["steps"] if target
                else [s["title"] for s in store.steps() if s["status"] == "todo"])
        if journey.is_dup(title, have):
            wrote.append({"type": "step", "label": "我想试试", "text": title, "where": "小步里已经有了"})
        else:
            step = store.add_step(title, why="聊聊你的愿望 · 行动", wish=target["title"] if target else "",
                                  wish_id=target["id"] if target else "")
            wrote.append({"type": "step", "label": "我想试试", "text": step["title"],
                          "where": f"「{target['title']}」的小步" if target else "小步"})
    if "say" in picks:
        if target:
            journey.add_moment(store, target["id"], "对自己说：" + picks["say"], source="scene")
            wrote.append({"type": "moment", "label": "我想对自己说", "text": picks["say"], "where": f"「{target['title']}」的轨迹"})
        else:
            store.add_memory("对自己说过：" + picks["say"], "insight", "scene:seven_steps_lite")
            wrote.append({"type": "memory", "label": "我想对自己说", "text": picks["say"], "where": "记忆"})
    if "worry" in picks:
        store.add_memory((f"想到「{target['title']}」时会有压力：" if target else "有个让自己有压力的想法：") + picks["worry"],
                         "insight", "scene:seven_steps_lite")
        wrote.append({"type": "memory", "label": "我注意到的压力", "text": picks["worry"], "where": "记忆"})

    # 固定的话，不调模型：说清放到了哪儿
    lines = []
    if made and step:
        lines.append(f"「{made['title']}」放进愿望里了，第一小步是「{step['title']}」。")
    elif made:
        lines.append(f"「{made['title']}」放进愿望里了。第一步想做什么，我们可以慢慢想。")
    elif step:
        lines.append(f"「{step['title']}」放进{'「' + target['title'] + '」的' if target else ''}小步里了，做完了跟我说一声。")
    if "say" in picks:
        lines.append(f"你对自己说的「{clip(picks['say'], 20)}」，我{'留在轨迹上了' if target else '记下了'}。")
    if "worry" in picks:
        lines.append("让你有压力的那个想法，我也记着，想聊的时候随时说。")
    return {"reply": "".join(lines[:3]), "wrote": wrote}


def _meditation_note(store: Store, extra: str) -> dict:
    text = clip((extra or "").strip(), 180)
    if not text:
        raise ValueError("写一句再保存吧")
    store.add_record("good", "冥想后：" + text)
    return {"reply": "", "wrote": [{"type": "record", "label": "刚才的感受", "text": text, "where": "好消息"}]}


def _meditation_talk(answers: list) -> dict:
    """「我想和你聊聊」：小光先开口提一句刚才的画面，用户接着说；之后的对话里小光也知道刚才想象了什么。"""
    by = _by_key("meditation", answers)
    bits = []
    if by.get("place") in PLACE:
        bits.append(f"你在{PLACE[by['place']]}")
    if by.get("self") in FUTURE_SELF:
        bits.append(f"看到了{FUTURE_SELF[by['self']]}的自己")
    if by.get("light") in LIGHT:
        bits.append(f"那束光带来了{by['light']}")
    head = ("刚才那几分钟，" + "，".join(bits) + "。") if bits else "刚才那几分钟，你陪自己慢了下来。"
    return {"reply": head + "想从哪儿聊起都行。", "wrote": []}


TONE = {"gentle": "你说话温柔、慢一点。", "clear": "你说话有条理，温和又清楚。", "lively": "你说话轻快，有点小俏皮。"}

# ---------------------------------------------------------------- 答完就写的场景 ----

def finish(store: Store, sid: str, a: list[str]) -> list[dict]:
    """Write-back rules from the creative spec §B."""
    out = []

    def mem(text, kind):
        m = store.add_memory(text, kind, "scene:" + sid)
        out.append({"type": "memory", "label": "记住了一条", "item": m})

    def rec(type_, text):
        r = store.add_record(type_, text)
        out.append({"type": "record", "label": "记下一条好消息" if type_ == "good" else "记下一条发现", "item": r})

    if sid == "gratitude":
        text = "；".join(clip(x, 40) for x in a)
        rec("good", text)
        mem("感恩三件事：" + text, "good_news")
    return out


def summary(sid: str, a: list[str]) -> str:
    return "三件好事都收好了。今天其实没有那么空。"
