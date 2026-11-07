"""小光的发现 + 笔记本这一页的把关。

「小光的发现」是小光翻自己的笔记本时注意到的、TA 自己可能没留意的事：一两句话，平实的或带一点诗意的，
每条背后至少有两件不同日子的真事（evidence）。夜里整理之后、隔几天写一次（due），最多留 12 条。
TA 点「不太像」的不再出现（profile.insight_fb，和旧的发现共用），之后写新的也会避开它。

把关（代码做，不靠模型自觉）：
  - 句子里用「」引的原话，必须能在 TA 自己写过的话里逐字找到，找不到整条不要；
  - 一串「AI 腔」的词（旅程、见证、不是……而是……等）出现就不要；
  - 和已有的、被说不像的太像（字面相似度）就不要。
"""
from __future__ import annotations

import re
from datetime import timedelta

from . import llm
from .util import clip, iso, new_id, now, parse_iso

KEEP = 12
EVERY_DAYS = 3
MIN_DAYS = 5
MIN_THINGS = 12

AI_WORDS = ("旅程", "见证", "闪闪发光", "值得被", "每一步都", "了不起", "宇宙", "能量", "成长之路", "蜕变之", "数据显示",
            "记录显示", "统计", "系统", "你是一个", "你真的很棒", "为你骄傲", "加油哦", "温柔地", "勇敢地", "光芒", "绽放")
NOT_BUT = re.compile(r"不是.{0,14}而是")
QUOTE = re.compile(r"「([^」]{2,40})」")
LABEL = {"good": "小确幸", "meme": "内心戏", "rest": "休息日", "find": "新发现"}

PROMPT = """你是陪伴者「小光」。夜里你翻着自己的笔记本，想写下一两件关于 TA 的、TA 自己可能都没注意到的事。
这些会放在 TA 的「我的空间 → 了解你 → 小光的发现」里，是整个页面最想让 TA 看的部分：要让 TA 读完心里动一下，
或者笑一下，觉得「你居然注意到了」。

怎么写：
1. 每条一到两句，≤36 字。两种语气都可以：
   - 平实的，像朋友顺口告诉你：「你记下的开心事，差不多一半和吃的有关。」
   - 带一点诗意、留白的：「周四晚上，你总会回来。」
2. 一条发现要把**至少两个不同日子**的事连起来，说出它们共同的那个东西，或者前后的变化。
   只复述一件发生过的事（「你说想早睡，结果凌晨一点还在看猫」）不算发现。
   撑着它的事写进 evidence（2–4 件，每件 ≤24 字，带日期，如「11月3日 你说……」）。
   只用下面材料里出现过的事。要引 TA 的原话就用「」，并且必须一字不差。
3. 最值得写的：反复出现的小细节；前后对照（以前怎样、现在怎样）；TA 在意却没说出口的；TA 和某个人、某样东西的关系；
   时间上的小规律；TA 说话的小习惯。
4. 不要：性格判断和贴标签（「你是一个……的人」）；拔高、鸡汤、喊口号；拿失败和没做到的次数说事；
   「数据显示」「统计」这种说法；「不是……而是……」；旅程、见证、闪闪发光、值得被看见、每一步都算数、温柔地。
5. 不要和「已经写过的」「TA 说不像的」重复或换个说法再写一遍；笔记本里某一晚已经写过的话也别原样搬，发现要比单独一晚看得更远。
   不用破折号（——），用逗号或句号。
6. 先在心里想 4–5 个候选，只留下最好的 1–2 条，每条打 score（1–5：TA 读到会不会心里一动、或者会心一笑）。
   4 分以下的不要写出来。材料不够、写不出让人心动的，就返回空列表。宁缺毋滥。

好的样子（别的用户的，只看感觉，不要照抄）：
- 你说「算了」的那两次，第二天都又试了一次。
- 你给别人带早饭的那几天，自己也起得特别早。
- 你很少说「我做到了」，都说「还行」。可那几次都是做到了。
- 下雨的日子，你记下的开心事反而更多。
不好的样子：你是一个坚持不懈的人 / 数据显示你周三最活跃 / 你的每一步都在发光 / 你不是在拖延，而是在积蓄力量

只输出 JSON：{"finds":[{"text":"...","evidence":["...","..."],"score":5}]}"""


# ---- 把关 --------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[\s，。！？、,.!?~～…\"'“”‘’]", "", s or "")


