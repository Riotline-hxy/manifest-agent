"""小光在聊天里做的每个动作，统一成三种样子给界面画（2026-11-07 的展示系统）：

  entry   推荐：一个功能入口（图标 + 名字 + 一句介绍 + 开始），所有功能同一个结构
  slip    回执：气泡下面一行，「动词 + 是哪一项」，有改前改后就写 旧 → 新；能撤销的带撤销
  ask     待确认：小光提议、TA 点了才算（留在轨迹上、提议的计划）；点完原地变成结果

只读的动作（看了看、翻了翻、查说明书、查成长）不出东西。

视图存进那条回复的 meta.acts，重看聊天时还在。撤销不信任前端传来的内容：
只认存在这条消息里的 undo（改动前后的整行数据），而且这一行之后没再被改过才撤。
"""
from __future__ import annotations

import re
from datetime import timedelta

from .journey import _md, freq_text
from .scenes import SCENES
from .util import clip, dumps, loads, now, parse_iso

# 「推荐」能指向的功能。名字、介绍、时长都从这里出，所以每个入口一样。
FEATURES = {
    "meditation": {"title": "冥想体验", "icon": "wind", "color": "var(--c-sky)", "open": {"scene": "meditation"}},
    "gratitude": {"title": "三分钟感恩", "icon": "heart", "color": "var(--c-pink)", "open": {"scene": "gratitude"}},
    "seven_steps_lite": {"title": "聊聊你的愿望", "icon": "steps", "color": "var(--c-orange)", "open": {"scene": "seven_steps_lite"}},
    "relearn": {"title": "聊聊现在的你", "icon": "compass", "color": "var(--c-violet)", "open": {"scene": "relearn"}},
    "kickstart": {"title": "两分钟启动", "icon": "play", "color": "var(--c-mint)", "minutes": 2,
                  "desc": "把开不了头的事拆成一两分钟的小动作，我陪你一步步做", "open": {"kick": True}},
    "plan": {"title": "蜕变计划", "icon": "flag", "color": "var(--c-orange)", "desc": "看看愿望、里程碑和这周的习惯", "open": {"go": "plan"}},
    "report": {"title": "蜕变报告", "icon": "sparkles", "color": "var(--c-violet)", "desc": "这两周、这一个月的变化，都在这里", "open": {"go": "plan"}},
    "goodnews": {"title": "好消息", "icon": "star", "color": "var(--c-lemon)", "desc": "你记下的每件小好事，是夜空里的一颗星", "open": {"go": "goodnews"}},
    "town": {"title": "我的小镇", "icon": "home", "color": "var(--c-mint)", "desc": "用攒下的金币盖点什么", "open": {"go": "town"}},
    "academy": {"title": "心灵学堂", "icon": "book", "color": "var(--c-coral)", "desc": "团队写的小文章，几分钟读完", "open": {"go": "academy"}},
}
for _k, _s in SCENES.items():   # 练习的介绍和时长照点子页
    if _k in FEATURES:
        FEATURES[_k].setdefault("desc", clip(_s.get("desc") or "", 40))
        FEATURES[_k].setdefault("minutes", _s.get("minutes"))

READ_ONLY = {"look_up", "app_guide", "search_memory", "search_chats", "kick_history", "get_growth", "list_tasks"}

# 小光嘴上推荐了一个练习、却忘了调 suggest_feature：照它说的名字补一个入口（说了「试试」就一定有入口）
MENTION = [("两分钟启动", "kickstart"), ("冥想", "meditation"), ("三分钟感恩", "gratitude"), ("感恩练习", "gratitude"),
           ("聊聊你的愿望", "seven_steps_lite"), ("聊聊现在的你", "relearn")]
SUGGEST_CUE = re.compile(r"试试|要不要|可以用|用一下|来个|做个|做一次|陪你做")


def infer_entry(reply: str, done: list[dict]) -> dict | None:
    if any(a.get("type") == "entry" for a in done) or not SUGGEST_CUE.search(reply or ""):
        return None
    for word, feature in MENTION:
        if word in reply:
            return entry(feature)
    return None

# 会改这些表的工具：改之前拍一张，改完对比，就知道改了什么、怎么撤
TABLES = {"complete_step": ["step"], "add_step": ["step"], "add_habit": ["habit"], "adjust_habit": ["habit"],
          "checkin_habit": ["habit_log"], "log_good_news": ["record"], "edit_good_news": ["record"], "log_lazy_day": ["record"]}
