"""日终记忆整理（讨论稿 2.3「隐性记忆按日整理」）。

普通聊天不再每轮都触发一次记忆抽取；每天一次，把这一天真正发生的事
（对话、瞬间、完成的小步、练习）交给模型做**增量**整理：
  - 只输出变化：ADD / UPDATE / DELETE，不重写整份画像；
  - 用户明确说过「记住」的、亲手确认过的、建档时写下的是**受保护记忆**：
    只有当天用户原话里能逐字找到依据时才允许修改或删除（依据存进 memory_rev）；
  - 事件留作事件：「三天没健身」最多记成带日期的事，不升格为性格；
  - 推测每天最多 1 条，且以 guess 状态进入，等用户点头；
  - 超长的粘贴文本当作资料，不当作用户本人的经历。
同时写一条当天的小结（首页那句话）。小光的笔记本一周一页，在 core/weekly.py。
模型不可用时只写确定性小结，不动任何记忆。
"""
from __future__ import annotations

from datetime import timedelta

from . import kickstart, llm
from .memory import KINDS
from .store import Store
from .util import clip, day_key, now

# 用户亲口要求记的、亲手确认的、建档写的，以及在点子结束页勾选保存的：夜里整理只有拿到原话依据才能改
PROTECTED = {"chat:explicit", "confirmed", "onboarding", "scene:relearn", "scene:seven_steps_lite"}
LONG_PASTE = 1200

PROMPT = """你在为「显化陪伴」应用做每天一次的记忆整理。下面是用户某一天的全部材料和已有记忆。
任务：只找出**需要变化**的部分，输出增量操作；没有变化就返回空列表。

规则：
1. 只记关于用户本人的、对以后陪伴有用的信息：身份、愿景、偏好、边界、对自己的新发现、重要事件。
2. 一次性的状态是「事件」，要带日期写，例如「10月27日：连续三天没去健身」。绝不能据此写成性格判断（如「三分钟热度」「没毅力」）。
3. 已有记忆标了 [保护] 的，是用户亲口要求记住或亲手确认的。只有当用户当天**明确更正或否定**它时才能 UPDATE / DELETE，
   并且 evidence 必须逐字摘录用户当天说的原话。
4. 推测（从行为推断、用户没直接说的）source 填 guess，最多 1 条，要谨慎。用户亲口说的 source 填 said。
5. 已经记过的不要重复；补充或修正用 UPDATE 给出合并后的新文本。
6. 标了 [长文资料] 的内容是用户粘贴的材料，不是他的经历，不要从中抽取个人信息。
7. 另写一句 summary：这是陪伴者「小光」第二天对 TA 说的一句话，会出现在 TA 的首页上。
   一句话、≤40 字、第二人称，像朋友随口说起；只用材料里的事实，带一点自己的感受或注意到的细节
   （比如「昨天你说完还是去跑了，我挺替你高兴的」），不要写成流水账或总结报告，不说教，不用「不是……而是……」。
   以及最多 3 个值得记住的瞬间（每个 ≤20 字）。
8. 更新「笔记本」：这是陪伴者自己记的、关于用户的长期笔记，以后几周、几个月都会靠它记得这个人。
   在上一版的基础上，把今天值得长期记住的内容合并进去，输出完整的新版本（≤1200 字），分这几块写，每块几行短句：
   最近的生活 / 在意的人 / 正在努力的事 / 心情和状态 / 相处时的偏好 / 时间线（带日期的重要事件，按时间排）。
   只写材料里出现过的事实；推测要标「（猜）」；过时的内容可以删掉或合并。今天没有值得写进去的，就原样返回上一版。
9. 「两分钟启动记忆」是 TA 勾选让你记住的启动经历（想做什么、卡在哪、怎么调整、做了几步）。
   从里面找值得长期记住的：常见的阻碍、对 TA 管用的启动方式、行为上的规律，写进记忆或笔记本；
   只出现一次的经历最多记成带日期的事件，不要直接当成稳定的偏好或性格；已经记过的不要重复。
10. 每条 ADD 都写 cat，归进「了解你」的六个大类之一（用户在「我的空间」里按这六类看自己的记忆）：
   effort 在努力（想靠近的样子、正在做的事）/ people 在意的人（家人、朋友、宠物，和他们有关的事）/
   likes 喜好和习惯（口味、喜欢不喜欢、作息习惯）/ self 关于你自己（处境、身份、对自己的认识）/
   recent 最近发生的事（带日期的事件）/ rules 相处的小规矩（希望小光怎么陪、别碰的话题）。
11. portrait：「小光眼中的你」，一句话、≤30 字、第二人称或「一个……的人」。写这个人是什么样的人、最近在变成什么样，
   只用笔记本和已有记忆里的事实，温暖、具体，不夸张、不说教。材料太少写不出来就返回空字符串。

只输出 JSON：
{"summary":"...","highlights":["..."],"notebook":"（完整的新笔记本）","portrait":"...","ops":[{"op":"ADD|UPDATE|DELETE","id":"(UPDATE/DELETE 必填)","text":"...","kind":"identity|intent|preference|boundary|insight|event","cat":"effort|people|likes|self|recent|rules","source":"said|guess","evidence":"(改动保护记忆时必填：用户原话)"}]}"""


