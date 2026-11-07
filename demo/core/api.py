"""Pieces shared by server.py and routes.py."""
from __future__ import annotations

from . import academy, cheer, finds, weekly, growth, journey, kickstart, portrait, scenes, scheduler, tasks, town
from .store import Store

VERSION = "3.12.0"

# 「点子」：点一下就进入一个可体验的 Agent 场景。每一项都必须有真实可玩的
# 后端状态机，不做纯展示的假卡片。
IDEAS = [
    {"id": "relearn", "title": "聊聊现在的你", "scene": "relearn", "minutes": 2, "cta": "开始聊聊",
     "group": "聊聊", "prompt": "最近的我有些变化，想和你重新聊聊。",
     "desc": "最近的你有没有一些变化？我们可以重新聊聊你的习惯和喜好。"},
    {"id": "seven_steps_lite", "title": "聊聊你的愿望", "scene": "seven_steps_lite", "minutes": 2,
     "group": "聊聊", "prompt": "陪我聊聊我最近想实现的愿望。",
     "desc": "我们一起聊聊，你最近想实现的愿望吧～"},
    {"id": "kickstart", "title": "两分钟启动", "scene": "", "kind": "kick", "minutes": 2,
     "group": "日常", "prompt": "有件事想做，但一直开始不了。",
     "desc": "把任务变得不靠意志也能做。"},
    {"id": "meditation", "title": "冥想体验：遇见更好的自己", "scene": "meditation", "minutes": 3,
     "group": "日常", "prompt": "陪我放松几分钟，想象一下期待的生活。",
     "desc": "花几分钟放松一下，想象你期待的生活。"},
    {"id": "gratitude", "title": "三分钟感恩", "scene": "gratitude", "minutes": 3,
     "group": "日常", "prompt": "我想记下三件已经发生的好事。",
     "desc": "小到一杯热水也算。练习的是注意力。"},
]


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
        # 陪伴偏好：设置里那张「陪伴偏好」表单用这些选项
        "chat_style": p.get("chat_style") or "",
        "remind_pref": p.get("remind_pref") or "",
        "energy_time": p.get("energy_time") or "",
        "options": {"chat_style": [shown for shown, _ in scenes.CHAT_STYLES.values()],
                    "remind_pref": scenes.REMIND, "energy_time": scenes.ENERGY},
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