PLAN_TABLE = {"wish": "wish", "milestone": "milestone", "habit": "habit", "step": "step", "moment": "moment"}
KIND_NAME = {"wish": "愿望", "milestone": "里程碑", "habit": "习惯", "step": "小步", "moment": "瞬间"}
UNDO_HOURS = 24


def _tables(name: str, args: dict) -> list[str]:
    if name == "edit_plan":
        t = PLAN_TABLE.get(str(args.get("kind") or ""))
        return [t] if t else []
    return TABLES.get(name, [])


def before(st, name: str, args: dict) -> dict:
    return {t: {r["id"]: dict(r) for r in st.c.execute(f"SELECT * FROM {t}")} for t in _tables(name, args)}


def _diff(st, snap: dict) -> list[dict]:
    """改动前后对比出来的每一行：{table, id, before, after}（新加的 before 是 None，删掉的 after 是 None）。"""
    out = []
    for t, old in snap.items():
        new = {r["id"]: dict(r) for r in st.c.execute(f"SELECT * FROM {t}")}
        for i in set(old) | set(new):
            a, b = old.get(i), new.get(i)
            if a != b:
                out.append({"table": t, "id": i, "before": a, "after": b})
    return out


def _title(row: dict | None) -> str:
    row = row or {}
    return clip(row.get("title") or row.get("text") or "", 24)


def _change_text(kind: str, ch: dict) -> tuple[str, str, str]:
    """一行改动 → (动词, 对象, 旧→新 里的 旧, 新)。返回 (verb, old, new)；old 为空就只写 new。"""
    a, b = ch["before"], ch["after"]
    name = KIND_NAME.get(kind, "")
    if a is None:
        return f"新增{name}", "", _title(b)
    if b is None:
        return f"删掉{name}", "", _title(a)
    if a.get("archived") != b.get("archived"):
        return (f"收起{name}" if b.get("archived") else f"找回{name}"), "", _title(b)
    if (a.get("title") or a.get("text")) != (b.get("title") or b.get("text")):
        return name, _title(a), _title(b)
    for k in ("due_day", "target_day"):
        if a.get(k) != b.get(k):
            return f"{name}「{_title(b)}」日期", _md(a[k]) if a.get(k) else "没定", _md(b[k]) if b.get(k) else "没定"
    if (a.get("freq"), a.get("per_week")) != (b.get("freq"), b.get("per_week")):
        return f"习惯「{_title(b)}」", freq_text(a), freq_text(b)
    if a.get("status") != b.get("status"):
        done = b.get("status") in ("done", "reached")
        return (f"到达{name}" if kind == "milestone" and done else f"完成{name}" if done else f"{name}改回没做"), "", _title(b)
    return f"改了{name}", "", _title(b)


def _xp_refs(name: str, result: dict, changes: list[dict]) -> list[str]:
    refs = []
    for ch in changes:
        if ch["before"] is None and ch["table"] == "record":
            refs.append("rec:" + ch["id"])
        if ch["table"] == "habit_log" and ch["before"] is None:
            refs.append(f"habit:{ch['after']['habit_id']}:{ch['after']['day']}")
        if ch["table"] == "step" and (ch["after"] or {}).get("status") == "done" and (ch["before"] or {}).get("status") != "done":
            refs.append("step:" + ch["id"])
        if ch["table"] == "milestone" and (ch["after"] or {}).get("status") in ("done", "reached"):
            refs.append("ms:" + ch["id"])
        if ch["table"] == "moment" and ch["before"] is None:
            refs.append("moment:" + ch["id"])
    return refs


def _slip(icon: str, color: str, verb: str, new: str = "", old: str = "", **kw) -> dict:
    return {"type": "slip", "icon": icon, "color": color, "verb": verb, "old": old, "new": new, **kw}


def entry(feature: str, why: str = "", task: str = "", article: dict | None = None) -> dict | None:
    if article:
        return {"type": "entry", "feature": "article", "title": clip(article.get("title") or "", 20), "icon": "book",
                "color": "var(--c-coral)", "desc": clip(article.get("summary") or why or "团队写的小文章", 40),
                "minutes": article.get("minutes"), "open": {"article": article.get("id")}}
    f = FEATURES.get(feature)
    if not f:
        return None
    return {"type": "entry", "feature": feature, "title": f["title"], "icon": f["icon"], "color": f["color"],
            "desc": f.get("desc") or "", "minutes": f.get("minutes"), "open": {**f["open"], **({"task": task} if task else {})}}