def material(st: Store, day: str) -> dict:
    msgs = st.msgs_on(day)
    user_lines, long_pastes = [], 0
    convo = []
    for m in msgs:
        if m["role"] == "user":
            if len(m["content"]) > LONG_PASTE:
                long_pastes += 1
                convo.append(f"用户：[长文资料，{len(m['content'])} 字，略]")
                continue
            user_lines.append(m["content"])
            convo.append("用户：" + clip(m["content"], 400))
        elif m["role"] == "assistant" and m["content"]:
            convo.append("小光：" + clip(m["content"], 160))
    recs = [r for r in st.records(300) if r["day"] == day]
    done = [s for s in st.steps(300) if s["status"] == "done" and (s.get("done_at") or "")[:10] == day]
    added = [s for s in st.steps(300) if (s.get("created_at") or "")[:10] == day]
    scenes = [dict(r) for r in st.c.execute(
        "SELECT scene FROM scene_run WHERE status='done' AND substr(created_at,1,10)=?", (day,))]
    moments = [dict(r) for r in st.c.execute(
        "SELECT m.text, m.feeling, COALESCE(w.title, '') AS title FROM moment m LEFT JOIN wish w ON w.id=m.wish_id WHERE m.day=?", (day,))]
    for m in moments:   # 用户亲手写下的瞬间，也是 TA 的原话
        user_lines.append(m["text"] + (" " + m["feeling"] if m["feeling"] else ""))
    kicks = kickstart.on_day(st, day)
    for k in kicks:     # 两分钟启动里 TA 自己说的话（调整原因、三问的回答）
        user_lines += k["said"]
    return {"day": day, "convo": convo, "user_lines": user_lines, "long_pastes": long_pastes,
            "records": recs, "done": done, "added": added, "scenes": scenes, "moments": moments, "kicks": kicks}


def has_material(mat: dict) -> bool:
    return bool(mat["convo"] or mat["records"] or mat["done"] or mat["scenes"] or mat.get("moments") or mat.get("kicks"))


def fallback_summary(mat: dict) -> tuple[str, list[str]]:
    parts = []
    n_user = sum(1 for c in mat["convo"] if c.startswith("用户："))
    if n_user:
        parts.append(f"聊了 {n_user} 句")
    if mat["done"]:
        parts.append(f"完成 {len(mat['done'])} 个小步")
    if any(r["type"] == "rest" for r in mat["records"]):
        parts.append("给自己放了一天假")
    if mat["scenes"]:
        parts.append(f"做了 {len(mat['scenes'])} 次练习")
    if mat.get("moments"):
        parts.append(f"留下 {len(mat['moments'])} 个瞬间")
    if mat.get("kicks"):
        parts.append(f"用两分钟启动开始了 {len(mat['kicks'])} 件事")
    summary = ("今天" + "，".join(parts) + "。") if parts else "今天很安静。"
    hl = [clip(m["text"], 20) for m in (mat.get("moments") or [])[:2]] + [clip(s["title"], 20) for s in mat["done"][:1]]
    return summary, hl[:3]


