"""「显化你的愿望」「调整现有计划」提示词的试跑：用真模型把每一步和结尾跑一遍，打印出来看。

用法（在 manifest-agent 目录）：
  python tools/flow_eval.py              # 全跑
  python tools/flow_eval.py manifest     # 只跑显化七步（新愿望 + 已有的愿望）
  python tools/flow_eval.py adjust       # 只跑调整现有计划（几种状态 + 一次重新调整）
改了 demo/core/manifest_flow.py（P 里每一步）或 demo/core/relearn.py（PLAN、REVISE）以后跑一下，看：
  - 小光每一步有没有接着 TA 的回答说，有没有说教、口号、玄的词；
  - 小纸条有没有用上 TA 说的那个声音、挑的那句话、今天要做的事，最后一句是不是落在自爱；
  - 调整方案是不是贴着状态（累就放轻、顺就加一点），每条都对得上计划里的东西。
用的是 .env 里的模型 key，数据写在临时目录，不碰真实用户。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent / "demo"
os.environ["MANIFEST_DATA"] = tempfile.mkdtemp(prefix="flow_eval_")
os.environ["MANIFEST_SCHEDULER"] = "0"
sys.path.insert(0, str(DEMO))
sys.stdout.reconfigure(encoding="utf-8")

from core.util import load_dotenv  # noqa: E402

load_dotenv(HERE.parent / ".env")
from core import journey, manifest_flow as mf, relearn  # noqa: E402
from core.store import Store  # noqa: E402


def timed(fn, *a):
    t = time.time()
    out = fn(*a)
    return out, time.time() - t


def setup(st):
    st.set_profile({"nickname": "阿青", "persona": "gentle"})
    w = journey.add_wish(st, "敢开口说英语", "confidence", vision_text="我在小组讨论里自然地用英语说出想法，大家都在认真听。")
    journey.add_habit(st, w["id"], "每天背 20 个单词", "daily")
    journey.add_habit(st, w["id"], "跟读一段对话", "weekly", 3)
    st.add_step("约 Mia 周末练口语", wish_id=w["id"])
    journey.add_milestone(st, w["id"], "能用英语做 3 分钟自我介绍", (date.today() + timedelta(days=10)).isoformat())
    w2 = journey.add_wish(st, "睡好一点", "body")
    journey.add_habit(st, w2["id"], "12 点前放下手机", "daily")
    return w


def manifest(st, w):
    print("\n=== 显化你的愿望 · 新的愿望（每一步都调一次模型）===")
    a = mf.clean(st, {"pick": "new", "want": "换一份喜欢的工作"})
    r, s = timed(mf.step, st, "spec", a)
    print(f"\n[1 说具体 · 换一份喜欢的工作] {s:.1f}s\n  小光：{r['say']}\n  " + " / ".join(r["opts"]))
    a = mf.clean(st, {**a, "spec": r["opts"][0], "feel": "平静"})
    r, s = timed(mf.step, st, "vision", a)
    print(f"\n[1 那一刻 · 平静] {s:.1f}s\n  画面：{r['vision']}\n  小光：{r['say']}")
    a = mf.clean(st, {**a, "vision": r["vision"], "doubt": "已经太晚了"})
    for kind, extra, show in [
        ("doubt", {}, lambda r: f"小光：{r['say']}\n  肯定语：" + " / ".join(r["opts"])),
        ("act", {}, lambda r: "今天去做：" + " / ".join(r["opts"])),
        ("test", {"test": "想将就一下"}, lambda r: f"小光：{r['say']}\n  " + " / ".join(r["opts"])),
        ("thanks", {"thanks": "我必须早起"}, lambda r: f"{r['line']}\n  小光：{r['say']}"),
        ("envy", {"envy": "有点酸"}, lambda r: f"小光：{r['say']}\n  可以学的：{r['learn']}"),
    ]:
        a = mf.clean(st, {**a, **extra})
        r, s = timed(mf.step, st, kind, a)
        print(f"\n[{kind}] {s:.1f}s\n  {show(r)}")
        if kind == "doubt":
            a = mf.clean(st, {**a, "aff": r["opts"][0]})
        if kind == "act":
            a = mf.clean(st, {**a, "act": r["opts"][0]})
            r2, s2 = timed(mf.step, st, "act_say", a)
            print(f"  小光（挑了第一件）：{r2['say']}  {s2:.1f}s")
        if kind == "test":
            a = mf.clean(st, {**a, "plan": r["opts"][0]})
        if kind == "thanks":
            a = mf.clean(st, {**a, "thanks_line": r["line"]})
        if kind == "envy":
            a = mf.clean(st, {**a, "learn": r["learn"]})
    for t in ("很急，想快点看到", "能慢慢等"):
        r, s = timed(mf.step, st, "trust", mf.clean(st, {**a, "trust": t}))
        print(f"\n[7 信任 · {t}] {s:.1f}s\n  小光：{r['say']}\n  " + " / ".join(r["opts"]))
    a = mf.clean(st, {**a, "trust": "很急，想快点看到", "letgo": r["opts"][0]})
    e, s = timed(mf.ending, st, a)
    print(f"\n[走完 · 小纸条] {s:.1f}s\n  {e['letter']}\n  最后一句：{e['card']['vow']}")

    print("\n=== 显化你的愿望 · 已有的愿望「敢开口说英语」===")
    a = mf.clean(st, {"pick": w["id"], "doubt": "怕别人怎么看", "aff": "我开口是为了把话说完", "act": "用英语点一次咖啡", "trust": "怕它一直不来"})
    for kind in ("doubt", "trust"):
        r, s = timed(mf.step, st, kind, a)
        print(f"\n[{kind}] {s:.1f}s\n  小光：{r['say']}\n  " + " / ".join(r["opts"]))
    e, s = timed(mf.ending, st, a)
    print(f"\n[走完 · 小纸条] {s:.1f}s\n  {e['letter']}\n  最后一句：{e['card']['vow']}")


def adjust(st):
    print("\n=== 调整现有计划 ===")
    cases = [("busy", "seed", "full"), ("slow", "seed", "none"), ("steady", "sprout", "stuck"), ("change", "more", "smooth")]
    first = None
    for s_, e_, f_ in cases:
        a = relearn.clean(st, {"state": s_, "energy": e_, "feel": f_})
        e, s = timed(relearn.ending, st, a)
        first = first or (a, e)
        print(f"\n[{a['state'].split('（')[0]} · {a['energy'].split('（')[0]} · {a['feel'].split('（')[0]}] {s:.1f}s\n  小光：{e['say']}")
        for c in e["changes"]:
            print(f"  {c['label']} · {c['target']} → {c['to']}（{c['why']}）")
    a, e = first
    r, s = timed(relearn.revise, st, a, e, "背单词我不想减，别的可以")
    print(f"\n[重新调 · 背单词我不想减，别的可以] {s:.1f}s\n  小光：{r['say']}")
    for c in r["changes"]:
        print(f"  {c['label']} · {c['target']} → {c['to']}（{c['why']}）")


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"manifest", "adjust"}
    with Store("u_" + "f" * 16) as st:
        w = setup(st)
        if "manifest" in which:
            manifest(st, w)
        if "adjust" in which:
            adjust(st)
