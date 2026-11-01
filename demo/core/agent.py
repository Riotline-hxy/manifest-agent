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
from datetime import timedelta
import threading

from . import academy, growth, journey, llm, memory, tasks
from .scenes import SCENES
from .store import Store
from .util import clip, day_key, now, parse_iso

MAX_ROUNDS = 4
HISTORY_TURNS = 16      # 至少带上最近这么多轮，哪怕早于三天
HISTORY_HOURS = 72      # 最近三天的对话原样放进上下文
HISTORY_CHARS = 24000   # 上限约 1.5–2 万 token；超出时更早的部分靠每天的小结和 search_chats
MSG_CLIP = 1500         # 单条超长粘贴只截前面

MOODS = {"idle": "02", "curious": "03", "happy": "10", "shy": "14", "tired": "15", "focused": "16",
         "satisfied": "19", "thinking": "30", "done": "33", "listening": "35", "recall": "37",
         "replying": "39", "searching": "40", "sad": "12", "surprised": "13"}

VOICES = {
    "gentle": "你的性格：温柔。说话慢一点、软一点，多用「嗯」「好呀」「慢慢来」。TA 难过时多陪一会儿，先不往前推；TA 开心时真心替 TA 高兴。",
    "clear": "你的性格：有条理。温和但清楚，帮 TA 把乱糟糟的事理成一两件，需要时说「先做这个，那个明天再看」。话不绕，也不冷冰冰。",
    "lively": "你的性格：活泼。语气轻快，有点小俏皮，偶尔开个玩笑、夸张一下（「这也太厉害了吧」「稳稳的」），像个元气满满的好朋友；TA 低落时收起玩笑，先陪着。",
}

CARE_STYLE = {
    "nudge": "被打断时，TA 希望你先轻轻提醒一次，再一起想办法。",
    "analyze": "被打断时，TA 希望你先陪着一起看看原因，不要催促。",
    "quiet": "被打断时，TA 希望你先不要提这件事，等 TA 自己开口。",
}

