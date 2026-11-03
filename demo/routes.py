"""Route table and handlers. Each handler: (handler, user, body, query) ->
(status, json[, headers]) or None if it streamed the response itself.
`user` is None only on public routes; otherwise it is the session's user and
the only source of the user id.
"""
from __future__ import annotations

from core import academy, admin, auth, digest, metrics, webpush, growth, journey, llm, onboarding, report, scenes, scheduler, tasks, town, trial
from core.store import Store
from core.util import clip, day_key, iso
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
    metrics.bump("signup")
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


def trial_chat(h, u, b, q):
    """首页引导式体验：不建账号，历史由前端带着。"""
    key = "trial:" + h._ip()
    if auth.too_many(key, 40):
        raise ApiError(429, "聊得有点快，歇一会儿再试")
    auth.note_fail(key)
    try:
        return 200, trial.chat(b.get("goal"), b.get("history"), bool(b.get("finish")), bool(b.get("smaller")))
    except ValueError as e:
        raise ApiError(400, str(e))


# ---- 推送（网页关着也能收到小光的消息） ----
def push_key(h, u, b, q):
    return 200, {"key": webpush.keys()["pub"], "devices": len(webpush.subs(u["id"]))}


def push_subscribe(h, u, b, q):
    try:
        webpush.subscribe(u["id"], b.get("subscription") or {}, h.headers.get("User-Agent") or "")
    except ValueError as e:
        raise ApiError(400, str(e))
    return 200, {"ok": True, "devices": len(webpush.subs(u["id"]))}


def push_unsubscribe(h, u, b, q):
    webpush.unsubscribe(u["id"], str(b.get("endpoint") or ""))
    return 200, {"ok": True, "devices": len(webpush.subs(u["id"]))}


def push_latest(h, u, b, q):
    """service worker 被叫醒后来取要显示的那句话：最新一条没看过的主动消息 / 提醒。"""
    with Store(u["id"]) as st:
        p = st.profile()
        items = st.unseen_inbox()
        item = items[-1] if items else None
        return 200, {"title": p.get("agent_name") or "小光", "text": item["text"] if item else "",
                     "id": item["id"] if item else "", "cue": item["cue"] if item else ""}


def push_test(h, u, b, q):
    if not webpush.subs(u["id"]):
        raise ApiError(400, "这台设备还没开启通知")
    with Store(u["id"]) as st:
        name = st.profile().get("agent_name") or "小光"
        item = st.push_inbox(f"通知开好了。以后我想你、或者提醒到点了，就算网页关着也会在这里叫你。——{name}", "test")
    out = webpush.notify(u["id"], ttl=600, urgency="high")
    return 200, {**out, "inbox_id": item["id"]}


# ---- 管理后台（只读；登录用 MANIFEST_ADMIN_KEY，cookie 与用户会话分开） ----
def _admin(h):
    if not admin.key():
        raise ApiError(404, "后台未开启")
    if not admin.check_token(h._token(admin.COOKIE)):
        raise ApiError(401, "请先登录后台")


def admin_login(h, u, b, q):
    if not admin.key():
        raise ApiError(404, "后台未开启：在服务器 .env 里设置 MANIFEST_ADMIN_KEY")
    k = "admin:" + h._ip()
    if auth.too_many(k, 5):
        raise ApiError(429, "试太多次了，十分钟后再来")
    if not admin.check_key(b.get("key")):
        auth.note_fail(k)
        raise ApiError(401, "口令不对")
    return 200, {"ok": True}, {"Set-Cookie": h._admin_cookie(admin.make_token())}


def admin_logout(h, u, b, q):
    return 200, {"ok": True}, {"Set-Cookie": h._admin_cookie(None)}


def admin_overview(h, u, b, q):
    _admin(h)
    try:
        days = int((q.get("days") or ["30"])[0])
    except ValueError:
        days = 30
    return 200, admin.overview(days)


def admin_users(h, u, b, q):
    _admin(h)
    return 200, {"users": admin.users()}


def admin_user(h, u, b, q):
    _admin(h)
    r = admin.user(str((q.get("id") or [""])[0]))
    if not r:
        raise ApiError(404, "没有这个用户")
    return 200, r


