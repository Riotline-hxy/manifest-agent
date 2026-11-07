"""两分钟启动：把一件想做、却迟迟开始不了的事，拆成几个极小的动作，小光陪着一步一步做。

和聊天是两套提示词：这里只读少量东西——称呼和陪伴偏好、几条和这件事相关的记忆、
以前存下的相关启动经历（最多 2 条）、从蜕变计划进来时那个小步和愿望，以及这一次的任务 / 模式 / 回答 / 路线 / 反馈。

一次启动 = kick_run 里的一行：
  mode     default 默认 | low 低能量 | precise 拆更准（先问三个问题）
  ctx      {step_id, step, why, wish}：从蜕变计划的小步进来时
  answers  拆更准的三问 {now, want, block}；qs 是给这三问生成的快捷选项
  route    [{title, tip, minutes, state}]，state = todo | done | skipped；cur 是现在这一步
  log      这一次里用户说过的话和小光怎么改的 [{kind, text, say, change, at}]
  status   active | closed
调整路线、遇到困难只改「现在这一步和后面的」，做完的不动；不跳到普通聊天。
结束时用户勾了「让小光记住这次体验」，才写一条《两分钟启动记忆》（kick_memory）：夜里的记忆整理会读它，
聊天里小光用 kick_history 按需查。没勾就不写，这一次的回答、反馈和路线细节也清掉，只留任务和步数。
"""
from __future__ import annotations

import re

from . import llm
from .scenes import TONE
from .store import Store
from .util import clip, dumps, iso, loads, new_id, now, parse_iso

MODES = {"default": "默认", "low": "低能量", "precise": "拆更准"}
QUESTIONS = [("now", "你现在做到哪了？"), ("want", "你现在最想推进的是什么？"), ("block", "你现在最大的阻碍是什么？")]
SHORT = {"now": "现在做到", "want": "最想推进", "block": "最大的阻碍"}
FALLBACK_OPTS = {
    "now": ["还没开始，刚有这个念头", "开了个头又停下了", "做了一部分", "东西都备好了，还没动"],
    "want": ["先开个头", "先动一下最难的那块", "先做完一小部分", "先理清要做什么"],
    "block": ["提不起劲", "不知道从哪开始", "怕做不好", "总被别的事打断"],
}
CHEERS = ["开头最难的那一下，已经过去了。", "你没有等到想做才开始，这很了不起。", "动起来了，后面会轻一点。"]
MAX_STEPS = 5
WEEK = "一二三四五六日"
LLM_TIMEOUT = 45

BASE = """你是「{name}」，在「两分钟启动」里陪 TA 把一件想做却开始不了的事做起来。{tone}
你做的事：把它拆成几个极小、具体、马上能做的动作，TA 一次只做一个。
- 每个动作 1～3 分钟能做完，身体能直接做：起身、拿起、打开、摆好、写下一句……不写「调整心态」「做好准备」这种空话。
- 第一个动作要小到几乎不用意志力。
- title 不超过 10 个字；tip 一句话、不超过 30 字，说清怎么做，像朋友在旁边轻声提醒；minutes 是 1～3 的整数。
- 只用下面给你的信息，不知道的别假设（不知道 TA 家里有什么，就别写「拿出瑜伽垫」）。
- 不讲道理，不分析拖延，不给 TA 贴标签，不说「加油」「你一定可以」，不用「不是……而是……」和破折号。"""

MODE_RULE = {
    "default": "节奏正常：3～5 个动作，最后一步落到这件事真正开始了（写下第一句、做完第一组、开始第一题）。",
    "low": "TA 现在能量很低：3～4 个动作，每个更小、更温和，可以先让身体动一下（坐起来、喝口水、走到桌前）；"
           "最后一步停在「已经开始了」就好，不要求做完。",
    "precise": "照 TA 回答的三个问题来拆：从 TA 现在做到的地方接着往下，第一个动作冲着 TA 说的最大阻碍去，最后落到 TA 最想推进的那件事。3～5 个动作。",
}

