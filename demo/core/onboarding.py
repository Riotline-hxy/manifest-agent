"""建构流程（8 题 → user_profile）与体验账号的种子数据。

题目与字段沿用 creative/onboarding-and-scenes-v0.1.md，只加了两点：
- 第 3 题之后允许「先跳过，以后再答」，不把问卷变成门槛；
- 新增一题「中断时希望我怎么反应」（care_style），它是「重新认识我」
  场景里同一偏好的早期版本，两者写同一个字段。
"""
from __future__ import annotations

from datetime import timedelta

from . import growth
from .store import Store
from .util import clip, iso, now

QUESTIONS = [
    {"key": "agent_name", "q": "先给你的伙伴起个名字？", "type": "text", "default": "小光", "ph": "小光",
     "hint": "它会一直用这个名字。以后也能改。"},
    {"key": "agent_avatar_id", "q": "选一个它的气质", "type": "single",
     "options": [{"v": "soft", "label": "柔光", "hue": "#8a7dff"}, {"v": "stardust", "label": "星尘", "hue": "#ff8fb1"},
                 {"v": "ink", "label": "水墨", "hue": "#5c6b7a"}, {"v": "geo", "label": "几何", "hue": "#3fbf9f"}]},
    {"key": "intent_primary", "q": "你这阵子最想靠近的是？", "type": "single_or_text",
     "options": ["自信与表达", "健康作息", "学业或作品", "关系与边界"], "ph": "或者自己写一句"},
    {"key": "intent_why", "q": "为什么这件事对你重要？一句话就好。", "type": "text", "ph": "比如：交换项目时想敢开口"},
    {"key": "schedule_hint", "q": "你更像哪种节奏？", "type": "single", "options": ["早起型", "夜猫", "不固定"],
     "optional": True, "skip": True},
    {"key": "care_style", "q": "如果连续三天没完成计划，你希望我怎么反应？", "type": "single",
     "options": [{"v": "nudge", "label": "轻轻提醒我一下"}, {"v": "analyze", "label": "陪我一起找原因"},
                 {"v": "quiet", "label": "先别提，等我自己说"}],
     "hint": "这个选择以后可以随时改，也会出现在「重新认识我」里。"},
    {"key": "traits", "q": "别人常觉得你是？最多选 3 个", "type": "multi", "max": 3,
     "options": ["敏感", "理性", "行动派", "拖延但爆发", "需要被提醒", "喜欢独处"], "optional": True, "skip": True},
    {"key": "mbti_hint", "q": "有没有想对号入座的类型标签？只是好玩", "type": "single_or_text", "optional": True,
     "options": ["跳过", "不确定"], "ph": "比如 INFP"},
    {"key": "boundaries", "q": "有什么是绝对别碰的？", "type": "multi_or_text",
     "options": ["别说教", "别鸡血催促", "无"], "ph": "别提某个话题……", "optional": True, "skip": True},
]

HUE_BY_AVATAR = {o["v"]: o["hue"] for o in QUESTIONS[1]["options"]}


def apply(store: Store, answers: dict) -> dict:
    """Only writes once every required answer is present. Optional questions may
    be skipped with an empty value; the profile simply stays unknown there."""
    a = {}
    for q in QUESTIONS:
        v = answers.get(q["key"])
        if q["type"] in ("multi", "multi_or_text"):
            v = [clip(str(x), 20) for x in (v or []) if str(x).strip()][: q.get("max", 5)]
        elif q["type"] == "single" and isinstance(v, dict):
            v = v.get("v") or v.get("label") or ""
        else:
            v = clip(str(v or ""), 60)
        if q["key"] == "agent_name":
            v = v or "小光"
        if q["key"] == "mbti_hint" and v in ("跳过",):
            v = ""
        if not v and not q.get("optional") and q["key"] not in ("boundaries",):
            raise ValueError(f"缺少：{q['q']}")
        a[q["key"]] = v
    if isinstance(a.get("agent_avatar_id"), str) and a["agent_avatar_id"] in HUE_BY_AVATAR:
        a["agent_hue"] = HUE_BY_AVATAR[a["agent_avatar_id"]]
    a["onboarded"] = True
    a["last_chat_at"] = iso()
    if not a.get("care_style"):
        a["care_style"] = ""
    p = store.set_profile(a)
    # profile is the always-on core block; mirror the most important parts into
    # archival memory so retrieval can find them later by meaning.
    store.add_memory(f"想靠近「{a['intent_primary']}」，因为{a['intent_why']}", "intent", "onboarding")
    if a["traits"]:
        store.add_memory("觉得自己" + "、".join(a["traits"]), "identity", "onboarding")
    b = [x for x in a["boundaries"] if x != "无"]
    if b:
        store.add_memory("不希望被：" + "、".join(b), "boundary", "onboarding")
    store.log("onboarding", f"完成建档：想靠近「{clip(a['intent_primary'], 16)}」")
    return p


