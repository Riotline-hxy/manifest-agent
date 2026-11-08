"""「调整现有计划」（scene id 沿用 relearn）：先简单说说现在的自己，小光按你的状态一键调整现有计划。

和「两分钟启动」一样是一条说得清的流程：
  三个小问题（最近的状态 / 现在能拿出多少劲 / 这阵子的计划做起来怎么样，都能自己写）
  → 把回答 + TA 现在的整份计划（愿望、习惯和本周打卡、没做的小步、里程碑）+ 提示词发给模型（finish）
  → 一份调整方案：一句看到的你 + 0～5 条具体改动（改哪一项、怎么改、为什么）
  → 觉得不对：取消某一条，或者说一句，把意见、上下文、上一版方案发给模型重新调（step: revise）
  → 「一键调整」：勾了的改动写进蜕变计划，看到改了什么；勾了「让小光记住现在的你」才记成一条近况记忆（save）。
模型能做的改动是固定几种，每种都对得上 App 里真的能改的东西；对不上计划里任何一项的改动，不给 TA 看。
问题在前端 public/js/flows.js，流程在 core/flows.py。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from . import journey, llm
from .store import Store
from .util import clip, iso, now

TITLE = "调整现有计划"
LLM_TIMEOUT = 25
MAX_CHANGES = 5
STATE = {"busy": "忙忙碌碌（事情一件接一件）", "steady": "按自己的节奏（和平时差不多）", "change": "正在变化（有些事不一样了）",
         "slow": "想慢下来（有点累了）"}
ENERGY = {"seed": "一点点就好（两分钟就够）", "sprout": "每天一小会（十分钟左右）", "more": "可以多一点（半小时左右）"}
FEEL = {"smooth": "挺顺的（照着做就行）", "stuck": "有点卡（有一件动不起来）", "full": "太满了（顾了这头顾不上那头）",
        "none": "顾不上（这周几乎没碰）"}
KIND = {"habit_small": "改小一点", "habit_freq": "降频率", "habit_cue": "换个时间", "habit_pause": "这周先停",
        "step_small": "先做第一下", "step_move": "换个日子", "ms_delay": "推后一点", "step_add": "加一小步"}
MARK = "最近的状态："

PLAN = """你是「{name}」，TA 的朋友，帮 TA 把现有的计划调到贴着 TA 现在的状态走。{tone}
下面是 TA 刚说的现在的状态，和 TA 现在的整份计划。按 TA 的状态，给一份调整方案：
1. see：一句话说出你看到的现在的 TA，对 TA 说，不超过 34 字，把状态和计划连起来。
2. changes：0～5 条具体改动，每条 {{"kind":"","target":"","to":"","why":""}}：
   kind 只能是：habit_small 习惯改小（to 写新的做法，别写频率）/ habit_freq 习惯降频（to 写「每周 N 次」）/ habit_cue 习惯挂到每天某个时候（to 写那个时候）/
   habit_pause 习惯这周先停 / step_small 小步改成更小的第一下（to 写那一下）/ step_move 小步换个日子（to 写哪天：明天 / 后天 / 这个周末 / 下周一 这样）/
   ms_delay 里程碑推后（to 写推后几天，比如「推后 7 天」）/ step_add 加一个新小步（to 写这一步，只在 TA 状态好、计划做得顺时用）。
   target 写计划里那一项的原名（step_add 写愿望名）。why 不超过 18 字，说为什么这么改。
   每一项最多一条改动（想又改小又降频，就挑更要紧的那个）；习惯只能用 habit_ 开头的，小步只能用 step_ 开头的，里程碑只能用 ms_delay。
   只改需要改的：TA 累、忙、顾不上，就改小、降频、停一停，别加；顺的时候可以不改，或者加一小步。劲头只有一点点时，留下的每件事都要两分钟内做得完。
   计划没什么要改的，changes 给空，see 说一句「照现在的来就好」的意思。计划是空的，就用 step_add 给愿望加 2～3 个很小的开始。