ROUTE_ASK = """把下面这件事拆成路线。{mode_rule}
只输出 JSON：{{"say":"开始前对 TA 说的一句话，不超过 25 字，可以空","steps":[{{"title":"","tip":"","minutes":1}}],"cheer":"TA 做完以后的一句鼓励，不超过 20 字，具体到这件事"}}"""

QUESTIONS_ASK = """TA 选了「拆更准」，要先回答三个问题：1. 你现在做到哪了？ 2. 你现在最想推进的是什么？ 3. 你现在最大的阻碍是什么？
给每个问题写 4 个快捷选项：贴着这件事、像 TA 可能的真实状态，口语，每个不超过 12 个字。
只输出 JSON：{"now":["","","",""],"want":["","","",""],"block":["","","",""]}"""

REVISE_ASK = {
    "adjust": "TA 想调整路线，原话：「{text}」。按 TA 说的改「现在这一步」和后面的步骤，做完的不动。",
    "stuck": "TA 在「现在这一步」卡住了，原话：「{text}」。先用一句话接住 TA（不说教），再把现在这一步换成更小的版本或换个做法，"
             "实在不合适就换成别的动作，让 TA 能接着走；后面的步骤需要时一起调。",
    "more": "TA 把这几步都做完了，想继续做这件事。接着刚才的进度，再给 2～4 个动作，可以比开头稍大一点，但还是马上能做的。",
}
REVISE_OUT = """只输出 JSON：{"say":"回 TA 的一句话，不超过 40 字","steps":[{"title":"","tip":"","minutes":1}]}
steps 是从「现在这一步」开始的新路线（继续时是接在后面的新动作），1～5 个。"""


# ---------------------------------------------------------------- 读写 ----

