"""官方展示账号：一个用了快两个月的人（阿周，27 岁，上海做产品运营）。

给组里、给合作方演示用：每个页面都有真实感的内容，数字前后对得上。
  - 三个愿望：早点睡、重新跑起来、带妈妈去大理（旅行基金），每个有站点、习惯、做过的和接下来的小步；
  - 小步有的安排在今天、明天、周六，有的还没安排；日历上过去的日子只有真做过的事；
  - 瞬间有挂在愿望下的，也有生活里随手记的；
  - 小光记得的事分在六类里，夜里整理有两页笔记，小光的发现有三条，对话是最近几天的；
  - 经验和金币逐条记账（和真实规则一样：完成小步 +10 经验 +10 金币……），到 Lv15 左右；
    小镇是一块 9×9 的地，房子、路、树、店铺是按解锁的时间一点点买下来的，账本里都有。

用法（服务器上）：python make_showcase.py 用户名 密码   —— 已有这个用户名就清空重建。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import base64
from pathlib import Path

from . import growth, journey, photos, town, weekly
from .onboarding import LOOK_DEFAULT
from .util import dumps, now, parse_iso

SPAN = 58          # 账号建了多少天（第 0 天到今天）
# 带照片的瞬间用的真照片：showcase_photos/<名字>.jpg（大图）+ <名字>_s.jpg（小图），由 tools/prep_showcase_photos.py 从原图压出来。
# 没有这个文件，那条瞬间就只有文字（不会随便配一张图）。
PHOTO_DIR = Path(__file__).resolve().parent.parent / "showcase_photos"


def _photo(st, name: str) -> str:
    full, small = PHOTO_DIR / f"{name}.jpg", PHOTO_DIR / f"{name}_s.jpg"
    if not (full.is_file() and small.is_file()):
        return ""
    b = lambda f: base64.b64encode(f.read_bytes()).decode()
    return photos.save(st, b(full), b(small))


def seed_showcase(st) -> dict:
    today = now()
    t0 = today - timedelta(days=SPAN)

    def day(d):
        return (t0 + timedelta(days=d)).date().isoformat()

    def md(d):
        x = t0 + timedelta(days=d)
        return f"{x.month}月{x.day}日"

    def at(d, h, m=0):
        dt = t0.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=d)
        if d >= SPAN:   # 今天的不能晚于现在
            dt = min(dt, today - timedelta(minutes=30 + (24 - h)))
        return dt.isoformat(timespec="seconds")

    def back(table, col, rid, when):
        st.c.execute(f"UPDATE {table} SET {col}=? WHERE id=?", (when, rid))

    # ---------------------------------------------------------------- 画像 ----
    st.set_profile({
        "agent_name": "小光", "agent_avatar_id": LOOK_DEFAULT, "agent_hue": "", "theme": "paper", "nickname": "阿周",
        "intent_primary": "把睡眠找回来", "intent_why": "不想再靠咖啡撑一整天", "schedule_hint": "夜猫",
        "traits": ["行动派", "想得多"], "mbti_hint": "", "boundaries": ["别鸡血催促"],
        "care_style": "analyze", "chat_style": "帮你想想具体可以怎么做", "energy_time": "晚上",
        "onboarded": True, "proactive": "normal", "persona": "gentle", "town_name": "晚风镇",
        "created_at": at(0, 21), "last_chat_at": at(SPAN - 1, 22), "last_proactive_at": at(SPAN - 1, 12),
    })

    # ---------------------------------------------------------------- 愿望 ----
    def wish(title, cat, now_t, vision, start, span):
        w = journey.add_wish(st, title, cat, now_t, vision, started=day(start), target_day=day(start + span))
        back("wish", "created_at", w["id"], at(start, 21))
        return w

    sleep = wish("早点睡，睡得踏实", "calm", "每天刷手机到一两点，第二天靠两杯咖啡撑着", "十二点前放下手机，早上不用闹钟也能醒", 0, 90)
    run = wish("重新跑起来", "body", "上一次跑步是去年秋天，爬五楼都喘", "每周跑三次，明年春天跑一次 10 公里", 12, 120)
    trip = wish("带妈妈去一趟大理", "freedom", "工资一到手就花掉一半，月底总不够", "明年三月带妈妈去大理住一周，钱是自己攒的", 25, 150)
    W = {"sleep": sleep, "run": run, "trip": trip}

    # 站点：(愿望, 名字, 计划日, 到达日)
    ms_rows = []
    for k, title, due, done_d in [
        ("sleep", "一周有 4 天 12 点前睡", 21, 20), ("sleep", "连续两周 12 点前睡", 66, None), ("sleep", "不靠咖啡过完一个工作日", 82, None),
        ("run", "连续跑完 3 公里", 36, 34), ("run", "连续跑完 5 公里", 70, None), ("run", "报名一场 10 公里", 112, None),
        ("trip", "旅行基金存到 3000", 52, 50), ("trip", "存到 6000", 100, None), ("trip", "订好去大理的机票", 160, None),
    ]:
        m = journey.add_milestone(st, W[k]["id"], title, day(due))
        st.c.execute("UPDATE milestone SET created_at=?, status=?, done_at=? WHERE id=?",
                     (at(W[k] is sleep and 1 or (12 if k == "run" else 26), 21), "done" if done_d else "todo",
                      at(done_d, 22) if done_d else "", m["id"]))
        if done_d:
            ms_rows.append((done_d, m["id"], title))

    # 习惯：打卡的日子（第几天）
    def habit(k, title, freq, per, days, created):
        h = journey.add_habit(st, W[k]["id"], title, freq, per)
        back("habit", "created_at", h["id"], at(created, 21))
        for d in days:
            st.c.execute("INSERT OR IGNORE INTO habit_log(id, habit_id, day, created_at) VALUES(?,?,?,?)",
                         (f"hl_{h['id']}_{d}", h["id"], day(d), at(d, 23 if k == "sleep" else 21)))
        return h, [(d, h["id"], title) for d in days]

    rest_days = {8, 29, 43}
    phone_days = [d for d in range(2, SPAN) if d not in rest_days and d not in (5, 11, 16, 23, 30, 31, 32, 38, 53, 54, 55)]
    _, hl_phone = habit("sleep", "11 点半把手机放客厅充电", "daily", 7, phone_days, 1)
    stretch_days = [d for d in range(10, SPAN) if d % 7 in (0, 2, 4, 5) and d not in rest_days and d not in (53, 54)]
    _, hl_stretch = habit("sleep", "睡前拉伸 10 分钟", "weekly", 4, stretch_days, 9)
    run_days = [14, 15, 17, 20, 22, 24, 27, 30, 32, 34, 36, 39, 41, 45, 46, 48, 50, 52, 56]
    _, hl_run = habit("run", "夜跑 30 分钟", "weekly", 3, run_days, 13)
    book_days = [d for d in range(27, SPAN) if (d - 27) % 7 == 0]
    _, hl_book = habit("trip", "周日晚上记一次账", "weekly", 1, book_days, 26)
    habit_rows = hl_phone + hl_stretch + hl_run + hl_book

    # ---------------------------------------------------------------- 小步 ----
    sat = next(SPAN + i for i in range(1, 8) if (t0 + timedelta(days=SPAN + i)).weekday() == 5)
    step_rows = []
    for k, title, why, created, done_d, plan in [
        ("sleep", "把充电器从床头挪到客厅", "手机不在手边，就不会顺手拿起来", 0, 1, None),
        ("sleep", "下午三点后不喝咖啡，试三天", "看看是不是咖啡让晚上睡不着", 3, 4, None),
        ("sleep", "卸载最常刷的那个短视频 App", "一刷就是一小时", 8, 9, None),
        ("sleep", "买一个机械闹钟", "这样就不用拿手机当闹钟了", 13, 15, None),
        ("sleep", "周末也在 9 点前起床", "周末睡太晚，周日晚上就睡不着", 26, 28, None),
        ("sleep", "睡前把第二天要穿的衣服挑好", "早上少一件要想的事", 46, 47, None),
        ("sleep", "把刷手机挪到洗澡前，定 20 分钟", "时间还是自己的，只是换个位置", 55, 56, None),
        ("sleep", "睡前那十分钟换成读纸质书", "刷手机之外，给睡前找件别的事", 55, None, SPAN),
        ("sleep", "把卧室窗帘换成遮光的", "早上五点多就被晒醒", 50, None, sat),
        ("run", "翻出旧跑鞋，看看还能不能穿", "先别花钱", 12, 12, None),
        ("run", "下班后绕小区快走 20 分钟", "先让腿动起来", 12, 13, None),
        ("run", "第一次跑走结合 2 公里", "跑一分钟走一分钟", 14, 15, None),
        ("run", "买一双新跑鞋", "旧的那双鞋底磨平了", 18, 22, None),
        ("run", "在操场连续跑满 8 圈", "就是 3 公里", 30, 34, None),
        ("run", "找一个周六早上的跑团", "一个人跑容易偷懒", 40, 45, None),
        ("run", "周六跟跑团跑一次 5 公里", "上次跑了 4 公里", 56, None, sat),
        ("run", "找一个跑后拉伸的视频存好", "上次跑完小腿酸了两天", 52, None, None),
        ("trip", "把这三个月的账单导出来看一遍", "先知道钱花去哪了", 25, 25, None),
        ("trip", "开一个单独的储蓄账户", "存进去就不动", 25, 26, None),
        ("trip", "取消两个没在用的会员", "每个月自动扣的", 26, 27, None),
        ("trip", "问妈妈三月哪周有空", "先定时间", 38, 40, None),
        ("trip", "查一下大理三月的天气和民宿价格", "心里有个数", 54, None, SPAN + 1),
        ("trip", "把十月的账单分一下类", "看看外卖到底花了多少", 47, 48, None),
        ("trip", "把外卖预算定成每周 200", "外卖是最大的一笔", 49, None, None),
    ]:
        s = st.add_step(title, why, W[k]["title"], due_day=day(created), wish_id=W[k]["id"],
                        scheduled_day=day(plan) if plan is not None else "")
        back("step", "created_at", s["id"], at(created, 21))
        if done_d is not None:
            st.c.execute("UPDATE step SET status='done', done_at=?, scheduled_day='' WHERE id=?", (at(done_d, 21, 30), s["id"]))
            step_rows.append((done_d, s["id"], title))

    # ---------------------------------------------------------------- 瞬间 ----
    mo_rows = []
    for k, d, h, text, feeling, mood, pic in [
        ("", 21, 15, "周末去了趟香港，在商场里抬头看了好久这个天花板。", "像掉进一个大海螺里", "开心", "hk"),
        ("run", 22, 11, "第二天去西贡徒步，走了三个多小时，翻过山就看到这片海。", "腿酸，但值了", "开心", "coast"),
        ("trip", 48, 20, "第一次自己做沙茶面，虾、鱿鱼、鱼丸都放了，比外卖好吃。", "一顿省下四十块", "骄傲", "noodle"),
        ("", 53, 23, "断了好一阵的扇贝又打开了，累计 1546 天，连续打卡从 1 重新开始。", "从 1 开始也没关系", "", "words"),
        ("", 35, 21, "妈妈发来老家院子里的柿子，说等我回去摘。", "", "开心", ""),
        ("sleep", 41, 7, "早上六点四十醒了，比闹钟早二十分钟。", "", "平静", ""),
        ("run", 50, 9, "跑团的阿姨说我步子比第一次稳多了。", "", "开心", ""),
    ] + [(*x, "") for x in [
        ("sleep", 3, 0, "十二点零五分就躺下了，比昨天早了一个小时。", "有点不习惯，脑子还在转", ""),
        ("sleep", 9, 23, "删掉短视频以后，睡前翻了二十页书。", "居然困了", "平静"),
        ("sleep", 20, 22, "这周有四天是十二点前睡的。", "早上起床没那么难了", "开心"),
        ("sleep", 31, 23, "加班到十点，回家还是按时把手机放客厅了。", "", "累"),
        ("sleep", 47, 8, "周六没定闹钟，八点自己醒了。", "好久没有这种感觉", "平静"),
        ("run", 15, 21, "跑走结合两公里，跑一分钟就喘，但走完了。", "腿软，心情还行", ""),
        ("run", 22, 20, "新跑鞋到了，在家穿着走了三圈。", "", "开心"),
        ("run", 34, 21, "第一次连续跑完三公里，停下来的时候想喊一声。", "原来我能跑这么久", "骄傲"),
        ("run", 45, 9, "跟跑团跑了第一次，有个六十多岁的阿姨跑得比我快多了。", "被超了也挺开心", "开心"),
        ("run", 54, 21, "下雨没跑，在家跟着视频拉伸了二十分钟。", "", ""),
        ("trip", 27, 22, "取消了两个会员，一个月省 58 块。", "小钱也是钱", ""),
        ("trip", 40, 21, "妈妈说三月中旬都行，还问要不要她出一半。", "我说不用，这次我请", "感动"),
        ("trip", 50, 22, "旅行基金到 3000 了。", "离大理又近了一点", "开心"),
        ("", 6, 8, "楼下面包店的老板多送了我一个可颂。", "", "开心"),
        ("", 18, 15, "同事帮我带了伞，下午果然下雨了。", "", ""),
        ("", 38, 10, "阳台的绿萝救活了，冒出两片新叶子。", "", "平静"),
        ("", 52, 22, "和大学室友小雨视频了一个小时，她明年要结婚了。", "替她高兴，也有点恍惚", ""),
        ("", 57, 19, "下班路上的晚霞是粉色的，停下来拍了一张。", "", "开心"),
    ]]:
        m = journey.add_moment(st, W[k]["id"] if k else "", text, feeling, mood=mood, day=day(d))
        if pic:
            st.c.execute("UPDATE moment SET photo=? WHERE id=?", (_photo(st, pic), m["id"]))
        st.c.execute("UPDATE moment SET created_at=?, updated_at=? WHERE id=?", (at(d, h), at(d, h), m["id"]))
        mo_rows.append((d, m["id"]))

    for d, text in [(8, "今天偷个懒：连着加了三天班，歇一下"), (29, "今天偷个懒：就是不想动"), (43, "今天偷个懒：感冒了")]:
        r = st.add_record("rest", text, day=day(d))
        back("record", "created_at", r["id"], at(d, 20))

    # 做过的练习（点子里的）：只留结果，写进记忆的在下面
    prac = [("meditation", 7), ("gratitude", 19), ("gratitude", 33), ("relearn", 44), ("meditation", 51)]
    for i, (sid, d) in enumerate(prac):
        st.c.execute("INSERT OR REPLACE INTO scene_run(id, scene, step, answers, status, created_at) VALUES(?,?,?,?,?,?)",
                     (f"sc_show_{i}", sid, 9, "[]", "done", at(d, 22)))

    # ---------------------------------------------------------------- 记忆 ----
    for text, kind, src, status, d, cat in [
        ("27 岁，在上海一家互联网公司做产品运营，一个人住", "identity", "onboarding", "active", 0, "self"),
        ("想把睡眠找回来，不想再靠两杯咖啡撑一整天", "intent", "onboarding", "active", 0, "effort"),
        ("不喜欢被打鸡血，说话直接一点就好", "boundary", "onboarding", "active", 0, ""),
        ("下班后才有自己的时间，所以晚上总舍不得睡", "insight", "chat", "active", 2, "self"),
        ("手机放在床头就会一直刷，放客厅就好很多", "insight", "confirmed", "active", 6, "likes"),
        ("下午三点后喝咖啡，晚上会睡不着", "insight", "chat", "active", 5, "likes"),
        ("妈妈在老家，计划明年三月带她去大理住一周", "event", "chat", "active", 25, "people"),
        ("想自己攒钱请妈妈旅行，不想让她出钱", "preference", "chat", "active", 40, "people"),
        ("和别人一起跑比一个人跑更容易坚持", "insight", "confirmed", "active", 45, "likes"),
        ("周六早上跟一个跑团跑步，团里有位六十多岁的阿姨跑得很快", "event", "chat", "active", 45, "people"),
        ("大学室友小雨明年要结婚", "event", "chat", "active", 52, "people"),
        ("十月去香港玩了一个周末，在西贡徒步了三个多小时", "event", "chat", "active", 22, ""),
        ("用扇贝背单词，累计一千五百多天，中间断过", "identity", "chat", "active", 53, "likes"),
        ("会自己下厨，做过沙茶面", "preference", "chat", "active", 48, "likes"),
        ("小时候学过两年电子琴，看得懂谱", "identity", "chat", "active", 57, "self"),
        ("十一月开始学电吉他，琴是自己买的；工作日晚上能练二十分钟", "event", "chat", "active", 57, "effort"),
        ("十一月初连着加了三周班，那段时间睡得很差", "event", "chat", "active", 55, "self"),
        ("加班的日子回家只想刷手机，觉得一天都没有属于自己的时间", "insight", "chat", "active", 55, "self"),
        ("冥想后的感受：肩膀松下来了，想早点睡", "event", "scene:meditation", "active", 7, ""),
        ("感恩三件事：同事带的伞、面包店的可颂、按时下班的一天", "event", "scene:gratitude", "active", 19, ""),
        ("中断时希望一起找原因，不想被催", "preference", "scene:relearn", "active", 44, ""),
        ("可能不是自制力差，是白天太满了，晚上想补回一点自己的时间", "insight", "chat", "guess", 56, "self"),
    ]:
        m = st.add_memory(text, kind, src, status, cat=cat)
        st.c.execute("UPDATE memory SET created_at=?, updated_at=? WHERE id=?", (at(d, 22), at(d, 22), m["id"]))

    # ---------------------------------------------------------------- 对话（最近几天） ----
    convo = [
        (45, 10, 5, "user", "今天跟跑团跑了，4 公里，中间停了一次"),
        (45, 10, 6, "assistant", "4 公里，比上次多跑了一公里。停一次没关系，一个月前你还在跑一分钟走一分钟。跑团感觉怎么样？"),
        (45, 10, 8, "user", "人挺好的，有个阿姨六十多了，跑得比我快"),
        (45, 10, 9, "assistant", "被六十多岁的阿姨超过，听起来你还挺开心的。下周六还去吗？"),
        (45, 10, 10, "user", "去"),
        (45, 10, 11, "assistant", "好，周六早上我提醒你。"),
        (55, 22, 40, "user", "这周又加班，三天都是一点多才睡"),
        (55, 22, 41, "assistant", "加班那几天，手机还放客厅吗？"),
        (55, 22, 43, "user", "没有，回家就想刷一会儿，感觉一天都没有自己的时间"),
        (55, 22, 44, "assistant", "累了一天，想留点时间给自己，很正常。要不把刷手机挪到洗澡之前，定个二十分钟，洗完澡就不碰了？这样时间还是你的，只是换了个位置。"),
        (55, 22, 46, "user", "可以试试"),
        (55, 22, 47, "assistant", "那今晚就试。睡前那十分钟，我帮你安排成读纸质书了，书桌上那本还没读完吧？"),
        (55, 22, 48, "user", "还没，读了一半"),
    ]
    for d, h, mi, role, text in convo:
        st.add_msg(role, text, at=at(d, h, mi))

    # ---------------------------------------------------------------- 最近一次：和小光一起把「学电吉他」排出来 ----
    guitar = wish("学会弹电吉他", "freedom", "小时候学过两年电子琴，吉他一次都没碰过", "能抱着琴弹唱一首完整的歌", SPAN - 1, 90)
    v1 = {"milestones": [{"title": "能弹下来《晴天》的前奏", "due_in_days": 30}, {"title": "完整弹唱一首歌", "due_in_days": 90}],
          "habits": [{"title": "每天练琴 20 分钟", "freq": "daily", "per_week": 7}],
          "steps": [{"title": "跟着视频把琴调准音", "why": "琴到手的第一件事"},
                    {"title": "认识六根弦和前三品", "why": "先知道手指往哪按"},
                    {"title": "学会 C 和 G 两个和弦", "why": "《晴天》前奏用得上"}]}
    v2 = {**v1, "habits": [{"title": "下班后练琴 20 分钟", "freq": "weekly", "per_week": 4}]}

    def card(plan, state, why):
        return {"type": "ask", "ask": "plan", "icon": "flag", "color": "var(--c-orange)",
                "question": "给「学会弹电吉他」的一套安排，勾掉不想要的", "plan": plan, "why": why,
                "wish_id": guitar["id"], "wish_title": guitar["title"], "state": state}
    new_wish = {"type": "slip", "icon": "flag", "color": "var(--c-orange)", "verb": "新愿望", "new": "学会弹电吉他", "old": "", "go": "plan"}
    for mi, role, text, acts in [
        (2, "user", "帮我安排一下怎么新学电吉他", None),
        (3, "assistant", "好呀。先问三件事：以前碰过乐器吗？琴买了没有？一周大概能练几次，每次多久？", None),
        (6, "user", "小时候学过两年电子琴。琴昨天下单了，明天到。工作日晚上大概能弹二十分钟，周末可以多一点", None),
        (7, "assistant", "学过电子琴，看谱和节奏就不用从零开始了。我先把它建成一个愿望，再按你的时间拆一版。\n\n"
                         "第一个月先把手指练出来，目标是弹下来《晴天》的前奏。三个小步在琴到的头两天就能做完。",
         [new_wish, card(v1, "replaced", "第一个月先练手指")]),
        (10, "user", "每天练有点难，加班的时候肯定做不到", None),
        (11, "assistant", "那就一周四次，加班的日子不练也不算断。其他的不变，你再看看。", [card(v2, "added", "一周四次，加班的日子跳过")]),
        (13, "user", "可以，就这样", None),
        (14, "assistant", "加进去了：两个站点，一个月弹下来《晴天》的前奏，三个月弹唱一首完整的歌；下班后练琴，一周四次；还有三个小步。\n\n明天琴到了先调音，那一步排在明天。C 和 G 两个和弦放在周四，周六上午跑完步，下午可以多弹一会儿。", None),
    ]:
        st.add_msg(role, text, {"acts": acts} if acts else None, at=at(SPAN - 1, 20, mi))
    for title, due in [("能弹下来《晴天》的前奏", 30), ("完整弹唱一首歌", 90)]:
        m = journey.add_milestone(st, guitar["id"], title, day(SPAN - 1 + due))
        back("milestone", "created_at", m["id"], at(SPAN - 1, 20, 13))
    h = journey.add_habit(st, guitar["id"], "下班后练琴 20 分钟", "weekly", 4)
    back("habit", "created_at", h["id"], at(SPAN - 1, 20, 13))
    for title, why, plan in [("跟着视频把琴调准音", "琴到手的第一件事", SPAN), ("认识六根弦和前三品", "先知道手指往哪按", None),
                             ("学会 C 和 G 两个和弦", "《晴天》前奏用得上", SPAN + 2)]:
        s_ = st.add_step(title, why, guitar["title"], due_day=day(SPAN - 1), wish_id=guitar["id"],
                         scheduled_day=day(plan) if plan is not None else "")
        back("step", "created_at", s_["id"], at(SPAN - 1, 20, 13))
    st.add_msg("user", "琴到了！比想象中重", at=at(SPAN, 12, 20))
    st.add_msg("assistant", "电吉他是会沉一点，背带调短些会舒服。今天那一步就是调音，晚上回家先调准，弹一下空弦听听。", at=at(SPAN, 12, 21))
    st.push_inbox("周六的 5 公里不用一口气跑完，跑不动就走一段。", "checkin")
    st.c.execute("UPDATE inbox SET created_at=?, seen=1", (at(SPAN - 1, 12),))

    # ---------------------------------------------------------------- 夜里整理、笔记本、发现 ----
    none = {"added": 0, "updated": 0, "deleted": 0, "guesses": 0, "user_lines": 3}
    for d, summary, hl in [
        (45, "被六十多岁的阿姨超过，你还挺开心的。", ["跟跑团跑了 4 公里"]),
        (52, "小雨要结婚了，你说替她高兴，也有点恍惚。", ["和小雨视频了一个小时"]),
        (55, "加班的三天都一点多才睡，你说一天都没有自己的时间。", ["想把刷手机挪到洗澡前"]),
        (57, "你想学电吉他，我们一起排了第一个月，琴明天到。", ["开始学电吉他", "下班路上的粉色晚霞"]),
    ]:
        st.save_digest(day(d), summary, hl, none, [], True)
        st.c.execute("UPDATE digest SET created_at=? WHERE day=?", (at(d + 1, 3, 10) if d + 1 < SPAN else at(SPAN, 3, 10), day(d)))
    st.set_profile({"last_digest_day": day(SPAN - 1)})
    pages = [
        (4, "手机睡在客厅的第一周", ["有点不习惯，脑子还在转"], ["充电器挪到客厅", "三点后不喝咖啡", "面包店的可颂", "第一次冥想"],
         "这周你把充电器从床头挪到了客厅。第三天十二点零五分就躺下了，比前一天早了一个小时，你说有点不习惯，脑子还在转。"
         "三点以后不喝咖啡试了三天，你自己发现晚上好睡一些。小事，但是你自己试出来的。"),
        (11, "删掉那个 App 以后", ["居然困了"], ["加班后偷了一天懒", "翻了二十页书", "翻出旧跑鞋"],
         "连着加了三天班，你给自己放了一天假。第二天把最常刷的短视频卸载了，睡前翻了二十页书，写下「居然困了」。"
         "周末你又开了一个新愿望：重新跑起来。第一天只是把旧跑鞋翻出来，看看还能不能穿。"),
        (18, "一周四天", ["腿软，心情还行", "早上起床没那么难了"], ["跑一分钟走一分钟", "机械闹钟", "同事带的伞", "去香港"],
         "第一次跑走结合两公里，跑一分钟就喘，你说腿软，心情还行。买了机械闹钟，手机终于不用进卧室了。"
         "这周有四天是十二点前睡的，第一个站点到了。周末你去了香港，在商场里抬头看了好久那个天花板。"),
        (25, "从山那边回来", ["腿酸，但值了", "小钱也是钱"], ["西贡的海", "新跑鞋", "两个会员取消了"],
         "在西贡走了三个多小时，翻过山看到那片海，你说腿酸，但值了。回来以后你开了第三个愿望：明年三月带妈妈去大理。"
         "第一件事是把三个月的账单看一遍，然后取消了两个没在用的会员，一个月省 58 块。"),
        (32, "原来我能跑这么久", ["原来我能跑这么久"], ["加班也把手机放客厅", "操场 8 圈", "老家的柿子"],
         "加班到十点那天，你回家还是把手机放到了客厅。周四在操场连续跑了 8 圈，三公里，停下来的时候想喊一声。"
         "周末妈妈发来院子里的柿子，说等你回去摘。"),
        (39, "这次我请", ["我说不用，这次我请"], ["绿萝冒了新叶", "妈妈说三月都行", "六点四十自己醒"],
         "你问妈妈三月哪周有空，她说中旬都行，还问要不要出一半。你说不用，这次你请。"
         "阳台的绿萝救活了，有一天早上你六点四十就醒了，比闹钟早二十分钟。"),
        (46, "被阿姨超过的那个早上", ["被超了也挺开心", "一顿省下四十块"], ["感冒歇了一天", "跑团的 4 公里", "周六八点自己醒", "沙茶面"],
         "这周你第一次跟跑团跑，4 公里中间停了一次，被一个六十多岁的阿姨超过去，你说挺开心的。"
         "一个人跑总想偷懒，有人在前面，你就跟上了。周六没定闹钟，八点自己醒了；周日晚上第一次自己做了沙茶面，比外卖好吃。"),
        (53, "一天里属于自己的时间", ["感觉一天都没有自己的时间", "从 1 开始也没关系"], ["旅行基金 3000", "小雨要结婚了", "扇贝又打卡了"],
         "旅行基金到了 3000。后半周又加了三天班，三天都一点多才睡，你说回家只想刷一会儿，不然一天都没有自己的时间。"
         "所以晚睡大概不是管不住自己，是白天太满了。断了好一阵的扇贝你又打开了，连续打卡从 1 开始，你说也没关系。"),
    ]
    keys = []
    for d, title, quotes, bits, body in pages:
        k = weekly.week_key(parse_iso(at(d, 12)))
        st.save_week(k, {"title": title, "quotes": quotes, "bits": bits, "body": body}, k != weekly.week_key())
        st.c.execute("UPDATE week_page SET created_at=? WHERE week=?", (at(d + 4, 3, 20) if d + 4 <= SPAN else at(SPAN, 3, 20), k))
        keys.append(k)
    st.set_profile({"last_week_page": keys[-1]})
    st.set_profile({"portrait": {"text": "白天很满，所以总想在夜里给自己多留一会儿的人。", "by": "digest", "updated_at": at(SPAN, 3)}})
    st.set_profile({"finds_at": at(SPAN - 2, 4), "finds": [
        {"id": "fd_show_1", "at": at(SPAN - 2, 4), "text": "你睡得早的那几周，都是跑步跑得多的几周。",
         "evidence": [f"{md(20)} 这周四天 12 点前睡", f"{md(34)} 第一次连续跑完三公里", f"{md(47)} 周六八点自己醒了"]},
        {"id": "fd_show_2", "at": at(SPAN - 2, 4), "text": "有人一起的时候，你更容易开始：跑团、妈妈、帮你带伞的同事。",
         "evidence": [f"{md(45)} 跟跑团跑了 4 公里", f"{md(40)} 问妈妈三月哪周有空", f"{md(18)} 同事帮你带了伞"]},
        {"id": "fd_show_3", "at": at(40, 4), "text": "你记下的开心事，好几件都是被人记得：面包店的可颂，同事的伞。",
         "evidence": [f"{md(6)} 老板多送了一个可颂", f"{md(18)} 同事帮你带了伞"]},
    ]})
    st.set_profile({"notebook": {"by": "digest", "day": day(SPAN - 1), "updated_at": at(SPAN, 3), "text": (
        "最近的生活：27 岁，在上海做产品运营，一个人住；十一月加班多，下班后才有自己的时间。\n"
        "在意的人：妈妈在老家，明年三月要带她去大理；大学室友小雨明年结婚；周六跑团里有位跑得很快的阿姨。\n"
        "正在努力的事：十二点前睡，手机放客厅充电；每周跑三次，已经能连续跑 3 公里；给大理攒旅行基金，到 3000 了；刚开始学电吉他，一周练四次。\n"
        "心情和状态：加班的日子容易晚睡，不是管不住，是想给自己留点时间；有人一起的时候更容易开始。\n"
        "相处时的偏好：中断时想一起找原因，不想被催；说话直接一点，不要打鸡血。\n"
        f"时间线：{md(20)} 第一次一周四天早睡；{md(34)} 连续跑完 3 公里；{md(45)} 第一次跟跑团；{md(50)} 旅行基金到 3000。")}})
    from . import cheer
    st.set_profile({"cheer": {"slot": cheer.slot(), "kind": "you", "label": "最近的你", "source": "", "at": at(SPAN, 8),
                              "text": "加班的那几天，你还是有两天把手机放到了客厅。"}})

    # 动态：只留几条 TA 自己做的大事（建数据时顺手写下的「开启旅程」那些清掉）
    st.c.execute("DELETE FROM activity")
    for kind, text, d in [("journey", "开启了一段旅程：早点睡，睡得踏实", 0), ("journey", "开启了一段旅程：重新跑起来", 12),
                          ("journey", "到达里程碑「一周有 4 天 12 点前睡」", 20), ("journey", "开启了一段旅程：带妈妈去一趟大理", 25),
                          ("journey", "到达里程碑「连续跑完 3 公里」", 34), ("scene", "做完「调整现有计划」", 44),
                          ("journey", "到达里程碑「旅行基金存到 3000」", 50)]:
        st.c.execute("INSERT INTO activity(id, kind, text, at) VALUES(lower(hex(randomblob(6))),?,?,?)", (kind, text, at(d, 22)))

    # ---------------------------------------------------------------- 经验和金币：逐条记账 ----
    xp_day: dict[int, dict] = {}

    def book(d, h, source, xp, ref, note, coins=0, ckind="", mi=0):
        used = xp_day.setdefault(d, {"all": 0})
        if source in growth.SOURCES:
            xp = max(0, min(xp, growth.SOURCE_CAP - used.get(source, 0), growth.DAILY_CAP - used["all"]))
            used[source] = used.get(source, 0) + xp
            used["all"] += xp
        when = at(d, h, mi)
        if xp:
            st.c.execute("INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
                         (day(d), source, xp, ref, note, when))
        if coins:
            st.c.execute("INSERT INTO coin(id, day, kind, amount, ref, note, created_at) VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
                         (day(d), ckind or source, coins, ref, note, when))

    book(1, 21, "action", 0, "first", "第一份建材", growth.FIRST_GIFT, "first", mi=31)
    for d in range(SPAN):
        if d not in (11, 23, 38):
            book(d, 21, "checkin", 8, "day:" + day(d), "今天来聊了")
    for d, sid, title in step_rows:
        book(d, 21, "action", 10, "step:" + sid, f"完成：{title}", 10, "action", 30)
    for d, hid, title in habit_rows:
        book(d, 23 if "手机" in title or "拉伸" in title else 21, "action", 10, f"habit:{hid}:{day(d)}", f"打卡：{title}", 8, "action", 5)
    for d, mid, title in ms_rows:
        book(d, 22, "action", 10, "ms:" + mid, f"到达：{title}", 30, "milestone")
    for d, mid in mo_rows:
        book(d, 22, "good", 6, "moment:" + mid, "留下一个瞬间", 5, "record", 10)
    for i, (sid, d) in enumerate(prac):
        book(d, 22, "practice", 12, f"scene:sc_show_{i}", "完成练习", 10, "practice", 20)
    for d in range(2, SPAN):
        if d in rest_days or d in (11, 23, 38):
            continue
        book(d, 22, "daily", 8, f"daily:{day(d)}:a", "每日任务：完成 1 个小步或打一次卡", 10, "daily", 40)
        book(d, 22, "daily", 5, f"daily:{day(d)}:b", "每日任务：留下一个瞬间" if d % 2 else "每日任务：做 1 次练习", 8, "daily", 41)
        if d % 3 == 0:
            book(d, 22, "daily", 10, f"daily:{day(d)}:all", "每日任务四件都做到了", 20, "daily", 42)

    # 每天到了多少经验 → 哪天升到几级（买东西的日子不能早于解锁）
    lv_day: dict[int, int] = {}
    tot = 0
    for d in range(SPAN + 1):
        tot += int(st.c.execute("SELECT COALESCE(SUM(amount),0) FROM xp WHERE day=?", (day(d),)).fetchone()[0])
        lv = growth.level_of(tot, 1)["lv"]
        lv_day.setdefault(lv, d)
        for L in range(1, lv):
            lv_day.setdefault(L, d)
    st.set_profile({"xp": tot})

    # ---------------------------------------------------------------- 小镇 ----
    # 不走 town.ensure：那是给老账号换金币、记保底等级用的；这里直接标成新版小镇，整块地自己摆
    st.set_profile({"town_v": town.TOWN_V, "level_floor": 1})
    st.c.execute("DELETE FROM town_item")
    cat = {c["id"]: c for c in town.catalog()}
    gifts = {"cottage", "sign", "lamp", "road"}

    def put(kind, x, y, rot=0, gift=False, note="", d=None, ref=""):
        c = cat.get(kind) or town.meta(kind)
        d = d if d is not None else max(lv_day.get(c["lv"], 0) + 1, 1)
        d = min(d, SPAN)
        story = None
        if not gift:
            last = max([r for r in step_rows + ms_rows if r[0] <= d] or [(0, "", "")], key=lambda r: r[0])
            story = {"text": f"完成了「{last[2]}」" if last[2] else "", "day": day(last[0])}
        iid = journey.new_id("t")
        st.c.execute("INSERT INTO town_item(id, kind, x, y, placed, note, story, source, price, ref, created_at, placed_at, rot) "
                     "VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?)",
                     (iid, kind, x, y, note, dumps(story) if story else "", "gift" if gift else "shop",
                      0 if gift else c["price"], ref or ("" if gift else f"buy:show{iid}"), at(d, 22, 50), at(d, 22, 50), rot))
        if not gift:
            st.c.execute("INSERT INTO coin(id, day, kind, amount, ref, note, created_at) VALUES(lower(hex(randomblob(6))),?,?,?,?,?,?)",
                         (day(d), "buy", -c["price"], f"buy:show{iid}", f"建造：{c['name']}", at(d, 22, 50)))

    # 一条东西向的主街（y=4）和一条往南的小路（x=4），十字路口；北边一排店铺，西南是小公园，东南是游乐的角落
    for x in range(9):
        put("road", x, 4, gift=x in (1, 2, 3), d=0 if x in (1, 2, 3) else None)
    for y in range(5, 9):
        put("road", 4, y)
    put("sign", 0, 5, gift=True, d=0)
    put("cottage", 2, 3, gift=True, d=0)
    put("lamp", 1, 5, gift=True, d=0)
    put("lamp", 3, 3, gift=True, d=0)
    # 北边一排：面朝主街
    put("house", 1, 3, d=lv_day.get(3, 10) + 1)
    put("bakery", 0, 3)
    put("cafe", 5, 3)
    put("library", 6, 3)
    put("flowershop", 7, 3)
    put("icecream", 8, 3, rot=1)
    put("greenhouse", 4, 2)
    put("windmill", 7, 1)
    put("tower", 1, 1)
    # 北边后排的树
    for k, x, y in [("pine", 0, 0), ("pine", 0, 1), ("tree", 2, 1), ("sakura", 3, 1), ("tree", 5, 1), ("pine", 8, 0),
                    ("bush", 3, 2), ("flowers", 5, 2), ("flowers", 2, 0), ("tree", 6, 0), ("bush", 8, 2)]:
        put(k, x, y)
    # 西南：小公园
    put("fountain", 2, 6)
    put("pond", 1, 7)
    put("bench", 3, 6, rot=1)
    put("sakura", 0, 6)
    put("sakura", 3, 8)
    put("tree", 0, 8)
    put("flowers", 2, 8)
    put("flowers", 1, 6)
    put("lamp", 3, 5)
    put("mailbox", 5, 5)
    # 东南：热气球、纪念碑、拱门
    put("balloon", 7, 7)
    put("lamp", 5, 7)
    put("tree", 8, 8)
    put("pine", 8, 6)
    put("bush", 6, 8)
    put("flowers", 6, 6)
    for i, (d, mid, title) in enumerate(ms_rows):   # 到达里程碑送的纪念碑
        x, y = [(6, 5), (7, 5), (8, 5)][i]
        put("monument", x, y, gift=True, note=title, d=d, ref="gift:ms:" + mid)
        st.c.execute("UPDATE town_item SET story=? WHERE ref=?",
                     (dumps({"text": f"到达了里程碑「{title}」", "day": day(d)}), "gift:ms:" + mid))

    lv_now = growth.level(st)["lv"]
    st.set_profile({"town_v": town.TOWN_V, "town_seen_level": lv_now, "town_welcome": "", "level_floor": 1})
    st.set_profile({"current_wish": guitar["id"]})
    return {"lv": lv_now, "xp": tot, "coins": growth.coins(st), "size": town.size_for(lv_now)}
