"""点子里的「话题」：不知道聊什么的时候点一个，小光照着配好的提示词陪 TA 聊（参考 Muse 的点子）。

点了以后：前端替 TA 发出 send 那句话（带着话题 id）；这一段对话里，话题提示词接在小光的系统提示后面。
话题进行中不打开别的练习（不给 start_scene、不走路由）；30 分钟没再聊、或者开始两小时以后，就算聊完了。
聊出来的东西都走现有的工具（remember / add_step），要 TA 点头才存。
话题只在点子里，TA 自己点：小光不主动推荐（不进 acts.FEATURES、主动消息、路由）。
"""
from __future__ import annotations

from datetime import timedelta

from .store import Store
from .util import iso, now, parse_iso

IDLE = timedelta(minutes=30)
LONGEST = timedelta(hours=2)
COMMON = "\n- 对 TA 说话用「你」，别说「TA」。"

TOPICS = {
    "blank_day": {
        "title": "完全空白的一天", "icon": "sun", "color": "var(--c-lemon)",
        "hook": "明天什么安排都没有，你会怎么过？",
        "send": "想聊聊：如果明天什么安排都没有，我会怎么过。",
        "prompt": """## 这段对话的话题：完全空白的一天
TA 在点子里点了这个话题：如果明天什么安排都没有，TA 会怎么过。
想聊出来的：TA 真正享受的是什么样的时间。从一个个具体的画面里看，不替 TA 总结性格。
怎么聊：
- 先用一句话接住，再问第一个问题：那天几点醒、醒来第一件事做什么。
- 之后每次只问一个问题，顺着 TA 刚说的细节往下问：在哪、和谁、吃什么、手机在不在手边、什么时候最舒服。像朋友好奇地问，不像采访。
- 每次回复 1～3 句。不给建议，不讲道理，不说「这说明你……」。
- 聊了 4～6 个来回，或者 TA 想停了：用一两句话说出你注意到的一个具体的点（比如「你两次提到窗边的位置」），再问 TA 要不要让你记住。TA 说要，才用 remember 记一句，用 TA 自己的说法。
- TA 想换话题就跟着换，不用把这个话题聊完。""",
    },
    "manual": {
        "title": "我的使用说明书", "icon": "book", "color": "var(--c-sky)",
        "hook": "如果你有一份说明书，上面会写什么？",
        "send": "想聊聊：如果我有一份使用说明书，上面会写什么。",
        "prompt": """## 这段对话的话题：我的使用说明书
TA 点了这个话题：如果 TA 有一份使用说明书，上面会写什么。
想聊出来的：TA 自己的「用法」，什么时候快没电、怎么充电、什么时候别打扰、有什么少有人知道的好用之处。轻松好玩，像一起给 TA 写说明书。
怎么聊：
- 先用一句话接住，再从最好答的一项问起：快没电的时候，TA 身上会出现什么信号。
- 一次只问一项，大致按这个顺序往下（TA 说得多，就在一项上多聊两句）：快没电的信号 → 最快的充电方式 → 请勿在什么时候打扰 → 少有人知道的隐藏功能 → 正确的夸法或安慰法。
- 每次回复 1～3 句：先用说明书的口吻把 TA 刚说的写成一条（比如「第 2 条：电量低时请投喂热汤面」），再问下一项。可以开点小玩笑，但不笑话 TA。
- 不分析性格，不下结论，不讲道理。
- 写满 4～5 条，或者 TA 想停了：把这几条整理成一份短短的说明书（每条一行，带编号），问 TA 要不要让你记住。TA 说要，才用 remember 一条一条记，用 TA 的说法。
- TA 想换话题就跟着换。""",
    },
    "parallel": {
        "title": "平行宇宙里的你", "icon": "sparkles", "color": "var(--c-violet)",
        "hook": "另一个宇宙里，你当初选了另一条路。那个你现在过得怎样？",
        "send": "想聊聊：平行宇宙里的另一个我。",
        "prompt": """## 这段对话的话题：平行宇宙里的另一个我
TA 点了这个话题：在另一个宇宙里，TA 当初做了另一个选择，那个 TA 现在过得怎么样。
想聊出来的：那个宇宙里让 TA 羡慕或者好奇的东西，从中看见 TA 心里想要什么。不比较哪边更好，也不劝 TA 后悔或者不后悔。
怎么聊：
- 先用一句话接住，再请 TA 挑一个岔路口：「如果当初……」（选了另一个专业、去了另一座城市、或者一个很小的选择）。TA 没想好，就给两三个轻松的例子。
- 然后一次只问一个画面：那个 TA 早上在哪醒来、每天在忙什么、身边是谁、什么时候最开心。跟着 TA 的细节往下问，像一起拍一部小电影。
- 每次回复 1～3 句，可以帮 TA 把画面说得具体一点，但别替 TA 编。
- 聊了 4～5 个来回以后，问 TA：那个宇宙里有没有一样东西，是 TA 想「偷」一点到这个宇宙来的。TA 说了，就陪 TA 想一个今天就能做的、很小的做法；TA 想试，再问要不要加成一个小步（add_step）。
- TA 聊着聊着难过了，就先停下来陪 TA，不急着往下走。
- 说起平行宇宙里的那个 TA，就叫「那个你」。
- TA 想换话题就跟着换。""",
    },
}


def ideas() -> list[dict]:
    """点子页「话题」那一组（core/api.py 的 IDEAS 用）。"""
    return [{"id": "topic_" + k, "title": t["title"], "kind": "topic", "topic": k, "scene": "", "minutes": 5, "group": "话题",
             "desc": t["hook"], "send": t["send"]} for k, t in TOPICS.items()]


def start(st: Store, tid: str) -> dict | None:
    """TA 在点子里点了一个话题：从这一句开始算。"""
    if tid not in TOPICS:
        return None
    t = iso()
    st.set_profile({"topic": {"id": tid, "since": t, "at": t}})
    st.log("topic", f"聊一个话题「{TOPICS[tid]['title']}」")
    return TOPICS[tid]


def active(st: Store) -> dict | None:
    """正在聊的话题：30 分钟内还在聊、开始不到两小时。是的话顺手把「最近一次」挪到现在。"""
    cur = st.profile().get("topic") or {}
    t = TOPICS.get(cur.get("id") or "")
    at, since = parse_iso(cur.get("at") or ""), parse_iso(cur.get("since") or "")
    if not t or not at or not since or now() - at > IDLE or now() - since > LONGEST:
        return None
    st.set_profile({"topic": {**cur, "at": iso()}})
    return {"id": cur["id"], **t}


def prompt(t: dict) -> str:
    return t["prompt"] + COMMON
