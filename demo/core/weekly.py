"""小光的笔记本：一周一页。

这个产品不需要 TA 天天来，一天一页会很空；所以笔记本按周写：
  - 每周日夜里（周一 03:00 之后，跑完周日的夜里整理），小光把上一周零散的事想一想，写成一页：
    小标题、几句话、最多两句 TA 的原话、页边「这周的小事」几条。
  - 这一周还没过完时，笔记本最上面是「这周到现在」：代码从 TA 记下的、做完的事里拣几条碎片，不调模型；
    TA 也可以点「先把这周写下来」，小光先写一版草稿（final=0），周日夜里再重写成定稿。
  - 一周什么都没有，就不写这一页（不留空白页）。
每天的夜里整理（core/digest.py）照常做记忆和首页那句话，不再写页。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import finds, llm
from .util import clip, iso, now

LABEL = {"good": "小确幸", "rest": "休息日", "find": "新发现"}
WD = "一二三四五六日"

PROMPT = """你是陪伴者「小光」。这是你自己的笔记本，一周写一页。本子是你的，但 TA 会翻开看，所以对 TA 说「你」，说自己用「我」。
下面是 TA 这一周的材料。把这一周零零散散的事想一想，写成一页。

- title：这一页的小标题，≤12 字。从这一周里取一个具体的东西：一样东西、一句话、一个时刻
  （如「多买的一个包子」「声音在抖的那一次」「凌晨一点的猫咪视频」）。不要「充实的一周」「这周的你」这种空标题。
- body：3–5 句，合起来 ≤180 字。**不要按时间顺序一件件写**（「周一……后来……周四……」）。
  先从这一周里挑 2–3 件彼此有关系的事，说出它们之间的那根线：一个反复出现的细节、一个前后的变化、你在意的人或东西，
  或者我自己读到时的感受。别的事放进 bits，不用都写进来。写具体的细节，像随手写在本子上的话。
  body 里转述 TA 的话要换成「你」的说法（TA 写「她说像我」，你写「她说像你」）；一字不差的原话放进 quotes。
  只有材料里给了「上一页」时，才可以说和上一页的呼应；没给就不要提「上一页」「上周」。
  这一周只有一两件小事，就写短一点，两三句也行。
- quotes：从 TA 这一周自己写下或说出的话里，**一字不差**地摘 1–2 句最想留下的（每句 ≤30 字）；没有合适的就给空列表。
- bits：页边的「这周的小事」，2–4 条，每条 ≤14 字，像随手记在边上的词组（「最后一份糖醋排骨」「Mia 约了英语角」）。
  只写材料里真有的事，挑有画面的、有点意思的，不写「完成 3 个小步」这种统计。
- 不说教、不喊口号、不打分；不用「不是……而是……」「旅程」「见证」「闪闪发光」「值得被看见」「每一步都算数」「温柔地」，
  也不用「你在往前走」「一步一步」「慢慢来也没关系」这种谁都能说的收尾；结尾宁可停在一个具体的细节上。不用破折号（——）。

例（别的用户的，只看感觉，不要照抄）：
{"title":"多买的一个包子","body":"这周有两个早上，你多买了一个包子给同桌，自己那个凉了才吃。周三你又先帮室友改完简历，才开始写自己的。你好像总是先把别人安顿好，再轮到自己。周五你说想一个人去江边走走，我觉得挺好，那天是留给你自己的。","quotes":["她说好吃，我就觉得今天值了"],"bits":["多买的包子","室友的简历","一个人去江边"]}

