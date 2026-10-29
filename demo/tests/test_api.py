"""End-to-end API tests against a real server on a temp data dir.

The LLM is replaced by a scripted fake (tests/fake_llm.py) so tests are
deterministic and free. Run:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="xb_test_")
os.environ["MANIFEST_DATA"] = TMP
os.environ["MANIFEST_SCHEDULER"] = "0"
os.environ["MODELFLARE_API_KEY"] = "test-key"
sys.path.insert(0, DEMO)

import server  # noqa: E402
from core import auth, llm, scheduler, tasks  # noqa: E402
from core.store import Store  # noqa: E402

ONBOARD = {"agent_name": "阿光", "agent_avatar_id": "stardust", "intent_primary": "健康作息",
           "intent_why": "白天总是很困", "schedule_hint": "夜猫", "care_style": "analyze",
           "traits": ["拖延但爆发"], "mbti_hint": "跳过", "boundaries": ["别说教"]}


class FakeLLM:
    """Scripted stand-in for llm.stream_chat / complete_json."""

    def __init__(self):
        self.turns = []        # list of lists of events per stream_chat call
        self.json_out = None   # returned by complete_json
        self.seen = []         # captured messages

    def stream(self, messages, tools=None, model=None, reasoning=None, timeout=None):
        self.seen.append(messages)
        script = self.turns.pop(0) if self.turns else [("text", "嗯，我在。")]
        for ev in script:
            yield ev
        yield ("done", {"finish_reason": "stop", "usage": None})

    def complete(self, messages, model=None, timeout=40):
        return self.json_out


class Client:
    def __init__(self, port):
        self.port, self.cookie = port, None

    def req(self, method, path, body=None, headers=None, raw=False):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json"}
        if self.cookie:
            h["Cookie"] = self.cookie
        h.update(headers or {})
        c.request(method, path, body=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read().decode("utf-8")
        sc = r.getheader("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0] if "Max-Age=0" not in sc else None
        c.close()
        if raw:
            return r.status, data, sc
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    def sse(self, text):
        status, data, _ = self.req("POST", "/api/chat", {"text": text}, raw=True)
        events = []
        for block in data.split("\n\n"):
            ev = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
            if "event" in ev:
                events.append((ev["event"], json.loads(ev.get("data", "{}"))))
        return status, events


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeLLM()
        cls._orig = (llm.stream_chat, llm.complete_json)
        llm.stream_chat = cls.fake.stream
        llm.complete_json = cls.fake.complete
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        llm.stream_chat, llm.complete_json = cls._orig
        auth.reset_for_tests()
        tasks.reset_for_tests()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.fake.turns, self.fake.json_out, self.fake.seen = [], None, []

    def member(self, name):
        c = Client(self.port)
        s, d = c.req("POST", "/api/auth/register", {"username": name, "password": "secret12"})
        self.assertEqual(s, 201, d)
        return c, d["user"]["id"]

    def onboarded(self, name):
        c, uid = self.member(name)
        s, d = c.req("POST", "/api/onboard", {"answers": ONBOARD})
        self.assertEqual(s, 200, d)
        return c, uid

    # ---- auth & isolation ----------------------------------------------------
    def test_requires_session(self):
        c = Client(self.port)
        for path in ("/api/bootstrap", "/api/report", "/api/export"):
            self.assertEqual(c.req("GET", path)[0], 401, path)
        self.assertEqual(c.req("POST", "/api/record", {"type": "good", "text": "x"})[0], 401)

    def test_users_cannot_see_each_other(self):
        a, uid_a = self.onboarded("iso_a")
        b, uid_b = self.member("iso_b")
        a.req("POST", "/api/record", {"type": "good", "text": "A 的秘密好消息"})
        _, db = b.req("GET", "/api/bootstrap")
        self.assertEqual(db["user"]["id"], uid_b)
        blob = json.dumps(db, ensure_ascii=False)
        self.assertNotIn("A 的秘密好消息", blob)
        self.assertNotIn(uid_a, blob)
        # client-supplied ids are ignored: there is no parameter that selects a user
        _, db2 = b.req("GET", f"/api/bootstrap?user_id={uid_a}")
        self.assertEqual(db2["user"]["id"], uid_b)
        # memory ids from A cannot be touched by B
        _, da = a.req("GET", "/api/bootstrap")
        mid = da["memories"][0]["id"]
        self.assertEqual(b.req("POST", "/api/memory", {"action": "forget", "id": mid})[0], 404)
        _, da2 = a.req("GET", "/api/bootstrap")
        self.assertIn(mid, [m["id"] for m in da2["memories"]])
        # physically separate files
        self.assertTrue(os.path.isfile(os.path.join(TMP, "u", uid_a, "mind.db")))
        self.assertTrue(os.path.isfile(os.path.join(TMP, "u", uid_b, "mind.db")))

    def test_login_logout_and_bad_password(self):
        c, _ = self.member("Login_Me")
        self.assertEqual(c.req("POST", "/api/auth/logout", {})[0], 200)
        self.assertIsNone(c.cookie)
        self.assertEqual(c.req("GET", "/api/bootstrap")[0], 401)
        self.assertEqual(c.req("POST", "/api/auth/login", {"username": "login_me", "password": "nope"})[0], 401)
        self.assertEqual(c.req("POST", "/api/auth/login", {"username": "login_me", "password": "secret12"})[0], 200)
        self.assertEqual(c.req("GET", "/api/bootstrap")[0], 200)

    def test_duplicate_username_and_validation(self):
        self.member("dup_user")
        c = Client(self.port)
        self.assertEqual(c.req("POST", "/api/auth/register", {"username": "DUP_user", "password": "secret12"})[0], 409)
        self.assertEqual(c.req("POST", "/api/auth/register", {"username": "x", "password": "secret12"})[0], 400)
        self.assertEqual(c.req("POST", "/api/auth/register", {"username": "okname", "password": "123"})[0], 400)

    def test_cookie_flags_and_password_hashing(self):
        c = Client(self.port)
        _, _, sc = c.req("POST", "/api/auth/register", {"username": "flags", "password": "secret12"}, raw=True)
        self.assertIn("HttpOnly", sc)
        self.assertIn("SameSite=Lax", sc)
        _, _, sc2 = Client(self.port).req("POST", "/api/auth/register", {"username": "flags2", "password": "secret12"},
                                          headers={"X-Forwarded-Proto": "https"}, raw=True)
        self.assertIn("Secure", sc2)
        row = auth.db().execute("SELECT pw_hash FROM users WHERE username='flags'").fetchone()
        self.assertTrue(row["pw_hash"].startswith("pbkdf2_sha256$"))
        self.assertNotIn("secret12", row["pw_hash"])
        tok = c.cookie.split("=", 1)[1]
        self.assertIsNone(auth.db().execute("SELECT 1 FROM sessions WHERE token_hash=?", (tok,)).fetchone())

    def test_cross_origin_post_rejected(self):
        c, _ = self.member("csrf")
        s, _ = c.req("POST", "/api/record", {"type": "good", "text": "x"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(s, 403)
        s, _ = c.req("POST", "/api/record", {"type": "good", "text": "x"}, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(s, 200)

    def test_guest_seed_and_claim_keeps_data(self):
        c = Client(self.port)
        s, d = c.req("POST", "/api/auth/guest", {})
        self.assertEqual(s, 201)
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertTrue(boot["profile"]["onboarded"])
        self.assertGreaterEqual(boot["counts"]["good"], 5)
        s, d = c.req("POST", "/api/auth/register", {"username": "claimed", "password": "secret12"})
        self.assertEqual((s, d["user"]["kind"]), (200, "member"))
        _, boot2 = c.req("GET", "/api/bootstrap")
        self.assertEqual(boot2["counts"]["good"], boot["counts"]["good"])

    def test_static_path_traversal_blocked(self):
        c = Client(self.port)
        self.assertEqual(c.req("GET", "/../server.py", raw=True)[0], 404)
        self.assertEqual(c.req("GET", "/%2e%2e/server.py", raw=True)[0], 404)
        s, body, _ = c.req("GET", "/", raw=True)
        self.assertEqual(s, 200)

    # ---- onboarding / scenes / records ---------------------------------------
    def test_onboarding_writes_locked_fields(self):
        c, uid = self.onboarded("onb")
        _, d = c.req("GET", "/api/bootstrap")
        p = d["profile"]
        self.assertEqual((p["agent_name"], p["intent_primary"], p["schedule_hint"]), ("阿光", "健康作息", "夜猫"))
        self.assertEqual(p["mbti_hint"], "")          # 「跳过」 stores nothing
        self.assertEqual(p["care_style"], "analyze")  # 中断时的陪伴方式，建档就写进去
        self.assertTrue(p["onboarded"])
        kinds = {m["kind"] for m in d["memories"]}
        self.assertTrue({"intent", "identity", "boundary"} <= kinds)
        bad = Client(self.port)
        bad.req("POST", "/api/auth/register", {"username": "onb_bad", "password": "secret12"})
        self.assertEqual(bad.req("POST", "/api/onboard", {"answers": {"agent_name": "x"}})[0], 400)

    def test_scene_waits_for_each_answer_then_writes(self):
        c, _ = self.onboarded("scene")
        s, d = c.req("POST", "/api/scene/start", {"scene": "clarify"})
        self.assertEqual(s, 200)
        rid = d["run"]["id"]
        _, d1 = c.req("POST", "/api/scene/answer", {"run_id": rid, "text": "周末早上在阳台看书"})
        self.assertFalse(d1["done"])
        self.assertEqual(d1["step"]["index"], 1)
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual(boot["scene"]["id"], rid)      # resumable after reload
        c.req("POST", "/api/scene/answer", {"run_id": rid, "text": "在阳台看书"})
        _, d3 = c.req("POST", "/api/scene/answer", {"run_id": rid, "text": "把书放到床头"})
        self.assertTrue(d3["done"])
        types = sorted(w["type"] for w in d3["wrote"])
        self.assertEqual(types, ["memory", "step"])
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertIn("把书放到床头", [x["title"] for x in boot["steps"]])
        self.assertIsNone(boot["scene"])

    def test_every_scene_writes_something(self):
        from core import scenes
        c, _ = self.onboarded("scene_all")
        for sid, sc in scenes.SCENES.items():
            _, d = c.req("POST", "/api/scene/start", {"scene": sid})
            out = None
            for i in range(len(sc["steps"])):
                _, out = c.req("POST", "/api/scene/answer", {"run_id": d["run"]["id"], "text": f"回答{i}"})
            self.assertTrue(out["done"], sid)
            self.assertGreaterEqual(len(out["wrote"]), 1, sid)

    def test_lazy_day_never_resets_progress(self):
        c, _ = self.onboarded("lazy")
        c.req("POST", "/api/record", {"type": "good", "text": "早睡了"})
        _, before = c.req("GET", "/api/bootstrap")
        c.req("POST", "/api/record", {"type": "rest", "text": "今天想休息"})
        _, after = c.req("GET", "/api/bootstrap")
        self.assertEqual(after["counts"]["good"], before["counts"]["good"])
        self.assertEqual(after["counts"]["rest"], 1)
        self.assertEqual(after["growth"]["total"], before["growth"]["total"])

    def test_step_done_gives_xp(self):
        c, _ = self.onboarded("xp")
        c.req("POST", "/api/step", {"action": "add", "title": "十一点前放下手机"})
        _, d = c.req("GET", "/api/bootstrap")
        sid = [s for s in d["steps"] if s["status"] == "todo"][0]["id"]
        s, d2 = c.req("POST", "/api/step", {"action": "done", "id": sid})
        self.assertEqual(s, 200)
        self.assertEqual(d2["xp"]["amount"], 10)
        self.assertEqual(d2["growth"]["today"]["by_source"]["action"], 10)
        earned = {b["id"] for b in d2["growth"]["badges"] if b["earned"]}
        self.assertIn("step_1", earned)

    def test_memory_confirm_edit_forget(self):
        c, uid = self.onboarded("mem")
        with Store(uid) as st:
            g = st.add_memory("可能更怕说错而不是不会说", "insight", "chat", "guess")
        c.req("POST", "/api/memory", {"action": "confirm", "id": g["id"]})
        _, d = c.req("GET", "/api/bootstrap")
        m = next(x for x in d["memories"] if x["id"] == g["id"])
        self.assertEqual((m["status"], m["source"]), ("active", "confirmed"))
        c.req("POST", "/api/memory", {"action": "edit", "id": g["id"], "text": "更怕说错"})
        c.req("POST", "/api/memory", {"action": "forget", "id": g["id"]})
        _, d = c.req("GET", "/api/bootstrap")
        self.assertNotIn(g["id"], [x["id"] for x in d["memories"]])
        with Store(uid) as st:  # forgotten means gone from the index too
            self.assertEqual(st.search("说错"), [])

    # ---- retrieval -------------------------------------------------------------
    def test_retrieval_bigram_and_status(self):
        c, uid = self.onboarded("rag")
        with Store(uid) as st:
            st.add_memory("和熟悉的朋友一起练口语时不紧张", "insight")
            st.add_memory("喜欢在图书馆三楼靠窗的位置", "preference")
            st.add_memory("可能害怕被评价", "insight", status="guess")
            hits = st.search("口语练习好紧张")
            self.assertEqual(hits[0]["text"], "和熟悉的朋友一起练口语时不紧张")
            self.assertNotIn("可能害怕被评价", [h["text"] for h in st.search("害怕评价")])
            self.assertIn("可能害怕被评价", [h["text"] for h in st.search("害怕评价", include_guess=True)])
            self.assertEqual(st.search("完全无关的天文学"), [])

    # ---- agent loop ------------------------------------------------------------
    def test_chat_streams_and_runs_tools(self):
        c, uid = self.onboarded("agent")
        with Store(uid) as st:
            st.add_memory("晚上十一点后容易刷手机停不下来", "event")
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "log_good_news", "arguments": json.dumps({"text": "今天十一点就睡了"})},
                             {"id": "c2", "name": "set_mood", "arguments": '{"mood":"happy"}'}])],
            [("text", "太好了，"), ("text", "这条我收下了。")],
        ]
        s, ev = c.sse("今天十一点就睡了！刷手机的习惯好像好一点")
        self.assertEqual(s, 200)
        names = [e for e, _ in ev]
        self.assertIn("context", names)
        self.assertIn("tool", names)
        self.assertEqual("".join(d["text"] for e, d in ev if e == "delta"), "太好了，这条我收下了。")
        ctx = next(d for e, d in ev if e == "context")
        self.assertIn("晚上十一点后容易刷手机停不下来", [m["text"] for m in ctx["memories"]])
        self.assertIn("10", [d["id"] for e, d in ev if e == "mood"])
        sys_prompt = " ".join(m["content"] for m in self.fake.seen[0] if m["role"] == "system")
        self.assertIn("健康作息", sys_prompt)
        self.assertIn("别说教", sys_prompt)
        self.assertIn("晚上十一点后容易刷手机", sys_prompt)
        tool_msg = self.fake.seen[1][-1]
        self.assertEqual(tool_msg["role"], "tool")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertIn("今天十一点就睡了", [r["text"] for r in d["records"]])
        last = d["messages"][-1]
        self.assertEqual((last["role"], last["content"]), ("assistant", "太好了，这条我收下了。"))
        self.assertEqual(last["meta"]["tools"][0]["name"], "log_good_news")

    def test_complete_step_by_title(self):
        c, uid = self.onboarded("agent_step")
        c.req("POST", "/api/step", {"action": "add", "title": "睡前把手机放在客厅"})
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "complete_step", "arguments": '{"title":"手机放在客厅"}'}])],
            [("text", "做到了。")],
        ]
        _, ev = c.sse("昨晚我把手机放客厅了")
        tool = next(d for e, d in ev if e == "tool")
        self.assertTrue(tool["result"]["ok"], tool)
        self.assertIn("33", [d["id"] for e, d in ev if e == "mood"])

    def test_llm_failure_degrades_gracefully(self):
        c, _ = self.onboarded("agent_fail")

        def boom(*a, **k):
            raise llm.LLMError("HTTP 502")
            yield  # pragma: no cover

        orig, llm.stream_chat = llm.stream_chat, boom
        try:
            s, ev = c.sse("你好")
        finally:
            llm.stream_chat = orig
        self.assertEqual(s, 200)
        self.assertIn("error", [e for e, _ in ev])
        self.assertIn("done", [e for e, _ in ev])

    def test_memory_write_pipeline(self):
        from core import memory
        c, uid = self.onboarded("pipe")
        with Store(uid) as st:
            old = st.add_memory("每天晚上一点才睡", "event")
            self.fake.json_out = {"ops": [
                {"op": "UPDATE", "id": old["id"], "text": "最近能在十二点前睡", "kind": "event", "source": "said"},
                {"op": "ADD", "text": "早上醒来会先喝水", "kind": "preference", "source": "said"},
                {"op": "ADD", "text": "可能在压力大时更晚睡", "kind": "insight", "source": "guess"},
                {"op": "ADD", "text": "第二条猜测应被丢弃", "kind": "insight", "source": "guess"},
                {"op": "DELETE", "id": "m_not_shown_to_model"},
            ]}
            applied = memory.extract_and_apply(st, "这周我都在十二点前睡了，早上起来先喝水", "真好")
            self.assertEqual([a["op"] for a in applied], ["UPDATE", "ADD", "ADD"])
            self.assertEqual(st.get_memory(old["id"])["text"], "最近能在十二点前睡")
            texts = {m["text"]: m["status"] for m in st.memories()}
            self.assertEqual(texts["可能在压力大时更晚睡"], "guess")
            self.assertNotIn("第二条猜测应被丢弃", texts)


    # ---- growth: caps, branching, one-shot celebrations -------------------------
    def test_xp_caps_and_dedup(self):
        c, uid = self.onboarded("caps")
        for i in range(5):
            c.req("POST", "/api/step", {"action": "add", "title": f"第{i}步"})
        _, d = c.req("GET", "/api/bootstrap")
        got = []
        for s_ in [x for x in d["steps"] if x["status"] == "todo"]:
            _, out = c.req("POST", "/api/step", {"action": "done", "id": s_["id"]})
            got.append(out["xp"]["amount"])
        self.assertEqual(got, [10, 10, 10, 0, 0])            # 行动每天 30 封顶
        goods = [c.req("POST", "/api/record", {"type": "good", "text": f"好事{i}"})[1]["xp"]["amount"] for i in range(6)]
        self.assertEqual(goods, [6, 6, 6, 6, 6, 0])          # 好消息每天 30 封顶
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["today"]["total"], 60)
        self.assertLessEqual(d["growth"]["today"]["total"], 120)
        with Store(uid) as st:                                # 同一件事不重复计分
            from core import growth
            r = growth.award(st, "good", ref="rec:same")
            r2 = growth.award(st, "good", ref="rec:same")
            self.assertTrue(r["capped"] or r["amount"] >= 0)
            self.assertTrue(r2.get("duplicate") or r2.get("capped"))

    def test_pet_branches_by_affinity_and_evolves_once(self):
        from core import growth
        c, uid = self.onboarded("branch")
        with Store(uid) as st:   # 300 经验，好消息为主，分布在过去几天（绕开每日上限）
            for i in range(30):
                st.c.execute("INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(?,?,?,?,?,?,?)",
                             (f"x{i}", f"2026-01-{i % 28 + 1:02d}", "good" if i % 3 else "action", 10, f"seed:{i}", "",
                              f"2026-01-{i % 28 + 1:02d}T10:00:00+08:00"))
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["stage"]["key"], "baby")
        self.assertEqual(d["growth"]["leaning"], "deer")
        self.assertEqual(d["growth"]["evolved"]["to"], "baby")      # 300 经验：蛋已经孵化
        _, d = c.req("GET", "/api/bootstrap")
        self.assertIsNone(d["growth"]["evolved"])                   # 只报一次
        self.assertTrue(all(n["silhouette"] for n in d["growth"]["tree"] if n.get("tier")))
        c.req("POST", "/api/record", {"type": "good", "text": "第 306"})
        c.req("POST", "/api/record", {"type": "good", "text": "跨过 310 的那一件"})
        _, d = c.req("GET", "/api/bootstrap")
        _, d2 = c.req("GET", "/api/bootstrap")
        evolved = [x["growth"]["evolved"] for x in (d, d2) if x["growth"]["evolved"]]
        # the record call itself returns a bootstrap, so the flag may have been consumed there
        self.assertLessEqual(len(evolved), 1)
        self.assertEqual(d2["growth"]["branch"], "deer")
        self.assertEqual(d2["growth"]["stage"]["key"], "deer-1")
        self.assertIsNone(d2["growth"]["evolved"])
        self.assertEqual(growth.leaning([{"id": k, "xp": 10, "share": 1 / 3, "branch": b}
                                         for k, b in (("action", "fox"), ("good", "deer"), ("practice", "whale"))]), "star")

    def test_badges_unlock_once(self):
        c, _ = self.onboarded("badges")
        _, out = c.req("POST", "/api/record", {"type": "good", "text": "第一颗星"})
        self.assertIn("good_1", [b["id"] for b in out["growth"]["badges_new"]])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertNotIn("good_1", [b["id"] for b in d["growth"]["badges_new"]])
        self.assertTrue(next(b for b in d["growth"]["badges"] if b["id"] == "good_1")["earned"])
        cats = {b["cat"] for b in d["growth"]["badges"]}
        self.assertTrue({"对话", "计划", "好消息", "练习", "记忆", "学堂", "报告", "陪伴", "成长"} <= cats)

    # ---- nightly digest ------------------------------------------------------------
    def test_digest_protects_explicit_memory(self):
        from core import digest
        c, uid = self.onboarded("digest")
        with Store(uid) as st:
            sushi = st.add_memory("喜欢吃寿司", "preference", "chat:explicit")
            loose = st.add_memory("周末常去图书馆", "event", "chat")
            st.add_msg("user", "今天三天没去健身了，有点烦")
            self.fake.json_out = {"summary": "你说三天没去健身。", "highlights": ["有点烦"], "ops": [
                {"op": "UPDATE", "id": sushi["id"], "text": "不喜欢寿司", "kind": "preference", "source": "said"},
                {"op": "DELETE", "id": sushi["id"]},
                {"op": "UPDATE", "id": loose["id"], "text": "周末常去图书馆自习", "kind": "event", "source": "said"},
                {"op": "ADD", "text": "连续三天没去健身", "kind": "event", "source": "said"},
                {"op": "ADD", "text": "可能压力大", "kind": "insight", "source": "guess"},
                {"op": "ADD", "text": "第二条猜测", "kind": "insight", "source": "guess"},
            ]}
            out = digest.run(st)
            self.assertEqual(st.get_memory(sushi["id"])["text"], "喜欢吃寿司")     # 没有原话依据，不许动
            self.assertEqual(st.get_memory(loose["id"])["text"], "周末常去图书馆自习")
            self.assertEqual(out["stats"]["guesses"], 1)
            self.assertEqual(out["stats"]["rejected"], 3)
            self.assertEqual(st.digests(1)[0]["summary"], "你说三天没去健身。")
            # 用户当天明确更正了，才允许改，并留下依据
            st.add_msg("user", "我现在不喜欢寿司了")
            self.fake.json_out = {"summary": "x", "ops": [{"op": "UPDATE", "id": sushi["id"], "text": "现在不喜欢寿司",
                                                          "kind": "preference", "evidence": "我现在不喜欢寿司了"}]}
            digest.run(st)
            self.assertEqual(st.get_memory(sushi["id"])["text"], "现在不喜欢寿司")
            rev = st.revisions(5)[0]
            self.assertEqual((rev["old_text"], rev["evidence"]), ("喜欢吃寿司", "我现在不喜欢寿司了"))
        # 模型不可用：只写模板小结，不动记忆
        self.fake.json_out = None
        s, d = c.req("POST", "/api/memory/digest", {})
        self.assertEqual(s, 200)
        self.assertFalse(d["digest"]["by_model"])
        self.assertEqual(d["digest"]["stats"]["added"], 0)

    def test_remember_needs_explicit_request(self):
        c, uid = self.onboarded("remember_guard")
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "remember", "arguments": json.dumps({"text": "三天没健身", "kind": "event"})}])],
            [("text", "嗯，我在。")],
            [("tool_calls", [{"id": "c2", "name": "remember", "arguments": json.dumps({"text": "喜欢吃寿司", "kind": "preference"})}])],
            [("text", "记住了。")],
        ]
        _, ev = c.sse("我三天没健身了")
        self.assertNotIn("remember", [d["name"] for e, d in ev if e == "tool"])
        _, ev = c.sse("帮我记住我喜欢吃寿司")
        self.assertIn("remember", [d["name"] for e, d in ev if e == "tool"])
        with Store(uid) as st:
            texts = [m["text"] for m in st.memories()]
        self.assertIn("喜欢吃寿司", texts)
        self.assertNotIn("三天没健身", texts)

    def test_theme_and_agent_color(self):
        c, _ = self.onboarded("theme")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["profile"]["theme"], "forest")              # 建档没选时用默认
        s, d = c.req("POST", "/api/profile", {"theme": "peach", "agent_hue": "#4fd1a5"})
        self.assertEqual(s, 200)
        self.assertEqual((d["profile"]["theme"], d["profile"]["agent_hue"]), ("peach", "#4fd1a5"))
        self.assertEqual(c.req("POST", "/api/profile", {"theme": "neon"})[0], 400)
        self.assertEqual(c.req("POST", "/api/profile", {"agent_hue": "#123456"})[0], 400)

    def test_correct_memory_tool(self):
        c, uid = self.onboarded("correct")
        with Store(uid) as st:
            m = st.add_memory("喜欢吃寿司", "preference", "chat:explicit")
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "correct_memory",
                              "arguments": json.dumps({"about": "寿司", "new_text": "现在不喜欢寿司了", "quote": "我现在不喜欢寿司了"})}])],
            [("text", "好，改过来了。")],
        ]
        _, ev = c.sse("我现在不喜欢寿司了")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "correct_memory")
        self.assertTrue(tool["result"]["ok"])
        with Store(uid) as st:
            self.assertEqual(st.get_memory(m["id"])["text"], "现在不喜欢寿司了")
            self.assertEqual(st.revisions(1)[0]["reason"], "user_corrected")

    # ---- proactive & report ----------------------------------------------------
    def test_proactive_rules(self):
        from datetime import datetime
        from core.util import TZ
        base = {"onboarded": True, "proactive": "normal", "last_chat_at": "2026-10-20T10:00:00+08:00"}
        at = lambda h: datetime(2026, 10, 22, h, 0, tzinfo=TZ)
        self.assertTrue(scheduler.should_reach_out(base, False, at(10))[0])
        self.assertFalse(scheduler.should_reach_out(base, False, at(23))[0])   # quiet
        self.assertFalse(scheduler.should_reach_out(base, False, at(7))[0])    # quiet
        self.assertFalse(scheduler.should_reach_out(base, True, at(10))[0])    # unseen pending
        self.assertFalse(scheduler.should_reach_out({**base, "proactive": "off"}, False, at(10))[0])
        recent = {**base, "last_chat_at": "2026-10-22T02:00:00+08:00"}
        self.assertFalse(scheduler.should_reach_out(recent, False, at(10))[0])  # 8h < 24h
        self.assertTrue(scheduler.should_reach_out({**recent, "proactive": "more"}, False, at(15))[0])

    def test_proactive_demo_delivers_to_inbox_and_thread(self):
        c, _ = self.onboarded("pro")
        self.fake.json_out = {"text": "还在靠近「健康作息」吗？"}
        s, d = c.req("POST", "/api/proactive/now", {})
        self.assertTrue(d["sent"])
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual(len(boot["inbox"]), 1)
        self.assertTrue(boot["messages"][-1]["meta"]["proactive"])
        c.req("POST", "/api/inbox/seen", {})
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual(boot["inbox"], [])

    def test_report_surprise_from_real_data(self):
        c = Client(self.port)
        c.req("POST", "/api/auth/guest", {})
        self.fake.json_out = None  # model unavailable -> template letter
        s, d = c.req("GET", "/api/report?days=14")
        self.assertEqual(s, 200)
        self.assertFalse(d["empty"])
        self.assertTrue(d["surprise"])
        self.assertIn(str(d["facts"]["good"]), json.dumps(d["facts"]))
        self.assertTrue(d["ready"])  # the seeded guest is 15 days in
        self.assertGreaterEqual(len(d["nodes"]), 2)
        self.assertTrue(all("sources" in n for n in d["nodes"]))
        c2, _ = self.onboarded("empty_report")
        _, d2 = c2.req("GET", "/api/report?days=14")
        self.assertTrue(d2["empty"])
        self.assertIsNone(d2["narrative"])
        self.assertFalse(d2["ready"])

    # ---- 成长轨迹看板 ---------------------------------------------------------
    def test_journey_board_from_onboarding_and_moment_crud(self):
        c, uid = self.onboarded("journey")
        _, d = c.req("GET", "/api/bootstrap")
        j = d["journey"]
        self.assertEqual([w["title"] for w in j["wishes"]], ["健康作息"])   # 建档答案直接变成第一张看板
        self.assertEqual(j["wishes"][0]["category"], "body")
        wid = j["current"]
        s, d = c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": "十一点前关了灯", "feeling": "有点不习惯"})
        self.assertEqual(s, 200, d)
        mid = d["moment"]["id"]
        self.assertEqual(d["moment"]["day"], d["journey"]["today"])
        self.assertGreater(d["xp"]["amount"], 0)
        # 同一天第二条：仍然是同一天，只是多一条
        _, d = c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": "午饭后散步十分钟"})
        self.assertEqual(len({m["day"] for m in d["journey"]["moments"]}), 1)
        self.assertEqual(len(d["journey"]["moments"]), 2)
        # 未来的日子、空内容都拒绝
        today = d["journey"]["today"]
        from datetime import date, timedelta
        tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
        self.assertEqual(c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": "x", "day": tomorrow})[0], 400)
        self.assertEqual(c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": "  "})[0], 400)
        # 补记以前的日子可以
        past = (date.fromisoformat(today) - timedelta(days=40)).isoformat()
        _, d = c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": "第一次早起跑步", "day": past})
        self.assertIn(past, [m["day"] for m in d["journey"]["moments"]])
        # 编辑 / 删除
        _, d = c.req("POST", "/api/moment", {"action": "edit", "id": mid, "feeling": "其实挺舒服"})
        self.assertEqual(next(m for m in d["journey"]["moments"] if m["id"] == mid)["feeling"], "其实挺舒服")
        _, d = c.req("POST", "/api/moment", {"action": "delete", "id": mid})
        self.assertNotIn(mid, [m["id"] for m in d["journey"]["moments"]])
        # 别人看不到、也删不了
        other, _ = self.member("journey_other")
        self.assertEqual(other.req("POST", "/api/moment", {"action": "delete", "id": d["journey"]["moments"][0]["id"]})[0], 404)
        self.assertEqual(other.req("GET", "/api/bootstrap")[1]["journey"]["moments"], [])

    def test_journey_review_only_counts_range(self):
        c, uid = self.member("journey_review")
        s, d = c.req("POST", "/api/wish", {"action": "add", "title": "心里安静一点", "category": "calm", "now_text": "总是紧绷"})
        self.assertEqual(s, 200, d)
        wid = d["journey"]["current"]
        today = d["journey"]["today"]
        from datetime import date, timedelta
        day = lambda n: (date.fromisoformat(today) - timedelta(days=n)).isoformat()
        for n, t in ((1, "开完会给自己留了十分钟喝茶"), (3, "下午出去散步，安静地走了一圈"), (5, "睡前喝茶，放松下来"), (20, "周末去公园散步")):
            c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": t, "day": day(n)})
        _, r = c.req("GET", f"/api/wish/review?id={wid}&days=7")
        self.assertEqual((r["count"], r["active_days"]), (3, 3))
        self.assertEqual(r["top"]["word"], "喝茶")
        self.assertIn("过去 7 天，你留下了 3 个瞬间，其中 2 次提到了「喝茶」", r["line"])
        _, r30 = c.req("GET", f"/api/wish/review?id={wid}&days=30")
        self.assertEqual(r30["count"], 4)
        # 空区间：直说，不编
        c2, _ = self.member("journey_empty")
        _, d2 = c2.req("POST", "/api/wish", {"action": "add", "title": "", "category": "freedom"})
        _, e = c2.req("GET", f"/api/wish/review?id={d2['journey']['current']}&days=15")
        self.assertEqual(e["count"], 0)
        self.assertTrue(e["line"].startswith("这段时间还没有留下记录"))
        _, r = c.req("POST", "/api/wish/reflect", {"id": wid, "days": 7, "text": "好像没那么紧了"})
        self.assertEqual(r["reflections"][0]["text"], "好像没那么紧了")

    def test_journey_insight_needs_confirmation(self):
        c, uid = self.member("journey_insight")
        _, d = c.req("POST", "/api/wish", {"action": "add", "title": "敢开口", "category": "confidence"})
        wid = d["journey"]["current"]
        self.fake.json_out = {"text": "会不会…", "claim": "x", "basis": []}
        _, out = c.req("POST", "/api/wish/insight", {"id": wid})
        self.assertIsNone(out["insight"])           # 记录不足 4 条不生成
        ids = []
        for t in ("课上举手了", "主动问了老师问题", "和室友说出了不舒服", "投了稿"):
            _, d = c.req("POST", "/api/moment", {"action": "add", "wish_id": wid, "text": t})
            ids.append(d["moment"]["id"])
        self.fake.json_out = {"text": "编出来的发现", "claim": "很勇敢", "basis": ["mo_fake"]}
        _, out = c.req("POST", "/api/wish/insight", {"id": wid})
        self.assertIsNone(out["insight"])           # 依据对不上真实记录就不要
        self.fake.json_out = {"text": "你担心做得不够好，但还是投了稿。这算一次勇敢的尝试吗？",
                              "claim": "害怕不够好时，仍然愿意尝试", "basis": [ids[3], "mo_fake"]}
        _, out = c.req("POST", "/api/wish/insight", {"id": wid})
        ins = out["insight"]
        self.assertEqual(ins["basis"], [ids[3]])
        with Store(uid) as st:
            self.assertNotIn("害怕不够好时，仍然愿意尝试", [m["text"] for m in st.memories(statuses=("active", "guess"))])
        _, out = c.req("POST", "/api/wish/insight", {"insight_id": ins["id"], "answer": "yes"})
        self.assertEqual(out["memory"]["text"], "害怕不够好时，仍然愿意尝试")
        self.assertIsNone(out["journey"]["insights"][wid])

    def test_chat_only_proposes_moments(self):
        c, uid = self.onboarded("journey_chat")
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "propose_moment",
                              "arguments": json.dumps({"text": "昨晚十一点就睡了", "feeling": "早上很清醒"})}])],
            [("text", "真好。要不要把它留在轨迹上？")],
        ]
        s, ev = c.sse("昨晚十一点就睡了，早上很清醒")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "propose_moment")
        self.assertTrue(tool["result"]["pending"])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["journey"]["moments"], [])     # 没点「留下」就什么都没存
        p = tool["result"]["proposal"]
        _, d = c.req("POST", "/api/moment", {"action": "add", "wish_id": p["wish_id"], "text": p["text"], "feeling": p["feeling"], "source": "chat"})
        self.assertEqual(d["moment"]["source"], "chat")

    # ---- 蜕变计划：路径（习惯 / 里程碑 / 小步）与时间 ----------------------------
    def test_plan_path_habits_milestones_and_target(self):
        c, uid = self.member("path")
        from datetime import date, timedelta
        s, d = c.req("POST", "/api/wish", {"action": "add", "title": "规律健身", "category": "body"})
        self.assertEqual(s, 200, d)
        w = d["journey"]["wishes"][0]
        today = d["journey"]["today"]
        # 默认计划日：定下后 90 天；改成更早于定下日会被拒绝
        self.assertEqual(w["target_day"], (date.fromisoformat(w["started"]) + timedelta(days=30)).isoformat())
        bad = (date.fromisoformat(w["started"]) - timedelta(days=1)).isoformat()
        self.assertEqual(c.req("POST", "/api/wish", {"action": "edit", "id": w["id"], "target_day": bad})[0], 400)
        new_t = (date.fromisoformat(today) + timedelta(days=60)).isoformat()
        _, d = c.req("POST", "/api/wish", {"action": "edit", "id": w["id"], "target_day": new_t})
        self.assertEqual(d["journey"]["wishes"][0]["target_day"], new_t)
        # 习惯：每周 3 次；打卡一次给行动经验，同一天再打不重复计分；撤销后本周次数回落
        s, d = c.req("POST", "/api/habit", {"action": "add", "wish_id": w["id"], "title": "去健身房", "freq": "weekly", "per_week": 3})
        self.assertEqual(s, 200, d)
        hid = d["habit"]["id"]
        self.assertEqual((d["habit"]["need"], d["habit"]["freq_text"]), (3, "每周 3 次"))
        _, d = c.req("POST", "/api/habit", {"action": "check", "id": hid})
        self.assertEqual(d["xp"]["amount"], 10)
        h = d["journey"]["wishes"][0]["habits"][0]
        self.assertEqual((h["today"], h["week"]), (True, 1))
        _, d = c.req("POST", "/api/habit", {"action": "check", "id": hid})
        self.assertNotIn("xp", d)
        _, d = c.req("POST", "/api/habit", {"action": "uncheck", "id": hid})
        self.assertEqual(d["journey"]["wishes"][0]["habits"][0]["week"], 0)
        _, d = c.req("POST", "/api/habit", {"action": "check", "id": hid})
        self.assertTrue(d["xp"]["duplicate"])          # 撤销再打卡，不会再拿一次经验
        # 小光的提议里和路径上重复的项不会再加一遍
        _, d = c.req("POST", "/api/plan/apply", {"wish_id": w["id"], "habits": [{"title": "去 健身房", "freq": "daily"}],
                                                  "steps": [{"title": "买一双跑鞋"}]})
        self.assertEqual(d["made"], {"milestones": 0, "habits": 0, "steps": 1})
        # 里程碑
        s, d = c.req("POST", "/api/milestone", {"action": "add", "wish_id": w["id"], "title": "能连续跑 5 公里", "due_day": new_t})
        mid = d["milestone"]["id"]
        _, d = c.req("POST", "/api/milestone", {"action": "done", "id": mid})
        self.assertEqual(d["journey"]["wishes"][0]["milestones"][0]["status"], "done")
        self.assertIn("第一站", [b["name"] for b in d["growth"]["badges"] if b["earned"]])
        # 休息日：记一次、重复点不重复记、可以撤销
        _, d = c.req("POST", "/api/record", {"type": "rest"})
        _, d = c.req("POST", "/api/record", {"type": "rest"})
        self.assertEqual(d["journey"]["rest_days"], [today])
        self.assertEqual(sum(1 for r in d["records"] if r["type"] == "rest"), 1)
        _, d = c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.assertEqual(d["journey"]["rest_days"], [])
        # 内心戏是好消息页的第二种记录；find 不能再新建
        _, d = c.req("POST", "/api/record", {"type": "meme", "text": "我：早睡。也是我：再刷十分钟"})
        self.assertEqual(d["record"]["type"], "meme")
        self.assertEqual(c.req("POST", "/api/record", {"type": "find", "text": "x"})[0], 400)
        # 别人动不了
        other, _ = self.member("path_other")
        self.assertEqual(other.req("POST", "/api/habit", {"action": "check", "id": hid})[0], 400)
        self.assertEqual(other.req("POST", "/api/milestone", {"action": "done", "id": mid})[0], 404)

    def test_chat_proposes_plan_and_user_applies(self):
        c, uid = self.onboarded("plan_chat")
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "propose_plan", "arguments": json.dumps({
                "wish": "健康作息",
                "milestones": [{"title": "一周有 5 天 12 点前睡", "due_in_days": 14}],
                "habits": [{"title": "11 点放下手机", "freq": "daily"}, {"title": "晨跑", "freq": "weekly", "per_week": 2}],
                "steps": [{"title": "把充电器挪到客厅"}]})}])],
            [("text", "你看看哪些想加进计划。")],
        ]
        s, ev = c.sse("帮我规划一下健康作息这条路")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "propose_plan")
        self.assertTrue(tool["result"]["pending"])
        _, d = c.req("GET", "/api/bootstrap")
        w = d["journey"]["wishes"][0]
        self.assertEqual((w["habits"], w["milestones"]), ([], []))     # 没确认就什么都没加
        plan = tool["result"]["plan"]
        _, d = c.req("POST", "/api/plan/apply", {"wish_id": tool["result"]["wish_id"], "milestones": plan["milestones"],
                                                  "habits": plan["habits"][:1], "steps": plan["steps"]})
        self.assertEqual(d["made"], {"milestones": 1, "habits": 1, "steps": 1})
        w = d["journey"]["wishes"][0]
        self.assertEqual([h["title"] for h in w["habits"]], ["11 点放下手机"])
        self.assertTrue(w["milestones"][0]["due_day"])
        self.assertIn("把充电器挪到客厅", [s_["title"] for s_ in d["steps"] if s_["wish_id"] == w["id"]])
        # 「今天跑了」→ 打卡工具
        c.req("POST", "/api/habit", {"action": "add", "wish_id": w["id"], "title": "晨跑", "freq": "weekly", "per_week": 2})
        self.fake.turns = [[("tool_calls", [{"id": "c2", "name": "checkin_habit", "arguments": '{"title":"晨跑"}'}])], [("text", "跑完了，真好。")]]
        s, ev = c.sse("今天早上去晨跑了")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "checkin_habit")
        self.assertEqual(tool["result"]["habit"]["week"], 1)

    def test_cheer_rotates_every_half_day(self):
        from core import cheer
        c, uid = self.member("cheer")
        _, d = c.req("GET", "/api/bootstrap")
        ch = d["cheer"]
        self.assertEqual((ch["kind"], ch["slot"]), ("quote", cheer.slot()))
        self.assertIn(ch["text"], [q[0] for q in cheer.QUOTES])
        self.assertEqual(c.req("GET", "/api/bootstrap")[1]["cheer"]["text"], ch["text"])   # 同一时段不变
        with Store(uid) as st:
            st.add_record("good", "楼下的猫让我摸了")
            st.add_record("meme", "今天的我：社恐但嘴硬")
            self.fake.json_out = {"text": "这不是小事，而是你在照顾自己。"}
            self.assertIsNone(cheer.refresh(uid, cheer.slot()))              # 「不是……而是」的句子不用
            self.fake.json_out = {"text": "这几天你一直在留意身边的小可爱。"}
            out = cheer.refresh(uid, cheer.slot())
        self.assertEqual(out["kind"], "you")
        self.assertEqual(c.req("GET", "/api/bootstrap")[1]["cheer"]["text"], "这几天你一直在留意身边的小可爱。")
        with Store(uid) as st:
            st.set_profile({"cheer": {**out, "slot": "2000-01-01-am"}})     # 时段过去了 → 换一句
        self.assertNotEqual(c.req("GET", "/api/bootstrap")[1]["cheer"]["slot"], "2000-01-01-am")

    # ---- 偷懒日 ------------------------------------------------------------------
    def test_lazy_day_pauses_today_and_offers_adjust(self):
        c, uid = self.member("rest_mode")
        _, d = c.req("POST", "/api/wish", {"action": "add", "title": "规律健身", "category": "body"})
        wid = d["journey"]["current"]
        _, d = c.req("POST", "/api/habit", {"action": "add", "wish_id": wid, "title": "去健身房", "freq": "daily"})
        hid = d["habit"]["id"]
        # 单项暂停：这个习惯今天先不做；之后又做了，暂停自动取消
        _, d = c.req("POST", "/api/habit", {"action": "skip", "id": hid})
        self.assertTrue(d["journey"]["wishes"][0]["habits"][0]["skipped"])
        _, d = c.req("POST", "/api/habit", {"action": "check", "id": hid})
        h = d["journey"]["wishes"][0]["habits"][0]
        self.assertEqual((h["skipped"], h["today"]), (False, True))
        # 调轻一档：每天 → 每周 3 次 → 2 → 1，到 1 次就不能再调
        for want in ("每周 3 次", "每周 2 次", "每周 1 次"):
            _, d = c.req("POST", "/api/habit", {"action": "ease", "id": hid})
            self.assertEqual(d["eased"], want)
        self.assertEqual(c.req("POST", "/api/habit", {"action": "ease", "id": hid})[0], 400)
        # 一键偷懒（带原因）：行动这项任务暂停并算作完成，休息记录留在时间线上
        c2, uid = self.member("rest_mode2")       # 今天还没做任何行动的人
        _, d = c2.req("POST", "/api/record", {"type": "rest", "text": "今天偷个懒：有点累"})
        q = next(x for x in d["growth"]["quests"] if x["id"] == "action")
        self.assertTrue(q["done"] and q.get("rest"))
        self.assertIn("今天偷个懒：有点累", [a["text"] for a in d["activity"]])
        c = c2
        # 偷懒日小光不主动打扰（演示用的强制触发不受影响）
        with Store(uid) as st:
            st.set_profile({"onboarded": True, "last_chat_at": "", "last_proactive_at": ""})
            self.assertEqual(scheduler.deliver(st)["reason"], "今天是偷懒日，不打扰")
        # 不偷懒了：任务恢复
        _, d = c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.assertFalse(next(x for x in d["growth"]["quests"] if x["id"] == "action").get("rest"))

    def test_chat_lazy_day_and_adjust_habit(self):
        c, uid = self.onboarded("lazy_chat")
        _, d = c.req("GET", "/api/bootstrap")
        wid = d["journey"]["current"]
        c.req("POST", "/api/habit", {"action": "add", "wish_id": wid, "title": "11 点放下手机", "freq": "daily"})
        self.fake.turns = [[("tool_calls", [{"id": "c1", "name": "log_lazy_day", "arguments": '{"note":"加班太累"}'}])],
                           [("text", "收到，今天给自己放个假吧。")],
                           [("tool_calls", [{"id": "c2", "name": "adjust_habit", "arguments": '{"title":"放下手机","action":"ease"}'}])],
                           [("text", "调成每周 3 次了。")]]
        s, ev = c.sse("今天加班太累了，想偷个懒")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "log_lazy_day")
        self.assertEqual(tool["result"]["record"]["text"], "今天偷个懒：加班太累")
        s, ev = c.sse("放下手机那个每天做有点难，能不能少一点")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "adjust_habit")
        self.assertEqual(tool["result"]["done"], "调成每周 3 次")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["journey"]["wishes"][0]["habits"][0]["freq_text"], "每周 3 次")

    # ---- 定时任务 ------------------------------------------------------------------
    def test_tasks_schedule_fire_and_toggle(self):
        from datetime import timedelta
        from core.util import now
        c, uid = self.onboarded("tasks_user")
        s, d = c.req("POST", "/api/task", {"action": "add", "title": "开财富与爱情的会", "repeat": "once", "in_minutes": 5})
        self.assertEqual(s, 200, d)
        tid = d["task"]["id"]
        self.assertTrue(d["task"]["when"].endswith("一次"))
        self.assertIn(tid, [t["id"] for t in d["tasks"]])
        _, d = c.req("POST", "/api/task", {"action": "add", "title": "早安鼓励", "kind": "ai", "message": "给我一句鼓励",
                                           "repeat": "daily", "time": "08:00"})
        daily = d["task"]["id"]
        self.assertEqual(d["task"]["when"], "每天 08:00")
        self.assertEqual(c.req("POST", "/api/task", {"action": "add", "title": "x", "repeat": "daily", "time": "25:00"})[0], 400)
        # 别人碰不到
        other, _ = self.member("tasks_other")
        self.assertEqual(other.req("POST", "/api/task", {"action": "off", "id": tid})[0], 404)
        # 还没到点：什么都不发
        self.assertEqual(scheduler.run_tasks(now() + timedelta(minutes=2)), 0)
        # 到点：remind 不调模型，消息进对话和收件箱，一次性任务关掉
        self.fake.json_out = None
        _, before = c.req("GET", "/api/pulse")
        self.assertGreaterEqual(scheduler.run_tasks(now() + timedelta(minutes=6)), 1)
        _, d = c.req("GET", "/api/bootstrap")
        last = d["messages"][-1]
        self.assertEqual(last["meta"]["task"], tid)
        self.assertIn("开财富与爱情的会", last["content"])
        self.assertFalse(next(t for t in d["tasks"] if t["id"] == tid)["enabled"])
        _, after = c.req("GET", "/api/pulse")
        self.assertGreater(after["unseen"], before["unseen"])
        # ai 任务：到点由小光写一句；每天的任务跑完排到下一天
        self.fake.json_out = {"text": "早呀，今天也从一件小事开始就好。"}
        scheduler.run_tasks(now() + timedelta(days=1, hours=1))
        _, d = c.req("GET", "/api/bootstrap")
        self.assertIn("早呀，今天也从一件小事开始就好。", [m["content"] for m in d["messages"]])
        t = next(t for t in d["tasks"] if t["id"] == daily)
        self.assertTrue(t["enabled"])
        # 开关与内置例行任务
        _, d = c.req("POST", "/api/task", {"action": "off", "id": daily})
        self.assertFalse(next(t for t in d["tasks"] if t["id"] == daily)["enabled"])
        _, d = c.req("POST", "/api/task", {"action": "delete", "id": daily})
        self.assertNotIn(daily, [t["id"] for t in d["tasks"]])

    def test_chat_schedules_task(self):
        c, uid = self.onboarded("tasks_chat")
        self.fake.turns = [
            [("tool_calls", [{"id": "c1", "name": "schedule_task", "arguments": json.dumps(
                {"title": "开会", "kind": "remind", "repeat": "once", "in_minutes": 5})}])],
            [("text", "好，五分钟后叫你。")],
        ]
        s, ev = c.sse("你能5分钟后提醒我开一个会议吗")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "schedule_task")
        self.assertTrue(tool["result"]["ok"])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual([t["title"] for t in d["tasks"]], ["开会"])

    # ---- 记忆：三天原话 + 笔记本 + 翻聊天记录 ------------------------------------------
    def test_history_window_notebook_and_search(self):
        from datetime import timedelta
        from core import agent, digest
        from core.util import now
        c, uid = self.onboarded("memory_long")
        with Store(uid) as st:
            for d, text in ((6, "上周我和 Mia 去看了海"), (2, "前天面试被问到最喜欢的书"), (1, "昨天熬夜到两点")):
                m = st.add_msg("user", text)
                st.c.execute("UPDATE msg SET created_at=? WHERE id=?", ((now() - timedelta(days=d)).isoformat(timespec="seconds"), m["id"]))
            for i in range(40):     # 让总条数超过「至少 16 轮」，三天的窗口才起作用
                st.add_msg("assistant" if i % 2 else "user", f"今天的闲聊 {i}")
            hist = agent.history(st)
            texts = " ".join(h["content"] for h in hist)
            self.assertIn("前天面试被问到最喜欢的书", texts)
            self.assertIn("昨天熬夜到两点", texts)
            self.assertNotIn("去看了海", texts)                       # 超过三天的不在上下文里
            self.assertTrue(any(h["content"].startswith("［") for h in hist if h["role"] == "user"))
            hits = agent.search_chats(st, "和 Mia 去看海")
            self.assertIn("上周我和 Mia 去看了海", [h["text"] for h in hits])   # 但能翻到
            # 夜里整理顺手更新笔记本
            st.add_msg("user", "我决定下个月开始学游泳")
            self.fake.json_out = {"summary": "你决定学游泳。", "highlights": [], "ops": [],
                                  "notebook": "最近的生活：决定下个月开始学游泳。\n在意的人：Mia。"}
            digest.run(st)
            self.assertIn("学游泳", st.profile()["notebook"]["text"])
            sp = agent.system_prompt(st, [])
            self.assertIn("你的笔记本", sp)
            self.assertIn("学游泳", sp)
        _, d = c.req("POST", "/api/notebook", {"text": "在意的人：Mia、室友。"})
        self.assertEqual(d["profile"]["notebook"]["by"], "user")

    def test_persona_and_custom_moments(self):
        from core import agent
        c, uid = self.onboarded("persona_user")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["profile"]["persona"], "gentle")
        self.assertEqual(c.req("POST", "/api/profile", {"persona": "robot"})[0], 400)
        _, d = c.req("POST", "/api/profile", {"persona": "lively", "custom_moods": ["松了口气", " ", "超开心的那种很长的心情"]})
        self.assertEqual(d["profile"]["custom_moods"], ["松了口气", "超开心的那种很长"])
        with Store(uid) as st:
            self.assertIn("活泼", agent.system_prompt(st, []))
        wid = d["journey"]["current"]
        _, d = c.req("POST", "/api/wish", {"action": "edit", "id": wid, "prompts": ["今天哪一刻我没有逃避？", ""]})
        self.assertEqual(d["journey"]["wishes"][0]["prompts"], ["今天哪一刻我没有逃避？"])

    def test_rename_nickname_and_username(self):
        c, uid = self.onboarded("old_name")
        _, d = c.req("POST", "/api/profile", {"nickname": "小鱼"})
        self.assertEqual(d["profile"]["nickname"], "小鱼")
        s, d = c.req("POST", "/api/auth/rename", {"username": "new_name"})
        self.assertEqual((s, d["user"]["username"]), (200, "new_name"))
        self.member("taken_name")
        self.assertEqual(c.req("POST", "/api/auth/rename", {"username": "taken_name"})[0], 409)
        self.assertEqual(c.req("POST", "/api/auth/rename", {"username": "x"})[0], 400)
        c2 = Client(self.port)
        self.assertEqual(c2.req("POST", "/api/auth/login", {"username": "new_name", "password": "secret12"})[0], 200)
        g = Client(self.port)
        g.req("POST", "/api/auth/guest", {"seed": False})
        self.assertEqual(g.req("POST", "/api/auth/rename", {"username": "guest_x"})[0], 400)


if __name__ == "__main__":
    unittest.main()
