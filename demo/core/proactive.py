"""主动消息：像朋友时不时发来的一条微信（2026-11-07 改）。

每条从四种里挑一种，但只挑**手上有真材料**的那几种，并且不连着两次同一种：
  chat    随便聊聊：TA 最近提过的人和事、TA 前两天说过的话，接着问一句
  plan    计划：快到日子的里程碑、这周跟不上的习惯、放了好几天的小步（都来自真实数据）
  feature 体验功能：TA 还没试过、又正合适的一个功能（消息下面带一个入口，和聊天里的推荐同一个样子）
  cheer   鼓励：最近真做成的事（完成的小步、留下的瞬间），说具体的
文字由小光按 TA 选的性格写，示范对话用的是产品负责人亲手写的参考回复（core/voice.py），不套模板；
消息上不标「这是哪一类」，也不标「主动找你」，就是一条普通的消息。
"""
from __future__ import annotations

import random
from datetime import timedelta

from . import acts, journey, llm, nudges, town, voice
from .util import clip, now, parse_iso

KIND_GOAL = {
    "chat": "随便聊两句。从下面的材料里挑一件 TA 最近提过的人或事，接着关心一下或者好奇地问一句，像朋友想起 TA 了。",
    "plan": "顺手提一下计划里的一件事。用朋友的口吻带一句，给 TA 一个很小、马上能做的选择；不催、不算账。",
    "feature": "邀请 TA 试一个 App 里的小功能。先说为什么想到它（和 TA 最近的状态有关），再轻轻邀请；功能的介绍会出现在消息下面，你不用讲它怎么用。",
    "cheer": "为 TA 最近真做成的一件事高兴一下。说具体的那件事，说出你注意到的细节；不说「加油」「你真棒」这种空话。",
}
FEATURE_WHY = {
    "kickstart": "有一个小步放了好几天还没开始",
    "meditation": "最近事情有点多",
    "gratitude": "最近好像有点累，可以停下来数数身边的好事",
    "seven_steps_lite": "还没许过一个自己的愿望",
    "relearn": "还没回头看过这周的计划做得怎么样",
    "town": "攒的金币够盖一样新东西了",
}


def _recent_user_lines(st, days: int = 3) -> list[str]:
    edge = (now() - timedelta(days=days)).isoformat()
    out = [m["content"] for m in st.messages(40) if m["role"] == "user" and m["content"] and (m["created_at"] or "") >= edge]
    return [clip(t, 60) for t in out[-6:]]


def _chat_material(st) -> list[str]:
    lines = []
    nb = (st.profile().get("notebook") or {}).get("text") or ""
    for l in nb.splitlines():
        if l.startswith(("最近的生活", "在意的人", "心情和状态")) and "：" in l:
            lines.append(l)
    edge = (now() - timedelta(days=14)).isoformat()
    for m in st.memories(statuses=("active",), limit=40):
        if (m["updated_at"] or "") >= edge and m["kind"] in ("event", "identity", "preference"):
            lines.append(m["text"])
    lines += ["TA 前两天说过：" + t for t in _recent_user_lines(st)]
    return lines[:10]


def _plan_material(st) -> list[str]:
    items = [x for x in nudges.attention(st, limit=4) if x["kind"] != "rest" and (x["prio"] >= 2 or x["kind"] in ("old_step", "no_path"))]
    return [x["text"] + (f"（可以给的小选择：{x['hint']}）" if x.get("hint") else "") for x in items[:2]]


def _feature_pick(st) -> str | None:
    counts = {r[0]: r[1] for r in st.c.execute("SELECT scene, COUNT(*) FROM scene_run WHERE status='done' GROUP BY scene")}
    kicks = st.c.execute("SELECT COUNT(*) FROM kick_run").fetchone()[0]
    old = [s for s in st.steps() if s["status"] == "todo" and not journey.planned_day(s)
           and (now() - (parse_iso(s["created_at"]) or now())).days >= 3]
    options = []
    if old and not kicks:
        options.append("kickstart")
    for f in ("meditation", "gratitude", "seven_steps_lite", "relearn"):
        if not counts.get(f):
            options.append(f)
    try:
        t = town.state(st)
        if any(c["unlocked"] and c["price"] and c["price"] <= t["coins"] and c["cat"] == "build" for c in t["catalog"]):
            options.append("town")
    except Exception:
        pass
    return random.choice(options) if options else None