不说教，不喊口号，不用「不是……而是……」、破折号，不说「加油」。
只输出 JSON：{{"see":"","changes":[{{"kind":"","target":"","to":"","why":""}}]}}"""

REVISE = PLAN + """
这是第二轮：TA 看了上一版方案，提了意见。只改 TA 提到的地方，别的保持不变；TA 不想改的项就从 changes 里拿掉。see 换一句接住 TA 的意见。"""

FALLBACK_SEE = "我先按你说的，把计划放轻一点。"


def _days_ago(ts: str) -> int:
    try:
        return max(0, (now().date() - date.fromisoformat(str(ts)[:10])).days)
    except ValueError:
        return 0


def _plan(store: Store) -> list[dict]:
    """TA 现在的整份计划：每个愿望下的习惯（本周进度）、没做的小步、没到的里程碑。"""
    out, today = [], now().date()
    for w in journey.wishes(store):
        items = []
        for h in journey.habits(store, w["id"]):
            items.append({"kind": "habit", "id": h["id"], "title": h["title"],
                          "text": f"习惯「{h['title']}」：{h['freq_text']}" + (f"，{h['cue']}" if h.get("cue") else "")
                          + f"，本周做到 {h['week']}/{h['need']}",
                          "hint": f"习惯 · {h['freq_text']} · 本周 {h['week']}/{h['need']}", "prog": round(min(1, h["week"] / h["need"]), 2)})
        for s in store.c.execute("SELECT * FROM step WHERE status='todo' AND wish_id=? ORDER BY created_at LIMIT 4", (w["id"],)):
            n = _days_ago(s["created_at"])
            items.append({"kind": "step", "id": s["id"], "title": s["title"],
                          "text": f"小步「{s['title']}」：" + (f"放了 {n} 天还没做" if n >= 2 else "还没做"),
                          "hint": f"小步 · 放了 {n} 天" if n >= 2 else "小步 · 还没做"})
        for m in journey.milestones(store, w["id"]):
            if m["status"] == "done":
                continue
            left = (date.fromisoformat(m["due_day"]) - today).days if m["due_day"] else None
            when = "没定日子" if left is None else f"还有 {left} 天" if left >= 0 else f"过了 {-left} 天"
            items.append({"kind": "ms", "id": m["id"], "title": m["title"], "due": m["due_day"],
                          "text": f"里程碑「{m['title']}」：{when}", "hint": f"里程碑 · {when}"})
        out.append({"id": w["id"], "title": w["title"], "items": items})
    return out


def ctx(store: Store, wish_id: str = "") -> dict:
    """给前端：这周的样子（第三题上面放）和三题的选项。"""
    show = lambda it: {k: it[k] for k in ("kind", "title", "hint", "prog") if k in it}   # noqa: E731
    return {"wishes": [{"id": w["id"], "title": w["title"], "items": [show(it) for it in w["items"]]} for w in _plan(store)],
            "state": STATE, "energy": ENERGY, "feel": FEEL}


def clean(store: Store, a: dict) -> dict:
    s = lambda k, n=40: clip(str(a.get(k) or "").strip(), n)   # noqa: E731
    out = {}
    for k, table in (("state", STATE), ("energy", ENERGY), ("feel", FEEL)):
        v = s(k)
        out[k] = table[v] if v in table else s(k + "_label")    # 点的卡片用完整说法；自己写的照原话
    return out


def _plan_text(plan: list[dict]) -> str:
    if not plan:
        return "还没有愿望"
    return "\n".join(f"愿望「{w['title']}」：\n" + ("\n".join("- " + it["text"] for it in w["items"]) or "- 计划还是空的") for w in plan)


def _ask(store: Store, system: str, user: str) -> dict:
    from .scenes import TONE
    p = store.profile()
    system = system.format(name=p.get("agent_name") or "小光", tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    for _ in range(2):
        out = llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                timeout=LLM_TIMEOUT, reasoning="none") or {}
        if out.get("see"):
            return out
    return {}


def _norm(t: str) -> str:
    return re.sub(r"[\s「」『』\"'“”，。,.！!？?、]+", "", t or "").lower()


def _find(plan: list[dict], kind: str, target: str) -> tuple[dict | None, dict | None]:
    """模型写的 target 对上计划里的哪一项（先全等，再互相包含）。step_add 对的是愿望。"""
    t = _norm(target)
    if kind == "step_add":
        hit = next((w for w in plan if _norm(w["title"]) == t), None) or \
            next((w for w in plan if t and (t in _norm(w["title"]) or _norm(w["title"]) in t)), None)
        return (hit or (plan[0] if len(plan) == 1 else None)), None
    if not t:
        return None, None
    want = kind.split("_")[0]
    pool = [(w, it) for w in plan for it in w["items"] if it["kind"] == want]
    hit = next(((w, it) for w, it in pool if _norm(it["title"]) == t), None) or \
        next(((w, it) for w, it in pool if t in _norm(it["title"]) or _norm(it["title"]) in t), None)
    return hit if hit else (None, None)


CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def _per_week(to: str) -> tuple[str, int] | None:
    if "每天" in to:
        return "daily", 7
    m = re.search(r"(\d+)", to) or re.search(r"([一二两三四五六])", to)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else CN[m.group(1)]
    return "weekly", max(1, min(6, n))


def _move_day(to: str) -> str | None:
    d = now().date()
    if "后天" in to:
        return (d + timedelta(days=2)).isoformat()
    if "明天" in to or "明早" in to or "明晚" in to:
        return (d + timedelta(days=1)).isoformat()
    if "今天" in to or "今晚" in to:
        return d.isoformat()
    m = re.search(r"(下)?(?:周|星期|礼拜)([一二三四五六日天])", to)
    if m:
        target = "一二三四五六日天".index(m.group(2))
        target = min(target, 6)
        ahead = (target - d.weekday()) % 7 + (7 if m.group(1) else 0)
        return (d + timedelta(days=ahead or 7)).isoformat()
    if "周末" in to:
        return (d + timedelta(days=max(0, 5 - d.weekday()) + (7 if "下" in to else 0))).isoformat()
    if "下周" in to:
        return (d + timedelta(days=7 - d.weekday())).isoformat()
    return None


def _changes(plan: list[dict], raw) -> list[dict]:
    """模型的改动 → 对得上计划、做得到的改动（同一项只留第一条，最多 5 条）。"""
    out, seen = [], set()
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict) or c.get("kind") not in KIND:
            continue
        kind, to = c["kind"], clip(str(c.get("to") or "").strip().strip("「」").rstrip("。"), 24)
        w, it = _find(plan, kind, str(c.get("target") or ""))
        if not w or (kind != "step_add" and not it) or (kind != "habit_pause" and not to):
            continue
        ref = it["id"] if it else "add:" + _norm(to)
        if ref in seen:
            continue
        op = {"kind": kind, "wish_id": w["id"], "id": it["id"] if it else "", "target": it["title"] if it else w["title"],
              "to": to or "这周先停", "why": clip(str(c.get("why") or "").strip(), 24)}
        if kind == "habit_freq":
            f = _per_week(to)
            if not f:
                continue
            op["freq"], op["per_week"] = f
            op["to"] = "每天" if f[0] == "daily" else f"每周 {f[1]} 次"
        elif kind == "step_move":
            op["due"] = _move_day(to)
        elif kind == "ms_delay":
            m = re.search(r"(\d+)", to)
            if not m or not it.get("due"):
                continue
            op["days"] = max(1, min(60, int(m.group(1))))
            op["to"] = f"推后 {op['days']} 天"
        elif kind == "habit_pause":
            op["to"] = "这周先停"
        seen.add(ref)
        out.append(op)
    return out[:MAX_CHANGES]


def _public(see: str, changes: list[dict], a: dict) -> dict:
    rows = [{"key": f"c{i}", "kind": c["kind"], "label": KIND[c["kind"]], "target": c["target"], "to": c["to"], "why": c["why"]}
            for i, c in enumerate(changes)]
    keeps = list(rows)
    if a["state"] or a["energy"]:
        keeps.append({"key": "remember", "html": f"让小光记住现在的你：{(a['state'] or '（没说）').split('（')[0]}，"
                                                f"劲头{(a['energy'] or '（没说）').split('（')[0]}", "to": "记忆", "on": False})
    return {"say": see, "changes": rows, "keeps": keeps, "card": None, "acts": ["apply"]}


def ending(store: Store, a: dict) -> dict:
    """答完三题：把回答 + 整份计划发给模型，拿一份调整方案。"""
    plan = _plan(store)
    nick = store.profile().get("nickname") or "（没填）"
    out = _ask(store, PLAN, f"TA 的称呼：{nick}\n最近的状态：{a['state'] or '（没说）'}\n现在的劲头：{a['energy'] or '（没说）'}\n"
                            f"这阵子的计划做起来：{a['feel'] or '（没说）'}\n\nTA 现在的计划：\n{_plan_text(plan)}")
    see = clip(str(out.get("see") or "").strip(), 50) or FALLBACK_SEE
    changes = _changes(plan, out.get("changes"))
    return {**_public(see, changes, a), "ops": changes, "by_model": bool(out)}


def revise(store: Store, a: dict, end: dict, text: str) -> dict:
    """TA 说了一句哪里不对：把意见、上下文和上一版方案发给模型，只改提到的地方。"""
    text = clip((text or "").strip(), 60)
    if not text:
        raise ValueError("说一句哪里不对")
    plan = _plan(store)
    nick = store.profile().get("nickname") or "（没填）"
    prev = {"see": end.get("say", ""), "changes": [{k: c[k] for k in ("kind", "target", "to", "why")} for c in end.get("ops") or []]}
    out = _ask(store, REVISE, f"TA 的称呼：{nick}\n最近的状态：{a['state'] or '（没说）'}\n现在的劲头：{a['energy'] or '（没说）'}\n"
                              f"这阵子的计划做起来：{a['feel'] or '（没说）'}\n\nTA 现在的计划：\n{_plan_text(plan)}\n\n"
                              f"上一版方案：{json.dumps(prev, ensure_ascii=False)}\nTA 的意见：{text}")
    if not out:
        raise ValueError("小光没想出来，再说一次试试")
    see = clip(str(out.get("see") or "").strip(), 50) or end.get("say", "")
    changes = _changes(plan, out.get("changes"))
    return {**_public(see, changes, a), "ops": changes, "by_model": True}


def pause_week(store: Store, hid: str) -> None:
    """这周先停一停：今天到周日都记成「先不做」，不影响进度，下周一自己回来。"""
    d = now().date()
    with store.lock:
        for i in range(7 - d.weekday()):
            store.c.execute("INSERT OR IGNORE INTO habit_skip(habit_id, day, created_at) VALUES(?,?,?)",
                            (hid, (d + timedelta(days=i)).isoformat(), iso()))


def _apply(store: Store, c: dict) -> str:
    k, cid = c["kind"], c["id"]
    q = lambda t: f"「{t}」"   # noqa: E731
    if k == "habit_small":
        journey.edit_habit(store, cid, {"title": c["to"]})
        return f"{q(c['target'])}改成{q(c['to'])}"
    if k == "habit_freq":
        journey.edit_habit(store, cid, {"freq": c["freq"], "per_week": c["per_week"]})
        return f"{q(c['target'])}改成{c['to']}"
    if k == "habit_cue":
        with store.lock:
            store.c.execute("UPDATE habit SET cue=? WHERE id=?", (clip(c["to"], 12), cid))
        return f"{q(c['target'])}放到{c['to']}"
    if k == "habit_pause":
        pause_week(store, cid)
        return f"{q(c['target'])}这周先停一停"
    if k == "step_small":
        s = store.add_step(c["to"], why=f"先做「{c['target']}」的第一下", wish_id=c["wish_id"], scheduled_day=now().date().isoformat())
        return f"先做{q(s['title'])}（今天）"
    if k == "step_move":
        with store.lock:
            if c.get("due"):   # 挪到哪天 = 在蜕变计划的日历上安排到那一天
                store.c.execute("UPDATE step SET scheduled_day=?, rest_from='' WHERE id=?", (c["due"], cid))
            else:
                store.c.execute("UPDATE step SET why=? WHERE id=?", (clip(f"打算：{c['to']}", 160), cid))
        return f"{q(c['target'])}挪到{c['to']}"
    if k == "ms_delay":
        r = store.c.execute("SELECT due_day FROM milestone WHERE id=?", (cid,)).fetchone()
        if r and r["due_day"]:
            journey.edit_milestone(store, cid, {"due_day": (date.fromisoformat(r["due_day"]) + timedelta(days=c["days"])).isoformat()})
        return f"{q(c['target'])}推后 {c['days']} 天"
    s = store.add_step(c["to"], why="调整现有计划 · 加一小步", wish_id=c["wish_id"])
    return f"{q(s['title'])}加进了{q(c['target'])}"


def save(store: Store, a: dict, end: dict, keys: set) -> dict:
    """一键调整：只做勾了的改动；勾了「让小光记住现在的你」才记一条近况（再做一次就更新那一条）。"""
    done = []
    for i, c in enumerate(end.get("ops") or []):
        if f"c{i}" in keys:
            try:
                done.append(_apply(store, c))
            except (ValueError, KeyError, TypeError):
                continue
    if done:
        store.log("plan", "调整现有计划：" + "；".join(done))
    wrote = [{"type": "plan", "label": "改好了", "text": t, "where": "蜕变计划"} for t in done]
    if "remember" in keys and (a["state"] or a["energy"]):
        t = now()
        text = (f"{t.month}月{t.day}日说，{MARK}{a['state'] or '（没说）'}；劲头：{a['energy'] or '（没说）'}；"
                f"计划做起来：{a['feel'] or '（没说）'}")
        old = store.c.execute("SELECT id FROM memory WHERE source='scene:relearn' AND status!='archived' AND text LIKE ? "
                              "ORDER BY created_at DESC LIMIT 1", (f"%{MARK}%",)).fetchone()
        if old:
            store.update_memory(old["id"], text=text, status="active", reason="scene:relearn")
        else:
            store.add_memory(text, "event", "scene:relearn")
        wrote.append({"type": "memory", "label": "现在的你", "text": a["state"] or a["energy"], "where": "记忆"})
    reply = ("计划调好了：" + "；".join(done[:3]) + ("……" if len(done) > 3 else "") + "。") if done else ("记下了现在的你。" if wrote else "")
    return {"reply": reply, "wrote": wrote, "done": done, "step": None}