def _row(st: Store, rid: str) -> dict | None:
    r = st.c.execute("SELECT * FROM kick_run WHERE id=?", (rid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k, empty in (("ctx", {}), ("answers", {}), ("qs", {}), ("route", []), ("first_route", []), ("log", [])):
        d[k] = loads(d.get(k) or "", empty) or empty
    return d


def _get(st: Store, rid: str, active: bool = True) -> dict:
    run = _row(st, rid)
    if not run or (active and run["status"] != "active"):
        raise KeyError(rid)
    return run


def _save(st: Store, run: dict) -> None:
    with st.lock:
        st.c.execute("UPDATE kick_run SET task=?, mode=?, ctx=?, answers=?, qs=?, route=?, first_route=?, cur=?, log=?, say=?, cheer=?, "
                     "status=?, awarded=?, updated_at=? WHERE id=?",
                     (run["task"], run["mode"], dumps(run["ctx"]), dumps(run["answers"]), dumps(run["qs"]), dumps(run["route"]),
                      dumps(run["first_route"]), run["cur"], dumps(run["log"]), run.get("say") or "", run.get("cheer") or "",
                      run["status"], run.get("awarded") or 0, iso(), run["id"]))


def public(run: dict) -> dict:
    """给前端的样子。"""
    route = run["route"]
    return {
        "id": run["id"], "task": run["task"], "mode": run["mode"], "mode_label": MODES.get(run["mode"], ""),
        "ctx": {k: run["ctx"].get(k, "") for k in ("step_id", "step", "wish")},
        "route": route, "cur": run["cur"], "status": run["status"],
        "say": run.get("say") or "", "cheer": run.get("cheer") or "",
        "done": sum(1 for s in route if s["state"] == "done"), "total": len(route),
        "finished": bool(route) and run["cur"] >= len(route),
        "questions": [{"key": k, "q": q, "options": run["qs"].get(k) or FALLBACK_OPTS[k]} for k, q in QUESTIONS]
        if run["mode"] == "precise" and not route else [],
        "log": [{k: x.get(k, "") for k in ("kind", "text", "say")} for x in run["log"] if x.get("kind") in ("adjust", "stuck")][-6:],
    }


def home(st: Store) -> dict:
    """打开两分钟启动：有没做完的那一次（6 小时内）就让用户接着做。"""
    act = st.c.execute("SELECT id, updated_at FROM kick_run WHERE status='active' ORDER BY updated_at DESC LIMIT 1").fetchone()
    active = None
    if act:
        t = parse_iso(act["updated_at"])
        run = _row(st, act["id"])
        if t and (now() - t).total_seconds() < 6 * 3600 and run["route"]:
            active = public(run)
    return {"active": active}


def _close_others(st: Store) -> None:
    for r in st.c.execute("SELECT id FROM kick_run WHERE status='active'").fetchall():
        run = _row(st, r["id"])
        _wipe(run)
        _save(st, run)


def _wipe(run: dict) -> None:
    """没让小光记住：这一次的回答、反馈和路线细节都不留，只留任务、模式和走了几步。"""
    done = sum(1 for s in run["route"] if s["state"] == "done")
    run.update(status="closed", answers={}, qs={}, log=[], say="", cheer="", ctx={k: run["ctx"].get(k, "") for k in ("step_id",)},
               route=[{"title": "", "tip": "", "minutes": 0, "state": "done"}] * done, first_route=[], cur=done)


# ---------------------------------------------------------------- 开始 ----

def start(st: Store, task: str, mode: str = "default", step_id: str = "") -> dict:
    task = clip(re.sub(r"\s+", " ", task or "").strip(), 40)
    if not task:
        raise ValueError("先写一件想做的事")
    mode = mode if mode in MODES else "default"
    ctx = {}
    if step_id:
        s = st.c.execute("SELECT id, title, why, wish_id FROM step WHERE id=?", (step_id,)).fetchone()
        if s:
            w = st.c.execute("SELECT title FROM wish WHERE id=?", (s["wish_id"] or "",)).fetchone()
            ctx = {"step_id": s["id"], "step": s["title"], "why": s["why"] or "", "wish": w["title"] if w else ""}
    _close_others(st)
    rid = new_id("k")
    with st.lock:
        st.c.execute("INSERT INTO kick_run(id, task, mode, ctx, answers, qs, route, first_route, cur, log, status, created_at, updated_at) "
                     "VALUES(?,?,?,?,'{}','{}','[]','[]',0,'[]','active',?,?)", (rid, task, mode, dumps(ctx), iso(), iso()))
    st.log("kick", f"两分钟启动：{task}")
    run = _row(st, rid)
    if mode == "precise":
        run["qs"] = _questions(st, run)
        _save(st, run)
        return {"run": public(run)}
    return _plan(st, run)


def answer(st: Store, rid: str, answers: dict) -> dict:
    run = _get(st, rid)
    run["answers"] = {k: clip(str(answers.get(k) or "").strip(), 40) for k, _ in QUESTIONS if str(answers.get(k) or "").strip()}
    return _plan(st, run)


def _plan(st: Store, run: dict) -> dict:
    out = _ask(st, run, ROUTE_ASK.format(mode_rule=MODE_RULE[run["mode"]]))
    steps = _steps((out or {}).get("steps"), 2)
    if steps:
        say, cheer = clip(str(out.get("say") or "").strip(), 40), clip(str(out.get("cheer") or "").strip(), 30)
    else:   # 模型不在：先给一条最朴素的路，别让人卡在这里
        steps, say, cheer = _fallback(run), "我这会儿有点慢，先按最简单的来。", ""
    run.update(route=steps, first_route=[dict(s) for s in steps], cur=0, say=say, cheer=cheer)
    _save(st, run)
    return {"run": public(run), "by_model": bool(out and _steps(out.get("steps"), 2))}


def _fallback(run: dict) -> list[dict]:
    rows = [("把要用的东西拿出来", f"做「{clip(run['task'], 12)}」要用的东西，先拿一样放到手边。", 1),
            ("只做最小的一下", "就做一分钟，做一点点也算。", 2),
            ("停一下，看看感觉", "做完停一停。想继续，就点「继续做这件事」。", 1)]
    if run["mode"] == "low":
        rows.insert(0, ("先让身体动一下", "坐直一点，或者站起来伸个懒腰。", 1))
    return [{"title": t, "tip": tip, "minutes": m, "state": "todo"} for t, tip, m in rows]


# ---------------------------------------------------------------- 执行中 ----

def _next(run: dict) -> int:
    return next((i for i, s in enumerate(run["route"]) if s["state"] == "todo"), len(run["route"]))


def advance(st: Store, rid: str, how: str = "done") -> dict:
    """完成这一步 / 先跳过这一步（跳过不用问模型）。全部走完那一下，算做了一次练习。"""
    from . import growth
    run = _get(st, rid)
    if run["cur"] >= len(run["route"]):
        return {"run": public(run)}
    cur = run["route"][run["cur"]]
    cur["state"] = "done" if how == "done" else "skipped"
    if how != "done":
        run["log"].append({"kind": "skip", "text": "", "say": "", "change": f"跳过了「{cur['title']}」", "at": iso()})
    run["cur"] = _next(run)
    run["say"] = ""
    out = {}
    if run["cur"] >= len(run["route"]) and not run.get("awarded") and any(s["state"] == "done" for s in run["route"]):
        run["awarded"] = 1
        out["xp"] = growth.award(st, "practice", ref="kick:" + run["id"], note="两分钟启动：" + run["task"])
    _save(st, run)
    return {"run": public(run), **out}


def feedback(st: Store, rid: str, kind: str, text: str) -> dict:
    """调整路线 / 遇到困难：带着这一次的全部上下文问模型，只改现在这一步和后面的。"""
    run = _get(st, rid)
    text = clip((text or "").strip(), 120)
    if not text:
        raise ValueError("说一句哪里不合适")
    if run["cur"] >= len(run["route"]):
        raise ValueError("这几步都做完了")
    out = _ask(st, run, REVISE_ASK[kind].format(text=text) + "\n" + REVISE_OUT)
    steps = _steps((out or {}).get("steps"), 1)
    if not steps:
        raise ValueError("刚才没想好，换个说法再试一次？")
    old = run["route"][run["cur"]]["title"]
    run["route"] = run["route"][:run["cur"]] + steps[:MAX_STEPS]
    say = clip(str(out.get("say") or "").strip(), 60) or "好，换成这样。"
    change = f"「{old}」换成了「{steps[0]['title']}」" if steps[0]["title"] != old else f"「{old}」的做法改了"
    run["log"].append({"kind": kind, "text": text, "say": say, "change": change, "at": iso()})
    run["say"] = say
    _save(st, run)
    return {"run": public(run), "say": say}


def more(st: Store, rid: str) -> dict:
    """「继续做这件事」：接着刚才的进度再给几步，同一次会话。"""
    run = _get(st, rid)
    out = _ask(st, run, REVISE_ASK["more"] + "\n" + REVISE_OUT)
    steps = _steps((out or {}).get("steps"), 1)
    if not steps:
        raise ValueError("刚才没想好，再点一次试试？")
    run["route"] = run["route"] + steps[:4]
    run["cur"] = _next(run)
    run["say"] = clip(str(out.get("say") or "").strip(), 60)
    run["log"].append({"kind": "more", "text": "", "say": run["say"], "change": f"接着加了 {len(steps[:4])} 步", "at": iso()})
    _save(st, run)
    return {"run": public(run)}


def finish(st: Store, rid: str, remember: bool = False) -> dict:
    run = _get(st, rid)
    saved = None
    if remember:
        saved = _remember(st, run)
        run["status"] = "closed"
    else:
        _wipe(run)
    _save(st, run)
    done = sum(1 for s in run["route"] if s["state"] == "done")
    st.log("kick", f"两分钟启动做了 {done} 步：{run['task']}" + ("，让小光记住了" if saved else ""))
    return {"ok": True, "saved": bool(saved)}


def close(st: Store, rid: str) -> dict:
    """中途关掉：和不勾「记住」一样，什么都不留。"""
    run = _row(st, rid)
    if run and run["status"] == "active":
        _wipe(run)
        _save(st, run)
    return {"ok": True}


# ---------------------------------------------------------------- 问模型 ----

def _context(st: Store, run: dict) -> str:
    p = st.profile()
    t = now()
    lines = [f"现在：{t:%m月%d日 %H:%M}（周{WEEK[t.weekday()]}）"]
    if p.get("nickname"):
        lines.append(f"TA 的称呼：{p['nickname']}")
    if p.get("energy_time"):
        lines.append(f"TA 一天里比较有精神的时候：{p['energy_time']}")
    if p.get("chat_style"):
        lines.append(f"TA 希望你怎么陪：{p['chat_style']}")
    mems = [m["text"] for m in st.search(run["task"], k=3)]
    if mems:
        lines.append("可能和这件事有关的记忆：" + "；".join(mems))
    past = history(st, run["task"], k=2)
    if past:
        lines.append("TA 以前存下的启动经历（看看哪些动作对 TA 有用、卡在哪）：\n" + "\n".join(e["text"] for e in past))
    c = run["ctx"]
    if c.get("step"):
        lines.append(f"这件事来自蜕变计划：愿望「{c.get('wish') or '（没挂愿望）'}」下的小步「{c['step']}」" + (f"，当时写的原因：{c['why']}" if c.get("why") else ""))
    return "\n".join(lines)


def _state(run: dict) -> str:
    lines = [f"想做的事：{run['task']}", f"模式：{MODES[run['mode']]}"]
    a = run["answers"]
    if a:
        lines.append("TA 回答的三个问题：" + "；".join(f"{q}{a[k]}" for k, q in QUESTIONS if a.get(k)))
    if run["route"]:
        lines.append("现在的路线（✓ 做完了，→ 现在这一步，· 还没做，跳 = 跳过了）：")
        for i, s in enumerate(run["route"]):
            mark = "✓" if s["state"] == "done" else "跳" if s["state"] == "skipped" else "→" if i == run["cur"] else "·"
            lines.append(f"{i + 1}. {mark} {s['title']}：{s['tip']}")
    said = [x for x in run["log"] if x.get("text")]
    if said:
        lines.append("这一次里 TA 说过的话和你的调整：")
        lines += [f"- {'调整路线' if x['kind'] == 'adjust' else '遇到困难'}：「{x['text']}」→ 你说「{x['say']}」，{x['change']}" for x in said[-6:]]
    return "\n".join(lines)


def _ask(st: Store, run: dict, ask: str) -> dict | None:
    p = st.profile()
    system = BASE.format(name=p.get("agent_name") or "小光", tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    user = f"## 关于 TA\n{_context(st, run)}\n\n## 这一次\n{_state(run)}\n\n## 现在要你做的\n{ask}"
    return llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             timeout=LLM_TIMEOUT, reasoning="none")   # TA 在等：不思考，最快


def _questions(st: Store, run: dict) -> dict:
    out = _ask(st, run, QUESTIONS_ASK) or {}
    qs = {}
    for k, _ in QUESTIONS:
        opts = [clip(str(x).strip(), 14) for x in (out.get(k) or []) if isinstance(x, str) and str(x).strip()][:4]
        qs[k] = opts if len(opts) >= 2 else FALLBACK_OPTS[k]
    return qs


def _steps(raw, at_least: int) -> list[dict]:
    out = []
    for s in (raw if isinstance(raw, list) else [])[:MAX_STEPS]:
        if not isinstance(s, dict) or not str(s.get("title") or "").strip():
            continue
        try:
            m = max(1, min(5, int(s.get("minutes") or 1)))
        except (TypeError, ValueError):
            m = 1
        out.append({"title": clip(str(s["title"]).strip().rstrip("。"), 14), "tip": clip(str(s.get("tip") or "").strip(), 50),
                    "minutes": m, "state": "todo"})
    return out if len(out) >= at_least else []


# ---------------------------------------------------------------- 《两分钟启动记忆》 ----

def _remember(st: Store, run: dict) -> dict:
    t = parse_iso(run["created_at"]) or now()
    label = MODES[run["mode"]]
    lines = [f"{t.month}月{t.day}日 {t:%H:%M}｜{run['task']}（{label}）"]
    c = run["ctx"]
    if c.get("step"):
        lines.append(f"来自蜕变计划：{('「' + c['wish'] + '」的') if c.get('wish') else ''}小步「{c['step']}」")
    a = run["answers"]
    if a:
        lines.append("状态：" + "；".join(f"{SHORT[k]}：{a[k]}" for k, _ in QUESTIONS if a.get(k)))
    if run["first_route"]:
        lines.append("一开始的路线：" + " → ".join(s["title"] for s in run["first_route"]))
    for x in run["log"]:
        if x["kind"] in ("adjust", "stuck"):
            lines.append(f"{'调整路线' if x['kind'] == 'adjust' else '遇到困难'}：TA 说「{x['text']}」，{x['change']}")
        elif x["kind"] == "skip":
            lines.append(x["change"])
        elif x["kind"] == "more":
            lines.append("做完以后想继续，" + x["change"])
    done = [s["title"] for s in run["route"] if s["state"] == "done"]
    lines.append(f"实际做了：{'、'.join(done) if done else '还没做完一步'}（{len(done)}/{len(run['route'])} 步）")
    text = "\n".join(lines)
    data = {k: run[k] for k in ("answers", "first_route", "route", "log", "ctx")}
    mid = new_id("km")
    with st.lock:
        st.c.execute("INSERT INTO kick_memory(id, run_id, day, task, mode, text, data, created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (mid, run["id"], t.date().isoformat(), run["task"], run["mode"], text, dumps(data), iso()))
    return {"id": mid, "text": text}


def entries(st: Store, limit: int = 30) -> list[dict]:
    return [dict(r) for r in st.c.execute("SELECT id, day, task, mode, text, created_at FROM kick_memory ORDER BY created_at DESC LIMIT ?", (limit,))]


def on_day(st: Store, day: str) -> list[dict]:
    """夜里整理用：这一天存下的启动经历，连同 TA 在里面说过的原话（改受保护记忆时要拿原话当依据）。"""
    out = []
    for r in st.c.execute("SELECT text, data FROM kick_memory WHERE day=? ORDER BY created_at", (day,)):
        d = loads(r["data"] or "", {}) or {}
        said = [x.get("text") for x in d.get("log", []) if x.get("text")] + list((d.get("answers") or {}).values())
        out.append({"text": r["text"], "said": [s for s in said if s]})
    return out


def history(st: Store, query: str = "", k: int = 4) -> list[dict]:
    """按关键词找存下的启动经历（中文按两个字一组打分）；没给关键词就是最近几次。"""
    rows = [dict(r) for r in st.c.execute("SELECT id, day, task, text, created_at FROM kick_memory ORDER BY created_at DESC LIMIT 200")]
    q = re.sub(r"[\s，。,.!?！？、；;：:「」]+", "", query or "")
    if not q:
        return rows[:k]
    grams = {q[i:i + 2] for i in range(len(q) - 1)} or {q}
    scored = [(sum(g in (r["task"] + r["text"]) for g in grams) + (3 if q in r["task"] else 0), r) for r in rows]
    return [r for s, r in sorted(scored, key=lambda z: -z[0]) if s > 0][:k]


def forget(st: Store, mid: str) -> dict:
    with st.lock:
        n = st.c.execute("DELETE FROM kick_memory WHERE id=?", (mid,)).rowcount
    if not n:
        raise KeyError(mid)
    st.log("memory", "删掉了一条两分钟启动记忆")
    return {"ok": True}
