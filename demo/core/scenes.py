"""灵感 scenes from creative/onboarding-and-scenes-v0.1.md, run as step machines.

Unlike v0 (pre-baked bubbles), each step waits for the user's answer. When the
last step is answered, the scene writes back exactly what the creative spec
asks for (≥1 memory_entry or plan_step).

A step can offer `chips` (tap-to-answer), and `timer` for the breathing
countdown the client renders.
"""
from __future__ import annotations

from .store import Store
from .util import clip

SCENES = {
    "relearn": {
        "title": "重新认识我", "minutes": 4, "stage": "偏好", "icon": "compass",
        "desc": "六个生活中的小岔路。答完，小光会知道以后怎么陪你。",
        "steps": [
            {"q": "如果连续三天没完成计划，你更希望小光怎么反应？",
             "chips": ["轻轻提醒我一下", "陪我一起找原因", "先别提，等我自己说"],
             "save": {"field": "care_style",
                      "map": {"轻轻提醒我一下": "nudge", "陪我一起找原因": "analyze", "先别提，等我自己说": "quiet"}}},
            {"q": "你更愿意怎么被称呼？", "ph": "比如：小鱼、名字、随便叫"},
            {"q": "一天里，你状态最好的时候通常是？",
             "chips": ["早上", "下午", "晚上", "不固定"]},
            {"q": "完成一件小事以后，你希望被怎样对待？",
             "chips": ["被看见、被说出来", "自己知道就好", "想听具体的观察，不想听夸奖"]},
            {"q": "有什么话题你现在不想聊？", "ph": "写一个词就好，也可以跳过", "optional": True},
            {"q": "最后一题：如果只能改一件小事，你想先改哪件？", "ph": "越具体越好"},
        ],
    },
    "clarify": {
        "title": "说清想要的", "minutes": 3, "stage": "澄清",
        "desc": "把模糊的「想变好」说成一个具体画面。",
        "steps": [
            {"q": "用一句话说你想要的生活片段（不是职位名）。", "ph": "比如：周末早上，在阳台上写完一篇自己满意的文章"},
            {"q": "去掉「应该」之后，哪半句是真的？", "ph": "留下你真正想要的那部分"},
            {"q": "如果它已经实现了，明天早上你会先做什么？", "ph": "越小越好"},
        ],
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
        "title": "短冥想引导", "minutes": 4, "stage": "感受",
        "desc": "4 拍吸、4 拍呼，六轮，然后感受愿望实现时的身体。",
        "steps": [
            {"q": "找个舒服的姿势。跟着圆圈呼吸：4 拍吸、4 拍呼，共 6 轮。准备好就开始。",
             "timer": {"inhale": 4, "exhale": 4, "rounds": 6}, "chips": ["做完了"]},
            {"q": "想象你的意图已经实现了。身体哪里最先放松？", "ph": "肩膀、眉心、胸口……"},
            {"q": "用一个词记下这种感觉。", "chips": ["平静", "轻松", "温暖", "踏实", "开阔"]},
        ],
    },
    "seven_steps_lite": {
        "title": "七步轻走一遍", "minutes": 6, "stage": "七步",
        "desc": "澄清→信念→感受→行动→感恩→释放→见证，每步一句话。",
        "steps": [
            {"q": "① 澄清｜你现在最想靠近的是「{intent}」。还是它吗？可以改一句。", "chips": ["还是它"], "ph": "或者写下新的那一句"},
            {"q": "② 信念｜补完这句：我配得上它，因为……", "ph": "我配得上，因为……"},
            {"q": "③ 感受｜想到它实现时，你更接近哪种情绪？", "chips": ["平静", "兴奋", "坚定", "温柔"]},
            {"q": "④ 行动｜今天能做的一小步是什么？", "ph": "5 分钟能做完的"},
            {"q": "⑤ 感恩｜一句你已经拥有的。", "ph": "我已经有……"},
            {"q": "⑥ 释放｜写下一个可以先放下的执念。不评判它。", "ph": "比如：必须一次做到完美"},
            {"q": "⑦ 见证｜允许自己慢一点？", "chips": ["允许自己慢一点"]},
        ],
    },
}


def catalog() -> list[dict]:
    return [{"id": k, "title": v["title"], "minutes": v["minutes"], "stage": v["stage"], "desc": v["desc"],
             "icon": v.get("icon", ""), "steps": len(v["steps"])} for k, v in SCENES.items()]


def _render_step(scene_id: str, i: int, profile: dict) -> dict:
    st = dict(SCENES[scene_id]["steps"][i])
    st["q"] = st["q"].replace("{intent}", profile.get("intent_primary") or "想成为的自己")
    st["index"], st["total"] = i, len(SCENES[scene_id]["steps"])
    return st


def start(store: Store, scene_id: str) -> dict:
    if scene_id not in SCENES:
        raise KeyError(scene_id)
    run = store.start_scene(scene_id)
    store.log("scene", f"开始灵感场景「{SCENES[scene_id]['title']}」")
    return {"run": run, "scene": {"id": scene_id, "title": SCENES[scene_id]["title"]},
            "step": _render_step(scene_id, 0, store.profile())}


