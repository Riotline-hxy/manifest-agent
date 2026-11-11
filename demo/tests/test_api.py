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
os.environ["MANIFEST_ADMIN_KEY"] = "test-admin"
sys.path.insert(0, DEMO)

import server  # noqa: E402
from core import auth, llm, scheduler, tasks, town, webpush  # noqa: E402
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
        self.seen_json = []    # captured complete_json messages
        self.seen_tools = []   # tool names offered per stream_chat call

    def stream(self, messages, tools=None, model=None, reasoning=None, timeout=None):
        self.seen.append(messages)
        self.seen_tools.append([t["function"]["name"] for t in tools or []])
        script = self.turns.pop(0) if self.turns else [("text", "嗯，我在。")]
        for ev in script:
            yield ev
        yield ("done", {"finish_reason": "stop", "usage": None})

    def complete(self, messages, model=None, timeout=40, reasoning="low"):
        self.seen_json.append(messages)
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

    def sse(self, text, **extra):
        status, data, _ = self.req("POST", "/api/chat", {"text": text, **extra}, raw=True)
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
        cls.pushed = []   # (endpoint, headers) sent to the fake push service
        cls._orig_post = webpush._post
        webpush._post = lambda ep, headers: (cls.pushed.append((ep, headers)), 410 if "gone" in ep else 201)[1]
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
        webpush._post = cls._orig_post
        webpush.reset_for_tests()
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
        a.req("POST", "/api/moment", {"action": "add", "text": "A 的秘密瞬间"})
        _, db = b.req("GET", "/api/bootstrap")
        self.assertEqual(db["user"]["id"], uid_b)
        blob = json.dumps(db, ensure_ascii=False)
        self.assertNotIn("A 的秘密瞬间", blob)
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
        s, _ = c.req("POST", "/api/moment", {"action": "add", "text": "x"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(s, 403)
        s, _ = c.req("POST", "/api/moment", {"action": "add", "text": "x"}, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(s, 200)

    def test_guest_seed_and_claim_keeps_data(self):
        c = Client(self.port)
        s, d = c.req("POST", "/api/auth/guest", {})
        self.assertEqual(s, 201)
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertTrue(boot["profile"]["onboarded"])
        self.assertGreaterEqual(boot["counts"]["moments"], 5)
        self.assertTrue(any(not m["wish_id"] for m in boot["journey"]["moments"]))   # 有不挂愿望的瞬间
        self.assertEqual([r["type"] for r in boot["records"]], ["rest", "rest"])
        s, d = c.req("POST", "/api/auth/register", {"username": "claimed", "password": "secret12"})
        self.assertEqual((s, d["user"]["kind"]), (200, "member"))
        _, boot2 = c.req("GET", "/api/bootstrap")
        self.assertEqual(boot2["counts"]["moments"], boot["counts"]["moments"])

    def test_trial_chat_is_public_and_ends_in_a_step(self):
        c = Client(self.port)
        hist = [{"role": "assistant", "content": "现在一般几点睡？"}, {"role": "user", "content": "总是刷手机到一两点"}]
        self.fake.json_out = {"reply": "刷到一两点，第二天肯定很难受吧。是停不下来，还是睡不着？", "step": None}
        s, d = c.req("POST", "/api/trial/chat", {"goal": "想早点睡", "history": hist})
        self.assertEqual((s, d["step"], d["round"]), (200, None, 1), d)
        self.assertIsNone(c.cookie)                   # no account is created
        # finishing must return a step; the model's meta prefix on tomorrow is stripped
        self.fake.json_out = {"reply": "今晚先试试这个？", "step": {"title": "11 点把手机放到书桌上", "when": "今晚", "why": "离手就好"},
                              "remember": ["你常刷手机到一两点"], "tomorrow": "明天我来问你，昨晚放下了吗？", "why_goal": "白天总犯困"}
        s, d = c.req("POST", "/api/trial/chat", {"goal": "想早点睡", "history": hist, "finish": True})
        self.assertEqual(d["step"]["title"], "11 点把手机放到书桌上")
        self.assertEqual(d["tomorrow"], "昨晚放下了吗？")
        # model down -> scripted fallback still ends in a step
        self.fake.json_out = None
        s, d = c.req("POST", "/api/trial/chat", {"goal": "想早点睡", "history": hist, "finish": True})
        self.assertEqual(s, 200)
        self.assertTrue(d["step"]["title"] and d["remember"])
        self.assertEqual(c.req("POST", "/api/trial/chat", {"goal": "", "history": hist})[0], 400)
        self.assertEqual(c.req("POST", "/api/trial/chat", {"goal": "想早点睡", "history": hist[:1]})[0], 400)

    def test_onboard_carries_the_trial_step(self):
        c, uid = self.member("carry")
        carry = {"step": "11 点把手机放到书桌上", "why": "离手就好", "remember": ["你常刷手机到一两点"]}
        s, d = c.req("POST", "/api/onboard", {"answers": ONBOARD, "carry": carry})
        self.assertEqual(s, 200, d)
        self.assertIn("11 点把手机放到书桌上", [x["title"] for x in d["steps"]])
        self.assertIn("你常刷手机到一两点", [m["text"] for m in d["memories"]])
        self.assertIn("11 点把手机放到书桌上", d["messages"][-1]["content"])

    def test_admin_is_locked_and_shows_counts_not_content(self):
        c, uid = self.onboarded("adm_user")
        self.fake.turns = [[("text", "嗯，我在。")]]
        c.sse("我的秘密是我怕黑")
        a = Client(self.port)
        self.assertEqual(a.req("GET", "/api/admin/overview")[0], 401)
        self.assertEqual(c.req("GET", "/api/admin/users")[0], 401)       # a user session is not an admin session
        self.assertEqual(a.req("POST", "/api/admin/login", {"key": "nope"})[0], 401)
        s, _ = a.req("POST", "/api/admin/login", {"key": "test-admin"})
        self.assertEqual(s, 200)
        s, ov = a.req("GET", "/api/admin/overview?days=7")
        self.assertEqual(s, 200, ov)
        self.assertGreaterEqual(ov["users"]["members"], 1)
        self.assertEqual(len(ov["series"]), 7)
        self.assertGreaterEqual(ov["series"][-1]["msgs"], 1)
        s, us = a.req("GET", "/api/admin/users")
        row = next(u for u in us["users"] if u["id"] == uid)
        self.assertEqual((row["username"], row["msgs"], row["profile"]["intent_primary"]), ("adm_user", 1, "健康作息"))
        s, one = a.req("GET", f"/api/admin/user?id={uid}")
        self.assertEqual(s, 200)
        blob = json.dumps([us, one], ensure_ascii=False)
        self.assertNotIn("怕黑", blob)                                     # no chat content in the admin API
        self.assertNotIn("pw_hash", blob)
        self.assertEqual(a.req("GET", "/api/admin/user?id=u_0000000000000000")[0], 404)
        a.req("POST", "/api/admin/logout")
        self.assertEqual(a.req("GET", "/api/admin/users")[0], 401)
        self.assertEqual(c.req("GET", "/admin", raw=True)[0], 200)

    def test_tokens_are_counted_per_user(self):
        c, uid = self.onboarded("tok_user")
        with Store(uid):
            llm._note_usage({"total_tokens": 100, "prompt_tokens": 90, "completion_tokens": 10,
                             "prompt_tokens_details": {"cached_tokens": 80}}, "chat")
            with Store(uid):                       # nested open/close keeps the outer attribution
                pass
            llm._note_usage({"total_tokens": 40, "prompt_tokens": 35, "completion_tokens": 5}, "bg")
        llm._note_usage({"total_tokens": 7}, "bg")  # no current user (e.g. landing demo): site-wide only
        a = Client(self.port)
        a.req("POST", "/api/admin/login", {"key": "test-admin"})
        _, one = a.req("GET", f"/api/admin/user?id={uid}")
        t = one["tokens"]["d30"]
        self.assertEqual((t["tokens"], t["calls"], t["tokens_chat"], t["tokens_bg"], t["tokens_cached"]), (140, 2, 100, 40, 80))
        _, us = a.req("GET", "/api/admin/users")
        self.assertEqual(next(u for u in us["users"] if u["id"] == uid)["tokens_30d"], 140)
        _, b = c.req("GET", "/api/bootstrap")
        self.assertNotIn("llm_tokens", json.dumps(b))                     # users don't see their usage (yet)

    def test_admin_can_delete_a_user_and_guests(self):
        c, uid = self.onboarded("del_me")
        with Store(uid):
            llm._note_usage({"total_tokens": 10}, "chat")
        tasks.add(uid, "喝水", time="09:00", repeat="daily")
        a = Client(self.port)
        a.req("POST", "/api/admin/login", {"key": "test-admin"})
        self.assertEqual(c.req("POST", "/api/admin/user/delete", {"id": uid, "confirm": "del_me"})[0], 401)  # not as a user
        self.assertEqual(a.req("POST", "/api/admin/user/delete", {"id": uid, "confirm": "nope"})[0], 400)
        s, _ = a.req("POST", "/api/admin/user/delete", {"id": uid, "confirm": "del_me"})
        self.assertEqual(s, 200)
        self.assertEqual(c.req("GET", "/api/bootstrap")[0], 401)       # logged out at once
        self.assertFalse(os.path.exists(os.path.join(TMP, "u", uid)))
        self.assertEqual(tasks.list_for(uid), [])
        _, us = a.req("GET", "/api/admin/users")
        self.assertNotIn(uid, [u["id"] for u in us["users"]])
        self.assertEqual(a.req("GET", f"/api/admin/user?id={uid}")[0], 404)
        # a new account can take the freed username
        self.assertEqual(Client(self.port).req("POST", "/api/auth/register", {"username": "del_me", "password": "secret12"})[0], 201)

        g = Client(self.port)
        g.req("POST", "/api/auth/guest", {"seed": False})
        _, us = a.req("GET", "/api/admin/users")
        n = sum(1 for u in us["users"] if u["kind"] == "guest")
        self.assertEqual(a.req("POST", "/api/admin/guests/delete", {"confirm": "删除"})[0], 400)
        s, out = a.req("POST", "/api/admin/guests/delete", {"confirm": f"删除 {n} 个体验账号"})
        self.assertEqual((s, out["deleted"]), (200, n))
        _, us = a.req("GET", "/api/admin/users")
        self.assertEqual([u for u in us["users"] if u["kind"] == "guest"], [])

    def wait_pushes(self, n, timeout=3.0):
        t = time.time()
        while len(self.pushed) < n and time.time() - t < timeout:
            time.sleep(0.05)
        return self.pushed

    def test_push_subscribe_notify_and_cleanup(self):
        self.pushed.clear()
        c, uid = self.onboarded("push_user")
        s, k = c.req("GET", "/api/push/key")
        self.assertEqual((s, len(k["key"]), k["devices"]), (200, 87, 0))   # 65-byte P-256 point, base64url
        self.assertEqual(c.req("POST", "/api/push/subscribe", {"subscription": {"endpoint": "http://evil"}})[0], 400)
        # 只认浏览器真正的推送服务：别的 https 地址（内网、任意网站、换了端口）不收，不然登录用户能让服务器去敲任意地址
        for bad in ("https://push.example/abc", "https://127.0.0.1/x", "https://fcm.googleapis.com.evil.cn/x",
                    "https://fcm.googleapis.com:8443/x", "https://evil.cn/fcm.googleapis.com"):
            self.assertEqual(c.req("POST", "/api/push/subscribe", {"subscription": {"endpoint": bad}})[0], 400, bad)
        self.assertEqual(webpush.subs(uid), [])
        sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "x", "auth": "y"}}
        s, out = c.req("POST", "/api/push/subscribe", {"subscription": sub})
        self.assertEqual((s, out["devices"]), (200, 1))
        c.req("POST", "/api/push/subscribe", {"subscription": {"endpoint": "https://fcm.googleapis.com/fcm/send/gone"}})

        # a proactive message wakes every device; the service worker then fetches the text
        self.fake.json_out = {"text": "还在靠近「健康作息」吗？"}
        c.req("POST", "/api/proactive/now", {})
        pushed = self.wait_pushes(2)
        self.assertEqual(sorted(ep for ep, _ in pushed), ["https://fcm.googleapis.com/fcm/send/abc", "https://fcm.googleapis.com/fcm/send/gone"])
        ep, hd = pushed[0]
        self.assertTrue(hd["Authorization"].startswith("vapid t=") and f"k={k['key']}" in hd["Authorization"])
        self.assertEqual(hd["Content-Length"], "0")                         # no payload goes to the push service
        s, latest = c.req("GET", "/api/push/latest")
        self.assertEqual((latest["title"], latest["text"]), ("阿光", "还在靠近「健康作息」吗？"))
        time.sleep(0.2)
        self.assertEqual([x["endpoint"] for x in webpush.subs(uid)], ["https://fcm.googleapis.com/fcm/send/abc"])  # 410 pruned

        # the same device logging in as someone else moves to that account; logout unbinds it
        d, uid2 = self.onboarded("push_other")
        d.req("POST", "/api/push/subscribe", {"subscription": sub})
        self.assertEqual((webpush.subs(uid), len(webpush.subs(uid2))), ([], 1))
        d.req("POST", "/api/auth/logout", {"endpoint": sub["endpoint"]})
        self.assertEqual(webpush.subs(uid2), [])

        # test push + admin delete removes subscriptions
        c.req("POST", "/api/push/subscribe", {"subscription": sub})
        n = len(self.pushed)
        s, out = c.req("POST", "/api/push/test", {})
        self.assertEqual((s, out["sent"]), (200, 1))
        self.assertEqual(len(self.pushed), n + 1)
        a = Client(self.port)
        a.req("POST", "/api/admin/login", {"key": "test-admin"})
        self.assertEqual(a.req("GET", f"/api/admin/user?id={uid}")[1]["push_devices"], 1)
        a.req("POST", "/api/admin/user/delete", {"id": uid, "confirm": "push_user"})
        self.assertEqual(webpush.subs(uid), [])

    def test_pwa_files_are_served(self):
        c = Client(self.port)
        for path, ctype in (("/manifest.webmanifest", "application/manifest+json"), ("/sw.js", "javascript"),
                            ("/icons/icon-192.png", "image/png"), ("/icons/apple-touch-icon.png", "image/png")):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request("GET", path)
            r = conn.getresponse()
            r.read()
            self.assertEqual(r.status, 200, path)
            self.assertIn(ctype, r.getheader("Content-Type"), path)
            conn.close()
        s, html, _ = c.req("GET", "/", raw=True)
        self.assertIn('rel="manifest"', html)

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
        # 三段都能跳过：什么都不填也能进门，用默认值，不建愿望
        skip = Client(self.port)
        skip.req("POST", "/api/auth/register", {"username": "onb_skip", "password": "secret12"})
        s, d = skip.req("POST", "/api/onboard", {"answers": {}})
        self.assertEqual(s, 200, d)
        p = d["profile"]
        self.assertEqual((p["agent_name"], p["agent_avatar_id"], p["persona"], p["care_style"]), ("小光", "cloud.moon.jelly", "gentle", "nudge"))
        self.assertTrue(p["onboarded"])
        self.assertEqual(d["journey"]["wishes"], [])
        self.assertIn("不急着定目标", d["messages"][-1]["content"])
        s, d = skip.req("POST", "/api/onboard", {"answers": {"persona": "evil", "care_style": "x", "schedule_hint": "半夜", "agent_avatar_id": "x.y.z"}})
        self.assertEqual((d["profile"]["persona"], d["profile"]["care_style"], d["profile"]["schedule_hint"]), ("gentle", "nudge", ""))

    def test_onboard_first_wish_is_planned_with_xiaoguang(self):
        c, _ = self.member("onb_plan")
        hist = [{"role": "assistant", "content": "想早点睡，现在一般几点睡？"}, {"role": "user", "content": "总是刷手机到两点"}]
        self.fake.json_out = {"reply": "刷到两点，第二天肯定很难受吧。是停不下来，还是睡不着？", "plan": None}
        s, d = c.req("POST", "/api/onboard/plan", {"goal": "想早点睡", "history": hist, "about": {"persona": "lively", "nickname": "阿夏"}})
        self.assertEqual((s, d["plan"], d["round"]), (200, None, 1))
        self.assertIn("阿夏", self.fake.seen_json[-1][0]["content"])           # 刚在「你」里填的称呼带进了提示
        self.fake.json_out = {"reply": "我帮你拆了一下，看看哪些想放进计划。", "remember": ["你常刷手机到两点"], "why_goal": "白天上课犯困",
                              "plan": {"title": "早睡早起", "category": "body", "days": 30,
                                       "milestones": [{"title": "连续 7 天 12 点前睡着", "due_in_days": 21}],
                                       "habits": [{"title": "23:30 放下手机"}], "steps": [{"title": "今晚手机放书桌上"}, {"title": ""}]}}
        s, d = c.req("POST", "/api/onboard/plan", {"goal": "想早点睡", "history": hist, "finish": True})
        self.assertEqual(s, 200, d)
        self.assertEqual((d["plan"]["title"], d["plan"]["milestones"], d["plan"]["steps"], d["plan"]["due_in_days"]),
                         ("早睡早起", ["连续 7 天 12 点前睡着"], ["今晚手机放书桌上"], 21))
        # 「让小光改改」：上一版和用户的意见一起交给模型，这一轮一定给出新的一版
        rev = hist + [{"role": "assistant", "content": "我拆的是：愿望「早睡早起」，一个月；里程碑「连续 7 天 12 点前睡着」。"},
                      {"role": "user", "content": "我想 1 点前睡就行"}]
        self.fake.json_out = {"reply": "好，改成 1 点前。", "plan": {"title": "1 点前睡", "milestones": [{"title": "一周 5 晚 1 点前睡"}], "habits": [], "steps": [{"title": "今晚 0:30 放下手机"}]}}
        s, d = c.req("POST", "/api/onboard/plan", {"goal": "想早点睡", "history": rev, "revise": True})
        self.assertEqual((s, d["plan"]["title"]), (200, "1 点前睡"))
        prompt = self.fake.seen_json[-1]
        self.assertIn("提了意见", prompt[0]["content"])
        self.assertEqual(prompt[-1]["content"], "我想 1 点前睡就行")
        self.assertIn("连续 7 天 12 点前睡着", prompt[-2]["content"])
        self.fake.json_out = None                                                    # 模型不可用：也照样给出一条路
        s, d = c.req("POST", "/api/onboard/plan", {"goal": "想早点睡", "history": hist, "finish": True})
        self.assertTrue(d["plan"]["steps"] and d["plan"]["milestones"] and d["plan"]["habits"])
        self.assertEqual(c.req("POST", "/api/onboard/plan", {"goal": "", "history": hist})[0], 400)
        self.assertEqual(Client(self.port).req("POST", "/api/onboard/plan", {"goal": "想早点睡", "history": hist})[0], 401)
        wish = {**d["plan"], "milestones": d["plan"]["milestones"], "due_in_days": 21}
        s, d = c.req("POST", "/api/onboard", {"answers": {"wish": wish, "remember": ["你常刷手机到两点"], "intent_why": "白天上课犯困"}})
        self.assertEqual(s, 200, d)
        self.assertEqual(len(d["journey"]["wishes"]), 1)
        self.assertIn("你常刷手机到两点", [m["text"] for m in d["memories"]])

    def test_onboard_sets_up_the_first_wish(self):
        c, _ = self.member("onb_wish")
        wish = {"title": "早睡早起", "category": "body", "days": 90, "milestones": ["连续 7 天 12 点前睡"],
                "steps": ["今晚手机放到床外面", "定一个 23:30 的提醒", "   "], "habits": ["23:30 放下手机"]}
        s, d = c.req("POST", "/api/onboard", {"answers": {"nickname": "阿夏", "schedule_hint": "夜猫", "traits": ["想得多", "行动派"],
                                                          "boundaries": ["别说教"], "persona": "lively", "wish": wish}})
        self.assertEqual(s, 200, d)
        p = d["profile"]
        self.assertEqual((p["nickname"], p["intent_primary"], p["persona"]), ("阿夏", "早睡早起", "lively"))
        [w] = d["journey"]["wishes"]
        self.assertEqual((w["title"], w["category"]), ("早睡早起", "body"))
        self.assertEqual([m["title"] for m in w["milestones"]], ["连续 7 天 12 点前睡"])
        self.assertEqual([h["title"] for h in w["habits"]], ["23:30 放下手机"])
        self.assertEqual(sorted(x["title"] for x in d["steps"] if x["wish_id"] == w["id"]), ["今晚手机放到床外面", "定一个 23:30 的提醒"])
        self.assertIn("今晚手机放到床外面", d["messages"][-1]["content"])
        kinds = {m["kind"] for m in d["memories"]}
        self.assertTrue({"intent", "identity", "preference", "boundary"} <= kinds)

    def test_scene_waits_for_each_answer_then_writes(self):
        c, _ = self.onboarded("scene")
        s, d = c.req("POST", "/api/scene/start", {"scene": "gratitude"})
        self.assertEqual(s, 200)
        rid = d["run"]["id"]
        _, d1 = c.req("POST", "/api/scene/answer", {"run_id": rid, "text": "食堂的汤很好喝"})
        self.assertFalse(d1["done"])
        self.assertEqual(d1["step"]["index"], 1)
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual(boot["scene"]["id"], rid)      # resumable after reload
        c.req("POST", "/api/scene/answer", {"run_id": rid, "text": "同事帮我带了伞"})
        _, d3 = c.req("POST", "/api/scene/answer", {"run_id": rid, "text": "按时下班了"})
        self.assertTrue(d3["done"])
        types = sorted(w["type"] for w in d3["wrote"])
        self.assertEqual(types, ["memory"])            # 感恩只记进小光的记忆，不会自动变成瞬间
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertIn("感恩三件事：食堂的汤很好喝；同事帮我带了伞；按时下班了", [m["text"] for m in boot["memories"]])
        self.assertEqual((boot["records"], boot["journey"]["moments"]), ([], []))
        self.assertIsNone(boot["scene"])

    def test_topic_from_ideas_adds_prompt_for_a_while(self):
        from datetime import timedelta
        from core import acts, topics
        from core.util import iso, now
        c, uid = self.onboarded("topic")
        _, boot = c.req("GET", "/api/bootstrap")
        t = next(i for i in boot["ideas"] if i["id"] == "topic_manual")
        self.assertEqual((t["kind"], t["group"], t["topic"], t["scene"]), ("topic", "话题", "manual", ""))
        self.assertNotIn("topic_manual", acts.FEATURES)                     # 话题只在点子里，小光不推
        self.fake.turns = [[("text", "第 1 条……")], [("text", "嗯。")], [("text", "好。")]]
        s, _ = c.sse(t["send"], topic="manual")
        self.assertEqual(s, 200)
        sys_prompt = self.fake.seen[-1][0]["content"]
        self.assertIn("## 这段对话的话题：我的使用说明书", sys_prompt)
        self.assertIn("别说「TA」", sys_prompt)
        self.assertNotIn("start_scene", self.fake.seen_tools[-1])            # 话题里不打开别的练习
        self.assertEqual(c.req("GET", "/api/bootstrap")[1]["messages"][-2]["meta"].get("topic"), "manual")
        c.sse("没电的时候不想回消息")                                          # 接着聊：话题还在
        self.assertIn("我的使用说明书", self.fake.seen[-1][0]["content"])
        with Store(uid) as st:                                              # 半小时没再聊：话题结束
            cur = st.profile()["topic"]
            st.set_profile({"topic": {**cur, "at": iso(now() - timedelta(minutes=31))}})
        c.sse("今天天气不错")
        self.assertNotIn("这段对话的话题", self.fake.seen[-1][0]["content"])
        self.assertIn("start_scene", self.fake.seen_tools[-1])
        self.assertEqual(c.sse("随便", topic="nope")[0], 200)                 # 不认识的话题：当普通一句
        self.assertNotIn("这段对话的话题", self.fake.seen[-1][0]["content"])

    def test_removed_ideas_are_gone(self):
        c, uid = self.onboarded("removed")
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual([i["id"] for i in boot["ideas"]], ["seven_steps_lite", "relearn", "kickstart", "meditation", "gratitude",
                                                            "topic_blank_day", "topic_manual", "topic_parallel"])
        self.assertNotIn("clarify", [s["id"] for s in boot["scenes"]])
        self.assertEqual(c.req("POST", "/api/scene/start", {"scene": "clarify"})[0], 404)
        with Store(uid) as st:     # 上线前做到一半的「说清想要的」：再答就结束，不报错
            st.c.execute("INSERT INTO scene_run(id, scene, step, answers, status, created_at) VALUES('sc_old','clarify',1,'[\"x\"]','active','2026-11-01T10:00:00')")
        s, d = c.req("POST", "/api/scene/answer", {"run_id": "sc_old", "text": "y"})
        self.assertEqual((s, d.get("error")), (404, "这个练习已经下架了"))
        with Store(uid) as st:
            self.assertEqual((st.get_scene("sc_old")["status"], st.get_scene("sc_old")["answers"]), ("abandoned", []))

    def test_meditation_journey_keeps_nothing_unless_asked(self):
        c, uid = self.onboarded("meditate")
        _, boot = c.req("GET", "/api/bootstrap")
        med = next(s for s in boot["scenes"] if s["id"] == "meditation")
        self.assertEqual((med["title"], med["music"]), ("冥想体验：遇见更好的自己", "/audio/meditation.mp3"))
        n_msgs, n_recs, n_mems = len(boot["messages"]), len(boot["records"]), len(boot["memories"])
        answers = ["准备好了", "在阳光下，享受户外的空气", "更平静，不再总是担心", "有人理解我、支持我", "自信", "我准备好了"]
        rid, outs = self._scene(c, "meditation", answers)
        first = outs[0]["step"]
        self.assertEqual((first["cta"], first["breath"], first["calm"], first["optional"]), ("准备好了", True, True, False))
        self.assertTrue(outs[1]["step"]["auto"])                              # 选了就往下走
        self.assertEqual(outs[3]["reply"], "那是你期待成为的样子。\n我们一起再看看，那时的你过着怎样的生活。")
        self.assertEqual(outs[5]["reply"], "你选择了自信。\n现在，试着在心里对自己说：\n我正在慢慢相信自己。")
        self.assertTrue(outs[5]["glow"])
        done = outs[-1]
        self.assertEqual(done["review"]["kind"], "feel")
        self.assertEqual([x["key"] for x in done["review"]["choices"]], ["write", "talk", "end"])
        self.assertEqual(done["xp"]["amount"], 12)
        _, boot = c.req("GET", "/api/bootstrap")                             # 冥想时选的什么都没存
        self.assertEqual((len(boot["messages"]), len(boot["records"]), len(boot["memories"])), (n_msgs, n_recs, n_mems))
        # 记下感受：小光记住（不会自动变成瞬间）
        self.assertEqual(c.req("POST", "/api/scene/save", {"run_id": rid, "extra": "  "})[0], 400)
        s, out = c.req("POST", "/api/scene/save", {"run_id": rid, "extra": "肩膀松下来了，想多晒太阳"})
        self.assertEqual(s, 200, out)
        self.assertIn("冥想后的感受：肩膀松下来了，想多晒太阳", [m["text"] for m in out["state"]["memories"]])
        self.assertEqual(out["state"]["journey"]["moments"], [])
        self.assertEqual(len(out["state"]["messages"]), n_msgs)
        # 和你聊聊：小光带着刚才的画面先开口
        rid, outs = self._scene(c, "meditation", answers)
        s, out = c.req("POST", "/api/scene/save", {"run_id": rid, "talk": True})
        self.assertEqual(s, 200, out)
        self.assertEqual(out["reply"], "刚才那几分钟，你在阳光下的户外，看到了更平静的自己，那束光带来了自信。想从哪儿聊起都行。")
        self.assertEqual(out["state"]["messages"][-1]["content"], out["reply"])
        # 先不记录：什么都不留
        rid, outs = self._scene(c, "meditation", answers)
        c.req("POST", "/api/scene/discard", {"run_id": rid})
        with Store(uid) as st:
            self.assertEqual(st.get_scene(rid)["answers"], [])

    # ---- 两分钟启动 -------------------------------------------------------------
    def _kick(self, c, action, **body):
        s, d = c.req("POST", "/api/kick", {"action": action, **body})
        self.assertEqual(s, 200, d)
        return d

    def test_kickstart_route_adjust_and_forget_by_default(self):
        c, uid = self.onboarded("kick_low")
        self.fake.json_out = {"say": "被子先掀开一角就行。", "cheer": "起来了，今天已经赢了一半。", "steps": [
            {"title": "先坐起来", "tip": "慢慢撑起身体，靠在床头。", "minutes": 1},
            {"title": "双脚踩地", "tip": "把脚放到地上，感受地板的凉。", "minutes": 1},
            {"title": "喝一口温水", "tip": "拿起旁边的水，小口喝下。", "minutes": 1}]}
        run = self._kick(c, "start", task="想起床", mode="low")["run"]
        self.assertEqual((run["mode"], run["total"], run["cur"], run["questions"]), ("low", 3, 0, []))
        sent = self.fake.seen_json[-1]
        self.assertIn("两分钟启动", sent[0]["content"])                          # 独立的提示词，不是聊天的人设
        self.assertIn("想起床", sent[1]["content"])
        self.assertIn("能量很低", sent[1]["content"])
        run = self._kick(c, "done", run_id=run["id"])["run"]
        run = self._kick(c, "done", run_id=run["id"])["run"]
        self.assertEqual((run["cur"], run["done"]), (2, 2))
        # 调整路线：只改现在这一步和后面的，做完的不动
        self.fake.json_out = {"say": "没有温水也没关系。", "steps": [
            {"title": "倒杯凉白开", "tip": "去厨房倒小半杯。", "minutes": 2}, {"title": "做三次深呼吸", "tip": "吸四拍，呼四拍。", "minutes": 1}]}
        out = self._kick(c, "adjust", run_id=run["id"], text="没有温水")
        run = out["run"]
        self.assertEqual(out["say"], "没有温水也没关系。")
        self.assertEqual([s["title"] for s in run["route"]], ["先坐起来", "双脚踩地", "倒杯凉白开", "做三次深呼吸"])
        self.assertEqual([s["state"] for s in run["route"]][:2], ["done", "done"])
        prompt = self.fake.seen_json[-1][1]["content"]
        self.assertIn("✓ 先坐起来", prompt)
        self.assertIn("→ 喝一口温水", prompt)
        self.assertIn("没有温水", prompt)
        # 遇到困难：第二轮还记得第一轮说过的话
        self.fake.json_out = {"say": "那就只拿起杯子。", "steps": [{"title": "只拿起杯子", "tip": "拿起来就算。", "minutes": 1}]}
        run = self._kick(c, "stuck", run_id=run["id"], text="不想动")["run"]
        self.assertIn("「没有温水」", self.fake.seen_json[-1][1]["content"])
        self.assertEqual([x["text"] for x in run["log"]], ["没有温水", "不想动"])
        out = self._kick(c, "done", run_id=run["id"])
        self.assertTrue(out["run"]["finished"])
        self.assertEqual(out["xp"]["amount"], 12)                                 # 走完一条路线，算一次练习
        # 结束时没勾「记住」：不写记忆，这一次的细节也清掉
        out = self._kick(c, "finish", run_id=run["id"], remember=False)
        self.assertFalse(out["saved"])
        self.assertEqual(out["state"]["kick_memories"], [])
        with Store(uid) as st:
            row = dict(st.c.execute("SELECT * FROM kick_run WHERE id=?", (run["id"],)).fetchone())
        self.assertEqual((row["status"], row["log"], row["answers"]), ("closed", "[]", "{}"))
        self.assertNotIn("倒杯凉白开", row["route"])
        _, home = c.req("GET", "/api/kick")
        self.assertIsNone(home["active"])

    def test_kickstart_precise_remember_and_recall(self):
        c, uid = self.onboarded("kick_precise")
        self.fake.json_out = {"now": ["还没开始", "写了个开头", "大纲有了", "资料还没找"], "want": ["写完第一段", "列个大纲", "找两份资料", "定个标题"],
                              "block": ["怕写不好", "不知道写什么", "太累了", "总刷手机"]}
        run = self._kick(c, "start", task="开始写周报", mode="precise")["run"]
        self.assertEqual(run["total"], 0)
        self.assertEqual([q["q"] for q in run["questions"]], ["你现在做到哪了？", "你现在最想推进的是什么？", "你现在最大的阻碍是什么？"])
        self.assertEqual(run["questions"][2]["options"][0], "怕写不好")
        self.fake.json_out = {"say": "从你写了的那个开头接着来。", "steps": [
            {"title": "打开周报文档", "tip": "就打开，先不写。", "minutes": 1}, {"title": "写一句最简单的", "tip": "比如「本周做了三件事」。", "minutes": 2},
            {"title": "列三个关键词", "tip": "", "minutes": 1}]}
        run = self._kick(c, "answer", run_id=run["id"], answers={"now": "写了个开头", "want": "写完第一段", "block": "怕写不好"})["run"]
        self.assertIn("怕写不好", self.fake.seen_json[-1][1]["content"])
        self.assertIn("最大阻碍", self.fake.seen_json[-1][1]["content"])
        run = self._kick(c, "done", run_id=run["id"])["run"]
        run = self._kick(c, "skip", run_id=run["id"])["run"]                    # 先跳过这一步：不用问模型
        self.assertEqual(run["route"][1]["state"], "skipped")
        run = self._kick(c, "done", run_id=run["id"])["run"]
        self.assertTrue(run["finished"])
        self.fake.json_out = {"say": "接着来。", "steps": [{"title": "再写三句", "tip": "", "minutes": 3}]}
        run = self._kick(c, "more", run_id=run["id"])["run"]                    # 继续做这件事：同一次会话接着加
        self.assertEqual((run["total"], run["cur"], run["finished"]), (4, 3, False))
        self.assertIn("✓ 打开周报文档", self.fake.seen_json[-1][1]["content"])
        run = self._kick(c, "done", run_id=run["id"])["run"]
        out = self._kick(c, "finish", run_id=run["id"], remember=True)
        self.assertTrue(out["saved"])
        [k] = out["state"]["kick_memories"]
        for part in ("开始写周报（拆更准）", "最大的阻碍：怕写不好", "一开始的路线：打开周报文档 → 写一句最简单的 → 列三个关键词",
                     "跳过了「写一句最简单的」", "实际做了：打开周报文档、列三个关键词、再写三句（3/4 步）"):
            self.assertIn(part, k["text"])
        # 夜里整理能读到它（连同 TA 的原话），聊天里按需查
        from core import agent, digest
        with Store(uid) as st:
            mat = digest.material(st, k["day"])
            self.assertEqual(len(mat["kicks"]), 1)
            self.assertIn("怕写不好", mat["user_lines"])
            hit = agent.run_tool(st, "kick_history", {"query": "周报"})
            miss = agent.run_tool(st, "kick_history", {"query": "练琴"})
        self.assertEqual(len(hit["entries"]), 1)
        self.assertEqual((miss["entries"], bool(miss["note"])), ([], True))
        # 我的空间里能删
        out = self._kick(c, "forget", id=k["id"])
        self.assertEqual(out["state"]["kick_memories"], [])

    def test_kickstart_from_plan_step_and_model_failure(self):
        c, uid = self.onboarded("kick_fail")
        _, d = c.req("POST", "/api/step", {"action": "add", "title": "整理桌面"})
        step = next(s for s in d["steps"] if s["title"] == "整理桌面")
        self.fake.json_out = None                                                  # 模型不在：给一条最朴素的路，别卡住
        out = self._kick(c, "start", task="整理桌面", step_id=step["id"])
        run = out["run"]
        self.assertFalse(out["by_model"])
        self.assertEqual(run["total"], 3)
        self.assertEqual(run["ctx"]["step"], "整理桌面")
        self.assertIn("来自蜕变计划", self.fake.seen_json[-1][1]["content"])
        s, d = c.req("POST", "/api/kick", {"action": "adjust", "run_id": run["id"], "text": "太难了"})
        self.assertEqual((s, d["error"]), (400, "刚才没想好，换个说法再试一次？"))
        _, home = c.req("GET", "/api/kick")
        self.assertEqual(home["active"]["id"], run["id"])                         # 刷新页面也能接着做
        self._kick(c, "close", run_id=run["id"])
        _, home = c.req("GET", "/api/kick")
        self.assertIsNone(home["active"])
        self.assertEqual(c.req("POST", "/api/kick", {"action": "done", "run_id": run["id"]})[0], 404)
        self.assertEqual(c.req("POST", "/api/kick", {"action": "start", "task": "  "})[0], 400)

    def test_kickstart_guess_fix_found_and_review(self):
        c, uid = self.onboarded("kick_guess")
        with Store(uid) as st:
            st.c.execute("INSERT INTO wish(id, title, category, started, archived, sort, created_at) VALUES('w_dress', '变得更会打扮', 'other', '2026-11-01', 0, 0, '2026-11-01T00:00:00+08:00')")
            st.set_profile({"current_wish": "w_dress"})
        # 先写理解、再拆：理解存下来（页面上不显示，记忆里有）
        self.fake.json_out = {"guess": "在衣柜里挑一套衣服换上", "say": "先看看衣柜。", "cheer": "搭出来了。", "steps": [
            {"title": "打开衣柜", "tip": "", "minutes": 1}, {"title": "挑一件上衣", "tip": "", "minutes": 2}]}
        run = self._kick(c, "start", task="学穿搭")["run"]
        self.assertEqual(run["guess"], "在衣柜里挑一套衣服换上")
        sent = self.fake.seen_json[-1]
        self.assertIn("先理解这件事", sent[0]["content"])
        self.assertIn('"guess"', sent[1]["content"])
        self.assertIn("「变得更会打扮」（现在主要在做）", sent[1]["content"])        # 愿望帮小光猜意思
        # 在「调整路线」里说理解错了：理解换掉，路线从现在这一步重排
        self.fake.json_out = {"guess": "在小红书上看穿搭，照着搭一套", "say": "好，那就上网学。", "found": "学穿搭你想先看别人怎么搭", "steps": [
            {"title": "打开小红书", "tip": "搜「秋冬穿搭」", "minutes": 1}, {"title": "收藏一套", "tip": "", "minutes": 2},
            {"title": "照着配一套", "tip": "", "minutes": 3}]}
        run = self._kick(c, "adjust", run_id=run["id"], text="我想在网上学")["run"]
        prompt = self.fake.seen_json[-1][1]["content"]
        self.assertIn("你理解错了", prompt)
        self.assertIn("你对这件事的理解：在衣柜里挑一套衣服换上", prompt)
        self.assertEqual((run["guess"], run["total"], run["route"][0]["title"]), ("在小红书上看穿搭，照着搭一套", 3, "打开小红书"))
        self.assertEqual([(x["kind"], x["step"], x["found"]) for x in run["log"]], [("adjust", 0, "学穿搭你想先看别人怎么搭")])
        # 每一步实际用了多久（从这一步出现算起）
        from datetime import timedelta
        from core.util import iso, now
        with Store(uid) as st:
            st.c.execute("UPDATE kick_run SET mark=? WHERE id=?", (iso(now() - timedelta(seconds=150)), run["id"]))
        run = self._kick(c, "done", run_id=run["id"])["run"]
        self.assertTrue(140 <= run["route"][0]["sec"] <= 160)
        self.fake.json_out = {"say": "那就先存一套。", "found": "", "steps": [{"title": "随手存一套", "tip": "", "minutes": 1}]}
        run = self._kick(c, "stuck", run_id=run["id"], text="看花眼了")["run"]
        self.assertEqual([(x["kind"], x["step"]) for x in run["log"]], [("adjust", 0), ("stuck", 1)])
        run = self._kick(c, "done", run_id=run["id"])["run"]
        self.assertTrue(run["finished"])
        self.assertGreaterEqual(run["secs"], 140)
        self.fake.json_out = {"say": "接着来。", "steps": [{"title": "换上拍一张", "tip": "", "minutes": 2}]}
        run = self._kick(c, "more", run_id=run["id"])["run"]
        self.assertEqual(run["log"][-1]["kind"], "more")
        self.assertEqual(run["log"][-1]["step"], 2)                               # 路线回顾里「接着又做了」插在这一步前面
        self._kick(c, "done", run_id=run["id"])
        out = self._kick(c, "finish", run_id=run["id"], remember=True)
        [k] = out["state"]["kick_memories"]
        for part in ("小光的理解：在小红书上看穿搭，照着搭一套", "调整路线：TA 说「我想在网上学」", "小光的发现：学穿搭TA想先看别人怎么搭",
                     "用了约 3 分钟"):
            self.assertIn(part, k["text"])

    def test_kickstart_fallback_route_is_generic(self):
        c, _ = self.onboarded("kick_generic")
        self.fake.json_out = None
        out = self._kick(c, "start", task="学穿搭", mode="low")
        run = out["run"]
        self.assertEqual(run["guess"], "")
        self.assertIn("没连上", run["say"])                                        # 说实话：这是通用的路，不是猜出来的
        self.assertEqual([s["title"] for s in run["route"]], ["先让身体动一下", "先把要用的打开", "只做最小的一下", "停一下，看看感觉"])
        self.assertNotIn("学穿搭", "".join(s["tip"] for s in run["route"]))

    def test_audio_supports_range_requests(self):
        import pathlib
        from core.util import PUBLIC
        f = pathlib.Path(PUBLIC) / "audio" / "_range_test.mp3"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(bytes(range(32, 127)) * 10)     # 950 字节，测试客户端按 UTF-8 读，所以只放可见字符
        try:
            c = Client(self.port)
            s, body, _ = c.req("GET", "/audio/_range_test.mp3", headers={"Range": "bytes=10-19"}, raw=True)
            self.assertEqual((s, body), (206, bytes(range(42, 52)).decode()))
            s, body, _ = c.req("GET", "/audio/_range_test.mp3", headers={"Range": "bytes=5000-"}, raw=True)
            self.assertEqual(s, 416)
            s, body, _ = c.req("GET", "/audio/_range_test.mp3", raw=True)
            self.assertEqual((s, len(body)), (200, 950))
        finally:
            f.unlink()

    def test_every_scene_writes_something(self):
        from core import scenes
        c, _ = self.onboarded("scene_all")
        for sid, sc in scenes.SCENES.items():
            if sc.get("flow"):        # 许个愿、让愿望落地走 /api/flow，下面单独测
                self.assertEqual(c.req("POST", "/api/scene/start", {"scene": sid})[0], 404)
                continue
            _, d = c.req("POST", "/api/scene/start", {"scene": sid})
            out = None
            for i in range(len(sc["steps"])):
                _, out = c.req("POST", "/api/scene/answer", {"run_id": d["run"]["id"], "text": f"回答{i}"})
            self.assertTrue(out["done"], sid)
            if sc.get("review"):      # 先确认再存：答完什么都没写，勾选后保存才写
                self.assertNotIn("wrote", out, sid)
                if out["review"].get("kind") == "feel":     # 冥想：写下感受再保存
                    body = {"run_id": d["run"]["id"], "extra": "很放松"}
                else:
                    body = {"run_id": d["run"]["id"], "items": [{"key": it["key"], "text": it["text"]}
                                                               for it in out["review"]["items"] if not it.get("off")]}
                s, out = c.req("POST", "/api/scene/save", body)
                self.assertEqual(s, 200, out)
            self.assertGreaterEqual(len(out["wrote"]), 1, sid)

    def _scene(self, c, sid, answers):
        """走完一个场景，返回 (run_id, 每一步的返回)。"""
        _, d = c.req("POST", "/api/scene/start", {"scene": sid})
        rid, outs = d["run"]["id"], [d]
        for a in answers:
            s, out = c.req("POST", "/api/scene/answer", {"run_id": rid, "text": a})
            self.assertEqual(s, 200, out)
            outs.append(out)
        return rid, outs

    # ---- 显化你的愿望 / 调整现有计划（core/flows.py）--------------------------------------
    def _flow(self, c, sid, wish_id=""):
        s, d = c.req("POST", "/api/flow", {"action": "start", "scene": sid, "wish_id": wish_id})
        self.assertEqual(s, 200, d)
        return d["run"]["id"], d["ctx"]

    MANIFEST = {"pick": "new", "want": "换一份喜欢的工作", "spec": "明年春天前进一家做设计的小公司", "feel": "平静",
                "vision": "我坐在窗边画图，心里很安静。", "doubt": "已经太晚了", "aff": "我现在开始也来得及",
                "act": "整理三份作品发给老同学", "test": "想将就一下", "plan": "下次它出现时，我会写下为什么想换",
                "thanks": "我必须早起", "thanks_line": "我有幸能早起看见清晨", "envy": "很羡慕", "learn": "看他怎么投简历",
                "trust": "很急，想快点看到", "letgo": "我先做好今天这一件"}

    def test_manifest_new_wish_walks_seven_steps(self):
        c, uid = self.onboarded("manifest_new")
        _, boot = c.req("GET", "/api/bootstrap")
        before = (len(boot["journey"]["wishes"]), len(boot["messages"]), len(boot["steps"]))
        rid, ctx = self._flow(c, "seven_steps_lite")
        self.assertEqual(ctx["wishes"][0]["title"], boot["journey"]["wishes"][0]["title"])
        self.assertEqual(list(ctx["doubts"]), ["worth", "able", "late", "others", "none"])
        # 每一步调一次模型，接着 TA 的回答说
        self.fake.json_out = {"say": "我们把它说细一点。", "opts": ["明年春天前进一家做设计的小公司", "通勤半小时内的设计岗"]}
        s, out = c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "spec", "answers": {"pick": "new", "want": "换一份喜欢的工作"}})
        self.assertEqual((s, out["opts"][0]), (200, "明年春天前进一家做设计的小公司"))
        self.assertIn("TA 说想要：换一份喜欢的工作", self.fake.seen_json[-1][1]["content"])
        self.assertIn("清晰你的愿景", self.fake.seen_json[-1][0]["content"])
        self.fake.json_out = {"say": "这个声音很常见。", "opts": ["我现在开始也来得及", "我的节奏我来定"]}
        _, out = c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "doubt", "answers": self.MANIFEST})
        self.assertIn("TA 心里冒出来的声音：已经太晚了", self.fake.seen_json[-1][1]["content"])
        self.fake.json_out = None                                             # 模型不在：这一步也能接着走
        _, out = c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "trust", "answers": self.MANIFEST})
        self.assertEqual(len(out["opts"]), 2)
        _, out = c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "thanks", "answers": {**self.MANIFEST, "thanks": "我必须上班"}})
        self.assertEqual(out["line"], "我有幸能上班")
        self.assertEqual(c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "nope", "answers": self.MANIFEST})[0], 400)
        # 走完：小纸条 + 显化卡，什么都还没存
        self.fake.json_out = {"letter": "阿青，那句「已经太晚了」冒出来时，就对自己说现在开始也来得及。今天先整理三份作品。", "love": "记得对自己温柔一点。"}
        s, out = c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": self.MANIFEST})
        self.assertEqual(s, 200, out)
        self.assertTrue(out["letter"].startswith("阿青"))
        self.assertEqual(out["card"]["vow"], "记得对自己温柔一点。")
        self.assertEqual([x["em"] for x in out["card"]["lines"]], ["那一刻", "对自己说", "今天去做", "下次它出现", "我有幸能", "可以学的", "交给时间"])
        self.assertEqual(out["card"]["lines"][3]["text"], "我会写下为什么想换")
        self.assertEqual([(k["key"], k.get("on", True)) for k in out["keeps"]],
                         [("wish", True), ("aff", True), ("act", True), ("thanks", True), ("mind", False), ("remind", False)])
        self.assertEqual(out["xp"]["amount"], 12)
        sent = self.fake.seen_json[-1][1]["content"]
        for part in ("已经太晚了", "我现在开始也来得及", "整理三份作品发给老同学"):
            self.assertIn(part, sent)
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual((len(boot["journey"]["wishes"]), len(boot["messages"]), len(boot["steps"])), before)
        calls = len(self.fake.seen_json)
        s, again = c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": self.MANIFEST})   # 结尾上一步又原样答完
        self.assertEqual((s, len(self.fake.seen_json), again["letter"]), (200, calls, out["letter"]))
        self.assertNotIn("xp", again)
        s, out = c.req("POST", "/api/flow", {"action": "save", "run_id": rid, "keys": ["wish", "aff", "act", "thanks", "remind"]})
        self.assertEqual(s, 200, out)
        st_ = out["state"]
        w = next(x for x in st_["journey"]["wishes"] if x["title"] == "明年春天前进一家做设计的小公司")
        self.assertEqual(w["vision_text"], "我坐在窗边画图，心里很安静。")
        self.assertEqual(st_["journey"]["moments"], [])                 # 走完流程不会自动加瞬间
        step = next(x for x in st_["steps"] if x["title"] == "整理三份作品发给老同学")
        self.assertEqual((step["wish_id"], out["step"]["id"]), (w["id"], step["id"]))
        self.assertIn(("念一遍：我现在开始也来得及", "08:00", "daily"), [(t["title"], t["time"], t["repeat"]) for t in st_["tasks"]])
        mems = [m["text"] for m in st_["memories"] if m["source"] == "scene:seven_steps_lite"]
        self.assertTrue(any("我现在开始也来得及" in t for t in mems) and any("我有幸能早起看见清晨" in t for t in mems), mems)   # 肯定语、感恩让小光记着
        self.assertFalse(any("怀疑" in t or "考验" in t for t in mems))      # 怀疑和考验没勾：不记
        self.assertEqual(st_["messages"][-1]["content"], out["reply"])
        self.assertEqual(c.req("POST", "/api/flow", {"action": "save", "run_id": rid, "keys": ["wish"]})[0], 400)   # 同一次不能存两遍

    def test_manifest_existing_wish_starts_at_step_two(self):
        c, uid = self.onboarded("manifest_old")
        _, boot = c.req("GET", "/api/bootstrap")
        w = boot["journey"]["wishes"][0]
        rid, ctx = self._flow(c, "seven_steps_lite", w["id"])
        self.assertEqual(ctx["wishes"][0]["vision"], w["vision_text"])
        a = {**self.MANIFEST, "pick": w["id"], "want": "", "spec": "", "vision": "随便写的不算"}
        self.fake.json_out = {"letter": "你已经在路上了。", "love": "好好睡一觉。"}
        s, out = c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": a})
        self.assertEqual(s, 200, out)
        self.assertEqual((out["card"]["title"], out["card"]["lines"][0]["text"]), (w["title"], w["vision_text"]))   # 那一刻用当初写下的样子
        self.assertEqual(out["intro"], "这是你今天走过的六步，收好它：")
        self.assertNotIn("wish", [k["key"] for k in out["keeps"]])
        s, out = c.req("POST", "/api/flow", {"action": "save", "run_id": rid, "keys": ["aff", "mind"]})
        self.assertEqual(s, 200, out)
        self.assertFalse(any(m["wish_id"] == w["id"] and m["source"] == "scene" for m in out["state"]["journey"]["moments"]))
        mems = [m["text"] for m in out["state"]["memories"] if m["source"] == "scene:seven_steps_lite"]
        self.assertTrue(any("我现在开始也来得及" in t and w["title"] in t for t in mems), mems)   # 肯定语让小光记着，带上是哪个愿望
        self.assertTrue(any("已经太晚了" in t for t in mems))
        self.assertEqual(len(out["state"]["journey"]["wishes"]), len(boot["journey"]["wishes"]))
        rid, _ = self._flow(c, "seven_steps_lite")
        self.assertEqual(c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": {"pick": "w_nope"}})[0], 400)

    def test_adjust_plan_applies_only_checked_and_revises(self):
        from datetime import date, timedelta
        from core import journey
        from core.util import day_key
        c, uid = self.onboarded("adjust")
        with Store(uid) as st:
            w = journey.current(st)
            h1 = journey.add_habit(st, w["id"], "背单词", "daily")
            h2 = journey.add_habit(st, w["id"], "跟读一段对话", "weekly", 3)
            stp = st.add_step("约 Mia 练口语", wish_id=w["id"])
            due = (date.today() + timedelta(days=10)).isoformat()
            ms = journey.add_milestone(st, w["id"], "三分钟自我介绍", due)
        rid, ctx = self._flow(c, "relearn")
        me = next(x for x in ctx["wishes"] if x["id"] == w["id"])
        self.assertIn({"kind": "habit", "title": "背单词", "hint": "习惯 · 每天 · 本周 0/7", "prog": 0}, me["items"])
        self.assertIn("三分钟自我介绍", [i["title"] for i in me["items"]])
        self.fake.json_out = {"see": "你最近很满，先把每件事放轻。", "changes": [
            {"kind": "habit_small", "target": "背单词", "to": "每天背 5 个", "why": "两分钟做得完"},
            {"kind": "habit_freq", "target": "背单词", "to": "每周 3 次", "why": "同一项第二条，不要"},
            {"kind": "habit_freq", "target": "跟读", "to": "每周 1 次", "why": "先留一次"},
            {"kind": "habit_pause", "target": "约 Mia 练口语", "to": "", "why": "小步不能用习惯的改法"},
            {"kind": "step_move", "target": "约 Mia 练口语", "to": "明天", "why": "换个日子"},
            {"kind": "ms_delay", "target": "三分钟自我介绍", "to": "推后 7 天", "why": "给忙碌留余量"},
            {"kind": "habit_small", "target": "不存在的习惯", "to": "x", "why": "对不上"}]}
        ans = {"state": "busy", "energy": "seed", "feel": "full", "feel_label": "太满了"}
        s, out = c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": ans})
        self.assertEqual(s, 200, out)
        self.assertEqual(out["say"], "你最近很满，先把每件事放轻。")
        self.assertEqual([(x["kind"], x["target"], x["to"]) for x in out["changes"]], [
            ("habit_small", "背单词", "每天背 5 个"), ("habit_freq", "跟读一段对话", "每周 1 次"),
            ("step_move", "约 Mia 练口语", "明天"), ("ms_delay", "三分钟自我介绍", "推后 7 天")])
        self.assertEqual(out["keeps"][-1]["key"], "remember")
        sent = self.fake.seen_json[-1][1]["content"]
        for part in ("忙忙碌碌（事情一件接一件）", "一点点就好", "习惯「背单词」：每天，本周做到 0/7", "小步「约 Mia 练口语」", "里程碑「三分钟自我介绍」：还有 10 天"):
            self.assertIn(part, sent)
        # 说一句哪里不对：带着上一版方案和意见重新调
        self.fake.json_out = {"see": "背单词按你的来，别的放轻。", "changes": [
            {"kind": "habit_freq", "target": "跟读一段对话", "to": "每周 1 次", "why": "先留一次"},
            {"kind": "step_move", "target": "约 Mia 练口语", "to": "明天", "why": "换个日子"},
            {"kind": "ms_delay", "target": "三分钟自我介绍", "to": "推后 7 天", "why": "留余量"}]}
        s, out = c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "revise", "text": "背单词我不想减", "answers": ans})
        self.assertEqual((s, len(out["changes"])), (200, 3))
        sent = self.fake.seen_json[-1][1]["content"]
        self.assertIn("TA 的意见：背单词我不想减", sent)
        self.assertIn("上一版方案", sent)
        with Store(uid) as st:
            self.assertEqual(journey.habits(st, w["id"])[0]["title"], "背单词")       # 没点一键调整之前什么都不改
        s, out = c.req("POST", "/api/flow", {"action": "save", "run_id": rid, "keys": ["c0", "c1", "c2", "remember"]})
        self.assertEqual(s, 200, out)
        self.assertEqual(len(out["done"]), 3)
        with Store(uid) as st:
            hs = {h["id"]: h for h in journey.habits(st, w["id"])}
            self.assertEqual((hs[h1["id"]]["title"], hs[h2["id"]]["per_week"]), ("背单词", 1))
            # 挪到明天 = 在日历上安排到明天
            self.assertEqual(st.c.execute("SELECT scheduled_day FROM step WHERE id=?", (stp["id"],)).fetchone()[0],
                             (date.fromisoformat(day_key()) + timedelta(days=1)).isoformat())
            self.assertEqual(st.c.execute("SELECT due_day FROM milestone WHERE id=?", (ms["id"],)).fetchone()[0],
                             (date.today() + timedelta(days=17)).isoformat())
        mem = next(m for m in out["state"]["memories"] if "最近的状态：" in m["text"])
        self.assertEqual((mem["source"], mem["kind"]), ("scene:relearn", "event"))
        self.assertEqual(out["state"]["messages"][-1]["content"], out["reply"])
        # 再来一次：改小、这周先停、加一小步；只勾一条就只改一条
        rid, _ = self._flow(c, "relearn")
        self.fake.json_out = {"see": "顺的时候多走一步。", "changes": [
            {"kind": "habit_small", "target": "背单词", "to": "每天背 5 个", "why": "x"},
            {"kind": "habit_pause", "target": "跟读一段对话", "to": "这周先停", "why": "x"},
            {"kind": "step_add", "target": w["title"], "to": "用英语点一次咖啡", "why": "x"}]}
        _, out = c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": {"state": "steady", "energy": "more", "feel": "smooth"}})
        self.assertEqual([x["kind"] for x in out["changes"]], ["habit_small", "habit_pause", "step_add"])
        s, out = c.req("POST", "/api/flow", {"action": "save", "run_id": rid, "keys": ["c1", "c2"]})
        self.assertEqual(s, 200, out)
        hb = next(x for x in out["state"]["journey"]["wishes"] if x["id"] == w["id"])["habits"]
        self.assertTrue(next(x for x in hb if x["id"] == h2["id"])["skipped"])
        self.assertEqual(next(x for x in hb if x["id"] == h1["id"])["title"], "背单词")
        self.assertIn("用英语点一次咖啡", [x["title"] for x in out["state"]["steps"]])

    def test_adjust_plan_empty_and_cancel_keep_nothing(self):
        from core import journey
        c, uid = self.member("adjust_empty")                                 # 还没有愿望
        rid, ctx = self._flow(c, "relearn")
        self.assertEqual(ctx["wishes"], [])
        c.req("POST", "/api/scene/cancel")
        with Store(uid) as st:
            w = journey.add_wish(st, "睡好一点", "body")
        rid, ctx = self._flow(c, "relearn")
        self.assertEqual(ctx["wishes"][0]["items"], [])
        self.assertEqual(c.req("POST", "/api/flow", {"action": "step", "run_id": rid, "kind": "revise", "text": "x", "answers": {}})[0], 400)
        self.fake.json_out = {"see": "计划还是空的，先放两件很小的事。", "changes": [
            {"kind": "step_add", "target": "睡好", "to": "今晚十一点关灯", "why": "先开个头"}]}
        s, out = c.req("POST", "/api/flow", {"action": "finish", "run_id": rid, "answers": {"state": "custom", "state_label": "期中周好累"}})
        self.assertEqual((s, out["changes"][0]["target"]), (200, "睡好一点"))
        self.assertIn("最近的状态：期中周好累", self.fake.seen_json[-1][1]["content"])       # 自己写的照原话发给模型
        self.assertEqual(c.req("POST", "/api/scene/discard", {"run_id": rid})[0], 200)   # 结尾不存
        with Store(uid) as st:
            self.assertEqual(st.get_scene(rid)["answers"], [])
        self.assertEqual(c.req("POST", "/api/flow", {"action": "save", "run_id": rid, "keys": ["c0"]})[0], 400)
        _, boot = c.req("GET", "/api/bootstrap")
        self.assertEqual(boot["steps"], [])
        self.assertEqual(c.req("POST", "/api/flow", {"action": "start", "scene": "gratitude"})[0], 404)
        self.assertEqual(c.req("POST", "/api/flow", {"action": "nope"})[0], 400)

    def test_companion_prefs_editable_in_settings(self):
        c, _ = self.onboarded("prefs")
        s, d = c.req("POST", "/api/profile", {"chat_style": "给你一些鼓励和信心", "care_style": "analyze", "energy_time": "晚上"})
        self.assertEqual(s, 200, d)
        self.assertEqual((d["prefs"]["chat_style"], d["prefs"]["care_style"], d["prefs"]["energy_time"]),
                         ("给你一些鼓励和信心", "analyze", "晚上"))
        self.assertIn("多听你说，不急着给建议", d["prefs"]["options"]["chat_style"])
        self.assertEqual(sorted(d["prefs"]["options"]), ["chat_style", "energy_time"])
        _, d = c.req("POST", "/api/profile", {"care_style": "", "energy_time": ""})   # 再点一下就是不设
        self.assertEqual((d["prefs"]["care_style"], d["prefs"]["energy_time"]), ("", ""))

    def test_lazy_day_never_resets_progress(self):
        c, _ = self.onboarded("lazy")
        c.req("POST", "/api/moment", {"action": "add", "text": "早睡了"})
        _, before = c.req("GET", "/api/bootstrap")
        c.req("POST", "/api/record", {"type": "rest", "text": "今天想休息"})
        _, after = c.req("GET", "/api/bootstrap")
        self.assertEqual(after["counts"]["moments"], before["counts"]["moments"])
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
        # 金币：小步 10 + 第一份建材 40 + 每日任务「完成 1 个小步」10；经验：小步 10 + 每日任务 5
        self.assertEqual((d2["xp"]["coin_event"], d2["xp"]["first_gift"], d2["xp"]["coins"]), (10, 40, 60))
        self.assertEqual((d2["xp"]["amount"], d2["xp"]["amount_total"]), (10, 15))
        self.assertEqual(d2["growth"]["coins"], 60)
        self.assertGreaterEqual(d2["growth"]["coins"], d2["town"]["catalog"][0]["price"])   # 够盖第一栋小木屋

    def test_step_schedule_and_lazy_day_moves_planned_steps(self):
        from datetime import date, timedelta
        c, _ = self.member("plan_cal")
        _, d = c.req("POST", "/api/wish", {"action": "add", "title": "规律健身", "category": "body"})
        wid = d["journey"]["wishes"][0]["id"]
        today = d["journey"]["today"]
        day = lambda n: (date.fromisoformat(today) + timedelta(days=n)).isoformat()
        # 新加的小步可以直接带上日子；没给就是没安排
        _, d = c.req("POST", "/api/step", {"action": "add", "title": "办好健身卡", "wish_id": wid, "day": today})
        a = next(s for s in d["steps"] if s["title"] == "办好健身卡")
        self.assertEqual(a["scheduled_day"], today)
        _, d = c.req("POST", "/api/step", {"action": "add", "title": "买一双跑鞋", "wish_id": wid})
        b = next(s for s in d["steps"] if s["title"] == "买一双跑鞋")
        self.assertEqual(b["scheduled_day"], "")
        self.assertEqual(c.req("POST", "/api/step", {"action": "add", "title": "x", "wish_id": "w_nope"})[0], 404)
        # 安排：只能今天或以后；空 = 不安排了
        self.assertEqual(c.req("POST", "/api/step", {"action": "schedule", "id": b["id"], "day": day(-1)})[0], 400)
        self.assertEqual(c.req("POST", "/api/step", {"action": "schedule", "id": b["id"], "day": "周六"})[0], 400)
        _, d = c.req("POST", "/api/step", {"action": "schedule", "id": b["id"], "day": day(1)})
        self.assertEqual(next(s for s in d["steps"] if s["id"] == b["id"])["scheduled_day"], day(1))
        # 偷懒日：今天安排的挪到明天，明天的不动；再点一次不会再挪
        s, d = c.req("POST", "/api/record", {"type": "rest"})
        self.assertEqual((s, d["rest_plan"]), (200, {"postponed": 1}))
        steps = {s["id"]: s for s in d["steps"]}
        self.assertEqual((steps[a["id"]]["scheduled_day"], steps[b["id"]]["scheduled_day"]), (day(1), day(1)))
        _, d = c.req("POST", "/api/record", {"type": "rest"})
        self.assertNotIn("rest_plan", d)
        # 不偷懒了：挪走的回到今天，本来就在明天的不动
        _, d = c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.assertEqual(d["rest_plan"], {"restored": 1})
        steps = {s["id"]: s for s in d["steps"]}
        self.assertEqual((steps[a["id"]]["scheduled_day"], steps[b["id"]]["scheduled_day"]), (today, day(1)))
        # 偷懒后自己又改过日子的，取消偷懒时不再挪回来
        c.req("POST", "/api/record", {"type": "rest"})
        c.req("POST", "/api/step", {"action": "schedule", "id": a["id"], "day": day(3)})
        _, d = c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.assertEqual(d["rest_plan"], {"restored": 0})
        self.assertEqual(next(s for s in d["steps"] if s["id"] == a["id"])["scheduled_day"], day(3))
        # 不安排了；做完的不能再安排；安排过的照样能完成、照样给经验
        _, d = c.req("POST", "/api/step", {"action": "schedule", "id": a["id"], "day": ""})
        self.assertEqual(next(s for s in d["steps"] if s["id"] == a["id"])["scheduled_day"], "")
        s, d = c.req("POST", "/api/step", {"action": "done", "id": b["id"]})
        self.assertEqual((s, d["xp"]["amount"]), (200, 10))
        self.assertEqual(c.req("POST", "/api/step", {"action": "schedule", "id": b["id"], "day": today})[0], 404)

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
            [("tool_calls", [{"id": "c1", "name": "propose_moment", "arguments": json.dumps({"text": "今天十一点就睡了"})},
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
        self.assertTrue([d["id"] for e, d in ev if e == "mood"])          # 调工具时小光换了表情
        sys_prompt = " ".join(m["content"] for m in self.fake.seen[0] if m["role"] == "system")
        self.assertIn("健康作息", sys_prompt)
        self.assertIn("别说教", sys_prompt)
        self.assertIn("晚上十一点后容易刷手机", sys_prompt)
        tool_msg = self.fake.seen[1][-1]
        self.assertEqual(tool_msg["role"], "tool")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["journey"]["moments"], [])          # 只是提议：TA 点「留下」才存
        last = d["messages"][-1]
        self.assertEqual((last["role"], last["content"]), ("assistant", "太好了，这条我收下了。"))
        self.assertEqual(last["meta"]["tools"][0]["name"], "propose_moment")
        ask = next(a for a in last["meta"]["acts"] if a["type"] == "ask")
        self.assertEqual((ask["ask"], ask["proposal"]["wish_id"]), ("moment", ""))   # 没说是哪个愿望就不挂

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
        goods = [c.req("POST", "/api/moment", {"action": "add", "text": f"瞬间{i}"})[1]["xp"]["amount"] for i in range(6)]
        self.assertEqual(goods, [6, 6, 6, 6, 6, 0])          # 瞬间每天 30 封顶
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["today"]["events"], 60)          # 真实的事；每日任务的经验另算
        self.assertLessEqual(d["growth"]["today"]["events"], 120)
        with Store(uid) as st:                                # 同一件事不重复计分
            from core import growth
            r = growth.award(st, "good", ref="moment:same")
            r2 = growth.award(st, "good", ref="moment:same")
            self.assertTrue(r["capped"] or r["amount"] >= 0)
            self.assertTrue(r2.get("duplicate") or r2.get("capped"))

    def test_old_account_moves_into_a_town(self):
        """老账号：经验和等级一分不少，过去的经验按一半换成金币，宠物 / 徽章的记忆收起来，升级只庆祝一次。"""
        from core import growth
        c, uid = self.onboarded("migrate")
        with Store(uid) as st:   # 假装这是升级前的老账号：300 经验，小光还记着小芽
            st.c.execute("DELETE FROM coin")
            st.c.execute("DELETE FROM town_item")
            st.set_profile({"town_v": 0, "town_seen_level": 0, "town_welcome": "",
                            "notebook": {"text": "喜欢早上跑步。\n给宠物小芽起名叫豆豆。", "by": "digest"}})
            for i in range(30):
                st.c.execute("INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(?,?,?,?,?,?,?)",
                             (f"x{i}", f"2026-01-{i % 28 + 1:02d}", "good" if i % 3 else "action", 10, f"seed:{i}", "",
                              f"2026-01-{i % 28 + 1:02d}T10:00:00+08:00"))
            pet = st.add_memory("TA 的宠物小芽快分化了", "event")
            keep = st.add_memory("TA 喜欢早上跑步", "preference")
        _, d = c.req("GET", "/api/bootstrap")
        g, t = d["growth"], d["town"]
        self.assertEqual((g["total"], g["level"]["lv"]), (300, 8))     # 旧算法 300 经验是 Lv8，换曲线后保底
        self.assertEqual(g["coins"], 150)
        self.assertEqual(t["size"], 7)
        self.assertEqual(t["welcome"]["kind"], "migrated")
        self.assertIsNone(g["level_up"])                               # 老账号已经到的等级不补庆祝
        self.assertEqual({i["kind"] for i in t["items"]}, {"cottage", "road", "sign", "lamp"})   # 新手小镇
        with Store(uid) as st:
            self.assertEqual(st.get_memory(pet["id"])["status"], "archived")
            self.assertEqual(st.get_memory(keep["id"])["status"], "active")
            self.assertNotIn("小芽", st.profile()["notebook"]["text"])
            self.assertIn("跑步", st.profile()["notebook"]["text"])
        _, d = c.req("GET", "/api/bootstrap")                         # 只迁移一次
        self.assertEqual(d["growth"]["coins"], 150)
        c.req("POST", "/api/town", {"action": "welcome_seen"})
        _, out = c.req("POST", "/api/moment", {"action": "add", "text": "跨过 320 的那一件"})
        self.assertEqual(out["xp"]["first_gift"], 0)                  # 换过金币的老账号不再送第一份建材
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["level"]["lv"], 8)                 # 曲线上还不到 Lv9（740），保底不掉
        self.assertEqual(d["growth"]["level"]["to_next"], growth.xp_for_level(9) - d["growth"]["total"])
        with Store(uid) as st:   # 过去的几天又攒了一些，跨过 Lv9
            for i in range(45):
                st.c.execute("INSERT INTO xp(id, day, source, amount, ref, note, created_at) VALUES(?,?,?,?,?,?,?)",
                             (f"y{i}", "2026-02-01", "action", 10, f"seed:y{i}", "", "2026-02-01T10:00:00+08:00"))
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["level"]["lv"], 9)
        self.assertEqual(d["growth"]["level_up"]["to"], 9)
        self.assertIn("小图书馆", [i["name"] for i in d["growth"]["level_up"]["unlocks"]])
        self.assertIsNone(d["town"]["welcome"])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertIsNone(d["growth"]["level_up"])                     # 只报一次

    def test_town_buy_place_move_store(self):
        c, uid = self.onboarded("town")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["coins"], 0)
        self.assertEqual(sorted((i["kind"], i["x"], i["y"]) for i in d["town"]["items"]),          # 新手小镇：屋、路、路牌、两盏灯
                         sorted(town.STARTER))
        s, err = c.req("POST", "/api/town", {"action": "buy", "kind": "cottage", "x": 0, "y": 0, "nonce": "first-try"})
        self.assertEqual(s, 400)                                       # 还没做事，没有金币
        c.req("POST", "/api/step", {"action": "add", "title": "整理书桌"})
        sid = next(x for x in c.req("GET", "/api/bootstrap")[1]["steps"] if x["status"] == "todo")["id"]
        _, d = c.req("POST", "/api/step", {"action": "done", "id": sid})
        self.assertEqual(d["growth"]["coins"], 60)
        buy = {"action": "buy", "kind": "cottage", "x": 0, "y": 0, "nonce": "click-0001"}
        s, d = c.req("POST", "/api/town", buy)
        self.assertEqual(s, 200, d)
        hid = d["built"]["id"]
        self.assertEqual(d["built"]["name"], "小木屋")
        self.assertIn("整理书桌", d["built"]["story"]["text"])        # 记下那之前做成的事
        self.assertEqual(d["growth"]["coins"], 20)
        s, d = c.req("POST", "/api/town", buy)                        # 同一次点击重发：不再扣钱
        self.assertTrue(d["built"]["again"])
        self.assertEqual(d["growth"]["coins"], 20)
        self.assertEqual(sum(1 for i in d["town"]["items"] if i["kind"] == "cottage"), 2)   # 送的那间 + 买的这间
        for bad, why in ((dict(buy, nonce="click-0002"), "这里已经有东西了"),
                         (dict(buy, nonce="click-0003", x=1, y=1), "金币还差"),
                         (dict(buy, nonce="click-0004", kind="house", x=1, y=1), "Lv3"),
                         (dict(buy, nonce="click-0005", kind="road", x=9, y=9), "还没开出来")):
            s, err = c.req("POST", "/api/town", bad)
            self.assertEqual(s, 400, bad)
            self.assertIn(why, err["error"])
        self.assertEqual(c.req("GET", "/api/bootstrap")[1]["growth"]["coins"], 20)   # 失败的不扣钱
        _, d = c.req("POST", "/api/town", {"action": "move", "id": hid, "x": 4, "y": 1})
        self.assertEqual((d["moved"]["x"], d["moved"]["y"]), (4, 1))
        self.assertEqual(c.req("POST", "/api/town", {"action": "move", "id": hid, "x": 1, "y": 4})[0], 400)   # 路牌在那儿
        _, d = c.req("POST", "/api/town", {"action": "store", "id": hid})
        self.assertIn(hid, [i["id"] for i in d["town"]["warehouse"]])
        self.assertNotIn(hid, [i["id"] for i in d["town"]["items"]])
        _, d = c.req("POST", "/api/town", {"action": "place", "id": hid, "x": 4, "y": 4})
        self.assertIn(hid, [i["id"] for i in d["town"]["items"]])
        self.assertEqual(d["growth"]["coins"], 20)                    # 挪、收、放都不花钱
        _, d = c.req("POST", "/api/town", {"action": "move", "id": hid, "x": 4, "y": 4, "rot": 1})   # 正方形的也能转（画的时候左右翻）
        self.assertEqual(d["moved"]["rot"], 1)
        road = next(i for i in d["town"]["items"] if i["kind"] == "road")
        _, d = c.req("POST", "/api/town", {"action": "move", "id": road["id"], "x": road["x"], "y": road["y"], "rot": 1})
        self.assertEqual(d["moved"]["rot"], 0)                                                    # 路没有方向
        _, d = c.req("POST", "/api/town", {"action": "rename", "name": "晴 天 镇"})
        self.assertEqual(d["town"]["name"], "晴天镇")
        ledger = c.req("GET", "/api/bootstrap")[1]["growth"]["ledger"]
        self.assertIn(("建造：小木屋", -40), [(e["note"], e["coins"]) for e in ledger])
        self.assertIn(("完成：整理书桌", 10, 10), [(e["note"], e["xp"], e["coins"]) for e in ledger])   # 同一件事一行

    def test_old_starter_town_upgrades_only_if_untouched(self):
        """以前开镇只有路牌和两格路：原样没动过的换成新手小镇；自己摆过东西的一样都不碰。只做一次。"""
        old = [("sign", 0, 0), ("road", 2, 4), ("road", 2, 3)]
        accounts = {}
        for name, extra in (("starter_old", None), ("starter_built", ("tree", 4, 0))):
            c, uid = self.onboarded(name)
            with Store(uid) as st:
                st.c.execute("DELETE FROM town_item")
                for kind, x, y in old + ([extra] if extra else []):
                    town._insert(st, kind, x, y, source="gift" if not extra or (kind, x, y) != extra else "shop")
                st.set_profile({"town_v": 2})
            accounts[name] = c
        _, d = accounts["starter_old"].req("GET", "/api/bootstrap")
        self.assertEqual(sorted((i["kind"], i["x"], i["y"]) for i in d["town"]["items"]), sorted(town.STARTER))
        _, d = accounts["starter_built"].req("GET", "/api/bootstrap")
        self.assertEqual(sorted((i["kind"], i["x"], i["y"]) for i in d["town"]["items"]), sorted(old + [("tree", 4, 0)]))

    def test_showcase_account_is_consistent(self):
        """官方展示账号：等级、金币、小镇都对得上账；地上的东西不重叠、不出界；小步的安排都在今天以后。"""
        from core import growth, journey
        from core.showcase import seed_showcase
        c, uid = self.member("showcase")
        with Store(uid) as st:
            out = seed_showcase(st)
            self.assertGreaterEqual(out["lv"], 15)
            self.assertEqual(out["coins"], growth.coins(st))
            self.assertGreater(out["coins"], 300)
            cells = [(i["x"], i["y"]) for i in town.items(st)]
            self.assertEqual(len(cells), len(set(cells)))
            self.assertTrue(all(0 <= x < out["size"] and 0 <= y < out["size"] for x, y in cells))
            today = journey.now().date().isoformat()
            self.assertTrue(all(s["scheduled_day"] >= today for s in st.steps(200) if s["status"] == "todo" and s["scheduled_day"]))
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["level"]["lv"], out["lv"])
        self.assertEqual(len(d["journey"]["wishes"]), 4)   # 睡觉、跑步、大理、刚加的电吉他

    def test_daily_tasks_pay_once_and_chat_gives_no_coins(self):
        from core.util import day_key
        c, uid = self.onboarded("daily")
        with Store(uid) as st:   # 今天的四件：固定的行动 + 留下一个瞬间 + 做一次练习 + 留下两个瞬间
            st.set_profile({"daily_pick": {"day": day_key(), "ids": ["act", "moment", "practice", "record2"], "scene": "gratitude"}})
        self.fake.turns = [[("text", "嗨")]]
        c.sse("在吗")                                                 # 每天第一次来聊：只有经验
        _, d = c.req("GET", "/api/bootstrap")
        dl = d["growth"]["daily"]
        self.assertEqual((d["growth"]["today"]["by_source"]["checkin"], d["growth"]["coins"]), (8, 0))
        self.assertEqual([t["id"] for t in dl["tasks"]], ["act", "moment", "practice", "record2"])
        self.assertEqual(dl["max"], {"xp": 5 + 5 + 8 + 10 + 10, "coins": 10 + 8 + 12 + 18 + 20})
        self.assertFalse(any(t["done"] for t in dl["tasks"]))
        self.assertEqual(c.req("POST", "/api/record", {"type": "good", "text": "晒到了太阳"})[0], 400)   # 好消息下线了
        _, out = c.req("POST", "/api/moment", {"action": "add", "text": "晒到了太阳"})
        self.assertEqual([x["id"] for x in out["xp"]["daily"]], ["moment"])
        self.assertEqual((out["xp"]["amount"], out["xp"]["amount_total"]), (6, 11))   # 瞬间 6 + 每日任务 5
        _, out = c.req("POST", "/api/moment", {"action": "add", "text": "又一件"})
        self.assertEqual([x["id"] for x in out["xp"]["daily"]], ["record2"])            # 第二件：留下两个瞬间
        _, out = c.req("POST", "/api/moment", {"action": "add", "text": "第三件"})
        self.assertEqual(out["xp"]["daily"], [])                       # 一天只发一次
        from core import scenes
        _, d = c.req("POST", "/api/scene/start", {"scene": "gratitude"})
        for i in range(len(scenes.SCENES["gratitude"]["steps"])):
            _, sc = c.req("POST", "/api/scene/answer", {"run_id": d["run"]["id"], "text": f"第{i}件"})
        self.assertEqual([x["id"] for x in sc["xp"]["daily"]], ["practice"])
        # 偷懒：行动那项先暂停，另外三件做到了就拿全勤
        _, d = c.req("POST", "/api/record", {"type": "rest", "text": "今天偷个懒"})
        act = next(t for t in d["growth"]["daily"]["tasks"] if t["id"] == "act")
        self.assertTrue(act["rest"] and not act["done"])
        self.assertTrue(d["growth"]["daily"]["bonus"]["paid"])
        coins, xp = d["growth"]["coins"], d["growth"]["total"]
        for _ in range(2):
            _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual((d["growth"]["coins"], d["growth"]["total"]), (coins, xp))   # 刷新不会多发
        self.assertEqual(d["growth"]["daily"]["got"], {"xp": 5 + 8 + 10 + 10, "coins": 8 + 12 + 18 + 20})
        with Store(uid) as st:
            n = st.c.execute("SELECT COUNT(*) FROM coin WHERE kind='daily'").fetchone()[0]
            self.assertEqual(n, 4)                                     # 一个瞬间 + 两个瞬间 + 练习 + 全勤
            self.assertIn("今天的每日任务四件都做到了", [a["text"] for a in st.activity(10)])

    def test_daily_tasks_rotate_and_fit_the_person(self):
        from core import growth
        from core.util import day_key
        c, uid = self.onboarded("rotate")
        with Store(uid) as st:
            picks = []
            for day in ("2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04"):
                p = growth._pick(st, day)
                self.assertEqual(p["ids"][0], "act")                   # 第一件永远是行动
                self.assertEqual([growth.DAILY[i]["slot"] for i in p["ids"]], list(growth.SLOTS))
                self.assertNotIn("habit2", p["ids"])                   # 没有两个习惯就不出「两个习惯」
                self.assertNotIn("wish2", p["ids"])                    # 只有一个愿望
                picks.append(tuple(p["ids"]))
                self.assertEqual(growth._pick(st, day), p)             # 同一天再问一遍不变
            self.assertGreater(len(set(picks)), 1)                     # 每天不一样
            st.set_profile({"daily_pick": {"day": day_key(), "ids": ["act", "moment", "pick", "act3"], "scene": "meditation"}})
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["growth"]["daily"]["pick"], "meditation")   # 点子页的今日推荐就是它
        self.assertIn("遇见更好的自己", next(t for t in d["growth"]["daily"]["tasks"] if t["id"] == "pick")["label"])
        from core import scenes
        _, run = c.req("POST", "/api/scene/start", {"scene": "gratitude"})   # 做别的练习：不算「今天推荐的」
        for i in range(len(scenes.SCENES["gratitude"]["steps"])):
            _, sc = c.req("POST", "/api/scene/answer", {"run_id": run["run"]["id"], "text": "好"})
        self.assertEqual(sc["xp"]["daily"], [])
        _, run = c.req("POST", "/api/scene/start", {"scene": "meditation"})
        for i in range(len(scenes.SCENES["meditation"]["steps"])):
            _, sc = c.req("POST", "/api/scene/answer", {"run_id": run["run"]["id"], "text": "好"})
        self.assertEqual([x["id"] for x in sc["xp"]["daily"]], ["pick"])

    def test_level_curve_grows_and_never_drops(self):
        from core import growth
        self.assertEqual([growth.xp_for_level(l) for l in (1, 2, 3, 5, 10, 20)], [0, 40, 95, 250, 900, 3325])
        self.assertEqual(growth.level_of(39)["lv"], 1)
        self.assertEqual(growth.level_of(40)["lv"], 2)
        lv = growth.level_of(322, floor=9)                             # 老账号保底 Lv9
        self.assertEqual((lv["lv"], lv["into"], lv["to_next"]), (9, 0, growth.xp_for_level(10) - 322))
        self.assertEqual(growth.level_of(2000, floor=9)["lv"], 15)      # 曲线追上来以后照常升
        # 每级最多 500（满额大约三天一级），不会无限涨
        self.assertEqual(growth.level_cost(31), 490)
        self.assertEqual([growth.level_cost(n) for n in (32, 50, 200)], [500, 500, 500])
        self.assertEqual(growth.xp_for_level(60) - growth.xp_for_level(59), 500)
        self.assertEqual(growth.level_of(growth.xp_for_level(45))["lv"], 45)

    # ---- 小镇：素材库、后台全局改价格和等级、大建筑 ----
    def admin(self):
        a = Client(self.port)
        self.assertEqual(a.req("POST", "/api/admin/login", {"key": "test-admin"})[0], 200)
        return a

    def test_building_library_and_admin_overrides(self):
        from core import town
        lib = town.library()
        self.assertGreaterEqual(len(lib), 30)
        self.assertEqual(lib["market"]["size"], [1, 2])
        s, js, _ = Client(self.port).req("GET", "/js/buildings/all.js", raw=True)
        self.assertEqual(s, 200)
        self.assertIn('B["ferris"]', js)
        self.assertNotIn("export default function", js)                # 每个文件都换成了 B[id] = …
        c, uid = self.onboarded("lib_town")
        a = self.admin()
        self.assertEqual(c.req("GET", "/api/admin/town")[0], 401)       # 用户会话不是后台会话
        s, cat = a.req("GET", "/api/admin/town")
        self.assertEqual(s, 200)
        self.assertTrue(any(i["id"] == "cottage" and i["price"] == 40 for i in cat["items"]))
        s, _ = a.req("POST", "/api/admin/town", {"items": {"cottage": {"price": 25, "lv": 1}, "bush": {"enabled": False}}})
        self.assertEqual(s, 200)
        _, d = c.req("GET", "/api/bootstrap")
        ids = {x["id"]: x for x in d["town"]["catalog"]}
        self.assertEqual(ids["cottage"]["price"], 25)
        self.assertNotIn("bush", ids)                                  # 下架了就不卖
        c.req("POST", "/api/step", {"action": "add", "title": "第一步"})
        sid = next(x for x in c.req("GET", "/api/bootstrap")[1]["steps"] if x["status"] == "todo")["id"]
        _, d = c.req("POST", "/api/step", {"action": "done", "id": sid})
        coins = d["growth"]["coins"]
        _, d = c.req("POST", "/api/town", {"action": "buy", "kind": "cottage", "x": 4, "y": 0, "nonce": "cheap-0001"})
        self.assertEqual(d["growth"]["coins"], coins - 25)            # 按后台改过的价格扣
        self.assertEqual(c.req("POST", "/api/town", {"action": "buy", "kind": "bush", "x": 0, "y": 3, "nonce": "bush-0001"})[0], 400)
        for bad in ({"nope": {"price": 1}}, {"cottage": {"price": -1}}, {"cottage": {"lv": "x"}}):
            self.assertEqual(a.req("POST", "/api/admin/town", {"items": bad})[0], 400, bad)
        _, cat = a.req("POST", "/api/admin/town", {"items": {"cottage": None, "bush": None}})   # 恢复默认
        self.assertEqual(next(i for i in cat["items"] if i["id"] == "cottage")["price"], 40)
        self.assertEqual(c.req("GET", "/api/bootstrap")[1]["town"]["catalog"][0]["price"], 40)

    def test_admin_adjusts_xp_and_coins_with_a_record(self):
        c, uid = self.onboarded("adj_user")
        a = self.admin()
        self.assertEqual(a.req("POST", "/api/admin/user/adjust", {"id": uid, "coins": 50})[0], 400)            # 要写原因
        self.assertEqual(a.req("POST", "/api/admin/user/adjust", {"id": uid, "coins": -1, "reason": "x"})[0], 400)  # 不能扣到负数
        s, g = a.req("POST", "/api/admin/user/adjust", {"id": uid, "xp": 120, "coins": 300, "reason": "活动奖励"})
        self.assertEqual(s, 200, g)
        self.assertEqual((g["xp"], g["coins"]), (120, 300))
        self.assertEqual(g["adjustments"][0]["reason"], "活动奖励")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual((d["growth"]["total"], d["growth"]["coins"]), (120, 300))
        self.assertIn(("后台调整：活动奖励", 120, 300), [(e["note"], e["xp"], e["coins"]) for e in d["growth"]["ledger"]])
        self.assertEqual(d["growth"]["coins_today"], 0)                # 后台给的不算「今天挣的」
        s, g = a.req("POST", "/api/admin/user/adjust", {"id": uid, "coins": -100, "reason": "多给了"})
        self.assertEqual(g["coins"], 200)
        row = next(u for u in a.req("GET", "/api/admin/users")[1]["users"] if u["id"] == uid)
        self.assertEqual(row["coins"], 200)
        self.assertGreaterEqual(len(a.req("GET", "/api/admin/log")[1]["entries"]), 2)

    def test_big_buildings_take_several_cells_and_turn(self):
        c, uid = self.onboarded("big_town")
        a = self.admin()
        from core import growth
        a.req("POST", "/api/admin/user/adjust", {"id": uid, "xp": growth.xp_for_level(16), "coins": 2000, "reason": "测试"})
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["town"]["size"], 9)
        buy = lambda kind, x, y, n, rot=0: c.req("POST", "/api/town", {"action": "buy", "kind": kind, "x": x, "y": y, "rot": rot, "nonce": n})
        s, d = buy("market", 4, 4, "mk-000001")                        # 1×2：占 (4,4)、(4,5)
        self.assertEqual(s, 200, d)
        mid = d["built"]["id"]
        self.assertEqual(buy("tree", 4, 5, "tr-000001")[0], 400)        # 第二格也被占了
        self.assertEqual(buy("market", 8, 8, "mk-000002")[0], 400)      # 伸出地外
        self.assertEqual(buy("market", 4, 3, "mk-000003")[0], 400)      # 和上一座重叠
        s, d = c.req("POST", "/api/town", {"action": "move", "id": mid, "x": 5, "y": 1, "rot": 1})   # 转过来：占 (5,1)、(6,1)
        self.assertEqual((s, d["moved"]["rot"]), (200, 1))
        self.assertEqual(buy("tree", 6, 1, "tr-000002")[0], 400)
        self.assertEqual(buy("tree", 4, 5, "tr-000003")[0], 200)        # 原来的地方空出来了
        self.assertEqual(buy("park", 0, 6, "pk-000001")[0], 400)        # 中心花园要 Lv22

    def test_last_step_of_a_wish_says_so(self):
        c, uid = self.onboarded("cleared")
        _, d = c.req("GET", "/api/bootstrap")
        wid = d["journey"]["current"]
        for t in ("第一步", "第二步"):
            c.req("POST", "/api/step", {"action": "add", "title": t, "wish_id": wid})
        todo = [x for x in c.req("GET", "/api/bootstrap")[1]["steps"] if x["status"] == "todo" and x["wish_id"] == wid]
        _, out = c.req("POST", "/api/step", {"action": "done", "id": todo[0]["id"]})
        self.assertIsNone(out["cleared"])                              # 还有一步
        _, out = c.req("POST", "/api/step", {"action": "done", "id": todo[1]["id"]})
        self.assertEqual((out["cleared"]["wish_id"], out["cleared"]["done"]), (wid, 2))
        from core import nudges
        with Store(uid) as st:
            self.assertIn("steps_cleared", [x["kind"] for x in nudges.attention(st)])

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

    def test_agent_look(self):
        c, _ = self.onboarded("look")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["profile"]["agent_avatar_id"], "cloud.moon.jelly")   # 建档没选时是云朵 · 月白
        s, d = c.req("POST", "/api/profile", {"agent_avatar_id": "cat.lilac.liquid"})
        self.assertEqual((s, d["profile"]["agent_avatar_id"]), (200, "cat.lilac.liquid"))
        for bad in ("soft", "cat.lilac", "cat.neon.jelly", "dragon.moon.jelly", "cat.moon.metal", ""):
            self.assertEqual(c.req("POST", "/api/profile", {"agent_avatar_id": bad})[0], 400, bad)
        # 下架的形状：换成最接近的保留形状，颜色和质感不变
        for old, new in (("hex.origin.jelly", "cube.origin.jelly"), ("heart.sakura.liquid", "flower.sakura.liquid"), ("gummy.sky.jelly", "mochi.sky.jelly")):
            s, d = c.req("POST", "/api/profile", {"agent_avatar_id": old})
            self.assertEqual((s, d["profile"]["agent_avatar_id"]), (200, new), old)
        c2, _ = self.member("look2")
        s, d = c2.req("POST", "/api/onboard", {"answers": {**ONBOARD, "agent_avatar_id": "star.night.jelly"}})
        self.assertEqual((s, d["profile"]["agent_avatar_id"]), (200, "star.night.jelly"))
        c3, _ = self.member("look3")
        s, d = c3.req("POST", "/api/onboard", {"answers": {**ONBOARD, "agent_avatar_id": "drop.sea.liquid"}})
        self.assertEqual((s, d["profile"]["agent_avatar_id"]), (200, "mochi.sea.liquid"))
        keys = [q["key"] for q in c2.req("GET", "/api/bootstrap")[1]["onboarding"]]
        self.assertNotIn("agent_hue", keys)
        self.assertIn("agent_avatar_id", keys)

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
        self.assertFalse(scheduler.should_reach_out(recent, False, at(9))[0])   # 7h < 8h
        self.assertTrue(scheduler.should_reach_out(recent, False, at(11))[0])   # 9h ≥ 8h
        self.assertFalse(scheduler.should_reach_out({**recent, "proactive": "less"}, False, at(15))[0])   # 13h < 24h
        self.assertTrue(scheduler.should_reach_out({**recent, "proactive": "more"}, False, at(8))[0])     # 6h ≥ 4h

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

    def test_old_unseen_message_does_not_block_proactive(self):
        # 之前前端从不标记已读：一条旧的主动消息会永远挡住后面的
        c, uid = self.onboarded("pro_stuck")
        self.fake.json_out = {"text": "还在靠近「健康作息」吗？"}
        c.req("POST", "/api/proactive/now", {})
        with Store(uid) as st:
            self.assertTrue(scheduler.waiting_unseen(st))
            st.set_profile({"last_chat_at": "2999-01-01T00:00:00+08:00"})   # TA 之后又来聊过
            self.assertFalse(scheduler.waiting_unseen(st))
        self.fake.turns = [[("text", "嗯，我在。")]]
        c.sse("我回来啦")                                                      # sending a message marks it seen
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
        self.assertGreaterEqual(d["facts"]["moments"], 5)
        self.assertIn("第一个瞬间", [n["label"] for n in d["nodes"]])
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

    def test_review_and_remind_pref_gone(self):
        """阶段回望下线（愿望卡上换成蜕变报告入口）、陪伴偏好去掉「多久提醒一次」：
        写过的回望和它的动态删掉，提醒频率清空，当天抽到的「写一段阶段回望」换成「做 1 次练习」；只做一次。"""
        from core import agent, growth, lookup
        from core.util import day_key
        c, uid = self.member("review_gone")
        _, d = c.req("POST", "/api/wish", {"action": "add", "title": "心里安静一点", "category": "calm"})
        wid = d["journey"]["current"]
        with Store(uid) as st:
            st.c.execute("CREATE TABLE IF NOT EXISTS reflection(id TEXT PRIMARY KEY, wish_id TEXT, days INTEGER, text TEXT, created_at TEXT)")
            st.c.execute("INSERT INTO reflection VALUES('rf_1', ?, 7, '好像没那么紧了', '2026-11-01T10:00:00')", (wid,))
            st.log("journey", "写下了一段阶段回望")
            st.c.execute("INSERT OR REPLACE INTO profile(k, v) VALUES('remind_pref', '\"每天\"')")
            st.c.execute("DELETE FROM profile WHERE k='review_gone'")      # 当作还没迁移过的老账号
        with Store(uid) as st:
            self.assertIsNone(st.c.execute("SELECT 1 FROM sqlite_master WHERE name='reflection'").fetchone())
            self.assertNotIn("回望", " ".join(a["text"] for a in st.activity(20)))
            self.assertNotIn("remind_pref", st.profile())
            day = day_key()
            growth._pick(st, day)
            ids = st.profile()["daily_pick"]["ids"]
            st.set_profile({"daily_pick": {**st.profile()["daily_pick"], "ids": [ids[0], ids[1], "reflect", ids[3]]}})
            self.assertEqual(growth._pick(st, day)["ids"], [ids[0], ids[1], "practice", ids[3]])
            self.assertNotIn("reflect", growth.DAILY)
            self.assertNotIn("remind_pref", agent.SETTING_LABEL)
            self.assertNotIn("回望", lookup.look_up(st, "wish", "心里安静一点")["text"])
        self.assertEqual(c.req("GET", f"/api/wish/review?id={wid}&days=7")[0], 404)
        self.assertEqual(c.req("POST", "/api/wish/reflect", {"id": wid, "days": 7, "text": "x"})[0], 404)
        _, d = c.req("POST", "/api/profile", {"remind_pref": "每天"})                # 旧页面发来的也不收
        self.assertNotIn("remind_pref", d["prefs"])
        self.assertNotIn("remind_pref", d["profile"])

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
        self.assertEqual([(i["name"], i["note"]) for i in d["town"]["warehouse"]], [("纪念碑", "能连续跑 5 公里")])
        _, d = c.req("POST", "/api/milestone", {"action": "todo", "id": mid})
        _, d = c.req("POST", "/api/milestone", {"action": "done", "id": mid})
        self.assertEqual(len(d["town"]["warehouse"]), 1)               # 改回来再到达，不会再送一块
        # 休息日：记一次、重复点不重复记、可以撤销
        _, d = c.req("POST", "/api/record", {"type": "rest"})
        _, d = c.req("POST", "/api/record", {"type": "rest"})
        self.assertEqual(d["journey"]["rest_days"], [today])
        self.assertEqual(sum(1 for r in d["records"] if r["type"] == "rest"), 1)
        _, d = c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.assertEqual(d["journey"]["rest_days"], [])
        # 好消息（连同内心戏、新发现）下线了，换成了瞬间
        self.assertEqual(c.req("POST", "/api/record", {"type": "meme", "text": "我：早睡。也是我：再刷十分钟"})[0], 400)
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

    def _photo(self, c, kind="jpg", size=2000):
        import base64
        head = {"jpg": b"\xff\xd8\xff\xe0", "webp": b"RIFF\x00\x00\x00\x00WEBPVP8 ", "txt": b"hello"}[kind]
        b64 = lambda n: base64.b64encode(head + b"\x00" * n).decode()
        return c.req("POST", "/api/photo", {"data": b64(size), "thumb": b64(200)})

    def _get_bytes(self, c, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", path, headers={"Cookie": c.cookie} if c.cookie else {})
        r = conn.getresponse()
        out = (r.status, r.getheader("Content-Type"), r.getheader("Cache-Control"), r.read())
        conn.close()
        return out

    def test_moment_photo_upload_view_replace_delete(self):
        from core import photos
        c, uid = self.member("photo_a")
        other, _ = self.member("photo_b")
        s, out = self._photo(c, "jpg")
        self.assertEqual(s, 200, out)
        pid = out["photo"]
        # 只有本人能看；大图和小图都在
        st_, ctype, cache, data = self._get_bytes(c, f"/api/photo?id={pid}")
        self.assertEqual((st_, ctype), (200, "image/jpeg"))
        self.assertIn("private", cache)
        self.assertTrue(data.startswith(b"\xff\xd8\xff"))
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid}&s=1")[0], 200)
        self.assertEqual(self._get_bytes(other, f"/api/photo?id={pid}")[0], 404)
        self.assertEqual(self._get_bytes(Client(self.port), f"/api/photo?id={pid}")[0], 401)
        self.assertEqual(self._get_bytes(c, "/api/photo?id=../mind.db")[0], 404)
        # 不是图片、太大：不收
        self.assertEqual(self._photo(c, "txt")[0], 400)
        self.assertEqual(self._photo(c, "jpg", photos.MAX_FULL + 10)[0], 400)   # 照片超过 3MB 不收
        # 瞬间可以不挂愿望、带一张照片；别人的照片 id 挂不上
        self.assertEqual(c.req("POST", "/api/moment", {"action": "add", "text": "x", "photo": "ph_000000000000"})[0], 400)
        _, d = c.req("POST", "/api/moment", {"action": "add", "text": "今天的晚霞", "photo": pid})
        m = d["moment"]
        self.assertEqual((m["wish_id"], m["photo"]), ("", pid))
        self.assertIn(m["id"], [x["id"] for x in d["journey"]["moments"]])
        # 挂到一个愿望下；换一张照片：旧的那张删掉
        _, d = c.req("POST", "/api/wish", {"action": "add", "title": "更爱生活", "category": "calm"})
        wid = d["journey"]["wishes"][0]["id"]
        pid2 = self._photo(c, "webp")[1]["photo"]
        _, d = c.req("POST", "/api/moment", {"action": "edit", "id": m["id"], "wish_id": wid, "photo": pid2})
        m2 = next(x for x in d["journey"]["moments"] if x["id"] == m["id"])
        self.assertEqual((m2["wish_id"], m2["photo"]), (wid, pid2))
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid}")[0], 404)
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid2}")[1], "image/webp")
        # 去掉照片、再挂回没愿望；删掉瞬间：照片文件跟着没了
        pid3 = self._photo(c, "jpg")[1]["photo"]
        c.req("POST", "/api/moment", {"action": "edit", "id": m["id"], "photo": "", "wish_id": ""})
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid2}")[0], 404)
        _, d = c.req("POST", "/api/moment", {"action": "edit", "id": m["id"], "photo": pid3})
        c.req("POST", "/api/moment", {"action": "delete", "id": m["id"]})
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid3}")[0], 404)
        with Store(uid) as st:
            self.assertEqual(list((st.dir / "photos").iterdir()), [])
            # 没挂上的照片放一天以后清掉
            p4 = photos.save(st, *(__import__("base64").b64encode(b"\xff\xd8\xff" + b"0" * 50).decode() for _ in range(2)))
            for f in photos.files(st, p4):
                os.utime(f, (time.time() - 90000, time.time() - 90000))
            self.assertEqual(photos.clean_orphans(st), 2)
            # 每人上限
            old = photos.MAX_PER_USER
            photos.MAX_PER_USER = 1
            try:
                photos.save(st, *(__import__("base64").b64encode(b"\xff\xd8\xff" + b"0" * 50).decode() for _ in range(2)))
                with self.assertRaises(ValueError):
                    photos.save(st, *(__import__("base64").b64encode(b"\xff\xd8\xff" + b"0" * 50).decode() for _ in range(2)))
            finally:
                photos.MAX_PER_USER = old

    def test_goodnews_gone_once_and_tasks_map_to_moments(self):
        """好消息下线：旧的好消息、新发现、内心戏连同动态一起删掉，记忆里「好消息」并进「发生过的事」，经验和金币不动；只做一次。"""
        from core import agent, growth, lookup
        from core.util import day_key
        c, uid = self.member("goodnews_gone")
        with Store(uid) as st:
            for t, text in (("good", "楼下的猫让我摸了"), ("find", "旧的新发现"), ("meme", "今天的我：社恐但嘴硬"), ("rest", "今天偷个懒")):
                st.add_record(t, text)
            st.log("record", "记下一件小确幸")
            m = st.add_memory("TA 最近被老师夸了", "good_news")
            growth.award(st, "good", ref="rec:old", note="小确幸")
            xp = growth.total_xp(st)
            st.c.execute("DELETE FROM profile WHERE k='goodnews_gone'")   # 当作还没迁移过的老账号
        with Store(uid) as st:
            self.assertEqual([r["type"] for r in st.records()], ["rest"])
            self.assertNotIn("小确幸", " ".join(a["text"] for a in st.activity(20)))
            self.assertEqual(st.get_memory(m["id"])["kind"], "event")
            self.assertEqual(growth.total_xp(st), xp)                      # 不倒扣
            # 今天已经抽到了「好消息」「内心戏」：换成「留下一个瞬间」
            day = day_key()
            growth._pick(st, day)
            ids = st.profile()["daily_pick"]["ids"]
            st.set_profile({"daily_pick": {**st.profile()["daily_pick"], "ids": [ids[0], "good", ids[2], ids[3]]}})
            self.assertEqual(growth._pick(st, day)["ids"], [ids[0], "moment", ids[2], ids[3]])
            # 小光：好消息的工具没了，查「好消息」落到瞬间
            self.assertNotIn("log_good_news", [t["function"]["name"] for t in agent.TOOLS])
            self.assertIn("ok", agent.run_tool(st, "log_good_news", {"text": "x"}))
            self.assertIn("瞬间", lookup.look_up(st, "good_news")["text"])
            st.add_record("good", "迁移以后又写进来的")                     # 只迁移一次：之后不再动
        with Store(uid) as st:
            self.assertEqual(len(st.records()), 2)
        self.assertEqual(c.req("POST", "/api/record", {"type": "good", "text": "x"})[0], 400)
        _, ex = c.req("GET", "/api/export")
        self.assertNotIn("社恐", json.dumps(ex, ensure_ascii=False))

    def test_cheer_you_and_affirmations(self):
        from core import cheer
        c, uid = self.member("cheer")
        _, d = c.req("GET", "/api/bootstrap")
        ch = d["cheer"]
        self.assertIsNone(ch["you"])                                   # 没材料就没有「最近的你」
        self.assertIn("我值得拥有精彩的人生。", ch["affirm"])
        self.assertTrue(all(t.startswith(("我", "好事", "今天", "事情", "平静", "机会")) for t in ch["affirm"]))
        c.req("POST", "/api/wish", {"action": "add", "title": "身体好一点", "category": "body"})
        self.assertIn("我的身体是一个奇迹。", c.req("GET", "/api/bootstrap")[1]["cheer"]["affirm"])
        self.assertNotIn("我身边有爱我的人。", c.req("GET", "/api/bootstrap")[1]["cheer"]["affirm"])   # 关系类只给有关系愿望的人
        with Store(uid) as st:
            from core import journey
            journey.add_moment(st, "", "楼下的猫让我摸了")
            journey.add_moment(st, "", "第一次在课上举手了")
            self.fake.json_out = {"text": "这不是小事，而是你在照顾自己。"}
            self.assertIsNone(cheer.refresh(uid))                       # 「不是……而是」的句子不用
            self.fake.json_out = {"text": "这几天你一直在留意身边的小可爱。"}
            self.assertEqual(cheer.refresh(uid)["kind"], "you")
        self.assertEqual(c.req("GET", "/api/bootstrap")[1]["cheer"]["you"]["text"], "这几天你一直在留意身边的小可爱。")

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
        # 一键偷懒（带原因）：每日任务的行动这项先暂停，休息记录留在时间线上
        c2, uid = self.member("rest_mode2")       # 今天还没做任何行动的人
        _, d = c2.req("POST", "/api/record", {"type": "rest", "text": "今天偷个懒：有点累"})
        q = next(x for x in d["growth"]["daily"]["tasks"] if x["id"] == "act")
        self.assertTrue(q["rest"] and not q["done"])
        self.assertIn("今天偷个懒：有点累", [a["text"] for a in d["activity"]])
        c = c2
        # 偷懒日小光不主动打扰（演示用的强制触发不受影响）
        with Store(uid) as st:
            st.set_profile({"onboarded": True, "last_chat_at": "", "last_proactive_at": ""})
            self.assertEqual(scheduler.deliver(st)["reason"], "今天是偷懒日，不打扰")
        # 不偷懒了：任务恢复
        _, d = c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.assertFalse(next(x for x in d["growth"]["daily"]["tasks"] if x["id"] == "act")["rest"])

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

    def test_memory_requests_follow_the_conversation(self):
        c, uid = self.onboarded("notebook_user")
        with Store(uid) as st:
            st.set_profile({"notebook": {"text": "最近的生活：在准备考试。\n相处时的偏好：不喜欢被催。", "by": "digest"}})
        # 1) 直接让小光往笔记本里加
        self.fake.turns = [[("tool_calls", [{"id": "n1", "name": "update_notebook", "arguments": json.dumps(
            {"action": "add", "text": "爱看动漫", "section": "相处时的偏好"})}])], [("text", "加好啦。")]]
        s, ev = c.sse("我看到你的笔记本了，好好笑，帮我加一个“我爱看动漫”吧")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "update_notebook")
        self.assertTrue(tool["result"]["ok"])
        with Store(uid) as st:
            nb = st.profile()["notebook"]["text"]
            self.assertIn("相处时的偏好：不喜欢被催；爱看动漫", nb)
            self.assertIn("爱看动漫", [m["text"] for m in st.memories(limit=50)])
        # 2) 前面提了一句、小光问要不要记，这一句只说「那你加进去吧」也算同意
        self.fake.turns = [[("text", "要我帮你记住你喜欢猫吗？")]]
        c.sse("我好喜欢猫")
        self.fake.turns = [[("tool_calls", [{"id": "n2", "name": "remember", "arguments": json.dumps({"text": "喜欢猫", "kind": "preference"})}])],
                           [("text", "记下啦。")]]
        s, ev = c.sse("那你加进去吧")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "remember")
        self.assertTrue(tool["result"]["ok"], tool["result"])
        # 2b)「对了……」开头的新话题不是同意
        self.fake.turns = [[("tool_calls", [{"id": "n4", "name": "remember", "arguments": json.dumps({"text": "养了一只叫团团的猫"})}])],
                           [("text", "团团！听起来软乎乎的。")]]
        c.sse("对了我养了一只叫团团的猫")
        with Store(uid) as st:
            self.assertNotIn("养了一只叫团团的猫", [m["text"] for m in st.memories(limit=50)])
        # 2c) 「记着点」「那条删了吧」这种说法也算
        self.fake.turns = [[("tool_calls", [{"id": "n5", "name": "remember", "arguments": json.dumps({"text": "特别怕打雷"})}])], [("text", "好，记着呢。")]]
        c.sse("我其实特别怕打雷，你能记着点吗")
        with Store(uid) as st:
            self.assertIn("特别怕打雷", [m["text"] for m in st.memories(limit=50)])
        # 3) 和记忆无关的一句话，小光自己想写也写不进去
        self.fake.turns = [[("tool_calls", [{"id": "n3", "name": "remember", "arguments": json.dumps({"text": "今天下雨"})}])],
                           [("text", "下雨天适合窝着。")]]
        s, ev = c.sse("今天下雨了")
        self.assertFalse([d for e, d in ev if e == "tool" and d["name"] == "remember"])   # 被拦下的写入不显示卡片
        with Store(uid) as st:
            self.assertNotIn("今天下雨", [m["text"] for m in st.memories(limit=50)])
        # 4) 改和删
        with Store(uid) as st:
            from core import agent
            self.assertTrue(agent.notebook_edit(st, "replace", "在准备期末考试", old="在准备考试")["ok"])
            self.assertTrue(agent.notebook_edit(st, "remove", "", old="爱看动漫")["ok"])
            nb = st.profile()["notebook"]["text"]
            self.assertIn("在准备期末考试", nb)
            self.assertNotIn("动漫", nb)
            self.assertTrue(nb.split("\n")[1].endswith("不喜欢被催"))
            self.assertFalse(agent.notebook_edit(st, "remove", "", old="不存在的话")["ok"])

    def test_agent_edits_existing_plan_items(self):
        from datetime import date, timedelta
        c, uid = self.onboarded("plan_edit")
        _, d = c.req("GET", "/api/bootstrap")
        wid = d["journey"]["current"]
        today = date.fromisoformat(d["journey"]["today"])
        c.req("POST", "/api/milestone", {"action": "add", "wish_id": wid, "title": "选定一首慵懒浪漫的爵士曲",
                                          "due_day": (today + timedelta(days=10)).isoformat()})
        c.req("POST", "/api/habit", {"action": "add", "wish_id": wid, "title": "练琴 20 分钟", "freq": "daily"})
        c.req("POST", "/api/step", {"action": "add", "title": "买一本爵士和弦书", "wish_id": wid})
        new_due = (today + timedelta(days=3)).isoformat()
        self.fake.turns = [
            [("tool_calls", [{"id": "e1", "name": "edit_plan", "arguments": json.dumps(
                {"kind": "milestone", "target": "选定慵懒爵士曲目", "due_day": new_due})}])],
            [("text", "改好啦，选曲提前到了。")],
        ]
        s, ev = c.sse("你改一下吧")
        tool = next(d for e, d in ev if e == "tool" and d["name"] == "edit_plan")
        self.assertTrue(tool["result"]["ok"], tool["result"])
        _, d = c.req("GET", "/api/bootstrap")
        m = d["journey"]["wishes"][0]["milestones"][0]
        self.assertEqual(m["due_day"], new_due)
        with Store(uid) as st:
            from core import journey
            self.assertEqual(journey.edit_item(st, "habit", "练琴", {"freq": "weekly", "per_week": 3})["changed"], ["改成每周 3 次"])
            self.assertTrue(journey.edit_item(st, "step", "爵士和弦书", {"delete": True})["ok"])
            self.assertFalse(st.c.execute("SELECT 1 FROM step WHERE title='买一本爵士和弦书'").fetchone())
            out = journey.edit_item(st, "wish", "", {"due_in_days": 21})
            self.assertTrue(out["ok"] and out["changed"][0].startswith("计划日期改到"))
            miss = journey.edit_item(st, "milestone", "不存在的里程碑", {"title": "x"})
            self.assertFalse(miss["ok"])
            self.assertIn("选定一首慵懒浪漫的爵士曲", miss["have"])


    # ---- 小光能看、能改、会提醒（2.11） ----------------------------------------------
    def _tool_events(self, ev, name):
        return [d for e, d in ev if e == "tool" and d["name"] == name]

    def test_agent_removes_and_restores_a_wish_after_asking(self):
        """线上的 bug：小光问「要我帮你删掉早睡早起吗？」，用户说「可以」，结果「没有要改的内容」。"""
        c, uid = self.onboarded("wish_rm")
        _, d = c.req("POST", "/api/wish", {"action": "add", "title": "早睡早起", "category": "body"})
        wid = d["journey"]["current"]
        c.req("POST", "/api/habit", {"action": "add", "wish_id": wid, "title": "11 点上床", "freq": "daily"})
        c.req("POST", "/api/wish", {"action": "add", "title": "财富与事业", "category": "wealth"})
        self.fake.turns = [[("text", "我会建议保留「健康作息」，删掉「早睡早起」。要我帮你删掉「早睡早起」吗？")],
                           [("tool_calls", [{"id": "w1", "name": "edit_plan", "arguments": json.dumps(
                               {"kind": "wish", "target": "早睡早起", "delete": True})}])],
                           [("text", "收起了，记录都还在。")]]
        c.sse("你觉得删掉哪个呢")
        s, ev = c.sse("可以")
        tool = self._tool_events(ev, "edit_plan")[0]
        self.assertTrue(tool["result"]["ok"], tool["result"])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual([w["title"] for w in d["journey"]["wishes"]], ["健康作息", "财富与事业"])
        with Store(uid) as st:
            from core import agent, journey
            self.assertNotIn("11 点上床", [h["title"] for h in journey.habits(st)])   # 收起的愿望，它的习惯也不再算
            self.assertIn("收起的愿望", agent.core_block(st.profile(), st))
            back = agent.run_tool(st, "edit_plan", {"action": "restore", "kind": "wish", "target": "早睡早起"}, "把早睡早起找回来")
            self.assertTrue(back["ok"], back)
            self.assertIn("11 点上床", [h["title"] for h in journey.habits(st)])
            # 「删掉一个吧」没点名：不能替 TA 挑一个删
            vague = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "wish", "target": "健康作息"},
                                   "早睡早起和健康作息是不是冲突了呀，删掉一个吧")
            self.assertTrue(vague.get("need_consent"), vague)
            self.assertTrue(agent.consented(st, "删掉早睡早起吧", removing=True))
            # 名字对不上时不能悄悄改到「正在看的那个」愿望上
            miss = journey.edit_item(st, "wish", "学吉他", {"title": "x"})
            self.assertFalse(miss["ok"])
            self.assertIn("早睡早起", miss["have"])

    def test_agent_needs_consent_before_changing_things(self):
        c, uid = self.onboarded("consent")
        _, d = c.req("GET", "/api/bootstrap")
        c.req("POST", "/api/habit", {"action": "add", "wish_id": d["journey"]["current"], "title": "每天跑步", "freq": "daily"})
        self.fake.turns = [[("tool_calls", [{"id": "x1", "name": "edit_plan", "arguments": json.dumps(
                               {"action": "remove", "kind": "habit", "target": "每天跑步"})}])],
                           [("text", "最近是不是太累了？要不要把跑步先收起来？")]]
        s, ev = c.sse("最近好累啊")
        self.assertFalse(self._tool_events(ev, "edit_plan"))          # 没让改，就不动，也不出卡片
        tool_msg = next(m for m in self.fake.seen[-1] if m["role"] == "tool")
        self.assertIn("need_consent", tool_msg["content"])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(len(d["journey"]["wishes"][0]["habits"]), 1)
        self.fake.turns = [[("tool_calls", [{"id": "x2", "name": "edit_plan", "arguments": json.dumps(
                               {"action": "remove", "kind": "habit", "target": "跑步"})}])],
                           [("text", "先收起来了。")]]
        s, ev = c.sse("好呀")
        self.assertTrue(self._tool_events(ev, "edit_plan")[0]["result"]["ok"])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["journey"]["wishes"][0]["habits"], [])

    def test_agent_adds_and_edits_every_kind_of_plan_item(self):
        c, uid = self.onboarded("plan_crud")
        from datetime import date, timedelta
        from core import agent, journey
        with Store(uid) as st:
            run = lambda args, said="帮我加一下": agent.run_tool(st, "edit_plan", args, said)
            w = run({"action": "add", "kind": "wish", "title": "学吉他", "due_in_days": 60})
            self.assertTrue(w["ok"], w)
            m = run({"action": "add", "kind": "milestone", "title": "弹完第一首曲子", "due_in_days": 20, "wish": "吉他"})
            self.assertEqual(m["wish_title"], "学吉他")
            self.assertTrue(run({"action": "add", "kind": "habit", "title": "练琴 15 分钟", "freq": "weekly", "per_week": 3})["ok"])
            self.assertTrue(run({"action": "add", "kind": "step", "title": "买一套琴弦"})["ok"])
            mo = run({"action": "add", "kind": "moment", "text": "第一次按响了 C 和弦", "feeling": "手指好痛但很开心"})
            self.assertTrue(mo["ok"] and mo["xp"]["amount"] > 0, mo)
            reached = run({"kind": "milestone", "target": "第一首曲子", "status": "done"}, "我弹完第一首了，标一下")
            self.assertTrue(reached["ok"] and reached["xp"]["amount"] > 0, reached)
            self.assertTrue(run({"action": "change", "kind": "moment", "target": "C 和弦", "feeling": "很开心"}, "改一下")["ok"])
            self.assertTrue(run({"action": "remove", "kind": "moment", "target": "C 和弦"}, "删了吧")["ok"])
            self.assertFalse(journey.moments(st))
            self.assertTrue(run({"action": "change", "kind": "step", "target": "琴弦", "status": "dropped"}, "先放一放")["ok"])
            self.assertTrue(run({"action": "restore", "kind": "step", "target": "琴弦"}, "放回来")["ok"])
            self.assertTrue(run({"action": "remove", "kind": "habit", "target": "练琴"}, "收起")["ok"])
            self.assertTrue(run({"action": "restore", "kind": "habit", "target": "练琴"}, "找回来")["ok"])
            wish = next(x for x in journey.wishes(st) if x["title"] == "学吉他")
            self.assertEqual(wish["target_day"], (date.today() + timedelta(days=60)).isoformat())

    def test_new_wish_and_revising_a_pending_plan(self):
        """2026-11-08 的两段对话：「我想要做一个新愿望，是健身」被许可检查挡掉、一直陪聊；
        提议的安排还没加进计划，TA 说其中一个小步麻烦，小光却去计划里找。"""
        c, uid = self.onboarded("wish_flow")
        from core import acts, agent, router
        with Store(uid) as st:
            ok = agent.run_tool(st, "edit_plan", {"action": "add", "kind": "wish", "title": "健身"}, "我想要做一个新愿望，是健身")
            self.assertTrue(ok["ok"], ok)
            routed = agent.run_tool(st, "edit_plan", {"action": "add", "kind": "step", "title": "换上运动鞋", "wish": "健身"},
                                    "早上起来很昏沉", routed="edit_plan")
            self.assertTrue(routed["ok"], routed)                        # 路由判断就是要加：放行
            gone = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "step", "target": "换上运动鞋"},
                                  "最近好累", routed="edit_plan")
            self.assertTrue(gone.get("need_consent"))                    # 删东西仍然只认 TA 的原话
            empty = agent.run_tool(st, "propose_plan", {})
            self.assertFalse(empty["ok"])
            self.assertNotIn("已经有了", empty["error"])
            nowish = agent.run_tool(st, "propose_plan", {"wish": "学钢琴", "steps": [{"title": "找一首曲子"}]})
            self.assertFalse(nowish["ok"])
            self.assertIn("学钢琴", nowish["error"])
            self.assertEqual(acts.view(st, "propose_plan", {}, nowish, {}), [])   # 没办成的不在界面上出报错，小光在回复里说

        plan = {"wish": "健身", "milestones": [{"title": "一周能练上三次", "due_in_days": 14}],
                "habits": [{"title": "练完拉伸五分钟", "freq": "weekly", "per_week": 3}],
                "steps": [{"title": "今晚挑一个想练的部位，存个视频"}, {"title": "现在站起来走十分钟"}]}
        self.fake.turns = [[("tool_calls", [{"id": "p1", "name": "propose_plan", "arguments": json.dumps(plan, ensure_ascii=False)}])],
                           [("text", "拆好啦，你看看哪些想加进来～")]]
        c.sse("帮我拆一下吧")
        with Store(uid) as st:
            self.assertIn("今晚挑一个想练的部位", "".join(router.pending_plan(st)))
            last = [m for m in agent.history(st) if m["role"] == "system"][-1]["content"]
            self.assertIn("还没加进计划", last)
            self.assertIn("今晚挑一个想练的部位，存个视频", last)
        plan2 = {**plan, "steps": [{"title": "现在站起来走十分钟"}]}
        self.fake.turns = [[("tool_calls", [{"id": "p2", "name": "propose_plan", "arguments": json.dumps(plan2, ensure_ascii=False)}])],
                           [("text", "把存视频那条拿掉了，你再看看～")]]
        c.sse("今晚挑一个想练的部位，存个视频这个小步，我觉得有点麻烦")
        with Store(uid) as st:
            asks = [a for m in st.messages(20) for a in (m.get("meta") or {}).get("acts") or [] if a.get("ask") == "plan"]
            self.assertEqual([a["state"] for a in asks], ["replaced", ""])   # 旧的一版作废，新的一版等 TA 点
            self.assertNotIn("存个视频", "".join(router.pending_plan(st)))

    def test_look_up_and_app_guide_cover_every_area(self):
        c, uid = self.onboarded("lookup")
        c.req("POST", "/api/moment", {"action": "add", "text": "楼下的猫冲我叫了一声"})
        from core import agent, lookup, guide
        with Store(uid) as st:
            for area in lookup.AREAS:
                out = agent.run_tool(st, "look_up", {"area": area}, "看看")
                self.assertTrue(out["ok"] and out["text"], area)
            self.assertIn("楼下的猫", agent.run_tool(st, "look_up", {"area": "moments"})["text"])
            self.assertIn("健康作息", agent.run_tool(st, "look_up", {"area": "plan"})["text"])
            for t in guide.TOPICS:
                self.assertTrue(agent.run_tool(st, "app_guide", {"topic": t})["text"])
            self.assertEqual(guide.guide("里程碑怎么删")["topic"], "plan")
            prompt = agent.system_prompt(st, [])
            self.assertIn("瞬间", prompt)
            self.assertNotIn("log_good_news", prompt)
            self.assertIn("look_up", prompt)
            self.assertIn("小镇", prompt)
            self.assertNotIn("宠物「", prompt)
            g = agent.run_tool(st, "get_growth", {}, "我能建什么")
            self.assertTrue(g["ok"] and "coins" in g["growth"] and g["growth"]["town"]["land"] == "5×5")

    def test_moments_tasks_settings_and_lazy_undo_via_agent(self):
        c, uid = self.onboarded("misc_tools")
        from core import agent, journey
        with Store(uid) as st:
            # TA 明确让小光记下：不挂愿望；说了愿望就挂上；改、删也行
            first = agent.run_tool(st, "edit_plan", {"action": "add", "kind": "moment", "text": "开会时脑子里在想晚饭"}, "帮我把这个记下来")
            self.assertTrue(first["ok"] and first["new_moment"], first)
            self.assertEqual(st.c.execute("SELECT wish_id FROM moment WHERE id=?", (first["id"],)).fetchone()[0], "")
            agent.run_tool(st, "edit_plan", {"action": "add", "kind": "moment", "text": "喝到一杯好喝的拿铁"}, "帮我记下来")
            out = agent.run_tool(st, "edit_plan", {"action": "change", "kind": "moment", "target": "拿铁", "text": "喝到一杯超好喝的燕麦拿铁"}, "改一下")
            self.assertTrue(out["ok"], out)
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "moment", "target": "晚饭"}, "删掉")["ok"])
            texts = [m["text"] for m in journey.moments(st)]
            self.assertIn("喝到一杯超好喝的燕麦拿铁", texts)
            self.assertNotIn("开会时脑子里在想晚饭", texts)
            # 没有愿望也能提议瞬间（以前必须先有愿望）
            p = agent.run_tool(st, "propose_moment", {"text": "今天自己做了一顿饭"})
            self.assertEqual((p["ok"], p["proposal"]["wish_id"]), (True, ""))

            agent.run_tool(st, "schedule_task", {"title": "早安鼓励", "kind": "ai", "repeat": "daily", "time": "08:30"})
            self.assertTrue(agent.run_tool(st, "edit_task", {"target": "早安", "action": "off"}, "先关掉")["ok"])
            self.assertTrue(agent.run_tool(st, "edit_task", {"target": "早安", "action": "on"}, "打开吧")["ok"])
            ch = agent.run_tool(st, "edit_task", {"target": "早安", "action": "change", "time": "09:00"}, "改到九点")
            self.assertIn("09:00", ch["done"])
            self.assertTrue(agent.run_tool(st, "edit_task", {"target": "早安", "action": "delete"}, "删了")["ok"])
            self.assertEqual(tasks.list_for(uid), [])

            s_ = agent.run_tool(st, "update_settings", {"proactive": "more", "persona": "lively", "nickname": "小鱼"}, "多督促我")
            self.assertTrue(s_["ok"], s_)
            p = st.profile()
            self.assertEqual((p["proactive"], p["persona"], p["nickname"]), ("more", "lively", "小鱼"))
            self.assertFalse(agent.run_tool(st, "update_settings", {"theme": "neon"}, "换个主题")["ok"])

            agent.run_tool(st, "log_lazy_day", {})
            self.assertTrue(journey.is_resting(st))
            self.assertTrue(agent.run_tool(st, "log_lazy_day", {"undo": True}, "不偷懒了")["ok"])
            self.assertFalse(journey.is_resting(st))

    def test_attention_drives_chat_context_and_proactive_cues(self):
        from datetime import date, timedelta
        c, uid = self.onboarded("nudges")
        _, d = c.req("GET", "/api/bootstrap")
        wid = d["journey"]["current"]
        today = date.fromisoformat(d["journey"]["today"])
        c.req("POST", "/api/milestone", {"action": "add", "wish_id": wid, "title": "连续一周 12 点前睡",
                                          "due_day": (today + timedelta(days=2)).isoformat()})
        c.req("POST", "/api/milestone", {"action": "add", "wish_id": wid, "title": "戒掉睡前刷手机",
                                          "due_day": (today - timedelta(days=3)).isoformat()})
        from core import agent, nudges
        with Store(uid) as st:
            kinds = [x["kind"] for x in nudges.attention(st)]
            self.assertIn("milestone_due", kinds)
            self.assertIn("milestone_overdue", kinds)
            note = agent.context_note([], st)
            self.assertIn("连续一周 12 点前睡", note)
            self.assertIn("戒掉睡前刷手机", agent.run_tool(st, "look_up", {"area": "attention"})["text"])
            cue = scheduler.pick_cue(st)
            self.assertIn(cue["cue"], ("milestone_due", "milestone_overdue"))
            self.assertTrue(cue["fact"])
            st.add_record("rest", "今天偷个懒")
            self.assertNotIn("可以顺手提的事", agent.context_note([], st))   # 偷懒日什么都不提


    def test_ids_with_brackets_and_dropped_streams(self):
        from core import journey
        items = [{"id": "r_2ac0bb9e3216", "title": "喝到一杯燕麦拿铁"}, {"id": "w_1a2b3c4d5e6f", "title": "早睡早起"}]
        self.assertEqual(journey._pick(items, "[r_2ac0bb9e3216]")["title"], "喝到一杯燕麦拿铁")
        self.assertEqual(journey._pick(items, "[w_1a2b3c4d5e6f] 早睡早起")["title"], "早睡早起")

        def broken():
            yield b"data: {}"
            raise ConnectionResetError("peer reset")
        with self.assertRaises(llm.LLMError):
            list(llm._lines(broken()))

        c, uid = self.onboarded("dropped")

        def half(messages, tools=None, **kw):
            yield ("text", "嗯，先把明天要穿的衣服")
            raise llm.LLMError("stream interrupted: ConnectionResetError")
        orig, llm.stream_chat = llm.stream_chat, half
        try:
            s, ev = c.sse("今天不知道干啥")
        finally:
            llm.stream_chat = orig
        self.assertTrue(any(e == "error" for e, _ in ev))
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["messages"][-1]["content"], "嗯，先把明天要穿的衣服")   # 半句也存下了


    def test_push_back_moves_from_the_current_date_and_noop_is_quiet(self):
        """「往后推两周」要在原来的日子上加 14 天（线上实测曾被算成从今天起两周，反而提前了）。"""
        c, uid = self.onboarded("shift")
        from datetime import date, timedelta
        target = (date.today() + timedelta(days=26)).isoformat()
        c.req("POST", "/api/wish", {"action": "add", "title": "早睡早起", "category": "body", "target_day": target})
        self.fake.turns = [[("tool_calls", [{"id": "s1", "name": "edit_plan", "arguments": json.dumps(
                               {"kind": "wish", "target": "早睡早起", "shift_days": 14})}])],
                           [("text", "往后推了两周。")],
                           [("tool_calls", [{"id": "s2", "name": "edit_plan", "arguments": json.dumps(
                               {"kind": "wish", "target": "早睡早起", "due_day": (date.today() + timedelta(days=40)).isoformat()})}])],
                           [("text", "嗯，就是这天。")]]
        s, ev = c.sse("早睡早起的计划日期往后推两周吧")
        self.assertTrue(self._tool_events(ev, "edit_plan")[0]["result"]["ok"])
        _, d = c.req("GET", "/api/bootstrap")
        w = next(x for x in d["journey"]["wishes"] if x["title"] == "早睡早起")
        self.assertEqual(w["target_day"], (date.today() + timedelta(days=40)).isoformat())
        s, ev = c.sse("改到那天对吧")
        self.assertFalse(self._tool_events(ev, "edit_plan"))      # 已经是这样了：不出「没成功」的卡片


    # ---- 2026-11-11 交付前审查：每一条都是先复现、再修好的缺陷 -------------------------------
    def test_archiving_the_only_wish_does_not_bring_it_back(self):
        """收起唯一的愿望，下一次打开不能照建档时的说法又长出一个同名的。"""
        c, uid = self.onboarded("rv_onlywish")
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual([w["title"] for w in d["journey"]["wishes"]], ["健康作息"])
        wid = d["journey"]["wishes"][0]["id"]
        _, d = c.req("POST", "/api/wish", {"action": "edit", "id": wid, "archived": True})
        self.assertEqual(d["journey"]["wishes"], [])
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["journey"]["wishes"], [])
        with Store(uid) as st:
            from core import agent, journey
            self.assertEqual(len(journey.wishes(st, include_archived=True)), 1)       # 还是原来那一个，只是收起了
            self.assertIsNone(journey.current(st))
            self.assertIn("TA 还没有愿望", agent.core_block(st.profile(), st))
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "restore", "kind": "wish", "target": "健康作息"}, "把健康作息找回来")["ok"])
            self.assertEqual([w["id"] for w in journey.wishes(st)], [wid])

    def test_bad_tool_arguments_do_not_break_the_turn(self):
        """模型把参数类型写错（名字写成数组、星期写成数字）：这一轮照样有回复、照样存下来，下一轮还能聊。"""
        c, uid = self.onboarded("rv_badargs")
        c.req("POST", "/api/step", {"action": "add", "title": "读两页书"})
        for name, args, said in (("complete_step", {"step_id": 12, "title": ["读两页书"]}, "读两页书做完了"),
                                 ("start_scene", {"scene": ["meditation"]}, "我想冥想"),
                                 ("schedule_task", {"title": "喝水", "kind": "remind", "repeat": "weekly", "time": "9:5", "days": 3}, "每周三九点零五提醒我喝水")):
            self.fake.turns = [[("tool_calls", [{"id": "b1", "name": name, "arguments": json.dumps(args)}])], [("text", "好。")]]
            s, ev = c.sse(said)
            self.assertEqual(s, 200)
            self.assertTrue([d for e, d in ev if e == "done"], name)                  # 这一轮正常收尾
            self.assertEqual("".join(d["text"] for e, d in ev if e == "delta"), "好。", name)
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual([m["role"] for m in d["messages"]][-6:], ["user", "assistant"] * 3)
        t = next(t for t in d["tasks"] if t["title"] == "喝水")
        self.assertEqual((t["time"], t["days"], t["when"]), ("09:05", "3", "每周周三 09:05"))   # 时间写整齐，单个数字也算星期
        # 工具自己出了意外：模型拿到「没办成」的回执（不是整轮崩掉），界面上不出回执
        from core import agent
        orig = agent.run_tool
        agent.run_tool = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            self.fake.turns = [[("tool_calls", [{"id": "b2", "name": "add_step", "arguments": json.dumps({"title": "x"})}])],
                               [("text", "刚才没加上，我再试试？")]]
            s, ev = c.sse("帮我加一个小步")
        finally:
            agent.run_tool = orig
        tool_msg = next(m for m in self.fake.seen[-1] if m["role"] == "tool")
        self.assertIn('"ok": false', tool_msg["content"])
        self.assertEqual(self._tool_events(ev, "add_step")[0]["acts"], [])
        self.assertTrue([d for e, d in ev if e == "done"])

    def test_a_turn_never_ends_without_words(self):
        """模型调完工具却一个字没说：先再要一次；还是不说，就照真实做了的事给一句最短的话。存下来的不能是空消息。"""
        c, uid = self.onboarded("rv_silent")
        from core import agent
        self.fake.turns = [[("tool_calls", [{"id": "s1", "name": "log_lazy_day", "arguments": "{}"}])], [], [("text", "偷懒日已设置。")]]
        s, ev = c.sse("今天想躺平")
        self.assertEqual("".join(d["text"] for e, d in ev if e == "delta"), "偷懒日已设置。")
        self.assertEqual(self.fake.seen[-1][-1], {"role": "system", "content": agent.SPEAK_UP})
        c.req("POST", "/api/record", {"type": "rest", "undo": True})
        self.fake.turns = [[("tool_calls", [{"id": "s2", "name": "log_lazy_day", "arguments": "{}"}])], [], []]
        s, ev = c.sse("今天想躺平")
        _, d = c.req("GET", "/api/bootstrap")
        last = d["messages"][-1]
        self.assertEqual((last["role"], last["content"]), ("assistant", "弄好了，在下面。"))
        self.assertIn("今天偷个懒", [a.get("verb") for a in last["meta"]["acts"]])
        self.fake.turns = [[], []]                                                    # 什么都没做也没说
        s, ev = c.sse("在吗")
        self.assertEqual("".join(d["text"] for e, d in ev if e == "delta"), "嗯，我在。你接着说。")

    def test_removing_without_a_clear_target_asks_first(self):
        """「把那个愿望删了吧」「把背单词那个习惯删了」：对象不清楚，不替 TA 挑一个动手。"""
        c, uid = self.onboarded("rv_vague")
        with Store(uid) as st:
            from core import agent, journey
            w = journey.current(st)
            journey.add_wish(st, "学吉他", "other")
            out = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "wish"}, "把那个愿望删了吧")
            self.assertFalse(out["ok"])
            self.assertEqual(sorted(out["have"]), ["健康作息", "学吉他"])
            self.assertEqual(len(journey.wishes(st)), 2)
            journey.add_habit(st, w["id"], "每天背20个单词", "daily")
            journey.add_habit(st, w["id"], "睡前背单词", "daily")
            journey.add_habit(st, w["id"], "晨跑", "daily")
            out = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "habit", "target": "背单词"}, "把背单词那个习惯删了")
            self.assertTrue(out.get("ambiguous"), out)
            self.assertEqual(sorted(out["have"]), ["每天背20个单词", "睡前背单词"])
            self.assertEqual(len(journey.habits(st)), 3)
            pick = next(h for h in journey.habits(st) if h["title"] == "每天背20个单词")
            for target in (pick["id"], "每天背20个单词"):                # 模型自己挑了一个、填上准确的 id 或名字：照样拦下
                out = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "habit", "target": target}, "把背单词那个习惯删了吧")
                self.assertTrue(out.get("ambiguous"), out)
                self.assertEqual(sorted(out["have"]), ["每天背20个单词", "睡前背单词"])
            out = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "habit", "target": pick["id"]}, "那个早上的习惯不要了")
            self.assertTrue(out.get("ambiguous"), out)                                # TA 这句话没点到任何一个
            wid = next(x["id"] for x in journey.wishes(st) if x["title"] == "学吉他")
            out = agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "wish", "target": wid}, "把那个愿望删了吧")
            self.assertTrue(out.get("ambiguous"), out)
            self.assertEqual(len(journey.habits(st)), 3)
            # 小光上一句刚提议过这一项，TA 说「删吧」：是在回应提议，直接做
            st.add_msg("assistant", "要不留下「每天背20个单词」，把「晨跑」先收起来？")
            self.assertIsNone(journey.unnamed_removal(st, "habit", "晨跑", "删吧", "要不留下「每天背20个单词」，把「晨跑」先收起来？"))
            self.assertIsNone(journey.unnamed_removal(st, "habit", "晨跑", "把这几个习惯都删了"))       # 说了「都」
            out = agent.run_tool(st, "edit_plan", {"action": "change", "kind": "habit", "target": "背单词", "freq": "weekly", "per_week": 3},
                                 "背单词改成每周三次")
            self.assertTrue(out.get("ambiguous"), out)                                # 改也一样：不知道是哪个就先问
            # 点了名的（完整名字、id、只对得上一个的说法）照旧利落地做
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "habit", "target": "睡前背单词"}, "把睡前背单词删了")["ok"])
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "habit", "target": "跑"}, "把晨跑收起来")["ok"])
            hid = journey.habits(st)[0]["id"]
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "habit", "target": f"[{hid}] 每天背20个单词"}, "删掉")["ok"])
            self.assertEqual(journey.habits(st), [])
            # 只有一个愿望时，「把愿望收起来」对象是清楚的
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "wish", "target": "学吉他"}, "把学吉他收起来")["ok"])
            self.assertTrue(agent.run_tool(st, "edit_plan", {"action": "remove", "kind": "wish"}, "把愿望收起来吧")["ok"])
            self.assertEqual(journey.wishes(st), [])

    def test_forgotten_memory_is_gone_from_notebook_prompt_and_digest(self):
        """「忘掉」要真的生效：笔记本里的那半句拿掉、提示里明说别再提、夜里整理不从当天的对话里再记回来。"""
        c, uid = self.onboarded("rv_forget")
        from core import agent, digest, memory
        with Store(uid) as st:
            m = st.add_memory("喜欢吃寿司", "preference", "chat:explicit")
            k = st.add_memory("室友叫阿琪", "identity", "chat:explicit")
            st.set_profile({"notebook": {"text": "最近的生活：喜欢吃寿司，常去学校旁边那家；宿舍新养了只橘猫叫土豆。\n在意的人：室友阿琪", "by": "digest"}})
            self.assertIn("寿司", agent.system_prompt(st, []))
        s, d = c.req("POST", "/api/memory", {"action": "forget", "id": m["id"]})
        self.assertEqual(s, 200)
        self.assertEqual(d["profile"]["notebook"]["text"], "最近的生活：宿舍新养了只橘猫叫土豆。\n在意的人：室友阿琪")
        with Store(uid) as st:
            note = agent.context_note([], st)                       # 放在离 TA 这句话最近的那条系统消息里
            self.assertIn("TA 亲手让你忘掉、或者更正过的", note)
            self.assertIn("「喜欢吃寿司」（TA 让你忘掉了）", note)
            self.assertFalse("寿司" in agent.system_prompt(st, []).split("## 你的笔记本")[-1])   # 笔记本里那半句已经拿掉
            # 当天聊天里还有这句话，模型想把它记回去、写回笔记本：都拦下
            st.add_msg("user", "中午又去吃了寿司")
            self.fake.json_out = {"summary": "s", "highlights": [], "portrait": "",
                                  "notebook": "最近的生活：喜欢吃寿司；宿舍新养了只橘猫叫土豆。\n在意的人：室友阿琪",
                                  "ops": [{"op": "ADD", "text": "喜欢吃寿司", "kind": "preference", "source": "said"},
                                          {"op": "ADD", "text": "中午常去吃日料", "kind": "preference", "source": "said"}]}
            out = digest.run(st)
            self.assertIn({"op": "ADD", "text": "喜欢吃寿司", "why": "user forgot this"}, out["rejected"])
            self.assertEqual([o["text"] for o in out["ops"]], ["中午常去吃日料"])
            self.assertIn("TA 亲手删掉或更正过的", self.fake.seen_json[-1][1]["content"])
            self.assertNotIn("喜欢吃寿司", st.profile()["notebook"]["text"])
            self.assertNotIn("喜欢吃寿司", [x["text"] for x in st.memories()])
        # 更正：旧说法从笔记本拿掉，提示里写「旧 → 新」
        s, d = c.req("POST", "/api/memory", {"action": "edit", "id": k["id"], "text": "室友叫小琪，不叫阿琪"})
        self.assertNotIn("室友阿琪", d["profile"]["notebook"]["text"])
        with Store(uid) as st:
            self.assertIn("「室友叫阿琪」 → 现在是「室友叫小琪，不叫阿琪」", agent.context_note([], st))
            # TA 自己又把它加回来了：不再算「忘掉的」
            st.add_memory("喜欢吃寿司", "preference", "confirmed")
            self.assertNotIn("喜欢吃寿司", [f["old"] for f in memory.forgotten(st)])
            # 聊天里更正（correct_memory）也一样清笔记本
            st.add_memory("交换的学校在英国", "identity", "chat:explicit")
            st.set_profile({"notebook": {"text": "正在努力的事：准备交换；交换的学校在英国", "by": "digest"}})
            out = agent.run_tool(st, "correct_memory", {"about": "交换学校 英国", "new_text": "交换的学校换成澳洲了", "quote": "交换的学校换成澳洲了"},
                                 "交换的学校换成澳洲了")
            self.assertTrue(out["ok"], out)
            self.assertEqual(st.profile()["notebook"]["text"], "正在努力的事：准备交换")
        self.assertEqual(memory.scrub_text("最近的生活：养了只猫", "猫"), "最近的生活：养了只猫")       # 太短的不拿来删，免得误伤

    def test_habit_checkin_counts_once_per_day_however_the_day_is_written(self):
        """打卡的奖励按「习惯 + 这一天」只算一次；同一天换个写法（多个空格、带时间）不能再拿一次。"""
        c, uid = self.onboarded("rv_habitxp")
        _, d = c.req("GET", "/api/bootstrap")
        _, d = c.req("POST", "/api/habit", {"action": "add", "wish_id": d["journey"]["current"], "title": "散步", "freq": "daily"})
        hid = d["habit"]["id"]
        today = d["journey"]["today"]
        got = []
        for day in (None, today, today + " ", today + "T08:00", today + "x"):
            s, d = c.req("POST", "/api/habit", {"action": "check", "id": hid, "day": day})
            self.assertEqual(s, 200, d)
            got.append((d.get("xp") or {}).get("amount", 0))
            c.req("POST", "/api/habit", {"action": "uncheck", "id": hid, "day": day})
        self.assertEqual(got, [10, 0, 0, 0, 0])
        with Store(uid) as st:
            self.assertEqual([r[0] for r in st.c.execute("SELECT ref FROM xp WHERE source='action'")], [f"habit:{hid}:{today}"])

    def test_manual_digest_today_does_not_skip_tonight(self):
        """白天手动整理了今天，夜里还要再整理一遍今天（不然后半天说的话永远不会被整理）。"""
        from datetime import timedelta
        from core import digest
        from core.util import now
        c, uid = self.onboarded("rv_digest")
        with Store(uid) as st:
            st.add_msg("user", "上午：我想学吉他")
            self.fake.json_out = {"summary": "s", "highlights": [], "notebook": "", "portrait": "", "ops": []}
            out = digest.run(st)
            self.assertFalse(out.get("skipped"))
            st.add_msg("user", "晚上：报了周六的吉他课")
            tomorrow = (now() + timedelta(days=1)).replace(hour=3, minute=5)
            self.assertEqual(digest.due(st, tomorrow), out["day"])
            digest.run(st, out["day"])                      # 这是「昨天」的整理了：还没过完的今天不记号
            self.assertEqual(st.profile()["last_digest_day"], "")
            yday = (now() - timedelta(days=1)).strftime("%Y-%m-%d")
            st.add_msg("user", "昨天说的话", at=yday + "T20:00:00+08:00")
            digest.run(st, yday)
            self.assertEqual(st.profile()["last_digest_day"], yday)

    def test_finds_wait_a_few_days_between_runs(self):
        """「小光的发现」隔几天写一次：上次写的时间要真的存下来（以前存不进去，每晚都会再调一次模型）。"""
        from core import finds
        c, uid = self.onboarded("rv_finds")
        with Store(uid) as st:
            st.set_profile({"created_at": "2026-01-01T08:00:00+08:00"})
            self.assertTrue(finds.due(st))
            self.fake.json_out = {"finds": []}
            n = len(self.fake.seen_json)
            finds.discover(st, force=True)
            self.assertEqual(len(self.fake.seen_json), n + 1)
            self.assertTrue(st.profile()["finds_at"])
            self.assertFalse(finds.due(st))
            self.assertEqual(finds.discover(st), [])
            self.assertEqual(len(self.fake.seen_json), n + 1)                         # 没到日子：不再调模型

    def test_rate_limits_ignore_a_spoofed_forwarded_for(self):
        """X-Forwarded-For 最前面那段是来访者自己写的：换着写不能绕过限流；只认离我们最近的代理填的那一段。"""
        c = Client(self.port)
        codes = []
        for i in range(10):
            s, _ = c.req("POST", "/api/auth/login", {"username": f"rv_nobody{i}", "password": "wrongpass"},
                         headers={"X-Forwarded-For": f"10.9.{i}.1, 203.0.113.77"})
            codes.append(s)
        self.assertEqual(codes, [401] * 8 + [429] * 2)
        s, _ = c.req("POST", "/api/auth/login", {"username": "rv_nobody_x", "password": "wrongpass"},
                     headers={"X-Forwarded-For": "203.0.113.77, 198.51.100.5"})        # 另一个真实来源不受影响
        self.assertEqual(s, 401)

    def test_profile_and_insight_reject_malformed_values(self):
        c, uid = self.onboarded("rv_profile")
        self.assertEqual(c.req("POST", "/api/profile", {"nickname": {"a": 1}})[0], 400)
        self.assertEqual(c.req("POST", "/api/profile", {"schedule_hint": ["x"] * 50})[0], 400)
        self.assertEqual(c.req("POST", "/api/profile", {"pace": "warp"})[0], 400)
        s, d = c.req("POST", "/api/profile", {"nickname": "小周", "pace": "steady"})
        self.assertEqual((s, d["profile"]["nickname"], d["profile"]["pace"]), (200, "小周", "steady"))
        self.assertEqual(c.req("POST", "/api/insight", {"id": "x" * 5000, "fb": "no"})[0], 404)
        s, d = c.req("POST", "/api/insight", {"id": "energy", "fb": "no"})
        self.assertEqual((s, d["profile"]["insight_fb"]), (200, {"energy": "no"}))
        self.fake.turns = [[("text", "嗯。")]]
        s, ev = c.sse("在吗")                                                          # 画像没被弄坏，对话照常
        self.assertTrue([d for e, d in ev if e == "done"])

    def test_photo_shared_by_two_moments_survives_deleting_one(self):
        c, uid = self.member("rv_photo")
        _, out = self._photo(c, "jpg")
        pid = out["photo"]
        _, a = c.req("POST", "/api/moment", {"action": "add", "text": "晚霞", "photo": pid})
        _, b = c.req("POST", "/api/moment", {"action": "add", "text": "还是晚霞", "photo": pid})
        c.req("POST", "/api/moment", {"action": "delete", "id": a["moment"]["id"]})
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid}")[0], 200)          # 另一个瞬间还挂着它
        c.req("POST", "/api/moment", {"action": "delete", "id": b["moment"]["id"]})
        self.assertEqual(self._get_bytes(c, f"/api/photo?id={pid}")[0], 404)

    def test_discarding_a_flow_drops_its_computed_ending(self):
        """「显化你的愿望」答完不存：算好的小纸条（profile.flow_end）也不留。"""
        c, uid = self.onboarded("rv_flow")
        with Store(uid) as st:
            run = st.start_scene("relearn")
            st.update_scene(run["id"], 1, [{"state": "累"}], "done")
            st.set_profile({"flow_end": {"run": run["id"], "key": "k", "end": {"say": "看到的你"}}})
        self.assertEqual(c.req("POST", "/api/scene/discard", {"run_id": run["id"]})[0], 200)
        with Store(uid) as st:
            self.assertEqual(st.profile()["flow_end"], {})
            self.assertEqual(st.get_scene(run["id"])["answers"], [])


    def test_static_files_revalidate_with_etag(self):
        """页面、脚本、样式每次打开都会问有没有新版本：没变就回 304、不带内容，不用整份重下。"""
        for path in ("/", "/js/app.js", "/css/base.css", "/js/buildings/all.js"):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            c.request("GET", path)
            r = c.getresponse()
            body = r.read()
            etag = r.getheader("ETag")
            self.assertEqual(r.status, 200, path)
            self.assertTrue(etag and len(body) > 100, path)
            self.assertEqual(r.getheader("Cache-Control"), "no-cache", path)
            c.request("GET", path, headers={"If-None-Match": etag})      # 同一条连接接着用：304 不能把连接弄坏
            r = c.getresponse()
            self.assertEqual((r.status, r.read(), r.getheader("ETag")), (304, b"", etag), path)
            c.request("GET", path, headers={"If-None-Match": '"old", W/' + etag})   # nginx 压缩后会改成弱校验，也认
            r = c.getresponse()
            self.assertEqual((r.status, r.read()), (304, b""), path)
            c.request("GET", path, headers={"If-None-Match": '"stale"'})
            r = c.getresponse()
            self.assertEqual((r.status, r.read()), (200, body), path)
            c.close()
        # 按段取音频时不走 304（iPhone 放音频靠 Range）
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/audio/meditation.mp3", headers={"Range": "bytes=0-9"})
        r = c.getresponse()
        etag = r.getheader("ETag")
        self.assertEqual((r.status, len(r.read())), (206, 10))
        c.request("GET", "/audio/meditation.mp3", headers={"Range": "bytes=0-9", "If-None-Match": etag})
        r = c.getresponse()
        self.assertEqual((r.status, len(r.read())), (206, 10))
        c.close()


    def test_abandoned_kickstart_is_wiped_and_orphan_folders_are_skipped(self):
        """两分钟启动做到一半直接关了页面：过了 6 小时就和中途关掉一样，什么都不留。
        账号删了、文件夹还在：后台不替一个不存在的人整理记忆、发消息。"""
        from core import scheduler
        c, uid = self.onboarded("rv_kick")
        self.fake.json_out = {"say": "从最小的开始。", "cheer": "开始了。", "steps": [
            {"title": "打开文档", "tip": "只打开，不写。", "minutes": 1}, {"title": "写一行", "tip": "随便写。", "minutes": 1},
            {"title": "再写一行", "tip": "接着写。", "minutes": 1}]}
        run = self._kick(c, "start", task="写论文的引言", mode="low")["run"]
        self.assertTrue(c.req("GET", "/api/kick")[1]["active"])                       # 刚开始：能接着做
        with Store(uid) as st:
            st.c.execute("UPDATE kick_run SET updated_at='2026-01-01T08:00:00+08:00' WHERE id=?", (run["id"],))
        self.assertIsNone(c.req("GET", "/api/kick")[1]["active"])
        with Store(uid) as st:
            row = st.c.execute("SELECT status, route, say FROM kick_run WHERE id=?", (run["id"],)).fetchone()
            self.assertEqual((row["status"], row["say"]), ("closed", ""))
            self.assertNotIn("打开文档", row["route"])
        ghost = "u_" + "0" * 16                       # 没有账号的文件夹
        with Store(ghost) as st:
            st.set_profile({"onboarded": True, "proactive": "more"})
            st.add_msg("user", "昨天说的话", at="2026-01-01T20:00:00+08:00")
        n = len(self.fake.seen_json)
        orig = scheduler.deliver
        seen = []
        scheduler.deliver = lambda st, force=False: (seen.append(st.uid), {"sent": False})[1]
        try:
            scheduler.tick()
        finally:
            scheduler.deliver = orig
        self.assertIn(uid, seen)
        self.assertNotIn(ghost, seen)
        with Store(ghost) as st:
            self.assertEqual(st.digests(3), [])
        shutil.rmtree(os.path.join(TMP, "u", ghost), ignore_errors=True)


    def test_router_leaves_moment_proposals_to_the_chat_and_saves_on_yes(self):
        """「提议留成一个瞬间」是小光自己的主意，路由不再强制它；小光刚问过、TA 说好，就是存下（不再弹第二张提议卡）。"""
        from core import router
        self.assertNotIn("propose_moment", router.ACTIONS)
        c, uid = self.onboarded("rv_router")
        with Store(uid) as st:
            self.fake.json_out = {"tool": "propose_moment"}                    # 模型硬要判成它：不认
            self.assertEqual(router.decide(router.context(st), "今天食堂的糖醋排骨居然没卖完，我抢到了最后一份！"), "")
            st.add_msg("user", "今天在英语课上第一次举手发言了，手都在抖")
            st.add_msg("assistant", "手抖着也举起来了，这一下真的不容易。要不要把它留成一个瞬间？")
            ctx = router.context(st)
            self.assertTrue(ctx["moment_asked"])
            n = len(self.fake.seen_json)
            self.assertEqual(router.decide(ctx, "好呀，留着吧"), "edit_plan")
            self.assertEqual(len(self.fake.seen_json), n)                       # 不用再问模型
            self.fake.json_out = {"tool": ""}
            self.assertEqual(router.decide(ctx, "不用啦"), "")
            self.fake.json_out = {"tool": "checkin_habit"}
            self.assertEqual(router.decide(ctx, "对了我今天还去跑步了"), "")     # 没有习惯：不逼着去打一个不存在的卡

    def test_history_drops_what_the_user_asked_to_forget(self):
        """TA 亲手忘掉的事：之前的对话里说到它的那句不再带进上下文；忘掉之后 TA 自己又说起的照旧带上。"""
        from core import agent
        c, uid = self.onboarded("rv_hist")
        with Store(uid) as st:
            st.add_msg("user", "我最喜欢吃寿司了，每周都想去", at="2026-01-05T12:00:00+08:00")
            st.add_msg("assistant", "那你肯定有一家心里的第一名吧～", at="2026-01-05T12:00:05+08:00")
            st.add_msg("user", "有，学校旁边那家", at="2026-01-05T12:01:00+08:00")
            m = st.add_memory("最喜欢吃寿司", "preference", "chat:explicit")
            said = lambda: [x["content"] for x in agent.history(st) if x["role"] == "user"]
            self.assertTrue(any("寿司" in t for t in said()))
        self.assertEqual(c.req("POST", "/api/memory", {"action": "forget", "id": m["id"]})[0], 200)
        with Store(uid) as st:
            self.assertFalse(any("寿司" in t for t in said()))
            self.assertTrue(any("学校旁边那家" in t for t in said()))            # 别的话都在
            st.add_msg("user", "今天又想吃寿司了")
            self.assertTrue(any("今天又想吃寿司了" in t for t in said()))        # 忘掉之后自己又说起：照 TA 现在说的来


    def test_asking_to_keep_a_moment_always_shows_the_card(self):
        """小光嘴上问了「要不要留成一个瞬间」却没调工具：补上那张「留下」的卡片（内容是 TA 自己的话）；只是讲到这个功能时不补。"""
        c, uid = self.onboarded("rv_ask_moment")
        said = "刚才小组讨论我第一个用英语发言了，手心全是汗，但说完感觉好爽"
        self.fake.turns = [[("text", "第一个开口诶，这一步可不小。要不要把这个留成一个瞬间？")]]
        s, ev = c.sse(said)
        card = self._tool_events(ev, "propose_moment")
        self.assertEqual(len(card), 1)
        self.assertEqual((card[0]["acts"][0]["ask"], card[0]["acts"][0]["text"], card[0]["acts"][0]["state"]), ("moment", said, ""))
        _, d = c.req("GET", "/api/bootstrap")
        self.assertEqual(d["messages"][-1]["meta"]["acts"][-1]["ask"], "moment")       # 存进了这条回复，翻回去看还在
        self.assertEqual(d["journey"]["moments"], [])                                   # 只是提议，没点「留下」不会存
        # 模型自己调了 propose_moment：不重复出卡
        self.fake.turns = [[("tool_calls", [{"id": "p1", "name": "propose_moment", "arguments": json.dumps({"text": "第一次举手发言"})}])],
                           [("text", "要不要把它留成一个瞬间？")]]
        s, ev = c.sse("今天在英语课上第一次举手发言了，手都在抖")
        self.assertEqual(len(self._tool_events(ev, "propose_moment")), 1)
        # 只是在讲「瞬间」这个功能、或者 TA 只回了一两个字：不出卡
        self.fake.turns = [[("text", "瞬间页右上角点「留下一个瞬间」，就能把一件事留成一个瞬间啦。")]]
        s, ev = c.sse("瞬间这个功能怎么用呀，在哪里")
        self.assertEqual(self._tool_events(ev, "propose_moment"), [])
        self.fake.turns = [[("text", "嗯嗯。要不要把刚才那件事留成一个瞬间？")]]
        s, ev = c.sse("嗯")
        self.assertEqual(self._tool_events(ev, "propose_moment"), [])


