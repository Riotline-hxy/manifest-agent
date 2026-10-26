"""Onboarding (creative spec §A, 8 questions → profile) and the guest seed."""
from __future__ import annotations

from datetime import timedelta

from .store import Store
from .util import clip, iso, now

QUESTIONS = [
    {"key": "agent_name", "q": "先给你的伙伴起个名字？", "type": "text", "default": "小光", "ph": "小光"},
    {"key": "agent_avatar_id", "q": "选一个它的气质", "type": "single",
     "options": [{"v": "soft", "label": "柔光", "hue": "#8a7dff"}, {"v": "stardust", "label": "星尘", "hue": "#ff8fb1"},
                 {"v": "ink", "label": "水墨", "hue": "#5c6b7a"}, {"v": "geo", "label": "几何", "hue": "#3fbf9f"}]},
    {"key": "intent_primary", "q": "你这阵子最想靠近的是？", "type": "single_or_text",
     "options": ["自信与表达", "健康作息", "学业或作品", "关系与边界"], "ph": "或者自己写一句"},
    {"key": "intent_why", "q": "为什么这件事对你重要？一句话就好。", "type": "text", "ph": "比如：交换项目时想敢开口"},
    {"key": "schedule_hint", "q": "你更像哪种节奏？", "type": "single", "options": ["早起型", "夜猫", "不固定"]},
    {"key": "traits", "q": "别人常觉得你是？最多选 3 个", "type": "multi", "max": 3,
     "options": ["敏感", "理性", "行动派", "拖延但爆发", "需要被提醒", "喜欢独处"]},
    {"key": "mbti_hint", "q": "有没有想对号入座的类型标签？只是好玩", "type": "single_or_text", "optional": True,
     "options": ["跳过", "不确定"], "ph": "比如 INFP"},
    {"key": "boundaries", "q": "有什么是绝对别碰的？", "type": "multi_or_text",
     "options": ["别说教", "别鸡血催促", "无"], "ph": "别提某个话题……"},
]

HUE_BY_AVATAR = {o["v"]: o["hue"] for o in QUESTIONS[1]["options"]}


def apply(store: Store, answers: dict) -> dict:
    """All-or-nothing: only writes the profile once every required answer is present."""
    a = {}
    for q in QUESTIONS:
        v = answers.get(q["key"])
        if q["type"] in ("multi", "multi_or_text"):
            v = [clip(str(x), 20) for x in (v or []) if str(x).strip()][: q.get("max", 5)]
        else:
            v = clip(str(v or ""), 60)
        if q["key"] == "agent_name":
            v = v or "小光"
        if q["key"] == "mbti_hint" and v in ("跳过",):
            v = ""
        if not v and not q.get("optional") and q["key"] not in ("boundaries",):
            raise ValueError(f"缺少：{q['q']}")
        a[q["key"]] = v
    a["agent_hue"] = HUE_BY_AVATAR.get(a["agent_avatar_id"], "#8a7dff")
    a["onboarded"] = True
    a["last_chat_at"] = iso()
    p = store.set_profile(a)
    # The profile is the core block; mirror the most important parts into
    # archival memory so retrieval can find them by meaning later.
    store.add_memory(f"想靠近「{a['intent_primary']}」，因为{a['intent_why']}", "intent", "onboarding")
    if a["traits"]:
        store.add_memory("觉得自己" + "、".join(a["traits"]), "identity", "onboarding")
    b = [x for x in a["boundaries"] if x != "无"]
    if b:
        store.add_memory("不希望被：" + "、".join(b), "boundary", "onboarding")
    store.log("onboarding", f"完成建档：想靠近「{clip(a['intent_primary'], 16)}」")
    return p