def run(st: Store, day: str | None = None, use_model: bool = True) -> dict:
    day = day or day_key()
    mat = material(st, day)
    if not has_material(mat):
        st.set_profile({"last_digest_day": day})
        return {"day": day, "skipped": True, "reason": "这一天没有可整理的内容"}

    existing = st.memories(statuses=("active", "guess"), limit=60)
    mem_txt = "\n".join(
        f"- id={m['id']} [{m['kind']}]{' [保护]' if m['source'] in PROTECTED else ''}{' [猜测]' if m['status'] == 'guess' else ''} {m['text']}"
        for m in existing) or "（无）"
    lines = [f"日期：{day}", "", "## 对话"] + (mat["convo"] or ["（没有聊天）"])
    if mat["records"]:
        lines += ["", "## 记录"] + [f"- [{ {'rest': '休息日'}.get(r['type'], r['type'])}] {r['text']}" for r in mat["records"]]
    if mat["done"]:
        lines += ["", "## 完成的小步"] + [f"- {s['title']}" for s in mat["done"]]
    if mat["added"]:
        lines += ["", "## 新加的小步"] + [f"- {s['title']}" for s in mat["added"]]
    if mat["scenes"]:
        lines += ["", "## 练习"] + [f"- {s['scene']}" for s in mat["scenes"]]
    if mat.get("moments"):
        lines += ["", "## 瞬间（用户亲手留下的）"] + [f"- {'[' + m['title'] + '] ' if m['title'] else ''}{m['text']}" + (f"（感受：{m['feeling']}）" if m["feeling"] else "")
                                                     for m in mat["moments"]]
    if mat.get("kicks"):
        lines += ["", "## 两分钟启动记忆（TA 勾选让你记住的启动经历）"] + [k["text"] for k in mat["kicks"]]
    lines += ["", "## 已有记忆", mem_txt]
    old_nb = (st.profile().get("notebook") or {}).get("text") or ""
    lines += ["", "## 笔记本（上一版）", old_nb or "（还没有，今天开始写）"]

    out = llm.complete_json([{"role": "system", "content": PROMPT},
                             {"role": "user", "content": clip("\n".join(lines), 12000)}], timeout=90) if use_model else None

    applied, rejected, page = [], [], None
    if out:
        summary = clip(str(out.get("summary") or ""), 80)
        highlights = [clip(str(h), 24) for h in (out.get("highlights") or [])][:3]
        applied, rejected = apply(st, out.get("ops") or [], {m["id"]: m for m in existing}, mat, day)
        nb = str(out.get("notebook") or "").strip()
        if len(nb) >= 20 and nb != old_nb:
            st.set_profile({"notebook": {"text": clip(nb, 1600), "updated_at": now().isoformat(timespec="seconds"), "day": day, "by": "digest"}})
        pt = clip(str(out.get("portrait") or "").strip(), 40)
        if pt and (st.profile().get("portrait") or {}).get("by") != "user":     # TA 亲手改过的那句不覆盖
            st.set_profile({"portrait": {"text": pt, "by": "digest", "updated_at": now().isoformat(timespec="seconds")}})
        if not summary:
            summary, _ = fallback_summary(mat)
    else:
        summary, highlights = fallback_summary(mat)

    stats = {
        "added": sum(1 for a in applied if a["op"] == "ADD" and a.get("status") != "guess"),
        "guesses": sum(1 for a in applied if a["op"] == "ADD" and a.get("status") == "guess"),
        "updated": sum(1 for a in applied if a["op"] == "UPDATE"),
        "deleted": sum(1 for a in applied if a["op"] == "DELETE"),
        "rejected": len(rejected),
        "user_lines": len(mat["user_lines"]), "long_pastes": mat["long_pastes"],
    }
    ops_log = [{"op": a["op"], "text": a.get("text", ""), "old": a.get("old", ""), "kind": a.get("kind", ""),
                "status": a.get("status", "")} for a in applied]
    st.save_digest(day, summary, highlights, stats, ops_log, bool(out), page)
    st.set_profile({"last_digest_day": day})
    st.log("memory", f"整理了 {day[5:]} 的记忆：新记 {stats['added']}，更新 {stats['updated']}，待确认 {stats['guesses']}")
    return {"day": day, "summary": summary, "highlights": highlights, "page": page, "stats": stats, "ops": ops_log,
            "rejected": rejected, "by_model": bool(out)}


def apply(st: Store, ops: list, known: dict, mat: dict, day: str) -> tuple[list[dict], list[dict]]:
    """Apply defensively. Every refusal is recorded so the behaviour is testable."""
    said = "\n".join(mat["user_lines"])
    applied, rejected, guesses = [], [], 0
    for op in ops[:12]:
        if not isinstance(op, dict):
            continue
        act = str(op.get("op") or "").upper()
        text = clip(str(op.get("text") or ""), 80).strip()
        kind = op.get("kind") if op.get("kind") in KINDS else "insight"
        evidence = clip(str(op.get("evidence") or ""), 200).strip()
        target = known.get(op.get("id") or "")
        if act == "ADD":
            if not text:
                continue
            if any(text == m["text"] for m in known.values()):
                rejected.append({"op": act, "text": text, "why": "duplicate"})
                continue
            is_guess = op.get("source") == "guess"
            if is_guess:
                if guesses >= 1:
                    rejected.append({"op": act, "text": text, "why": "guess limit"})
                    continue
                guesses += 1
            cat = op.get("cat") if op.get("cat") in ("effort", "people", "likes", "self", "recent", "rules") else ""
            m = st.add_memory(text, kind, "digest", "guess" if is_guess else "active", cat=cat)
            applied.append({"op": "ADD", "text": m["text"], "kind": kind, "status": m["status"]})
        elif act in ("UPDATE", "DELETE"):
            if not target:
                rejected.append({"op": act, "text": text, "why": "unknown id"})
                continue
            if target["source"] in PROTECTED and not (evidence and evidence in said):
                rejected.append({"op": act, "text": target["text"], "why": "protected without verbatim evidence"})
                continue
            if act == "UPDATE":
                if not text:
                    continue
                m = st.update_memory(target["id"], text=text, reason="digest:" + day, evidence=evidence)
                applied.append({"op": "UPDATE", "text": m["text"], "old": target["text"], "kind": target["kind"]})
            else:
                st.delete_memory(target["id"], reason="digest:" + day, evidence=evidence)
                applied.append({"op": "DELETE", "text": "", "old": target["text"], "kind": target["kind"]})
    return applied, rejected


def due(st: Store, ref=None) -> str | None:
    """Which day still needs its nightly pass. Runs after 03:00 for 'yesterday'."""
    ref = ref or now()
    if ref.hour < 3:
        return None
    yday = day_key(ref - timedelta(days=1))
    last = st.profile().get("last_digest_day") or ""
    if last >= yday:
        return None
    return yday