class MemoryTest(unittest.TestCase):
    """记忆读写（2026-11-07）：写之前查重（mem0 的 ADD / UPDATE / NOOP），要点一直放在提示里（Letta 的 core block）。"""

    def setUp(self):
        from core import agent
        self.agent = agent
        self.st = Store("u_" + os.urandom(8).hex())
        self.st.add_memory("不吃香菜", "preference", "chat:explicit")
        self.st.add_memory("喜欢吃寿司", "preference", "onboarding")

    def test_remember_does_not_duplicate(self):
        r = self.agent.run_tool(self.st, "remember", {"text": "不吃香菜", "kind": "preference"}, "你记一下，我不吃香菜")
        self.assertTrue(r["ok"])
        self.assertEqual(sum(1 for m in self.st.memories() if "香菜" in m["text"]), 1)

    def test_correct_keeps_revision(self):
        r = self.agent.run_tool(self.st, "correct_memory", {"about": "寿司", "new_text": "以前喜欢寿司，现在吃腻了", "quote": "不喜欢寿司了"},
                                "我现在不喜欢寿司了")
        self.assertTrue(r["ok"])
        self.assertEqual(r["old"], "喜欢吃寿司")
        self.assertTrue(self.st.c.execute("SELECT 1 FROM memory_rev WHERE old_text='喜欢吃寿司'").fetchone())

    def test_pinned_in_prompt_and_search_fallback(self):
        prompt = self.agent.system_prompt(self.st, [])
        self.assertIn("不吃香菜", prompt)
        self.assertEqual(self.st.search("晚饭吃什么"), [])
        self.assertTrue(self.st.search("晚饭吃什么", fallback=True))


