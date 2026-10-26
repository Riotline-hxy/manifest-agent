"""Route table and handlers. Each handler: (handler, user, body, query) ->
(status, json[, headers]) or None if it streamed the response itself.
`user` is None only on public routes; otherwise it is the session's user and
the only source of the user id.
"""
from __future__ import annotations

from core import auth, llm, onboarding, report, scenes, scheduler
from core.store import Store
from core.util import clip, iso
from core.api import VERSION, ApiError, bootstrap, public_user


def health(h, u, b, q):
    return 200, {"ok": True, "version": VERSION, "model": llm.config()["model"],
                 "llm_key": bool(llm.api_key()), "time": iso()}


def me(h, u, b, q):
    cur = auth.session_user(h._token())
    return 200, {"user": public_user(cur) if cur else None}


def _logged_in(h, user: dict, status=200):
    token = auth.new_session(user["id"])
    return status, {"user": public_user(user)}, {"Set-Cookie": h._set_cookie(token)}


def register(h, u, b, q):
    cur = auth.session_user(h._token())
    if cur and cur["kind"] == "guest":  # upgrade in place; keeps everything the guest did
        return 200, {"user": public_user(auth.claim_guest(cur["id"], b.get("username"), b.get("password")))}
    return _logged_in(h, auth.register(b.get("username"), b.get("password")), 201)


def login(h, u, b, q):
    return _logged_in(h, auth.login(b.get("username"), b.get("password"), h._ip()))


def guest(h, u, b, q):
    key = "guest:" + h._ip()
    if auth.too_many(key):
        raise ApiError(429, "体验账号创建太频繁，稍后再试")
    auth.note_fail(key)  # counts creations per IP
    user = auth.create_guest()
    with Store(user["id"]) as st:
        if b.get("seed", True):
            onboarding.seed_guest(st)
        else:
            st.set_profile({"created_at": iso()})
    return _logged_in(h, user, 201)


def logout(h, u, b, q):
    auth.end_session(h._token())
    return 200, {"ok": True}, {"Set-Cookie": h._set_cookie(None)}


def boot(h, u, b, q):
    with Store(u["id"]) as st:
        if not st.profile().get("created_at"):
            st.set_profile({"created_at": iso()})
        return 200, {"user": public_user(u), "onboarding": onboarding.QUESTIONS, **bootstrap(st)}


def onboard(h, u, b, q):
    with Store(u["id"]) as st:
        try:
            onboarding.apply(st, b.get("answers") or {})
        except ValueError as e:
            raise ApiError(400, str(e))
        p = st.profile()
        st.add_msg("assistant", f"我是{p['agent_name']}。你想靠近「{p['intent_primary']}」，因为{p['intent_why']}。"
                                "我们不急，先从今天能做的最小一步开始。今天有什么想跟我说的吗？", {"onboarding": True})
        return 200, bootstrap(st)


def chat(h, u, b, q):
    h.sse_chat(u, b)


PROFILE_FIELDS = {"nickname", "agent_name", "agent_hue", "agent_avatar_id", "intent_primary", "intent_why",
                  "schedule_hint", "traits", "mbti_hint", "boundaries", "proactive"}


def profile(h, u, b, q):
    patch = {k: v for k, v in b.items() if k in PROFILE_FIELDS}
    if "proactive" in patch and patch["proactive"] not in ("more", "normal", "less", "off"):
        raise ApiError(400, "频率不对")
    for k in ("traits", "boundaries"):
        if k in patch:
            patch[k] = [clip(str(x), 20) for x in (patch[k] or [])][:6]
    for k, v in list(patch.items()):
        if isinstance(v, str):
            patch[k] = clip(v, 60)
    with Store(u["id"]) as st:
        st.set_profile(patch)
        if patch:
            st.log("profile", "你修改了画像")
        return 200, bootstrap(st)


def memory(h, u, b, q):
    act = b.get("action")
    with Store(u["id"]) as st:
        m = st.get_memory(str(b.get("id") or "")) if b.get("id") else None
        if act != "add" and not m:
            raise ApiError(404, "没有这条记忆")
        text = clip(str(b.get("text") or ""), 120).strip()
        if act == "confirm":
            st.update_memory(m["id"], status="active")
            st.c.execute("UPDATE memory SET source='confirmed' WHERE id=?", (m["id"],))
            st.log("memory", "你确认了：" + m["text"])
        elif act in ("reject", "forget"):
            st.delete_memory(m["id"])
            st.log("memory", ("你说不对，删掉了：" if act == "reject" else "按你说的忘掉了：") + m["text"])
        elif act == "edit":
            if not text:
                raise ApiError(400, "内容不能为空")
            st.update_memory(m["id"], text=text, status="active")
            st.c.execute("UPDATE memory SET source='confirmed' WHERE id=?", (m["id"],))
            st.log("memory", "你改了一条记忆：" + text)
        elif act == "add":
            if not text:
                raise ApiError(400, "内容不能为空")
            m = st.add_memory(text, "identity", "confirmed")
            st.log("memory", "你亲手写下：" + text)
        else:
            raise ApiError(400, "未知操作")
        return 200, {"memories": st.memories(limit=120), "counts": st.counts()}