只输出 JSON：{"title":"...","body":"...","quotes":["..."],"bits":["..."]}"""


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_key(ref: datetime | None = None) -> str:
    return monday((ref or now()).date()).isoformat()


def week_days(week: str) -> tuple[str, str]:
    start = date.fromisoformat(week)
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


def _md(day: str) -> str:
    d = date.fromisoformat(day[:10])
    return f"{d.month}月{d.day}日（周{WD[d.weekday()]}）"


def material(st, week: str) -> tuple[str, str, int]:
    """这一周给模型看的材料、核对原话用的语料、「事」的数量。"""
    a, b = week_days(week)
    lo, hi = a, b + "T99"
    out = [f"这一周：{_md(a)} 到 {_md(b)}"]
    prev = st.week_page((date.fromisoformat(week) - timedelta(days=7)).isoformat())
    if prev and (prev.get("page") or {}).get("body"):
        pg = prev["page"]
        out += ["", "## 上一页（上一周）", f"《{pg.get('title', '')}》{pg['body']}"]
    else:
        out += ["", "## 上一页", "（没有。这是笔记本里关于 TA 的第一页，不要提上一页、上周）"]
    nb = (st.profile().get("notebook") or {}).get("text") or ""
    if nb:
        out += ["", "## 笔记本里整理好的要点（背景，不是这周的事）", clip(nb, 800)]
    corpus = []
    digs = [d for d in st.digests(60) if a <= d["day"] <= b]
    if digs:
        out += ["", "## 每天夜里整理时写下的一句"] + [f"- {_md(d['day'])} {d['summary']}" for d in reversed(digs)]
        learned = [o.get("text") for d in digs for o in d.get("ops") or [] if o.get("op") in ("ADD", "UPDATE") and o.get("text")]
        if learned:
            out += ["", "## 这周新知道的关于 TA 的事"] + [f"- {t}" for t in learned]
    recs = [dict(r) for r in st.c.execute("SELECT type, text, day, created_at FROM record WHERE day>=? AND day<=? AND type!='meme' ORDER BY created_at", (a, b))]
    if recs:
        out += ["", "## TA 记下的"] + [f"- {_md(r['day'])} {r['created_at'][11:16]} [{LABEL.get(r['type'], r['type'])}] {r['text']}" for r in recs]
        corpus += [r["text"] for r in recs]
    done = [dict(r) for r in st.c.execute("SELECT title, done_at FROM step WHERE status='done' AND done_at>=? AND done_at<=? ORDER BY done_at", (lo, hi))]
    if done:
        out += ["", "## 做完的小步"] + [f"- {_md(s['done_at'])} {s['title']}" for s in done]
    moms = [dict(r) for r in st.c.execute("SELECT day, text, feeling FROM moment WHERE day>=? AND day<=? ORDER BY day", (a, b))]
    if moms:
        out += ["", "## TA 在成长轨迹上写的瞬间"] + [f"- {_md(m['day'])} {m['text']}" + (f"（{m['feeling']}）" if m["feeling"] else "") for m in moms]
        corpus += [m["text"] + " " + (m["feeling"] or "") for m in moms]
    kicks = [dict(r) for r in st.c.execute("SELECT day, task FROM kick_memory WHERE day>=? AND day<=?", (a, b))]
    if kicks:
        out += ["", "## 用两分钟启动开始的事"] + [f"- {_md(k['day'])} {k['task']}" for k in kicks]
    msgs = [dict(r) for r in st.c.execute("SELECT content, created_at FROM msg WHERE role='user' AND created_at>=? AND created_at<=? "
                                          "ORDER BY created_at", (lo, hi)) if len(r["content"] or "") <= 1200]
    if msgs:
        pick = msgs if len(msgs) <= 70 else msgs[:20] + msgs[-50:]
        out += ["", "## TA 在聊天里说的话"] + [f"- {_md(m['created_at'])} {m['created_at'][11:16]} {clip(m['content'], 100)}" for m in pick]
        corpus += [m["content"] for m in msgs]
    things = len(recs) + len(done) + len(moms) + len(kicks) + len(msgs)
    return "\n".join(out), "\n".join(corpus), things


def clean(out, corpus: str) -> dict | None:
    if not isinstance(out, dict):
        return None
    pg = finds.page_clean({"title": out.get("title"), "body": out.get("body"), "quote": ""}, corpus)
    if not pg:
        return None
    pg["body"] = clip(str(out.get("body") or "").strip().replace("——", "，"), 260)
    qs = []
    for q in (out.get("quotes") or [])[:3]:
        q = clip(str(q).strip().strip("「」\"“”"), 40)
        if q and finds._norm(q) and finds._norm(q) in finds._norm(corpus) and q not in qs:
            qs.append(q)
    bits = [clip(str(x).strip().strip("「」"), 16) for x in (out.get("bits") or []) if str(x).strip()][:4]
    return {"title": pg["title"], "body": pg["body"], "quotes": qs[:2], "bits": bits}


def write(st, week: str, final: bool = True) -> dict | None:
    """写这一周的一页；材料是空的或模型没写好就不写，返回 None。"""
    text, corpus, things = material(st, week)
    if not things:
        return None
    out = llm.complete_json([{"role": "system", "content": PROMPT}, {"role": "user", "content": clip(text, 14000)}], timeout=90)
    page = clean(out, corpus)
    if not page:
        return None
    st.save_week(week, page, final)
    st.log("memory", f"小光把 {week[5:]} 那一周写进了笔记本：「{page['title']}」")
    return page


def due(st, ref: datetime | None = None) -> str | None:
    """上一周的定稿还没写：周一 03:00 之后返回上一周的 key（周日的夜里整理先跑完）。一周只试一次。"""
    ref = ref or now()
    this = monday(ref.date())
    if ref.date() == this and ref.hour < 3:
        return None
    last = (this - timedelta(days=7)).isoformat()
    if (st.profile().get("last_week_page") or "") >= last:
        return None
    have = st.week_page(last)
    if have and have.get("final"):
        st.set_profile({"last_week_page": last})
        return None
    return last


def run_due(st) -> dict | None:
    wk = due(st)
    if not wk:
        return None
    page = write(st, wk, final=True)
    st.set_profile({"last_week_page": wk})
    return page


def scraps(st, ref: datetime | None = None) -> list[dict]:
    """这周到现在的碎片（不调模型）：TA 记下的、做完的、写下的瞬间，新的在前，最多 6 条。"""
    a, b = week_days(week_key(ref))
    items = []
    for r in st.c.execute("SELECT type, text, created_at FROM record WHERE day>=? AND day<=? AND type IN ('good','find')", (a, b)):
        items.append({"at": r["created_at"], "kind": r["type"], "text": clip(r["text"], 40)})
    for r in st.c.execute("SELECT title, done_at FROM step WHERE status='done' AND done_at>=? AND done_at<=?", (a, b + "T99")):
        items.append({"at": r["done_at"], "kind": "step", "text": clip(r["title"], 40)})
    for r in st.c.execute("SELECT text, created_at FROM moment WHERE day>=? AND day<=?", (a, b)):
        items.append({"at": r["created_at"], "kind": "moment", "text": clip(r["text"], 40)})
    items.sort(key=lambda x: x["at"] or "", reverse=True)
    out = []
    for x in items:      # 同一件事记成了好消息又写成瞬间，只留一条
        if not any(finds._sim(x["text"], y["text"]) > 0.5 for y in out):
            out.append(x)
    return out[:6]


def view(st) -> dict:
    """给页面用：这一周（草稿或碎片）+ 已经写好的几页（新的在前）。"""
    cur = week_key()
    pages = st.week_pages(16)
    return {"current": cur, "draft": next((p for p in pages if p["week"] == cur), None),
            "pages": [p for p in pages if p["week"] < cur], "scraps": scraps(st),
            "created": (st.profile().get("created_at") or "")[:10]}
