"""建档：三段，每段一屏、都能跳过（public/js/views/onboarding.js）。
- 小光：外貌、说话方式（persona）、几天没动时怎么陪你（care_style）、名字；
- 你：怎么称呼、作息节奏、像什么样的人、别对我做什么——写进画像和几条基础记忆；
- 第一个愿望：一个方向 + 现成的路（1 个里程碑、几个小步、1 个习惯），直接放进蜕变计划。
什么都不填也能进门：画像用默认值，不建愿望。
"""
from __future__ import annotations

from datetime import timedelta

from . import growth, journey
from .store import Store
from .util import clip, iso, now, parse_iso

# 小光的外貌：形状.颜色.质感（和 public/js/jelly.js 里的 LOOK_SHAPES / THEMES / MATERIALS 保持一致）
LOOK_SHAPES = {"cloud", "mochi", "cat", "star", "cube", "flower"}
# 下架的形状：存过的外貌换成最接近的保留形状，颜色和质感不变（和 jelly.js 的 RETIRED 一致）
RETIRED_SHAPES = {"hex": "cube", "pudding": "cube", "onigiri": "mochi", "drop": "mochi", "gummy": "mochi", "heart": "flower"}
LOOK_COLORS = {"origin", "gold", "moon", "dawn", "sun", "mint", "sea", "sakura", "orange", "sky", "lilac", "night"}
LOOK_MATERIALS = {"jelly", "liquid"}
LOOK_DEFAULT = "cloud.moon.jelly"


def norm_look(v) -> str:
    """Old shape names become the shape that replaced them; anything else is returned as is."""
    parts = str(v or "").split(".")
    if len(parts) == 3:
        parts[0] = RETIRED_SHAPES.get(parts[0], parts[0])
    return ".".join(parts)


def valid_look(v) -> bool:
    parts = str(v or "").split(".")
    return len(parts) == 3 and parts[0] in LOOK_SHAPES and parts[1] in LOOK_COLORS and parts[2] in LOOK_MATERIALS


PERSONAS = ("gentle", "clear", "lively")
CARE_STYLES = ("nudge", "analyze", "quiet")
SCHEDULES = ("早起型", "夜猫", "不固定")
WISH_SPANS = (30, 90, 180)
# 建档写进画像的字段（前端按三段来问；这里只认这些）
QUESTIONS = [{"key": k, "section": s} for s, ks in (
    ("agent", ("agent_avatar_id", "persona", "care_style", "agent_name")),
    ("me", ("nickname", "schedule_hint", "traits", "boundaries")),
    ("wish", ("intent_primary", "intent_why", "wish")),
) for k in ks]

# 背景氛围在首页就能选；小光的外貌用户自己选，成长发生在用户自己的小镇上
THEMES = {"forest", "midnight", "paper", "peach", "mist"}
AGENT_COLORS = {"#f7cb4d", "#f2f2f4", "#8b7cff", "#ff8a65", "#4fd1a5", "#5b9dff", "#ff8fb1"}


def _texts(v, n: int, size: int = 20) -> list[str]:
    return [clip(str(x).strip(), size) for x in (v or []) if str(x).strip()][:n] if isinstance(v, list) else []


def apply(store: Store, answers: dict) -> dict:
    """Every answer is optional; anything missing or out of range falls back to a default."""
    g = lambda k: answers.get(k)
    a = {
        "agent_name": clip(str(g("agent_name") or "").strip(), 8) or "小光",
        "agent_avatar_id": norm_look(g("agent_avatar_id")) if valid_look(norm_look(g("agent_avatar_id"))) else LOOK_DEFAULT,
        "persona": g("persona") if g("persona") in PERSONAS else "gentle",
        "care_style": g("care_style") if g("care_style") in CARE_STYLES else "nudge",
        "theme": g("theme") if g("theme") in THEMES else "forest",
        "schedule_hint": g("schedule_hint") if g("schedule_hint") in SCHEDULES else "",
        "traits": _texts(g("traits"), 3),
        "boundaries": [x for x in _texts(g("boundaries"), 5) if x != "无"],
        "intent_primary": clip(str(g("intent_primary") or "").strip(), 60),
        "intent_why": clip(str(g("intent_why") or "").strip(), 60),
        "mbti_hint": "" if str(g("mbti_hint") or "") in ("跳过", "不确定") else clip(str(g("mbti_hint") or "").strip(), 12),
        "agent_hue": g("agent_hue") if g("agent_hue") in AGENT_COLORS else "",
        "onboarded": True,
        "last_chat_at": iso(),
    }
    nick = clip(str(g("nickname") or "").strip(), 12)
    if nick:
        a["nickname"] = nick
    wish = g("wish") if isinstance(g("wish"), dict) else None
    if wish and not a["intent_primary"]:
        a["intent_primary"] = clip(str(wish.get("title") or "").strip(), 60)
    p = store.set_profile(a)
    # 画像是常驻的核心块；最重要的几条同时写进记忆，聊天时能按意思检索到
    if a["intent_primary"]:
        store.add_memory(f"想靠近「{a['intent_primary']}」" + (f"，因为{a['intent_why']}" if a["intent_why"] else ""), "intent", "onboarding")
    if a["traits"]:
        store.add_memory("觉得自己" + "、".join(a["traits"]), "identity", "onboarding")
    if a["schedule_hint"]:
        store.add_memory({"早起型": "习惯早起", "夜猫": "是夜猫子，晚上更有精神", "不固定": "作息不太固定，看心情"}[a["schedule_hint"]], "preference", "onboarding")
    if a["boundaries"]:
        store.add_memory("不希望被：" + "、".join(a["boundaries"]), "boundary", "onboarding")
    for text in _texts(g("remember"), 3):     # 聊第一个愿望时，小光从 TA 原话里记下的
        store.add_memory(text, "identity", "onboarding")
    if wish:
        make_wish(store, wish, a["intent_why"])
    store.log("onboarding", "完成建档" + (f"：想靠近「{clip(a['intent_primary'], 16)}」" if a["intent_primary"] else ""))
    return p