def ai_tone(text: str) -> bool:
    return bool(NOT_BUT.search(text)) or any(w in text for w in AI_WORDS)


def quotes_ok(text: str, corpus: str) -> bool:
    """句子里「」引的每一句，都得在 TA 写过的话里逐字找到（忽略标点空格）。"""
    c = _norm(corpus)
    return all(_norm(q) in c for q in QUOTE.findall(text or ""))


def _sim(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if len(a) < 2 or len(b) < 2:
        return 0.0
    x = {a[i:i + 2] for i in range(len(a) - 1)}
    y = {b[i:i + 2] for i in range(len(b) - 1)}
    return 2 * len(x & y) / (len(x) + len(y))


def page_clean(page, corpus: str) -> dict | None:
    """笔记本这一页：{title, body, quote}。quote 不是原话就去掉；没有 body 就不要这一页。"""
    if not isinstance(page, dict):
        return None
    title = clip(str(page.get("title") or "").strip().strip("「」\"“”"), 14)
    body = clip(str(page.get("body") or "").strip().replace("——", "，"), 160)
    quote = clip(str(page.get("quote") or "").strip().strip("「」\"“”"), 40)
    if len(body) < 8:
        return None
    if quote and _norm(quote) not in _norm(corpus):
        quote = ""
    return {"title": title or "这一天", "body": body, "quote": quote}


# ---- 发现 --------------------------------------------------------------------

def view(st) -> list[dict]:
    """给页面用：TA 没说「不太像」的，新的在前。"""
    p = st.profile()
    fb = p.get("insight_fb") or {}
    out = []
    for f in p.get("finds") or []:
        if not isinstance(f, dict) or fb.get(f.get("id")) == "no":
            continue
        out.append({**f, "fb": fb.get(f.get("id"), "")})
    return out


def liked(st) -> list[str]:
    """TA 点过「像我」的发现，给对话用。"""
    return [f["text"] for f in view(st) if f["fb"] == "yes"]


def _user_corpus(st, since: str) -> tuple[list[str], str]:
    lines = [r[0] for r in st.c.execute("SELECT content FROM msg WHERE role='user' AND created_at>=? ORDER BY created_at",
                                        (since,)) if r[0] and len(r[0]) <= 1200]
    extra = [r[0] for r in st.c.execute("SELECT text FROM record WHERE created_at>=?", (since,))]
    extra += [r[0] for r in st.c.execute("SELECT text || ' ' || COALESCE(feeling,'') FROM moment WHERE day>=?", (since[:10],))]
    extra += [r[0] for r in st.c.execute("SELECT text FROM memory WHERE status='active'")]
    return lines, "\n".join(lines + [e or "" for e in extra])


def _md(s: str) -> str:
    d = parse_iso(s) if s and "T" in s else None
    if d:
        return f"{d.month}月{d.day}日"
    try:
        return f"{int(s[5:7])}月{int(s[8:10])}日"
    except (ValueError, TypeError):
        return s or ""


def material(st) -> tuple[str, str, int]:
    """给模型看的材料、用来核对原话的语料、材料里「事」的数量。"""
    from . import portrait
    p = st.profile()
    since = (now() - timedelta(days=45)).isoformat(timespec="seconds")
    lines, corpus = _user_corpus(st, since)
    out = [f"认识 TA {st.counts().get('days', 1)} 天。"]
    nb = (p.get("notebook") or {}).get("text") or ""
    if nb:
        out += ["", "## 笔记本里整理好的要点", nb]
    mems = [m["text"] for m in st.memories(statuses=("active",), limit=60)]
    if mems:
        out += ["", "## 记得的事"] + [f"- {t}" for t in mems]
    pages = []
    for d in st.digests(21):
        pg = d.get("page") or {}
        pages.append(f"- {_md(d['day'])}《{pg.get('title', '')}》{pg.get('body', '')}" if pg.get("body") else f"- {_md(d['day'])} {d['summary']}")
    if pages:
        out += ["", "## 笔记本里每晚写的（新的在前）"] + pages
    recs = [r for r in st.records(80) if (r.get("created_at") or "") >= since]
    if recs:
        out += ["", "## TA 记下的（小确幸、内心戏、休息日）"] + [
            f"- {_md(r['created_at'])} {r['created_at'][11:16]} [{LABEL.get(r['type'], r['type'])}] {r['text']}" for r in recs]
    done = [s for s in st.steps(200) if s["status"] == "done" and (s.get("done_at") or "") >= since]
    if done:
        out += ["", "## 做完的小步（加的日子 → 做完的日子）"] + [
            f"- {s['title']}（{_md(s.get('created_at') or '')} → {_md(s.get('done_at') or '')} {(s.get('done_at') or '')[11:16]}）" for s in done[:40]]
    moms = [dict(r) for r in st.c.execute("SELECT day, text, feeling FROM moment WHERE day>=? ORDER BY day", (since[:10],))]
    if moms:
        out += ["", "## TA 在成长轨迹上写的瞬间"] + [f"- {_md(m['day'])} {m['text']}" + (f"（{m['feeling']}）" if m["feeling"] else "") for m in moms]
    rows = [dict(r) for r in st.c.execute("SELECT content, created_at FROM msg WHERE role='user' AND created_at>=? "
                                           "ORDER BY created_at DESC LIMIT 80", (since,))]
    said = [f"- {_md(r['created_at'])} {r['created_at'][11:16]} {clip(r['content'], 80)}" for r in reversed(rows) if len(r["content"]) <= 1200]
    if said:
        out += ["", "## TA 在聊天里说的话（节选）"] + said
    stats = []
    for f in portrait.insights(st):
        if f.get("ready") and not f.get("flat"):
            stats.append(f"- {f['a']}（{f['src']}）" + ("；" + "；".join(f.get("evidence") or []) if f.get("evidence") else ""))
    if stats:
        out += ["", "## 算出来的小规律（可以用，但要说成人话，别说「统计」）"] + stats
    old = [f["text"] for f in p.get("finds") or [] if isinstance(f, dict)]
    fb = p.get("insight_fb") or {}
    no = [f["text"] for f in p.get("finds") or [] if isinstance(f, dict) and fb.get(f.get("id")) == "no"]
    out += ["", "## 已经写过的（不要重复）"] + ([f"- {t}" for t in old] or ["（还没有）"])
    if no:
        out += ["", "## TA 说不像的（不要再往这个方向写）"] + [f"- {t}" for t in no]
    things = len(recs) + len(done) + len(moms) + len(said)
    return "\n".join(out), corpus, things


def due(st, ref=None) -> bool:
    ref = ref or now()
    p = st.profile()
    if st.counts().get("days", 1) < MIN_DAYS:
        return False
    last = parse_iso(p.get("finds_at") or "")
    return not last or (ref - last) >= timedelta(days=EVERY_DAYS) - timedelta(hours=2)


def discover(st, force: bool = False) -> list[dict]:
    """写新的发现；返回这次加上的。材料不够、模型没写出好的，就什么都不加。"""
    if not force and not due(st):
        return []
    text, corpus, things = material(st)
    if things < MIN_THINGS and not force:
        return []
    out = llm.complete_json([{"role": "system", "content": PROMPT}, {"role": "user", "content": clip(text, 14000)}], timeout=90)
    st.set_profile({"finds_at": iso()})
    if not out:
        return []
    p = st.profile()
    have = [f for f in p.get("finds") or [] if isinstance(f, dict)]
    added = []
    for f in (out.get("finds") or [])[:2]:
        if not isinstance(f, dict):
            continue
        t = clip(str(f.get("text") or "").strip().replace("——", "，").replace("—", "，"), 60)
        ev = [clip(str(e).strip(), 40) for e in (f.get("evidence") or []) if str(e).strip()][:4]
        try:
            score = float(f.get("score") or 5)
        except (TypeError, ValueError):
            score = 5
        if score < 4 or len(t) < 6 or len(ev) < 2 or ai_tone(t) or not quotes_ok(t, corpus):
            continue
        if any(_sim(t, h["text"]) > 0.55 for h in have + added):
            continue
        added.append({"id": new_id("fd"), "text": t, "evidence": ev, "at": iso()})
    if added:
        fb = p.get("insight_fb") or {}
        keep = added[::-1] + have
        liked_ = [f for f in keep if fb.get(f["id"]) == "yes"]
        rest = [f for f in keep if fb.get(f["id"]) != "yes"]
        keep = (liked_ + rest)[:KEEP] if len(keep) > KEEP else keep
        keep.sort(key=lambda f: f.get("at") or "", reverse=True)
        st.set_profile({"finds": keep})
    return added
