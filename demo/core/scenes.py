"""点子里的引导场景：一题一题问（界面在 public/js/lesson.js），这里管进度和写回。

两种结束方式：
- 答完就写（gratitude）：最后一题答完，直接写进好消息和记忆；
- 先确认再存（review=True：「遇见更好的自己」）：答题时什么都不写，也不进聊天记录。
  冥想的结束页问一句「有没有什么让你想记住」：记下感受 / 和小光聊聊 / 直接结束。
  不保存就把这次的回答清掉（discard）。练习经验在答完时就给，存不存都算。
「许个愿」（seven_steps_lite）和「让愿望落地」（relearn）不走这里一题一题的问法：它们是对话样子的全屏层，
问题和分支在前端（public/js/flows.js、tune.js），开始、建议、结尾、保存在 core/flows.py。这里只留名字和介绍。

题目字段：q 问题，hint 气泡里的小字；chips 选项；ask {选项: 占位}：选了它才出输入框，答案是输入的文字；
ph 一直显示的输入框；after 选项放在输入框下面；multi / max 多选；none 算作「没想好」的选项；
replies {选项: 小光的回应}、reply_any 选了就回应、reply_unknown 回答「不知道」时的回应；
cta 没有选项、只有一个按钮的页（按钮上的字）；
breath 这一页放一颗慢慢呼吸的光；glow 回应时那颗光变暖、亮起来。
场景上的 calm：冥想的节奏，选了就往下走、不能跳过，问题一行一行慢慢出来；music 背景音乐。
"""
from __future__ import annotations

import re

from .store import Store
from .util import clip

SKIP = "（跳过）"
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
    # 对话样子的两个：问题在前端，流程在 core/flows.py
    "relearn": {
        "title": "让愿望落地", "minutes": 2, "stage": "落地", "icon": "sprout", "review": True, "kind": "tune", "flow": True,
        "desc": "看看这周做得怎么样，把卡住的那一件调到做得成。", "steps": [],
    },
    "seven_steps_lite": {
        "title": "许个愿", "minutes": 2, "stage": "愿望", "icon": "star", "review": True, "kind": "tune", "flow": True,
        "desc": "说出想要的，看见它实现的那一天；或者看看走过的路，给它添点信心。", "steps": [],
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
    st["q"] = st.get("q", "").replace("{intent}", store.profile().get("intent_primary") or "想成为的自己")
    st["index"], st["total"] = i, len(sc["steps"])
    if sc.get("review"):
        st["optional"], st["plain"] = not sc.get("calm"), True
    if sc.get("calm"):        # 冥想：选了就往下走
        st["calm"] = True
        if st.get("chips"):
            st["auto"] = True
    return st


def start(store: Store, scene_id: str) -> dict:
    if scene_id not in SCENES or SCENES[scene_id].get("flow"):    # 许个愿、让愿望落地走 core/flows.py
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
    if SCENES[sid].get("flow"):
        raise KeyError(run_id)
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
    if sc.get("flow") or len(run["answers"]) >= len(steps):
        raise KeyError(run_id)
    step = steps[len(run["answers"])]
    v = _norm(value, sc.get("review", False))
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


def review(store: Store, sid: str, a: list, run_id: str = "") -> dict:
    if sid == "meditation":
        return {"kind": "feel", "say": "刚刚的几分钟里，有没有什么让你想记住？", "choices": FEEL,
                "ph": "写下刚才的感受，一句也好", "to": "会记在「好消息」里"}
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
    if sid != "meditation":     # 许个愿、让愿望落地存在 core/flows.py
        raise KeyError(run_id)
    out = _meditation_talk(run["answers"]) if talk else _meditation_note(store, extra)
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
