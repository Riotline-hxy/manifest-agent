"""Pieces shared by server.py and routes.py."""
from __future__ import annotations

from . import scenes, scheduler
from .store import Store, rank

VERSION = "1.0.0"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u.get("username"), "kind": u.get("kind")}


def bootstrap(st: Store) -> dict:
    """Everything the client needs to render all five zones in one request."""
    p = st.profile()
    return {
        "profile": {k: v for k, v in p.items() if k not in ("last_proactive_at",)},
        "rank": rank(int(p.get("xp") or 0)),
        "counts": st.counts(),
        "memories": st.memories(limit=120),
        "steps": st.steps(),
        "records": st.records(200),
        "messages": st.messages(60),
        "activity": st.activity(30),
        "inbox": st.unseen_inbox(),
        "scene": st.scene_active(),
        "scenes": scenes.catalog(),
        "proactive": dict(zip(("ok", "reason"), scheduler.should_reach_out(p, bool(st.unseen_inbox())))),
    }
