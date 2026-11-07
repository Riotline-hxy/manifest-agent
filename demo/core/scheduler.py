"""Proactive messages: a timer thread that decides who 小光 should reach out to.

Meeting decision (10-22): simulate proactivity with a scheduled job that looks
at the user's memory and last-chat time. Rules (creative spec §C):
  - idle ≥ threshold hours (by frequency: more 4h / normal 8h / less 24h / off never), counted from the last chat or proactive message
  - never in the quiet window 23:00–08:00 Asia/Shanghai
  - at most one unseen inbox message at a time
What to say and how to say it lives in core/proactive.py (four kinds, real material only, the persona's own voice).
"""
from __future__ import annotations

import threading
import time

from . import digest, finds, llm, nudges, proactive, tasks, webpush, weekly
from .store import Store, UID_RE
from .util import DATA, clip, day_key, hours_since, iso, now
from .voice import STYLE

IDLE_HOURS = {"more": 4, "normal": 8, "less": 24}   # 最多 4 小时一条（产品负责人定的上限）
QUIET = (23, 8)
TICK_SECONDS = 600
TASK_SECONDS = 30

REMIND = {
    "gentle": "到点啦，{title}的时间到了。{message}",
    "clear": "提醒你一下：{title}，现在开始吧。{message}",
    "lively": "叮！{title}时间到～{message}",
}


def in_quiet(hour: int) -> bool:
    return hour >= QUIET[0] or hour < QUIET[1]


def waiting_unseen(store: Store, p: dict | None = None) -> bool:
    """还有一条 TA 没看过的主动消息在等着。TA 之后又来聊过天的不算——
    那条已经出现在对话里了（之前前端从不标记已读，一条旧消息会永远挡住后面的）。"""
    p = p or store.profile()
    since = p.get("last_chat_at") or ""
    return any(i["created_at"] >= since for i in store.unseen_inbox())


def should_reach_out(p: dict, has_unseen: bool, ref=None) -> tuple[bool, str]:
    ref = ref or now()
    freq = p.get("proactive") or "normal"
    if freq == "off":
        return False, "已关闭主动消息"
    if not p.get("onboarded"):
        return False, "还没完成建档"
    if in_quiet(ref.hour):
        return False, "静默时段 23:00–08:00"
    if has_unseen:
        return False, "上一条还没看"
    last = max(filter(None, [p.get("last_chat_at"), p.get("last_proactive_at")]), default=None)
    idle = hours_since(last, ref)
    need = IDLE_HOURS[freq]
    if idle is not None and idle < need:
        return False, f"距上次互动 {idle:.0f}h，未到 {need}h"
    return True, "ok"


# 计划里值得提的事 → 主动消息的参考文案（模型会按 TA 的记忆改写成自己的话）
CUE_TEXT = {
    "milestone_overdue": "「{t}」那个站点的日子过了，到了吗？没到也没关系，我们把日子挪一挪。",
    "milestone_due": "「{t}」快到日子了，现在走到哪一步了？",
    "habit_behind": "这周「{t}」有点赶不上了，要不要这周先少做一次？",
    "habit_week": "「{t}」这周还差一点，今天要不要做一次？",
    "habit_today": "今天的「{t}」做了吗？做了跟我说一声，我帮你打卡。",
    "wish_due": "「{t}」快到你定的日子了，想不想一起看看这段路？",
    "wish_overdue": "「{t}」定的日子已经过了，要不要一起回头看看，或者把日子往后挪？",
    "old_step": "「{t}」放了好几天了，还想做吗？可以拆得再小一点。",
    "no_path": "「{t}」还没有具体的路，要不要一起拆一拆？",
}


def pick_cue(store: Store) -> dict:
    """What to talk about, in priority order: the plan first (things due / falling behind), then the old cues."""
    p = store.profile()
    recs = store.records(5)
    if recs and recs[0]["type"] == "rest" and recs[0]["day"] != day_key():
        return {"cue": "after_rest", "text": "昨天好好歇了一天，小镇也安安静静地等着你。今天想从哪件小事开始？"}
    for it in nudges.attention(store):
        if it["kind"] in CUE_TEXT and (it["prio"] >= 2 or it["kind"] in ("old_step", "no_path")):
            name = it["text"].split("「", 1)[1].split("」", 1)[0] if "「" in it["text"] else ""
            return {"cue": it["kind"], "text": CUE_TEXT[it["kind"]].format(t=clip(name, 18)), "fact": it["text"]}
    todo = [s for s in store.steps() if s["status"] == "todo"]
    if todo:
        return {"cue": "step", "text": f"「{clip(todo[0]['title'], 18)}」还在等你。今天只做开头五分钟，也算。"}
    if p.get("intent_primary"):
        return {"cue": "intent", "text": f"还在靠近「{clip(p['intent_primary'], 18)}」吗？今天只要动一小步就够。"}
    return {"cue": "checkin", "text": "今天过得怎么样？有一件小好事也可以告诉我。"}