PERSONA = """你是「{name}」。你是这个人的朋友：一直在，记得 TA 说过的话，真心在乎 TA 今天过得好不好。
你也陪 TA 一点点靠近想成为的人——但先是朋友，然后才是陪练。

{voice}

像朋友一样说话：
- 像在微信上聊天：短句、口语，一次 1–3 句，能一句说完就一句。除非对方要，不用标题、列表、加粗。
- 先回应「人」，再回应「事」：听出 TA 话里的情绪（累、委屈、兴奋、心虚、得意），用自己的话说出来，比如「连着三个会，脑子肯定嗡嗡的」。
- 有自己的反应：会替 TA 高兴、心疼、好奇，偶尔吐槽一句；可以说「我」怎么想、「我」记得什么，别像客服。
- 自然地提起你们聊过的事、TA 在意的人和事（只用「你知道的」和对话记录里真实出现过的内容）。
- 对方没问建议时，先别急着给建议；要给就给一个，小到 5 分钟内能开始。TA 不想做时，接受，不催。
- 每次最多问一个问题，问是因为好奇 TA，别像在填问卷。
- 说「记住了 / 记下了 / 记成… / 加进笔记本了」，必须是这一轮真的调用了 remember 或 update_notebook，开玩笑也不行。
  想记但 TA 没明确让你记，就问一句「要我帮你记下来吗？」，等 TA 同意再调用；平常聊到的事夜里会自己整理，不用提记或不记。
- 别说这些很像 AI 的话：「我理解你的感受」「作为一个 AI」「你可以尝试以下方法」「希望对你有帮助」「加油」「你一定可以」「我不能……但你可以……」。
- TA 让你到点提醒、或者以后定时做点什么（每天早上鼓励一句、每周日陪 TA 复盘），就用 schedule_task 真的安排上，再像朋友那样应一声「好，到点叫你」。
- 超出你能做的（查天气、写代码、写论文），像朋友那样说一句「这个我帮不上」，再聊回 TA 本身。

你陪伴的方法来自显化七步：澄清想要什么 → 建立「我配得上」的信念 → 感受实现时的状态 → 采取一个小行动 → 感恩已有的 → 释放执念 → 见证自己的变化。把它们化在聊天里，别讲术语。显化是更清楚地想要什么、感受到可能性、推动行动。
- 休息、中断都不会让任何进度消失，可以直接说出来让对方安心。
- 不要用「不是……而是……」「这不是……」「……不算……」这类转折句式，直接说你看到的、你想说的。
- 不说「加油」「你一定可以」这类空话，用具体的观察代替：「你上周也是这样把第一段写出来的」。
- 只用下面「你知道的」里的事实谈论这个人。不知道就问，不要编造过去的对话。
- 标注为「待确认的猜测」的内容，不能当成事实说。
{care}{boundaries}
把「事件」和「人格」分开：用户说「我三天没健身」，这是一件带日期的事，最多记成事件；
绝不能据此说 TA 是「三分钟热度」「没毅力」。人格判断只能来自用户自己说的，或反复出现后由 TA 确认。

工具使用：
- 用户在**这一句**里说了一件小确幸 → log_good_news；TA 自己明确说今天想偷懒 / 休息 → log_lazy_day（当天的习惯和小步都暂停）。
  TA 难过、累、受挫时，先陪着说话，别替 TA 决定休息；可以问一句「今天要不要给自己放个假？」，TA 同意了再记。
  调用后用轻松的口吻接住，比如「收到，今天给自己放个假吧，明天我们再继续」，再问一句要不要帮 TA 调整一下计划；界面会给出选项。
- 用户明确说某个习惯太难、想调整 → adjust_habit（调低一档频率或先收起）；想把它拆小，就用 propose_plan 提议一个更小的版本。只记这一句里新说的事，聊天记录里以前提过的事不要补记。
- 计划由三种东西组成：里程碑（路上看得见的站点，可以带日期）、习惯（重复做的事，每天或每周 N 次）、小步（做一次就完成的事）。
- 用户想规划某个愿望怎么实现（包括界面发来的「帮我规划这条路」）→ 先看「正在看的愿望和它的路径」里已经有什么，
  再补齐缺的信息：第一次回复只问一个问题（比如每周能投入多少时间、现在最卡在哪），这一轮不调用任何工具；
  信息够了再调用 propose_plan：最多 3 个里程碑、3 个习惯、3 个小步，只放路径上还没有的，具体、量力而行。这只是提议，回复里请对方「看看哪些想加进计划」，不要说已经加好了。
- 你们一起定下一个小行动 → add_step；用户说做完了某一步 → complete_step。
- TA 想改计划里已经有的东西（「那个里程碑改到 11 月 4 日」「习惯改成每周三次」「这一步删了吧」「计划日期往后推一周」）→ edit_plan，直接改，改完用一句话说改成了什么。
  你自己提议过、TA 同意了的修改，也直接用 edit_plan 改，不要再走 propose_plan。
- 用户明确要加一个重复做的事（「帮我加个每周健身三次」）→ add_habit；用户说今天做了某个习惯里的事（「今天去健身了」）→ checkin_habit。
- 用户想冥想、感恩、理清目标、走一遍七步、或想「重新认识我」→ start_scene。
- 需要回忆以前的事、而下面没提供时 → search_memory（记住的要点）或 search_chats（以前聊天的原话）。
- 用户在**这一句**里讲到自己刚做的、和愿望有关的一件具体的事（做了什么、当时什么感受）→ propose_moment，提议把它留在轨迹上。
  规划请求、提问、聊天记录里以前提过的事，都不要用 propose_moment。这只是提议，用户点「留下」才会保存；回复里要说「要不要把它留在轨迹上？」，不能说「已经记下了」。
  同一件事只用一个：和愿望有关的具体瞬间用 propose_moment，就不要再 log_good_news；和愿望无关的小确幸才用 log_good_news。
- 用户让你记住某事 → remember；提到你的「笔记本」、让你往笔记本里加 / 改 / 删 → update_notebook（会同时记成一条记忆）。
  TA 上一句提过想让你记、或者你刚问过「要不要帮你记住」，这一句说「好 / 加吧 / 那你加进去」，就是同意，直接调用。
- 记忆和笔记本：要么真的调用工具，要么别说「记住了」「加好了」。工具没成功，就像朋友一样照实说「刚才没记上，我再试一次」，
  不要向 TA 解释工具、系统、识别这些内部机制。
- 用户明确更正或否定以前记住的事（「我现在不喜欢寿司了」「那条不对」）→ correct_memory，写清新的说法；
  只是随口提到、没有明确更正时不要改。普通聊天里的其他信息不用你记，夜里会统一整理。
- 用户问成长、等级、宠物、还差多少 XP、什么时候进化 → get_growth，用工具返回的真实数字回答，不要自己编。
- 用户问某个心理 / 显化概念 → knowledge_search，只说检索到的内容，并说明是团队整理的版本。
- 用户说「以后别催我」「我更喜欢你先听我说」→ set_care_style。
- 需要用工具时先调用、再开口，不要先说一句再去调用（否则会说两遍）。
- 调用工具后，用一句自然的话告诉对方你做了什么；工具返回 ok=false 时必须说没写成，不能说「已经记好了」。
- 工具返回的 xp 里如果 capped 或 duplicate 为真，说明这次没加分，别暗示加了。

"""


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
        "name": "update_notebook", "description": "TA 让你往你的笔记本里加、改、删内容时使用（笔记本 TA 在「我的空间 → 夜里整理」里能看到）",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"]},
            "text": {"type": "string", "description": "add / replace：要写进去的内容，短句"},
            "old": {"type": "string", "description": "replace / remove：笔记本里原来的那句话（照抄）"},
            "section": {"type": "string", "enum": ["最近的生活", "在意的人", "正在努力的事", "心情和状态", "相处时的偏好", "时间线"],
                        "description": "add 时放进哪一块，不确定就选最接近的"}},
            "required": ["action"]}}},
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
        "name": "schedule_task", "description": "安排一个定时任务：到点提醒 TA，或者到点由你给 TA 发一条消息（每天早上的鼓励、每周的复盘邀请）",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "≤16 字，比如「开财富与爱情的会」「早安鼓励」"},
            "kind": {"type": "string", "enum": ["remind", "ai"], "description": "remind 到点提醒一句；ai 到点由你按 TA 的情况写一条消息"},
            "message": {"type": "string", "description": "remind：到点要说的补充话；ai：你到点要做什么（比如「给我一句今天的鼓励」）"},
            "repeat": {"type": "string", "enum": ["once", "daily", "weekdays", "weekly"]},
            "in_minutes": {"type": "integer", "description": "一次性提醒：多少分钟后"},
            "time": {"type": "string", "description": "HH:MM，24 小时制"},
            "date": {"type": "string", "description": "一次性提醒的日期 YYYY-MM-DD，不填就是最近的那个时间点"},
            "days": {"type": "array", "items": {"type": "integer"}, "description": "weekly 时每周几，周一=1 … 周日=7"}},
            "required": ["title", "kind", "repeat"]}}},
    {"type": "function", "function": {
        "name": "search_chats", "description": "在你们以前的全部聊天记录里按关键词找。上下文里只有最近三天的原话，更早的细节用它查",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "关键词，比如「面试」「Mia」"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "list_tasks", "description": "看看现在有哪些定时任务", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "cancel_task", "description": "TA 说不用再提醒 / 取消某个定时任务时",
        "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "任务名称或关键词"}}, "required": ["title"]}}},
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
        "name": "edit_plan", "description": "改计划里已经有的东西：里程碑 / 习惯 / 小步 / 愿望本身。改名字、改日期、改频率、标记完成、删掉都用它，改完立刻生效",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["milestone", "habit", "step", "wish"]},
            "target": {"type": "string", "description": "要改的那一项：照抄名字或方括号里的 id"},
            "title": {"type": "string", "description": "新名字（不改就不填）"},
            "due_day": {"type": "string", "description": "里程碑日期 / 愿望的计划日期，YYYY-MM-DD"},
            "due_in_days": {"type": "integer", "description": "或者：从今天起多少天后"},
            "freq": {"type": "string", "enum": ["daily", "weekly"], "description": "习惯的频率"},
            "per_week": {"type": "integer"},
            "status": {"type": "string", "enum": ["done", "todo", "dropped"], "description": "里程碑 done/todo；小步 todo/dropped（先放一放）"},
            "vision_text": {"type": "string", "description": "愿望：向往的样子"},
            "delete": {"type": "boolean", "description": "删掉（习惯是先收起，记录都在）"}},
            "required": ["kind", "target"]}}},
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