def make_wish(store: Store, wish: dict, why: str = "") -> dict | None:
    """第一个愿望和它的路：一个里程碑、几个小步、一个习惯；每一项都走和手动添加一样的校验。"""
    title = clip(str(wish.get("title") or "").strip(), 30)
    if not title:
        return None
    cat = wish.get("category") if wish.get("category") in journey.CATEGORIES else journey.guess_category(title)
    try:
        days = int(wish.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    days = days if days in WISH_SPANS else 30
    w = journey.add_wish(store, title, cat, vision_text=why, target_day=(now().date() + timedelta(days=days)).isoformat())
    rows = lambda k, n: [{"title": t} for t in _texts(wish.get(k), n, 40)]
    try:
        due = max(7, min(days, int(wish.get("due_in_days") or days // 2)))
    except (TypeError, ValueError):
        due = days // 2
    plan = {"milestones": [dict(m, due_in_days=due) for m in rows("milestones", 2)],
            "steps": rows("steps", 4), "habits": [dict(h, freq="daily") for h in rows("habits", 2)]}
    journey.apply_plan(store, w["id"], plan)
    return w


def seed_guest(store: Store) -> None:
    """A believable 15-day history so a first-time visitor sees every zone
    populated. Written through the same Store API as real use, with back-dated
    times, and the XP ledger is built by growth.award on those past rows so the
    per-day / per-source caps hold exactly like a real account."""
    t0 = now() - timedelta(days=14)
    seeded_at = now().isoformat(timespec="seconds")

    def day(d):   # 只要日期（计划日、里程碑日期可以在未来）
        return (t0 + timedelta(days=d)).date().isoformat()

    def md(d):
        x = t0 + timedelta(days=d)
        return f"{x.month}月{x.day}日"

    def at(d, h, m=0):
        # 「今天」的种子时间不能晚于现在，否则会排在用户真正发的消息后面
        dt = t0.replace(hour=h, minute=m, second=0) + timedelta(days=d)
        cap = now() - timedelta(minutes=5 + (24 - h) * 3)
        return min(dt, cap).isoformat(timespec="seconds")

    store.set_profile({
        "agent_name": "小光", "agent_avatar_id": LOOK_DEFAULT, "agent_hue": "", "theme": "forest", "nickname": "林夏",
        "intent_primary": "自信与表达", "intent_why": "交换项目时想敢开口说英语", "schedule_hint": "夜猫",
        "traits": ["敏感", "拖延但爆发", "需要被提醒"], "mbti_hint": "INFJ", "boundaries": ["别鸡血催促"],
        "care_style": "analyze", "onboarded": True, "proactive": "normal", "xp": 0, "persona": "gentle",
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
        ("good", "终于把录音听完了，没那么难听", 6),
        ("good", "Mia 说我口音比上次自然", 8), ("rest", "今天偷个懒：就是想歇歇", 9),
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
    for sid, d in [("meditation", 4), ("gratitude", 8), ("seven_steps_lite", 11)]:
        rid = f"sc_seed_{sid}"
        store.c.execute(
            "INSERT OR REPLACE INTO scene_run(id, scene, step, answers, status, created_at) VALUES(?,?,?,?,?,?)",
            (rid, sid, 9, "[]", "done", at(d, 20)))

    # 经验账本：按日期逐条记，走 award 的同一套限额与去重；金币最后按老账号的规则一次换算（town.seed_demo）
    def backdated_award(source, ref, d, hour=21):
        out = growth.award(store, source, ref=ref, note="", coins=False)
        if out.get("ok") and out.get("amount"):
            row = out["row"]
            store.c.execute("UPDATE xp SET created_at=?, day=? WHERE id=?", (at(d, hour), at(d, hour)[:10], row["id"]))
            # award() already bumped profile xp; recompute at the end instead
        return out

    for d, sid, title in done_rows:
        backdated_award("action", "step:" + sid, d, 22)
    for d, rid in good_rows:
        backdated_award("good", "rec:" + rid, d, 20)
    for sid, d in [("meditation", 4), ("gratitude", 8), ("seven_steps_lite", 11)]:
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
                          ("scene", "做完「聊聊现在的你」", 11)]:
        store.log(kind, text)
        store.c.execute("UPDATE activity SET at=? WHERE id=(SELECT id FROM activity ORDER BY rowid DESC LIMIT 1)", (at(d, 22),))
    store.push_inbox("明天那一步不急。今天想说的话，我都在。", "checkin")
    store.c.execute("UPDATE inbox SET created_at=?", (at(13, 9),))

    # 过去几晚的日终整理（与 core/digest.py 写入的结构一致）：首页那句话 + 小光笔记本里的一页
    none = {"added": 0, "updated": 0, "deleted": 0, "guesses": 0, "user_lines": 2}
    digests = [
        (5, "听自己的录音会有点尴尬，可你和 Mia 聊得比想象中顺。", ["和 Mia 聊了十分钟"], none, [],
         {"title": "录音里的陌生声音", "quote": "录音里的我：这是谁？？我平时就是这个声音吗",
          "body": "你第一次听自己的英文录音，问这是谁。可就在同一天，你和 Mia 用英语聊了十分钟，比你想的顺。别人耳朵里的你，好像比你自己听到的要好一点。"}),
        (8, "Mia 说你口音自然了，这句我也替你记着。", ["Mia 说口音更自然"], none, [],
         {"title": "Mia 说的那一句", "quote": "Mia 说我口音比上次自然",
          "body": "周末和 Mia 练了二十分钟，她说你的口音比上次自然。你在旁边写：被看见的感觉很好。好像有人认真在听的时候，你就会说得更好一点。"}),
        (10, "你是先开口的那个人了，这一天我想多记一会儿。", ["小组里第一次主动提问"],
         {**none, "added": 1}, [{"op": "ADD", "text": "在小组讨论里常常想好了却没说出口", "kind": "event", "status": "active"}],
         {"title": "先开口的那个人", "quote": "有点紧张，但说完发现大家都在认真听",
          "body": "小组讨论里，你第一次主动提了问题。一周前你还说，常常想好了却没说出口。你说当时有点紧张，可说完发现大家都在认真听。我把这一页折了个角。"}),
        (11, "你说中断的时候更想被陪着找原因，我记下了，下次就这样陪你。", ["选了「一起找原因」", "把第一句话练顺"],
         {"added": 1, "updated": 0, "deleted": 0, "guesses": 0, "user_lines": 6},
         [{"op": "ADD", "text": "中断时更希望被陪着找原因，不想被催", "kind": "preference", "status": "active"}],
         {"title": "凌晨一点的猫咪视频", "quote": "我：今晚一定早睡。也是我：凌晨一点在看猫咪视频",
          "body": "你说今晚一定早睡，结果凌晨一点还在看猫。白天你在小组里提了问题，晚上又告诉我，中断的时候想被陪着找原因，不想被催。看猫那一会儿，大概也是你给自己留的一口气。"}),
        (12, "面试官那一笑，我猜你心里松了一大口气吧。", ["面试官笑了一下", "对着镜子练开场"],
         {"added": 0, "updated": 1, "deleted": 0, "guesses": 0, "user_lines": 4},
         [{"op": "UPDATE", "text": "跟熟悉的朋友一起练口语时不紧张，面对陌生人也在慢慢放松",
           "old": "跟熟悉的朋友一起练口语时不紧张", "kind": "insight", "status": ""}],
         {"title": "镜子里的开场白", "quote": "面试官笑了一下，我没那么紧张了",
          "body": "面试前，你对着镜子把第一句话练了一遍。面试官笑了一下，你记下的是「没那么紧张了」，没写「我表现得很好」。你总把做到的说小一点，那我就替你多记一笔。"}),
        (13, "你居然自然醒了，还顺手读完一篇英文文稿，昨天状态真不错。", ["自然醒", "读完一篇文稿"],
         {"added": 0, "updated": 0, "deleted": 0, "guesses": 1, "user_lines": 3},
         [{"op": "ADD", "text": "可能其实会说，更怕的是说错", "kind": "insight", "status": "guess"}],
         {"title": "自然醒的早上", "quote": "早上居然自然醒了",
          "body": "你一直说早上很难进入状态，今天却自然醒了，还顺手读完一篇英文文稿。两周前跟读播客，你读了三分钟，声音很小。现在读完一整篇，你都没觉得这值得说一说。"}),
    ]
    for d, summary, hl, stats, ops, _ in digests:
        store.save_digest(at(d, 3)[:10], summary, hl, stats, ops, True)
        store.c.execute("UPDATE digest SET created_at=? WHERE day=?", (at(d + 1, 3, 10), at(d, 3)[:10]))
    store.set_profile({"last_digest_day": at(13, 3)[:10]})
    # 小光的笔记本：一周一页（core/weekly.py）。后一周如果就是这一周，存成草稿
    from . import weekly
    wa, wb = weekly.week_key(parse_iso(at(4, 12))), weekly.week_key(parse_iso(at(11, 12)))
    store.save_week(wa, {"title": "录音里的陌生声音", "quotes": ["说完心跳很快，但没有人笑", "原来我可以"],
                         "bits": ["少糖的奶茶", "课上开口一次", "和 Mia 聊了十分钟", "30 秒自我介绍"],
                         "body": "这周你第一次在课上说了自己的想法，声音在抖，但没有人笑。后来你录了自我介绍，听了三遍才敢删掉重录。"
                                 "可也是这周，你和 Mia 用英语聊了十分钟，比想的顺。别人耳朵里的你，好像比你自己听到的要好一点。"}, True)
    store.save_week(wb, {"title": "先开口的那个人", "quotes": ["有点紧张，但说完发现大家都在认真听", "面试官笑了一下，我没那么紧张了"],
                         "bits": ["Mia 的那句话", "楼下的猫让摸了", "读完一篇英文文稿", "自然醒的早上"],
                         "body": "这周 Mia 说你口音比上次自然，你在旁边写：被看见的感觉很好。几天后的小组讨论里，你第一次主动提问。"
                                 "面试前你对着镜子练开场，面试官笑了一下，你只写了「没那么紧张了」。你总把做到的说小一点，那我就替你多记一笔。"},
                    wb != weekly.week_key())
    store.set_profile({"last_week_page": wb if wb != weekly.week_key() else wa})
    store.set_profile({"portrait": {"text": "一个总是想好了才开口的人，这两周开始先开口了。", "by": "digest", "updated_at": at(13, 3)}})
    # 小光的发现：小光翻笔记本时注意到的（core/finds.py 写的结构）
    store.set_profile({"finds_at": at(13, 4), "finds": [
        {"id": "fd_seed_1", "at": at(13, 4), "text": "你说得最顺的几次，身边都有一个认真在听的人。",
         "evidence": [f"{md(5)} 给室友讲了一个英文词", f"{md(8)} Mia 说你口音比上次自然", f"{md(10)} 小组里提问，大家都在认真听"]},
        {"id": "fd_seed_2", "at": at(13, 4), "text": "晚上九点以后的你，比白天勇敢一点。",
         "evidence": [f"{md(3)} 晚上九点，你记下课上被老师夸", f"{md(10)} 夜里十点，你跟小光说主动提问的事", "你说过晚上 9–11 点最有精神"]},
        {"id": "fd_seed_3", "at": at(10, 4), "text": "你很少说「我做到了」。面试那天，你写的是「没那么紧张了」。",
         "evidence": [f"{md(6)} 录完自我介绍，你写「没那么难听」", f"{md(12)} 面试后你写「没那么紧张了」"]},
        {"id": "fd_seed_4", "at": at(7, 4), "text": "让你开心的事，常常是有人记得你：少糖的奶茶，Mia 的那句话。",
         "evidence": [f"{md(0)} 室友带奶茶，还记得你要少糖", f"{md(8)} Mia 说你口音比上次自然"]},
    ]})
    store.bump("report_open", 0)

    # 两张成长轨迹看板：主线「自信与表达」，加一张「心灵平静」（文档里的首个主题示例）
    def seed_wish(title, cat, now_t, vision_t, start_d, items, span=60):
        w = journey.add_wish(store, title, cat, now_t, vision_t, started=at(start_d, 9)[:10],
                             target_day=day(start_d + span))
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

    # 路径：习惯（带打卡历史，今天留给访客自己打）+ 里程碑。历史打卡不补经验
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
        m = journey.add_milestone(store, w["id"], title, day(due_d))
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

    # 建示例数据时顺手写下的「加了习惯 / 定了里程碑」之类的动态不是用户做的，清掉
    store.c.execute("DELETE FROM activity WHERE kind IN ('plan','journey','task') AND at >= ?", (seeded_at,))

    # 示例账号的小镇：经验换成金币、摆上几样东西；已经到的等级算作「看过」，免得一打开就弹庆祝
    from . import town
    town.seed_demo(store)
