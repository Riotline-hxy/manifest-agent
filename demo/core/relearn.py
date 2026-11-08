"""「让愿望落地」（scene id 沿用 relearn）：看看这周做得怎么样，把卡住的那一件调到做得成。管「做」，不建愿望、不讨论愿望本身。

问题和卡片在前端 public/js/flows.js，跟着 TA 的回答走：
  这周觉得怎么样？（下面先放这周的样子：习惯打卡进度、放着没动的小步、下一个里程碑）
  - 有点卡 / 太满了 / 我自己写 → 是哪一件（先放下哪一件）→ 想怎么调：改小一点 / 换个时间 / 这周先停一停 / 我自己写
  - 顾不上 → 只留一件最想保住的 → 改小一点，其余的习惯这周先停一停
  - 挺顺的 → 再加一点（小光给两个新小步）/ 保持现在就好
  计划还是空的愿望：直接「给它定第一件事」。
每一题都能跳过、都能自己写；小光的建议旁边都有「不用了」。
模型只在 TA 要建议时调（改小一点 / 再加一件 / 第一件事，suggest）；结尾的话是写好的，不调模型。
结尾「这周的打算」列出改了什么，勾了「改到蜕变计划里」才改；换到固定时候的习惯，多一行「每天 HH:MM 提醒我」，默认不勾。
流程本身在 core/flows.py。
"""
from __future__ import annotations

from datetime import date, timedelta

from . import journey, llm, tasks
from .store import Store
from .util import clip, day_key, iso, now

TITLE = "让愿望落地"
LLM_TIMEOUT = 15
MAX_HABITS = 4        # 「这周的样子」最多列几个习惯
MAX_STEPS = 2         # 和几个放着没动的小步

# 习惯：挂在每天都会经过的时刻（执行意图）；小步：哪天做
WHEN_HABIT = [
    {"v": "wake", "label": "起床后", "hint": "08:00 左右", "ill": "sunrise", "time": "08:00"},
    {"v": "lunch", "label": "午饭后", "hint": "13:00 左右", "ill": "bowl", "time": "13:00"},
    {"v": "after", "label": "下课或下班后", "hint": "18:30 左右", "ill": "bag", "time": "18:30"},
    {"v": "bed", "label": "睡前", "hint": "22:00 左右", "ill": "night", "time": "22:00"},
]
WHEN_STEP = [
    {"v": "today", "label": "今天", "hint": "趁现在还记得", "ill": "sunrise"},
    {"v": "tomorrow", "label": "明天", "hint": "给自己留一晚", "ill": "night"},
    {"v": "weekend", "label": "这个周末", "hint": "时间宽一点", "ill": "life"},
]

SMALLER = """你是「{name}」。{tone}
TA 想把计划里的一件事先改小一点，好让它这周做得成。下面是这件事。
给两个更小的版本，每个不超过 16 字，具体到数量或时长，都比原来明显容易，两个要不一样。
两个都必须还是这件事本身：习惯就给更轻的做法（频率另算，别写「每天」「每周几次」），一次性的小步就给做成它的第一下（像「先给 Mia 发条消息问问」）。
只输出 JSON：{{"opts":["",""]}}"""

ADD = """你是「{name}」。{tone}
TA 这周的愿望进行得挺顺，想再加一点。下面是 TA 的愿望和现在的计划。
给两个这周就能做的新小步，每个不超过 16 字，比现在的稍微难一点但做得到，具体到一件事，两个要不一样，也别和现在的计划重复。
只输出 JSON：{{"opts":["",""]}}"""

FIRST = """你是「{name}」。{tone}
TA 刚有了一个愿望，计划还是空的，想先定第一件事。下面是这个愿望。
给两个这周就能做的第一件事，每个不超过 16 字，小到不用下决心，具体到一个动作，两个要不一样。
只输出 JSON：{{"opts":["",""]}}"""

