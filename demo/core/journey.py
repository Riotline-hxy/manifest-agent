"""成长轨迹看板（蜕变计划 v3）：愿望 · 瞬间 · 阶段回望 · 小光的小发现。

依据《显化成长轨迹看板设计文档》：
  - 每个愿望一张看板：左下「现在的我」，右上「向往的我」，中间是时间轨迹；
  - 亮点 = 某天真实留下的瞬间；休息或没记录的日子什么都不出现，不清零、不提示补卡；
  - 曲线是时间，不是进度：不把记录次数换算成「愿望完成度」；
  - 阶段回望只用所选区间内的真实记录做统计，不编造；
  - 小光的小发现是「推测」，用户选「像我 / 有一部分 / 不太像 / 跳过」，没确认就不写成事实；
  - 小光在聊天里只能「提议」记录，用户点了「留下」才保存（routes / agent 负责）。
"""
from __future__ import annotations

from datetime import date, timedelta

from . import llm
from .util import clip, day_key, iso, loads, dumps, new_id, now

CATEGORIES = {
    "calm": {"label": "心灵平静", "vision": "在忙碌中也能找到平静的片刻",
             "words": ["休息", "呼吸", "喝茶", "散步", "安静", "放松", "早睡", "冥想", "停下", "慢慢", "晒太阳"]},
    "wealth": {"label": "财富与事业", "vision": "拥有更多选择，做喜欢的事",
               "words": ["学习", "机会", "项目", "投递", "面试", "作品", "完成", "收入", "存钱", "客户"]},
    "body": {"label": "理想身材与健康", "vision": "拥有自己喜欢的身体状态",
             "words": ["跑步", "散步", "运动", "拉伸", "早睡", "早起", "蔬菜", "喝水", "健身", "瑜伽"]},
    "confidence": {"label": "自信与自我接纳", "vision": "更相信自己，愿意表达",
                   "words": ["开口", "表达", "提问", "勇敢", "尝试", "拒绝", "分享", "发言", "主动", "说出"]},
    "relation": {"label": "亲密关系与人际", "vision": "在关系中安心表达自己的需要",
                 "words": ["聊天", "沟通", "需要", "陪伴", "拥抱", "谢谢", "朋友", "家人", "一起", "理解"]},
    "freedom": {"label": "生活方式与自由", "vision": "拥有更多时间做自己喜欢的事",
                "words": ["喜欢", "选择", "第一次", "出门", "旅行", "自在", "安排", "尝试"]},
    "other": {"label": "其他愿望", "vision": "慢慢靠近想要的自己",
              "words": ["开心", "完成", "尝试", "休息", "喜欢", "第一次"]},
}

RANGES = (7, 15, 30, 60, 90)
MAX_ACTIVE = 6


def guess_category(text: str) -> str:
    t = text or ""
    rules = [
        ("confidence", ["自信", "表达", "勇敢", "开口", "接纳"]),
        ("calm", ["平静", "焦虑", "放松", "压力", "情绪", "安心"]),
        ("body", ["健康", "身材", "健身", "作息", "睡", "运动", "减"]),
        ("wealth", ["钱", "财富", "事业", "工作", "学业", "作品", "职业", "收入"]),
        ("relation", ["关系", "朋友", "家人", "恋", "边界", "伴侣", "人际"]),
        ("freedom", ["自由", "生活", "旅行", "时间", "方式"]),
    ]
    for cat, keys in rules:
        if any(k in t for k in keys):
            return cat
    return "other"


# ---------------------------------------------------------------- 愿望 ----

def wishes(st, include_archived: bool = False) -> list[dict]:
    q = "SELECT * FROM wish" + ("" if include_archived else " WHERE archived=0") + " ORDER BY sort, created_at"
    out = []
    for r in st.c.execute(q):
        w = dict(r)
        w["label"] = CATEGORIES.get(w["category"], CATEGORIES["other"])["label"]
        w["count"] = st.c.execute("SELECT COUNT(*) FROM moment WHERE wish_id=?", (w["id"],)).fetchone()[0]
        w["days"] = st.c.execute("SELECT COUNT(DISTINCT day) FROM moment WHERE wish_id=?", (w["id"],)).fetchone()[0]
        out.append(w)
    return out