def resume(store: Store, run_id: str) -> dict:
    run = store.get_scene(run_id)
    if not run or run["status"] != "open":
        raise KeyError(run_id)
    sid = run["scene"]
    return {"run": run, "scene": {"id": sid, "title": SCENES[sid]["title"]},
            "step": _render_step(sid, len(run["answers"]), store.profile())}


def answer(store: Store, run_id: str, text: str) -> dict:
    run = store.get_scene(run_id)
    if not run or run["status"] != "open":
        raise KeyError(run_id)
    sid = run["scene"]
    steps = SCENES[sid]["steps"]
    answers = list(run["answers"]) + [clip(text, 300)]
    if len(answers) < len(steps):
        store.update_scene(run_id, len(answers), answers)
        return {"done": False, "step": _render_step(sid, len(answers), store.profile())}
    store.update_scene(run_id, len(answers), answers, "done")
    wrote = finish(store, sid, answers)
    store.log("scene", f"完成「{SCENES[sid]['title']}」，" + "、".join(w["label"] for w in wrote))
    return {"done": True, "wrote": wrote, "summary": summary(sid, answers)}


def finish(store: Store, sid: str, a: list[str]) -> list[dict]:
    """Write-back rules from the creative spec §B."""
    out = []

    def mem(text, kind):
        m = store.add_memory(text, kind, "scene:" + sid)
        out.append({"type": "memory", "label": "记住了一条", "item": m})

    def step(title, why):
        s = store.add_step(title, why=why, wish=store.profile().get("intent_primary") or "")
        out.append({"type": "step", "label": "加了一小步", "item": s})

    def rec(type_, text):
        r = store.add_record(type_, text)
        out.append({"type": "record", "label": "记下一条好消息" if type_ == "good" else "记下一条发现", "item": r})

    if sid == "relearn":
        steps_def = SCENES["relearn"]["steps"]
        patch = {}
        for i, sd in enumerate(steps_def):
            field = (sd.get("save") or {}).get("field")
            if not field or i >= len(a):
                continue
            val = a[i]
            mapping = (sd.get("save") or {}).get("map") or {}
            patch[field] = mapping.get(val, clip(val, 60))
        if a[1]:
            patch["nickname"] = clip(a[1], 16)
        if a[2]:
            patch["schedule_hint"] = clip(a[2], 12)
        if patch:
            store.set_profile(patch)
            out.append({"type": "profile", "label": "更新了互动偏好", "item": patch})
        if a[3]:
            mem("完成一件小事后更希望：" + clip(a[3], 40), "preference")
        if a[4] and a[4] not in ("跳过", "无", "（跳过）"):
            mem("暂时不想聊：" + clip(a[4], 40), "boundary")
        if a[5]:
            step(clip(a[5], 40), "来自「重新认识我」：想先改的那件小事")
    elif sid == "clarify":
        step(clip(a[2], 40), "来自「说清想要的」：" + clip(a[0], 40))
        mem("想要的画面：" + clip(a[1] or a[0], 60), "intent")
    elif sid == "gratitude":
        text = "；".join(clip(x, 40) for x in a)
        rec("good", text)
        mem("感恩三件事：" + text, "good_news")
    elif sid == "meditation":
        mem(f"想到意图实现时，{clip(a[1], 20)}先放松，感觉是「{clip(a[2], 8)}」", "insight")
        rec("find", f"冥想时的感觉：{clip(a[2], 8)}")
    elif sid == "seven_steps_lite":
        if a[0] and a[0] != "还是它":
            store.set_profile({"intent_primary": clip(a[0], 40)})
        step(clip(a[3], 40), "七步显化 · 行动")
        mem("我配得上它，因为" + clip(a[1].removeprefix("我配得上，因为"), 50), "insight")
        if a[5]:
            rec("find", "可以先放下：" + clip(a[5], 40))
    return out


def summary(sid: str, a: list[str]) -> str:
    if sid == "relearn":
        style = {"轻轻提醒我一下": "轻轻提醒你", "陪我一起找原因": "陪你一起看原因",
                 "先别提，等我自己说": "先不提，等你开口"}.get(a[0], "按你选的来")
        return f"记下了。以后你中断的时候，我会{style}。这些都可以在「我的空间」里改。"
    if sid == "clarify":
        return f"你想要的画面是「{clip(a[0], 30)}」。明天早上的第一件事，我放进计划了：{clip(a[2], 30)}。"
    if sid == "gratitude":
        return "三件好事都收好了。今天其实没有那么空。"
    if sid == "meditation":
        return f"记下了这种「{clip(a[2], 8)}」。下次想放弃的时候，可以先回到这里。"
    return f"七步走完了。今天那一小步是：{clip(a[3], 30)}。慢一点也算数。"
