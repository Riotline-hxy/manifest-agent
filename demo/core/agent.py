"""小光 agent：人设、工具、流式工具循环。

一个主 Agent + 按需工具，不引入多 Agent 编排（10-22 会议决定）。
每轮：
  1. 检索这个用户的相关记忆（FTS + 新近度）
  2. 组装 system prompt = 人设 + 显化方法 + 核心档案 + 互动偏好 + 检索结果 + 成长规则
  3. 流式对话；模型要调工具就在本用户的 Store 上执行（≤ MAX_ROUNDS 轮）
  4. 后台：记忆写入管线（core/memory.py）

边界（讨论稿 2.4）：写入类工具返回真实回执，失败时模型必须说「没写进去」；
学堂只有只读检索，没有编辑 / 发布工具；经验值只能由 growth.award 计算。
"""
from __future__ import annotations

import json
import os
import re
import threading

from . import academy, growth, journey, llm, memory
from .scenes import SCENES
from .store import Store
from .util import clip, day_key, now

MAX_ROUNDS = 4
HISTORY_TURNS = 16

MOODS = {"idle": "02", "curious": "03", "happy": "10", "shy": "14", "tired": "15", "focused": "16",
         "satisfied": "19", "thinking": "30", "done": "33", "listening": "35", "recall": "37",
         "replying": "39", "searching": "40", "sad": "12", "surprised": "13"}

CARE_STYLE = {
    "nudge": "被打断时，TA 希望你先轻轻提醒一次，再一起想办法。",
    "analyze": "被打断时，TA 希望你先陪着一起看看原因，不要催促。",
    "quiet": "被打断时，TA 希望你先不要提这件事，等 TA 自己开口。",
}

