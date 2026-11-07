"""小光面板顶部的一句话。只有两种，打开面板时随机给一句，点一下换一句：

  - 「最近的你」：从最近 7 天真实发生的事里写一句（第二人称），每 12 小时（0 点 / 12 点）在后台更新一次；
  - 「对自己说」：第一人称的内心肯定语（affirmation），像「我值得拥有精彩的人生。」，按用户的愿望类别挑。

没有足够材料时没有「最近的你」，只显示肯定语。
"""
from __future__ import annotations

import os
import threading
from datetime import timedelta

from . import llm
from .store import Store
from .util import clip, day_key, iso, now, parse_iso

# (肯定语, 适合的愿望类别；general 对谁都合适)
AFFIRMATIONS = [
    ("我值得拥有精彩的人生。", "general"),
    ("好事正在向我靠近。", "general"),
    ("我正在一点点成为想成为的人。", "general"),
    ("今天的我已经足够好。", "general"),
    ("我欣赏今天认真生活的自己。", "general"),
    ("我的努力正在悄悄累积。", "general"),
    ("我相信自己的节奏。", "general"),
    ("事情会按照所需的方式得到解决。", "general"),
    ("我允许自己慢慢来。", "calm"),
    ("平静一直在我心里，我随时可以回到那里。", "calm"),
    ("我可以放下今天放不下的事。", "calm"),
    ("我允许自己好好休息。", "calm"),
    ("我说出的想法值得被听见。", "confidence"),
    ("我对自己有耐心，也有信心。", "confidence"),
    ("我敢于尝试，也接纳不完美的自己。", "confidence"),
    ("我配得上被温柔对待。", "confidence"),
    ("我的身体在照顾我，我也在照顾它。", "body"),
    ("我的身体是一个奇迹。", "body"),
    ("我每天都在给身体一点好的东西。", "body"),
    ("我有能力创造更多的选择。", "wealth"),
    ("机会会在我准备好的时候出现。", "wealth"),
    ("我做的事情正在变得有价值。", "wealth"),
    ("我在关系里可以安心说出自己的需要。", "relation"),
    ("我值得被理解，也愿意理解别人。", "relation"),
    ("我身边有爱我的人。", "relation"),
    ("我正在创造自己喜欢的生活。", "freedom"),
    ("我有选择，也有改变的力量。", "freedom"),
    ("我愿意给新的可能一个开始。", "freedom"),
]

PROMPT = """你是陪伴型 agent「小光」。根据这个人最近 7 天真实发生的事，写一句给 TA 的话，放在「最近的你」下面。
要求：
- 一句话，14–26 个字，第二人称，温和、具体，像朋友随口说的；
- 只用材料里的事实，可以概括（比如「这周你三次先开口了」），不要编；
- 不说教，不鸡血，不用感叹号；
- 不要用「不是……而是……」「这不是……」这种转折句式，直接说看到的；
- 材料太少写不出具体的话，就返回 {"skip": true}。
只输出 JSON：{"text":"..."} 或 {"skip": true}"""

YOU_KEEP_DAYS = 3        # 「最近的你」超过 3 天没更新就不再显示
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
    for r in st.c.execute("SELECT day, type, text FROM record WHERE day>=? AND type IN ('good','find') ORDER BY day", (since,)):
        out.append(f"{r['day'][5:]} 小确幸：{r['text']}")
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


def affirmations(st: Store) -> list[str]:
    cats = {r[0] for r in st.c.execute("SELECT category FROM wish WHERE archived=0")}
    return [t for t, c in AFFIRMATIONS if c == "general" or c in cats]


def get(st: Store, spawn: bool = True) -> dict:
    """{"you": {"text", "at"} 或 None, "affirm": [...]}。进入新时段时在后台重写「最近的你」。"""
    c = st.profile().get("cheer") or {}
    s = slot()
    if c.get("slot") != s:
        st.set_profile({"cheer": {**c, "slot": s}})
        # 后台改写和定时任务同开关（测试、本地调试时关掉）
        if spawn and os.environ.get("MANIFEST_SCHEDULER", "1") != "0" and len(material(st)) >= 2:
            _spawn(st.uid, s)
    you = None
    if c.get("kind") == "you" and c.get("text"):
        at = parse_iso(c.get("at"))
        if at and (now() - at).days < YOU_KEEP_DAYS:
            you = {"text": c["text"], "at": c["at"]}
    return {"you": you, "affirm": affirmations(st)}


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


def refresh(uid: str, s: str | None = None) -> dict | None:
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
        c = {"slot": s or slot(), "kind": "you", "text": text, "at": iso()}
        st.set_profile({"cheer": c})
        return c