def get_wish(st, wid: str) -> dict | None:
    r = st.c.execute("SELECT * FROM wish WHERE id=?", (wid,)).fetchone()
    return dict(r) if r else None


def add_wish(st, title: str, category: str, now_text: str = "", vision_text: str = "",
             started: str | None = None, scene: str = "") -> dict:
    category = category if category in CATEGORIES else guess_category(title)
    title = clip(title or CATEGORIES[category]["label"], 30)
    active = st.c.execute("SELECT COUNT(*) FROM wish WHERE archived=0").fetchone()[0]
    if active >= MAX_ACTIVE:
        raise ValueError(f"同时最多 {MAX_ACTIVE} 个愿望，可以先收起一个")
    wid = new_id("w")
    with st.lock:
        st.c.execute("INSERT INTO wish(id, title, category, now_text, vision_text, scene, started, archived, sort, created_at) "
                     "VALUES(?,?,?,?,?,?,?,0,?,?)",
                     (wid, title, category, clip(now_text, 80), clip(vision_text or CATEGORIES[category]["vision"], 80),
                      clip(scene, 20), started or day_key(), active, iso()))
    st.set_profile({"current_wish": wid})
    st.log("journey", f"开启了一段旅程：{title}")
    return get_wish(st, wid)


def edit_wish(st, wid: str, patch: dict) -> dict | None:
    w = get_wish(st, wid)
    if not w:
        return None
    fields = {}
    if "title" in patch:
        fields["title"] = clip(str(patch["title"] or w["title"]), 30)
    if patch.get("category") in CATEGORIES:
        fields["category"] = patch["category"]
    for k, n in (("now_text", 80), ("vision_text", 80), ("scene", 20)):
        if k in patch:
            fields[k] = clip(str(patch[k] or ""), n)
    if "archived" in patch:
        fields["archived"] = 1 if patch["archived"] else 0
    if fields:
        with st.lock:
            st.c.execute("UPDATE wish SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), wid))
        if fields.get("archived"):
            rest = wishes(st)
            st.set_profile({"current_wish": rest[0]["id"] if rest else ""})
            st.log("journey", f"把「{w['title']}」收起来了（记录都还在）")
    return get_wish(st, wid)


def current(st) -> dict | None:
    """The board the user last looked at. Creates the first board from the
    onboarding answer when someone arrives without one (so nobody starts empty)."""
    ws = wishes(st)
    if not ws:
        p = st.profile()
        intent = (p.get("intent_primary") or "").strip()
        if not intent or intent in ("还没想好",):
            return None
        w = add_wish(st, intent, guess_category(intent), now_text="", vision_text=p.get("intent_why") or "",
                     started=(p.get("created_at") or iso())[:10])
        return w
    cid = st.profile().get("current_wish") or ""
    return next((w for w in ws if w["id"] == cid), ws[0])


# ---------------------------------------------------------------- 瞬间 ----

def moments(st, wish_id: str | None = None, since: str | None = None, limit: int = 800) -> list[dict]:
    q, a = "SELECT * FROM moment WHERE 1=1", []
    if wish_id:
        q += " AND wish_id=?"; a.append(wish_id)
    if since:
        q += " AND day>=?"; a.append(since)
    q += " ORDER BY day DESC, created_at DESC LIMIT ?"
    a.append(limit)
    return [dict(r) for r in st.c.execute(q, a)]


def add_moment(st, wish_id: str, text: str, feeling: str = "", mood: str = "", day: str | None = None,
               source: str = "user") -> dict:
    w = get_wish(st, wish_id)
    if not w:
        raise ValueError("没有这个愿望")
    text = clip((text or "").strip(), 300)
    if not text:
        raise ValueError("写一句发生了什么就好")
    day = _valid_day(day)
    mid = new_id("mo")
    with st.lock:
        st.c.execute("INSERT INTO moment(id, wish_id, day, text, feeling, mood, source, created_at, updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?)",
                     (mid, wish_id, day, text, clip(feeling or "", 80), clip(mood or "", 10), source, iso(), iso()))
    st.log("journey", f"在「{w['title']}」留下一个瞬间")
    return dict(st.c.execute("SELECT * FROM moment WHERE id=?", (mid,)).fetchone())


def edit_moment(st, mid: str, patch: dict) -> dict | None:
    r = st.c.execute("SELECT * FROM moment WHERE id=?", (mid,)).fetchone()
    if not r:
        return None
    fields = {}
    if "text" in patch:
        t = clip(str(patch["text"] or "").strip(), 300)
        if not t:
            raise ValueError("内容不能为空")
        fields["text"] = t
    if "feeling" in patch:
        fields["feeling"] = clip(str(patch["feeling"] or ""), 80)
    if "mood" in patch:
        fields["mood"] = clip(str(patch["mood"] or ""), 10)
    if "day" in patch:
        fields["day"] = _valid_day(patch["day"])
    if fields:
        fields["updated_at"] = iso()
        with st.lock:
            st.c.execute("UPDATE moment SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), mid))
    return dict(st.c.execute("SELECT * FROM moment WHERE id=?", (mid,)).fetchone())


def delete_moment(st, mid: str) -> bool:
    with st.lock:
        return st.c.execute("DELETE FROM moment WHERE id=?", (mid,)).rowcount > 0


def _valid_day(day: str | None) -> str:
    today = now().date()
    if not day:
        return today.isoformat()
    try:
        d = date.fromisoformat(str(day)[:10])
    except ValueError:
        raise ValueError("日期不对")
    if d > today:
        raise ValueError("还没到那一天")
    if (today - d).days > 365:
        raise ValueError("太久以前的日子先不记了")
    return d.isoformat()


# ---------------------------------------------------------------- 阶段回望 ----

def review(st, wish_id: str, days: int) -> dict:
    """只用所选日历区间里的真实记录。没有记录时直说，不补故事。"""
    days = days if days in RANGES else 30
    w = get_wish(st, wish_id)
    if not w:
        raise ValueError("没有这个愿望")
    today = now().date()
    start = today - timedelta(days=days - 1)
    ms = sorted(moments(st, wish_id, since=start.isoformat()), key=lambda m: (m["day"], m["created_at"]))
    words = CATEGORIES.get(w["category"], CATEGORIES["other"])["words"]
    counts = {k: sum(1 for m in ms if k in (m["text"] + m["feeling"])) for k in words}
    top = max(counts.items(), key=lambda kv: kv[1]) if counts else ("", 0)
    feelings = [m["feeling"] for m in ms if m["feeling"]]
    quotes = []
    if ms:
        picks = [ms[0]] + ([ms[len(ms) // 2]] if len(ms) > 2 else []) + ([ms[-1]] if len(ms) > 1 else [])
        seen = set()
        for m in picks:
            if m["id"] not in seen:
                seen.add(m["id"])
                quotes.append({"id": m["id"], "day": m["day"], "text": m["text"], "feeling": m["feeling"]})
    if not ms:
        line = "这段时间还没有留下记录。你可以从今天开始，也可以先看看之前的自己。"
    else:
        line = f"过去 {days} 天，你留下了 {len(ms)} 个瞬间"
        if top[1] >= 2:
            line += f"，其中 {top[1]} 次提到了「{top[0]}」"
        line += "。你觉得这段时间有什么变化？"
    refl = [dict(r) for r in st.c.execute(
        "SELECT * FROM reflection WHERE wish_id=? ORDER BY created_at DESC LIMIT 6", (wish_id,))]
    return {"wish_id": wish_id, "days": days, "start": start.isoformat(), "end": today.isoformat(),
            "count": len(ms), "active_days": len({m["day"] for m in ms}),
            "top": {"word": top[0], "count": top[1]} if top[1] >= 2 else None,
            "feelings": feelings[-4:], "quotes": quotes, "line": line, "reflections": refl}


def reflect(st, wish_id: str, days: int, text: str) -> dict:
    text = clip((text or "").strip(), 300)
    if not text:
        raise ValueError("写一句也好")
    rid = new_id("rf")
    with st.lock:
        st.c.execute("INSERT INTO reflection(id, wish_id, days, text, created_at) VALUES(?,?,?,?,?)",
                     (rid, wish_id, int(days), text, iso()))
    st.log("journey", "写下了一段阶段回望")
    return dict(st.c.execute("SELECT * FROM reflection WHERE id=?", (rid,)).fetchone())


# ---------------------------------------------------------------- 小光的小发现 ----

INSIGHT_PROMPT = """你是显化陪伴 agent「小光」。读这个人在某个愿望下留下的真实瞬间，提出**一个**小发现。
要求：
- 必须基于下面列出的具体记录，至少引用其中一条的内容（可以转述），basis 写被引用记录的 id；
- 用推测和提问的口吻（「你觉得……吗？」「会不会……？」），不下结论，不贴性格标签，不鸡血；
- 不超过 60 字；
- 另给一个 claim：如果对方说「像我」，可以记下来的一句第三人称陈述（不超过 40 字）；
- 记录太少或看不出什么，就返回 {"skip": true}。
只输出 JSON：{"text":"...","claim":"...","basis":["id",...]} 或 {"skip":true}"""


def open_insight(st, wish_id: str) -> dict | None:
    r = st.c.execute("SELECT * FROM insight WHERE wish_id=? AND status='open' ORDER BY created_at DESC LIMIT 1",
                     (wish_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["basis"] = loads(d["basis"], [])
    return d


def make_insight(st, wish_id: str) -> dict:
    w = get_wish(st, wish_id)
    if not w:
        raise ValueError("没有这个愿望")
    existing = open_insight(st, wish_id)
    if existing:
        return {"insight": existing}
    ms = moments(st, wish_id, limit=24)
    if len(ms) < 4:
        return {"insight": None, "reason": "再多留几个瞬间，小光才看得出点什么"}
    lines = "\n".join(f"- id={m['id']} {m['day']}：{m['text']}" + (f"（感受：{m['feeling']}）" if m["feeling"] else "")
                      for m in reversed(ms))
    out = llm.complete_json([
        {"role": "system", "content": INSIGHT_PROMPT},
        {"role": "user", "content": f"愿望：{w['title']}\n现在的我：{w['now_text'] or '（没写）'}\n向往的我：{w['vision_text']}\n\n记录：\n{lines}"},
    ], timeout=40)
    if not out or out.get("skip") or not out.get("text"):
        return {"insight": None, "reason": "这次没看出特别的地方，过几天再来看看"}
    known = {m["id"] for m in ms}
    basis = [b for b in (out.get("basis") or []) if b in known][:4]
    if not basis:
        return {"insight": None, "reason": "这次没看出特别的地方，过几天再来看看"}
    iid = new_id("in")
    with st.lock:
        st.c.execute("INSERT INTO insight(id, wish_id, text, claim, basis, status, created_at) VALUES(?,?,?,?,?,?,?)",
                     (iid, wish_id, clip(out["text"], 90), clip(out.get("claim") or "", 60), dumps(basis), "open", iso()))
    return {"insight": open_insight(st, wish_id)}


def answer_insight(st, iid: str, answer: str) -> dict:
    r = st.c.execute("SELECT * FROM insight WHERE id=?", (iid,)).fetchone()
    if not r:
        raise ValueError("没有这条小发现")
    if answer not in ("yes", "partly", "no", "skip"):
        raise ValueError("回答不对")
    with st.lock:
        st.c.execute("UPDATE insight SET status=?, answered_at=? WHERE id=?", (answer, iso(), iid))
    claim = r["claim"] or ""
    wrote = None
    if claim and answer == "yes":
        wrote = st.add_memory(claim, "insight", "confirmed")
    elif claim and answer == "partly":
        wrote = st.add_memory(claim + "（自己说只有一部分像）", "insight", "confirmed")
    st.log("journey", {"yes": "确认了小光的一个发现", "partly": "说小光的发现有一部分像",
                       "no": "说小光的发现不太像", "skip": "跳过了小光的发现"}[answer])
    return {"ok": True, "memory": wrote}


# ---------------------------------------------------------------- 打包给前端 ----

def board(st) -> dict:
    cur = current(st)
    since = (now().date() - timedelta(days=89)).isoformat()
    return {
        "wishes": wishes(st),
        "current": cur["id"] if cur else "",
        "moments": moments(st, since=since),
        "insights": {w["id"]: open_insight(st, w["id"]) for w in wishes(st)},
        "categories": [{"id": k, "label": v["label"], "vision": v["vision"]} for k, v in CATEGORIES.items()],
        "today": day_key(),
    }
