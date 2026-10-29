"""建构流程（8 题 → user_profile）与体验账号的种子数据。

题目与字段沿用 creative/onboarding-and-scenes-v0.1.md，只加了两点：
- 第 3 题之后允许「先跳过，以后再答」，不把问卷变成门槛；
- 新增一题「中断时希望我怎么反应」（care_style），它是「重新认识我」
  场景里同一偏好的早期版本，两者写同一个字段。
"""
from __future__ import annotations

from datetime import timedelta

from . import growth, journey
from .store import Store
from .util import clip, iso, now

QUESTIONS = [
    {"key": "agent_name", "q": "先给你的伙伴起个名字？", "type": "text", "default": "小光", "ph": "小光",
     "hint": "它会一直用这个名字。以后也能改。"},
    {"key": "theme", "q": "选一个你喜欢的氛围", "type": "single", "optional": True, "hint": "点一下就能看到效果，之后随时能换。",
     "options": [{"v": "forest", "label": "森林夜", "sub": "安静、专注"}, {"v": "midnight", "label": "深空", "sub": "极简、夜里聊天"},
                 {"v": "paper", "label": "晨光", "sub": "清爽、白天用"}, {"v": "peach", "label": "暖阳", "sub": "温柔一点"},
                 {"v": "mist", "label": "海雾", "sub": "慢下来"}]},
    {"key": "agent_hue", "q": "给我挑个颜色？", "type": "single", "optional": True, "skip": True,
     "hint": "不选就用这个氛围的默认色。",
     "options": [{"v": c, "label": n} for c, n in (("#f7cb4d", "灯黄"), ("#f2f2f4", "月白"), ("#8b7cff", "薰衣草"),
                                                    ("#ff8a65", "珊瑚"), ("#4fd1a5", "薄荷"), ("#5b9dff", "海蓝"), ("#ff8fb1", "樱粉"))]},
    {"key": "intent_primary", "q": "你这阵子最想靠近的是？", "type": "single_or_text",
     "options": ["自信与表达", "健康作息", "学业或作品", "关系与边界"], "ph": "或者自己写一句"},
    {"key": "intent_why", "q": "为什么这件事对你重要？一句话就好。", "type": "text", "ph": "比如：交换项目时想敢开口"},
    {"key": "schedule_hint", "q": "你更像哪种节奏？", "type": "single", "options": ["早起型", "夜猫", "不固定"],
     "optional": True, "skip": True},
    {"key": "care_style", "q": "如果连续三天没完成计划，你希望我怎么反应？", "type": "single",
     "options": [{"v": "nudge", "label": "轻轻提醒我一下"}, {"v": "analyze", "label": "陪我一起找原因"},
                 {"v": "quiet", "label": "先别提，等我自己说"}],
     "hint": "这个选择以后可以随时改，也会出现在「重新认识我」里。"},
    {"key": "persona", "q": "你希望我是什么样的朋友？", "type": "single", "optional": True,
     "options": [{"v": "gentle", "label": "温柔", "sub": "先接住你的情绪，慢慢说"},
                 {"v": "clear", "label": "有条理", "sub": "帮你把乱糟糟的事理清楚"},
                 {"v": "lively", "label": "活泼", "sub": "轻松一点，偶尔逗你笑"}],
     "hint": "以后在设置里随时能换。"},
    {"key": "traits", "q": "别人常觉得你是？最多选 3 个", "type": "multi", "max": 3,
     "options": ["敏感", "理性", "行动派", "拖延但爆发", "需要被提醒", "喜欢独处"], "optional": True, "skip": True},
    {"key": "mbti_hint", "q": "有没有想对号入座的类型标签？只是好玩", "type": "single_or_text", "optional": True,
     "options": ["跳过", "不确定"], "ph": "比如 INFP"},
    {"key": "boundaries", "q": "有什么是绝对别碰的？", "type": "multi_or_text",
     "options": ["别说教", "别鸡血催促", "无"], "ph": "别提某个话题……", "optional": True, "skip": True},
]