def admin_delete(h, u, b, q):
    """删一个用户；confirm 必须等于用户名（体验账号用 id），防手滑。"""
    _admin(h)
    uid = str(b.get("id") or "")
    target = auth.get_user(uid)
    if not target:
        raise ApiError(404, "没有这个用户")
    if str(b.get("confirm") or "") != (target["username"] or uid):
        raise ApiError(400, "确认内容不对")
    admin.delete_user(uid)
    return 200, {"ok": True}


def admin_user_growth(h, u, b, q):
    _admin(h)
    r = admin.growth_detail(str((q.get("id") or [""])[0]))
    if not r:
        raise ApiError(404, "没有这个用户")
    return 200, r


def admin_adjust(h, u, b, q):
    """给一个用户加减经验、金币。必须写原因，留记录。"""
    _admin(h)
    try:
        return 200, admin.adjust(str(b.get("id") or ""), b.get("xp"), b.get("coins"), str(b.get("reason") or ""), h._ip())
    except ValueError as e:
        raise ApiError(400, str(e))


def admin_town(h, u, b, q):
    _admin(h)
    return 200, town.admin_catalog()


def admin_town_save(h, u, b, q):
    """改小镇里各样东西的价格、解锁等级、上下架；所有人立刻生效。"""
    _admin(h)
    try:
        return 200, admin.town_save(b.get("items") or {}, h._ip())
    except ValueError as e:
        raise ApiError(400, str(e))


def admin_log(h, u, b, q):
    _admin(h)
    return 200, {"entries": admin.log_entries("", 100)}


def admin_purge_guests(h, u, b, q):
    """一次删掉所有体验账号（旧版首页建的，带示例数据）。"""
    _admin(h)
    ids = admin.guest_ids()
    if str(b.get("confirm") or "") != f"删除 {len(ids)} 个体验账号":
        raise ApiError(400, "确认内容不对")
    n = sum(1 for uid in ids if admin.delete_user(uid))
    return 200, {"ok": True, "deleted": n}


def rename(h, u, b, q):
    user = auth.rename(u["id"], str(b.get("username") or ""))
    with Store(u["id"]) as st:
        st.log("profile", "你改了登录用户名")
    return 200, {"user": public_user(user)}


def logout(h, u, b, q):
    cur = auth.session_user(h._token())
    if cur and b.get("endpoint"):  # 这台设备不再收这个账号的推送
        webpush.unsubscribe(cur["id"], str(b["endpoint"]))
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
        carry = b.get("carry") if isinstance(b.get("carry"), dict) else {}
        first = clip(str(carry.get("step") or ""), 40).strip()
        metrics.bump("onboard")
        if first:
            metrics.bump("trial_signup")
        for text in (carry.get("remember") or [])[:3]:
            text = clip(str(text), 40).strip()
            if text:
                st.add_memory(text, "identity", "confirmed")
        if first:
            st.add_step(first, why=clip(str(carry.get("why") or ""), 60), wish=p.get("intent_primary") or "")
            st.log("plan", "体验时定下的一小步：" + first)
            st.add_msg("assistant", f"我是{p['agent_name']}，刚才我们聊过的我都记着。你想靠近「{p['intent_primary']}」，"
                                    f"今天就先做「{first}」。做完了跟我说一声，没做成也来说说，我们再调。", {"onboarding": True})
        else:
            st.add_msg("assistant", f"我是{p['agent_name']}。你想靠近「{p['intent_primary']}」，因为{p['intent_why']}。"
                                    "我们不急，先从今天能做的最小一步开始。今天有什么想跟我说的吗？", {"onboarding": True})
        return 200, bootstrap(st)


def chat(h, u, b, q):
    h.sse_chat(u, b)


PROFILE_FIELDS = {"nickname", "agent_name", "agent_hue", "agent_avatar_id", "intent_primary", "intent_why",
                  "schedule_hint", "traits", "mbti_hint", "boundaries", "proactive",
                  "care_style", "pace", "theme", "persona", "custom_moods"}