def view(st, name: str, args: dict, result: dict, snap: dict) -> list[dict]:
    """一次工具调用 → 要画的东西（可能是 0 个、1 个，学堂检索可能是几个入口）。"""
    if name in READ_ONLY or not isinstance(result, dict):
        return []
    ok = result.get("ok") is not False
    if result.get("skipped"):
        return []      # 被拦下的（TA 没让改）：小光会在回复里问，不出东西
    if not ok:
        return [_slip("close", "var(--danger)", "没弄成", clip(result.get("error") or "", 40), fail=True)]

    if name == "suggest_feature":
        e = entry(str(args.get("feature") or ""), task=str(args.get("task") or ""))
        return [e] if e else []
    if name == "start_scene":
        e = entry(result.get("scene") or "", task=result.get("task") or "")
        if e:
            e["opened"] = True
        return [e] if e else []
    if name == "knowledge_search":
        return [entry("", article=a) for a in (result.get("articles") or [])[:2]]
    if name == "propose_moment":
        p = result.get("proposal") or {}
        return [{"type": "ask", "ask": "moment", "icon": "sparkles", "color": "var(--c-violet)",
                 "question": f"留在「{p.get('wish_title') or ''}」的轨迹上？", "text": p.get("text") or "",
                 "proposal": p, "wishes": result.get("wishes") or [], "state": ""}]
    if name == "propose_plan":
        return [{"type": "ask", "ask": "plan", "icon": "flag", "color": "var(--c-orange)",
                 "question": f"给「{result.get('wish_title') or ''}」的一套安排，勾掉不想要的",
                 "plan": result.get("plan") or {}, "why": result.get("why") or "", "wish_id": result.get("wish_id"),
                 "wish_title": result.get("wish_title"), "state": ""}]

    gain = result.get("xp") if isinstance(result.get("xp"), dict) else (result if name == "checkin" else None)
    plus = (gain or {}).get("amount") or 0
    extra = {"gain": plus} if plus else {}

    changes = _diff(st, snap) if snap else []
    undo = None
    if changes:
        undo = {"rows": changes, "xp_refs": _xp_refs(name, result, changes), "until": (now() + timedelta(hours=UNDO_HOURS)).isoformat()}

    if name == "edit_plan":
        kind = str(result.get("kind") or args.get("kind") or "")
        if not changes:
            return [_slip("flag", "var(--c-orange)", "改了计划", clip("，".join(result.get("changed") or []), 40), go="plan")]
        verb, old, new = _change_text(kind, changes[0])
        if len(changes) > 1:
            new += f" 等 {len(changes)} 处"
        return [_slip("edit" if old else "flag", "var(--c-orange)", verb, new, old, go="plan", undo=undo, **extra)]
    if name in ("complete_step", "add_step", "add_habit", "adjust_habit"):
        kind = "habit" if "habit" in name else "step"
        if not changes:
            return [_slip("flag", "var(--c-orange)", "计划", _title(result.get("step") or result.get("habit")), go="plan")]
        verb, old, new = _change_text(kind, changes[0])
        if name == "add_habit":
            new += " · " + ((result.get("habit") or {}).get("freq_text") or "")
        return [_slip("check" if name == "complete_step" else "flag", "var(--c-orange)", verb, new, old, go="plan", undo=undo, **extra)]
    if name == "checkin_habit":
        h = result.get("habit") or {}
        note = "今天已经打过了" if result.get("already") else f"本周 {h.get('week')}/{h.get('need')}"
        return [_slip("check", "var(--c-mint)", "打卡", f"{h.get('title') or ''} · {note}", go="plan",
                      undo=undo if changes else None, **extra)]
    if name == "log_good_news":
        r = result.get("record") or {}
        return [_slip("star", "var(--c-lemon)", "记进内心戏" if r.get("type") == "meme" else "记进好消息",
                      clip(r.get("text") or "", 30), go="goodnews", undo=undo, **extra)]
    if name == "edit_good_news":
        if result.get("removed"):
            return [_slip("star", "var(--c-lemon)", "删掉好消息", clip(result.get("text") or "", 30), go="goodnews", undo=undo)]
        ch = changes[0] if changes else None
        old = _title(ch["before"]) if ch else ""
        return [_slip("edit", "var(--c-lemon)", "好消息", clip(result.get("text") or "", 30), old if old != clip(result.get("text") or "", 24) else "",
                      go="goodnews", undo=undo)]
    if name == "log_lazy_day":
        if result.get("undone") or args.get("undo"):
            return [_slip("moon", "var(--c-violet)", "不偷懒了", "习惯和小步都回来了")]
        if result.get("already"):
            return [_slip("moon", "var(--c-violet)", "今天本来就在偷懒", "")]
        return [_slip("moon", "var(--c-violet)", "今天偷个懒", "习惯和小步先暂停，什么都不会少", undo=undo, adjust=True)]
    if name == "schedule_task":
        t = result.get("task") or {}
        return [_slip("clock", "var(--c-sky)", "提醒", f"{t.get('title') or ''} · {t.get('when') or ''}", go="panel", notify=True)]
    if name in ("edit_task", "cancel_task"):
        return [_slip("clock", "var(--c-sky)", "提醒", f"{result.get('task') or ''} · {result.get('done') or '关掉了'}", go="panel")]
    if name == "update_settings":
        return [_slip("compass", "var(--c-sky)", "设置", clip("，".join(result.get("changed") or []), 40), go="space")]
    if name == "remember":
        m = result.get("memory") or {}
        if result.get("updated_from"):
            return [_slip("memory", "var(--c-violet)", "记忆", clip(m.get("text") or "", 30), clip(result["updated_from"], 24), go="space")]
        return [_slip("memory", "var(--c-violet)", "记住了", clip(m.get("text") or "", 30), go="space")]
    if name == "correct_memory":
        if result.get("deleted"):
            return [_slip("memory", "var(--c-violet)", "忘掉了", clip(result.get("old") or "", 30), go="space")]
        return [_slip("memory", "var(--c-violet)", "记忆", clip(result.get("new") or "", 30), clip(result.get("old") or "", 24), go="space")]
    if name == "update_notebook":
        verb = {"add": "笔记本里记下", "replace": "笔记本改成", "remove": "笔记本里删掉"}.get(str(args.get("action") or "add"), "笔记本")
        return [_slip("book", "var(--c-violet)", verb, clip(str(args.get("text") or args.get("old") or ""), 30), go="notebook")]
    if name == "checkin":
        return [_slip("chat", "var(--c-sky)", "今天来聊了", "", **extra)] if plus else []
    return []