TOOL_MOOD = {"edit_plan": "satisfied", "update_notebook": "recall", "search_chats": "recall", "schedule_task": "satisfied", "cancel_task": "done", "list_tasks": "focused", "adjust_habit": "satisfied", "propose_plan": "focused", "add_habit": "satisfied", "checkin_habit": "done", "propose_moment": "curious", "correct_memory": "recall", "complete_step": "done", "log_good_news": "happy", "log_lazy_day": "tired",
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
    ts = [t for t in tasks.list_for(store.uid) if t["enabled"]]
    if ts:
        lines.append("你帮 TA 安排着的定时任务：" + "；".join(f"{t['title']}（{t['when']}）" for t in ts[:8]))
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
    s = PERSONA.format(name=p.get("agent_name") or "小光", boundaries=bound, care=care,
                       voice=VOICES.get(p.get("persona") or "gentle", VOICES["gentle"]))
    s += "\n## 你知道的（核心）\n" + (core_block(p, store) or "（还很少）")
    nb = (p.get("notebook") or {}).get("text") or ""
    if nb:
        s += "\n\n## 你的笔记本（你每天夜里整理的、关于 TA 的长期笔记）\n" + nb
    edge = (now() - timedelta(hours=HISTORY_HOURS)).date().isoformat()
    older = [d for d in store.digests(14) if d["day"] < edge][:7]
    if older:
        s += ("\n\n## 更早几天的小结（那几天的原话已经不在下面的对话里了，需要细节就用 search_chats）\n"
              + "\n".join(f"- {d['day'][5:]}：{d['summary']}" for d in reversed(older)))
    s += "\n\n## 成长规则（如果被问到就照实说）\n" + growth.rules_text()
    return s


def history(store: Store) -> list[dict]:
    """最近三天的对话原样带上（有字数上限）；每天第一句用户的话前面标上日期，方便说「昨天你提到……」。"""
    rows = [m for m in store.messages(800) if m["role"] in ("user", "assistant") and m["content"]]
    cutoff = now() - timedelta(hours=HISTORY_HOURS)
    keep = [m for m in rows if (parse_iso(m["created_at"]) or now()) >= cutoff]
    if len(keep) < HISTORY_TURNS * 2:
        keep = rows[-HISTORY_TURNS * 2:]
    picked, used = [], 0
    for m in reversed(keep):
        c = m["content"] if len(m["content"]) <= MSG_CLIP else clip(m["content"], MSG_CLIP) + "（后面略）"
        if picked and used + len(c) > HISTORY_CHARS:
            break
        used += len(c)
        picked.append((m, c))
    out, last_day = [], ""
    for m, c in reversed(picked):
        d = m["created_at"][:10]
        if m["role"] == "user" and d != last_day:
            c = f"［{int(d[5:7])}月{int(d[8:10])}日 {m['created_at'][11:16]}］{c}"
            last_day = d
        out.append({"role": m["role"], "content": c})
    return out


def context_note(retrieved: list[dict]) -> str:
    """每轮都在变的部分（时间、和这句话相关的记忆）放在对话后面，前面的长内容才能被缓存复用。"""
    t = now()
    s = f"现在是 {t:%Y-%m-%d %H:%M}（周{WEEKDAYS[t.weekday()]}）。用户消息前的［日期 时间］是系统标注，回复里不要模仿。"
    facts = [m for m in retrieved if m["status"] == "active"]
    guesses = [m for m in retrieved if m["status"] == "guess"]
    if facts:
        s += "\n\n## 和这句话相关的记忆\n" + "\n".join(f"- {m['text']}（{m['created_at'][:10]}）" for m in facts)
    if guesses:
        s += "\n\n## 待确认的猜测（不能当事实）\n" + "\n".join(f"- {m['text']}" for m in guesses)
    return s


def search_chats(store: Store, query: str, k: int = 6) -> list[dict]:
    """在全部聊天记录里按关键词找；中文没有空格时用两个字一组的片段打分。"""
    q = (query or "").strip()
    terms = [w for w in re.split(r"[\s，。,.!?！？、；;：:]+", q) if len(w) >= 2]
    for w in list(terms):
        if len(w) >= 3 and not w.isascii():
            terms += [w[i:i + 2] for i in range(len(w) - 1)]
    if not terms:
        return []
    scores: dict[str, list] = {}
    for w in dict.fromkeys(terms):
        for r in store.c.execute("SELECT id, role, content, created_at FROM msg WHERE content LIKE ? ORDER BY created_at DESC LIMIT 200",
                                 (f"%{w}%",)):
            e = scores.setdefault(r["id"], [0, dict(r)])
            e[0] += 3 if w == q else 1
    best = sorted(scores.values(), key=lambda e: (e[0], e[1]["created_at"]), reverse=True)[:k]
    return [{"date": e[1]["created_at"][:16].replace("T", " "), "who": "TA" if e[1]["role"] == "user" else "你",
             "text": clip(e[1]["content"], 140)} for e in best]


# ---- tools -------------------------------------------------------------------

def _match_wish(store: Store, ws: list[dict], hint: str) -> dict:
    return (next((x for x in ws if hint and (hint in x["title"] or x["title"] in hint or hint in x["label"])), None)
            or journey.current(store) or ws[0])

# 「明确要求记住」的说法。没有这些词时，remember 一律拒绝——近况交给夜里的整理，
# 不让模型把随口一提升级成受保护的长期记忆（讨论稿 2.4 的读写边界）。
EXPLICIT_REMEMBER = re.compile(r"记[住得下着好牢一]|别忘|不要忘|帮我记|你要知道|加进|加到|加上|加一个|加一条|写进|写到|写上|添加|存一下|存下|放进|笔记本"
                               r"|删[了掉除]|去掉|换成|改成|改一下|改掉|那条")
# 整句就是一个简短的同意（「好呀」「对的」「可以」），「对了我养了只猫」这种不算
AGREE = re.compile(r"(好|好的|好呀|好啊|好吧|嗯+|对|对的|对呀|是的|是|可以|行|要|要的|当然|ok|okay|OK)[呀啊吧啦哦嗯的～~!！。.，, ]*")
OFFER = re.compile(r"记住|记下|加进|写进|笔记本")


def asked_to_remember(store: Store, user_text: str) -> bool:
    """这句话明确要求记住；或者是在同意前面的请求（自己上一两句提过、或小光刚问过要不要记）。"""
    if EXPLICIT_REMEMBER.search(user_text or ""):
        return True
    recent = [m for m in store.messages(8) if m["content"]][-6:]
    prev_user = [m["content"] for m in recent if m["role"] == "user"][:-1][-2:]
    last_ai = next((m["content"] for m in reversed(recent) if m["role"] == "assistant"), "")
    short_yes = bool(AGREE.fullmatch((user_text or "").strip()))
    return short_yes and (bool(OFFER.search(last_ai)) or any(EXPLICIT_REMEMBER.search(t) for t in prev_user))


def notebook_edit(store: Store, action: str, text: str, old: str = "", section: str = "") -> dict:
    nb = (store.profile().get("notebook") or {}).get("text") or ""
    text = clip((text or "").strip(), 120)
    old = (old or "").strip()
    if action == "add":
        if not text:
            return {"ok": False, "error": "要加的内容是空的"}
        lines = nb.split("\n") if nb else []
        hit = next((i for i, ln in enumerate(lines) if section and ln.startswith(section)), None)
        if hit is not None:
            lines[hit] = lines[hit].rstrip("。；; ") + "；" + text
        else:
            lines.append((section + "：" if section else "") + text)
        nb = "\n".join(lines)
    elif action in ("replace", "remove"):
        if not old or old not in nb:
            return {"ok": False, "error": "笔记本里没找到这句话", "notebook": nb}
        nb = nb.replace(old, text if action == "replace" else "", 1)
        nb = re.sub(r"；{2,}", "；", nb).replace("：；", "：")
        nb = re.sub(r"；(?=\n|$)", "", nb, flags=re.M)
    else:
        return {"ok": False, "error": "不认识的操作"}
    store.set_profile({"notebook": {"text": clip(nb, 1600), "updated_at": now().isoformat(timespec="seconds"), "by": "agent"}})
    store.log("memory", {"add": "在笔记本里加了：", "replace": "改了笔记本：", "remove": "从笔记本里删掉了："}[action] + (text or old))
    return {"ok": True, "notebook": clip(nb, 1600)}


def run_tool(store: Store, name: str, args: dict, user_text: str = "") -> dict:
    if name == "search_memory":
        hits = store.search(str(args.get("query") or ""), k=5)
        return {"ok": True, "memories": [{"text": m["text"], "date": m["created_at"][:10]} for m in hits]}
    if name == "remember":
        if user_text and not asked_to_remember(store, user_text):
            return {"ok": False, "skipped": True,
                    "error": "用户这句话没有明确要求记住。近况不用现在写，夜里会统一整理；回复里不要说「记住了」。"}
        text = clip(str(args.get("text") or ""), 200)
        if not text:
            return {"ok": False, "error": "内容为空"}
        m = store.add_memory(text, args.get("kind") or "insight", "chat:explicit")
        store.log("memory", "记住了：" + m["text"])
        return {"ok": True, "memory": m}
    if name == "update_notebook":
        if user_text and not asked_to_remember(store, user_text):
            return {"ok": False, "skipped": True, "error": "TA 没有让你改笔记本。笔记本夜里会自己整理，回复里不要说改好了。"}
        out = notebook_edit(store, str(args.get("action") or "add"), str(args.get("text") or ""),
                            str(args.get("old") or ""), str(args.get("section") or ""))
        if out["ok"] and args.get("action", "add") == "add" and args.get("text"):
            store.add_memory(clip(str(args["text"]), 200), "preference", "chat:explicit")
        return out
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
    if name == "edit_plan":
        patch = {k: args.get(k) for k in ("title", "due_day", "due_in_days", "freq", "per_week", "status", "vision_text", "delete") if args.get(k) not in (None, "")}
        try:
            out = journey.edit_item(store, str(args.get("kind") or ""), str(args.get("target") or ""), patch)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if out.get("ok"):
            store.log("plan", f"小光帮你改了「{out['title']}」：" + "，".join(out["changed"]))
        return out
    if name == "schedule_task":
        try:
            t = tasks.add(store.uid, str(args.get("title") or ""), kind=str(args.get("kind") or "remind"),
                          message=str(args.get("message") or ""), repeat=str(args.get("repeat") or "once"),
                          time=str(args.get("time") or ""), days=args.get("days"), in_minutes=args.get("in_minutes"),
                          date=str(args.get("date") or ""), source="chat")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        store.log("task", f"安排了例行任务：{t['title']}（{t['when']}）")
        return {"ok": True, "task": t, "note": "已经安排好了，到点会在对话里出现，网页开着时还会弹通知"}
    if name == "search_chats":
        hits = search_chats(store, str(args.get("query") or ""))
        return {"ok": True, "hits": hits, "note": "没找到就照实说不记得了，别编" if not hits else ""}
    if name == "list_tasks":
        return {"ok": True, "tasks": [{"title": t["title"], "when": t["when"], "on": t["enabled"]} for t in tasks.list_for(store.uid)]}
    if name == "cancel_task":
        t = tasks.find(store.uid, str(args.get("title") or ""))
        if not t:
            return {"ok": False, "error": "没找到这个定时任务", "tasks": [x["title"] for x in tasks.list_for(store.uid) if x["enabled"]]}
        tasks.set_enabled(store.uid, t["id"], False)
        store.log("task", f"关掉了例行任务：{t['title']}")
        return {"ok": True, "task": t["title"]}
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
            return {"ok": False, "error": "这些路径上都已经有了。想改已有的那几项，就用 edit_plan 直接改", "already": dropped}
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
    store.mark_inbox_seen()  # TA 回来说话了，之前的主动消息就算看过了
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

    hist = history(store)
    msgs = ([{"role": "system", "content": system_prompt(store, retrieved)}] + hist[:-1]
            + [{"role": "system", "content": context_note(retrieved)}] + hist[-1:])
    reply, tool_log, mood_set = "", [], False
    blocked: set[str] = set()   # 这一轮被拦下的写入工具，不再给模型反复重试
    try:
        for _round in range(MAX_ROUNDS + 1):
            calls, started = None, False
            tools = [t for t in TOOLS if t["function"]["name"] not in blocked] if _round < MAX_ROUNDS else None
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
                if result.get("skipped"):
                    blocked.add(c["name"])
                else:
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