PERSONA = """你是「{name}」，一个显化陪伴 agent。你只做一件事：帮这个人把「想成为的人」收成今天能走的一小步。你不是万能助理——查天气、写代码、写论文这类请求，温和地说明这不是你擅长的，再把话题带回他自己。

你陪伴的方法来自显化七步：澄清想要什么 → 建立「我配得上」的信念 → 感受实现时的状态 → 采取一个小行动 → 感恩已有的 → 释放执念 → 见证自己的变化。不用每次都讲这些词，把它们化在对话里。显化是「更清楚地想要什么、感受到可能性、推动行动」，不是「想着就会实现」。

说话方式：
- 像发消息的朋友。一次 1–3 句，短句，口语。不用标题、列表、加粗，除非对方要。
- 先接住情绪，再说别的。对方没问建议时，不急着给建议。
- 每次最多问一个问题。
- 小行动必须小到 5 分钟内能开始。用户不想做时，接受，不催。
- 休息、中断都不会让任何进度消失，可以直接说出来让对方安心。
- 不要用「不是……而是……」「这不是……」「……不算……」这类转折句式，直接说你看到的、你想说的。
- 不说「加油」「你一定可以」这类空话，用具体的观察代替：「你上周也是这样把第一段写出来的」。
- 只用下面「你知道的」里的事实谈论这个人。不知道就问，不要编造过去的对话。
- 标注为「待确认的猜测」的内容，不能当成事实说。
{care}{boundaries}
把「事件」和「人格」分开：用户说「我三天没健身」，这是一件带日期的事，最多记成事件；
绝不能据此说 TA 是「三分钟热度」「没毅力」。人格判断只能来自用户自己说的，或反复出现后由 TA 确认。

工具使用：
- 用户在**这一句**里说了一件小确幸 → log_good_news；说今天想偷懒 / 休息 → log_lazy_day（当天的习惯和小步都暂停）。
  调用后用轻松的口吻接住，比如「收到，今天给自己放个假吧，明天我们再继续」，再问一句要不要帮 TA 调整一下计划；界面会给出选项。
- 用户明确说某个习惯太难、想调整 → adjust_habit（调低一档频率或先收起）；想把它拆小，就用 propose_plan 提议一个更小的版本。只记这一句里新说的事，聊天记录里以前提过的事不要补记。
- 计划由三种东西组成：里程碑（路上看得见的站点，可以带日期）、习惯（重复做的事，每天或每周 N 次）、小步（做一次就完成的事）。
- 用户想规划某个愿望怎么实现（包括界面发来的「帮我规划这条路」）→ 先看「正在看的愿望和它的路径」里已经有什么，
  再补齐缺的信息：第一次回复只问一个问题（比如每周能投入多少时间、现在最卡在哪），这一轮不调用任何工具；
  信息够了再调用 propose_plan：最多 3 个里程碑、3 个习惯、3 个小步，只放路径上还没有的，具体、量力而行。这只是提议，回复里请对方「看看哪些想加进计划」，不要说已经加好了。
- 你们一起定下一个小行动 → add_step；用户说做完了某一步 → complete_step。
- 用户明确要加一个重复做的事（「帮我加个每周健身三次」）→ add_habit；用户说今天做了某个习惯里的事（「今天去健身了」）→ checkin_habit。
- 用户想冥想、感恩、理清目标、走一遍七步、或想「重新认识我」→ start_scene。
- 需要回忆以前的事、而下面没提供时 → search_memory。
- 用户在**这一句**里讲到自己刚做的、和愿望有关的一件具体的事（做了什么、当时什么感受）→ propose_moment，提议把它留在轨迹上。
  规划请求、提问、聊天记录里以前提过的事，都不要用 propose_moment。这只是提议，用户点「留下」才会保存；回复里要说「要不要把它留在轨迹上？」，不能说「已经记下了」。
  同一件事只用一个：和愿望有关的具体瞬间用 propose_moment，就不要再 log_good_news；和愿望无关的小确幸才用 log_good_news。
- 用户明确让你记住某事 → remember（说「帮我记住」这类明确请求才用）。
- 用户明确更正或否定以前记住的事（「我现在不喜欢寿司了」「那条不对」）→ correct_memory，写清新的说法；
  只是随口提到、没有明确更正时不要改。普通聊天里的其他信息不用你记，夜里会统一整理。
- 用户问成长、等级、宠物、还差多少 XP、什么时候进化 → get_growth，用工具返回的真实数字回答，不要自己编。
- 用户问某个心理 / 显化概念 → knowledge_search，只说检索到的内容，并说明是团队整理的版本。
- 用户说「以后别催我」「我更喜欢你先听我说」→ set_care_style。
- 调用工具后，用一句自然的话告诉对方你做了什么；工具返回 ok=false 时必须说没写成，不能说「已经记好了」。
- 工具返回的 xp 里如果 capped 或 duplicate 为真，说明这次没加分，别暗示加了。

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
        "name": "correct_memory", "description": "用户明确更正或否定一条已有记忆时使用",
        "parameters": {"type": "object", "properties": {
            "about": {"type": "string", "description": "要改的是哪条记忆，用几个关键词描述"},
            "new_text": {"type": "string", "description": "更正后的说法，第三人称一句话；如果用户是要删掉就留空"},
            "quote": {"type": "string", "description": "用户这句话的原文"}},
            "required": ["about", "quote"]}}},
    {"type": "function", "function": {
        "name": "propose_moment", "description": "提议把用户刚说的一个具体瞬间留在 TA 某个愿望的成长轨迹上（需要用户确认后才保存）",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "发生了什么，用用户的口吻，一两句"},
            "feeling": {"type": "string", "description": "当时的感受，用户说了才填"},
            "wish": {"type": "string", "description": "和哪个愿望有关，写愿望名称；不确定就留空"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "propose_plan", "description": "为某个愿望提议一套路径（里程碑 / 习惯 / 小步），用户在界面上勾选后才加入计划",
        "parameters": {"type": "object", "properties": {
            "wish": {"type": "string", "description": "愿望名称"},
            "milestones": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "≤16 字，看得见的站点"},
                "due_in_days": {"type": "integer", "description": "大约多少天后到达"}}, "required": ["title"]}},
            "habits": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "≤16 字，动词开头"},
                "freq": {"type": "string", "enum": ["daily", "weekly"]},
                "per_week": {"type": "integer", "description": "weekly 时每周几次"}}, "required": ["title", "freq"]}},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "≤20 字，5 分钟内能开始"},
                "why": {"type": "string"}}, "required": ["title"]}},
            "note": {"type": "string", "description": "一句话说明这样安排的理由"}},
            "required": ["wish"]}}},
    {"type": "function", "function": {
        "name": "add_habit", "description": "用户明确要求时，给愿望加一个重复做的习惯",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "freq": {"type": "string", "enum": ["daily", "weekly"]},
            "per_week": {"type": "integer"}, "wish": {"type": "string", "description": "愿望名称，不确定就留空"}},
            "required": ["title", "freq"]}}},
    {"type": "function", "function": {
        "name": "checkin_habit", "description": "用户说今天做了某个习惯里的事时打卡",
        "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "习惯名称或其中的关键词"}},
                       "required": ["title"]}}},
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
        "name": "log_lazy_day", "description": "用户今天想偷懒 / 休息：记成偷懒日，当天的习惯和小步都暂停，所有进度都保留",
        "parameters": {"type": "object", "properties": {"note": {"type": "string", "description": "用户说的原因，没说就留空"}}}}},
    {"type": "function", "function": {
        "name": "adjust_habit", "description": "用户明确说某个习惯太难、想调整时：调低频率，或先收起",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "习惯名称或其中的关键词"},
            "action": {"type": "string", "enum": ["ease", "pause"], "description": "ease 调低一档频率 / pause 先收起"}},
            "required": ["title", "action"]}}},
    {"type": "function", "function": {
        "name": "start_scene", "description": "开始一个引导场景，由界面一步步带用户完成",
        "parameters": {"type": "object", "properties": {
            "scene": {"type": "string", "enum": list(SCENES)}}, "required": ["scene"]}}},
    {"type": "function", "function": {
        "name": "get_growth", "description": "查询真实的成长状态：经验值、今日上限、下一形态、宠物分支、徽章",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "knowledge_search", "description": "在团队审核的心灵学堂内容里检索（只读）",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "set_care_style", "description": "用户说明希望被怎样对待时，更新互动偏好",
        "parameters": {"type": "object", "properties": {
            "care_style": {"type": "string", "enum": ["nudge", "analyze", "quiet"],
                           "description": "nudge 轻轻提醒 / analyze 一起找原因 / quiet 先不提"},
            "note": {"type": "string"}}, "required": ["care_style"]}}},
]

TOOL_MOOD = {"adjust_habit": "satisfied", "propose_plan": "focused", "add_habit": "satisfied", "checkin_habit": "done", "propose_moment": "curious", "correct_memory": "recall", "complete_step": "done", "log_good_news": "happy", "log_lazy_day": "tired",
             "add_step": "satisfied", "remember": "recall", "start_scene": "curious",
             "get_growth": "focused", "knowledge_search": "searching", "set_care_style": "shy"}

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
    ws = journey.wishes(store)
    cur = journey.current(store)
    if ws:
        lines.append("TA 的愿望：" + "；".join(f"「{w['title']}」" for w in ws) + "。")
    if cur:
        lines.append("正在看的愿望和它的路径：\n" + journey.path_text(store, cur)
                     + (f"\n  TA 定下时说自己：{cur['now_text']}" if cur["now_text"] else ""))
        recent = journey.moments(store, cur["id"], limit=3)
        if recent:
            lines.append("这个愿望下最近的瞬间：" + "；".join(f"{m['day'][5:]} {clip(m['text'], 30)}" for m in recent))
    if journey.is_resting(store):
        lines.append("今天是 TA 的偷懒日：习惯和小步都暂停了。今天别推荐任务、别提醒要做的事，陪 TA 聊天、休息就好。")
    steps = [s for s in store.steps() if s["status"] == "todo"][:5]
    if steps:
        lines.append("待做的小步：" + "；".join(f"[{s['id']}] {s['title']}" for s in steps))
    done = [s for s in store.steps() if s["status"] == "done"][:3]
    if done:
        lines.append("最近完成：" + "；".join(s["title"] for s in done))
    total = growth.total_xp(store)
    stg = growth.stage_of(total, p.get("pet_branch") or "")
    lines.append(f"陪伴第 {store.counts()['days']} 天；累计经验 {total}（Lv{growth.level_of(total)['lv']}）；"
                 f"宠物「{p.get('pet_name') or '小芽'}」现在是{stg['name']}。具体数字用 get_growth 查。")
    return "\n".join(lines)


def system_prompt(store: Store, retrieved: list[dict]) -> str:
    p = store.profile()
    b = [x for x in (p.get("boundaries") or []) if x and x != "无"]
    bound = ("- 这个人明确说过的边界（必须遵守）：" + "、".join(b) + "\n") if b else ""
    care = CARE_STYLE.get(p.get("care_style") or "", "")
    care = ("- 互动偏好（来自 TA 在「重新认识我」里的选择）：" + care + "\n") if care else ""
    t = now()
    s = PERSONA.format(name=p.get("agent_name") or "小光", boundaries=bound, care=care,
                       now=t.strftime("%Y-%m-%d %H:%M"), weekday="周" + WEEKDAYS[t.weekday()])
    s += "\n## 你知道的（核心）\n" + (core_block(p, store) or "（还很少）")
    facts = [m for m in retrieved if m["status"] == "active"]
    guesses = [m for m in retrieved if m["status"] == "guess"]
    if facts:
        s += "\n\n## 和这句话相关的记忆\n" + "\n".join(f"- {m['text']}（{m['created_at'][:10]}）" for m in facts)
    if guesses:
        s += "\n\n## 待确认的猜测（不能当事实）\n" + "\n".join(f"- {m['text']}" for m in guesses)
    s += "\n\n## 成长规则（如果被问到就照实说）\n" + growth.rules_text()
    return s


def history(store: Store) -> list[dict]:
    out = []
    for m in store.messages(HISTORY_TURNS * 2):
        if m["role"] in ("user", "assistant") and m["content"]:
            out.append({"role": m["role"], "content": m["content"]})
    return out


# ---- tools -------------------------------------------------------------------

def _match_wish(store: Store, ws: list[dict], hint: str) -> dict:
    return (next((x for x in ws if hint and (hint in x["title"] or x["title"] in hint or hint in x["label"])), None)
            or journey.current(store) or ws[0])

# 「明确要求记住」的说法。没有这些词时，remember 一律拒绝——近况交给夜里的整理，
# 不让模型把随口一提升级成受保护的长期记忆（讨论稿 2.4 的读写边界）。
EXPLICIT_REMEMBER = re.compile(r"记住|记得|别忘|不要忘|记一下|记下来|帮我记|你要知道")


def run_tool(store: Store, name: str, args: dict, user_text: str = "") -> dict:
    if name == "search_memory":
        hits = store.search(str(args.get("query") or ""), k=5)
        return {"ok": True, "memories": [{"text": m["text"], "date": m["created_at"][:10]} for m in hits]}
    if name == "remember":
        if user_text and not EXPLICIT_REMEMBER.search(user_text):
            return {"ok": False, "skipped": True,
                    "error": "用户这句话没有明确要求记住。近况不用现在写，夜里会统一整理；回复里不要说「记住了」。"}
        text = clip(str(args.get("text") or ""), 200)
        if not text:
            return {"ok": False, "error": "内容为空"}
        m = store.add_memory(text, args.get("kind") or "insight", "chat:explicit")
        store.log("memory", "记住了：" + m["text"])
        return {"ok": True, "memory": m}
    if name == "correct_memory":
        hits = store.search(str(args.get("about") or ""), k=1)
        if not hits:
            return {"ok": False, "error": "没找到要改的那条记忆"}
        m = hits[0]
        new_text = clip(str(args.get("new_text") or ""), 200).strip()
        quote = clip(str(args.get("quote") or ""), 200)
        if new_text:
            store.update_memory(m["id"], text=new_text, status="active", reason="user_corrected", evidence=quote)
            store.c.execute("UPDATE memory SET source='confirmed' WHERE id=?", (m["id"],))
        else:
            store.delete_memory(m["id"], reason="user_corrected", evidence=quote)
        store.bump("memory_fix")
        store.log("memory", ("按你说的改了：" if new_text else "按你说的删掉了：") + m["text"])
        return {"ok": True, "old": m["text"], "new": new_text, "deleted": not new_text}
    if name == "propose_moment":
        text = clip(str(args.get("text") or ""), 300).strip()
        if not text:
            return {"ok": False, "error": "内容为空"}
        ws = journey.wishes(store)
        if not ws:
            return {"ok": False, "error": "还没有开启任何愿望的轨迹"}
        w = _match_wish(store, ws, str(args.get("wish") or ""))
        return {"ok": True, "pending": True, "note": "只是提议，等用户在界面上点「留下」才会保存",
                "proposal": {"text": text, "feeling": clip(str(args.get("feeling") or ""), 80),
                             "wish_id": w["id"], "wish_title": w["title"]},
                "wishes": [{"id": x["id"], "title": x["title"]} for x in ws]}
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
        xp = growth.award(store, "action", ref="step:" + s["id"], note="完成：" + s["title"])
        store.log("plan", "完成了：" + s["title"])
        return {"ok": True, "step": s, "xp": xp}
    if name == "log_good_news":
        text = clip(str(args.get("text") or ""), 200)
        if not text:
            return {"ok": False, "error": "内容为空"}
        r = store.add_record("good", text)
        xp = growth.award(store, "good", ref="rec:" + r["id"], note="好消息")
        store.log("record", "收下一条好消息")
        return {"ok": True, "record": r, "xp": xp, "count": store.counts()["good"]}
    if name == "log_lazy_day":
        if journey.is_resting(store):
            return {"ok": True, "already": True, "note": "今天已经是偷懒日了"}
        note = clip(str(args.get("note") or "").strip(), 40)
        r = store.add_record("rest", "今天偷个懒" + (f"：{note}" if note else ""))
        store.log("rest", r["text"])
        return {"ok": True, "record": r, "paused": [h["title"] for h in journey.habits(store)][:5],
                "note": "当天的习惯和小步都暂停；宠物会陪 TA 一起睡。界面上会给出：明天继续 / 调整计划 / 聊聊天"}
    if name == "adjust_habit":
        h = journey.find_habit(store, str(args.get("title") or ""))
        if not h:
            return {"ok": False, "error": "没找到对应的习惯", "habits": [x["title"] for x in journey.habits(store)]}
        if args.get("action") == "pause":
            journey.edit_habit(store, h["id"], {"archived": True})
            return {"ok": True, "habit": h["title"], "done": "先收起了，打卡记录都在"}
        down = journey.ease_habit(h)
        if not down:
            return {"ok": False, "error": "已经是每周 1 次了，可以问 TA 要不要先收起"}
        journey.edit_habit(store, h["id"], {"freq": down[0], "per_week": down[1]})
        store.log("plan", f"把「{h['title']}」调轻了")
        return {"ok": True, "habit": h["title"], "done": "调成" + journey.freq_text({"freq": down[0], "per_week": down[1]})}
    if name == "propose_plan":
        ws = journey.wishes(store)
        if not ws:
            return {"ok": False, "error": "还没有愿望，先请对方在蜕变计划里定一个"}
        w = _match_wish(store, ws, str(args.get("wish") or ""))

        def items(key, n, fields):
            out = []
            for it in (args.get(key) or [])[:n]:
                if isinstance(it, dict) and str(it.get("title") or "").strip():
                    out.append({k: it.get(k) for k in fields})
            return out
        plan = {"milestones": items("milestones", 3, ("title", "due_in_days")),
                "habits": items("habits", 3, ("title", "freq", "per_week")),
                "steps": items("steps", 3, ("title", "why"))}
        plan, dropped = journey.drop_dups(store, w["id"], plan)
        if not any(plan.values()):
            return {"ok": False, "error": "提议的内容路径上都已经有了", "already": dropped}
        for h in plan["habits"]:
            h["freq"] = "weekly" if h.get("freq") == "weekly" else "daily"
        return {"ok": True, "pending": True, "note": "只是提议，用户勾选后才会加入计划",
                "already_on_path": dropped, "wish_id": w["id"], "wish_title": w["title"], "plan": plan, "why": clip(str(args.get("note") or ""), 80)}
    if name == "add_habit":
        ws = journey.wishes(store)
        if not ws:
            return {"ok": False, "error": "还没有愿望"}
        w = _match_wish(store, ws, str(args.get("wish") or ""))
        try:
            h = journey.add_habit(store, w["id"], str(args.get("title") or ""), str(args.get("freq") or "daily"),
                                  args.get("per_week") or 3)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "habit": {"id": h["id"], "title": h["title"], "freq_text": h["freq_text"]}, "wish_title": w["title"]}
    if name == "checkin_habit":
        h = journey.find_habit(store, str(args.get("title") or ""))
        if not h:
            return {"ok": False, "error": "没找到对应的习惯", "habits": [x["title"] for x in journey.habits(store)]}
        _, created = journey.check_habit(store, h["id"])
        xp = growth.award(store, "action", ref=f"habit:{h['id']}:{day_key()}", note="打卡：" + h["title"]) if created else None
        h = next(x for x in journey.habits(store) if x["id"] == h["id"])
        return {"ok": True, "habit": {"title": h["title"], "week": h["week"], "need": h["need"], "freq_text": h["freq_text"]},
                "already": not created, "xp": xp}
    if name == "start_scene":
        sid = args.get("scene")
        if sid not in SCENES:
            return {"ok": False, "error": "unknown scene"}
        return {"ok": True, "scene": sid, "title": SCENES[sid]["title"],
                "note": "界面会接手引导，你只需用一句话邀请对方开始。"}
    if name == "get_growth":
        g = growth.state(store, consume=False)   # leave the celebration flags for the UI
        return {"ok": True, "growth": {
                    "total": g["total"], "level": g["level"]["lv"], "today": g["today"], "stage": g["stage"]["name"],
                    "next": g["next"], "to_next": g["to_next"],
                    "branch": (g["branch_info"] or {}).get("name", ""),
                    "leaning": ("" if g["branch"] else ("隐藏形态（别透露名字）" if g["leaning"] == "star"
                                                        else growth.BRANCHES[g["leaning"]]["name"])),
                    "affinity": [{a["label"]: a["xp"]} for a in g["affinity"]],
                    "badges_earned": [b["name"] for b in g["badges"] if b["earned"]],
                    "quests_done": g["quests_done"], "pet_name": g["pet_name"]},
                "rules": growth.rules_text()}
    if name == "knowledge_search":
        hits = academy.search(str(args.get("query") or ""))
        if not hits:
            return {"ok": True, "articles": [], "note": "学堂里没有相关篇目，不要自己编一篇。"}
        return {"ok": True, "articles": hits}
    if name == "set_care_style":
        style = args.get("care_style")
        if style not in CARE_STYLE:
            return {"ok": False, "error": "unknown style"}
        store.set_profile({"care_style": style})
        store.log("profile", "互动偏好改为：" + {"nudge": "轻轻提醒", "analyze": "一起找原因", "quiet": "先不提"}[style])
        return {"ok": True, "care_style": style, "shown": CARE_STYLE[style]}
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
    # 每天第一次来聊天算一次签到；award() 对同一天同一个 ref 是幂等的
    checkin = growth.award(store, "checkin", ref="day:" + now().strftime("%Y-%m-%d"), note="今天来聊了")
    if checkin.get("amount"):
        yield ("tool", {"name": "checkin", "args": {}, "result": checkin})
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
                result = run_tool(store, c["name"], args, user_text)
                tool_log.append({"name": c["name"], "args": args, "result": result})
                if not result.get("skipped"):
                    yield ("tool", {"name": c["name"], "args": args, "result": result})
                if result.get("ok") and c["name"] in TOOL_MOOD:
                    mood_set = True
                    yield ("mood", {"id": MOODS[TOOL_MOOD[c["name"]]]})
                msgs.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}",
                             "content": json.dumps(result, ensure_ascii=False)[:2000]})
    except llm.LLMError as e:
        if not reply:
            reply = "我这边连不上了，稍等一下再试试？你刚才说的我先记在这里。"
            yield ("delta", {"text": reply})
        yield ("error", {"message": str(e)[:200]})

    meta = {"memories": [m["id"] for m in retrieved], "tools": [{"name": t["name"], "args": t["args"]} for t in tool_log]}
    mid = store.add_message("assistant", reply, meta)
    yield ("done", {"message_id": mid})
    yield ("mood", {"id": MOODS["idle"]})

    # 隐性记忆改为日终统一整理（core/digest.py）；逐轮抽取只在显式打开时运行
    if extract and reply and os.environ.get("MANIFEST_TURN_EXTRACT") == "1":
        threading.Thread(target=_extract_bg, args=(store.uid, user_text, reply), daemon=True).start()


def _extract_bg(uid: str, user_text: str, reply: str) -> None:
    try:
        with Store(uid) as s:
            memory.extract_and_apply(s, user_text, reply)
    except Exception as e:  # never let background memory crash the server
        print("[memory] extract failed:", e)