# TA 自己写了一句（「我不知道怎么启动」「最近太忙」）：先听懂卡在哪，再给两个对症的调整，不把原话照搬进计划
ADJUST = """你是「{name}」，TA 的朋友，陪 TA 把愿望一点点做成。{tone}
TA 在「让愿望落地」里说计划里有件事这周不太顺，想调一调，但没选现成的办法，自己说了一句。下面是这件事、这周的情况和 TA 的原话。
先听懂 TA 卡在哪（不知道从哪开始 / 没时间 / 没力气 / 总忘 / 一想就有压力 / 别的），再把这件事调到这周做得成。
1. say：接住 TA 的话，一句，不超过 30 字。说出你听到的卡点，再说打算怎么帮；像朋友，不说教，不复述原话。
2. opts：两个调整，每个是 {{"kind":"","text":""}}，按 TA 说的挑最对症的：
   - kind=small：改成更小、马上能开始的版本。不知道从哪开始时，给做成它的第一下。text 不超过 16 字，具体到动作和数量；习惯别写「每天」「每周几次」。
   - kind=time：挂到每天都会经过的一个时候（起床后 / 午饭后 / 下课或下班后 / 睡前 / 别的具体时候），text 只写那个时候。
   - kind=pause：这周先停一停，text 写「这周先停一停」。只在 TA 明显累了、顾不过来时给。
   两个要不一样。
""" + "不说教，不喊口号，不用「不是……而是……」、破折号，不说「加油」「你一定可以」。" + """
只输出 JSON：{{"say":"","opts":[{{"kind":"","text":""}},{{"kind":"","text":""}}]}}"""

# 「这周觉得怎么样」TA 自己说了一句：听出是哪种，接住，再往下走
FEEL = """你是「{name}」，TA 的朋友，陪 TA 把愿望一点点做成。{tone}
TA 在「让愿望落地」里用自己的话说了这周的感觉。判断最接近哪一种：smooth 挺顺的 / stuck 有一件动不起来 / full 太满了、顾不过来 / none 这周几乎没碰。
say：接住 TA 的话，一句，不超过 24 字，像朋友，不说教，不复述原话；不要提问，下一题会接着问。
只输出 JSON：{{"feel":"","say":""}}"""

FALLBACK = {"smaller_habit": ["先只做两分钟", "先做原来的一半"], "smaller_step": ["先花两分钟开个头", "先把要用的东西准备好"],
            "add": ["比平时多做一点点", "找个人说说这周的进展"], "first": ["花两分钟想想从哪开始", "写下这周想做的一件事"],
            "adjust": [{"kind": "small", "text": "先只做两分钟"}, {"kind": "time", "text": "睡前"}]}
FEELS = ("smooth", "stuck", "full", "none")
ADJUST_KINDS = {"small": "改小一点", "time": "换个时间", "pause": "这周先停一停"}


def _days_ago(ts: str) -> int:
    try:
        return max(0, (now().date() - date.fromisoformat(str(ts)[:10])).days)
    except ValueError:
        return 0


def _items(store: Store, wid: str) -> list[dict]:
    """这周的样子：这个愿望的习惯（本周打卡进度）+ 放得最久、还没做的小步。"""
    out = []
    for h in journey.habits(store, wid)[:MAX_HABITS]:
        out.append({"v": "h:" + h["id"], "kind": "habit", "label": h["title"], "freq": h["freq_text"], "cue": h.get("cue") or "",
                    "hint": f"习惯 · {h['freq_text']} · 本周 {h['week']}/{h['need']}", "prog": round(min(1, h["week"] / h["need"]), 2)})
    for s in store.c.execute("SELECT * FROM step WHERE status='todo' AND wish_id=? ORDER BY created_at LIMIT ?", (wid, MAX_STEPS)):
        n = _days_ago(s["created_at"])
        out.append({"v": "s:" + s["id"], "kind": "step", "label": s["title"],
                    "hint": f"小步 · 放了 {n} 天" if n >= 2 else "小步 · 还没做"})
    return out


def _milestone(store: Store, wid: str) -> dict | None:
    today = day_key()
    for m in journey.milestones(store, wid):
        if m["status"] != "done":
            if m["due_day"] and m["due_day"] >= today:
                return {"title": m["title"], "days": (date.fromisoformat(m["due_day"]) - now().date()).days}
            if not m["due_day"]:
                return {"title": m["title"], "days": None}
    return None


