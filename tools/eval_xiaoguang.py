"""小光评测：把 docs/prompt-rework/评测集.yaml 里的每个场景，用三种性格各跑一遍真实的 agent.chat。

  python tools/eval_xiaoguang.py --label baseline            # 全部 20 条 × 3 种性格
  python tools/eval_xiaoguang.py --cases E02,E08 --persona 活泼
  python tools/eval_xiaoguang.py --no-judge                  # 只做硬检查，不请模型打分

每一格用一个全新的临时用户（数据放在临时目录，不碰线上），档案照「默认档案」+ 这一条的「档案改动」搭。
两层检查：
  1. 硬检查（代码判断）：该调的工具调了没有、不该调的有没有调、问号个数、AI 腔词、没调工具却说「记住了」、用了 markdown。
  2. 模型打分：拿用户写的三份参考回复对照，给「人味」「像不像这个性格」「要点做到没有」各打 1–5 分，并写出问题。
     打分模型和小光用的是同一个模型，分数只适合前后对比，不适合当绝对值。
结果写进 docs/prompt-rework/结果/<日期>-<label>.json 和 .md。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("MANIFEST_DATA", tempfile.mkdtemp(prefix="xb-eval-"))
sys.path.insert(0, str(REPO / "demo"))

import yaml  # noqa: E402

# 场景都按工作日白天写的：整个程序看到的「现在」固定在 2026-11-04（周三）上午 10 点。
# 各模块是 `from .util import now` 拿的函数，所以要在导入它们之前先换掉 util.now。
from datetime import datetime  # noqa: E402

from core import util  # noqa: E402

FIXED_NOW = datetime(2026, 11, 4, 10, 0, tzinfo=util.TZ)
util.now = lambda: FIXED_NOW

from core import agent, journey, llm, router  # noqa: E402
from core.store import Store  # noqa: E402
from core.util import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

CASES_FILE = REPO / "docs" / "prompt-rework" / "评测集.yaml"
OUT_DIR = REPO / "docs" / "prompt-rework" / "结果"
PERSONAS = {"温柔": "gentle", "有条理": "clear", "活泼": "lively"}
SEEN = {"E01", "E03", "E05", "E07", "E11", "E13", "E16", "E19"}   # 这几条的参考回复放进了提示词（core/voice.py）
AI_PHRASES = ["我理解你的感受", "作为一个AI", "作为一个 AI", "你可以尝试以下方法", "希望对你有帮助", "加油", "你一定可以"]
REMEMBER_CLAIM = re.compile(r"记住了|记住啦|记下了|记下啦|加进笔记本")
MARKDOWN = re.compile(r"\*\*|^#+ |^\s*[-*] |^\s*\d+\. ", re.M)

# 被调用的工具：包一层 run_tool，连被拦下（skipped）的调用也记上
_calls: dict[str, list] = {}
_orig_run_tool = agent.run_tool


def _run_tool(store, name, args, user_text="", routed=""):
    result = _orig_run_tool(store, name, args, user_text, routed)
    _calls.setdefault(store.uid, []).append({"name": name, "args": args, "ok": result.get("ok"),
                                              "skipped": bool(result.get("skipped") or result.get("unchanged"))})   # 和上一版一样、没出新卡片的，不算调用
    return result


agent.run_tool = _run_tool

# 每轮回复前的路由判断（core/router.py）也记下来，报告里能看到它挑了哪个工具
_routed: dict[str, str] = {}
_orig_decide = router.decide


def _decide(ctx, user_text, timeout=8):
    t = _orig_decide(ctx, user_text, timeout)
    _routed[ctx["uid"]] = t
    return t


router.decide = _decide

# ---- 搭一个临时用户 ------------------------------------------------------------

def build_user(profile: dict, persona: str) -> Store:
    uid = "u_" + secrets.token_hex(8)
    st = Store(uid)
    st.set_profile({"nickname": profile.get("称呼") or "", "persona": persona, "onboarded": True,
                    "proactive": "normal", "boundaries": profile.get("边界") or []})
    for w in profile.get("愿望") or []:
        wish = journey.add_wish(st, w["标题"], "", now_text=w.get("原因") or "")
        if w.get("原因"):
            st.set_profile({"intent_primary": w["标题"], "intent_why": w["原因"]})
        for m in w.get("里程碑") or []:
            journey.add_milestone(st, wish["id"], m)
        for h in w.get("习惯") or []:
            n = re.search(r"每周.*?(\d+)\s*次", h)
            journey.add_habit(st, wish["id"], h, "weekly" if n else "daily", int(n.group(1)) if n else 3)
        for s in w.get("小步") or []:
            st.add_step(re.sub(r"^\[[^\]]*\]\s*", "", s), wish_id=wish["id"])
    for m in profile.get("记忆") or []:
        st.add_memory(m, kind="preference", source="onboarding")
    if profile.get("今天是偷懒日") in ("是", True):
        st.add_record("rest", "今天偷个懒")
    return st


def plan_card(st, card: dict) -> dict:
    """前情里的「提议安排」→ 和 core/acts.py 画的一样的待确认卡片（还没点）。"""
    w = next((x for x in journey.wishes(st) if x["title"] == card.get("愿望")), None) or journey.wishes(st)[0]
    plan = {"milestones": [{"title": t} for t in card.get("里程碑") or []],
            "habits": [{"title": t, "freq": "weekly", "per_week": 3} for t in card.get("习惯") or []],
            "steps": [{"title": t} for t in card.get("小步") or []]}
    return {"type": "ask", "ask": "plan", "icon": "flag", "color": "var(--c-orange)", "question": f"给「{w['title']}」的一套安排，勾掉不想要的",
            "plan": plan, "why": "", "wish_id": w["id"], "wish_title": w["title"], "state": ""}


def merged_profile(base: dict, case: dict) -> dict:
    p = dict(base)
    p.update(case.get("档案改动") or {})
    return p


# ---- 跑一格 --------------------------------------------------------------------

def run_one(base: dict, case: dict, pname: str) -> dict:
    st = build_user(merged_profile(base, case), PERSONAS[pname])
    for turn in case.get("前情") or []:     # 这句话之前已经发生的对话
        card = turn.get("提议安排")             # 小光那句话下面还挂着一张没点的安排卡片
        for who, text in turn.items():
            if who == "提议安排":
                continue
            meta = {"acts": [plan_card(st, card)]} if card and who != "用户" else None
            st.add_msg("user" if who == "用户" else "assistant", str(text), meta)
    t0 = time.time()
    first, reply, errors = None, "", []
    try:
        for kind, val in agent.chat(st, case["用户说"], extract=False):
            if kind == "delta":
                first = first or round(time.time() - t0, 2)
                reply += val["text"]
            elif kind == "error":
                errors.append(val.get("message"))
    finally:
        calls = _calls.pop(st.uid, [])
        routed = _routed.pop(st.uid, None)
        st.close() if hasattr(st, "close") else None
    return {"id": case["id"], "性格": pname, "回复": reply.strip(), "工具": calls, "路由": routed, "错误": errors,
            "首字秒": first, "总秒": round(time.time() - t0, 2)}


def hard_checks(case: dict, r: dict) -> list[str]:
    called = {c["name"] for c in r["工具"] if not c["skipped"]}
    text = r["回复"]
    out = []
    for t in case.get("应该调用") or []:
        if t not in called:
            out.append(f"没调用 {t}")
    anyof = case.get("应该调用任一") or []
    if anyof and not called & set(anyof):
        out.append("没调用 " + " / ".join(anyof) + " 中的任何一个")
    for t in case.get("不能调用") or []:
        if t in called:
            out.append(f"不该调用 {t}")
    q = text.count("？") + text.count("?")
    if q > 2:
        out.append(f"问了 {q} 个问题")
    for w in AI_PHRASES:
        if w in text:
            out.append(f"AI 腔：{w}")
    if REMEMBER_CLAIM.search(text) and not called & {"remember", "update_notebook", "correct_memory"}:
        out.append("没调用记忆工具却说记住了")
    if MARKDOWN.search(text):
        out.append("用了 markdown")
    if r["错误"]:
        out.append("模型报错：" + "；".join(map(str, r["错误"]))[:80])
    return out


JUDGE = """你在给一个陪伴 App 里的 AI 朋友「小光」的回复打分。小光有三种性格，用户这一轮选的是「{p}」。

