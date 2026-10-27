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
from core import auth, llm, scheduler  # noqa: E402
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
        sys_prompt = self.fake.seen[0][0]["content"]
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


if __name__ == "__main__":
    unittest.main()
