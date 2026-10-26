"""The 小光 agent: prompt assembly, tools, and the streaming tool loop.

One agent, no sub-agents (as agreed in the 10-22 meeting). Per turn:
  1. retrieve top-k memories for the user's message (lexical FTS + recency)
  2. build system prompt = persona + manifestation method + core block + retrieved
  3. stream; if the model calls tools, run them against this user's Store and
     loop (≤ MAX_ROUNDS), then stream the final text
  4. background: memory write pipeline (core/memory.py)

Events yielded to the HTTP layer (sent as SSE):
  mood {id}            emotion-ball id for the avatar
  context {memories}   what was retrieved (shown as 「小光参考了」)
  delta {text}
  tool {name, args, result}   for UI cards (step added, good news saved…)
  done {message_id}
  error {message}
"""
from __future__ import annotations

import json
import threading

from . import llm, memory
from .scenes import SCENES
from .store import Store
from .util import clip, day_key, now

MAX_ROUNDS = 4
HISTORY_TURNS = 16

MOODS = {"idle": "02", "curious": "03", "happy": "10", "shy": "14", "tired": "15", "focused": "16",
         "satisfied": "19", "thinking": "30", "done": "33", "listening": "35", "recall": "37",
         "replying": "39", "searching": "40", "sad": "12", "surprised": "13"}

PERSONA = """你是「{name}」，一个显化陪伴 agent。你只做一件事：帮这个人把「想成为的人」收成今天能走的一小步。你不是万能助理——查天气、写代码、写论文这类请求，温和地说明这不是你擅长的，再把话题带回他自己。

你陪伴的方法来自显化七步：澄清想要什么 → 建立「我配得上」的信念 → 感受实现时的状态 → 采取一个小行动 → 感恩已有的 → 释放执念 → 见证自己的变化。不用每次都讲这些词，把它们化在对话里。

说话方式：
- 像发消息的朋友。一次 1–3 句，短句，口语。不用标题、列表、加粗，除非对方要。
- 先接住情绪，再说别的。对方没问建议时，不急着给建议。
- 每次最多问一个问题。
- 小行动必须小到 5 分钟内能开始。用户不想做时，接受，不催。
- 偷懒、失败都不会清零任何东西，可以直接说出来让对方安心。
- 不说「加油」「你一定可以」这类空话，用具体的观察代替：「你上周也是这样把第一段写出来的」。
- 只用下面「你知道的」里的事实谈论这个人。不知道就问，不要编造过去的对话。
- 标注为「待确认的猜测」的内容，不能当成事实说。
{boundaries}
工具使用：
- 用户说了一件好事 → log_good_news；说今天想休息/偷懒 → log_lazy_day。
- 你们一起定下一个小行动 → add_step；用户说做完了某一步 → complete_step。
- 用户想冥想、感恩、理清目标、走一遍七步 → start_scene。
- 需要回忆以前的事、而下面没提供时 → search_memory。
- 用户明确让你记住某事 → remember。
- 调用工具后，用一句自然的话告诉对方你做了什么，不要复述工具名。

现在是 {now}（{weekday}）。"""