def step(h, u, b, q):
    act = b.get("action")
    with Store(u["id"]) as st:
        result = {}
        if act == "add":
            title = clip(str(b.get("title") or ""), 40).strip()
            if not title:
                raise ApiError(400, "写一下这一步是什么")
            st.add_step(title, why=str(b.get("why") or ""), wish=st.profile().get("intent_primary") or "")
            st.log("plan", "你加了一小步：" + title)
        elif act == "done":
            s = st.complete_step(str(b.get("id") or ""))
            if not s:
                raise ApiError(404, "这一步不在待办里")
            result["xp"] = st.gain_xp(10)
            st.log("plan", "完成了：" + s["title"])
        elif act in ("todo", "drop"):
            s = st.set_step(str(b.get("id") or ""), "todo" if act == "todo" else "dropped")
            if not s:
                raise ApiError(404, "没有这一步")
            st.log("plan", ("放回待办：" if act == "todo" else "先放一放：") + s["title"])
        else:
            raise ApiError(400, "未知操作")
        return 200, {**result, **bootstrap(st)}


def record(h, u, b, q):
    type_ = b.get("type")
    if type_ not in ("good", "rest", "find"):
        raise ApiError(400, "类型不对")
    text = clip(str(b.get("text") or ""), 200).strip() or ("今天想休息" if type_ == "rest" else "")
    if not text:
        raise ApiError(400, "写点什么")
    with Store(u["id"]) as st:
        st.add_record(type_, text)
        if type_ == "good":
            st.gain_xp(5)
        st.log("record", {"good": "收下一条好消息", "rest": "今天是偷懒日", "find": "记下一条新发现"}[type_])
        return 200, bootstrap(st)


def scene_start(h, u, b, q):
    with Store(u["id"]) as st:
        try:
            if b.get("resume"):
                return 200, scenes.resume(st, str(b["resume"]))
            return 200, scenes.start(st, str(b.get("scene") or ""))
        except KeyError:
            raise ApiError(404, "没有这个场景")


def scene_answer(h, u, b, q):
    text = clip(str(b.get("text") or ""), 300).strip()
    if not text:
        raise ApiError(400, "写一句也行")
    with Store(u["id"]) as st:
        run = st.get_scene(str(b.get("run_id") or ""))
        if not run or run["status"] != "open":
            raise ApiError(404, "这个场景已经结束了")
        q = scenes.resume(st, run["id"])["step"]["q"]
        out = scenes.answer(st, run["id"], text)
        # keep the scene's Q&A in the one persistent thread, like the rest of the conversation
        st.add_msg("assistant", q, {"scene": run["scene"]})
        st.add_msg("user", text, {"scene": run["scene"]})
        if out["done"]:
            st.add_msg("assistant", out["summary"], {"scene_done": True, "wrote": [w["label"] for w in out["wrote"]]})
            st.gain_xp(8)
            out["state"] = bootstrap(st)
        return 200, out


def scene_cancel(h, u, b, q):
    with Store(u["id"]) as st:
        run = st.scene_active()
        if run:
            st.update_scene(run["id"], run["step"], run["answers"], "abandoned")
        return 200, {"ok": True}


def proactive_now(h, u, b, q):
    """Demo trigger: run the scheduler for this user now, ignoring the idle rule."""
    with Store(u["id"]) as st:
        out = scheduler.deliver(st, force=True)
        return 200, {**out, **bootstrap(st)}


def inbox_seen(h, u, b, q):
    with Store(u["id"]) as st:
        st.mark_inbox_seen()
        return 200, {"ok": True}


def report_get(h, u, b, q):
    try:
        days = int((q.get("days") or ["10"])[0])
    except ValueError:
        days = 10
    days = 30 if days >= 30 else 10
    with Store(u["id"]) as st:
        return 200, report.build(st, days)


def export(h, u, b, q):
    """Data portability: everything we store about you, as JSON."""
    with Store(u["id"]) as st:
        return 200, {"user": public_user(u), "exported_at": iso(), **bootstrap(st),
                     "memories": st.memories(limit=10000), "messages": st.messages(10000)}


ROUTES = {
    ("GET", "/api/health"): (health, False),
    ("GET", "/api/auth/me"): (me, False),
    ("POST", "/api/auth/register"): (register, False),
    ("POST", "/api/auth/login"): (login, False),
    ("POST", "/api/auth/guest"): (guest, False),
    ("POST", "/api/auth/logout"): (logout, False),
    ("GET", "/api/bootstrap"): (boot, True),
    ("POST", "/api/onboard"): (onboard, True),
    ("POST", "/api/chat"): (chat, True),
    ("POST", "/api/profile"): (profile, True),
    ("POST", "/api/memory"): (memory, True),
    ("POST", "/api/step"): (step, True),
    ("POST", "/api/record"): (record, True),
    ("POST", "/api/scene/start"): (scene_start, True),
    ("POST", "/api/scene/answer"): (scene_answer, True),
    ("POST", "/api/scene/cancel"): (scene_cancel, True),
    ("POST", "/api/proactive/now"): (proactive_now, True),
    ("POST", "/api/inbox/seen"): (inbox_seen, True),
    ("GET", "/api/report"): (report_get, True),
    ("GET", "/api/export"): (export, True),
}