def deliver(store: Store, force: bool = False) -> dict:
    p = store.profile()
    if not force and store.c.execute("SELECT 1 FROM record WHERE type='rest' AND day=?", (day_key(),)).fetchone():
        return {"sent": False, "reason": "今天是偷懒日，不打扰"}
    ok, why = should_reach_out(p, waiting_unseen(store, p))
    if not ok and not force:
        return {"sent": False, "reason": why}
    pick = proactive.choose(store) or {"kind": "chat", "material": [f"TA 想靠近：{p.get('intent_primary') or '还没说'}"], "feature": None}
    msg = proactive.compose(store, pick)
    item = store.add_inbox(msg["text"], msg["kind"])
    store.add_msg("assistant", msg["text"], {"proactive": True, "cue": msg["kind"], "inbox_id": item["id"], "acts": msg["acts"]})
    store.set_profile({"last_proactive_at": iso(), "last_proactive_kind": msg["kind"]})
    store.log("proactive", "主动发了一条消息" + ("（演示触发）" if force and not ok else ""))
    webpush.notify_async(store.uid)
    return {"sent": True, "item": item, "reason": why if not ok else "ok"}


def tick() -> int:
    root = DATA / "u"
    if not root.is_dir():
        return 0
    sent = 0
    for d in root.iterdir():
        if not UID_RE.match(d.name):
            continue
        try:
            with Store(d.name) as st:
                # 日终整理：03:00 之后处理「昨天」，每人每天一次
                day = digest.due(st) if st.profile().get("digest_on", True) else None
                if day:
                    out = digest.run(st, day)
                    if not out.get("skipped"):
                        finds.discover(st)      # 隔几天写一次「小光的发现」（finds.due 自己判断）
                weekly.run_due(st)              # 周一 03:00 之后：把上一周写成笔记本里的一页
                if deliver(st)["sent"]:
                    sent += 1
        except Exception as e:  # one broken user must not stop the loop
            print("[scheduler]", d.name, type(e).__name__, e)
    return sent


def compose_task(st: Store, t: dict) -> str:
    """remind 用模板（不调模型）；ai 让小光按 TA 的情况写一句，失败就退回模板。"""
    p = st.profile()
    persona = p.get("persona") or "gentle"
    base = REMIND.get(persona, REMIND["gentle"]).format(title=t["title"], message=t["message"] or "").strip()
    if t["kind"] != "ai":
        return base
    from .agent import core_block   # 避免循环引用
    recent = [m for m in st.messages(8) if m["content"]][-6:]
    out = llm.complete_json([
        {"role": "system", "content": (
            f"你是「{p.get('agent_name') or '小光'}」，这个人的朋友。{STYLE.get(persona, STYLE['gentle'])}\n"
            "现在是 TA 让你定时做的一件事，到点了。按要求给 TA 发一条消息：1–3 句，口语，像朋友发微信；"
            "只用下面给出的真实信息，不编造；不说教、不鸡血；不要用「不是……而是……」句式。只输出 JSON：{\"text\":\"...\"}")},
        {"role": "user", "content": (f"例行任务：{t['title']}\n要求：{t['message'] or t['title']}\n\n关于 TA：\n{core_block(p, st)}\n\n"
                                     f"从 TA 的计划里看到值得提的事（督促、复盘类的任务就用这些，挑最要紧的一两件）：\n"
                                     f"{nudges.as_text(nudges.attention(st)) or '没有特别的'}\n\n最近的对话：\n"
                                     + "\n".join(("TA：" if m["role"] == "user" else "你：") + clip(m["content"], 80) for m in recent))},
    ], timeout=30)
    text = clip(str((out or {}).get("text") or "").strip(), 200)
    return text or base


def run_tasks(ref=None) -> int:
    """把到点的任务执行掉。一个任务出错不影响其他任务，也不会反复重试刷屏。"""
    n = 0
    for t in tasks.due(ref):
        try:
            if not UID_RE.match(t["uid"] or ""):
                tasks.mark_ran(t, ref)
                continue
            with Store(t["uid"]) as st:
                text = compose_task(st, t)
                item = st.push_inbox(text, "task")
                st.add_msg("assistant", text, {"proactive": True, "task": t["id"], "task_title": t["title"], "inbox_id": item["id"]})
                st.log("task", f"例行任务：{t['title']}")
            webpush.notify_async(t["uid"], ttl=3600, urgency="high")  # 到点提醒过时就没意义了
            n += 1
        except Exception as e:
            print("[tasks]", t.get("id"), type(e).__name__, e)
        finally:
            tasks.mark_ran(t, ref)
    return n


def start_background() -> threading.Thread:
    def task_loop():
        while True:
            time.sleep(TASK_SECONDS)
            try:
                run_tasks()
            except Exception as e:
                print("[tasks] tick failed", e)

    threading.Thread(target=task_loop, name="tasks", daemon=True).start()

    def loop():
        while True:
            time.sleep(TICK_SECONDS)
            try:
                n = tick()
                if n:
                    print(f"[scheduler] {iso()} sent {n}")
            except Exception as e:
                print("[scheduler] tick failed", e)

    t = threading.Thread(target=loop, name="proactive", daemon=True)
    t.start()
    return t
