"""两分钟启动提示词的试跑：几个说得很短、容易误解的任务，用真模型拆一遍，打印「理解 / 路线 / 调整后」。

用法（在 manifest-agent 目录）：
  python tools/kick_eval.py                 # 默认那一组
  python tools/kick_eval.py 学穿搭:low 练琴    # 只跑这几个，冒号后面是模式（default / low）
  python tools/kick_eval.py talk              # 只跑带「调整路线 / 遇到困难」的几个
改了 demo/core/kick_prompts.py 以后跑一下，看理解得对不对、第一步是不是直接通向这件事。
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
os.environ["MANIFEST_DATA"] = tempfile.mkdtemp(prefix="kick_eval_")
os.environ["MANIFEST_SCHEDULER"] = "0"
sys.path.insert(0, str(DEMO))
sys.stdout.reconfigure(encoding="utf-8")

from core.util import load_dotenv  # noqa: E402

load_dotenv(HERE.parent / ".env")
from core import kickstart  # noqa: E402
from core.store import Store  # noqa: E402

# (任务, 模式, 这个人的愿望或要点, 做到第一步时说的一句「调整路线」/「遇到困难」)
CASES = [
    ("学穿搭", "default", None, None),
    ("学穿搭", "low", None, None),
    ("学穿搭", "default", {"wish": "变得更会打扮"}, ("adjust", "不是这个意思，我想在网上学")),
    ("学剪辑", "default", None, None),
    ("学做饭", "default", None, None),
    ("练口语", "default", None, None),
    ("整理房间", "default", None, None),
    ("投简历", "default", None, None),
    ("做PPT", "low", None, None),
    ("复习高数", "default", None, None),
    ("回妈妈消息", "default", None, None),
    ("起床", "low", None, ("stuck", "房间好冷，不想离开被窝")),
    ("跑步", "default", {"memory": "TA 住学校宿舍，晚上操场开放"}, None),
    ("写周报", "default", None, ("stuck", "一打开电脑就想刷手机")),
    ("练琴", "default", None, ("adjust", "我没有琴，用手机上的钢琴App")),
]


def show(r: dict, head: str) -> None:
    print(head)
    if r.get("guess"):
        print("  理解：", r["guess"])
    print("  说：", r.get("say") or "")
    for i, s in enumerate(r["route"]):
        mark = "✓" if s["state"] == "done" else "→" if i == r["cur"] else "·"
        print(f"  {mark} {s['title']}｜{s['tip']}（{s['minutes']}）")


def main(argv: list[str]) -> None:
    cases = CASES
    if argv == ["talk"]:          # 只跑带「调整路线 / 遇到困难」的几个
        cases = [c for c in CASES if c[3]]
    elif argv:
        cases = [(a.split(":")[0], (a.split(":") + ["default"])[1], None, None) for a in argv]
    for n, (task, mode, who, talk) in enumerate(cases):
        uid = "u_" + f"{n:016x}"
        with Store(uid) as st:
            if who and who.get("wish"):
                st.c.execute("INSERT INTO wish(id, title, category, started, archived, sort, created_at) VALUES('w1', ?, 'other', '2026-11-01', 0, 0, '2026-11-01T00:00:00+08:00')", (who["wish"],))
                st.set_profile({"current_wish": "w1"})
            if who and who.get("memory"):
                st.add_memory(who["memory"], kind="identity", source="chat:explicit", status="active")
            t0 = time.time()
            out = kickstart.start(st, task, mode)
            r = out["run"]
            extra = f"｜愿望「{who['wish']}」" if who and who.get("wish") else f"｜记忆「{who['memory']}」" if who else ""
            show(r, f"\n## {task}（{mode}）{extra}  {time.time() - t0:.1f}s{'' if out.get('by_model') else '  ← 模型没回，用的通用路线'}")
            print("  鼓励：", r.get("cheer") or "")
            if talk:
                t0 = time.time()
                o = kickstart.feedback(st, r["id"], talk[0], talk[1])
                r = o["run"]
                show(r, f"  -- {'调整路线' if talk[0] == 'adjust' else '遇到困难'}：「{talk[1]}」  {time.time() - t0:.1f}s")
                if r["log"] and r["log"][-1].get("found"):
                    print("  发现：", r["log"][-1]["found"])


if __name__ == "__main__":
    main(sys.argv[1:])