def profile(h, u, b, q):
    patch = {k: v for k, v in b.items() if k in PROFILE_FIELDS}
    if "proactive" in patch and patch["proactive"] not in ("more", "normal", "less", "off"):
        raise ApiError(400, "频率不对")
    if "care_style" in patch and patch["care_style"] not in ("", "nudge", "analyze", "quiet"):
        raise ApiError(400, "偏好不对")
    if "persona" in patch and patch["persona"] not in ("gentle", "clear", "lively"):
        raise ApiError(400, "没有这种性格")
    if "custom_moods" in patch:
        patch["custom_moods"] = [str(x).strip()[:8] for x in (patch["custom_moods"] or []) if str(x).strip()][:8]
    if "theme" in patch and patch["theme"] not in onboarding.THEMES:
        raise ApiError(400, "没有这个氛围")
    if "agent_hue" in patch and patch["agent_hue"] not in onboarding.AGENT_COLORS | {""}:
        raise ApiError(400, "没有这个颜色")
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
        if act in ("confirm", "reject", "edit"):
            st.bump("memory_fix")
        if act == "confirm":
            st.update_memory(m["id"], status="active")
            st.c.execute("UPDATE memory SET source='confirmed' WHERE id=?", (m["id"],))
            st.log("memory", "你确认了：" + m["text"])
        elif act in ("reject", "forget"):
            st.delete_memory(m["id"], reason="user_" + act)
            st.log("memory", ("你说不对，删掉了：" if act == "reject" else "按你说的忘掉了：") + m["text"])
        elif act == "edit":
            if not text:
                raise ApiError(400, "内容不能为空")
            st.update_memory(m["id"], text=text, status="active", reason="user_edit")
            st.c.execute("UPDATE memory SET source='confirmed' WHERE id=?", (m["id"],))
            st.log("memory", "你改了一条记忆：" + text)
        elif act == "add":
            if not text:
                raise ApiError(400, "内容不能为空")
            st.add_memory(text, "identity", "confirmed")
            st.log("memory", "你亲手写下：" + text)
        else:
            raise ApiError(400, "未知操作")
        return 200, bootstrap(st)


def step(h, u, b, q):
    act = b.get("action")
    with Store(u["id"]) as st:
        result = {}
        if act == "add":
            title = clip(str(b.get("title") or ""), 40).strip()
            if not title:
                raise ApiError(400, "写一下这一步是什么")
            st.add_step(title, why=str(b.get("why") or ""), wish=st.profile().get("intent_primary") or "",
                        wish_id=str(b.get("wish_id") or ""))
            st.log("plan", "你加了一小步：" + title)
        elif act == "done":
            s = st.complete_step(str(b.get("id") or ""))
            if not s:
                raise ApiError(404, "这一步不在待办里")
            result["xp"] = growth.award(st, "action", ref="step:" + s["id"], note="完成：" + s["title"])
            st.log("plan", "完成了：" + s["title"])
            result["cleared"] = journey.steps_cleared(st, s)   # 这个愿望的小步都做完了：前端弹一张鼓励
        elif act in ("todo", "drop"):
            s = st.set_step(str(b.get("id") or ""), "todo" if act == "todo" else "dropped")
            if not s:
                raise ApiError(404, "没有这一步")
            st.log("plan", ("放回待办：" if act == "todo" else "先放一放：") + s["title"])
        else:
            raise ApiError(400, "未知操作")
        return 200, {**result, **bootstrap(st)}


def record(h, u, b, q):
    """好消息页：小确幸(good) / 内心戏(meme)。蜕变计划：休息日(rest，可撤销)。find 只保留旧数据的展示。"""
    type_ = b.get("type")
    if type_ not in ("good", "meme", "rest"):
        raise ApiError(400, "类型不对")
    with Store(u["id"]) as st:
        if type_ == "rest" and b.get("undo"):
            with st.lock:
                st.c.execute("DELETE FROM record WHERE type='rest' AND day=?", (day_key(),))
            st.log("rest", "今天不偷懒了")
            return 200, bootstrap(st)
        text = clip(str(b.get("text") or ""), 200).strip() or ("今天偷个懒" if type_ == "rest" else "")
        if not text:
            raise ApiError(400, "写点什么")
        if type_ == "rest" and st.c.execute("SELECT 1 FROM record WHERE type='rest' AND day=?", (day_key(),)).fetchone():
            return 200, {"xp": None, **bootstrap(st)}
        r = st.add_record(type_, text)
        xp = None
        if type_ in ("good", "meme"):
            xp = growth.award(st, "good", ref="rec:" + r["id"], note="小确幸" if type_ == "good" else "内心戏")
        else:   # 偷懒日：每日任务里行动那项先暂停，另外两件做到了就能拿全勤
            daily = growth.settle_daily(st)
            if daily:
                xp = {"ok": True, "amount": 0, "coins": sum(d["coins"] for d in daily), "daily": daily}
        st.log("rest" if type_ == "rest" else "record",
               {"good": "记下一件小确幸", "meme": "记下一段内心戏", "rest": "今天偷个懒：" + text.replace("今天偷个懒：", "")}[type_])
        return 200, {"xp": xp, "record": r, **bootstrap(st)}


