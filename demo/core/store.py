"""Per-user storage: one SQLite file per user at data/u/<uid>/mind.db.

Isolation is physical: the only way to open a store is Store(uid), and uid
comes from the authenticated session. Nothing in here takes a path or uid
from request data.

Tables
  profile(k, v)               core memory block (always in the prompt)
  memory(id, kind, text, source, status, ...) + memory_fts (bigram FTS5)
      status: active | guess | archived     guess = 小光推测，等用户确认
  step(id, title, why, status, wish, due_day, done_at)   plan micro-steps
  record(id, type, text, day)   good / rest / find
  msg(id, role, content, meta, thread, created_at)        chat transcript
  activity(id, kind, text, at)  audit log shown under the avatar
  inbox(id, text, cue, created_at, seen)                  proactive messages
  scene_run(id, scene, step, answers, status)             灵感 scene progress
"""
from __future__ import annotations

import math
import re
import sqlite3
import threading

from .util import DATA, clip, day_key, dumps, fts_doc, fts_query, iso, loads, new_id, now, parse_iso

UID_RE = re.compile(r"^u_[0-9a-f]{16}$")

KIND_WEIGHT = {"identity": 1.25, "intent": 1.3, "preference": 1.15, "boundary": 1.4,
               "insight": 1.0, "event": 0.9, "good_news": 0.85}