def ctx(store: Store, wish_id: str = "") -> dict:
    ws = journey.wishes(store)
    cur = journey.current(store) if ws else None
    ws.sort(key=lambda w: w["id"] != (cur or {}).get("id"))
    return {"wishes": [{"id": w["id"], "title": w["title"], "items": _items(store, w["id"]), "ms": _milestone(store, w["id"])}
                       for w in ws],
            "pick": wish_id if any(w["id"] == wish_id for w in ws) else "",
            "when": {"habit": WHEN_HABIT, "step": WHEN_STEP}}


# ---------------------------------------------------------------- 小光给建议（TA 要的时候才调） ----

def _raw(store: Store, system: str, user: str) -> dict:
    from .scenes import TONE
    p = store.profile()
    system = system.format(name=p.get("agent_name") or "小光", tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    return llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             timeout=LLM_TIMEOUT, reasoning="none") or {}


def _ask(store: Store, system: str, user: str) -> list[str]:
    out = _raw(store, system, user)
    opts = []
    for x in out.get("opts") or []:
        t = clip(str(x or "").strip().strip("「」").rstrip("。"), 20)
        if t and t not in opts:
            opts.append(t)
    return opts[:2]


def _wish(store: Store, wid: str) -> dict:
    w = journey.get_wish(store, wid)
    if not w or w.get("archived"):
        raise ValueError("这个愿望找不到了")
    return w


def _find(store: Store, wid: str, v: str) -> dict | None:
    return next((it for it in _items(store, wid) if it["v"] == v), None)


def _ease(store: Store, v: str) -> dict | None:
    """习惯还能降一档频率时，多给一个「频率降一档」。"""
    if not v.startswith("h:"):
        return None
    r = store.c.execute("SELECT * FROM habit WHERE id=?", (v[2:],)).fetchone()
    e = journey.ease_habit(dict(r)) if r else None
    return {"freq": e[0], "per_week": e[1], "text": journey.freq_text({"freq": e[0], "per_week": e[1]})} if e else None


def _what(store: Store, wid: str, ref: str, label: str) -> tuple[dict | None, str]:
    it = _find(store, wid, ref) if ref else None
    if it:
        return it, (f"习惯「{it['label']}」（{it['freq']}，{it['hint'].split(' · ')[-1]}）" if it["kind"] == "habit"
                    else f"一次性的小步「{it['label']}」（{it['hint'].split(' · ')[-1]}）")
    label = clip(label.strip(), 30)
    if not label:
        raise ValueError("先说说是哪一件")
    return None, f"一件 TA 自己说的事「{label}」"