def habit_api(h, u, b, q):
    act = b.get("action")
    out = {}
    with Store(u["id"]) as st:
        try:
            if act == "add":
                out["habit"] = journey.add_habit(st, str(b.get("wish_id") or ""), str(b.get("title") or ""),
                                                 str(b.get("freq") or "daily"), b.get("per_week") or 3)
            elif act in ("check", "uncheck"):
                hb, created = journey.check_habit(st, str(b.get("id") or ""), b.get("day"), undo=act == "uncheck")
                if created:
                    day = b.get("day") or day_key()
                    out["xp"] = growth.award(st, "action", ref=f"habit:{hb['id']}:{day}", note="打卡：" + hb["title"])
            elif act in ("skip", "unskip"):
                journey.skip_habit(st, str(b.get("id") or ""), undo=act == "unskip")
            elif act == "ease":
                hb = next((x for x in journey.habits(st) if x["id"] == str(b.get("id") or "")), None)
                if not hb:
                    raise ApiError(404, "没有这个习惯")
                down = journey.ease_habit(hb)
                if not down:
                    raise ApiError(400, "已经是每周 1 次了，可以先收起它")
                journey.edit_habit(st, hb["id"], {"freq": down[0], "per_week": down[1]})
                st.log("plan", f"把「{hb['title']}」调轻了：{journey.freq_text({'freq': down[0], 'per_week': down[1]})}")
                out["eased"] = journey.freq_text({"freq": down[0], "per_week": down[1]})
            elif act == "edit":
                if not journey.edit_habit(st, str(b.get("id") or ""), b):
                    raise ApiError(404, "没有这个习惯")
            else:
                raise ApiError(400, "未知操作")
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, {**out, **bootstrap(st)}


def milestone_api(h, u, b, q):
    act = b.get("action")
    out = {}
    with Store(u["id"]) as st:
        try:
            if act == "add":
                out["milestone"] = journey.add_milestone(st, str(b.get("wish_id") or ""), str(b.get("title") or ""), b.get("due_day"))
            elif act in ("done", "todo", "edit", "delete"):
                patch = dict(b)
                if act in ("done", "todo"):
                    patch["status"] = act
                if act == "delete":
                    patch["delete"] = True
                m = journey.edit_milestone(st, str(b.get("id") or ""), patch)
                if not m:
                    raise ApiError(404, "没有这个里程碑")
                if act == "done":
                    out["xp"] = growth.award(st, "action", ref="ms:" + m["id"], note="到达：" + m["title"])
            else:
                raise ApiError(400, "未知操作")
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, {**out, **bootstrap(st)}


def task_api(h, u, b, q):
    act = b.get("action")
    uid = u["id"]
    out = {}
    try:
        if act == "add":
            out["task"] = tasks.add(uid, str(b.get("title") or ""), kind=str(b.get("kind") or "remind"),
                                    message=str(b.get("message") or ""), repeat=str(b.get("repeat") or "once"),
                                    time=str(b.get("time") or ""), days=b.get("days"), in_minutes=b.get("in_minutes"),
                                    date=str(b.get("date") or ""), source="user")
        elif act in ("on", "off"):
            if not tasks.set_enabled(uid, str(b.get("id") or ""), act == "on"):
                raise ApiError(404, "没有这个任务")
        elif act == "edit":
            if not tasks.edit(uid, str(b.get("id") or ""), b):
                raise ApiError(404, "没有这个任务")
        elif act == "delete":
            if not tasks.delete(uid, str(b.get("id") or "")):
                raise ApiError(404, "没有这个任务")
        else:
            raise ApiError(400, "未知操作")
    except ValueError as e:
        raise ApiError(400, str(e))
    with Store(uid) as st:
        if act == "add":
            st.log("task", f"安排了例行任务：{out['task']['title']}（{out['task']['when']}）")
        return 200, {**out, **bootstrap(st)}