def seed_guest(store: Store) -> None:
    """A believable 15-day history so a first-time visitor sees every zone
    populated. Written through the same Store API as real use, with back-dated
    times, and the XP ledger is built by growth.award on those past rows so the
    per-day / per-source caps hold exactly like a real account."""
    t0 = now() - timedelta(days=14)

    def at(d, h, m=0):
        return (t0.replace(hour=h, minute=m, second=0) + timedelta(days=d)).isoformat(timespec="seconds")

    store.set_profile({
        "agent_name": "小光", "agent_avatar_id": "soft", "agent_hue": "#8a7dff", "nickname": "林夏",
        "intent_primary": "自信与表达", "intent_why": "交换项目时想敢开口说英语", "schedule_hint": "夜猫",
        "traits": ["敏感", "拖延但爆发", "需要被提醒"], "mbti_hint": "INFJ", "boundaries": ["别鸡血催促"],
        "care_style": "analyze", "onboarded": True, "proactive": "normal", "xp": 0,
        "pet_name": "小芽", "pet_branch": "",
        "created_at": at(0, 21), "last_chat_at": at(14, 22), "last_proactive_at": at(13, 9),
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
        ("中断时更希望被陪着找原因，而不是被催", "preference", "scene:relearn", "active", 11),
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
        ("在小组里主动提一个问题", "从提问开始比发表观点轻松", 11, True),
        ("面试前对着镜子练一次开场", "想把第一句话练顺", 12, True),
        ("读一篇英文播客的文稿", "听懂和读懂的差距", 13, True),
        ("把自我介绍发给 Mia 听", "有人听的时候更容易改", 14, False),
        ("在便利店用英语问一次路", "把练习放进真实场景", 14, False),
    ]
    done_rows = []
    for title, why, d, done in steps:
        s = store.add_step(title, why, "自信与表达")
        store.c.execute("UPDATE step SET created_at=?, due_day=? WHERE id=?", (at(d, 21), at(d, 21)[:10], s["id"]))
        if done:
            store.c.execute("UPDATE step SET status='done', done_at=? WHERE id=?", (at(d, 22), s["id"]))
            done_rows.append((d, s["id"], title))

    recs = [
        ("good", "室友帮我带了奶茶，还记得我要少糖", 0), ("good", "课上老师夸我的问题问得好", 3),
        ("rest", "今天想休息", 4), ("good", "和 Mia 用英语聊了十分钟，比想象中顺", 5),
        ("find", "帮朋友准备面试时我特别投入", 5), ("good", "终于把录音听完了，没那么难听", 6),
        ("good", "Mia 说我口音比上次自然", 8), ("rest", "今天想休息", 9),
        ("good", "楼下的猫今天让我摸了", 9), ("good", "小组里第一次主动提问，大家都在认真听", 10),
        ("good", "面试官笑了一下，我没那么紧张了", 12), ("good", "早上居然自然醒了", 13),
        ("good", "把自我介绍发给 Mia，她说听起来像我", 14),
    ]
    good_rows = []
    for type_, text, d in recs:
        r = store.add_record(type_, text)
        store.c.execute("UPDATE record SET created_at=?, day=? WHERE id=?", (at(d, 21), at(d, 21)[:10], r["id"]))
        if type_ == "good":
            good_rows.append((d, r["id"]))

    # 三次已完成的练习 + 两个已走的场景
    for sid, d in [("meditation", 4), ("gratitude", 8), ("clarify", 11)]:
        rid = f"sc_seed_{sid}"
        store.c.execute(
            "INSERT OR REPLACE INTO scene_run(id, scene, step, answers, status, created_at) VALUES(?,?,?,?,?,?)",
            (rid, sid, 9, "[]", "done", at(d, 20)))

    # 经验账本：按日期逐条记，走 award 的同一套限额与去重
    def backdated_award(source, ref, d, hour=21):
        out = growth.award(store, source, ref=ref, note="")
        if out.get("ok") and out.get("amount"):
            row = out["row"]
            store.c.execute("UPDATE xp SET created_at=?, day=? WHERE id=?", (at(d, hour), at(d, hour)[:10], row["id"]))
            # award() already bumped profile xp; recompute at the end instead
        return out

    for d, sid, title in done_rows:
        backdated_award("action", "step:" + sid, d, 22)
    for d, rid in good_rows:
        backdated_award("good", "rec:" + rid, d, 20)
    for sid, d in [("meditation", 4), ("gratitude", 8), ("clarify", 11)]:
        backdated_award("practice", "scene:sc_seed_" + sid, d, 20)
    for d in range(15):
        backdated_award("checkin", "day:" + at(d, 9)[:10], d, 9)

    total = int(store.c.execute("SELECT COALESCE(SUM(amount),0) FROM xp").fetchone()[0])
    store.set_profile({"xp": total})
    store.c.execute("UPDATE xp SET day=substr(created_at,1,10)")

    convo = [
        (0, 21, "assistant", "你好，我是小光。接下来的日子，我陪你把「想成为的人」变成每天一小步。"),
        (10, 22, "user", "今天小组讨论我主动提了一个问题！"),
        (10, 22, "assistant", "你做到了。上周你还说想好了却说不出口，今天是先开口的那个人。当时心里是什么感觉？"),
        (10, 22, "user", "有点紧张，但说完发现大家都在认真听"),
        (10, 22, "assistant", "紧张还在，但它没有拦住你——这就是变化。要不要把这件事记成一条好消息？"),
        (14, 22, "assistant", "明天就是把自我介绍发给 Mia 了。要不要今晚先听一遍自己的录音？"),
    ]
    for d, h, role, text in convo:
        m = store.add_msg(role, text)
        store.c.execute("UPDATE msg SET created_at=? WHERE id=?", (at(d, h), m["id"]))
    for kind, text, d in [("onboarding", "完成建档：想靠近「自信与表达」", 0),
                          ("step", "完成一小步：约 Mia 周末一起练口语 20 分钟", 8),
                          ("memory", "猜了一条：可能更怕说错，而不是不会说", 10),
                          ("record", "记下好消息：小组里第一次主动提问", 10),
                          ("scene", "完成「重新认识我」，互动偏好：一起找原因", 11)]:
        store.log(kind, text)
        store.c.execute("UPDATE activity SET at=? WHERE id=(SELECT id FROM activity ORDER BY rowid DESC LIMIT 1)", (at(d, 22),))
    store.push_inbox("明天那一步不急。今天想说的话，我都在。", "checkin")
    store.c.execute("UPDATE inbox SET created_at=?", (at(13, 9),))