def suggest(store: Store, kind: str, wid: str, ref: str = "", label: str = "", text: str = "") -> dict:
    """改小一点（ref 是计划里的一件，或者 TA 自己写的 label）/ 再加一件 / 第一件事：两个建议。
    feel：TA 自己说了这周的感觉（text），听出是哪种、接一句；adjust：TA 自己说了想怎么调 / 卡在哪（text），接一句、给两个对症的调整。
    模型不在就给通用的。"""
    w = _wish(store, wid)
    text = clip((text or "").strip(), 60)
    if kind == "feel":
        out = _raw(store, FEEL, f"愿望：「{w['title']}」\n这周的计划：" + ("；".join(f"{i['label']}（{i['hint']}）" for i in _items(store, wid)) or "（还没有）")
                   + f"\nTA 说：{text}")
        feel = out.get("feel") if out.get("feel") in FEELS else "stuck"
        say = clip(str(out.get("say") or "").strip(), 40) or "嗯，我听到了。我们看看是哪一件。"
        return {"feel": feel, "say": say}
    if kind == "adjust":
        it, what = _what(store, wid, ref, label)
        out = _raw(store, ADJUST, f"愿望：「{w['title']}」\n这件事：{what}\nTA 说：{text or '（没写）'}")
        opts = []
        for x in out.get("opts") or []:
            if not isinstance(x, dict) or x.get("kind") not in ADJUST_KINDS:
                continue
            t = clip(str(x.get("text") or "").strip().strip("「」").rstrip("。"), 20)
            if x["kind"] == "pause":
                t = "这周先停一停"
            if t and all(o["text"] != t for o in opts):
                opts.append({"kind": x["kind"], "text": t})
        say = clip(str(out.get("say") or "").strip(), 44)
        if len(opts) < 2 or not say:
            opts, say = FALLBACK["adjust"], "好，我们把它调到这周做得成。"
        return {"say": say, "opts": opts[:2]}
    if kind == "smaller":
        it, what = _what(store, wid, ref, label)
        opts = _ask(store, SMALLER, f"愿望：「{w['title']}」\n这件事：{what}")
        if len(opts) < 2:
            opts = FALLBACK["smaller_habit" if it and it["kind"] == "habit" else "smaller_step"]
        e = _ease(store, ref) if it else None
        return {"opts": opts, "ease": e["text"] if e else ""}
    if kind == "add":
        plan = "；".join(f"{it['label']}（{it['hint']}）" for it in _items(store, wid)) or "（还没有）"
        done = [r[0] for r in store.c.execute("SELECT title FROM step WHERE wish_id=? AND status='done' ORDER BY done_at DESC LIMIT 3", (wid,))]
        opts = _ask(store, ADD, f"愿望：「{w['title']}」\n现在的计划：{plan}\n最近做完的小步：{'、'.join(done) or '（还没有）'}")
        return {"opts": opts if len(opts) >= 2 else FALLBACK["add"]}
    if kind == "first":
        opts = _ask(store, FIRST, f"愿望：「{w['title']}」\n实现那天的样子：{w.get('vision_text') or '（没写）'}")
        return {"opts": opts if len(opts) >= 2 else FALLBACK["first"]}
    raise ValueError("不认识的建议")


# ---------------------------------------------------------------- 答完：这周的打算 ----

def clean(store: Store, a: dict) -> dict:
    s = lambda k, n=24: clip(str(a.get(k) or "").strip(), n)   # noqa: E731
    w = _wish(store, s("wish", 40))
    out = {"wish": w["id"]}
    for k in ("feel", "which", "how", "small", "when", "more", "add", "first", "adjust"):
        out[k] = s(k, 40)
        out[k + "_label"] = s(k + "_label", 30)
    out["feel_kind"] = a.get("feel_kind") if a.get("feel_kind") in FEELS else ""
    out["adjust_kind"] = a.get("adjust_kind") if a.get("adjust_kind") in ADJUST_KINDS else ""
    # TA 自己说了这周的感觉：按小光听出来的那种走
    if out["feel"] == "custom" and out["feel_kind"]:
        out["feel"] = out["feel_kind"]
    # TA 自己说了想怎么调：按小光给的、TA 选的那个调整走；TA 再自己写一句就当作更小的版本
    if out["how"] == "custom":
        if out["adjust"] == "custom" and out["adjust_label"]:
            out.update(how="small", small="custom", small_label=out["adjust_label"])
        elif out["adjust"] and out["adjust"] != "keep" and out["adjust_kind"] and out["adjust_label"]:
            k, t = out["adjust_kind"], out["adjust_label"]
            if k == "small":
                out.update(how="small", small="custom", small_label=t)
            elif k == "time":
                wh = next((x for x in WHEN_HABIT + WHEN_STEP if x["label"] == t), None)
                out.update(how="time", when=wh["v"] if wh else "custom", when_label=t)
            else:
                out.update(how="pause")
        else:
            out.update(how="", how_label="")
    return out


def _next_monday() -> str:
    d = now().date()
    return (d + timedelta(days=7 - d.weekday())).isoformat()


def _due(when: str) -> str | None:
    """小步「哪天做」：今天 / 明天 / 这个周末（周六；已经是周末就今天）。"""
    d = now().date()
    day = {"today": d, "tomorrow": d + timedelta(days=1), "weekend": d + timedelta(days=max(0, 5 - d.weekday()))}.get(when)
    return day.isoformat() if day else None