场景：{scene}
{note}用户说：{said}
小光这一轮调用的工具：{tools}
小光的回复：{reply}

这一条要做到：
{musts}
通用要求：
{general}

产品负责人亲手写的三份参考回复（同一句话，三种性格各自会怎么回）：
{refs}

请对照参考回复，尤其是「{p}」那一份的语气、长度、用词、表情习惯，打三个 1–5 分：
- 人味：像不像真人朋友在微信上回的，而不是 AI 客服（5 = 和参考回复一样自然）
- 性格：像不像「{p}」这一种，和另外两种分得开吗
- 要点：这一条要做到的事和通用要求做到了多少
参考回复里提到的内容不必照抄；回复意思不同但同样自然，也可以给高分。
只输出 JSON：{{"人味": n, "性格": n, "要点": n, "问题": ["一句话说一个具体问题", ...]}}"""


def judge(case: dict, r: dict, general: list[str]) -> dict:
    refs = "\n".join(f"- {k}：{v or '（没写）'}" for k, v in (case.get("参考回复") or {}).items())
    tools = "、".join(c["name"] + ("（被拦下）" if c["skipped"] else "") for c in r["工具"]) or "无"
    prompt = JUDGE.format(p=r["性格"], scene=case.get("场景", ""), said=case["用户说"], tools=tools,
                          reply=r["回复"] or "（空）", refs=refs,
                          note=(f"备注：{case['备注']}\n" if case.get("备注") else ""),
                          musts="\n".join("- " + x for x in (case.get("回复要做到") or [])
                                          + ["不能有：" + y for y in (case.get("回复不能有") or [])]) or "- （无）",
                          general="\n".join("- " + x for x in general))
    out = llm.complete_json([{"role": "user", "content": prompt}], timeout=60) or {}
    return {k: out.get(k) for k in ("人味", "性格", "要点", "问题")}


# ---- 报告 ----------------------------------------------------------------------

def avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 2) if xs else None


def write_report(rows: list[dict], label: str, cfg: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime("%Y-%m-%d")}-{label}"          # label 里可能有「.」（v3.6），不能用 with_suffix
    js, md = OUT_DIR / (stem + ".json"), OUT_DIR / (stem + ".md")
    js.write_text(json.dumps({"label": label, "config": cfg, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"# 小光评测：{label}（{time.strftime("%Y-%m-%d")}）", "",
         f"模型 `{cfg['model']}`，思考 `{cfg['reasoning']}`。共 {len(rows)} 格。",
         f"「没见过」= 不在提示词示范对话里的 {len(set(r['id'] for r in rows) - SEEN)} 条，是真正的检验；「全部」含示范里那 8 条。", ""]
    L += ["| 性格 | 范围 | 硬检查全过 | 人味 | 性格 | 要点 | 首字秒（中位） |", "|---|---|---|---|---|---|---|"]
    for p in PERSONAS:
        for scope, rs in (("全部", [r for r in rows if r["性格"] == p]),
                          ("没见过", [r for r in rows if r["性格"] == p and r["id"] not in SEEN])):
            if not rs:
                continue
            firsts = sorted(r["首字秒"] for r in rs if r["首字秒"])
            L.append(f"| {p} | {scope} | {sum(1 for r in rs if not r['硬检查'])}/{len(rs)} | {avg(r['打分'].get('人味') for r in rs)} | "
                     f"{avg(r['打分'].get('性格') for r in rs)} | {avg(r['打分'].get('要点') for r in rs)} | "
                     f"{firsts[len(firsts) // 2] if firsts else '-'} |")
    L += ["", "## 每一格", ""]
    for r in rows:
        s = r["打分"]
        L.append(f"### {r['id']} · {r['性格']}　人味 {s.get('人味')} / 性格 {s.get('性格')} / 要点 {s.get('要点')}")
        L.append(f"- 用户说：{r['用户说']}")
        L.append(f"- 小光：{r['回复'] or '（空）'}")
        L.append(f"- 参考：{r['参考'] or '（没写）'}")
        L.append(f"- 工具：{'、'.join(c['name'] + ('（被拦下）' if c['skipped'] else '') for c in r['工具']) or '无'}"
                 + (f"（路由要求先调 {r['路由']}）" if r.get("路由") else ""))
        if r["硬检查"]:
            L.append(f"- ❌ 硬检查：{'；'.join(r['硬检查'])}")
        for q in s.get("问题") or []:
            L.append(f"- 打分意见：{q}")
        L.append("")
    md.write_text("\n".join(L), encoding="utf-8")
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="", help="逗号分隔的 id，默认全部")
    ap.add_argument("--persona", default="", help="温柔 / 有条理 / 活泼，默认三种都跑")
    ap.add_argument("--label", default="run")
    ap.add_argument("--file", default="", help="评测集文件名（docs/prompt-rework 下），默认 评测集.yaml")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not llm.api_key():
        sys.exit("没有模型 key：在 manifest-agent/.env 里配置")
    data = yaml.safe_load(((CASES_FILE.parent / a.file) if a.file else CASES_FILE).read_text(encoding="utf-8"))
    cases = [c for c in data["用例"] if not a.cases or c["id"] in a.cases.split(",")]
    personas = [a.persona] if a.persona else list(PERSONAS)
    jobs = [(c, p) for c in cases for p in personas]
    cfg = llm.config()
    print(f"{len(jobs)} 格，模型 {cfg['model']}，数据目录 {os.environ['MANIFEST_DATA']}", flush=True)

    def work(job):
        c, p = job
        r = run_one(data["默认档案"], c, p)
        r["用户说"] = c["用户说"]
        r["参考"] = (c.get("参考回复") or {}).get(p) or ""
        r["硬检查"] = hard_checks(c, r)
        r["打分"] = {} if a.no_judge else judge(c, r, data.get("通用要求") or [])
        print(f"  {r['id']} {p:3s} {'✓' if not r['硬检查'] else '✗ ' + '；'.join(r['硬检查'])}  "
              f"{r['打分'].get('人味')}/{r['打分'].get('性格')}/{r['打分'].get('要点')}", flush=True)
        return r

    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(work, jobs))
    print("报告：", write_report(rows, a.label, cfg))


if __name__ == "__main__":
    main()