# 小光的形象是固定的（v0.3：Agent 形象稳定，成长发生在宠物身上）；可以换的只有颜色和背景氛围
THEMES = {"forest", "midnight", "paper", "peach", "mist"}
AGENT_COLORS = {"#f7cb4d", "#f2f2f4", "#8b7cff", "#ff8a65", "#4fd1a5", "#5b9dff", "#ff8fb1"}
HUE_BY_AVATAR = {"soft": ""}


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
    if a.get("theme") not in THEMES:
        a["theme"] = "forest"
    if a.get("agent_hue") not in AGENT_COLORS:
        a["agent_hue"] = ""
    a["onboarded"] = True
    a["last_chat_at"] = iso()
    if not a.get("care_style"):
        a["care_style"] = ""
    if a.get("persona") not in ("gentle", "clear", "lively"):
        a["persona"] = "gentle"
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

    def md(d):
        x = t0 + timedelta(days=d)
        return f"{x.month}月{x.day}日"

    def at(d, h, m=0):
        # 「今天」的种子时间不能晚于现在，否则会排在用户真正发的消息后面
        dt = t0.replace(hour=h, minute=m, second=0) + timedelta(days=d)
        cap = now() - timedelta(minutes=5 + (24 - h) * 3)
        return min(dt, cap).isoformat(timespec="seconds")

    store.set_profile({
        "agent_name": "小光", "agent_avatar_id": "soft", "agent_hue": "", "theme": "forest", "nickname": "林夏",
        "intent_primary": "自信与表达", "intent_why": "交换项目时想敢开口说英语", "schedule_hint": "夜猫",
        "traits": ["敏感", "拖延但爆发", "需要被提醒"], "mbti_hint": "INFJ", "boundaries": ["别鸡血催促"],
        "care_style": "analyze", "onboarded": True, "proactive": "normal", "xp": 0, "persona": "gentle",
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
        ("把「拖延」看成准备不足", "insight", "confirmed", "active", 8),
        ("可能其实会说，更怕的是说错", "insight", "chat", "guess", 10),
        ("中断时更希望被陪着找原因，不想被催", "preference", "scene:relearn", "active", 11),
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
        ("rest", "今天偷个懒：连着上了三天早八，有点累", 4), ("good", "和 Mia 用英语聊了十分钟，比想象中顺", 5),
        ("meme", "录音里的我：这是谁？？我平时就是这个声音吗", 5), ("good", "终于把录音听完了，没那么难听", 6),
        ("good", "Mia 说我口音比上次自然", 8), ("rest", "今天偷个懒：就是想歇歇", 9),
        ("meme", "我：今晚一定早睡。也是我：凌晨一点在看猫咪视频", 11),
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
                          ("memory", "猜了一条：可能其实会说，更怕的是说错", 10),
                          ("record", "记下好消息：小组里第一次主动提问", 10),
                          ("scene", "完成「重新认识我」，互动偏好：一起找原因", 11)]:
        store.log(kind, text)
        store.c.execute("UPDATE activity SET at=? WHERE id=(SELECT id FROM activity ORDER BY rowid DESC LIMIT 1)", (at(d, 22),))
    store.push_inbox("明天那一步不急。今天想说的话，我都在。", "checkin")
    store.c.execute("UPDATE inbox SET created_at=?", (at(13, 9),))

    # 过去三晚的日终整理（与 core/digest.py 写入的结构一致）
    digests = [
        (11, "你完成了「重新认识我」，说中断时更想被陪着找原因。", ["选了「一起找原因」", "把第一句话练顺"],
         {"added": 1, "updated": 0, "deleted": 0, "guesses": 0, "user_lines": 6},
         [{"op": "ADD", "text": "中断时更希望被陪着找原因，不想被催", "kind": "preference", "status": "active"}]),
        (12, "面试官笑了一下，你没那么紧张了。开场白练了一次。", ["面试官笑了一下", "对着镜子练开场"],
         {"added": 0, "updated": 1, "deleted": 0, "guesses": 0, "user_lines": 4},
         [{"op": "UPDATE", "text": "跟熟悉的朋友一起练口语时不紧张，面对陌生人也在慢慢放松",
           "old": "跟熟悉的朋友一起练口语时不紧张", "kind": "insight", "status": ""}]),
        (13, "早上居然自然醒了，还读完一篇英文播客文稿。", ["自然醒", "读完一篇文稿"],
         {"added": 0, "updated": 0, "deleted": 0, "guesses": 1, "user_lines": 3},
         [{"op": "ADD", "text": "可能其实会说，更怕的是说错", "kind": "insight", "status": "guess"}]),
    ]
    for d, summary, hl, stats, ops in digests:
        store.save_digest(at(d, 3)[:10], summary, hl, stats, ops, True)
        store.c.execute("UPDATE digest SET created_at=? WHERE day=?", (at(d + 1, 3, 10), at(d, 3)[:10]))
    store.set_profile({"last_digest_day": at(13, 3)[:10]})
    store.bump("report_open", 0)

    # 两张成长轨迹看板：主线「自信与表达」，加一张「心灵平静」（文档里的首个主题示例）
    def seed_wish(title, cat, now_t, vision_t, start_d, items, span=60):
        w = journey.add_wish(store, title, cat, now_t, vision_t, started=at(start_d, 9)[:10],
                             target_day=at(start_d + span, 9)[:10])
        store.c.execute("UPDATE wish SET created_at=? WHERE id=?", (at(start_d, 9), w["id"]))
        ids = []
        for d, h, text, feeling in items:
            m = journey.add_moment(store, w["id"], text, feeling, day=at(d, h)[:10])
            store.c.execute("UPDATE moment SET created_at=?, updated_at=? WHERE id=?", (at(d, h), at(d, h), m["id"]))
            ids.append(m["id"])
        return w, ids

    conf, cids = seed_wish("自信与表达", "confidence", "想好了却不敢开口，怕说错，怕别人觉得我笨。",
                           "在小组里、在面试里，都能自然地说出自己的想法", 0, [
        (1, 21, "跟着播客跟读了三分钟，声音很小，但读完了。", "有点不好意思，但还行"),
        (3, 15, "在课上开口说了一次自己的想法，声音在抖。", "说完心跳很快，但没有人笑"),
        (5, 20, "和 Mia 用英语聊了十分钟，比想象中顺。", "原来我可以"),
        (6, 22, "录了 30 秒自我介绍，听了三遍才敢删掉重录。", "第二遍好多了"),
        (8, 16, "周末和 Mia 练口语，她说我口音比上次自然。", "被看见的感觉很好"),
        (10, 14, "小组讨论里第一次主动开口提问，大家都在认真听。", "紧张还在，但它没拦住我"),
        (12, 10, "面试开场前对着镜子练了一次，面试官笑了一下。", "没那么紧张了"),
        (14, 20, "把自我介绍发给 Mia 听，她说听起来像我。", "想继续练"),
    ])
    calm, _ = seed_wish("心灵平静", "calm", "睡前总在想白天没做好的事，脑子停不下来。", "在忙碌中也能找到平静的片刻", 5, span=40, items=[
        (5, 22, "睡前做了六轮四拍呼吸，第三轮开始肩膀松下来了。", "比平时早一点睡着"),
        (8, 18, "今天开完会有些紧张，我给自己留了十分钟，安静地喝了一杯茶。", "慢慢放松了一些"),
        (10, 21, "绕操场慢慢走了两圈，没戴耳机。", "脑子里的声音小了一点"),
        (13, 23, "又开始想白天说错的话，这次没跟着想下去，写在纸上就去睡了。", "有点意外，原来可以放下"),
        (14, 12, "午饭后在楼下晒了十分钟太阳。", "暖暖的"),
    ])
    store.c.execute("UPDATE step SET wish_id=? WHERE wish_id='' OR wish_id IS NULL", (conf["id"],))

    # 路径：习惯（带打卡历史，今天留给访客自己打）+ 里程碑。历史打卡不补经验，保持 306 的进化演示
    def seed_habit(w, title, freq, per_week, days, created_d):
        h = journey.add_habit(store, w["id"], title, freq, per_week)
        store.c.execute("UPDATE habit SET created_at=? WHERE id=?", (at(created_d, 9), h["id"]))
        for d in days:
            store.c.execute("INSERT OR IGNORE INTO habit_log(id, habit_id, day, created_at) VALUES(?,?,?,?)",
                            (f"hl_{h['id']}_{d}", h["id"], at(d, 21)[:10], at(d, 21)))
    seed_habit(conf, "跟读英文播客 5 分钟", "daily", 7, [1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13], 1)
    seed_habit(conf, "小组里主动开口", "weekly", 2, [3, 10, 12], 3)
    seed_habit(calm, "睡前做 6 轮呼吸", "daily", 7, [5, 6, 8, 10, 11, 13], 5)
    for w, title, due_d, done_d in [(conf, "第一次在小组里先开口", 10, 10), (conf, "录好英文自我介绍", 16, None),
                                    (conf, "能用英语聊满 20 分钟", 38, None), (calm, "一周有 5 天按时睡着", 24, None)]:
        m = journey.add_milestone(store, w["id"], title, at(due_d, 9)[:10])
        store.c.execute("UPDATE milestone SET created_at=?, status=?, done_at=? WHERE id=?",
                        (at(1, 21), "done" if done_d is not None else "todo", at(done_d, 22) if done_d is not None else "", m["id"]))
    store.c.execute("INSERT INTO insight(id, wish_id, text, claim, basis, status, created_at) VALUES(?,?,?,?,?,?,?)",
                    ("in_seed", conf["id"], "你说过常常想好了却说不出口，但这两周你有三次是自己先开口的。你觉得，这算是更相信自己的开始吗？",
                     "这两周有三次主动开口，开始更相信自己了", journey.dumps([cids[1], cids[5], cids[6]]), "open", at(14, 21)))
    store.set_profile({"current_wish": conf["id"]})
    store.set_profile({"notebook": {"by": "digest", "day": at(13, 3)[:10], "updated_at": at(14, 3), "text": (
        "最近的生活：大三，在准备交换项目；晚上 9–11 点最有精神，早上很难进入状态。\n"
        "在意的人：Mia——一起练英语口语的朋友，和她说话不紧张；室友会记得她奶茶要少糖。\n"
        "正在努力的事：敢开口说英语。录了 30 秒自我介绍，改到第二版，准备发给 Mia 听；在小组里试着先开口。\n"
        "心情和状态：开口前会紧张，但说完常常发现没那么可怕；累的时候会给自己放一天假。\n"
        "相处时的偏好：中断时希望被陪着找原因，不想被催；不喜欢鸡血式的鼓励。\n"
        f"时间线：{md(3)} 第一次在课上开口，声音在抖；{md(6)} 录完自我介绍；{md(10)} 小组里第一次主动提问；"
        f"{md(12)} 面试前对着镜子练开场，面试官笑了一下。")}})
    from . import cheer
    store.set_profile({"cheer": {"slot": cheer.slot(), "kind": "you", "label": "最近的你", "source": "", "at": at(14, 12),
                                 "text": "这两周你有三次是自己先开口的，声音在抖也说完了。"}})

    # 示例账号里已经发生的进化与徽章算作「看过」，免得第一次打开就弹一串庆祝
    total = growth.total_xp(store)
    store.set_profile({"pet_stage_seen": growth.stage_of(total, "")["key"]})
    growth.badges(store, total=total)
