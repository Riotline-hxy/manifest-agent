"""Model benchmark for 技术评估: first-token latency, total time, tool-call
correctness, on the same relay and the same 小光 tool schema.

  python bench_models.py                 # default model list, 3 runs each
  python bench_models.py gpt-6.1-sol deepseek-v4-flash --runs 5

Needs MODELFLARE_API_KEY. Writes docs/bench-<date>.json and prints a table.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import agent, llm  # noqa: E402
from core.util import ROOT, day_key, load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / ".env")

DEFAULT = ["gpt-6.1-sol", "deepseek-v4-flash", "deepseek-v4-pro", "glm-5.3-flash", "glm-5.3", "MiniMax-H3"]

SYS = agent.PERSONA.format(name="小光", boundaries="", now="2026-10-26 21:00", weekday="周一") + \
    "\n\n## 你知道的（核心）\n现在最想靠近：自信与表达（因为：交换项目时想敢开口说英语）\n" \
    "计划里待做的小步：[s_1] 在小组里主动提一个问题"

CASES = [
    ("good_news", "今天和朋友用英语聊了半小时，完全没卡壳！", {"log_good_news"}),
    ("complete", "小组里那一步我做完了，主动提了问题", {"complete_step"}),
    ("lazy", "今天好累，什么都不想做", {"log_lazy_day"}),
    ("scene", "我想试试冥想", {"start_scene"}),
    ("chat", "最近有点焦虑，说不清为什么", set()),
]


def one(model: str, text: str, want: set, reasoning):
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": text}]
    t0 = time.time()
    first, calls = None, []
    try:
        for kind, val in llm.stream_chat(msgs, tools=agent.TOOLS, model=model, reasoning=reasoning, timeout=90):
            if first is None and kind in ("text", "tool_calls"):
                first = time.time() - t0
            if kind == "tool_calls":
                calls = [c["name"] for c in val]
    except llm.LLMError as e:
        return {"error": str(e)[:120]}
    got = set(calls)
    ok = (want <= got) if want else not (got - {"search_memory"})
    return {"first_s": round(first or 0, 2), "total_s": round(time.time() - t0, 2), "calls": calls, "correct": ok}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
    models = [a for a in args if not a.isdigit()] or DEFAULT
    if not llm.api_key():
        sys.exit("MODELFLARE_API_KEY not set")
    results = {}
    for m in models:
        reasoning = "low" if m.startswith("gpt") else ""
        rows = []
        for _ in range(runs):
            for name, text, want in CASES:
                r = one(m, text, want, reasoning)
                r["case"] = name
                rows.append(r)
                print(f"  {m:18s} {name:10s} {r}", flush=True)
        good = [r for r in rows if "error" not in r]
        results[m] = {
            "n": len(rows), "errors": len(rows) - len(good),
            "first_p50": round(statistics.median([r["first_s"] for r in good]), 2) if good else None,
            "total_p50": round(statistics.median([r["total_s"] for r in good]), 2) if good else None,
            "total_max": round(max([r["total_s"] for r in good]), 2) if good else None,
            "tool_accuracy": round(sum(r["correct"] for r in good) / len(good), 2) if good else None,
            "rows": rows,
        }
    print("\nmodel               errors  first_p50  total_p50  total_max  tool_acc")
    for m, r in results.items():
        print(f"{m:18s} {r['errors']:>6}  {r['first_p50']!s:>9}  {r['total_p50']!s:>9}  {r['total_max']!s:>9}  {r['tool_accuracy']!s:>8}")
    out = ROOT.parent / "docs" / f"bench-{day_key()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"date": day_key(), "runs": runs, "cases": [c[0] for c in CASES], "results": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
