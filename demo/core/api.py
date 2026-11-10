"""Pieces shared by server.py and routes.py."""
from __future__ import annotations

from . import academy, cheer, finds, weekly, growth, journey, kickstart, portrait, scenes, scheduler, tasks, topics, town
from .store import Store

VERSION = "3.20.4"

# 「点子」：点一下就进入一个可体验的 Agent 场景。每一项都必须有真实可玩的
# 后端状态机，不做纯展示的假卡片。
IDEAS = [
    {"id": "seven_steps_lite", "title": "显化你的愿望", "scene": "seven_steps_lite", "kind": "tune", "minutes": 4, "cta": "开始显化",
     "group": "愿望", "prompt": "想用显化七步，把一个愿望想清楚、更相信它。",
     "desc": "跟着显化七步走一遍：说清它，消除怀疑，今天就行动，把它交给时间。"},
    {"id": "relearn", "title": "调整现有计划", "scene": "relearn", "kind": "tune", "minutes": 2, "cta": "调一调",
     "group": "愿望", "prompt": "最近状态变了，想把计划调一调。",
     "desc": "说说现在的你，小光按你的状态一键调整现有计划。"},
    {"id": "kickstart", "title": "两分钟启动", "scene": "", "kind": "kick", "minutes": 2,
     "group": "日常", "prompt": "有件事想做，但一直开始不了。",
     "desc": "把任务变得不靠意志也能做。"},
    {"id": "meditation", "title": "冥想体验：遇见更好的自己", "scene": "meditation", "minutes": 3,
     "group": "日常", "prompt": "陪我放松几分钟，想象一下期待的生活。",
     "desc": "花几分钟放松一下，想象你期待的生活。"},
    {"id": "gratitude", "title": "三分钟感恩", "scene": "gratitude", "minutes": 3,
     "group": "日常", "prompt": "我想记下三件已经发生的好事。",
     "desc": "小到一杯热水也算。练习的是注意力。"},
] + topics.ideas()   # 「话题」：点了直接去对话，小光照话题陪你聊；只在点子里，小光不主动推荐


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u.get("username"), "kind": u.get("kind")}


def preferences(p: dict) -> dict:
    return {
        "care_style": p.get("care_style") or "",
        "care_label": {"nudge": "轻轻提醒我", "analyze": "一起找原因", "quiet": "先别提"}.get(p.get("care_style") or "", "还没选"),
        "pace": p.get("pace") or "gentle",
        "proactive": p.get("proactive") or "normal",
        "intent": p.get("intent_primary") or "",
        "why": p.get("intent_why") or "",
        "nickname": p.get("nickname") or "",
        "boundaries": p.get("boundaries") or [],
        # 陪伴偏好：设置里那张「陪伴偏好」表单（聊天时怎么陪 · 中断的时候 · 有精神的时候）用这些选项
        "chat_style": p.get("chat_style") or "",
        "energy_time": p.get("energy_time") or "",
        "options": {"chat_style": [shown for shown, _ in scenes.CHAT_STYLES.values()], "energy_time": scenes.ENERGY},
    }


def bootstrap(st: Store) -> dict:
    """Everything the client needs to render the whole shell in one request."""
    g = growth.state(st)          # 会结算每日任务、交出「升级了」的一次性标记，所以先于读画像
    p = st.profile()
    read = st.read_ids()
    return {
        "profile": {k: v for k, v in p.items() if k not in ("last_proactive_at",)},
        "growth": g,
        "town": town.state(st),
        "counts": st.counts(),
        "memories": st.memories(limit=120),
        "steps": st.steps(400),
        "records": st.records(400),
        "messages": st.messages(60),
        "activity": st.activity(30),
        "inbox": st.unseen_inbox(),
        "scene": st.scene_active(),
        "scenes": scenes.catalog(),
        "ideas": IDEAS,
        "academy": [{**a, "read": a["id"] in read} for a in academy.catalog()],
        "prefs": preferences(p),
        "journey": journey.board(st),
        "cheer": cheer.get(st),
        "tasks": tasks.list_for(st.uid),
        "digests": st.digests(21),       # 夜里整理 = 小光的笔记本，一晚一页
        "scene_counts": {r[0]: r[1] for r in st.c.execute(
            "SELECT scene, COUNT(*) FROM scene_run WHERE status='done' GROUP BY scene")},
        "revisions": st.revisions(60),
        "about": portrait.about(st),          # 我的空间 →「了解你」：六个大类
        "portrait": portrait.portrait(st),    # 小光眼中的你，一句话
        "notebook_weeks": weekly.view(st),    # 小光的笔记本：一周一页 + 这周到现在的碎片
        "finds": finds.view(st),              # 小光的发现（小光翻笔记本时注意到的事，core/finds.py）
        "kick_memories": kickstart.entries(st, 30),   # 《两分钟启动记忆》：我的空间 → 记忆 里能看、能删
        "proactive": dict(zip(("ok", "reason"), scheduler.should_reach_out(p, scheduler.waiting_unseen(st, p)))),
    }