DEFAULT_PROFILE = {
    "agent_name": "小光", "agent_hue": "", "agent_avatar_id": "soft", "theme": "forest",
    "nickname": "", "intent_primary": "", "intent_why": "", "schedule_hint": "",
    "traits": [], "mbti_hint": "", "boundaries": [], "onboarded": False,
    "proactive": "normal",  # more | normal | less | off
    # 互动偏好：中断时希望小光怎么做 + 一次问几个问题 + 是否接受被主动问候
    "care_style": "",       # nudge | analyze | quiet | ""
    "pace": "gentle",       # gentle | steady
    "pet_name": "小芽", "pet_branch": "", "pet_branch_at": "", "pet_stage_seen": "",
    "last_digest_day": "",
    "xp": 0, "badges": [], "last_chat_at": "", "last_proactive_at": "", "created_at": "",
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(uid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(uid, threading.Lock())


class Store:
    def __init__(self, uid: str):
        if not UID_RE.match(uid or ""):
            raise ValueError("bad uid")
        self.uid = uid
        self.dir = DATA / "u" / uid
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = _lock_for(uid)
        self.c = sqlite3.connect(self.dir / "mind.db", check_same_thread=False, isolation_level=None, timeout=10)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self._schema()

    def close(self):
        self.c.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _schema(self):
        self.c.executescript(
            """
            CREATE TABLE IF NOT EXISTS profile(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS memory(
              id TEXT PRIMARY KEY, kind TEXT, text TEXT, source TEXT, status TEXT,
              created_at TEXT, updated_at TEXT, hits INTEGER DEFAULT 0);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, tok);
            CREATE TABLE IF NOT EXISTS step(
              id TEXT PRIMARY KEY, title TEXT, why TEXT, status TEXT, wish TEXT,
              due_day TEXT, created_at TEXT, done_at TEXT);
            CREATE TABLE IF NOT EXISTS record(id TEXT PRIMARY KEY, type TEXT, text TEXT, day TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS msg(
              id TEXT PRIMARY KEY, role TEXT, content TEXT, meta TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS activity(id TEXT PRIMARY KEY, kind TEXT, text TEXT, at TEXT);
            CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY, text TEXT, cue TEXT, created_at TEXT, seen INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS scene_run(
              id TEXT PRIMARY KEY, scene TEXT, step INTEGER, answers TEXT, status TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS xp(
              id TEXT PRIMARY KEY, day TEXT, source TEXT, amount INTEGER, ref TEXT,
              note TEXT, created_at TEXT);
            CREATE INDEX IF NOT EXISTS xp_day ON xp(day, source);
            CREATE TABLE IF NOT EXISTS article_read(
              id TEXT PRIMARY KEY, at TEXT);
            CREATE TABLE IF NOT EXISTS badge(id TEXT PRIMARY KEY, at TEXT);
            CREATE TABLE IF NOT EXISTS stat(k TEXT PRIMARY KEY, n INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS digest(
              day TEXT PRIMARY KEY, summary TEXT, highlights TEXT, stats TEXT, ops TEXT,
              by_model INTEGER DEFAULT 0, created_at TEXT);
            CREATE TABLE IF NOT EXISTS memory_rev(
              id TEXT PRIMARY KEY, memory_id TEXT, old_text TEXT, new_text TEXT,
              reason TEXT, evidence TEXT, at TEXT);
            """
        )

    # ---- profile (core memory) ---------------------------------------------
    def profile(self) -> dict:
        p = dict(DEFAULT_PROFILE)
        for r in self.c.execute("SELECT k, v FROM profile"):
            p[r["k"]] = loads(r["v"], r["v"])
        return p

    def set_profile(self, patch: dict) -> dict:
        with self.lock:
            for k, v in patch.items():
                if k in DEFAULT_PROFILE:
                    self.c.execute("INSERT OR REPLACE INTO profile(k, v) VALUES(?,?)", (k, dumps(v)))
        return self.profile()

    # ---- memory -------------------------------------------------------------
    def add_memory(self, text: str, kind: str = "insight", source: str = "chat", status: str = "active") -> dict:
        text = clip(text, 240)
        mid = new_id("m")
        t = iso()
        with self.lock:
            self.c.execute("INSERT INTO memory(id, kind, text, source, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                           (mid, kind, text, source, status, t, t))
            self.c.execute("INSERT INTO memory_fts(id, tok) VALUES(?,?)", (mid, fts_doc(text + " " + kind)))
        return self.get_memory(mid)

    def get_memory(self, mid: str) -> dict | None:
        r = self.c.execute("SELECT * FROM memory WHERE id=?", (mid,)).fetchone()
        return dict(r) if r else None

    def update_memory(self, mid: str, text: str | None = None, status: str | None = None, kind: str | None = None,
                      reason: str = "", evidence: str = "") -> dict | None:
        m = self.get_memory(mid)
        if not m:
            return None
        with self.lock:
            if text is not None and text != m["text"]:
                text = clip(text, 240)
                self.c.execute("UPDATE memory SET text=?, updated_at=? WHERE id=?", (text, iso(), mid))
                self.c.execute("DELETE FROM memory_fts WHERE id=?", (mid,))
                self.c.execute("INSERT INTO memory_fts(id, tok) VALUES(?,?)", (mid, fts_doc(text + " " + (kind or m["kind"]))))
                self._rev(mid, m["text"], text, reason or "edit", evidence)
            if status is not None:
                self.c.execute("UPDATE memory SET status=?, updated_at=? WHERE id=?", (status, iso(), mid))
            if kind is not None:
                self.c.execute("UPDATE memory SET kind=? WHERE id=?", (kind, mid))
        return self.get_memory(mid)

    def delete_memory(self, mid: str, reason: str = "forget", evidence: str = "") -> bool:
        m = self.get_memory(mid)
        with self.lock:
            n = self.c.execute("DELETE FROM memory WHERE id=?", (mid,)).rowcount
            self.c.execute("DELETE FROM memory_fts WHERE id=?", (mid,))
            if n and m:
                self._rev(mid, m["text"], None, reason, evidence)
        return n > 0

    def _rev(self, mid: str, old: str | None, new: str | None, reason: str, evidence: str = "") -> None:
        """Every change to a memory keeps its before/after and why — the
        「变更依据」 that lets a user see how 小光 came to believe something."""
        self.c.execute("INSERT INTO memory_rev(id, memory_id, old_text, new_text, reason, evidence, at) VALUES(?,?,?,?,?,?,?)",
                       (new_id("v"), mid, old, new, reason, clip(evidence or "", 200), iso()))

    def revisions(self, limit: int = 40) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM memory_rev ORDER BY at DESC, rowid DESC LIMIT ?", (limit,))]

    # ---- counters (badges) ----------------------------------------------------
    def stat(self, k: str) -> int:
        r = self.c.execute("SELECT n FROM stat WHERE k=?", (k,)).fetchone()
        return int(r["n"]) if r else 0

    def bump(self, k: str, n: int = 1) -> int:
        with self.lock:
            self.c.execute("INSERT INTO stat(k, n) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET n = n + ?", (k, n, n))
        return self.stat(k)

    # ---- daily digests -------------------------------------------------------
    def digests(self, limit: int = 14) -> list[dict]:
        out = []
        for r in self.c.execute("SELECT * FROM digest ORDER BY day DESC LIMIT ?", (limit,)):
            d = dict(r)
            d["highlights"] = loads(d["highlights"], [])
            d["stats"] = loads(d["stats"], {})
            d["ops"] = loads(d["ops"], [])
            out.append(d)
        return out

    def save_digest(self, day: str, summary: str, highlights: list, stats: dict, ops: list, by_model: bool) -> None:
        with self.lock:
            self.c.execute("INSERT OR REPLACE INTO digest(day, summary, highlights, stats, ops, by_model, created_at) "
                           "VALUES(?,?,?,?,?,?,?)", (day, summary, dumps(highlights), dumps(stats), dumps(ops),
                                                     1 if by_model else 0, iso()))

    def memories(self, status: str | None = None, limit: int = 200, statuses: tuple | None = None) -> list[dict]:
        if statuses:
            q = ",".join("?" * len(statuses))
            rows = self.c.execute(f"SELECT * FROM memory WHERE status IN ({q}) ORDER BY created_at DESC LIMIT ?", (*statuses, limit))
        elif status:
            rows = self.c.execute("SELECT * FROM memory WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            rows = self.c.execute("SELECT * FROM memory WHERE status!='archived' ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def search(self, query: str, k: int = 6, include_guess: bool = False) -> list[dict]:
        """Hybrid retrieval: FTS5 BM25 relevance × recency decay × memory-kind weight.

        Without embeddings (the relay has no /v1/embeddings) this is a
        lexical retriever, which handles the short, personal facts we store
        well. Falls back to recent memories when nothing matches lexically.
        """
        q = fts_query(query)
        cand: dict[str, float] = {}
        if q:
            try:
                for r in self.c.execute("SELECT id, bm25(memory_fts) AS s FROM memory_fts WHERE memory_fts MATCH ? ORDER BY s LIMIT 40", (q,)):
                    cand[r["id"]] = -r["s"]  # bm25 is lower-is-better
            except sqlite3.OperationalError:
                cand = {}
        ok = ("active", "guess") if include_guess else ("active",)
        out = []
        ref = now()
        for mid, rel in cand.items():
            m = self.get_memory(mid)
            if not m or m["status"] not in ok:
                continue
            age_days = max(0.0, (ref - (parse_iso(m["updated_at"]) or ref)).total_seconds() / 86400)
            recency = 0.6 + 0.4 * math.exp(-age_days / 21)
            m["score"] = round((rel + 1e-6) * recency * KIND_WEIGHT.get(m["kind"], 1.0) * 1e6, 3)
            out.append(m)
        out.sort(key=lambda m: m["score"], reverse=True)
        out = out[:k]
        if out:
            with self.lock:
                self.c.executemany("UPDATE memory SET hits=hits+1 WHERE id=?", [(m["id"],) for m in out])
        return out

    # ---- plan steps ---------------------------------------------------------
    def add_step(self, title: str, why: str = "", wish: str = "", due_day: str | None = None) -> dict:
        sid = new_id("s")
        with self.lock:
            self.c.execute("INSERT INTO step(id, title, why, status, wish, due_day, created_at) VALUES(?,?,?,?,?,?,?)",
                           (sid, clip(title, 80), clip(why, 160), "todo", clip(wish, 80), due_day or day_key(), iso()))
        return dict(self.c.execute("SELECT * FROM step WHERE id=?", (sid,)).fetchone())

    def steps(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM step ORDER BY created_at DESC LIMIT ?", (limit,))]

    def set_step(self, sid: str, status: str) -> dict | None:
        with self.lock:
            done = iso() if status == "done" else None
            n = self.c.execute("UPDATE step SET status=?, done_at=? WHERE id=?", (status, done, sid)).rowcount
        if not n:
            return None
        return dict(self.c.execute("SELECT * FROM step WHERE id=?", (sid,)).fetchone())

    def complete_step(self, sid: str | None = None, title: str | None = None) -> dict | None:
        """Mark a todo step done by id, or by fuzzy title match (the model often only knows the title)."""
        todo = [x for x in self.steps() if x["status"] == "todo"]
        hit = next((x for x in todo if sid and x["id"] == sid), None)
        if not hit and title:
            t = title.strip()
            hit = next((x for x in todo if t and (t in x["title"] or x["title"] in t)), None)
            if not hit:
                from .util import tokens
                want = set(tokens(t))
                scored = sorted(((len(want & set(tokens(x["title"]))), x) for x in todo), key=lambda z: -z[0])
                hit = scored[0][1] if scored and scored[0][0] >= 2 else None
        return self.set_step(hit["id"], "done") if hit else None

    def gain_xp(self, n: int = 10) -> dict:
        """Legacy helper kept for older call sites; new code uses growth.award,
        which enforces the daily/source caps and de-duplication."""
        from . import growth
        out = growth.award(self, "action", ref=new_id("legacy"), note="经验", amount=n)
        return rank(int(self.profile().get("xp") or 0)) | {"gain": out.get("amount", 0)}

    # ---- records (好消息 / 偷懒日 / 新发现) ---------------------------------
    def add_record(self, type_: str, text: str, day: str | None = None) -> dict:
        rid = new_id("r")
        with self.lock:
            self.c.execute("INSERT INTO record(id, type, text, day, created_at) VALUES(?,?,?,?,?)",
                           (rid, type_, clip(text, 200), day or day_key(), iso()))
        return dict(self.c.execute("SELECT * FROM record WHERE id=?", (rid,)).fetchone())

    def records(self, limit: int = 500) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM record ORDER BY day DESC, created_at DESC LIMIT ?", (limit,))]

    # ---- transcript ---------------------------------------------------------
    def add_msg(self, role: str, content: str, meta: dict | None = None, at: str | None = None) -> dict:
        mid = new_id("c")
        with self.lock:
            self.c.execute("INSERT INTO msg(id, role, content, meta, created_at) VALUES(?,?,?,?,?)",
                           (mid, role, content, dumps(meta or {}), at or iso()))
        return {"id": mid, "role": role, "content": content, "meta": meta or {}, "created_at": at or iso()}

    def msgs(self, limit: int = 80) -> list[dict]:
        rows = self.c.execute("SELECT * FROM msg ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "meta": loads(r["meta"], {})} for r in reversed(rows)]

    def msgs_on(self, day: str) -> list[dict]:
        rows = self.c.execute("SELECT * FROM msg WHERE substr(created_at,1,10)=? ORDER BY created_at, rowid", (day,)).fetchall()
        return [{**dict(r), "meta": loads(r["meta"], {})} for r in rows]

    # ---- activity log -------------------------------------------------------
    def log(self, kind: str, text: str) -> None:
        with self.lock:
            self.c.execute("INSERT INTO activity(id, kind, text, at) VALUES(?,?,?,?)", (new_id("a"), kind, clip(text, 140), iso()))

    def activity(self, limit: int = 40) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM activity ORDER BY at DESC, rowid DESC LIMIT ?", (limit,))]

    # ---- inbox (proactive) --------------------------------------------------
    def push_inbox(self, text: str, cue: str) -> dict:
        iid = new_id("i")
        with self.lock:
            self.c.execute("INSERT INTO inbox(id, text, cue, created_at) VALUES(?,?,?,?)", (iid, text, cue, iso()))
        return {"id": iid, "text": text, "cue": cue}

    def unseen_inbox(self) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM inbox WHERE seen=0 ORDER BY created_at")]

    def mark_inbox_seen(self) -> None:
        with self.lock:
            self.c.execute("UPDATE inbox SET seen=1 WHERE seen=0")

    # ---- scene runs ---------------------------------------------------------
    def scene_active(self) -> dict | None:
        r = self.c.execute("SELECT * FROM scene_run WHERE status='active' ORDER BY created_at DESC LIMIT 1").fetchone()
        return {**dict(r), "answers": loads(r["answers"], [])} if r else None

    def scene_start(self, scene: str) -> dict:
        with self.lock:
            self.c.execute("UPDATE scene_run SET status='abandoned' WHERE status='active'")
            rid = new_id("sc")
            self.c.execute("INSERT INTO scene_run(id, scene, step, answers, status, created_at) VALUES(?,?,?,?,?,?)",
                           (rid, scene, 0, "[]", "active", iso()))
        return self.scene_active()

    def scene_update(self, rid: str, step: int, answers: list, status: str = "active") -> None:
        with self.lock:
            self.c.execute("UPDATE scene_run SET step=?, answers=?, status=? WHERE id=?", (step, dumps(answers), status, rid))

    def scenes_done(self) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT scene, created_at FROM scene_run WHERE status='done'")]

    # ---- academy read marks -------------------------------------------------
    def mark_read(self, article_id: str) -> None:
        with self.lock:
            self.c.execute("INSERT OR IGNORE INTO article_read(id, at) VALUES(?,?)", (article_id, iso()))

    def read_ids(self) -> set[str]:
        return {r["id"] for r in self.c.execute("SELECT id FROM article_read")}

    # ---- aggregates ---------------------------------------------------------
    def counts(self) -> dict:
        q = lambda sql, *a: self.c.execute(sql, a).fetchone()[0]
        created = parse_iso(self.profile().get("created_at")) or now()
        return {
            "days": max(1, (now().date() - created.date()).days + 1),
            "good": q("SELECT COUNT(*) FROM record WHERE type='good'"),
            "rest": q("SELECT COUNT(DISTINCT day) FROM record WHERE type='rest'"),
            "finds": q("SELECT COUNT(*) FROM record WHERE type='find'"),
            "done": q("SELECT COUNT(*) FROM step WHERE status='done'"),
            "todo": q("SELECT COUNT(*) FROM step WHERE status='todo'"),
            "memories": q("SELECT COUNT(*) FROM memory WHERE status='active'"),
            "guesses": q("SELECT COUNT(*) FROM memory WHERE status='guess'"),
        }

    # names used by the agent / scenes / scheduler layers
    add_message = add_msg
    messages = msgs
    add_inbox = push_inbox

    def inbox(self, unseen_only: bool = False) -> list[dict]:
        if unseen_only:
            return self.unseen_inbox()
        return [dict(r) for r in self.c.execute("SELECT * FROM inbox ORDER BY created_at DESC LIMIT 20")]

    def start_scene(self, scene: str) -> dict:
        return self.scene_start(scene)

    def get_scene(self, rid: str) -> dict | None:
        r = self.c.execute("SELECT * FROM scene_run WHERE id=?", (rid,)).fetchone()
        if not r:
            return None
        d = {**dict(r), "answers": loads(r["answers"], [])}
        d["status"] = "open" if d["status"] == "active" else d["status"]
        return d

    def update_scene(self, rid: str, step: int, answers: list, status: str = "active") -> None:
        self.scene_update(rid, step, answers, status)


RANKS = [(0, "萌芽"), (60, "微光"), (160, "小光"), (320, "星光")]


def rank(xp: int) -> dict:
    cur = RANKS[0]
    nxt = None
    for i, r in enumerate(RANKS):
        if xp >= r[0]:
            cur = r
            nxt = RANKS[i + 1] if i + 1 < len(RANKS) else None
    return {"xp": xp, "rank": cur[1], "next_rank": nxt[1] if nxt else None,
            "next_at": nxt[0] if nxt else None, "floor": cur[0]}