def pulse(h, u, b, q):
    """页面开着时每 30 秒问一次：有没有新的提醒 / 小光的消息。只读两个计数，很轻。"""
    with Store(u["id"]) as st:
        r = st.c.execute("SELECT COUNT(*), MAX(created_at) FROM inbox WHERE seen=0").fetchone()
        last = st.c.execute("SELECT id, content, meta FROM msg WHERE role='assistant' ORDER BY created_at DESC LIMIT 1").fetchone()
    return 200, {"unseen": r[0], "latest": r[1] or "", "last_msg": last["id"] if last else ""}


def plan_apply(h, u, b, q):
    with Store(u["id"]) as st:
        try:
            made = journey.apply_plan(st, str(b.get("wish_id") or ""), b)
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, {"made": {k: len(v) for k, v in made.items()}, **bootstrap(st)}


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
            out["xp"] = growth.award(st, "practice", ref="scene:" + run["id"],
                                     note="完成练习：" + scenes.SCENES[run["scene"]]["title"])
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


def growth_get(h, u, b, q):
    with Store(u["id"]) as st:
        return 200, growth.state(st)


def town_get(h, u, b, q):
    with Store(u["id"]) as st:
        return 200, town.state(st)


def town_api(h, u, b, q):
    """我的小镇：买并放下 / 挪位置（仓库里的放出来也是它）/ 收进仓库 / 改名 / 看过欢迎。金币只在后端算。"""
    act = b.get("action")
    out = {}
    with Store(u["id"]) as st:
        try:
            if act == "buy":
                out["built"] = town.buy(st, str(b.get("kind") or ""), b.get("x"), b.get("y"), str(b.get("nonce") or ""), b.get("rot") or 0)
            elif act in ("move", "place"):
                out["moved"] = town.move(st, str(b.get("id") or ""), b.get("x"), b.get("y"), b.get("rot"))
            elif act == "store":
                out["stored"] = town.store_item(st, str(b.get("id") or ""))
            elif act == "rename":
                out["name"] = town.rename(st, str(b.get("name") or ""))
            elif act == "welcome_seen":
                town.welcome_seen(st)
            else:
                raise ApiError(400, "未知操作")
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, {**out, **bootstrap(st)}


def digest_now(h, u, b, q):
    """Run today's nightly memory pass now (the scheduler does it at 03:00 for yesterday)."""
    with Store(u["id"]) as st:
        out = digest.run(st)
        return 200, {"digest": out, **bootstrap(st)}


def notebook(h, u, b, q):
    """用户可以直接改小光的笔记本；改过的版本夜里整理时会在它的基础上继续写。"""
    text = clip(str(b.get("text") or "").strip(), 1600)
    with Store(u["id"]) as st:
        st.set_profile({"notebook": {"text": text, "updated_at": iso(), "by": "user"}})
        st.log("memory", "你改了小光的笔记本")
        return 200, bootstrap(st)


def academy_list(h, u, b, q):
    with Store(u["id"]) as st:
        read = st.read_ids()
        items = [{**a, "read": a["id"] in read} for a in academy.catalog()]
    return 200, {"articles": items}


def academy_get(h, u, b, q):
    article = academy.get(str((q.get("id") or [""])[0]))
    if not article:
        raise ApiError(404, "没有这篇文章")
    with Store(u["id"]) as st:
        st.mark_read(article["id"])
    return 200, {"article": article}


def wish_api(h, u, b, q):
    act = b.get("action")
    with Store(u["id"]) as st:
        try:
            if act == "add":
                journey.add_wish(st, str(b.get("title") or ""), str(b.get("category") or ""),
                                 str(b.get("now_text") or ""), str(b.get("vision_text") or ""), scene=str(b.get("scene") or ""),
                                 target_day=b.get("target_day") or None)
            elif act == "edit":
                if not journey.edit_wish(st, str(b.get("id") or ""), b):
                    raise ApiError(404, "没有这个愿望")
            elif act == "select":
                if not journey.get_wish(st, str(b.get("id") or "")):
                    raise ApiError(404, "没有这个愿望")
                st.set_profile({"current_wish": b["id"]})
            else:
                raise ApiError(400, "未知操作")
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, bootstrap(st)


