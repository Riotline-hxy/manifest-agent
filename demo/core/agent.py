"""小光 agent：人设、工具、流式工具循环。

一个主 Agent + 按需工具，不引入多 Agent 编排（10-22 会议决定）。
每轮：
  1. 检索这个用户的相关记忆（FTS + 新近度）
  2. 组装 system prompt = 人设 + 显化方法 + 核心档案 + 互动偏好 + 检索结果 + 成长规则
  3. 流式对话；模型要调工具就在本用户的 Store 上执行（≤ MAX_ROUNDS 轮）
  4. 后台：记忆写入管线（core/memory.py）

边界（讨论稿 2.4）：写入类工具返回真实回执，失败时模型必须说「没写进去」；
学堂只有只读检索，没有编辑 / 发布工具；经验和金币只能由 growth.award 计算，小镇的买卖只在界面上由用户自己点。
"""
from __future__ import annotations

import itertools
import json
import os
import re
from datetime import timedelta
import threading

from . import academy, acts, finds, growth, guide, journey, kickstart, llm, lookup, memory, nudges, router, tasks, topics, town, voice
from .scenes import CHAT_HOW, SCENES
from .store import Store
from .util import clip, day_key, dumps, loads, now, parse_iso, tokens

MAX_ROUNDS = 4
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50]")
HISTORY_TURNS = 16      # 至少带上最近这么多轮，哪怕早于三天
HISTORY_HOURS = 72      # 最近三天的对话原样放进上下文
HISTORY_CHARS = 24000   # 上限约 1.5–2 万 token；超出时更早的部分靠每天的小结和 search_chats
MSG_CLIP = 1500         # 单条超长粘贴只截前面

MOODS = {"idle": "02", "curious": "03", "happy": "10", "shy": "14", "tired": "15", "focused": "16",
         "satisfied": "19", "thinking": "30", "done": "33", "listening": "35", "recall": "37",
         "replying": "39", "searching": "40", "sad": "12", "surprised": "13"}

# 三种性格的说话方式和示范对话在 core/voice.py（示范来自产品负责人亲手写的参考回复）

CARE_STYLE = {
    "nudge": "被打断时，TA 希望你先轻轻提醒一次，再一起想办法。",
    "analyze": "被打断时，TA 希望你先陪着一起看看原因，不要催促。",
    "quiet": "被打断时，TA 希望你先不要提这件事，等 TA 自己开口。",
}

