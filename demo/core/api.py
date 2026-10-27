"""Pieces shared by server.py and routes.py."""
from __future__ import annotations

from . import academy, growth, scenes, scheduler
from .store import Store

VERSION = "2.1.0"

# 「点子」：点一下就进入一个可体验的 Agent 场景。每一项都必须有真实可玩的
# 后端状态机，不做纯展示的假卡片。
IDEAS = [
    {"id": "relearn", "title": "重新认识我", "scene": "relearn", "minutes": 4,
     "group": "默契", "prompt": "如果你连续三天没完成计划，你希望我怎么办？",
     "desc": "六个生活里的小岔路。答完，我会按你选的方式陪你。"},
    {"id": "clarify", "title": "说清想要的", "scene": "clarify", "minutes": 3,
     "group": "愿望", "prompt": "用一句话描述你想要的生活画面。",
     "desc": "把「想变好」拆成一个能看见的具体早晨。"},
    {"id": "meditation", "title": "短冥想引导", "scene": "meditation", "minutes": 4,
     "group": "日常", "prompt": "陪我呼吸六轮，然后感受愿望实现时的身体。",
     "desc": "4 拍吸、4 拍呼。身体常常比头脑先知道。"},
    {"id": "gratitude", "title": "三分钟感恩", "scene": "gratitude", "minutes": 3,
     "group": "日常", "prompt": "我想记下三件已经发生的好事。",
     "desc": "小到一杯热水也算。练习的是注意力。"},
    {"id": "seven_steps_lite", "title": "七步轻走一遍", "scene": "seven_steps_lite", "minutes": 6,
     "group": "愿望", "prompt": "带我快速走一遍显化七步。",
     "desc": "澄清、信念、感受、行动、感恩、释放、见证，每步一句话。"},
    {"id": "know-me", "title": "你现在有多了解我", "scene": "", "minutes": 1,
     "group": "默契", "prompt": "__know_me__",
     "desc": "让我说你记得的我，也说出我不确定的部分。"},
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
        "pet_name": p.get("pet_name") or "小芽",
        "intent": p.get("intent_primary") or "",
        "why": p.get("intent_why") or "",
        "nickname": p.get("nickname") or "",
        "boundaries": p.get("boundaries") or [],
    }


def bootstrap(st: Store) -> dict:
    """Everything the client needs to render the whole shell in one request."""
    g = growth.state(st)          # may persist one-shot flags, so read profile after it
    p = st.profile()
    read = st.read_ids()
    return {
        "profile": {k: v for k, v in p.items() if k not in ("last_proactive_at",)},
        "growth": g,
        "counts": st.counts(),
        "memories": st.memories(limit=120),
        "steps": st.steps(),
        "records": st.records(200),
        "messages": st.messages(60),
        "activity": st.activity(30),
        "inbox": st.unseen_inbox(),
        "scene": st.scene_active(),
        "scenes": scenes.catalog(),
        "ideas": IDEAS,
        "academy": [{**a, "read": a["id"] in read} for a in academy.catalog()],
        "prefs": preferences(p),
        "digests": st.digests(7),
        "scene_counts": {r[0]: r[1] for r in st.c.execute(
            "SELECT scene, COUNT(*) FROM scene_run WHERE status='done' GROUP BY scene")},
        "revisions": st.revisions(20),
        "proactive": dict(zip(("ok", "reason"), scheduler.should_reach_out(p, bool(st.unseen_inbox())))),
    }