class ActsTest(unittest.TestCase):
    """聊天里的统一展示（core/acts.py）：回执写出旧 → 新，撤销只认存在消息里的那份改动。"""

    def setUp(self):
        from core import acts, agent, journey
        self.acts, self.agent = acts, agent
        self.st = Store("u_" + os.urandom(8).hex())
        w = journey.add_wish(self.st, "敢开口说英语", "")
        self.st.add_step("在小组里主动提一个问题", wish_id=w["id"])

    def _do(self, name, args, text):
        snap = self.acts.before(self.st, name, args)
        return self.acts.view(self.st, name, args, self.agent.run_tool(self.st, name, args, text), snap)

    def test_rename_shows_before_after_and_undoes(self):
        v = self._do("edit_plan", {"action": "change", "kind": "step", "target": "小组", "title": "在课上主动提一个问题"}, "把它改成课上提问")
        self.assertEqual((v[0]["old"], v[0]["new"]), ("在小组里主动提一个问题", "在课上主动提一个问题"))
        m = self.st.add_msg("assistant", "改好啦", {"acts": v})
        self.assertTrue(self.acts.set_state(self.st, m["id"], 0, "", do_undo=True)["ok"])
        self.assertEqual(self.st.c.execute("SELECT title FROM step").fetchone()[0], "在小组里主动提一个问题")
        self.assertFalse(self.acts.set_state(self.st, m["id"], 0, "", do_undo=True)["ok"])     # 不能撤两次

    def test_undo_refuses_after_later_edit(self):
        v = self._do("edit_plan", {"action": "change", "kind": "step", "target": "小组", "title": "A"}, "改成 A")
        m = self.st.add_msg("assistant", "好", {"acts": v})
        self._do("edit_plan", {"action": "change", "kind": "step", "target": "A", "title": "B"}, "再改成 B")
        self.assertFalse(self.acts.set_state(self.st, m["id"], 0, "", do_undo=True)["ok"])

    def test_agent_schedules_steps_and_lazy_day_undo_brings_them_back(self):
        from datetime import date, timedelta
        from core import journey
        from core.util import day_key
        today = day_key()
        later = lambda n: (date.fromisoformat(today) + timedelta(days=n)).isoformat()
        sid = self.st.c.execute("SELECT id FROM step").fetchone()[0]
        # 「安排到后天」：小步的日期 = 日历上安排的那天，回执写「安排」，能撤销
        v = self._do("edit_plan", {"action": "change", "kind": "step", "target": "小组", "due_in_days": 2}, "安排到后天")
        self.assertEqual(self.st.step(sid)["scheduled_day"], later(2))
        self.assertIn("安排", v[0]["verb"])
        m = self.st.add_msg("assistant", "排好了", {"acts": v})
        self.assertTrue(self.acts.set_state(self.st, m["id"], 0, "", do_undo=True)["ok"])
        self.assertEqual(self.st.step(sid)["scheduled_day"], "")
        # 往过去排不行；新加时也能带日子
        self.assertFalse(self.agent.run_tool(self.st, "edit_plan", {"action": "change", "kind": "step", "target": "小组",
                                                                    "due_day": later(-2)}, "x")["ok"])
        out = self.agent.run_tool(self.st, "edit_plan", {"action": "add", "kind": "step", "title": "背十个单词", "due_day": today}, "帮我加一个，今天背")
        self.assertEqual(self.st.step(out["id"])["scheduled_day"], today)
        # 小光的上下文里看得到安排的日子
        self.assertIn("背十个单词（今天）", self.agent.core_block(self.st.profile(), self.st))
        # 小光帮着设偷懒日：今天安排的挪到明天；在聊天里点撤销，挪走的回到今天
        v = self._do("log_lazy_day", {}, "今天想偷个懒")
        self.assertTrue(journey.is_resting(self.st))
        self.assertEqual(self.st.step(out["id"])["scheduled_day"], later(1))
        self.assertIn("挪到明天", v[0]["new"])
        m = self.st.add_msg("assistant", "好好休息", {"acts": v})
        self.assertTrue(self.acts.set_state(self.st, m["id"], 0, "", do_undo=True)["ok"])
        self.assertFalse(journey.is_resting(self.st))
        self.assertEqual(self.st.step(out["id"])["scheduled_day"], today)
        # 用 undo 参数说「不偷懒了」也一样
        self.agent.run_tool(self.st, "log_lazy_day", {}, "今天想偷个懒")
        back = self.agent.run_tool(self.st, "log_lazy_day", {"undo": True}, "不偷懒了")
        self.assertEqual((back["restored"], self.st.step(out["id"])["scheduled_day"]), (1, today))

    def test_read_only_and_suggest(self):
        self.assertEqual(self._do("look_up", {"area": "plan"}, "看看计划"), [])
        e = self._do("suggest_feature", {"feature": "kickstart", "task": "写引言"}, "x")[0]
        self.assertEqual((e["type"], e["title"], e["open"]["task"]), ("entry", "两分钟启动", "写引言"))
        self.assertEqual(self.acts.infer_entry("要不要试试冥想？", [])["feature"], "meditation")


