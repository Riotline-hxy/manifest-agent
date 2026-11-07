"""两分钟启动：把一件想做、却迟迟开始不了的事，拆成几个极小的动作，小光陪着一步一步做。

和聊天是两套提示词：这里只读少量东西——称呼和陪伴偏好、几条和这件事相关的记忆、
以前存下的相关启动经历（最多 2 条）、从蜕变计划进来时那个小步和愿望，以及这一次的任务 / 模式 / 回答 / 路线 / 反馈。

一次启动 = kick_run 里的一行：
  mode     default 默认 | low 低能量 | precise 拆更准（先问三个问题）
  ctx      {step_id, step, why, wish}：从蜕变计划的小步进来时
  answers  拆更准的三问 {now, want, block}；qs 是给这三问生成的快捷选项
  guess    小光对这件事的理解（不显示，让模型先想清楚再拆；TA 在「调整路线」里纠正了就跟着改）
  route    [{title, tip, minutes, state, sec}]，state = todo | done | skipped；sec 是这一步实际用了几秒；cur 是现在这一步
  mark     现在这一步从什么时候开始算
  log      这一次里用户说过的话和小光怎么改的 [{kind, text, say, change, found, step, at}]：step 是改的时候在第几步，
           found 是小光从 TA 这句话里看出来、下次也用得上的一点（结束页「小光发现」）
  status   active | closed
提示词都在 core/kick_prompts.py。
调整路线、遇到困难只改「现在这一步和后面的」，做完的不动；不跳到普通聊天。
结束时用户勾了「让小光记住这次体验」，才写一条《两分钟启动记忆》（kick_memory）：夜里的记忆整理会读它，
聊天里小光用 kick_history 按需查。没勾就不写，这一次的回答、反馈和路线细节也清掉，只留任务和步数。
"""
from __future__ import annotations

import re

from . import llm
from .kick_prompts import (BASE, FALLBACK, FALLBACK_LOW, FALLBACK_SAY, MODE_RULE, QUESTIONS_ASK, REVISE_ASK,
                           REVISE_OUT, ROUTE_ASK)
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
KIND = {"adjust": "调整路线", "stuck": "遇到困难"}
MAX_STEPS = 5
WEEK = "一二三四五六日"
LLM_TIMEOUT = 45


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
                     "status=?, awarded=?, guess=?, mark=?, updated_at=? WHERE id=?",
                     (run["task"], run["mode"], dumps(run["ctx"]), dumps(run["answers"]), dumps(run["qs"]), dumps(run["route"]),
                      dumps(run["first_route"]), run["cur"], dumps(run["log"]), run.get("say") or "", run.get("cheer") or "",
                      run["status"], run.get("awarded") or 0, run.get("guess") or "", run.get("mark") or "", iso(), run["id"]))


