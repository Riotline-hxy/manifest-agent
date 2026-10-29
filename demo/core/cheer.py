"""小光面板顶部的一句话，每 12 小时换一次（0 点和 12 点各一个时段）。

两种：
  - 「最近的你」：从最近 7 天真实发生的事里写一句，只用材料里的事实；
  - 「送你一句」：从下面这份核对过出处的名句里挑，按用户的愿望类别优先。
先立刻给出一句（名句或模板），模型可用且最近有材料时，在后台把这个时段换成「最近的你」。
"""
from __future__ import annotations

import hashlib
import os
import threading
from datetime import timedelta

from . import llm
from .store import Store
from .util import clip, day_key, iso, now

# (句子, 出处, 适合的愿望类别)
QUOTES = [
    ("千里之行，始于足下。", "《道德经》", ("other", "body", "wealth")),
    ("不积跬步，无以至千里。", "荀子《劝学》", ("wealth", "body", "confidence")),
    ("锲而不舍，金石可镂。", "荀子《劝学》", ("wealth", "body")),
    ("博观而约取，厚积而薄发。", "苏轼《稼说送张琥》", ("wealth",)),
    ("莫听穿林打叶声，何妨吟啸且徐行。", "苏轼《定风波》", ("calm", "confidence")),
    ("竹杖芒鞋轻胜马，谁怕？一蓑烟雨任平生。", "苏轼《定风波》", ("confidence", "freedom")),
    ("此心安处是吾乡。", "苏轼《定风波·常羡人间琢玉郎》", ("calm", "relation")),
    ("人生如逆旅，我亦是行人。", "苏轼《临江仙·送钱穆父》", ("freedom", "calm")),
    ("行到水穷处，坐看云起时。", "王维《终南别业》", ("calm", "freedom")),
    ("长风破浪会有时，直挂云帆济沧海。", "李白《行路难》", ("wealth", "confidence")),
    ("山重水复疑无路，柳暗花明又一村。", "陆游《游山西村》", ("other", "calm")),
    ("路漫漫其修远兮，吾将上下而求索。", "屈原《离骚》", ("wealth", "other")),
    ("天行健，君子以自强不息。", "《周易》", ("body", "wealth")),
    ("知者不惑，仁者不忧，勇者不惧。", "《论语·子罕》", ("confidence", "calm")),
    ("好的开始是成功的一半。", "亚里士多德", ("other", "body")),
    ("最好的出路，永远是穿过去。", "罗伯特·弗罗斯特", ("confidence", "other")),
    ("我不怕暴风雨，因为我正在学习如何驾驶我的船。", "路易莎·梅·奥尔科特《小妇人》", ("confidence", "freedom")),
    ("生活中没有什么可怕的东西，只有需要理解的东西。", "居里夫人", ("calm", "confidence")),
]

PROMPT = """你是陪伴型 agent「小光」。根据这个人最近 7 天真实发生的事，写一句给 TA 的话，放在「最近的你」下面。
要求：
- 一句话，14–26 个字，第二人称，温和、具体，像朋友随口说的；
- 只用材料里的事实，可以概括（比如「这周你三次先开口了」），不要编；
- 不说教，不鸡血，不用感叹号；
- 不要用「不是……而是……」「这不是……」这种转折句式，直接说看到的；
- 材料太少写不出具体的话，就返回 {"skip": true}。
只输出 JSON：{"text":"..."} 或 {"skip": true}"""

_inflight: set[tuple[str, str]] = set()
_guard = threading.Lock()


def slot(ref=None) -> str:
    ref = ref or now()
    return f"{day_key(ref)}-{'am' if ref.hour < 12 else 'pm'}"


def material(st: Store) -> list[str]:
    since = (now().date() - timedelta(days=6)).isoformat()
    out = []
    for r in st.c.execute("SELECT day, text, feeling FROM moment WHERE day>=? ORDER BY day", (since,)):
        out.append(f"{r['day'][5:]} 在计划里记下：{r['text']}" + (f"（感受：{r['feeling']}）" if r["feeling"] else ""))
    for r in st.c.execute("SELECT day, type, text FROM record WHERE day>=? AND type IN ('good','meme','find') ORDER BY day", (since,)):
        out.append(f"{r['day'][5:]} {'内心戏' if r['type'] == 'meme' else '小确幸'}：{r['text']}")
    for r in st.c.execute("SELECT title, done_at FROM step WHERE status='done' AND substr(done_at,1,10)>=?", (since,)):
        out.append(f"{r['done_at'][5:10]} 完成小步：{r['title']}")
    for r in st.c.execute("SELECT h.title, COUNT(*) n FROM habit_log l JOIN habit h ON h.id=l.habit_id WHERE l.day>=? GROUP BY h.id", (since,)):
        out.append(f"这周「{r['title']}」打卡 {r['n']} 次")
    for r in st.c.execute("SELECT title FROM milestone WHERE status='done' AND substr(done_at,1,10)>=?", (since,)):
        out.append(f"到达里程碑：{r['title']}")
    n_rest = st.c.execute("SELECT COUNT(*) FROM record WHERE type='rest' AND day>=?", (since,)).fetchone()[0]
    if n_rest:
        out.append(f"给自己放了 {n_rest} 天假")
    return out


def pick_quote(st: Store, s: str, avoid: str = "") -> dict:
    cats = [r[0] for r in st.c.execute("SELECT category FROM wish WHERE archived=0")]
    pool = [q for q in QUOTES if any(c in q[2] for c in cats)] or QUOTES
    pool = [q for q in pool if q[0] != avoid] or pool
    i = int(hashlib.sha1((st.uid + s).encode()).hexdigest(), 16) % len(pool)
    text, src, _ = pool[i]
    return {"slot": s, "kind": "quote", "label": "送你一句", "text": text, "source": src, "at": iso()}


def get(st: Store, spawn: bool = True) -> dict:
    s = slot()
    c = st.profile().get("cheer") or {}
    if c.get("slot") == s and c.get("text"):
        return c
    c = pick_quote(st, s, avoid=c.get("text") or "")
    st.set_profile({"cheer": c})
    # 后台改写和定时任务同开关（测试、本地调试时关掉）
    if spawn and os.environ.get("MANIFEST_SCHEDULER", "1") != "0" and len(material(st)) >= 2:
        _spawn(st.uid, s)
    return c


def _spawn(uid: str, s: str) -> None:
    key = (uid, s)
    with _guard:
        if key in _inflight:
            return
        _inflight.add(key)

    def work():
        try:
            refresh(uid, s)
        finally:
            with _guard:
                _inflight.discard(key)
    threading.Thread(target=work, daemon=True).start()


def refresh(uid: str, s: str) -> dict | None:
    with Store(uid) as st:
        mat = material(st)
        if len(mat) < 2:
            return None
        p = st.profile()
        out = llm.complete_json([
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": (f"称呼：{p.get('nickname') or '（没说）'}\n最近 7 天：\n" + "\n".join("- " + clip(x, 80) for x in mat[:24]))},
        ], timeout=30)
        text = clip(str((out or {}).get("text") or "").strip(), 40)
        if not out or out.get("skip") or not text or "不是" in text:
            return None
        cur = st.profile().get("cheer") or {}
        if cur.get("slot") != s:      # 时段已经过去了
            return None
        c = {"slot": s, "kind": "you", "label": "最近的你", "text": text, "source": "", "at": iso()}
        st.set_profile({"cheer": c})
        return c