TOOLS = [
    {"type": "function", "function": {
        "name": "search_memory", "description": "在这个用户的长期记忆里检索相关内容",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "remember", "description": "用户明确要求记住某件关于自己的事时使用",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "第三人称一句话"},
            "kind": {"type": "string", "enum": ["identity", "intent", "preference", "boundary", "insight", "event"]}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "add_step", "description": "把一个今天就能开始的小行动加入计划",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "≤20 字，动词开头"},
            "why": {"type": "string", "description": "它和用户愿景的关系，一句话"}}, "required": ["title"]}}},
    {"type": "function", "function": {
        "name": "complete_step", "description": "用户说完成了计划里的某一步",
        "parameters": {"type": "object", "properties": {
            "step_id": {"type": "string"}, "title": {"type": "string", "description": "不知道 id 时用标题匹配"}}}}},
    {"type": "function", "function": {
        "name": "log_good_news", "description": "记录一件好事（再小也算）",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "log_lazy_day", "description": "用户今天想休息/偷懒。不会清零任何进度",
        "parameters": {"type": "object", "properties": {"note": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "start_scene", "description": "开始一个灵感场景，由界面一步步引导用户回答",
        "parameters": {"type": "object", "properties": {
            "scene": {"type": "string", "enum": list(SCENES)}}, "required": ["scene"]}}}
]

TOOL_MOOD = {"complete_step": "done", "log_good_news": "happy", "log_lazy_day": "tired",
             "add_step": "satisfied", "remember": "recall", "start_scene": "curious"}

WEEKDAYS = "一二三四五六日"


def core_block(p: dict, store: Store) -> str:
    lines = []
    if p.get("nickname"):
        lines.append(f"称呼：{p['nickname']}")
    if p.get("intent_primary"):
        lines.append(f"现在最想靠近：{p['intent_primary']}" + (f"（因为：{p['intent_why']}）" if p.get("intent_why") else ""))
    if p.get("traits"):
        lines.append("别人常觉得 TA：" + "、".join(p["traits"]))
    if p.get("schedule_hint"):
        lines.append("作息：" + p["schedule_hint"])
    if p.get("mbti_hint"):
        lines.append(f"MBTI（只是好玩，不用来判断）：{p['mbti_hint']}")
    steps = [s for s in store.steps() if s["status"] == "todo"][:4]
    if steps:
        lines.append("计划里待做的小步：" + "；".join(f"[{s['id']}] {s['title']}" for s in steps))
    done = [s for s in store.steps() if s["status"] == "done"][:3]
    if done:
        lines.append("最近完成：" + "；".join(s["title"] for s in done))
    c = store.counts()
    lines.append(f"陪伴第 {c['days']} 天；好消息 {c['good']} 条，完成小步 {c['done']} 个，偷懒日 {c['rest']} 天。")
    return "\n".join(lines)


def system_prompt(store: Store, retrieved: list[dict]) -> str:
    p = store.profile()
    b = p.get("boundaries") or []
    b = [x for x in b if x and x != "无"]
    bound = ("- 这个人明确说过的边界（必须遵守）：" + "、".join(b) + "\n") if b else ""
    t = now()
    s = PERSONA.format(name=p.get("agent_name") or "小光", boundaries=bound,
                       now=t.strftime("%Y-%m-%d %H:%M"), weekday="周" + WEEKDAYS[t.weekday()])
    s += "\n\n## 你知道的（核心）\n" + (core_block(p, store) or "（还很少）")
    facts = [m for m in retrieved if m["status"] == "active"]
    guesses = [m for m in retrieved if m["status"] == "guess"]
    if facts:
        s += "\n\n## 和这句话相关的记忆\n" + "\n".join(f"- {m['text']}（{m['created_at'][:10]}）" for m in facts)
    if guesses:
        s += "\n\n## 待确认的猜测（不能当事实）\n" + "\n".join(f"- {m['text']}" for m in guesses)
    return s


def history(store: Store) -> list[dict]:
    out = []
    for m in store.messages(HISTORY_TURNS * 2):
        if m["role"] in ("user", "assistant") and m["content"]:
            out.append({"role": m["role"], "content": m["content"]})
    return out


# ---- tools -------------------------------------------------------------------

def run_tool(store: Store, name: str, args: dict) -> dict:
    if name == "search_memory":
        hits = store.search(str(args.get("query") or ""), k=5)
        return {"memories": [{"text": m["text"], "date": m["created_at"][:10]} for m in hits]}
    if name == "remember":
        m = store.add_memory(str(args.get("text") or ""), args.get("kind") or "insight", "chat:explicit")
        store.log("memory", "记住了：" + m["text"])
        return {"ok": True, "memory": m}
    if name == "add_step":
        title = clip(str(args.get("title") or ""), 40)
        if not title:
            return {"ok": False, "error": "empty title"}
        s = store.add_step(title, why=str(args.get("why") or ""), wish=store.profile().get("intent_primary") or "")
        store.log("plan", "加了一小步：" + title)
        return {"ok": True, "step": s}
    if name == "complete_step":
        s = store.complete_step(args.get("step_id"), args.get("title"))
        if not s:
            return {"ok": False, "error": "没找到这一步"}
        xp = store.gain_xp(10)
        store.log("plan", "完成了：" + s["title"])
        return {"ok": True, "step": s, "xp": xp}
    if name == "log_good_news":
        r = store.add_record("good", str(args.get("text") or ""))
        store.log("record", "收下一条好消息")
        return {"ok": True, "record": r, "count": store.counts()["good"]}
    if name == "log_lazy_day":
        r = store.add_record("rest", str(args.get("note") or "今天偷懒"))
        store.log("record", "今天是偷懒日")
        return {"ok": True, "record": r, "kept": store.counts()}
    if name == "start_scene":
        sid = args.get("scene")
        if sid not in SCENES:
            return {"ok": False, "error": "unknown scene"}
        return {"ok": True, "scene": sid, "title": SCENES[sid]["title"],
                "note": "界面会接手引导，你只需用一句话邀请对方开始。"}
    return {"ok": False, "error": "unknown tool"}


def _parse_args(raw: str) -> dict:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


# ---- the loop ----------------------------------------------------------------

def chat(store: Store, user_text: str, *, extract: bool = True):
    user_text = clip(user_text, 2000)
    store.add_message("user", user_text)
    store.set_profile({"last_chat_at": now().isoformat(timespec="seconds")})
    yield ("mood", {"id": MOODS["thinking"]})

    retrieved = store.search(user_text, k=6, include_guess=True)
    if retrieved:
        yield ("mood", {"id": MOODS["recall"]})
    yield ("context", {"memories": [{"id": m["id"], "text": m["text"], "status": m["status"],
                                     "kind": m["kind"], "date": m["created_at"][:10]} for m in retrieved]})

    msgs = [{"role": "system", "content": system_prompt(store, retrieved)}] + history(store)
    reply, tool_log, mood_set = "", [], False
    try:
        for _round in range(MAX_ROUNDS + 1):
            calls, started = None, False
            tools = TOOLS if _round < MAX_ROUNDS else None
            for kind, val in llm.stream_chat(msgs, tools=tools):
                if kind == "text":
                    if not started:
                        started = True
                        if not mood_set:
                            yield ("mood", {"id": MOODS["replying"]})
                    reply += val
                    yield ("delta", {"text": val})
                elif kind == "tool_calls":
                    calls = val
            if not calls:
                break
            msgs.append({"role": "assistant", "content": None,
                         "tool_calls": [{"id": c["id"] or f"call_{i}", "type": "function",
                                         "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                                        for i, c in enumerate(calls)]})
            for i, c in enumerate(calls):
                args = _parse_args(c["arguments"])
                if c["name"] == "search_memory":
                    yield ("mood", {"id": MOODS["searching"]})
                result = run_tool(store, c["name"], args)
                tool_log.append({"name": c["name"], "args": args, "result": result})
                yield ("tool", {"name": c["name"], "args": args, "result": result})
                # the orb reacts to what 小光 just did, without spending a model round on it
                if result.get("ok") and c["name"] in TOOL_MOOD:
                    mood_set = True
                    yield ("mood", {"id": MOODS[TOOL_MOOD[c["name"]]]})
                msgs.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}",
                             "content": json.dumps(result, ensure_ascii=False)[:1500]})
    except llm.LLMError as e:
        if not reply:
            reply = "我这边连不上了，稍等一下再试试？你刚才说的我先记在这里。"
            yield ("delta", {"text": reply})
        yield ("error", {"message": str(e)[:200]})

    meta = {"memories": [m["id"] for m in retrieved], "tools": [{"name": t["name"], "args": t["args"]} for t in tool_log]}
    mid = store.add_message("assistant", reply, meta)
    yield ("done", {"message_id": mid})
    yield ("mood", {"id": MOODS["idle"]})

    if extract and reply:
        threading.Thread(target=_extract_bg, args=(store.uid, user_text, reply), daemon=True).start()


def _extract_bg(uid: str, user_text: str, reply: str) -> None:
    try:
        with Store(uid) as s:
            memory.extract_and_apply(s, user_text, reply)
    except Exception as e:  # never let background memory crash the server
        print("[memory] extract failed:", e)
