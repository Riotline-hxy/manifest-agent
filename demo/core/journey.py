"""蜕变计划：愿望 → 路径（里程碑 · 习惯 · 小步）→ 时间轨迹。

  - 每个愿望有定下的日子（started）和计划实现的日子（target_day），轨迹从前者画到后者；
  - 路径有三种东西：里程碑（路上的站点，可带日期）、习惯（重复做的事，每天或每周 N 次）、
    小步（做一次就完成的事）；
  - 轨迹上的时间节点 = 那天为这个愿望做过的事：完成的小步、习惯打卡、到达的里程碑、留下的瞬间；
    跨度长时由前端按天数合并节点；
  - 休息日记成 record(type=rest)，那天的习惯不用做，什么进度都保留；
  - 小光的小发现是推测，用户选「像我 / 有一部分」才写进记忆；
  - 小光在聊天里只能提议瞬间或计划，用户确认后才保存（routes / agent 负责）。
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import llm
from .util import agent_name, clip, day_key, iso, loads, dumps, new_id, now

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

MAX_ACTIVE = 6
DEFAULT_SPAN = 30           # 没设计划日期时（比如建档自动生成的愿望），默认定下后 30 天
MAX_HABITS = 8


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
        w["target_day"] = target_of(w)
        w["prompts"] = loads(w.get("prompts") or "[]", [])
        w["count"] = st.c.execute("SELECT COUNT(*) FROM moment WHERE wish_id=?", (w["id"],)).fetchone()[0]
        w["days"] = st.c.execute("SELECT COUNT(DISTINCT day) FROM moment WHERE wish_id=?", (w["id"],)).fetchone()[0]
        out.append(w)
    return out


def get_wish(st, wid: str) -> dict | None:
    r = st.c.execute("SELECT * FROM wish WHERE id=?", (wid,)).fetchone()
    if not r:
        return None
    w = dict(r)
    w["target_day"] = target_of(w)
    return w


def target_of(w: dict) -> str:
    if w.get("target_day"):
        return w["target_day"]
    try:
        return (date.fromisoformat(w["started"][:10]) + timedelta(days=DEFAULT_SPAN)).isoformat()
    except (TypeError, ValueError, KeyError):
        return (now().date() + timedelta(days=DEFAULT_SPAN)).isoformat()


def _target_day(day, started: str) -> str:
    """计划实现的日子：在定下愿望那天之后，五年以内。"""
    if not day:
        return ""
    try:
        d = date.fromisoformat(str(day)[:10])
    except ValueError:
        raise ValueError("日期不对")
    if d <= date.fromisoformat(started[:10]):
        raise ValueError("计划日期要在定下愿望之后")
    if (d - now().date()).days > 365 * 5:
        raise ValueError("先定一个五年以内的日子吧")
    return d.isoformat()


def add_wish(st, title: str, category: str, now_text: str = "", vision_text: str = "",
             started: str | None = None, scene: str = "", target_day: str | None = None) -> dict:
    category = category if category in CATEGORIES else guess_category(title)
    title = clip(title or CATEGORIES[category]["label"], 30)
    active = st.c.execute("SELECT COUNT(*) FROM wish WHERE archived=0").fetchone()[0]
    if active >= MAX_ACTIVE:
        raise ValueError(f"同时最多 {MAX_ACTIVE} 个愿望，可以先收起一个")
    wid = new_id("w")
    started = started or day_key()
    target = _target_day(target_day, started)
    with st.lock:
        st.c.execute("INSERT INTO wish(id, title, category, now_text, vision_text, scene, started, archived, sort, created_at, target_day) "
                     "VALUES(?,?,?,?,?,?,?,0,?,?,?)",
                     (wid, title, category, clip(now_text, 80), clip(vision_text or CATEGORIES[category]["vision"], 80),
                      clip(scene, 20), started, active, iso(), target))
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
    if patch.get("target_day"):
        fields["target_day"] = _target_day(patch["target_day"], w["started"])
    if "prompts" in patch:   # 用户自己写的「从一个问题开始」
        fields["prompts"] = dumps([clip(str(x).strip(), 30) for x in (patch["prompts"] or []) if str(x).strip()][:6])
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
        if st.c.execute("SELECT 1 FROM wish LIMIT 1").fetchone():
            return None       # 有过愿望、现在都收起了：是 TA 自己收的，不再照建档时的说法替 TA 建一个
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


def _moment_wish(st, wish_id) -> dict | None:
    """瞬间可以不挂愿望（空）；给了就得是一个真的愿望。"""
    wish_id = str(wish_id or "")
    if not wish_id:
        return None
    w = get_wish(st, wish_id)
    if not w:
        raise ValueError("没有这个愿望")
    return w


def _moment_photo(st, pid) -> str:
    from . import photos
    pid = str(pid or "")
    if pid and not photos.exists(st, pid):
        raise ValueError("照片没传上来，再试一次")
    return pid


def add_moment(st, wish_id: str, text: str, feeling: str = "", mood: str = "", day: str | None = None,
               source: str = "user", photo: str = "") -> dict:
    """瞬间：一句话（可以配一张照片），可以挂在某个愿望下，也可以不挂。
    只在用户自己留、或者点了小光提议卡上的「留下」、或者明确让小光记下时才写——走一遍练习不会自动加。"""
    w = _moment_wish(st, wish_id)
    text = clip((text or "").strip(), 300)
    if not text:
        raise ValueError("写一句发生了什么就好")
    day = _valid_day(day)
    photo = _moment_photo(st, photo)
    mid = new_id("mo")
    with st.lock:
        st.c.execute("INSERT INTO moment(id, wish_id, day, text, feeling, mood, source, created_at, updated_at, photo) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (mid, w["id"] if w else "", day, text, clip(feeling or "", 80), clip(mood or "", 10), source, iso(), iso(), photo))
    st.log("journey", f"在「{w['title']}」留下一个瞬间" if w else "留下一个瞬间")
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
    if "wish_id" in patch:
        w = _moment_wish(st, patch["wish_id"])
        fields["wish_id"] = w["id"] if w else ""
    old_photo = r["photo"] or ""
    if "photo" in patch and str(patch["photo"] or "") != old_photo:
        fields["photo"] = _moment_photo(st, patch["photo"])
    if fields:
        fields["updated_at"] = iso()
        with st.lock:
            st.c.execute("UPDATE moment SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), mid))
        if "photo" in fields and old_photo:   # 换了或去掉了照片：旧的那张删掉
            _drop_photo(st, old_photo)
    return dict(st.c.execute("SELECT * FROM moment WHERE id=?", (mid,)).fetchone())


def delete_moment(st, mid: str) -> bool:
    r = st.c.execute("SELECT photo FROM moment WHERE id=?", (mid,)).fetchone()
    with st.lock:
        gone = st.c.execute("DELETE FROM moment WHERE id=?", (mid,)).rowcount > 0
    if gone and r and r["photo"]:
        _drop_photo(st, r["photo"])
    return gone


def _drop_photo(st, pid: str) -> None:
    """删照片文件；万一别的瞬间还挂着同一张（照片 id 是前端传来的），就先留着。"""
    from . import photos
    if pid and not st.c.execute("SELECT 1 FROM moment WHERE photo=? LIMIT 1", (pid,)).fetchone():
        photos.delete(st, pid)


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


# ---------------------------------------------------------------- 小光的小发现 ----

INSIGHT_PROMPT = """你是显化陪伴 agent「{name}」。读这个人在某个愿望下留下的真实瞬间，提出**一个**小发现。
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
        return {"insight": None, "reason": f"再多留几个瞬间，{agent_name(st.profile())}才看得出点什么"}
    lines = "\n".join(f"- id={m['id']} {m['day']}：{m['text']}" + (f"（感受：{m['feeling']}）" if m["feeling"] else "")
                      for m in reversed(ms))
    out = llm.complete_json([
        {"role": "system", "content": INSIGHT_PROMPT.replace("{name}", agent_name(st.profile()))},
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


# ---------------------------------------------------------------- 习惯 ----

def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def habits(st, wish_id: str | None = None, since: str | None = None, include_archived: bool = False) -> list[dict]:
    q, a = "SELECT * FROM habit WHERE 1=1" + ("" if include_archived else
                                              " AND archived=0 AND wish_id IN (SELECT id FROM wish WHERE archived=0)"), []
    if wish_id:
        q += " AND wish_id=?"; a.append(wish_id)
    today = now().date()
    wk = _week_start(today).isoformat()
    since = since or (today - timedelta(days=400)).isoformat()
    out = []
    for r in st.c.execute(q + " ORDER BY created_at", a).fetchall():
        h = dict(r)
        h["days"] = [x[0] for x in st.c.execute(
            "SELECT day FROM habit_log WHERE habit_id=? AND day>=? ORDER BY day", (h["id"], since))]
        h["need"] = 7 if h["freq"] == "daily" else max(1, min(6, int(h["per_week"] or 1)))
        h["week"] = sum(1 for d in h["days"] if d >= wk)
        h["today"] = today.isoformat() in h["days"]
        h["skips"] = [x[0] for x in st.c.execute(
            "SELECT day FROM habit_skip WHERE habit_id=? AND day>=? ORDER BY day", (h["id"], since))]
        h["skipped"] = today.isoformat() in h["skips"]
        h["total"] = st.c.execute("SELECT COUNT(*) FROM habit_log WHERE habit_id=?", (h["id"],)).fetchone()[0]
        h["freq_text"] = freq_text(h)
        out.append(h)
    return out


def freq_text(h: dict) -> str:
    return "每天" if h["freq"] == "daily" else f"每周 {h['per_week']} 次"


def add_habit(st, wish_id: str, title: str, freq: str = "daily", per_week=3) -> dict:
    if not get_wish(st, wish_id):
        raise ValueError("没有这个愿望")
    title = clip((title or "").strip(), 30)
    if not title:
        raise ValueError("写一下要重复做的事")
    if st.c.execute("SELECT COUNT(*) FROM habit WHERE wish_id=? AND archived=0", (wish_id,)).fetchone()[0] >= MAX_HABITS:
        raise ValueError(f"一个愿望最多 {MAX_HABITS} 个习惯，可以先收起一个")
    freq = "weekly" if freq == "weekly" else "daily"
    try:
        per_week = max(1, min(6, int(per_week or 3)))
    except (TypeError, ValueError):
        per_week = 3
    hid = new_id("h")
    with st.lock:
        st.c.execute("INSERT INTO habit(id, wish_id, title, freq, per_week, archived, created_at) VALUES(?,?,?,?,?,0,?)",
                     (hid, wish_id, title, freq, per_week if freq == "weekly" else 7, iso()))
    st.log("plan", f"加了一个习惯：{title}")
    return next(h for h in habits(st, wish_id) if h["id"] == hid)


def edit_habit(st, hid: str, patch: dict) -> dict | None:
    r = st.c.execute("SELECT * FROM habit WHERE id=?", (hid,)).fetchone()
    if not r:
        return None
    fields = {}
    if patch.get("title"):
        fields["title"] = clip(str(patch["title"]).strip(), 30)
    if patch.get("freq") in ("daily", "weekly"):
        fields["freq"] = patch["freq"]
        try:
            pw = max(1, min(6, int(patch.get("per_week") or 3)))
        except (TypeError, ValueError):
            pw = 3
        fields["per_week"] = 7 if patch["freq"] == "daily" else pw
    if "archived" in patch:
        fields["archived"] = 1 if patch["archived"] else 0
    if fields:
        with st.lock:
            st.c.execute("UPDATE habit SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), hid))
        if fields.get("archived"):
            st.log("plan", f"收起了习惯：{r['title']}（打卡记录都在）")
    return dict(st.c.execute("SELECT * FROM habit WHERE id=?", (hid,)).fetchone())


def check_habit(st, hid: str, day: str | None = None, undo: bool = False) -> tuple[dict, bool]:
    """打卡 / 撤销。返回 (habit, 这次是否新打了卡)。"""
    r = st.c.execute("SELECT * FROM habit WHERE id=?", (hid,)).fetchone()
    if not r:
        raise ValueError("没有这个习惯")
    day = _valid_day(day)
    with st.lock:
        if undo:
            st.c.execute("DELETE FROM habit_log WHERE habit_id=? AND day=?", (hid, day))
            created = False
        else:
            created = st.c.execute("INSERT OR IGNORE INTO habit_log(id, habit_id, day, created_at) VALUES(?,?,?,?)",
                                   (new_id("hl"), hid, day, iso())).rowcount > 0
            st.c.execute("DELETE FROM habit_skip WHERE habit_id=? AND day=?", (hid, day))   # 做了就不算跳过
    if created:
        st.log("plan", f"打卡：{r['title']}")
    return dict(r), created


def skip_habit(st, hid: str, undo: bool = False) -> dict:
    """单项暂停：这个习惯今天先不做。不影响其他习惯，也不影响任何进度。"""
    r = st.c.execute("SELECT * FROM habit WHERE id=?", (hid,)).fetchone()
    if not r:
        raise ValueError("没有这个习惯")
    day = day_key()
    with st.lock:
        if undo:
            st.c.execute("DELETE FROM habit_skip WHERE habit_id=? AND day=?", (hid, day))
        else:
            st.c.execute("INSERT OR IGNORE INTO habit_skip(habit_id, day, created_at) VALUES(?,?,?)", (hid, day, iso()))
    if not undo:
        st.log("rest", f"「{r['title']}」今天先休息")
    return dict(r)


def ease_habit(h: dict) -> tuple[str, int] | None:
    """调低一档：每天 → 每周 3 次 → 每周 2 次 → 每周 1 次。已经最低就返回 None。"""
    if h["freq"] == "daily":
        return "weekly", 3
    if int(h["per_week"] or 1) > 1:
        return "weekly", int(h["per_week"]) - 1
    return None


def is_resting(st, day: str | None = None) -> bool:
    return bool(st.c.execute("SELECT 1 FROM record WHERE type='rest' AND day=?", (day or day_key(),)).fetchone())


def find_habit(st, title: str) -> dict | None:
    return _pick(habits(st), title)


# ---------------------------------------------------------------- 里程碑 ----

def milestones(st, wish_id: str | None = None) -> list[dict]:
    q, a = "SELECT * FROM milestone", []
    if wish_id:
        q += " WHERE wish_id=?"; a.append(wish_id)
    rows = [dict(r) for r in st.c.execute(q, a)]
    rows.sort(key=lambda m: (m["due_day"] or "9999", m["created_at"]))
    return rows


def _due(day) -> str:
    if not day:
        return ""
    try:
        return date.fromisoformat(str(day)[:10]).isoformat()
    except ValueError:
        raise ValueError("日期不对")


def add_milestone(st, wish_id: str, title: str, due_day: str | None = None) -> dict:
    if not get_wish(st, wish_id):
        raise ValueError("没有这个愿望")
    title = clip((title or "").strip(), 30)
    if not title:
        raise ValueError("写一下这个站点是什么")
    mid = new_id("ms")
    with st.lock:
        st.c.execute("INSERT INTO milestone(id, wish_id, title, due_day, status, done_at, created_at) VALUES(?,?,?,?,?,?,?)",
                     (mid, wish_id, title, _due(due_day), "todo", "", iso()))
    st.log("plan", f"定了一个里程碑：{title}")
    return dict(st.c.execute("SELECT * FROM milestone WHERE id=?", (mid,)).fetchone())


def edit_milestone(st, mid: str, patch: dict) -> dict | None:
    r = st.c.execute("SELECT * FROM milestone WHERE id=?", (mid,)).fetchone()
    if not r:
        return None
    if patch.get("delete"):
        with st.lock:
            st.c.execute("DELETE FROM milestone WHERE id=?", (mid,))
        return dict(r)
    fields = {}
    if patch.get("title"):
        fields["title"] = clip(str(patch["title"]).strip(), 30)
    if "due_day" in patch:
        fields["due_day"] = _due(patch["due_day"])
    if patch.get("status") in ("todo", "done"):
        fields["status"] = patch["status"]
        fields["done_at"] = iso() if patch["status"] == "done" else ""
    if fields:
        with st.lock:
            st.c.execute("UPDATE milestone SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), mid))
        if fields.get("status") == "done":
            st.log("plan", f"到达里程碑：{r['title']}")
    return dict(st.c.execute("SELECT * FROM milestone WHERE id=?", (mid,)).fetchone())


# ---------------------------------------------------------------- 小光提议的整套计划 ----

def _norm(t: str) -> str:
    return re.sub(r"[\s，。,.!！?？、]+", "", t or "").lower()


def existing_titles(st, wish_id: str) -> dict:
    """路径上已经有的东西（用于去重）。"""
    return {
        "milestones": [m["title"] for m in milestones(st, wish_id)],
        "habits": [h["title"] for h in habits(st, wish_id)],
        "steps": [r[0] for r in st.c.execute("SELECT title FROM step WHERE wish_id=? AND status='todo'", (wish_id,))],
    }


def is_dup(title: str, have: list[str]) -> bool:
    t = _norm(title)
    return bool(t) and any(t == _norm(x) or (len(t) >= 4 and (t in _norm(x) or _norm(x) in t)) for x in have)


def drop_dups(st, wish_id: str, plan: dict) -> tuple[dict, list[str]]:
    have = existing_titles(st, wish_id)
    out, dropped = {}, []
    for k in ("milestones", "habits", "steps"):
        seen = list(have[k]) + (have["habits"] if k == "steps" else [])
        keep = []
        for it in plan.get(k) or []:
            title = str((it or {}).get("title") or "")
            if is_dup(title, seen):
                dropped.append(title)
                continue
            seen.append(title)
            keep.append(it)
        out[k] = keep
    return out, dropped


def apply_plan(st, wish_id: str, plan: dict) -> dict:
    """用户在对话卡片上勾选后才调用；每一项都走和手动添加一样的校验。"""
    w = get_wish(st, wish_id)
    if not w:
        raise ValueError("没有这个愿望")
    made = {"milestones": [], "habits": [], "steps": []}
    today = now().date()
    plan, _ = drop_dups(st, wish_id, plan)
    for m in (plan.get("milestones") or [])[:5]:
        due = m.get("due_day") or ""
        if not due and m.get("due_in_days"):
            try:
                due = (today + timedelta(days=max(1, min(1800, int(m["due_in_days"]))))).isoformat()
            except (TypeError, ValueError):
                due = ""
        if str(m.get("title") or "").strip():
            made["milestones"].append(add_milestone(st, wish_id, str(m["title"]), due))
    for h in (plan.get("habits") or [])[:4]:
        if str(h.get("title") or "").strip():
            made["habits"].append(add_habit(st, wish_id, str(h["title"]), str(h.get("freq") or "daily"), h.get("per_week") or 3))
    for s_ in (plan.get("steps") or [])[:5]:
        title = clip(str(s_.get("title") or "").strip(), 40)
        if title:
            made["steps"].append(st.add_step(title, why=str(s_.get("why") or ""), wish=w["title"], wish_id=wish_id))
    st.log("plan", f"和小光一起规划了「{w['title']}」")
    return made


def path_text(st, w: dict) -> str:
    """给小光看的一段路径描述。"""
    lines = [f"[{w['id']}] {w['title']}（{w['label']}）：{w['started']} 定下，计划 {w['target_day']} 实现；向往：{w['vision_text']}"]
    for m in milestones(st, w["id"]):
        lines.append(f"  - 里程碑 [{m['id']}] {'✓' if m['status'] == 'done' else '·'} {m['title']}" + (f"（{m['due_day']}）" if m["due_day"] else ""))
    for h in habits(st, w["id"]):
        lines.append(f"  - 习惯 [{h['id']}] {h['title']}，{h['freq_text']}，本周 {h['week']}/{h['need']}" + ("，今天已打卡" if h["today"] else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------- 改计划里已有的东西 ----

def _pick(items: list[dict], ref: str, key: str = "title") -> dict | None:
    """按 id 或名字找：id > 完全相同 > 互相包含 > 去掉空格标点后包含 > 两字片段重合。"""
    ref = (ref or "").strip()
    if not ref:
        return None
    # 模型常把 id 连方括号、甚至连名字一起抄过来：「[r_2ac0bb9e3216]」「[w_1a2b…] 早睡早起」
    ids = {it["id"]: it for it in items}
    for m in re.findall(r"[a-z]{1,3}_[0-9a-f]{6,}", ref):
        if m in ids:
            return ids[m]
    ref = ref.strip("[]【】「」\"' ")
    for it in items:
        if it["id"] == ref or it[key] == ref:
            return it
    for it in items:
        if ref in it[key] or it[key] in ref:
            return it
    n = _norm(ref)
    hit = next((it for it in items if n and (n in _norm(it[key]) or _norm(it[key]) in n)), None)
    if hit:
        return hit
    # 模型常会转述名字（「选定慵懒爵士曲目」↔「选定一首慵懒浪漫的爵士曲」）：按两字片段的重合度挑最像的
    grams = lambda t: {t[i:i + 2] for i in range(len(t) - 1)} or {t}
    want = grams(n)
    best, score = None, 0.0
    for it in items:
        sc = len(want & grams(_norm(it[key]))) / len(want)
        if sc > score:
            best, score = it, sc
    return best if score >= 0.5 else None


def _alike(items: list[dict], ref: str, key: str = "title") -> list[dict]:
    """ref 没有照抄 id 或完整名字时，名字「像」它的所有项：互相包含，或两字片段重合一半以上。
    照抄了 id / 完整名字（只对上一项）就返回空——那是点了名的。
    改、删之前用它：像的不止一个，就不替 TA 挑一个动手，先问（「把背单词那个删了」而计划里有两个背单词）。"""
    ref = (ref or "").strip()
    if not ref:
        return []
    ids = {it["id"] for it in items}
    if any(m in ids for m in re.findall(r"[a-z]{1,3}_[0-9a-f]{6,}", ref)):
        return []
    ref = ref.strip("[]【】「」\"' ")
    if sum(1 for it in items if it["id"] == ref or it[key] == ref) == 1:
        return []
    n = _norm(ref)
    if not n:
        return []
    grams = lambda t: {t[i:i + 2] for i in range(len(t) - 1)} or {t}
    want = grams(n)
    out = []
    for it in items:
        t = _norm(it[key])
        if t and (n in t or t in n or len(want & grams(t)) / len(want) >= 0.5):
            out.append(it)
    return out


def _unclear(cands: list[dict], key: str = "title") -> dict:
    return {"ok": False, "ambiguous": True, "have": [clip(c[key], 24) for c in cands[:6]],
            "error": f"有 {len(cands)} 项都对得上，别替 TA 挑一个动手：先问 TA 指的是哪一个（have 里是这几项）"}


ALL_OF_THEM = re.compile(r"都|全部|所有|全删|两个|三个|这些|那些|一起")


def _said(title: str, text: str) -> float:
    """这个名字有多少出现在一句话里（0–1）：整个名字都在就是 1，否则看两字片段对上了几成。"""
    from .util import tokens
    title, text = (title or "").strip(), text or ""
    if not title or not text:
        return 0.0
    if title in text or (_norm(title) and _norm(title) in _norm(text)):
        return 1.0
    want = set(tokens(title))
    return len(want & set(tokens(text))) / len(want) if want else 0.0


def unnamed_removal(st, kind: str, ref: str, said: str, last_ai: str = "") -> dict | None:
    """删东西之前：TA 这句话到底有没有点到这一项。看的是 TA 的原话，不是模型填的目标——
    模型会自己挑一个、把准确的 id 填进来（「把背单词那个习惯删了吧」，计划里有两个背单词，它就挑了一个删）。
    算点了名的：这一项的名字（大半）出现在 TA 这句话里；或者 TA 这句话只沾到这一项；
    或者 TA 没提任何一项、而小光上一句刚说到它（TA 是在回应小光的提议）。其余都先问。
    同类的东西只有一个、或者 TA 说了「都 / 全部」，不拦。返回 None 表示可以删。"""
    if kind == "habit":
        pool = habits(st)
    elif kind == "wish":
        pool = wishes(st)
    elif kind == "milestone":
        live = {w["id"] for w in wishes(st)}
        pool = [m for m in milestones(st) if m["wish_id"] in live]
    elif kind == "step":
        pool = [dict(r) for r in st.c.execute("SELECT * FROM step WHERE status IN ('todo','dropped') ORDER BY created_at DESC LIMIT 200")]
    else:
        return None           # 瞬间是一整句话，TA 很少照着念：交给上面按名字的检查
    if len(pool) < 2 or not (said or "").strip() or ALL_OF_THEM.search(said):
        return None
    it = _pick(pool, ref) if (ref or "").strip() else None
    if not it:
        return None           # 没找到 / 没填目标：edit_item 自己会照实说
    named = [x for x in pool if _said(x["title"], said) >= 0.2]
    if _said(it["title"], said) >= 0.8 or [x["id"] for x in named] == [it["id"]]:
        return None
    if not named and _said(it["title"], last_ai) >= 0.5:
        return None
    if len(named) > 1:
        return _unclear(named)
    return {"ok": False, "ambiguous": True, "have": [clip(x["title"], 24) for x in pool[:6]],
            "error": f"TA 这句话没点到「{clip(it['title'], 16)}」，别替 TA 挑一个删：先问一句是不是它"}


def _when(patch: dict, base: str = "") -> str | None:
    """新日期：指定的日子 / 从今天起 N 天后 / 在原来的日子上挪 N 天（「往后推两周」= +14，「提前三天」= -3）。"""
    if patch.get("shift_days") not in (None, "", 0):
        try:
            start = date.fromisoformat(base[:10]) if base else now().date()
            return (start + timedelta(days=max(-1800, min(1800, int(patch["shift_days"]))))).isoformat()
        except (TypeError, ValueError):
            raise ValueError("天数不对")
    if patch.get("due_day"):
        return _due(patch["due_day"])
    if patch.get("due_in_days") not in (None, ""):
        try:
            return (now().date() + timedelta(days=max(0, min(1800, int(patch["due_in_days"]))))).isoformat()
        except (TypeError, ValueError):
            raise ValueError("天数不对")
    return None


def _md(day: str) -> str:
    return f"{int(day[5:7])}月{int(day[8:10])}日"


CHANGE_KEYS = ("title", "due_day", "due_in_days", "shift_days", "freq", "per_week", "status", "vision_text", "now_text",
               "text", "feeling", "day")


def _done(kind: str, it: dict, changed: list[str], patch: dict | None = None, **extra) -> dict:
    if not changed:
        if any(k in (patch or {}) for k in CHANGE_KEYS):   # 要改成的样子和现在一样：不是失败，也不用再说一遍
            return {"ok": False, "unchanged": True, "kind": kind, "id": it["id"], "title": it["title"], "changed": [],
                    "error": "本来就是这样，这次什么都没动；回复里不用提这次操作，接着聊就好"}
        return {"ok": False, "kind": kind, "id": it["id"], "title": it["title"], "changed": [],
                "error": "没有要改的内容：说清楚要改成什么（名字、日期、频率），或者要删掉 / 收起"}
    return {"ok": True, "kind": kind, "id": it["id"], "title": it["title"], "changed": changed, **extra}


def _wish_for(st, ref: str) -> dict | None:
    """新加的东西放进哪个愿望：按名字找；没说就放进正在看的那个。"""
    ref = (ref or "").strip()
    return _pick(wishes(st), ref) if ref else current(st)


def edit_item(st, kind: str, ref: str, patch: dict, action: str = "") -> dict:
    """小光替用户增删改计划里的东西。
    kind = wish / milestone / habit / step / moment；action = add / change / remove / restore。
    返回 {ok, kind, id, title, changed: [...]}；找不到时把现有的名字一起返回，让小光照实说。"""
    action = action or ("remove" if patch.get("delete") else "change")
    if action not in ("add", "change", "remove", "restore"):
        return {"ok": False, "error": "不认识的操作"}
    if kind not in ("wish", "milestone", "habit", "step", "moment"):
        return {"ok": False, "error": "不认识要改的东西"}
    ref = (ref or "").strip()
    changed: list[str] = []

    # ---- 新加 ----
    if action == "add":
        title = str(patch.get("title") or ref or "").strip()
        if kind == "wish":
            w = add_wish(st, title, guess_category(title + str(patch.get("vision_text") or "")),
                         str(patch.get("now_text") or ""), str(patch.get("vision_text") or ""),
                         target_day=_when(patch) or None)
            return {"ok": True, "kind": kind, "id": w["id"], "title": w["title"],
                    "changed": [f"新开了一个愿望，计划 {_md(w['target_day'])} 实现"]}
        if kind == "moment":   # 瞬间可以不挂愿望：说了是哪个愿望才挂，没说就不挂
            ref_w = str(patch.get("wish") or "").strip()
            w = _pick(wishes(st), ref_w) if ref_w else None
            if ref_w and not w:
                return {"ok": False, "error": "没找到这个愿望", "have": [x["title"] for x in wishes(st)]}
            m = add_moment(st, w["id"] if w else "", str(patch.get("text") or title), str(patch.get("feeling") or ""),
                           day=patch.get("day") or None, source="chat")
            return {"ok": True, "kind": kind, "id": m["id"], "title": clip(m["text"], 30), "wish_title": w["title"] if w else "",
                    "changed": [f"留成了一个瞬间（{_md(m['day'])}）" + (f"，挂在「{w['title']}」下" if w else "")], "new_moment": True}
        w = _wish_for(st, str(patch.get("wish") or ""))
        if not w:
            return {"ok": False, "error": "没找到要放进的愿望", "have": [x["title"] for x in wishes(st)]}
        if kind == "milestone":
            m = add_milestone(st, w["id"], title, _when(patch))
            return {"ok": True, "kind": kind, "id": m["id"], "title": m["title"], "wish_title": w["title"],
                    "changed": ["加进了「" + w["title"] + "」" + (f"，{_md(m['due_day'])}" if m["due_day"] else "")]}
        if kind == "habit":
            if any(_norm(h["title"]) == _norm(title) for h in habits(st, w["id"])):
                return {"ok": False, "error": "这个习惯已经在了，想改频率就用 change"}
            h = add_habit(st, w["id"], title, str(patch.get("freq") or "daily"), patch.get("per_week") or 3)
            return {"ok": True, "kind": kind, "id": h["id"], "title": h["title"], "wish_title": w["title"],
                    "changed": [f"加进了「{w['title']}」，{h['freq_text']}"]}
        if kind == "step":
            title = clip(title, 40)
            if not title:
                raise ValueError("写一下这一步是什么")
            day = schedule_day(_when(patch) or "")
            s_ = st.add_step(title, why=str(patch.get("why") or ""), wish=w["title"], wish_id=w["id"], scheduled_day=day)
            st.log("plan", "加了一小步：" + title)
            return {"ok": True, "kind": kind, "id": s_["id"], "title": s_["title"], "wish_title": w["title"],
                    "changed": [f"加进了「{w['title']}」的小步" + (f"，安排在 {_md(day)}" if day else "")]}
        raise ValueError("不认识要加的东西")

    # ---- 愿望 ----
    if kind == "wish":
        pool = wishes(st, include_archived=action == "restore")
        if action == "restore":
            pool = [w for w in pool if w["archived"]]
        if not ref and action == "remove" and len(pool) > 1:    # 没说是哪个：不把「正在看的那个」当成 TA 要收起的
            return {"ok": False, "ambiguous": True, "have": [x["title"] for x in pool],
                    "error": "TA 没说是哪个愿望，别替 TA 挑：先问一句要收起哪一个"}
        if len(_alike(pool, ref)) > 1:
            return _unclear(_alike(pool, ref))
        w = _pick(pool, ref) if ref else (None if action == "restore" else current(st))
        if not w:
            have = [x["title"] for x in pool]
            return {"ok": False, "have": have,
                    "error": "没找到这个愿望" if have else ("没有收起的愿望" if action == "restore" else "还没有愿望")}
        if action == "remove":
            edit_wish(st, w["id"], {"archived": True})
            return _done(kind, w, ["收起了：它下面的里程碑、习惯、瞬间都还留着，想找回随时说"])
        if action == "restore":
            if len(wishes(st)) >= MAX_ACTIVE:
                return {"ok": False, "error": f"同时最多 {MAX_ACTIVE} 个愿望，先收起一个才能找回"}
            edit_wish(st, w["id"], {"archived": False})
            st.set_profile({"current_wish": w["id"]})
            st.log("journey", f"把「{w['title']}」找回来了")
            return _done(kind, w, ["找回来了，之前的记录都在"])
        p = {}
        if patch.get("title") and patch["title"] != w["title"]:
            p["title"] = patch["title"]; changed.append(f"名字改成「{clip(patch['title'], 30)}」")
        due = _when(patch, w["target_day"])
        if due is not None and due != w["target_day"]:
            p["target_day"] = due; changed.append(f"计划日期改到 {_md(due)}")
        for k, label in (("vision_text", "向往的样子"), ("now_text", "现在的自己")):
            if patch.get(k) and patch[k] != w.get(k):
                p[k] = patch[k]; changed.append(f"改了{label}")
        if p:
            edit_wish(st, w["id"], p)
            st.log("journey", f"改了愿望「{w['title']}」：" + "，".join(changed))
        return _done(kind, w, changed, patch)

    # ---- 里程碑 ----
    if kind == "milestone":
        live = {w["id"] for w in wishes(st)}
        pool = [m for m in milestones(st) if m["wish_id"] in live]
        if len(_alike(pool, ref)) > 1:
            return _unclear(_alike(pool, ref))
        m = _pick(pool, ref)
        if not m:
            return {"ok": False, "error": "没找到这个里程碑", "have": [x["title"] for x in pool]}
        if action == "remove":
            edit_milestone(st, m["id"], {"delete": True})
            st.log("plan", f"删掉了里程碑：{m['title']}")
            return _done(kind, m, ["删掉了"])
        if action == "restore":
            return {"ok": False, "error": "删掉的里程碑找不回来了，可以重新加一个"}
        p = {}
        if patch.get("title") and patch["title"] != m["title"]:
            p["title"] = patch["title"]; changed.append(f"名字改成「{clip(patch['title'], 30)}」")
        due = _when(patch, m["due_day"])
        if due is not None and due != m["due_day"]:
            p["due_day"] = due; changed.append(f"日期改到 {_md(due)}")
        if patch.get("status") in ("done", "todo") and patch["status"] != m["status"]:
            p["status"] = patch["status"]; changed.append("标成已到达" if patch["status"] == "done" else "改回还没到")
        if p:
            edit_milestone(st, m["id"], p)
        return _done(kind, m, changed, patch, reached=p.get("status") == "done")

    # ---- 习惯 ----
    if kind == "habit":
        pool = habits(st, include_archived=action == "restore")
        if action == "restore":
            pool = [h for h in pool if h["archived"]]
        if len(_alike(pool, ref)) > 1:
            return _unclear(_alike(pool, ref))
        h = _pick(pool, ref)
        if not h:
            return {"ok": False, "error": "没找到这个习惯" if pool else "没有收起的习惯", "have": [x["title"] for x in pool]}
        if action == "remove":
            edit_habit(st, h["id"], {"archived": True})
            return _done(kind, h, ["先收起了，打卡记录都在"])
        if action == "restore":
            edit_habit(st, h["id"], {"archived": False})
            st.log("plan", f"把习惯「{h['title']}」找回来了")
            return _done(kind, h, ["找回来了，之前的打卡都在"])
        p = {}
        if patch.get("title") and patch["title"] != h["title"]:
            p["title"] = patch["title"]; changed.append(f"名字改成「{clip(patch['title'], 30)}」")
        freq = patch.get("freq") or ("weekly" if patch.get("per_week") else None)
        if freq in ("daily", "weekly"):
            try:
                pw = max(1, min(6, int(patch.get("per_week") or h.get("per_week") or 3))) if freq == "weekly" else 7
            except (TypeError, ValueError):
                pw = 3
            if freq != h["freq"] or (freq == "weekly" and pw != int(h["per_week"] or 0)):
                p["freq"] = freq; p["per_week"] = pw
                changed.append("改成" + freq_text({"freq": freq, "per_week": pw}))
        if p:
            edit_habit(st, h["id"], p)
            st.log("plan", f"改了习惯「{h['title']}」：" + "，".join(changed))
        return _done(kind, h, changed, patch)

    # ---- 小步 ----
    if kind == "step":
        rows = [dict(r) for r in st.c.execute("SELECT * FROM step WHERE status IN ('todo','dropped') ORDER BY created_at DESC LIMIT 200")]
        if action == "restore":
            rows = [r for r in rows if r["status"] == "dropped"]
        if len(_alike(rows, ref)) > 1:
            return _unclear(_alike(rows, ref))
        s_ = _pick(rows, ref)
        if not s_:
            return {"ok": False, "error": "没找到这一步", "have": [x["title"] for x in rows if x["status"] == "todo"][:8]}
        if action == "remove":
            with st.lock:
                st.c.execute("DELETE FROM step WHERE id=?", (s_["id"],))
            st.log("plan", "删掉了一小步：" + s_["title"])
            return _done(kind, s_, ["删掉了"])
        fields = {}
        if action == "restore":
            fields["status"] = "todo"; changed.append("放回待做")
        if patch.get("title") and patch["title"] != s_["title"]:
            fields["title"] = clip(str(patch["title"]).strip(), 40); changed.append(f"改成「{fields['title']}」")
        if patch.get("status") in ("todo", "dropped") and patch["status"] != s_["status"] and "status" not in fields:
            fields["status"] = patch["status"]; changed.append("先放一放" if patch["status"] == "dropped" else "放回待做")
        if any(patch.get(k) not in (None, "", 0) for k in ("due_day", "due_in_days", "shift_days")):
            # 小步的日期 = 安排到哪天（日历上那一格）；在原来安排的那天上挪，没安排过就从今天算
            day = schedule_day(_when(patch, planned_day(s_) or day_key()))
            if day != (s_.get("scheduled_day") or ""):
                fields["scheduled_day"] = day; fields["rest_from"] = ""
                changed.append(f"安排到 {_md(day)}")
        if fields:
            with st.lock:
                st.c.execute("UPDATE step SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), s_["id"]))
        return _done(kind, s_, changed, patch)

    # ---- 轨迹上的瞬间 ----
    rows = moments(st, limit=300)
    for r in rows:
        r["title"] = r["text"]
    if len(_alike(rows, ref)) > 1:
        return _unclear(_alike(rows, ref))
    m = _pick(rows, ref)
    if not m:
        return {"ok": False, "error": "没找到这条瞬间", "have": [f"{r['day'][5:]} {clip(r['text'], 20)}" for r in rows[:8]]}
    m = {**m, "title": clip(m["text"], 30)}
    if action == "restore":
        return {"ok": False, "error": "删掉的瞬间找不回来了"}
    if action == "remove":
        delete_moment(st, m["id"])
        st.log("journey", "删掉了一个瞬间：" + m["title"])
        return _done(kind, m, ["删掉了"])
    p = {}
    if patch.get("text") and patch["text"] != m["text"]:
        p["text"] = patch["text"]; changed.append("改了内容")
    if patch.get("feeling") and patch["feeling"] != m["feeling"]:
        p["feeling"] = patch["feeling"]; changed.append(f"感受改成「{clip(patch['feeling'], 20)}」")
    if patch.get("day") and str(patch["day"])[:10] != m["day"]:
        p["day"] = patch["day"]; changed.append(f"日期改到 {_md(_valid_day(patch['day']))}")
    if p:
        edit_moment(st, m["id"], p)
    return _done(kind, m, changed, patch)


# ---------------------------------------------------------------- 小步排期 ----
# 小步可以安排到某天（step.scheduled_day），只是给自己的提醒：过了那天也不过期、不算逾期，
# 前端把「安排在过去」的当成还没安排。偷懒日把今天安排的挪到明天，取消偷懒再挪回来。

def schedule_day(day) -> str:
    """校验安排日：空 = 不安排；只能是今天或以后。"""
    if day in (None, ""):
        return ""
    try:
        d = date.fromisoformat(str(day)[:10])
    except ValueError:
        raise ValueError("日期不对")
    if d < now().date():
        raise ValueError("只能安排到今天或以后")
    if d > now().date() + timedelta(days=730):
        raise ValueError("安排得太远了，近两年内选一天吧")
    return d.isoformat()


def planned_day(step: dict, today: str | None = None) -> str:
    """这件小步还算数的安排日：没做、并且安排在今天或以后才算。"""
    d = step.get("scheduled_day") or ""
    return d if d and step.get("status") == "todo" and d >= (today or day_key()) else ""


def plan_label(day: str, today: str | None = None) -> str:
    """安排日的说法：今天 / 明天 / 11月9日周六。"""
    t = date.fromisoformat(today or day_key())
    d = date.fromisoformat(day[:10])
    return "今天" if d == t else "明天" if d == t + timedelta(days=1) else f"{_md(day)}周{'一二三四五六日'[d.weekday()]}"


def todo_by_plan(rows: list[dict], today: str | None = None) -> list[dict]:
    """待做小步排序：安排在今天的 → 之后安排的（按日子）→ 没安排的（保持原来的先后）。"""
    today = today or day_key()
    todo = [r for r in rows if r["status"] == "todo"]
    return sorted(todo, key=lambda r: (0, planned_day(r, today)) if planned_day(r, today) else (1, ""))


def rest_postpone(st) -> int:
    """设偷懒日：今天安排的、还没做的小步挪到明天，记下是从今天挪过去的。返回挪了几件。"""
    today = day_key()
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    with st.lock:
        return st.c.execute("UPDATE step SET scheduled_day=?, rest_from=? WHERE status='todo' AND scheduled_day=?",
                            (tomorrow, today, today)).rowcount


def rest_restore(st) -> int:
    """取消今天的偷懒日：今天挪走、之后没再改过日期的小步挪回今天。返回挪回几件。"""
    today = day_key()
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    with st.lock:
        n = st.c.execute("UPDATE step SET scheduled_day=?, rest_from='' WHERE status='todo' AND rest_from=? AND scheduled_day=?",
                         (today, today, tomorrow)).rowcount
        st.c.execute("UPDATE step SET rest_from='' WHERE rest_from=?", (today,))
    return n


# ---------------------------------------------------------------- 一段小步走完了 ----

def steps_cleared(st, step: dict) -> dict | None:
    """刚完成的这一步是不是这个愿望最后一个待做的小步。是的话返回这个愿望，前端会弹一张「这一段走完了」，
    小光也会问要不要一起想想下一步。没挂愿望的小步算在第一个愿望下（和计划页、面板一致）。"""
    ws = wishes(st)
    if not ws:
        return None
    wid = step.get("wish_id") or ws[0]["id"]
    w = next((x for x in ws if x["id"] == wid), None)
    if not w:
        return None
    mine = "(wish_id=? OR (? = ? AND (wish_id='' OR wish_id IS NULL)))"
    args = (wid, wid, ws[0]["id"])
    if st.c.execute(f"SELECT COUNT(*) FROM step WHERE status='todo' AND {mine}", args).fetchone()[0]:
        return None
    done = st.c.execute(f"SELECT COUNT(*) FROM step WHERE status='done' AND {mine}", args).fetchone()[0]
    return {"wish_id": wid, "title": w["title"], "category": w["category"], "done": done}


# ---------------------------------------------------------------- 打包给前端 ----

def board(st) -> dict:
    cur = current(st)
    ws = wishes(st)
    today = now().date()
    oldest = min([w["started"][:10] for w in ws] + [(today - timedelta(days=90)).isoformat()])
    since = max(oldest, (today - timedelta(days=730)).isoformat())
    hs = habits(st, since=since)
    ms = milestones(st)
    for w in ws:
        w["habits"] = [h for h in hs if h["wish_id"] == w["id"]]
        w["milestones"] = [m for m in ms if m["wish_id"] == w["id"]]
    return {
        "wishes": ws,
        "current": cur["id"] if cur else "",
        "moments": moments(st, since=(today - timedelta(days=730)).isoformat()),   # 瞬间可以不挂愿望：不按愿望的起点截
        "rest_days": [r[0] for r in st.c.execute("SELECT DISTINCT day FROM record WHERE type='rest' AND day>=?", (since,))],
        "insights": {w["id"]: open_insight(st, w["id"]) for w in ws},
        "categories": [{"id": k, "label": v["label"], "vision": v["vision"]} for k, v in CATEGORIES.items()],
        "today": today.isoformat(),
        "week_start": _week_start(today).isoformat(),
    }