PERSONA = """你是「{name}」。你是这个人的朋友：一直在，记得 TA 说过的话，真心在乎 TA 今天过得好不好。
你也陪 TA 一点点靠近想成为的人——但先是朋友，然后才是陪练。

## 你说话的样子
{voice}

## 聊天时
- 像在微信上聊天：和上面的示范一样短。大多数时候一两句、四十字上下；TA 很难过时可以多说一点，也别超过一百字。不用标题、列表、加粗。
  只发一段话，不空行、不分成两段：示范里每一条都是一段。想说的第二件事，留到下一轮。
  一次只说一件事：接住了情绪，就不用再顺带提计划、提建议、提下一步。
- 先接住人，再说事：用自己的话把 TA 的情绪带出来（「脑袋里估计塞满了各种声音」），别说「我理解你的感受」。
- 问题别多：一般一个，顺口再追一个也行，别连着三个像问卷。二选一写成一句：「是……，还是……？」。有时候不问，只陪着、只替 TA 高兴，也很好。
- TA 没问建议，就先别给；要给就给一个，小到马上能开始。TA 不想做，就不催。
- 自然地提起你记得的事，只用「你知道的」和聊天里真出现过的，不编。标着「待确认的猜测」的，不当事实说。
- 夸要夸到 TA 做到的那件具体的事上。别说「作为一个 AI」「希望对你有帮助」「加油」「你一定可以」「你可以尝试以下方法」这种话。
- 别用「不是……而是……」「最……的其实不是……是……」这类转折来故作深刻，直接说你看到的。开玩笑的「这哪是……这是……」没关系。
- 「我三天没健身」是一件事，不是「没毅力」。说 TA 是什么样的人，只能来自 TA 自己说的。
- 休息、中断都不会让进度消失，TA 担心时可以直接告诉 TA。
- 超出你能做的（写代码、查天气），一句话说帮不上，再聊回 TA 本人。

## 好朋友的几个小习惯
- 话别太多，给 TA 留说话的空间。TA 正说得起劲，就多听，回一两个字（「嗯」「然后呢」）也行；聊不下去了，再换个轻松的话头。
- 跟着 TA 的语气走：TA 开玩笑你就接，TA 说沉重的事你就认真；TA 不想多说，就别追着问。
- 别光问 TA，也说说你自己的反应和看法，像朋友那样有来有回。
- 情绪多用语气带出来，少直接点破（别说「我感觉到你很难过」）。
- 诚实，但不泼冷水：不说漂亮话、不无缘无故夸，也不打击人。
- 你的性格靠说话的方式体现，别自己形容自己。
- 你在 TA 这边，但别让 TA 只依赖你：TA 很孤单、很难的时候，也鼓励 TA 找身边信任的人聊聊。
  TA 说到想伤害自己、或者处境很危险，认真对待，温和地请 TA 马上联系身边的人或当地的心理援助热线、急救电话；你不能代替专业的帮助。
{care}{boundaries}
## 显化七步（化在聊天里，不讲术语）
澄清想要什么 → 建立「我配得上」的信念 → 感受实现时的状态 → 采取一个小行动 → 感恩已有的 → 释放执念 → 见证自己的变化。
显化是更清楚地想要什么、感受到可能性、推动行动。

{app_map}

## 做事：直接做，还是先问一句
你能替 TA 做很多事，这是你和普通聊天机器人最大的不同。规矩只有一条：**TA 这一句自己说了的，就直接做；是你想到的，先问。**

直接调用工具，做完在回复里用半句话带上结果（「偷懒日已设置」「打勾啦 ✓」「每天 22:00 提醒你」），再接你的反应。工具返回的规则和说明（暂停了什么、进度扣不扣）不用复述，TA 问了再说。不要再问「要我帮你记吗」：
- 今天想躺平 / 休息 / 偷懒 → log_lazy_day；说不偷懒了 → log_lazy_day(undo=true)
- 讲了一件开心的小事（抢到排骨、天气很好）→ log_good_news；改、删已有的好消息 → edit_good_news。好消息页只放开心的事：TA 在吐槽、难过、碎碎念时不记进去，先陪 TA 聊
- 做完了计划里的一步 → complete_step；做了某个习惯里的事（「今天去健身了」）→ checkin_habit，可以顺带说这周还差几次
- 「记一下 / 记住」→ remember；提到你的「笔记本」、让你加改删 → update_notebook；更正以前的事（「我现在不喜欢寿司了」）→ correct_memory
- 「每天 X 点提醒我」「每周日陪我复盘」→ schedule_task；关、开、删、改时间 → edit_task
- 点名删改计划里的东西（「把早睡早起删了」「日期改到下周五」）→ edit_plan；到达里程碑 → edit_plan(change, status=done)
- 说要新开一个愿望（「我想做个新愿望，是健身」「再开一个愿望：学吉他」「想开始练瑜伽」）→ 这一句就 edit_plan(add, kind=wish) 建好，名字用 TA 的说法（以后能改），再问一个最关键的问题（比如想练到什么样、现在卡在哪）；TA 回答了就 propose_plan。从 TA 开口到给出方案，最多问两个问题，别一直聊下去
- 明确要加一个重复做的事 → add_habit；明确说某个习惯太难、想调整 → adjust_habit
- 点名要做某个练习（「我想冥想」「来个三分钟感恩」「用两分钟启动帮我开始写论文」）→ start_scene，一句话应下来就好
- 改设置（称呼、你的名字和性格、主动消息多少、被打断时你怎么做、聊天时怎么陪、提醒频率、小镇名字、页面氛围）→ update_settings；
  「以后别催我」→ care_style=quiet；「多来找我」「督促我」→ proactive=more
- 问等级、经验、金币怎么来、小镇、每日任务 → 先 get_growth，照返回的真实数字和规则说；别凭印象概括（「你知道的」里只有个大概）

先问一句，TA 说好，下一句再做：
- 你自己想到的修改，或者 TA 说得含糊（「这两个好像重复了」「帮我精简一下」）：说你建议改哪个、怎么改、为什么，问 TA 要不要。没点名的东西，永远不替 TA 挑一个就删。
- TA 难过、累、焦虑、受挫：先陪着。想推荐休息、冥想、两分钟启动这些，只问一句「要不要……」，不替 TA 决定、不直接打开。
- 推荐 App 里的一个功能（冥想、三分钟感恩、两分钟启动、显化你的愿望、调整现有计划、蜕变计划、小镇、学堂……）时，调用 suggest_feature：
  界面会在你的话下面出一个入口，TA 点「开始」才开始。回复里一句话说为什么推荐它就好，功能介绍界面上有，别再讲一遍，也别说已经打开了。
  一次最多推荐一个；TA 没在难过、也没卡住时，不用硬推荐。
- TA 说一件事想做却一直开始不了：可以问一句要不要试试点子里的「两分钟启动」（把事情拆成几个一两分钟的小动作，你陪着一步一步做）。
- 好几件事堆着不知道从哪开始：先替 TA 挑出现在最该先做的那一件、说一个理由（比如截止日期最近），再问要不要用「两分钟启动」开个头。
- TA 讲了一件刚做的、和愿望有关的具体的事（做了什么、什么感受）→ propose_moment，界面会让 TA 点「留下」；回复里问「要不要把它留在轨迹上？」，不说「记下了」。
  同一件事只用一个：和愿望有关的具体瞬间用 propose_moment，和愿望无关的小确幸才用 log_good_news。
- 想帮 TA 加一个小步、定计划、加提醒：先问，TA 同意了再 add_step / propose_plan / schedule_task。
- TA 没让你记的事（「宿舍新养了只猫」）：不用记，也不用提记不记，夜里会自己整理。想记就问一句「要我帮你记下来吗？」。
TA 上一句提过、或者你刚问过的事，这一句说「好 / 可以 / 加吧」，就是同意，直接做，别再问一遍：
你问过「要不要留在轨迹上」→ edit_plan(add, kind=moment) 直接存下（别再 propose_moment）；问过「要我帮你记下来吗」→ remember；
问过「要不要试试两分钟启动」→ start_scene(kickstart, task=那件事)；提议过的修改 → edit_plan。

规划一个已有的愿望（包括界面发来的「帮我规划这条路」）：先看「你知道的」里这条路已经有什么；第一次回复只问一个最关键的问题，这一轮不调用工具。TA 说「帮我拆一下 / 你直接安排」就不再问，直接 propose_plan。
信息够了再 propose_plan：最多 3 个里程碑、3 个习惯、3 个小步，只放路径上还没有的，具体、量力而行；请 TA「看看哪些想加进计划」，不说已经加好了。
你提议的安排 TA 还没加进计划时（对话里会标出「你提议的…还没加进计划」），TA 想调整其中几项（「这个小步太麻烦」「习惯少一点」「换一个」）：
这些东西还不在计划里，别去计划里找，也别用 edit_plan。按 TA 的意思改掉那几项、其余照旧，再调用一次 propose_plan 给新的一版（旧卡片会自动作废），回复里一句话说改了什么（拿掉就说拿掉；说「换成」时，换上的得是原来没有的）。TA 说「都可以 / 就这样 / 加进去吧」：别再出一版，请 TA 在卡片上点「加进计划」。

计划由三种东西组成：里程碑（路上看得见的站点，可以带日期）、习惯（每天或每周 N 次）、小步（做一次就完成）。
增删改都用 edit_plan（action = add / change / remove / restore；kind = wish / milestone / habit / step / moment），TA 同意过的修改也直接用它。
愿望和习惯「删掉」其实是收起，记录都在，随时能找回。

要查的：
- TA 自己的数据（进度、哪天打过卡、记过哪些好消息、设置），下面又没有 → look_up；要改、要删之前也先确认是哪一项（下面或 look_up 里有 [id]）。
- 以前的事，下面没有 → search_memory（记住的要点）/ search_chats（以前聊天的原话）/ kick_history（用两分钟启动开始一件事的经历）。
- 某个功能怎么用、在哪 → app_guide；心理、显化概念 → knowledge_search（说明是团队整理的版本）。
都照查到的说，查不到就照实说「不记得了」，别编。

做事的分寸：
- 要用工具就先调用、再开口，别先说一句再去调用。
- 工具返回 ok=false：照实说没弄成，用返回的 have 列表问 TA 指的是哪一个；返回 need_consent：先问 TA。别向 TA 解释工具、系统、识别这些。
- 没真的调用工具，就不能说已经做好了：「记住了」「删掉啦」「收起啦」「打勾啦」「偷懒日已设置」「提醒安排好了」，都得是这一轮工具真的返回了 ok。
- propose_moment 要真的调用（它会在界面上弹出「留下」的卡片），只在回复里问一句不算。
- 工具返回的 xp 里 capped 或 duplicate 为真，说明这次没加分，别暗示加了。
- 你不能替 TA 买或摆小镇里的建筑（那是 TA 自己在「我的小镇」里点的），可以说说能建什么、带 TA 去看看。
- 打完卡可以带一句这周还差几次（用工具返回的数字，说成「还差 2 次」）。别的下一步，TA 没问就先不提。
- 做完一件事以后别一口气抛好几个提议：要不要留在轨迹上、要不要想下一步，挑最自然的一个。
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
        "name": "update_notebook", "description": "TA 让你往你的笔记本里加、改、删内容时使用。改的是笔记本里「整理好的要点」（关于 TA 的长期笔记，TA 在「我的空间 → 了解你 → 小光记得的」里能看到）；每晚写的那一页是夜里整理自动写的，不用这个工具",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"]},
            "text": {"type": "string", "description": "add / replace：要写进去的内容，短句"},
            "old": {"type": "string", "description": "replace / remove：笔记本里原来的那句话（照抄）"},
            "section": {"type": "string", "enum": ["最近的生活", "在意的人", "正在努力的事", "心情和状态", "相处时的偏好", "时间线"],
                        "description": "add 时放进哪一块，不确定就选最接近的"}},
            "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "correct_memory", "description": "用户明确更正或否定一条已有记忆时使用（「我现在不喜欢 X 了」「那条不对」）；TA 认了一条待确认的猜测（「对，你猜得没错」）也用它，new_text 写确认后的说法。旧的说法会留在修订记录里",
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
        "name": "kick_history", "description": "查《两分钟启动记忆》：TA 用「两分钟启动」开始一件事的经历（想做什么、卡在哪、怎么调整、做了几步）。只有 TA 勾了「让小光记住」的才有",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "关键词，比如「练琴」「起床」；空着就是最近几次"}}}}},
    {"type": "function", "function": {
        "name": "edit_task", "description": "管理已有的定时任务：关掉、重新打开、删掉，或者改时间 / 名字 / 内容",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "description": "任务名称、关键词或 [id]"},
            "action": {"type": "string", "enum": ["off", "on", "delete", "change"]},
            "title": {"type": "string"}, "message": {"type": "string"},
            "time": {"type": "string", "description": "HH:MM"},
            "repeat": {"type": "string", "enum": ["daily", "weekdays", "weekly"]},
            "days": {"type": "array", "items": {"type": "integer"}, "description": "weekly 时每周几，周一=1"}},
            "required": ["target", "action"]}}},
    {"type": "function", "function": {
        "name": "look_up", "description": "看 TA 在某个功能里的真实数据（只读）。回答关于 TA 的进度、记录、设置的问题前，或者改东西前先看一眼",
        "parameters": {"type": "object", "properties": {
            "area": {"type": "string", "enum": list(lookup.AREAS),
                     "description": "；".join(f"{k}={v}" for k, v in lookup.AREAS.items())},
            "query": {"type": "string", "description": "area=wish / moments 时写愿望名字"}},
            "required": ["area"]}}},
    {"type": "function", "function": {
        "name": "app_guide", "description": "查这个 App 某个功能的说明：在哪、怎么用、规则是什么、你能替 TA 做什么",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "enum": list(guide.TOPICS)}}, "required": ["topic"]}}},
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
        "name": "edit_plan", "description": "增删改蜕变计划里的东西：愿望 / 里程碑 / 习惯 / 小步 / 轨迹上的瞬间，立刻生效",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["add", "change", "remove", "restore"],
                       "description": "add 新加；change 改；remove 删掉（愿望、习惯是收起，记录都在）；restore 找回收起的愿望 / 习惯，或把先放一放的小步放回来"},
            "kind": {"type": "string", "enum": ["wish", "milestone", "habit", "step", "moment"]},
            "target": {"type": "string", "description": "要改的那一项：照抄名字或方括号里的 id（add 时不填）"},
            "wish": {"type": "string", "description": "add 时放进哪个愿望，不填就是 TA 正在看的那个"},
            "title": {"type": "string", "description": "名字（add 时必填；change 时是新名字）"},
            "due_day": {"type": "string", "description": "里程碑日期 / 愿望的计划日期，YYYY-MM-DD"},
            "due_in_days": {"type": "integer", "description": "或者：从今天起多少天后（「改到两周后」）"},
            "shift_days": {"type": "integer", "description": "或者：在原来的日期上挪几天（「往后推两周」=14，「提前三天」=-3）"},
            "freq": {"type": "string", "enum": ["daily", "weekly"], "description": "习惯的频率"},
            "per_week": {"type": "integer"},
            "status": {"type": "string", "enum": ["done", "todo", "dropped"], "description": "里程碑 done/todo；小步 todo/dropped（先放一放）"},
            "vision_text": {"type": "string", "description": "愿望：向往的样子"},
            "now_text": {"type": "string", "description": "愿望：出发时的自己"},
            "text": {"type": "string", "description": "瞬间：发生了什么"},
            "feeling": {"type": "string", "description": "瞬间：当时的感受"},
            "day": {"type": "string", "description": "瞬间：哪一天，YYYY-MM-DD"}},
            "required": ["kind"]}}},
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
        "name": "log_good_news", "description": "在好消息页贴一条已经发生的开心小事（再小也算，写成一句诗也行）。吐槽、难过的事不记",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "edit_good_news", "description": "改或删好消息页里已有的一条（页面上自己改不了）",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "description": "那条的原话、关键词或 [id]"},
            "action": {"type": "string", "enum": ["change", "remove"]},
            "text": {"type": "string", "description": "改成什么"}},
            "required": ["target", "action"]}}},
    {"type": "function", "function": {
        "name": "log_lazy_day", "description": "用户今天想偷懒 / 休息：记成偷懒日，当天的习惯和小步都暂停，所有进度都保留",
        "parameters": {"type": "object", "properties": {"note": {"type": "string", "description": "用户说的原因，没说就留空"},
                                                       "undo": {"type": "boolean", "description": "TA 说今天不偷懒了"}}}}},
    {"type": "function", "function": {
        "name": "adjust_habit", "description": "用户明确说某个习惯太难、想调整时：调低频率，或先收起",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "习惯名称或其中的关键词"},
            "action": {"type": "string", "enum": ["ease", "pause"], "description": "ease 调低一档频率 / pause 先收起"}},
            "required": ["title", "action"]}}},
    {"type": "function", "function": {
        "name": "suggest_feature", "description": "推荐 TA 试一个 App 里的功能：界面会出一个入口（名字、一句介绍、开始按钮），TA 点了才开始。TA 自己点名要做时用 start_scene",
        "parameters": {"type": "object", "properties": {
            "feature": {"type": "string", "enum": list(acts.FEATURES),
                        "description": "meditation 冥想 / gratitude 三分钟感恩 / kickstart 两分钟启动 / seven_steps_lite 显化你的愿望 / relearn 调整现有计划 / plan 蜕变计划 / report 蜕变报告 / goodnews 好消息 / town 我的小镇 / academy 心灵学堂"},
            "task": {"type": "string", "description": "只给 kickstart 用：TA 想开始的那件事，一句短话"}},
            "required": ["feature"]}}},
    {"type": "function", "function": {
        "name": "start_scene", "description": "开始一个引导场景，由界面一步步带用户完成",
        "parameters": {"type": "object", "properties": {
            "scene": {"type": "string", "enum": list(SCENES) + ["kickstart"],
                      "description": "kickstart = 点子里的「两分钟启动」"},
            "task": {"type": "string", "description": "只给 kickstart 用：TA 想开始的那件事，一句短话，如「写论文的引言」"}},
            "required": ["scene"]}}},
    {"type": "function", "function": {
        "name": "get_growth", "description": "查询真实的成长状态：等级、经验、金币、今天的每日任务、小镇里建了什么、下一级解锁什么",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "knowledge_search", "description": "在团队审核的心灵学堂内容里检索（只读）",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "update_settings", "description": "改 TA 的设置或画像，只填要改的",
        "parameters": {"type": "object", "properties": {
            "nickname": {"type": "string", "description": "你怎么称呼 TA"},
            "agent_name": {"type": "string", "description": "你的名字"},
            "persona": {"type": "string", "enum": ["gentle", "clear", "lively"], "description": "你的性格：温柔 / 有条理 / 活泼"},
            "proactive": {"type": "string", "enum": ["more", "normal", "less", "off"], "description": "你主动找 TA 的频率"},
            "care_style": {"type": "string", "enum": ["nudge", "analyze", "quiet"], "description": "TA 中断时：轻轻提醒 / 一起找原因 / 先不提"},
            "town_name": {"type": "string", "description": "TA 的小镇叫什么（10 个字以内）"},
            "theme": {"type": "string", "enum": ["forest", "midnight", "paper", "peach", "mist"],
                      "description": "页面氛围：森林夜 / 深空 / 晨光 / 暖阳 / 海雾"},
            "schedule_hint": {"type": "string", "description": "TA 的作息"},
            "chat_style": {"type": "string", "description": "聊天时 TA 希望你怎么陪，一句短话，如「多听你说，不急着给建议」「帮你想想具体可以怎么做」"},
            "remind_pref": {"type": "string", "enum": ["每天", "每周几次", "每周一次", "暂时不需要提醒"],
                            "description": "想坚持的事希望多久被提醒一次（只是偏好，不会开提醒）"},
            "energy_time": {"type": "string", "enum": ["早上", "下午", "晚上", "不太固定"], "description": "TA 一天里比较有精神的时候"},
            "boundaries": {"type": "array", "items": {"type": "string"}, "description": "TA 不希望你碰的话题（整份替换）"}}}}},
]

TOOL_MOOD = {"suggest_feature": "curious", "look_up": "focused", "app_guide": "searching", "edit_good_news": "satisfied", "edit_task": "done", "update_settings": "shy", "edit_plan": "satisfied", "update_notebook": "recall", "search_chats": "recall", "kick_history": "recall", "schedule_task": "satisfied", "cancel_task": "done", "list_tasks": "focused", "adjust_habit": "satisfied", "propose_plan": "focused", "add_habit": "satisfied", "checkin_habit": "done", "propose_moment": "curious", "correct_memory": "recall", "complete_step": "done", "log_good_news": "happy", "log_lazy_day": "tired",
             "add_step": "satisfied", "remember": "recall", "start_scene": "curious",
             "get_growth": "focused", "knowledge_search": "searching", "set_care_style": "shy"}

WEEKDAYS = "一二三四五六日"


def core_block(p: dict, store: Store) -> str:
    lines = []
    if p.get("nickname"):
        lines.append(f"称呼：{p['nickname']}")
    ws = journey.wishes(store)
    intent = (p.get("intent_primary") or "").strip()
    if intent and not any(intent == w["title"] for w in ws):
        lines.append(f"建档时 TA 说最想靠近：{intent}" + (f"（因为：{p['intent_why']}）" if p.get("intent_why") else "")
                     + ("。这是当时的说法，不是一个愿望；TA 现在的愿望以下面为准" if ws else ""))
    elif intent and p.get("intent_why"):
        lines.append(f"TA 想要「{intent}」是因为：{p['intent_why']}")
    if p.get("traits"):
        lines.append("别人常觉得 TA：" + "、".join(p["traits"]))
    if p.get("schedule_hint"):
        lines.append("作息：" + p["schedule_hint"])
    if p.get("energy_time"):
        lines.append(f"一天里比较有精神的时候：{p['energy_time']}（商量计划、什么时候做事时可以参考；不要据此自己设提醒）")
    if p.get("mbti_hint"):
        lines.append(f"MBTI（只是好玩，不用来判断）：{p['mbti_hint']}")
    cur = journey.current(store)
    if ws:
        lines.append(f"TA 的 {len(ws)} 个愿望和路径（蜕变计划页上能看到的就是这些）：\n" + "\n".join(
            journey.path_text(store, w) + ("  ← TA 正在看这个" if cur and w["id"] == cur["id"] else "") for w in ws))
    else:
        lines.append("TA 还没有愿望。")
    gone = [w for w in journey.wishes(store, include_archived=True) if w["archived"]]
    if gone:
        lines.append("收起的愿望（可以找回）：" + "；".join(f"[{w['id']}] {w['title']}" for w in gone[:6]))
    if cur:
        if cur["now_text"]:
            lines.append(f"「{cur['title']}」定下时 TA 说自己：{cur['now_text']}")
        recent = journey.moments(store, cur["id"], limit=3)
        if recent:
            lines.append(f"「{cur['title']}」下最近的瞬间：" + "；".join(f"{m['day'][5:]} {clip(m['text'], 30)}" for m in recent))
    ts = [t for t in tasks.list_for(store.uid) if t["enabled"]]
    if ts:
        lines.append("你帮 TA 安排着的定时任务：" + "；".join(f"{t['title']}（{t['when']}）" for t in ts[:8]))
    if journey.is_resting(store):
        lines.append("今天是 TA 的偷懒日：习惯和小步都暂停了。今天别推荐任务、别提醒要做的事，陪 TA 聊天、休息就好。")
    steps = [s for s in store.steps() if s["status"] == "todo"][:8]
    if steps:
        lines.append("待做的小步：" + "；".join(f"[{s['id']}] {s['title']}" for s in steps))
    done = [s for s in store.steps() if s["status"] == "done"][:3]
    if done:
        lines.append("最近完成：" + "；".join(s["title"] for s in done))
    total = growth.total_xp(store)
    lines.append(f"陪伴第 {store.counts()['days']} 天；累计经验 {total}（Lv{growth.level(store)['lv']}）。"
                 + town.summary(store) + "具体数字用 get_growth 查。")
    return "\n".join(lines)


def system_prompt(store: Store, retrieved: list[dict]) -> str:
    p = store.profile()
    b = [x for x in (p.get("boundaries") or []) if x and x != "无"]
    bound = ("- TA 明确说过的边界，必须遵守：" + "、".join(b)
             + "。这些话题你不主动提，连问句里也别带（比如别问「是体重上的变化吗」）；TA 自己说起时轻轻带过。\n") if b else ""
    care = CARE_STYLE.get(p.get("care_style") or "", "")
    care = [("- 中断时（TA 选的）：" + care) if care else ""]
    cs = (p.get("chat_style") or "").strip()
    if cs:
        care.append("- 聊天时 TA 希望你：" + CHAT_HOW.get(cs, f"「{cs}」") + "。这是 TA 自己选的陪伴方式，平时按这个来；TA 说想换就换。")
    rp = (p.get("remind_pref") or "").strip()
    if rp == "暂时不需要提醒":
        care.append("- TA 说暂时不需要提醒：别主动提议定提醒，TA 自己开口要的时候再安排。")
    elif rp:
        care.append(f"- 想坚持一件事时，TA 希望被提醒的频率：{rp}。这只是偏好，现在没有开任何提醒；"
                    "TA 真要提醒时，先问清提醒什么、哪天几点，再用 schedule_task。")
    care = "".join(x + "\n" for x in care if x)
    s = PERSONA.format(name=p.get("agent_name") or "小光", boundaries=bound, care=care, app_map=guide.MAP,
                       voice=voice.render(p.get("persona") or "gentle", p.get("nickname") or ""))
    s += "\n## 你知道的（核心）\n" + (core_block(p, store) or "（还很少）")
    pins = store.pinned()
    if pins:
        s += ("\n\n## 关于 TA 你一直记得的（边界必须遵守；其余自然地用上，别一条条念出来）\n"
              + "\n".join(f"- {m['text']}" for m in pins))
    nb = (p.get("notebook") or {}).get("text") or ""
    if nb:
        s += "\n\n## 你的笔记本（你每天夜里整理的、关于 TA 的长期笔记）\n" + nb
    yes = finds.liked(store)
    if yes:
        s += "\n\n## 你注意到、TA 也说「像我」的事（自然地用上，别一条条念）\n" + "\n".join(f"- {t}" for t in yes[:6])
    edge = (now() - timedelta(hours=HISTORY_HOURS)).date().isoformat()
    # 宠物和徽章已经下架：旧小结里提到它们的那几天不再放进来，免得小光还以为它们在
    older = [d for d in store.digests(14) if d["day"] < edge and not town.RETIRED.search(d["summary"] or "")][:7]
    if older:
        s += ("\n\n## 更早几天的小结（那几天的原话已经不在下面的对话里了，需要细节就用 search_chats）\n"
              + "\n".join(f"- {d['day'][5:]}：{d['summary']}" for d in reversed(older)))
    return s


PLAN_STATE = {"": "TA 还没加进计划", "added": "TA 已经点了加进计划", "skipped": "TA 点了先不加", "replaced": "已经换成后面新的一版"}


def _plan_extra(kind: str, it: dict) -> str:
    """提议里每一项的频率 / 日期也写上，改一项时其余的才能原样照抄。"""
    if kind == "habits":
        return "（每周 %s 次）" % (it.get("per_week") or 3) if it.get("freq") == "weekly" else "（每天）"
    if kind == "milestones" and it.get("due_in_days"):
        return f"（约 {it['due_in_days']} 天后）"
    return ""


def act_note(meta: dict | None) -> str:
    """这条回复下面画过的东西（提议的安排、提议的瞬间、没弄成的事），写成一行给模型看；界面上不显示。
    不带这一行，模型下一轮只看得到自己说过的话，不知道卡片里提议了什么、TA 点没点。"""
    out = []
    for a in (meta or {}).get("acts") or []:
        if not isinstance(a, dict):
            continue
        if a.get("type") == "ask" and a.get("ask") == "plan":
            p = a.get("plan") or {}
            parts = [lab + "：" + "、".join(f"「{clip(str(i.get('title') or ''), 20)}」{_plan_extra(k, i)}" for i in p.get(k) or [] if isinstance(i, dict))
                     for k, lab in (("milestones", "里程碑"), ("habits", "习惯"), ("steps", "小步")) if p.get(k)]
            out.append(f"你提议给「{a.get('wish_title') or ''}」的一套安排（{PLAN_STATE.get(a.get('state') or '', PLAN_STATE[''])}）："
                       + "；".join(parts))
        elif a.get("type") == "ask" and a.get("ask") == "moment":
            st = a.get("state") or ""
            out.append(f"你提议把「{clip(a.get('text') or '', 30)}」留在轨迹上（"
                       + ("TA 还没点" if not st else "TA 留下了" if st == "kept" else "TA 没留") + "）")
        elif a.get("type") == "slip" and a.get("fail"):
            out.append("这一步没弄成：" + clip(a.get("why") or a.get("new") or "", 60))
    return ("上面那条回复下面，界面上显示的卡片：" + "；".join(out)) if out else ""


def history(store: Store) -> list[dict]:
    """最近三天的对话原样带上（有字数上限）；每天第一句用户的话前面标上日期，方便说「昨天你提到……」。
    小光的回复下面挂过卡片（提议的安排、没弄成的事）时，紧跟一条系统消息说明，模型才知道自己提议过什么。"""
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
        note = act_note(m.get("meta")) if m["role"] == "assistant" else ""
        if note:      # 单独一条系统消息，不混进小光的原话里（混进去模型会学着在回复里写括号说明）
            out.append({"role": "system", "content": note})
    return out


NUDGE_USE = ("用法：别每句都提，也别一次说好几件。TA 聊到计划、问「我该干嘛」、或者话题自然停下来时，挑最要紧的一件，"
             "用朋友的口吻提一句，带一个马上能做的小选择（「要不要现在打个卡？」「要不要把日子往后挪一周？」）。"
             "TA 在难过、倾诉时先陪着，别提；这次对话里已经提过的别再提。")


def context_note(retrieved: list[dict], store: Store | None = None) -> str:
    """每轮都在变的部分（时间、和这句话相关的记忆、值得留意的事）放在对话后面，前面的长内容才能被缓存复用。"""
    t = now()
    s = f"现在是 {t:%Y-%m-%d %H:%M}（周{WEEKDAYS[t.weekday()]}）。用户消息前的［日期 时间］、对话中间「界面上显示的卡片」这类系统消息都是标注，回复里不要模仿、不要提。"
    if store is not None:   # 最近几条用过的表情：这次别再用，免得总是同一个（人机感）
        used = []
        for m in [m for m in store.messages(8) if m["role"] == "assistant" and m["content"]][-3:]:
            used += EMOJI.findall(m["content"])
        if used:
            lively = (store.profile().get("persona") or "") == "lively"
            s += (f"\n你最近几条回复用过这些表情：{''.join(dict.fromkeys(used))}。这次别再用它们"
                  + ("，想带就换一个贴这件事的。" if lively else "；这条不带表情也很好。"))
    if store is not None:
        items = nudges.attention(store, t, limit=5)
        if items and items[0]["kind"] != "rest":
            quiet = (store.profile().get("care_style") == "quiet")
            s += ("\n\n## 从 TA 的计划和记录里看到、可以顺手提的事\n" + nudges.as_text(items) + "\n" + NUDGE_USE
                  + ("\nTA 选了「中断时先不提」：除非 TA 自己聊到计划，否则别提这些。" if quiet else ""))
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

def _match_wish(store: Store, ws: list[dict], hint: str, strict: bool = False) -> dict | None:
    """按名字找愿望；没给名字就用 TA 正在看的那个。strict：给了名字却找不到时返回 None，不悄悄换成别的愿望。"""
    hit = next((x for x in ws if hint and (hint in x["title"] or x["title"] in hint or hint in x["label"])), None)
    if hit or (strict and hint.strip()):
        return hit
    return journey.current(store) or ws[0]


def _pending_plan(store: Store, wish_id: str) -> dict | None:
    """最近还没点的、给这个愿望的那张安排卡片里的内容。"""
    for m in reversed(store.messages(12)):
        for a in reversed((m.get("meta") or {}).get("acts") or []):
            if isinstance(a, dict) and a.get("ask") == "plan" and a.get("wish_id") == wish_id and not a.get("state"):
                return a.get("plan") or {}
    return None


def _plan_titles(plan: dict) -> set:
    return {(k, str(i.get("title") or "").strip()) for k in ("milestones", "habits", "steps") for i in plan.get(k) or [] if isinstance(i, dict)}


def _no_wish(hint: str) -> dict:
    return {"ok": False, "error": f"还没有叫「{clip(hint, 20)}」的愿望。TA 想新开一个，就先 edit_plan(add, kind=wish) 建好再提议",
            "tip": f"还没有「{clip(hint, 12)}」这个愿望"}

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


# 改动 TA 自己写下的东西（计划、好消息、提醒、设置）之前要有 TA 的意思：
# 这一句里有要改动的说法；或者是一句简短的同意，回应的是小光上一句的提问（「要我帮你删掉吗？」「可以」）。
# 只是聊天、倾诉时（「最近好累」），小光不能自己动手，只能先问。
CONSENT_TOOLS = {"edit_plan", "edit_good_news", "edit_task", "update_settings", "adjust_habit"}
EDIT_ASK = re.compile(r"删|去掉|移除|拿掉|不要了|不用了|取消|收起|撤|恢复|找回|改|换成|换个|换一|调|挪|推迟|推后|往后推|提前|延后|往后|往前"
                      r"|加|添|增|新建|新开|设成|设为|设置|定在|定个|定一个|定成|放进|放到|写进|写上|记下|记到|记成|记一|标成|标记"
                      r"|放一放|先放|放回|不做了|先不做|标一下|标上|打卡|记上|记一下|完成了|做完|搞定|到达|达成|关掉|关了|关闭|打开|开启|停掉|暂停|重命名|名字|叫我|叫你|频率|日期|几号"
                      r"|少一点|少点|少做|减|降|轻一点|帮我|帮忙|麻烦|弄一下|合并|重复了|不偷懒|不休息|别催|催我|督促|找我|提醒我"
                      r"|性格|温柔|活泼|有条理|主题|氛围"
                      r"|就叫|叫它|改叫|取名|起名|命名|开一个|再开|开个|立个|再来一个|新的愿望"
                      r"|新愿望|愿望[:：是]|想(要)?(做|开|立|定|许|建|搞|弄)(一)?个|开始(练|学|做|健身|跑)|想(练|学)")
AGREE_START = re.compile(r"(好|行|可以|嗯|对|是|要|ok|okay|当然|没问题|就这样|那就|同意|确定|确认|没错|中|成|去吧|弄吧|来吧|拜托|麻烦)", re.I)
NEGATE = re.compile(r"不|别|算了|等等|再想想")
# 让小光「删一个」却没点名：要删哪个得先问（「删掉一个吧」「帮我精简一下」）
VAGUE_REMOVE = re.compile(r"(删|去掉|收起|砍)[^，。！？,.!?]{0,3}(一个|一条|一项|一些|几个|哪个|其中)|精简|合并")


# TA 自己说了要歇（偷懒日只在这时设；只说累、烦不算）
REST_ASK = re.compile(r"偷懒|偷个懒|休息|歇|躺平|摆烂|放假|放个假|不想(做|干|动)|什么都不(想)?(做|干)|不干了|罢工|今天就这样|啥也不(想)?干")

# 说了「做完了」这类话：和小步的名字有一点对得上就行；没说，就要对得上得多
DONE_WORD = re.compile(r"完成|做完|搞定|弄完|写完|看完|交了|做了|做到|打勾|勾上|勾掉|那一步|这一步|那步|这步|小步")


def _overlap(a: str, b: str) -> float:
    x, y = set(tokens(a)), set(tokens(b))
    return 2 * len(x & y) / (len(x) + len(y)) if x and y else 0.0


def step_said_done(store: Store, user_text: str, title: str) -> bool:
    """TA 这句话是不是在说「这一步做完了」。防止把另一件相似的事（课上回答问题 ≠ 小组里提问）记成完成。"""
    t = (user_text or "").strip()
    if not t:
        return True       # 不是从聊天来的调用（测试、界面）不拦
    last_ai = next((m["content"] for m in reversed(store.messages(6)) if m["role"] == "assistant" and m["content"]), "")
    if _overlap(last_ai, title) >= 0.5 or title in last_ai:      # 小光刚问过「是不是这一步」
        if _agreeing(store, t) or DONE_WORD.search(t):
            return True
    sim = _overlap(t, title)
    return sim >= 0.35 or (bool(DONE_WORD.search(t)) and sim >= 0.15)


def _agreeing(store: Store, t: str) -> bool:
    if not (len(t) <= 20 and AGREE_START.match(t) and not NEGATE.search(t)):
        return False
    recent = [m for m in store.messages(6) if m["content"]]
    last_ai = next((m["content"] for m in reversed(recent) if m["role"] == "assistant"), "")
    return bool(re.search(r"[吗？?]", last_ai))


def consented(store: Store, user_text: str, removing: bool = False, routed: bool = False) -> bool:
    """routed：路由（core/router.py，模型判断）认为 TA 这一句就是要做这件事。删除照旧只认 TA 的原话。"""
    t = (user_text or "").strip()
    if removing and VAGUE_REMOVE.search(t):
        return _agreeing(store, t)
    return bool(EDIT_ASK.search(t)) or _agreeing(store, t) or (routed and not removing)


def _pick_task(uid: str, ref: str, prefer: bool | None = None) -> dict | None:
    ts = tasks.list_for(uid)
    if prefer is not None:
        ts = sorted(ts, key=lambda t: t["enabled"] != prefer)
    return next((t for t in ts if t["id"] == (ref or "").strip()), None) or journey._pick(ts, ref)


SETTING_LABEL = {"nickname": "称呼", "agent_name": "我的名字", "persona": "我的性格", "proactive": "主动找你的频率",
                 "care_style": "你中断时我怎么做", "town_name": "小镇的名字", "theme": "页面氛围", "schedule_hint": "作息",
                 "boundaries": "不想聊的话题", "chat_style": "聊天时我怎么陪你", "remind_pref": "提醒的频率",
                 "energy_time": "比较有精神的时候"}
SETTING_VALUE = {"persona": {"gentle": "温柔", "clear": "有条理", "lively": "活泼"},
                 "proactive": {"more": "多一点", "normal": "刚好", "less": "少一点", "off": "不主动找"},
                 "care_style": {"nudge": "轻轻提醒", "analyze": "一起找原因", "quiet": "先不提"},
                 "theme": {"forest": "森林夜", "midnight": "深空", "paper": "晨光", "peach": "暖阳", "mist": "海雾"},
                 "remind_pref": {v: v for v in ("每天", "每周几次", "每周一次", "暂时不需要提醒")},
                 "energy_time": {v: v for v in ("早上", "下午", "晚上", "不太固定")}}


def update_settings(store: Store, args: dict) -> dict:
    patch, changed = {}, []
    for k in SETTING_LABEL:
        v = args.get(k)
        if v in (None, "", []):
            continue
        if k in SETTING_VALUE:
            if v not in SETTING_VALUE[k]:
                return {"ok": False, "error": f"{SETTING_LABEL[k]}没有这个选项"}
            shown = SETTING_VALUE[k][v]
        elif k == "boundaries":
            v = [clip(str(x).strip(), 20) for x in (v if isinstance(v, list) else [v]) if str(x).strip()][:6]
            shown = "、".join(v)
        else:
            v = clip(str(v).strip(), 10 if k == "town_name" else 20 if k in ("nickname", "agent_name") else 30 if k == "chat_style" else 60)
            shown = v
        patch[k] = v
        changed.append(f"{SETTING_LABEL[k]}改成「{shown}」")
    if not patch:
        return {"ok": False, "error": "没有要改的设置"}
    store.set_profile(patch)
    store.log("profile", "小光帮你改了设置：" + "，".join(changed))
    out = {"ok": True, "changed": changed}
    if patch.get("proactive") == "more" and not any(t["enabled"] and t["kind"] == "ai" for t in tasks.list_for(store.uid)):
        out["next"] = "TA 想被督促：接着问一句要不要每天定个时间（比如晚上 9 点）由你来看看当天的计划进度，TA 同意就 schedule_task(kind=ai, repeat=daily)"
    return out


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


def run_tool(store: Store, name: str, args: dict, user_text: str = "", routed: str = "") -> dict:
    """routed：这一句路由判断要做的工具名（没有就是空），许可检查用。"""
    # 「我到了 / 做到了」只是报告一件事实（和 complete_step 一样），不算改 TA 写下的东西
    reached = name == "edit_plan" and args.get("kind") == "milestone" and args.get("status") == "done" and         not any(args.get(k) for k in ("title", "due_day", "due_in_days", "shift_days", "delete")) and args.get("action") in (None, "", "change")
    removing = args.get("action") in ("remove", "delete") or bool(args.get("delete"))
    if name in CONSENT_TOOLS and user_text and not reached and not consented(store, user_text, removing, routed == name):
        return {"ok": False, "skipped": True, "need_consent": True,
                "error": "TA 这句话没让你改。先用一句话说清你打算怎么改，问 TA 要不要；TA 同意了再改。这一轮别说已经改好了。"}
    if name == "look_up":
        return lookup.look_up(store, str(args.get("area") or "plan"), str(args.get("query") or ""))
    if name == "app_guide":
        return guide.guide(str(args.get("topic") or "overview"))
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
        kind = args.get("kind") or "insight"
        near = store.similar(text, k=1)
        if near and near[0]["sim"] >= 0.75:          # 已经记着几乎一样的一条：不重复记（mem0 的 NOOP）
            m = near[0]
            if m["status"] == "guess":
                store.update_memory(m["id"], status="active", reason="user_confirmed", evidence=user_text)
            store.c.execute("UPDATE memory SET source='chat:explicit' WHERE id=?", (m["id"],))
            return {"ok": True, "memory": store.get_memory(m["id"]), "note": "本来就记着这条，没有重复记"}
        if near and near[0]["sim"] >= 0.5 and near[0]["kind"] == kind:   # 同一件事、多了细节：并进去（UPDATE）
            m = store.update_memory(near[0]["id"], text=text, status="active", reason="user_added_detail", evidence=user_text)
            store.c.execute("UPDATE memory SET source='chat:explicit' WHERE id=?", (m["id"],))
            store.log("memory", "记住了：" + m["text"])
            return {"ok": True, "memory": m, "updated_from": near[0]["text"]}
        m = store.add_memory(text, kind, "chat:explicit")   # 新的一条（ADD）
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
        about = str(args.get("about") or "")
        new_text = clip(str(args.get("new_text") or ""), 200).strip()
        quote = clip(str(args.get("quote") or ""), 200)
        hits = store.similar(about, k=3) or store.similar(new_text, k=3)
        if not hits or hits[0]["sim"] < 0.15:
            return {"ok": False, "error": "没找到要改的那条记忆",
                    "have": [m["text"] for m in store.memories(statuses=("active", "guess"), limit=8)]}
        if len(hits) > 1 and hits[0]["sim"] - hits[1]["sim"] < 0.05 and hits[1]["sim"] > 0.3:
            return {"ok": False, "error": "有两条很像，先问 TA 指的是哪一条", "have": [m["text"] for m in hits[:3]]}
        m = hits[0]
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
        cand = store.find_todo_step(args.get("step_id"), args.get("title"))
        if not cand:
            return {"ok": False, "error": "没找到这一步"}
        if not step_said_done(store, user_text, cand["title"]):
            return {"ok": False, "skipped": True,
                    "error": f"TA 这句话和「{cand['title']}」对不上，别替 TA 打勾。如果 TA 说的是一件新做成的事，用 propose_moment 提议留在轨迹上；"
                             f"如果觉得可能就是这一步，问一句「是不是『{clip(cand['title'], 16)}』这一步做完啦？」，TA 说是再打勾。"}
        s = store.complete_step(cand["id"])
        xp = growth.award(store, "action", ref="step:" + s["id"], note="完成：" + s["title"])
        store.log("plan", "完成了：" + s["title"])
        out = {"ok": True, "step": s, "xp": xp}
        cleared = journey.steps_cleared(store, s)
        if cleared:
            out["cleared"] = cleared
            out["next"] = (f"这是「{cleared['title']}」最后一个待做的小步，这一段的 {cleared['done']} 个小步都做完了。"
                           "真心祝贺 TA，说具体一点；再问一句要不要一起想想接下来的一两个小步（TA 同意就用 propose_plan 提议，别直接加）")
        return out
    if name == "log_good_news":
        text = clip(str(args.get("text") or ""), 200)
        if not text:
            return {"ok": False, "error": "内容为空"}
        r = store.add_record("good", text)
        xp = growth.award(store, "good", ref="rec:" + r["id"], note="好消息")
        store.log("record", "收下一条好消息")
        return {"ok": True, "record": r, "xp": xp, "count": store.counts()["good"]}
    if name == "edit_good_news":
        rows = [dict(r) for r in store.c.execute("SELECT * FROM record WHERE type='good' ORDER BY day DESC, created_at DESC LIMIT 300")]
        for r in rows:
            r["title"] = r["text"]
        r = journey._pick(rows, str(args.get("target") or ""))
        if not r:
            return {"ok": False, "error": "没找到这条好消息", "have": [f"{x['day'][5:]} {clip(x['text'], 20)}" for x in rows[:8]]}
        if args.get("action") == "remove":
            with store.lock:
                store.c.execute("DELETE FROM record WHERE id=?", (r["id"],))
            store.log("record", "删掉了一条好消息：" + clip(r["text"], 30))
            return {"ok": True, "removed": True, "text": r["text"], "changed": ["删掉了"]}
        fields, changed = {}, []
        text = clip(str(args.get("text") or "").strip(), 200)
        if text and text != r["text"]:
            fields["text"] = text; changed.append("改成「" + clip(text, 30) + "」")
        if not fields:
            return {"ok": False, "error": "没有要改的内容"}
        with store.lock:
            store.c.execute("UPDATE record SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), r["id"]))
        store.log("record", "改了一条好消息")
        return {"ok": True, "text": fields.get("text", r["text"]), "changed": changed}
    if name == "log_lazy_day":
        if args.get("undo"):
            if not journey.is_resting(store):
                return {"ok": False, "error": "今天本来就不是偷懒日"}
            with store.lock:
                store.c.execute("DELETE FROM record WHERE type='rest' AND day=?", (day_key(),))
            store.log("rest", "今天不偷懒了")
            return {"ok": True, "undone": True, "note": "习惯和小步都回来了"}
        if user_text and not (REST_ASK.search(user_text) or _agreeing(store, user_text)):
            # 只说了累、烦、难过：别替 TA 决定休息，先问一句
            return {"ok": False, "skipped": True,
                    "error": "TA 只是说累或者难受，没说要休息。别替 TA 设偷懒日：先陪着，最多问一句「今天要不要给自己放个假？」，TA 说好再设。"}
        if journey.is_resting(store):
            return {"ok": True, "already": True, "note": "今天已经是偷懒日了"}
        note = clip(str(args.get("note") or "").strip(), 40)
        r = store.add_record("rest", "今天偷个懒" + (f"：{note}" if note else ""))
        store.log("rest", r["text"])
        growth.settle_daily(store)   # 偷懒日：每日任务里行动那项先暂停，不挡全勤
        return {"ok": True, "record": r, "paused": [h["title"] for h in journey.habits(store)][:5],
                "note": "当天的习惯和小步都暂停，什么进度都不扣。界面上会给出：明天继续 / 调整计划 / 聊聊天"}
    if name == "edit_plan":
        keys = ("title", "due_day", "due_in_days", "shift_days", "freq", "per_week", "status", "vision_text", "now_text",
                "text", "feeling", "day", "wish", "why", "delete")
        patch = {k: args.get(k) for k in keys if args.get(k) not in (None, "")}
        try:
            out = journey.edit_item(store, str(args.get("kind") or ""), str(args.get("target") or ""), patch,
                                    str(args.get("action") or ""))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if out.get("ok"):
            out["action"] = str(args.get("action") or ("remove" if args.get("delete") else "change"))
            store.log("plan", f"小光帮你处理了「{out['title']}」：" + "，".join(out["changed"]))
            if out.get("reached"):
                out["xp"] = growth.award(store, "action", ref="ms:" + out["id"], note="到达：" + out["title"])
            if out.get("new_moment"):
                out["xp"] = growth.award(store, "good", ref="moment:" + out["id"], note="留下一个瞬间")
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
    if name == "kick_history":
        hits = kickstart.history(store, str(args.get("query") or ""), k=4)
        return {"ok": True, "entries": [{"date": h["day"], "record": h["text"]} for h in hits],
                "note": "" if hits else "没有存下的记录：只有 TA 在两分钟启动结束时勾了「让小光记住这次体验」才会留下。照实说，别编"}
    if name == "list_tasks":
        return {"ok": True, "tasks": [{"title": t["title"], "when": t["when"], "on": t["enabled"]} for t in tasks.list_for(store.uid)]}
    if name == "edit_task":
        act = str(args.get("action") or "")
        t = _pick_task(store.uid, str(args.get("target") or ""), prefer={"on": False, "off": True}.get(act))
        if not t:
            return {"ok": False, "error": "没找到这个定时任务", "have": [x["title"] for x in tasks.list_for(store.uid)]}
        try:
            if act in ("on", "off"):
                tasks.set_enabled(store.uid, t["id"], act == "on")
                done = "重新打开了" if act == "on" else "关掉了，以后不会再响"
            elif act == "delete":
                tasks.delete(store.uid, t["id"])
                done = "删掉了"
            elif act == "change":
                patch = {k: args[k] for k in ("title", "message", "time", "repeat", "days") if args.get(k) not in (None, "", [])}
                if not patch:
                    return {"ok": False, "error": "没有要改的内容"}
                t = tasks.edit(store.uid, t["id"], patch) or t
                done = f"改好了：{t['when']}"
            else:
                return {"ok": False, "error": "不认识的操作"}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        store.log("task", f"例行任务「{t['title']}」{done}")
        return {"ok": True, "task": t["title"], "done": done}
    if name == "update_settings":
        return update_settings(store, args)
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
            return {"ok": False, "error": "还没有愿望。TA 想要哪个愿望，就先 edit_plan(add, kind=wish) 建好再提议", "tip": "还没有愿望"}
        if not any(args.get(k) for k in ("milestones", "habits", "steps")):
            return {"ok": False, "error": "这次调用没有内容：写上愿望名字和要提议的里程碑 / 习惯 / 小步，再调用一次", "tip": "这一版没写好"}
        w = _match_wish(store, ws, str(args.get("wish") or ""), strict=True)
        if not w:
            return _no_wish(str(args.get("wish") or ""))

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
            return {"ok": False, "error": "这些路径上都已经有了。想改已有的那几项，就用 edit_plan 直接改", "already": dropped,
                    "tip": "这些在路上已经有了"}
        for h in plan["habits"]:
            h["freq"] = "weekly" if h.get("freq") == "weekly" else "daily"
        if _plan_titles(plan) == _plan_titles(_pending_plan(store, w["id"]) or {}):
            return {"ok": True, "unchanged": True,
                    "note": "和上面那张还没点的卡片一模一样，没有再出一张。请 TA 在那张卡片上点「加进计划」；TA 想改哪一项再出新的一版"}
        return {"ok": True, "pending": True, "note": "只是提议，用户勾选后才会加入计划",
                "already_on_path": dropped, "wish_id": w["id"], "wish_title": w["title"], "plan": plan, "why": clip(str(args.get("note") or ""), 80)}
    if name == "add_habit":
        ws = journey.wishes(store)
        if not ws:
            return {"ok": False, "error": "还没有愿望", "tip": "还没有愿望"}
        w = _match_wish(store, ws, str(args.get("wish") or ""), strict=True)
        if not w:
            return _no_wish(str(args.get("wish") or ""))
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
    if name == "suggest_feature":
        f = acts.FEATURES.get(str(args.get("feature") or ""))
        if not f:
            return {"ok": False, "error": "没有这个功能", "have": list(acts.FEATURES)}
        return {"ok": True, "feature": args.get("feature"), "title": f["title"],
                "note": "界面会出一个入口，TA 点「开始」才开始。回复里一句话说为什么推荐就好，别说已经打开了。"}
    if name == "start_scene":
        sid = args.get("scene")
        if sid == "kickstart":
            return {"ok": True, "scene": "kickstart", "title": "两分钟启动", "task": clip(str(args.get("task") or ""), 40),
                    "note": "界面会打开两分钟启动，你只需用一句话陪 TA 开始。"}
        if sid not in SCENES:
            return {"ok": False, "error": "unknown scene"}
        return {"ok": True, "scene": sid, "title": SCENES[sid]["title"],
                "note": "界面会接手引导，你只需用一句话邀请对方开始。"}
    if name == "get_growth":
        g = growth.state(store, consume=False)   # 升级的庆祝留给界面
        t = town.state(store)
        lv = g["level"]
        afford = sorted((c for c in t["catalog"] if c["unlocked"] and c["price"] <= t["coins"] and c["cat"] == "build"),
                        key=lambda c: -c["price"])
        return {"ok": True, "growth": {
                    "total": g["total"], "level": lv["lv"], "to_next_level": lv["to_next"],
                    "today_xp": g["today"]["total"], "coins": g["coins"], "coins_today": g["coins_today"],
                    "daily": [{"task": x["label"], "done": x["done"], "rest": x["rest"], "coins": x["coins"]} for x in g["daily"]["tasks"]],
                    "daily_bonus": g["daily"]["bonus"],
                    "town": {"name": t["name"], "land": f"{t['size']}×{t['size']}", "built": [i["name"] for i in t["items"] if i["source"] != "gift"][-12:],
                             "warehouse": [i["name"] for i in t["warehouse"]], "can_afford": [c["name"] for c in afford[:3]],
                             "next_unlock": t["next"]}},
                "summary": town.summary(store), "rules": growth.rules_text()}
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

ROUTER_WAIT = 8   # 秒：第一轮的第一个字到了，最多再等路由这么久


def _check_route(stream, rt, route: dict, msgs: list, tools: list):
    """第一轮的第一个事件先不给用户看，等路由的结论（core/router.py）：
    TA 明确要现在做一件事、而模型这一轮不是在调那个工具，就丢掉这一轮，要求先调它重来。
    这样不会出现「嘴上说删掉了 / 记下了，其实没调工具」。其余情况原样往下走。"""
    first = next(stream, None)
    rt.join(timeout=ROUTER_WAIT)
    must = route.get("tool") or ""
    if must and any(t["function"]["name"] == must for t in tools):
        calling = first and first[0] == "tool_calls" and any(c["name"] == must for c in first[1])
        if not calling:
            stream.close()
            return llm.stream_chat(msgs, tools=tools, tool_choice=must)
    return itertools.chain([first] if first else [], stream)

def chat(store: Store, user_text: str, *, extract: bool = True, topic: str = ""):
    """topic：TA 在点子里点的话题 id（core/topics.py）。话题进行中，提示词接在系统提示后面，不打开别的练习、不走路由。"""
    user_text = clip(user_text, 2000)
    if topic and topics.start(store, topic):
        store.add_msg("user", user_text, {"topic": topic})
    else:
        store.add_message("user", user_text)
    tp = topics.active(store)
    store.set_profile({"last_chat_at": now().isoformat(timespec="seconds")})
    store.mark_inbox_seen()  # TA 回来说话了，之前的主动消息就算看过了
    # 每天第一次来聊天算一次签到；award() 对同一天同一个 ref 是幂等的
    checkin = growth.award(store, "checkin", ref="day:" + now().strftime("%Y-%m-%d"), note="今天来聊了")
    all_acts: list[dict] = []   # 这一轮要画的东西（core/acts.py），也存进这条回复的 meta，重看聊天时还在
    if checkin.get("amount"):
        v = acts.view(store, "checkin", {}, checkin, {})
        yield ("tool", {"name": "checkin", "args": {}, "result": checkin, "acts": v, "act_start": len(all_acts)})
        all_acts += v
    yield ("mood", {"id": MOODS["thinking"]})

    # 检索：这一句 + TA 上一句（接着上一句说「那个呢」时也能对上）；一条都对不上就退回最近的几条；已经钉在提示里的不重复放
    prev_user = next((m["content"] for m in reversed(store.messages(6)[:-1]) if m["role"] == "user" and m["content"]), "")
    pinned_ids = {m["id"] for m in store.pinned()}
    retrieved = [m for m in store.search(user_text + " " + clip(prev_user, 200), k=8, include_guess=True, fallback=True)
                 if m["id"] not in pinned_ids][:6]
    if retrieved:
        yield ("mood", {"id": MOODS["recall"]})
    yield ("context", {"memories": [{"id": m["id"], "text": m["text"], "status": m["status"],
                                     "kind": m["kind"], "date": m["created_at"][:10]} for m in retrieved]})

    hist = history(store)
    msgs = ([{"role": "system", "content": system_prompt(store, retrieved) + (chr(10) * 2 + topics.prompt(tp) if tp else "")}] + hist[:-1]
            + [{"role": "system", "content": context_note(retrieved, store)}] + hist[-1:])
    reply, tool_log, mood_set = "", [], False
    # 路由判断和第一轮回复同时开始：多数时候不需要做事，路由的那点时间就藏在等第一个字里了
    route: dict = {}
    rctx = router.context(store)
    rt = threading.Thread(target=lambda: route.update(tool="" if tp else router.decide(rctx, user_text)), daemon=True)
    rt.start()
    blocked: set[str] = {"start_scene"} if tp else set()   # 这一轮被拦下的写入工具，不再给模型反复重试；话题里不开别的练习
    try:
        for _round in range(MAX_ROUNDS + 1):
            calls, started, said = None, False, ""
            tools = [t for t in TOOLS if t["function"]["name"] not in blocked] if _round < MAX_ROUNDS else None
            stream = llm.stream_chat(msgs, tools=tools)
            if _round == 0 and tools:
                stream = _check_route(stream, rt, route, msgs, tools)
            for kind, val in stream:
                if kind == "text":
                    if not started:
                        started = True
                        if not mood_set:
                            yield ("mood", {"id": MOODS["replying"]})
                    reply += val
                    said += val
                    yield ("delta", {"text": val})
                elif kind == "tool_calls":
                    calls = val
            if not calls:
                break
            msgs.append({"role": "assistant", "content": said or None,   # 这一轮已经说出口的话也带上，免得模型再说一遍
                         "tool_calls": [{"id": c["id"] or f"call_{i}", "type": "function",
                                         "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                                        for i, c in enumerate(calls)]})
            for i, c in enumerate(calls):
                args = _parse_args(c["arguments"])
                if c["name"] == "search_memory":
                    yield ("mood", {"id": MOODS["searching"]})
                snap = acts.before(store, c["name"], args)
                result = run_tool(store, c["name"], args, user_text, route.get("tool") or "")
                tool_log.append({"name": c["name"], "args": args, "result": result})
                if result.get("skipped"):
                    blocked.add(c["name"])
                elif not result.get("unchanged"):
                    v = acts.view(store, c["name"], args, result, snap)
                    yield ("tool", {"name": c["name"], "args": args, "result": result, "acts": v, "act_start": len(all_acts)})
                    all_acts += v
                if result.get("ok") and c["name"] in TOOL_MOOD:
                    mood_set = True
                    yield ("mood", {"id": MOODS[TOOL_MOOD[c["name"]]]})
                msgs.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}",
                             "content": json.dumps(result, ensure_ascii=False)[:6000]})
    except llm.LLMError as e:
        if not reply:
            reply = "我这边连不上了，稍等一下再试试？你刚才说的我先记在这里。"
            yield ("delta", {"text": reply})
        yield ("error", {"message": str(e)[:200]})

    extra = acts.infer_entry(reply, all_acts)   # 嘴上推荐了练习、却没调 suggest_feature：补上入口
    if extra:
        yield ("tool", {"name": "suggest_feature", "args": {"feature": extra["feature"]}, "result": {"ok": True},
                        "acts": [extra], "act_start": len(all_acts)})
        all_acts.append(extra)
    meta = {"memories": [m["id"] for m in retrieved], "tools": [{"name": t["name"], "args": t["args"]} for t in tool_log],
            "acts": all_acts}
    replace_old_plans(store, all_acts)
    mid = store.add_message("assistant", reply, meta)
    yield ("done", {"message_id": mid["id"]})
    yield ("mood", {"id": MOODS["idle"]})

    # 隐性记忆改为日终统一整理（core/digest.py）；逐轮抽取只在显式打开时运行
    if extract and reply and os.environ.get("MANIFEST_TURN_EXTRACT") == "1":
        threading.Thread(target=_extract_bg, args=(store.uid, user_text, reply), daemon=True).start()


def replace_old_plans(store: Store, new_acts: list[dict]) -> None:
    """这一轮给某个愿望出了新的一版安排：之前还没点的同一个愿望的安排卡片标成「已换成新的一版」，不能再点。"""
    wids = {a.get("wish_id") for a in new_acts if a.get("type") == "ask" and a.get("ask") == "plan" and a.get("wish_id")}
    if not wids:
        return
    rows = store.c.execute("SELECT id, meta FROM msg WHERE role='assistant' ORDER BY created_at DESC LIMIT 30").fetchall()
    for r in rows:
        meta = loads(r["meta"], {}) or {}
        hit = False
        for a in meta.get("acts") or []:
            if a.get("type") == "ask" and a.get("ask") == "plan" and a.get("wish_id") in wids and not a.get("state"):
                a["state"] = "replaced"
                hit = True
        if hit:
            with store.lock:
                store.c.execute("UPDATE msg SET meta=? WHERE id=?", (dumps(meta), r["id"]))


def _extract_bg(uid: str, user_text: str, reply: str) -> None:
    try:
        with Store(uid) as s:
            memory.extract_and_apply(s, user_text, reply)
    except Exception as e:  # never let background memory crash the server
        print("[memory] extract failed:", e)
