"""Long-term memory write path (after each chat turn, in a background thread).

Pattern borrowed from mem0 (github.com/mem0ai/mem0): extract candidate facts
from the latest exchange, retrieve the most similar existing memories, then
let the model choose ADD / UPDATE / DELETE / NOOP per fact, so memory stays
deduplicated instead of growing a pile of near-copies. Tiering (core block in
the prompt + searchable archival store) follows Letta/MemGPT.

Difference from both: anything the model *infers* (rather than the user
stating it) is stored with status=guess and surfaces in the chat as a
confirm card. It does not shape replies until the user taps 「对」.
That's the manifestation-specific rule: beliefs about yourself are yours to
confirm.
"""
from __future__ import annotations

import re
from datetime import timedelta

from . import llm
from .store import Store
from .util import clip, now, tokens

KINDS = ["identity", "intent", "preference", "boundary", "insight", "event"]

EXTRACT_PROMPT = """你在为一个「显化陪伴」应用维护用户的长期记忆。
读最新一轮对话，找出值得长期记住、能帮助以后陪伴这个人的信息。

规则：
- 只记关于用户本人的信息：身份、想成为的人/愿景、偏好、边界（不想被怎样对待）、对自己的新发现、重要事件。
- 闲聊、一次性问题、小光自己说的话，不记。
- 用户亲口说的 → "source":"said"。从语气或行为推测出来的 → "source":"guess"（推测要谨慎，最多 1 条）。
- 每条一句话，第三人称写，例如「想在交换项目时敢开口说英语」。不超过 40 字。
- 对照「已有相关记忆」：
  - 新信息 → ADD
  - 补充或修正某条已有记忆 → UPDATE，并给出 id 和合并后的新文本
  - 用户明确否定了某条已有记忆 → DELETE，给出 id
  - 已经记过 → 不输出
- 没有可记的，返回空列表。

只输出 JSON：{"ops":[{"op":"ADD|UPDATE|DELETE","id":"(UPDATE/DELETE 必填)","text":"...","kind":"identity|intent|preference|boundary|insight|event","source":"said|guess"}]}"""


def extract_and_apply(store: Store, user_text: str, reply_text: str) -> list[dict]:
    if len((user_text or "").strip()) < 4:
        return []
    # Lexical hits alone miss paraphrases (「十二点前睡」 vs 「一点才睡」 share no
    # bigram), so the model also sees the most recent memories when deciding
    # whether something is new or an update.
    related = store.search(user_text, k=6, include_guess=True)
    seen = {m["id"] for m in related}
    related += [m for m in store.memories(statuses=("active", "guess"), limit=8) if m["id"] not in seen]
    rel_txt = "\n".join(f"- id={m['id']} [{m['kind']}] {m['text']}" for m in related) or "（无）"
    msgs = [
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content": f"已有相关记忆：\n{rel_txt}\n\n最新一轮：\n用户：{clip(user_text, 600)}\n小光：{clip(reply_text, 400)}"},
    ]
    out = llm.complete_json(msgs)
    if not out:
        return []
    return apply_ops(store, out.get("ops") or [], {m["id"] for m in related})


def apply_ops(store: Store, ops: list, allowed_ids: set[str]) -> list[dict]:
    """Apply model-proposed ops defensively: UPDATE/DELETE only on memories
    that were actually shown to the model; at most one new guess per turn."""
    applied, guesses = [], 0
    for op in ops[:5]:
        if not isinstance(op, dict):
            continue
        kind = op.get("kind") if op.get("kind") in KINDS else "insight"
        text = clip(str(op.get("text") or ""), 80)
        action = str(op.get("op") or "").upper()
        if action == "ADD" and text:
            is_guess = op.get("source") == "guess"
            if is_guess:
                if guesses >= 1:
                    continue
                guesses += 1
            m = store.add_memory(text, kind, "chat", "guess" if is_guess else "active")
            store.log("memory", ("猜了一条：" if is_guess else "记住了：") + text)
            applied.append({"op": "ADD", **m})
        elif action == "UPDATE" and op.get("id") in allowed_ids and text:
            m = store.update_memory(op["id"], text=text)
            if m:
                store.log("memory", "更新了记忆：" + text)
                applied.append({"op": "UPDATE", **m})
        elif action == "DELETE" and op.get("id") in allowed_ids:
            m = store.get_memory(op["id"])
            if m and store.delete_memory(op["id"]):
                store.log("memory", "按你说的忘掉了：" + m["text"])
                applied.append({"op": "DELETE", **m})
    return applied