def moment_api(h, u, b, q):
    act = b.get("action")
    out = {}
    with Store(u["id"]) as st:
        try:
            if act == "add":
                m = journey.add_moment(st, str(b.get("wish_id") or ""), str(b.get("text") or ""),
                                       str(b.get("feeling") or ""), str(b.get("mood") or ""), b.get("day"),
                                       source="chat" if b.get("source") == "chat" else "user")
                out["moment"] = m
                out["xp"] = growth.award(st, "good", ref="moment:" + m["id"], note="留下一个瞬间")
            elif act == "edit":
                if not journey.edit_moment(st, str(b.get("id") or ""), b):
                    raise ApiError(404, "没有这条记录")
            elif act == "delete":
                if not journey.delete_moment(st, str(b.get("id") or "")):
                    raise ApiError(404, "没有这条记录")
            else:
                raise ApiError(400, "未知操作")
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, {**out, **bootstrap(st)}


def wish_review(h, u, b, q):
    try:
        days = int((q.get("days") or ["30"])[0])
    except ValueError:
        days = 30
    with Store(u["id"]) as st:
        try:
            return 200, journey.review(st, str((q.get("id") or [""])[0]), days)
        except ValueError as e:
            raise ApiError(404, str(e))


def wish_reflect(h, u, b, q):
    with Store(u["id"]) as st:
        if not journey.get_wish(st, str(b.get("id") or "")):
            raise ApiError(404, "没有这个愿望")
        try:
            journey.reflect(st, b["id"], int(b.get("days") or 30), str(b.get("text") or ""))
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, journey.review(st, b["id"], int(b.get("days") or 30))


def wish_insight(h, u, b, q):
    with Store(u["id"]) as st:
        try:
            if b.get("answer"):
                out = journey.answer_insight(st, str(b.get("insight_id") or ""), str(b["answer"]))
            else:
                out = journey.make_insight(st, str(b.get("id") or ""))
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, {**out, **bootstrap(st)}


def report_get(h, u, b, q):
    try:
        days = int((q.get("days") or ["14"])[0])
    except ValueError:
        days = 14
    days = 30 if days >= 30 else 14
    fast = (q.get("fast") or ["0"])[0] == "1"
    with Store(u["id"]) as st:
        if fast:
            st.bump("report_open")
        return 200, report.build(st, days, with_letter=not fast)


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
    ("POST", "/api/trial/chat"): (trial_chat, False),
    ("GET", "/api/push/key"): (push_key, True),
    ("POST", "/api/push/subscribe"): (push_subscribe, True),
    ("POST", "/api/push/unsubscribe"): (push_unsubscribe, True),
    ("GET", "/api/push/latest"): (push_latest, True),
    ("POST", "/api/push/test"): (push_test, True),
    ("POST", "/api/admin/login"): (admin_login, False),
    ("POST", "/api/admin/logout"): (admin_logout, False),
    ("GET", "/api/admin/overview"): (admin_overview, False),
    ("GET", "/api/admin/users"): (admin_users, False),
    ("GET", "/api/admin/user"): (admin_user, False),
    ("POST", "/api/admin/user/delete"): (admin_delete, False),
    ("POST", "/api/admin/guests/delete"): (admin_purge_guests, False),
    ("GET", "/api/admin/user/growth"): (admin_user_growth, False),
    ("POST", "/api/admin/user/adjust"): (admin_adjust, False),
    ("GET", "/api/admin/town"): (admin_town, False),
    ("POST", "/api/admin/town"): (admin_town_save, False),
    ("GET", "/api/admin/log"): (admin_log, False),
    ("POST", "/api/auth/logout"): (logout, False),
    ("POST", "/api/auth/rename"): (rename, True),
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
    ("GET", "/api/growth"): (growth_get, True),
    ("GET", "/api/town"): (town_get, True),
    ("POST", "/api/town"): (town_api, True),
    ("POST", "/api/memory/digest"): (digest_now, True),
    ("POST", "/api/wish"): (wish_api, True),
    ("POST", "/api/moment"): (moment_api, True),
    ("POST", "/api/habit"): (habit_api, True),
    ("POST", "/api/milestone"): (milestone_api, True),
    ("POST", "/api/plan/apply"): (plan_apply, True),
    ("POST", "/api/task"): (task_api, True),
    ("POST", "/api/notebook"): (notebook, True),
    ("GET", "/api/pulse"): (pulse, True),
    ("GET", "/api/wish/review"): (wish_review, True),
    ("POST", "/api/wish/reflect"): (wish_reflect, True),
    ("POST", "/api/wish/insight"): (wish_insight, True),
    ("GET", "/api/academy"): (academy_list, True),
    ("GET", "/api/academy/article"): (academy_get, True),
    ("GET", "/api/report"): (report_get, True),
    ("GET", "/api/export"): (export, True),
}