# ---- 撤销 ----------------------------------------------------------------------

def undo(st, act: dict) -> dict:
    u = act.get("undo") or {}
    if act.get("state") == "undone":
        return {"ok": False, "error": "已经撤销过了"}
    until = parse_iso(u.get("until") or "")
    if not u.get("rows") or not until or now() > until:
        return {"ok": False, "error": "这一步现在撤不了了，可以去页面里改"}
    for ch in u["rows"]:
        cur = st.c.execute(f"SELECT * FROM {ch['table']} WHERE id=?", (ch["id"],)).fetchone()
        if (dict(cur) if cur else None) != ch["after"]:
            return {"ok": False, "error": "之后又改过了，去页面里改吧"}
    with st.lock:
        for ch in u["rows"]:
            t, b = ch["table"], ch["before"]
            if b is None:
                st.c.execute(f"DELETE FROM {t} WHERE id=?", (ch["id"],))
            else:
                cols = list(b)
                st.c.execute(f"INSERT OR REPLACE INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                             [b[c] for c in cols])
        refs = u.get("xp_refs") or []
        if refs:
            q = ",".join("?" * len(refs))
            st.c.execute(f"DELETE FROM xp WHERE ref IN ({q})", refs)
            got = st.c.execute(f"SELECT COALESCE(SUM(amount), 0) FROM coin WHERE ref IN ({q})", refs).fetchone()[0]
            bal = st.c.execute("SELECT COALESCE(SUM(amount), 0) FROM coin").fetchone()[0]
            if bal - got >= 0:     # 金币已经花掉的话就不往回扣，免得变成负数
                st.c.execute(f"DELETE FROM coin WHERE ref IN ({q})", refs)
    st.log("undo", "撤销了：" + (act.get("verb") or "") + " " + (act.get("new") or ""))
    return {"ok": True}


def set_state(st, msg_id: str, i: int, state: str, do_undo: bool = False) -> dict:
    row = st.c.execute("SELECT meta FROM msg WHERE id=?", (msg_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "没找到这条消息"}
    meta = loads(row["meta"]) or {}
    acts = meta.get("acts") or []
    if not (0 <= i < len(acts)):
        return {"ok": False, "error": "没找到这个动作"}
    if do_undo:
        out = undo(st, acts[i])
        if not out["ok"]:
            return out
        acts[i]["state"] = "undone"
    else:
        if acts[i].get("type") != "ask" or state not in ("kept", "skipped", "added"):
            return {"ok": False, "error": "不能这样改"}
        acts[i]["state"] = state
    meta["acts"] = acts
    with st.lock:
        st.c.execute("UPDATE msg SET meta=? WHERE id=?", (dumps(meta), msg_id))
    return {"ok": True, "act": acts[i]}