def ending(store: Store, a: dict) -> dict:
    """按 TA 走的那条路，算出「这周的打算」：卡片上的几行、真正要改的（ops）、小光写好的一句话。不调模型。"""
    w = _wish(store, a["wish"])
    items = _items(store, w["id"])
    it = next((x for x in items if x["v"] == a["which"]), None)
    if not it and a["which"] == "custom" and a["which_label"]:
        it = {"v": "custom", "kind": "other", "label": a["which_label"]}
    lines, ops, remind, now_step = [], [], None, None
    say = "这周就照这个来。"
    q = lambda t: f"「{t}」"   # noqa: E731

    if a["first"] and a["first"] != "none" and a["first_label"]:
        lines.append(f"第一件事：{q(a['first_label'])}")
        ops.append({"op": "step_add", "title": a["first_label"]})
        now_step = a["first_label"]
        say = "第一件事有了，它就开始了。"
    elif a["feel"] == "smooth":
        if a["more"] == "add" and a["add"] and a["add"] != "none" and a["add_label"]:
            lines.append(f"新的小步：{q(a['add_label'])}")
            ops.append({"op": "step_add", "title": a["add_label"]})
            now_step = a["add_label"]
            say = "顺的时候多走一步，刚刚好。"
        else:
            say = "这周照现在的来，挺好。有变化随时回来调。"
    elif it:
        kind, label = it["kind"], it["label"]
        how = "small" if a["feel"] == "none" else a["how"]
        if how == "pause":
            if kind == "habit":
                lines.append(f"{q(label)}这周先停一停")
                ops.append({"op": "habit_pause", "id": it["v"][2:]})
            elif kind == "step":
                lines.append(f"{q(label)}下周再做")
                ops.append({"op": "step_due", "id": it["v"][2:], "due": _next_monday()})
            else:
                return {"say": "好，这周先放一放，不算放弃。", "card": None, "keeps": [], "acts": [], "ops": []}
            say = "停一停不算退，下周再接上。"
        elif how == "time":
            wh = next((x for x in WHEN_HABIT if x["v"] == a["when"]), None) if kind == "habit" else \
                next((x for x in WHEN_STEP if x["v"] == a["when"]), None)
            text = wh["label"] if wh else a["when_label"]
            if text:
                if kind == "habit":
                    lines.append(f"{q(label)}放到{text}")
                    ops.append({"op": "habit_cue", "id": it["v"][2:], "cue": text})
                    if wh:
                        remind = {"title": clip(f"该{label}了", 30), "time": wh["time"]}
                elif kind == "step":
                    due = _due(a["when"])
                    lines.append(f"{q(label)}放到{text}" if wh else f"{q(label)}：{text}")
                    ops.append({"op": "step_due", "id": it["v"][2:], "due": due} if due else
                               {"op": "step_why", "id": it["v"][2:], "why": f"打算：{text}"})
                    if a["when"] == "today":
                        now_step = label
                else:
                    lines.append(f"{q(label)}放到{text}")
                    ops.append({"op": "step_add", "title": label, "due": _due(a["when"])})
                    if a["when"] in ("today", ""):
                        now_step = label
                say = "有个固定的时候，就不用每天想着了。"
        elif how == "small" and a["small"] and a["small"] != "keep":
            if a["small"] == "ease" and kind == "habit":
                e = _ease(store, it["v"])
                if e:
                    lines.append(f"{q(label)}改成{e['text']}")
                    ops.append({"op": "habit_freq", "id": it["v"][2:], "freq": e["freq"], "per_week": e["per_week"]})
            elif a["small_label"]:
                if kind == "habit":
                    lines.append(f"{q(label)}先改成{q(a['small_label'])}")
                    ops.append({"op": "habit_title", "id": it["v"][2:], "title": a["small_label"]})
                else:
                    lines.append(f"先做：{q(a['small_label'])}（今天）")
                    ops.append({"op": "step_add", "title": a["small_label"]})
                    now_step = a["small_label"]
            if lines:
                say = "小一点，这周就做得成。"
        elif how == "custom" and a["how_label"]:
            lines.append(f"{q(label)}：{a['how_label']}")
            ops.append({"op": "memory", "text": f"想把「{label}」这样调：{a['how_label']}"})
            say = "好，就照你说的来。"
        if a["feel"] == "none":
            rest = [x for x in items if x["kind"] == "habit" and x["v"] != it["v"]]
            if rest:
                lines.append("其余的习惯这周先停一停")
                ops += [{"op": "habit_pause", "id": x["v"][2:]} for x in rest]
            if not lines:
                lines.append(f"这周只保{q(label)}")
            say = "这周只保这一件，够了。"

    if not lines:
        return {"say": say if a["feel"] == "smooth" else "好，这周先不改。想调的时候随时回来。", "card": None, "keeps": [], "acts": [],
                "ops": []}
    only_memory = all(o["op"] == "memory" for o in ops)
    keeps = [{"key": "plan", "html": "记下这个打算" if only_memory else "改到蜕变计划里", "to": "记忆" if only_memory else "蜕变计划"}]
    if remind:
        keeps.append({"key": "remind", "html": f"每天 {remind['time']} 提醒我", "to": "例行任务", "on": False})
    return {"say": say, "card": {"small": "这周的打算", "title": w["title"], "list": lines}, "keeps": keeps,
            "acts": ["save"] + (["now"] if now_step else []), "ops": ops, "remind": remind, "now": now_step or ""}


