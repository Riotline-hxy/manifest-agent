"""首页的「先体验一下」：不建账号的两分钟引导式体验。

选一件想改变的事 → 和小光聊最多 3 轮 → 得到今天的一小步 → 看它记住了什么、
明天会来问什么。对话历史由前端带着，服务端不存任何东西；注册时前端把结果
（一小步、记住的话）交给 /api/onboard 的 carry，写进新账号。

模型不可用时退回到写好的回应，保证体验不断。
"""
from __future__ import annotations

import re

from . import llm, metrics
from .util import clip

MAX_ROUNDS = 3

PROMPT = """你是「小光」，一个会记住人、陪人一点点改变的朋友。现在有个新朋友第一次来试试你，只聊三句左右。

TA 想改变的事：「{goal}」

像微信聊天那样：
- 先接住 TA 说的：听出情绪，用自己的话说出来（「刷到一两点，第二天肯定很难受吧」），再好奇地问一个问题，弄清楚卡在哪。
- 一次 1–3 句，口语，不说教、不鸡血、不用列表和加粗，别像客服。
- 只用 TA 真说过的内容，别替 TA 编经历。
- 大致弄明白之后（最晚第 {max} 轮），给 TA 一个今天就能做的一小步：5–10 分钟能开始，具体到时间或场景，比如「今晚 11 点把手机放到书桌上再上床」。不要「坚持」「每天」这种大词。给出时在 reply 里自然地说出来，问 TA 这样行不行。

现在是第 {n} 轮。{extra}

只输出一个 JSON 对象：
{{"reply": "你这一轮说的话",
  "step": null 或 {{"title": "一小步，20 字内", "when": "什么时候做，8 字内", "why": "用大白话说为什么先做这个，25 字内"}},
  "remember": ["给出 step 时填：从 TA 原话里值得记住的 1–3 件事，每条 16 字内，以「你」开头"],
  "tomorrow": "给出 step 时填：明天你发给 TA 的那句话原文，24 字内，比如「昨晚手机放到书桌上了吗？睡得怎么样？」，不要写「明天我会问你」这类前缀",
  "why_goal": "TA 想改变的原因，只写原因本身，比如「白天上课总犯困」；TA 没说过就留空"}}"""

# 模型不可用时的退路：按关键词挑一套，回应仍然围绕 TA 选的事
FALLBACK = [
    (("睡", "作息", "熬夜", "早起"), {
        "ask": ["嗯，晚上那会儿通常在做什么？是停不下来刷手机，还是躺下了也睡不着？", "懂了。那我们不一下子改太多，先从今晚动一点点。"],
        "step": {"title": "今晚 11 点把手机放到书桌上", "when": "今晚 11 点", "why": "先把最容易拖住你的那件东西挪远一点"},
        "remember": ["你想早点睡"], "tomorrow": "昨晚手机放到书桌上了吗？睡得怎么样？"}),
    (("开口", "表达", "自信", "说话", "社交"), {
        "ask": ["最近有没有哪个场合，你其实想说点什么，最后没说出口？", "嗯，那种话到嘴边又咽回去的感觉，我懂。我们先挑个最不吓人的。"],
        "step": {"title": "今天主动跟一个人说一句话", "when": "今天任意时候", "why": "不用说得好，先让「开口」这件事变得普通一点"},
        "remember": ["你想更敢开口"], "tomorrow": "昨天那句话说出口了吗？对方什么反应？"}),
    (("拖", "作业", "论文", "项目", "学习", "做完"), {
        "ask": ["现在最卡的是哪一件？是不知道从哪下手，还是一打开就想逃？", "嗯，越拖越重的感觉挺磨人的。我们先别想做完，只想怎么开个头。"],
        "step": {"title": "把那件事打开，只做 10 分钟", "when": "今天晚饭前", "why": "开头最难，10 分钟够让它不再那么吓人"},
        "remember": ["你有件拖着的事想做完"], "tomorrow": "昨天那 10 分钟开了头吗？感觉怎么样？"}),
]
DEFAULT_FALLBACK = {
    "ask": ["嗯，说说现在大概是什么样子？卡在哪儿都行。", "好，我大概明白了。我们先不贪多，挑一件今天能动的。"],
    "step": {"title": "今天花 5 分钟写下你想要的样子", "when": "今晚睡前", "why": "先说清楚想去哪，路才会近一点"},
    "remember": [], "tomorrow": "昨晚那 5 分钟写了吗？写了些什么？"}


def _fallback(goal: str, n: int, want_step: bool) -> dict:
    fb = next((f for keys, f in FALLBACK if any(k in goal for k in keys)), DEFAULT_FALLBACK)
    if not want_step and n < 2:
        return {"reply": fb["ask"][0], "step": None}
    return {"reply": fb["ask"][-1] + f"今天就先做一件事：{fb['step']['title']}。这样行吗？",
            "step": dict(fb["step"]), "remember": list(fb["remember"]) or [clip("你想" + goal, 16)],
            "tomorrow": fb["tomorrow"], "why_goal": ""}


def _clean_history(history) -> list[dict]:
    out = []
    for m in (history or [])[-2 * MAX_ROUNDS:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        text = clip(str(m.get("content") or ""), 300).strip()
        if text:
            out.append({"role": m["role"], "content": text})
    return out


def chat(goal: str, history, finish: bool = False, smaller: bool = False) -> dict:
    goal = clip(str(goal or ""), 40).strip()
    if not goal:
        raise ValueError("先说说想改变什么")
    msgs = _clean_history(history)
    n = sum(1 for m in msgs if m["role"] == "user")
    if n == 0 or msgs[-1]["role"] != "user":
        raise ValueError("说点什么吧")
    want_step = finish or smaller or n >= MAX_ROUNDS
    extra = ("TA 觉得上一步还是有点难，换一个更小、更容易开始的，reply 里轻轻接住这一点。" if smaller
             else "这一轮必须给出 step。" if want_step
             else "如果 TA 已经说得很清楚，这一轮就可以给 step；否则先问。")
    sys_msg = PROMPT.format(goal=goal, max=MAX_ROUNDS, n=n, extra=extra)
    if n == 1:
        metrics.bump("trial_start")
    out = llm.complete_json([{"role": "system", "content": sys_msg}, *msgs], timeout=30)
    if not out or not str(out.get("reply") or "").strip() or (want_step and not isinstance(out.get("step"), dict)):
        metrics.bump("trial_fallback")
        out = _fallback(goal, n, want_step)
    step = out.get("step") if isinstance(out.get("step"), dict) else None
    if step and not str(step.get("title") or "").strip():
        step = None
    res = {"reply": clip(str(out["reply"]).strip(), 300), "step": None, "round": n, "max": MAX_ROUNDS}
    if step:
        if not smaller:
            metrics.bump("trial_step")
        res["step"] = {"title": clip(str(step.get("title")).strip(), 30), "when": clip(str(step.get("when") or "今天"), 12),
                       "why": clip(str(step.get("why") or ""), 50)}
        res["remember"] = [clip(str(x).strip(), 20) for x in (out.get("remember") or []) if str(x).strip()][:3]
        tomorrow = re.sub(r"^(明天)?(我)?(会)?(来)?问你[：:，,]?", "", str(out.get("tomorrow") or "").strip()).strip("「」\"' ")
        res["tomorrow"] = clip(tomorrow or f"「{res['step']['title']}」做了吗？", 40)
        res["why_goal"] = clip(str(out.get("why_goal") or "").strip(), 40)
    return res
