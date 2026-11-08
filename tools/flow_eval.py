"""「许个愿」「让愿望落地」提示词的试跑：用真模型把几种结尾和建议跑一遍，打印出来看。

用法（在 manifest-agent 目录）：
  python tools/flow_eval.py            # 全跑：新愿望的愿望卡、坚定旧愿望的那句话、改小一点、再加一件、第一件事
  python tools/flow_eval.py new keep   # 只跑这几种（new / keep / smaller / add / first / words）
改了 demo/core/wish_flow.py（NEW、KEEP）或 demo/core/relearn.py（SMALLER、ADD、FIRST）以后跑一下，看：
  - 小光那句话有没有复述卡片上的东西、有没有说教和口号；
  - 「那一天」是不是用了 TA 选的画面、写得具体；
  - 改小一点的两个版本是不是还是这件事本身（小步要给做成它的第一下），而且明显更容易；
  - TA 自己写了一句（「我不知道怎么启动」「最近太忙」）：小光有没有听懂卡在哪、给的调整是不是对症。
用的是 .env 里的模型 key，数据写在临时目录，不碰真实用户。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent / "demo"
os.environ["MANIFEST_DATA"] = tempfile.mkdtemp(prefix="flow_eval_")
os.environ["MANIFEST_SCHEDULER"] = "0"
sys.path.insert(0, str(DEMO))
sys.stdout.reconfigure(encoding="utf-8")

from core.util import load_dotenv  # noqa: E402

load_dotenv(HERE.parent / ".env")
from core import journey, relearn, wish_flow  # noqa: E402
from core.store import Store  # noqa: E402

# 新愿望：(哪一块, 想要的, 那一天的画面, 未来的你说)
NEW = [
    ("people", "关系与表达", "敢在课上发言", "举手说话不再心跳加速", "谢谢你那时候开始了"),
    ("body", "身体与作息", "每天 12 点前睡", "早上不用闹钟也自然醒", ""),
    ("mood", "心情与内在", "对自己温柔一点", "对自己说话温柔了", "别急，你会走到的"),
    ("life", "生活与自由", "存下一笔旅行基金", "订好了想去的旅行", ""),
    ("", "", "学会弹一首完整的曲子", "", ""),
]
# 坚定旧愿望：(最有感觉的一刻, 现在心里)
# TA 自己写的：(这周的感觉) 和 (哪一件, 想怎么调时写的话)
FEEL_WORDS = ["期中周，啥都顾不上", "还行吧，就是单词老忘背", "说不上来，有点烦", "这周状态很好，还想多练点"]
ADJUST_WORDS = [("s1", "我不知道怎么启动"), ("h1", "最近太忙了，没时间"), ("h2", "老是忘"), ("h1", "一想到就烦，不想做"),
                ("s1", "怕约了 Mia 她不理我")]
KEEP = [("第一次在课上用英语提问，声音在抖但说完了", "still"), ("录了一段 30 秒的自我介绍", "far"),
        ("和 Mia 用英语聊了十分钟", "more"), ("", "unsure")]


def setup(st):
    st.set_profile({"nickname": "阿青", "persona": "gentle"})
    w = journey.add_wish(st, "敢开口说英语", "confidence", vision_text="能在小组讨论里自然地用英语说出自己的想法")
    h1 = journey.add_habit(st, w["id"], "每天背 20 个单词", "daily")
    h2 = journey.add_habit(st, w["id"], "跟读一段对话", "weekly", 3)
    s1 = st.add_step("约 Mia 周末练口语", wish_id=w["id"])
    journey.add_moment(st, w["id"], "第一次在课上用英语提问，声音在抖但说完了", source="user")
    empty = journey.add_wish(st, "睡好一点", "body", vision_text="早上醒来不再昏昏沉沉")
    return w, h1, h2, s1, empty


def timed(fn, *a):
    t = time.time()
    out = fn(*a)
    return out, time.time() - t


def main(kinds):
    with Store("u_" + "f" * 16) as st:
        w, h1, h2, s1, empty = setup(st)
        if "new" in kinds:
            print("\n=== 许个愿 · 新的愿望 ===")
            for area, label, want, day, words in NEW:
                a = wish_flow.clean(st, {"pick": "new", "area": area, "area_label": label, "want": want, "day": day, "words": words})
                e, s = timed(wish_flow.ending, st, a)
                print(f"\n[{label or '自己写'}] {want} / {day or '（没选画面）'}  {s:.1f}s{'' if e['by_model'] else '  （模型没回，用了写好的）'}")
                print(f"  愿望名：{e['card']['title']}\n  那一天：{e['day']}\n  小光：{e['say']}")
        if "keep" in kinds:
            print("\n=== 许个愿 · 已有的愿望 ===")
            for moment, heart in KEEP:
                a = wish_flow.clean(st, {"pick": w["id"], "moment": moment, "heart": heart, "onward": "慢一点也是在走"})
                e, s = timed(wish_flow.ending, st, a)
                print(f"\n[{moment or '没选那一刻'} · {wish_flow.HEART[heart]}]  {s:.1f}s\n  小光：{e['say']}")
        if "smaller" in kinds:
            print("\n=== 让愿望落地 · 改小一点 ===")
            for ref, label in (("h:" + h1["id"], ""), ("h:" + h2["id"], ""), ("s:" + s1["id"], ""), ("", "周末去图书馆自习")):
                out, s = timed(relearn.suggest, st, "smaller", w["id"], ref, label)
                name = label or next(i["label"] for i in relearn._items(st, w["id"]) if i["v"] == ref)
                print(f"\n[{name}]  {s:.1f}s\n  " + " / ".join(out["opts"]) + (f"\n  频率降一档：{out['ease']}" if out.get("ease") else ""))
        if "words" in kinds:
            print("\n=== 让愿望落地 · TA 自己写的感觉 ===")
            for t in FEEL_WORDS:
                out, s = timed(relearn.suggest, st, "feel", w["id"], "", "", t)
                print(f"\n[{t}]  {s:.1f}s  → {out['feel']}\n  小光：{out['say']}")
            print("\n=== 让愿望落地 · 「我想这样调……」自己写的 ===")
            refs = {"h1": "h:" + h1["id"], "h2": "h:" + h2["id"], "s1": "s:" + s1["id"]}
            for k, t in ADJUST_WORDS:
                out, s = timed(relearn.suggest, st, "adjust", w["id"], refs[k], "", t)
                name = next(i["label"] for i in relearn._items(st, w["id"]) if i["v"] == refs[k])
                print(f"\n[{name} · {t}]  {s:.1f}s\n  小光：{out['say']}\n  " + " / ".join(f"{o['kind']}「{o['text']}」" for o in out["opts"]))
        if "add" in kinds:
            print("\n=== 让愿望落地 · 挺顺的，再加一件 ===")
            out, s = timed(relearn.suggest, st, "add", w["id"])
            print(f"  {s:.1f}s  " + " / ".join(out["opts"]))
        if "first" in kinds:
            print("\n=== 让愿望落地 · 计划还是空的，第一件事 ===")
            out, s = timed(relearn.suggest, st, "first", empty["id"])
            print(f"  {s:.1f}s  " + " / ".join(out["opts"]))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or {"new", "keep", "smaller", "add", "first", "words"})