class PortraitTest(unittest.TestCase):
    """我的空间 →「了解你」（core/portrait.py）：每条记忆都在且只在一个大类里；发现不到门槛不下结论。"""

    def setUp(self):
        from core import portrait
        self.p = portrait
        self.st = Store("u_" + os.urandom(8).hex())
        self.st.set_profile({"intent_primary": "敢开口说英语", "boundaries": ["别聊体重"]})
        for t, k in [("室友叫阿琪", "identity"), ("不吃香菜", "preference"), ("下学期去英国交换", "identity"),
                     ("11月5日在英语角和外国朋友聊了十分钟", "event"), ("想在课上敢发言", "intent"), ("累了先陪着", "boundary")]:
            self.st.add_memory(t, k, "digest")
        self.st.add_memory("可能有点焦虑", "insight", "digest", status="guess")

    def test_every_memory_in_exactly_one_category(self):
        cats = self.p.about(self.st)
        self.assertEqual([c["id"] for c in cats], self.p.CAT_IDS)
        ids = [i["id"] for c in cats for i in c["items"] if i["id"]]
        active = [m["id"] for m in self.st.memories(statuses=("active",))]
        self.assertEqual(sorted(ids), sorted(active))           # 一条不少，也不重复；猜测不在这里
        by = {i["text"]: c["id"] for c in cats for i in c["items"]}
        self.assertEqual(by["室友叫阿琪"], "people")
        self.assertEqual(by["11月5日在英语角和外国朋友聊了十分钟"], "recent")   # 事件里随口提到朋友，不算在意的人
        self.assertIn("别聊体重", by)                            # 设置里的边界也在小规矩里

    def test_category_override_and_early_portrait(self):
        m = self.st.memories(statuses=("active",))[0]
        self.st.set_cat(m["id"], "likes")
        self.assertIn(m["text"], [i["text"] for i in self.p.about(self.st)[2]["items"]])
        self.assertEqual(self.p.portrait(self.st)["by"], "early")

    def test_insights_locked_until_enough_and_hidden_after_no(self):
        f = {x["id"]: x for x in self.p.insights(self.st)}
        self.assertFalse(f["energy"]["ready"])
        self.assertEqual(f["energy"]["left"], 12)
        for i in range(10):
            self.st.c.execute("INSERT INTO moment(id, wish_id, day, text, feeling, mood, source, created_at, updated_at, photo) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (f"mo{i}", "", "2026-11-01", "好事", "", "", "user", "2026-11-01T21:00:00+08:00", "2026-11-01T21:00:00+08:00", ""))
        got = {x["id"]: x for x in self.p.insights(self.st)}["goodtime"]
        self.assertEqual(got["a"], "你多半在晚上留下瞬间")
        self.st.set_profile({"insight_fb": {"goodtime": "no"}})
        self.assertNotIn("goodtime", [x["id"] for x in self.p.insights(self.st)])     # 说了不太像，就不再出现


class StepJudgeAndProactiveTest(unittest.TestCase):
    """小步别打错勾；主动消息只挑有真材料的那种、不连着两次同一种、不带标签。"""

    def setUp(self):
        from core import agent, journey, proactive
        self.agent, self.journey, self.pro = agent, journey, proactive
        self.st = Store("u_" + os.urandom(8).hex())
        self.st.set_profile({"onboarded": True, "intent_primary": "敢开口说英语"})
        self.w = journey.add_wish(self.st, "敢开口说英语", "")
        self.st.add_step("在小组里主动提一个问题", wish_id=self.w["id"])

    def tearDown(self):
        self.st.close()

    def test_similar_but_different_thing_is_not_ticked(self):
        r = self.agent.run_tool(self.st, "complete_step", {"title": "在小组里主动提一个问题"},
                                "刚才我第一次在课上举手用英语回答了老师的问题")
        self.assertTrue(r.get("skipped"))
        self.assertEqual([s["status"] for s in self.st.steps()], ["todo"])
        r = self.agent.run_tool(self.st, "complete_step", {"title": "在小组里主动提一个问题"}, "小组里主动提问那一步我做完啦")
        self.assertTrue(r["ok"])

    def test_choose_needs_material_and_rotates(self):
        self.assertIsNone(self.pro.choose(self.st, resting=True))          # 什么都没有：不硬发
        self.st.add_memory("室友叫阿琪", "identity", "chat:explicit")
        from core import journey
        journey.add_moment(self.st, "", "抢到最后一份糖醋排骨")
        kinds = {self.pro.choose(self.st)["kind"] for _ in range(30)}
        self.assertTrue(kinds <= {"chat", "cheer", "plan", "feature"})
        self.st.set_profile({"last_proactive_kind": "chat"})
        self.assertNotIn("chat", {self.pro.choose(self.st, resting=True)["kind"] for _ in range(20)})   # 不连着两次


class LLMSwitchTest(unittest.TestCase):
    """后台切换模型：思考档按服务商翻译；思考 / 强制工具被拒、服务商 500 时自动换一种写法再试，保证有回复。"""

    def setUp(self):
        self.orig_open = llm._open
        self.calls = []
        os.environ.setdefault("MODELFLARE_API_KEY", "test")
        os.environ.setdefault("DEEPSEEK_API_KEY", "test")

    def tearDown(self):
        llm._open = self.orig_open
        if llm.CHOICE_PATH.exists():
            llm.CHOICE_PATH.unlink()

    def test_effort_translation_and_saved_choice(self):
        mf = llm.config({"provider": "modelflare", "model": "gpt-6.1-sol", "effort": "none"})
        self.assertNotIn("reasoning_effort", llm._body([], cfg=mf))                  # GPT 不认 none：不带
        ds = llm.config({"provider": "deepseek", "model": "deepseek-flash", "effort": "high"})
        self.assertEqual(llm._body([], cfg=ds)["reasoning_effort"], "max")
        llm.save_choice("modelflare", "kimi-k3", "low")
        c = llm.config()
        self.assertEqual((c["provider"], c["model"], c["reasoning"]), ("modelflare", "kimi-k3", "low"))

    def test_fallbacks_keep_a_reply(self):
        def fake(cfg, body, stream, timeout):
            self.calls.append((body.get("reasoning_effort"), body.get("tool_choice")))
            if body.get("reasoning_effort") not in (None, "none") and isinstance(body.get("tool_choice"), dict):
                raise llm.LLMError("HTTP 400: Thinking mode does not support this tool_choice")
            if len(self.calls) == 1:
                raise llm.LLMError("HTTP 500: Internal Server Error")
            return "resp"
        llm._open = fake
        ds = llm.config({"provider": "deepseek", "model": "deepseek-flash", "effort": "high"})
        body = llm._body([{"role": "user", "content": "x"}], tools=[{"type": "function", "function": {"name": "t"}}], tool_choice="t", cfg=ds)
        self.assertEqual(llm._request(body, True, 10, ds), "resp")
        self.assertEqual(self.calls[-1][0], "none")                                   # 最后是关掉思考、照样强制工具成功的
        llm._open = lambda *a: (_ for _ in ()).throw(llm.LLMError("HTTP 401: bad key"))
        with self.assertRaises(llm.LLMError):
            llm._request(body, True, 10, ds)                                          # key 不对不重试，直接报


if __name__ == "__main__":
    unittest.main()
