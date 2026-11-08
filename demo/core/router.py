"""每轮回复之前的一次小判断：TA 这一句是不是明确要小光**现在**做一件事。

是的话，小光这一轮第一次调用模型时就被要求先调这个工具（tool_choice），
这样「嘴上说记下了 / 删掉了，其实没调工具」就不会发生。不是、判断不了、或者超时，就照常让模型自己决定。

只挑「TA 自己说了就直接做」的那几种；含糊的、需要先问的、只是情绪，一律返回空——那些交给主对话去问。
"""
from __future__ import annotations

from . import journey, llm
from .util import clip

ACTIONS = {
    "log_lazy_day": "TA 说今天想躺平 / 休息 / 偷懒 / 什么都不干（只说累、焦虑、烦，不算）；或者说今天不偷懒了",
    "log_good_news": "TA 讲了一件已经发生的、开心的小事，和 TA 的愿望无关（抢到排骨、天气很好、收到礼物）",
    "propose_moment": "TA 讲了一件刚做的、和 TA 的愿望有关的具体的事，带着做了什么或什么感受（新做成的事默认是它）",
    "complete_step": "TA 说做完了计划里某个待做的小步：说的事要和下面「待做的小步」里的某一条对得上；对不上就不是它",
    "checkin_habit": "TA 说今天做了某个习惯里的事（今天去健身了、背完单词了）",
    "remember": "TA 明确让你记住一件关于 TA 的事（「记一下」「记住」「别忘了」）",
    "correct_memory": "TA 更正关于自己的一件事实（「我现在不喜欢 X 了」「交换的学校换成澳洲了」「那条不对」）。这是改记忆，不是改计划",
    "update_notebook": "TA 让你往你的笔记本里加、改、删",
    "schedule_task": "TA 让你到点提醒 TA，或者定时做一件事（「每天十点提醒我」）",
    "edit_task": "TA 让你关掉、打开、删掉、改时间一个已有的提醒 / 定时任务",
    "edit_plan": "TA 点名删除、修改、新增、找回计划里的愿望 / 里程碑 / 习惯 / 小步（「把 X 删了」哪怕带着「做不到」也是它），"
                 "说要新开一个愿望（「我想做个新愿望，是健身」），或者说到达了某个里程碑。"
                 "要改的东西得在上面的计划里：还在「小光刚提议、还没加进计划」里的，不是它",
    "propose_plan": "TA 想调整小光刚提议、还没加进计划的那套安排里的几项（「这个小步太麻烦」「习惯少一点」「换一个」）",
    "add_habit": "TA 明确要加一个重复做的事（「帮我加个每周跑步两次」）",
    "adjust_habit": "TA 说某个习惯太难、想调低频率或先停一停（TA 说了「删」，用 edit_plan）",
    "start_scene": "TA 点名要现在做一个练习：冥想、放松、感恩、两分钟启动、许个愿、让愿望落地",
    "get_growth": "TA 问金币、经验、等级怎么来、有多少，或者小镇、每日任务的规则和数字",
    "update_settings": "TA 要改设置或起名：怎么称呼 TA、你的名字或性格、小镇的名字（「小镇就叫 X 吧」）、主动消息多少、别催我、多来找我、提醒频率、页面氛围",
}

PROMPT = """你在帮陪伴 App 里的 AI 朋友「小光」做一个判断：TA 这一句，是不是明确要小光现在就替 TA 做一件事。

能直接做的事（TA 自己说了才算）：
{actions}

这些都返回空，交给小光自己去聊或者先问：
- TA 说得含糊（「这两个好像重复了」「帮我精简一下」），没点名要怎么改
- TA 只是在说情绪：累、难过、焦虑、烦（除非 TA 自己说了要休息 / 要做练习）
- 请小光帮忙规划、出主意、给建议
- 随口提到的事（「宿舍养了只猫」），没让记
- 闲聊、打招呼、问问题（问金币等级小镇除外）
- 小光帮不上的事（写代码、查天气）
如果小光上一句提议了一件事，TA 这一句说「好 / 可以 / 嗯 / 留吧」，就是同意：
「要不要把它留在轨迹上？」→ edit_plan；「要我帮你记下来吗？」→ remember；「要不要试试两分钟启动 / 冥想」→ start_scene；提议过的修改 → edit_plan。
小光刚提议了一套安排、TA 还没加进计划，TA 说「都可以 / 就这样 / 挺好 / 加进去吧」→ 返回空：TA 自己在卡片上点「加进计划」，不用再出一版。

TA 的愿望：{wishes}
计划里的习惯：{habits}
待做的小步：{steps}
小光刚提议、还没加进计划的安排：{pending}
小光上一句：{prev}
TA 这一句：{text}

只输出 JSON：{{"tool": "上面的工具名，或者空字符串"}}"""


def context(store) -> dict:
    """路由要看的几样东西。在主线程里读完（数据库连接不跨线程用），判断本身放到后台线程。"""
    return {
        "uid": store.uid,
        "wishes": [w["title"] for w in journey.wishes(store)],
        "habits": [h["title"] for h in journey.habits(store)][:10],
        "steps": [s["title"] for s in store.steps() if s["status"] == "todo"][:8],
        "prev": next((m["content"] for m in reversed(store.messages(6)) if m["role"] == "assistant" and m["content"]), ""),
        "pending": pending_plan(store),
    }


def pending_plan(store) -> list[str]:
    """最近几条回复里，还没点「加进计划 / 先不加」的那套提议里的各项。"""
    for m in reversed(store.messages(8)):
        for a in (m.get("meta") or {}).get("acts") or []:
            if isinstance(a, dict) and a.get("type") == "ask" and a.get("ask") == "plan" and not a.get("state"):
                p = a.get("plan") or {}
                return [i.get("title") or "" for k in ("milestones", "habits", "steps") for i in p.get(k) or [] if isinstance(i, dict)][:9]
    return []


def decide(ctx: dict, user_text: str, timeout: float = 8) -> str:
    try:
        prompt = PROMPT.format(
            actions="\n".join(f"- {k}：{v}" for k, v in ACTIONS.items()),
            wishes="、".join(ctx["wishes"]) or "（还没有）",
            habits="、".join(ctx["habits"]) or "（没有）", steps="、".join(ctx["steps"]) or "（没有）",
            pending="、".join(ctx.get("pending") or []) or "（没有）",
            prev=clip(ctx["prev"], 120) or "（没有）", text=clip(user_text, 300))
        out = llm.complete_json([{"role": "user", "content": prompt}], timeout=timeout, reasoning="none") or {}   # 路由要快：永远不思考
    except Exception as e:  # 判断失败就照常聊，不影响回复
        print("[router] failed:", e)
        return ""
    tool = out.get("tool") if isinstance(out, dict) else ""
    if not (isinstance(tool, str) and tool in ACTIONS):
        return ""
    # 没有待做的小步 / 没有习惯，就不可能「完成哪一步」「打哪个卡」：别逼着小光去调一个注定找不到的工具
    if (tool == "complete_step" and not ctx["steps"]) or (tool == "checkin_habit" and not ctx["habits"]) or (tool == "propose_plan" and not ctx.get("pending")):
        return ""
    return tool


def pick(store, user_text: str, timeout: float = 8) -> str:
    return decide(context(store), user_text, timeout)
