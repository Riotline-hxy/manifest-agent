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

from . import llm
from .store import Store
from .util import clip

KINDS = ["identity", "intent", "preference", "boundary", "insight", "event", "good_news"]

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

只输出 JSON：{"ops":[{"op":"ADD|UPDATE|DELETE","id":"(UPDATE/DELETE 必填)","text":"...","kind":"identity|intent|preference|boundary|insight|event|good_news","source":"said|guess"}]}"""


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