def _cheer_material(st) -> list[str]:
    edge = (now() - timedelta(days=7)).date().isoformat()
    lines = [f"完成了小步「{s['title']}」" for s in st.steps() if s["status"] == "done" and (s.get("done_at") or "")[:10] >= edge][:3]
    lines += [f"留下一个瞬间：{r[0]}" for r in st.c.execute("SELECT text FROM moment WHERE day>=? ORDER BY day DESC LIMIT 3", (edge,))]
    return lines


def choose(st, resting: bool = False) -> dict | None:
    """挑这一次聊什么。没有材料的那种不挑；偷懒日只闲聊或鼓励；不连着两次同一种。"""
    p = st.profile()
    have = {"chat": _chat_material(st), "cheer": _cheer_material(st)}
    if not resting:
        have["plan"] = _plan_material(st)
        f = _feature_pick(st)
        if f:
            have["feature"] = [f"想邀请 TA 试试「{acts.FEATURES[f]['title']}」，因为{FEATURE_WHY.get(f, '正合适')}"]
            have["_feature"] = f
    kinds = [k for k in ("chat", "plan", "feature", "cheer") if have.get(k)]
    if len(kinds) > 1 and p.get("last_proactive_kind") in kinds:
        kinds.remove(p["last_proactive_kind"])
    if not kinds:
        return None
    k = random.choice(kinds)
    return {"kind": k, "material": have[k], "feature": have.get("_feature") if k == "feature" else None}


def compose(st, pick: dict) -> dict:
    p = st.profile()
    name = p.get("agent_name") or "小光"
    nick = p.get("nickname") or ""
    t = now()
    sent = [m["content"] for m in st.messages(60) if m["role"] == "assistant" and (m.get("meta") or {}).get("proactive")][-4:]
    recent = [f"{'TA' if m['role'] == 'user' else '你'}：{clip(m['content'], 60)}" for m in st.messages(8) if m["content"]][-4:]
    system = (f"你是「{name}」，{('TA 叫' + nick + '，') if nick else ''}你是 TA 的朋友。现在你想主动给 TA 发一条微信，就像朋友想起对方时随手发的那种。\n\n"
              + voice.render(p.get("persona") or "gentle", nick) + "\n\n"
              "这条消息的要求：\n"
              "- 一两句话，大多 20–50 字；最多一个问题，也可以不问。\n"
              "- 直接说事，别用「嗨」「在吗」「最近怎么样」「好久不见」开头，也别自我介绍。\n"
              "- 只用下面给你的真实信息，一次只说一件事，不编没发生过的事。\n"
              "- 别提「提醒」「推送」「主动找你」「系统」「App 里」「这个功能」，功能直接叫名字；别说教、别打鸡血、别说「加油」。\n"
              "- 不要用「不是……而是……」这种句式。\n"
              "- 别和你最近发过的几条说一样的话、一样的开头。\n"
              '只输出 JSON：{"text": "..."}')
    user = (f"现在是周{'一二三四五六日'[t.weekday()]}{'早上' if t.hour < 12 else '下午' if t.hour < 18 else '晚上'} {t:%H:%M}。\n"
            f"这条想做的：{KIND_GOAL[pick['kind']]}\n材料：\n" + "\n".join("- " + x for x in pick["material"])
            + ("\n\n你们最近的对话：\n" + "\n".join(recent) if recent else "")
            + ("\n\n你最近主动发过的：\n" + "\n".join("- " + x for x in sent) if sent else ""))
    out = llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}], timeout=30, reasoning=None)
    text = clip(((out or {}).get("text") or "").strip(), 120)
    if not text:      # 模型不可用：只用材料里的事实，说得朴素一点
        text = {"chat": "想起你前两天说的事了，后来怎么样啦？", "plan": f"{pick['material'][0].split('（')[0]}，今天要不要动一小下？",
                "feature": f"想邀请你试试「{acts.FEATURES.get(pick.get('feature') or '', {}).get('title', '一个小练习')}」，几分钟就好。",
                "cheer": f"还记得你{pick['material'][0]}，我一直替你高兴。"}[pick["kind"]]
    extra = [acts.entry(pick["feature"])] if pick.get("feature") else []
    return {"kind": pick["kind"], "text": text, "acts": [e for e in extra if e]}