def save(store: Store, a: dict, end: dict, keys: set) -> dict:
    w = _wish(store, a["wish"])
    wrote, step = [], None
    if "plan" in keys:
        for o in end.get("ops") or []:
            k = o["op"]
            if k == "step_add":
                s = store.add_step(clip(o["title"], 40), why="让愿望落地", wish=w["title"], due_day=o.get("due") or None, wish_id=w["id"])
                step = step or s
            elif k == "step_due":
                with store.lock:
                    store.c.execute("UPDATE step SET due_day=? WHERE id=? AND wish_id=?", (o["due"], o["id"], w["id"]))
                if o["due"] == day_key():
                    step = step or dict(store.c.execute("SELECT * FROM step WHERE id=?", (o["id"],)).fetchone() or {}) or None
            elif k == "step_why":
                with store.lock:
                    store.c.execute("UPDATE step SET why=? WHERE id=? AND wish_id=?", (clip(o["why"], 160), o["id"], w["id"]))
            elif k == "habit_title":
                journey.edit_habit(store, o["id"], {"title": o["title"]})
            elif k == "habit_freq":
                journey.edit_habit(store, o["id"], {"freq": o["freq"], "per_week": o["per_week"]})
            elif k == "habit_cue":
                with store.lock:
                    store.c.execute("UPDATE habit SET cue=? WHERE id=? AND wish_id=?", (clip(o["cue"], 12), o["id"], w["id"]))
            elif k == "habit_pause":
                pause_week(store, o["id"])
            elif k == "memory":
                store.add_memory(clip(o["text"], 120), "insight", "scene:relearn")
        wrote.append({"type": "plan", "label": "这周的打算", "text": "；".join(end["card"]["list"]), "where": "蜕变计划"})
        store.log("plan", f"让愿望落地：{'；'.join(end['card']['list'])}")
    if "remind" in keys and end.get("remind"):
        r = end["remind"]
        tasks.add(store.uid, r["title"], kind="remind", repeat="daily", time=r["time"], source="scene")
        wrote.append({"type": "task", "label": "提醒", "text": f"每天 {r['time']}", "where": "例行任务"})
    reply = "存好了，蜕变计划里已经改好。" if "plan" in keys else ("提醒设好了。" if wrote else "")
    return {"reply": reply, "wrote": wrote, "step": {"id": step["id"], "title": step["title"]} if step else None}


def pause_week(store: Store, hid: str) -> None:
    """这周先停一停：今天到周日都记成「先不做」，不影响进度，下周一自己回来。"""
    d = now().date()
    with store.lock:
        for i in range(7 - d.weekday()):
            store.c.execute("INSERT OR IGNORE INTO habit_skip(habit_id, day, created_at) VALUES(?,?,?)",
                            (hid, (d + timedelta(days=i)).isoformat(), iso()))
    store.log("rest", "有个习惯这周先停一停")