def public(run: dict) -> dict:
    """给前端的样子。"""
    route = run["route"]
    return {
        "id": run["id"], "task": run["task"], "mode": run["mode"], "mode_label": MODES.get(run["mode"], ""),
        "ctx": {k: run["ctx"].get(k, "") for k in ("step_id", "step", "wish")},
        "route": route, "cur": run["cur"], "status": run["status"],
        "say": run.get("say") or "", "cheer": run.get("cheer") or "", "guess": run.get("guess") or "",
        "done": sum(1 for s in route if s["state"] == "done"), "total": len(route),
        "finished": bool(route) and run["cur"] >= len(route),
        "questions": [{"key": k, "q": q, "options": run["qs"].get(k) or FALLBACK_OPTS[k]} for k, q in QUESTIONS]
        if run["mode"] == "precise" and not route else [],
        # 调整路线 / 遇到困难：弹层里的来回对话、结束页路线回顾里「在哪一步改过」和「小光发现」都用它
        "log": [{k: x.get(k, "") for k in ("kind", "text", "say", "change", "found", "step")}
                for x in run["log"] if x.get("kind") in ("adjust", "stuck", "more")][-10:],
        "secs": sum(int(s.get("sec") or 0) for s in route),
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
    run.update(status="closed", answers={}, qs={}, log=[], say="", cheer="", guess="", ctx={k: run["ctx"].get(k, "") for k in ("step_id",)},
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
        run["guess"] = _guess(out) or run.get("guess") or ""
    else:   # 模型不在：先给一条通用的路，别让人卡在这里；不假装知道这件事要用什么
        steps, say, cheer = _fallback(run), FALLBACK_SAY, ""
        run["guess"] = ""
    run.update(route=steps, first_route=[dict(s) for s in steps], cur=0, say=say, cheer=cheer, mark=iso())
    _save(st, run)
    return {"run": public(run), "by_model": bool(out and _steps(out.get("steps"), 2))}


def _fallback(run: dict) -> list[dict]:
    rows = ([FALLBACK_LOW] if run["mode"] == "low" else []) + FALLBACK
    return [{"title": t, "tip": tip, "minutes": m, "state": "todo"} for t, tip, m in rows]


def _guess(out: dict | None) -> str:
    return clip(str((out or {}).get("guess") or "").strip().strip("「」。"), 30)


def _tick(run: dict) -> int:
    """现在这一步用了几秒（从 mark 算起），并把 mark 挪到现在。超过 2 小时按 2 小时算（多半是走开了）。"""
    t0 = parse_iso(run.get("mark") or "")
    run["mark"] = iso()
    return int(min(7200, max(0, (now() - t0).total_seconds()))) if t0 else 0


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
    cur["sec"] = _tick(run)
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
    """调整路线 / 遇到困难：带着这一次的全部上下文问模型，只改现在这一步和后面的（TA 说理解错了，就按新理解重排）。"""
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
    run["guess"] = _guess(out) or run.get("guess") or ""
    say = clip(str(out.get("say") or "").strip(), 60) or "好，换成这样。"
    change = f"「{old}」换成了「{steps[0]['title']}」" if steps[0]["title"] != old else f"「{old}」的做法改了"
    found = clip(str(out.get("found") or "").strip().rstrip("。"), 30)
    run["log"].append({"kind": kind, "text": text, "say": say, "change": change, "found": found, "step": run["cur"], "at": iso()})
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
    run["mark"] = iso()
    run["say"] = clip(str(out.get("say") or "").strip(), 60)
    run["log"].append({"kind": "more", "text": "", "say": run["say"], "change": f"接着加了 {len(steps[:4])} 步", "step": run["cur"], "at": iso()})
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
    pins = st.pinned(300)
    if pins:
        lines.append("TA 的基本情况（记住的要点）：" + "；".join(m["text"] for m in pins))
    cur_w = p.get("current_wish") or ""
    wishes = [dict(r) for r in st.c.execute("SELECT id, title FROM wish WHERE archived=0 ORDER BY sort, created_at LIMIT 4")]
    if wishes:
        lines.append("TA 的愿望：" + "、".join(f"「{w['title']}」" + ("（现在主要在做）" if w["id"] == cur_w else "") for w in wishes))
    seen = {m["id"] for m in pins}
    mems = [m["text"] for m in st.search(run["task"], k=4) if m["id"] not in seen][:3]
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
    if run.get("guess"):
        lines.append(f"你对这件事的理解：{run['guess']}")
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
        lines += [f"- {KIND.get(x['kind'], '调整路线')}：「{x['text']}」→ 你说「{x['say']}」，{x['change']}" for x in said[-6:]]
    return "\n".join(lines)


def _ask(st: Store, run: dict, ask: str) -> dict | None:
    p = st.profile()
    system = BASE.format(name=p.get("agent_name") or "小光", tone=TONE.get(p.get("persona") or "gentle", TONE["gentle"]))
    user = f"## 关于 TA\n{_context(st, run)}\n\n## 这一次\n{_state(run)}\n\n## 现在要你做的\n{ask}"
    return llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             timeout=LLM_TIMEOUT, reasoning="none")   # TA 在等：不思考，最快


def _questions(st: Store, run: dict) -> dict:
    out = _ask(st, run, QUESTIONS_ASK) or {}
    run["guess"] = _guess(out)
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
    if run.get("guess"):
        lines.append(f"小光的理解：{run['guess']}")
    if run["first_route"]:
        lines.append("一开始的路线：" + " → ".join(s["title"] for s in run["first_route"]))
    for x in run["log"]:
        if x["kind"] in KIND:
            lines.append(f"{KIND[x['kind']]}：TA 说「{x['text']}」，{x['change']}")
        elif x["kind"] == "skip":
            lines.append(x["change"])
        elif x["kind"] == "more":
            lines.append("做完以后想继续，" + x["change"])
    done = [s["title"] for s in run["route"] if s["state"] == "done"]
    mins = int(sum(int(s.get("sec") or 0) for s in run["route"]) / 60 + 0.5)   # 和页面上的 Math.round 一致
    lines.append(f"实际做了：{'、'.join(done) if done else '还没做完一步'}（{len(done)}/{len(run['route'])} 步"
                 + (f"，用了约 {mins} 分钟" if mins else "") + "）")
    found = [x["found"] for x in run["log"] if x.get("found") and x["kind"] in KIND]   # 和结束页上显示的一样
    if found:   # 小光对 TA 说的是「你」，存进记忆换成「TA」，和别的记忆说法一致
        lines.append("小光的发现：" + "；".join(f.replace("你", "TA") for f in list(dict.fromkeys(found))[-2:]))
    text = "\n".join(lines)
    data = {k: run.get(k) for k in ("answers", "first_route", "route", "log", "ctx", "guess")}
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