# ---------------------------------------------------------------- TA 亲手删掉 / 更正过的 ----
# 「忘掉」「不对」「改一下」要真的生效：记忆那一行删了、改了还不够——同一件事还写在小光的笔记本里（每轮都进提示词），
# 最近三天的聊天原话里也有，夜里整理还可能从对话里把它再记回来。这里做三件事：
#   1. scrub_notebook：把笔记本里说这件事的那半句拿掉（TA 删、改的那一下就做）；
#   2. forgotten：最近 TA 亲手删掉 / 更正过什么（直接读 memory_rev，不另存一份）——对话提示里告诉小光别再提，
#      夜里整理的提示里告诉模型别再写回去；
#   3. blocked：夜里整理想新记一条和「TA 删掉的」很像的 → 不记（TA 删掉之后又自己说起的那天除外）。
USER_REASONS = ("user_reject", "user_forget", "user_corrected", "user_edit")
_CLAUSE = re.compile(r"([；;。\n])")
_HEAD = re.compile(r"^\s*[^：:；;。\n]{1,8}[：:]")        # 「最近的生活：」这样的块名
_PUNCT = re.compile(r"[\s，。！？、,.!?~～…；;：:\"'“”‘’（）()]")


NL = chr(10)


def _dice(a: str, b: str) -> float:
    x, y = set(tokens(a)), set(tokens(b))
    return 2 * len(x & y) / (len(x) + len(y)) if x and y else 0.0


def _flat(s: str) -> str:
    return _PUNCT.sub("", s or "")


def forgotten(store: Store, days: int = 30, limit: int = 8) -> list[dict]:
    """最近 TA 亲手删掉（new 为空）或更正（old → new）的记忆，新的在前。
    后来又有一条几乎一样的记忆（TA 自己加回来了）的不算。"""
    since = (now() - timedelta(days=days)).isoformat(timespec="seconds")
    q = ",".join("?" * len(USER_REASONS))
    rows = store.c.execute(f"SELECT old_text, new_text, at FROM memory_rev WHERE reason IN ({q}) AND at>=? "
                           "ORDER BY at DESC, rowid DESC LIMIT 40", (*USER_REASONS, since)).fetchall()
    live = [m["text"] for m in store.memories(statuses=("active",), limit=400)]
    out, seen = [], set()
    for r in rows:
        old, new = (r["old_text"] or "").strip(), (r["new_text"] or "").strip()
        if not old or old in seen or old == new:
            continue
        seen.add(old)
        if any(_dice(old, t) >= 0.75 for t in live if t != new):
            continue
        out.append({"old": old, "new": new, "at": r["at"]})
        if len(out) >= limit:
            break
    return out


def forgotten_text(items: list[dict]) -> str:
    return "\n".join(f"- 「{clip(f['old'], 60)}」" + (f" → 现在是「{clip(f['new'], 60)}」" if f["new"] else "（TA 让你忘掉了）")
                     for f in items)


def scrub_text(text: str, old: str) -> str:
    """把一段笔记里说 old 这件事的那半句拿掉（按 ；。和换行分句；「块名：」留着）。"""
    o = _flat(old)
    if not text or len(o) < 3:
        return text
    parts = _CLAUSE.split(text)
    keep: list[list[str]] = []
    changed = False
    for i in range(0, len(parts), 2):
        seg, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        head, body = "", seg
        m = _HEAD.match(seg)
        if m:
            head, body = m.group(0), seg[m.end():]
        b = _flat(body)
        if b and ((len(o) >= 4 and o in b) or (len(b) >= 4 and b in o) or b == o or _dice(body, old) >= 0.45):
            body, changed = "", True
        if head or body.strip() or not keep:
            keep.append([head + body, sep])
        else:
            keep[-1][1] += sep if sep == NL else ""       # 这半句拿掉了：它后面的换行留着
    if not changed:
        return text
    out = "".join(a + b for a, b in keep)
    out = re.sub("([：:])[；;。]+", lambda m: m.group(1), out)
    out = re.sub("[；;]+(?=。|" + NL + "|$)", "", out)
    out = re.sub("^[；;。]+", "", out, flags=re.M)
    return out.strip()


def scrub_notebook(store: Store, old: str) -> bool:
    """TA 删掉 / 更正了一条记忆：笔记本里说这件事的那半句也拿掉。返回有没有动。"""
    nb = store.profile().get("notebook") or {}
    text = nb.get("text") or ""
    new = scrub_text(text, old)
    if new == text:
        return False
    store.set_profile({"notebook": {**nb, "text": new, "updated_at": now().isoformat(timespec="seconds")}})
    return True


def blocked(text: str, items: list[dict], day: str) -> bool:
    """夜里整理想新记的这一条，是不是 TA 在那天之后亲手删掉的（不带新说法的才算）。"""
    return any(not f["new"] and f["at"][:10] >= day and _dice(text, f["old"]) >= 0.6 for f in items)