def seed_guest(store: Store) -> None:
    """A believable 12-day history so a judge can see every zone populated.
    Written through the same Store API as real use, with back-dated times."""
    t0 = now() - timedelta(days=11)

    def at(d, h, m=0):
        return iso(t0.replace(hour=h, minute=m, second=0) + timedelta(days=d))

    store.set_profile({
        "agent_name": "小光", "agent_avatar_id": "soft", "agent_hue": "#8a7dff", "nickname": "林夏",
        "intent_primary": "自信与表达", "intent_why": "交换项目时想敢开口说英语", "schedule_hint": "夜猫",
        "traits": ["敏感", "拖延但爆发", "需要被提醒"], "mbti_hint": "INFJ", "boundaries": ["别鸡血催促"],
        "onboarded": True, "proactive": "normal", "xp": 0, "created_at": at(0, 21),
        "last_chat_at": at(10, 22), "last_proactive_at": at(10, 9),
    })
    mem = [
        ("想靠近「自信与表达」，因为交换项目时想敢开口说英语", "intent", "onboarding", "active", 0),
        ("觉得自己敏感、拖延但爆发、需要被提醒", "identity", "onboarding", "active", 0),
        ("不希望被：别鸡血催促", "boundary", "onboarding", "active", 0),
        ("晚上 9–11 点最有精神，早上很难进入状态", "preference", "chat", "active", 2),
        ("在小组讨论里常常想好了却没说出口", "event", "chat", "active", 3),
        ("有具体的人需要她时，更容易开始行动", "insight", "confirmed", "active", 5),
        ("跟熟悉的朋友一起练口语时不紧张", "insight", "chat", "active", 7),
        ("把「拖延」看成准备不足，而不是懒", "insight", "confirmed", "active", 8),
        ("可能更怕说错，而不是不会说", "insight", "chat", "guess", 10),
    ]
    for text, kind, src, status, d in mem:
        m = store.add_memory(text, kind, src, status)
        store.c.execute("UPDATE memory SET created_at=?, updated_at=? WHERE id=?", (at(d, 21), at(d, 21), m["id"]))
    steps = [
        ("跟着播客跟读 3 分钟", "先让嘴巴习惯英语", 1, True),
        ("在课上说一次自己的想法", "小组讨论里先开口一次", 3, True),
        ("给室友讲一个今天学到的英文词", "有人听的时候更容易开始", 5, True),
        ("录一段 30 秒的自我介绍", "交换面试会用到", 6, True),
        ("约 Mia 周末一起练口语 20 分钟", "和熟悉的人练不紧张", 8, True),
        ("把自我介绍改成第二版", "听完录音觉得可以更自然", 9, True),
        ("在小组里主动提一个问题", "从提问开始比发表观点轻松", 11, False),
    ]
    for title, why, d, done in steps:
        s = store.add_step(title, why, "自信与表达")
        store.c.execute("UPDATE step SET created_at=?, due_day=? WHERE id=?", (at(d, 21), at(d, 21)[:10], s["id"]))
        if done:
            store.c.execute("UPDATE step SET status='done', done_at=? WHERE id=?", (at(d, 22), s["id"]))
    recs = [
        ("good", "室友帮我带了奶茶，还记得我要少糖", 0), ("good", "课上老师夸我的问题问得好", 3),
        ("rest", "今天想休息", 4), ("good", "和 Mia 用英语聊了十分钟，比想象中顺", 5),
        ("find", "帮朋友准备面试时我特别投入", 5), ("good", "终于把录音听完了，没那么难听", 6),
        ("good", "Mia 说我口音比上次自然", 8), ("rest", "今天想休息", 9),
        ("good", "楼下的猫今天让我摸了", 9), ("good", "小组里第一次主动提问，大家都在认真听", 10),
    ]
    for type_, text, d in recs:
        r = store.add_record(type_, text)
        store.c.execute("UPDATE record SET created_at=?, day=? WHERE id=?", (at(d, 21), at(d, 21)[:10], r["id"]))
    xp = 20 * 6
    store.set_profile({"xp": xp, "badges": ["first_step", "first_good", "week_one"]})
    convo = [
        (0, 21, "assistant", "你好，我是小光。接下来的日子，我陪你把「想成为的人」变成每天一小步。"),
        (10, 22, "user", "今天小组讨论我主动提了一个问题！"),
        (10, 22, "assistant", "你做到了。上周你还说想好了却说不出口，今天是先开口的那个人。当时心里是什么感觉？"),
        (10, 22, "user", "有点紧张，但说完发现大家都在认真听"),
        (10, 22, "assistant", "记下了，这是第 7 条好消息。紧张还在，但它没有拦住你——这就是变化。"),
    ]
    for d, h, role, text in convo:
        m = store.add_msg(role, text)
        store.c.execute("UPDATE msg SET created_at=? WHERE id=?", (at(d, h), m["id"]))
    for kind, text, d in [("onboarding", "完成建档：想靠近「自信与表达」", 0),
                          ("step", "完成一小步：约 Mia 周末一起练口语 20 分钟", 8),
                          ("memory", "猜了一条：可能更怕说错，而不是不会说", 10),
                          ("record", "记下好消息：小组里第一次主动提问", 10)]:
        store.log(kind, text)
        store.c.execute("UPDATE activity SET at=? WHERE id=(SELECT id FROM activity ORDER BY rowid DESC LIMIT 1)", (at(d, 22),))
