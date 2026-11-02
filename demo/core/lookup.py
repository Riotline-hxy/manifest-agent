"""小光的「看一眼」：按功能读出这个用户在各个页面里的真实数据（只读）。

agent 的 look_up 工具用它。输出是给模型看的紧凑文字，带上每一项的 [id]，
这样后面要改、要删的时候能准确指到那一项。
"""
from __future__ import annotations

from datetime import timedelta

from . import academy, growth, journey, nudges, report, tasks
from .scenes import SCENES
from .util import clip, now

AREAS = {
    "plan": "蜕变计划全貌：所有愿望和它们的里程碑、习惯、小步，收起的愿望",
    "wish": "某一个愿望的细节：路径、最近的瞬间、阶段回望、小发现（query 写愿望名字）",
    "habits": "所有习惯：频率、本周进度、最近两周哪天打过卡、连续天数、收起的习惯",
    "steps": "小步：待做 / 最近做完 / 放一放的",
    "moments": "轨迹上留下的瞬间（可以用 query 指定愿望）",
    "good_news": "好消息页：小确幸和内心戏",
    "rest": "最近的偷懒日",
    "memories": "你长期记住的关于 TA 的事，和待确认的猜测",
    "notebook": "你的笔记本",
    "digests": "最近几天夜里整理的小结",
    "tasks": "定时提醒和例行任务",
    "settings": "TA 的画像和设置：称呼、你的名字和性格、主动消息频率、互动偏好、宠物名、主题……",
    "activity": "最近的动态日志：TA 和你在各个页面做过的事",
    "growth": "成长：经验、等级、宠物形态、今天的任务、徽章",
    "report": "最近 14 / 30 天的蜕变报告里的数字",
    "academy": "心灵学堂的文章，和 TA 读过哪些",
    "ideas": "点子页的练习，和 TA 做过哪些",
    "attention": "现在值得提醒 TA 的事（快到期的里程碑、跟不上的习惯、放久了的小步……）",
}

PERSONA = {"gentle": "温柔", "clear": "有条理", "lively": "活泼"}
CARE = {"nudge": "被打断时先轻轻提醒", "analyze": "被打断时一起找原因", "quiet": "被打断时先不提", "": "没选"}
PROACTIVE = {"more": "多一点（约 12 小时没聊就来找）", "normal": "正常（约一天）", "less": "少一点（两三天）", "off": "关掉了"}
THEME = {"forest": "森林夜", "midnight": "深空", "paper": "晨光", "peach": "暖阳", "mist": "海雾"}
MAX_CHARS = 3600


def _md(d: str) -> str:
    return d[5:10] if d else ""


def _wish_block(st, w: dict, steps: list[dict]) -> list[str]:
    out = [journey.path_text(st, w)]
    if w.get("now_text"):
        out.append(f"  定下时 TA 说自己：{w['now_text']}")
    for s_ in steps:
        if s_.get("wish_id") == w["id"] and s_["status"] == "todo":
            out.append(f"  - 小步 [{s_['id']}] {s_['title']}（{_md(s_['created_at'])} 加的）")
    out.append(f"  轨迹上 {w['count']} 个瞬间，{w['days']} 天有记录")
    return out


def look_up(st, area: str, query: str = "") -> dict:
    area = area if area in AREAS else "plan"
    q = (query or "").strip()
    L: list[str] = []
    today = now().date()

    if area == "plan":
        ws = journey.wishes(st)
        steps = st.steps(200)
        if not ws:
            L.append("还没有愿望。")
        for w in ws:
            L += _wish_block(st, w, steps)
        loose = [s_ for s_ in steps if s_["status"] == "todo" and not s_.get("wish_id")]
        if loose:
            L.append("没挂在愿望下的小步：" + "；".join(f"[{s_['id']}] {s_['title']}" for s_ in loose[:8]))
        gone = [w for w in journey.wishes(st, include_archived=True) if w["archived"]]
        if gone:
            L.append("收起的愿望（可以找回）：" + "；".join(f"[{w['id']}] {w['title']}" for w in gone))
        cur = journey.current(st)
        if cur:
            L.append(f"TA 现在在蜕变计划页看的是「{cur['title']}」")

    elif area == "wish":
        ws = journey.wishes(st, include_archived=True)
        w = journey._pick(ws, q) if q else journey.current(st)
        if not w:
            return {"ok": False, "error": "没找到这个愿望", "have": [x["title"] for x in ws]}
        L += _wish_block(st, w, st.steps(200))
        if w["archived"]:
            L.append("（这个愿望已经收起了）")
        if w.get("prompts"):
            L.append("TA 写给自己的问题：" + "；".join(w["prompts"]))
        for m in journey.moments(st, w["id"], limit=8):
            L.append(f"  - 瞬间 [{m['id']}] {m['day']} {clip(m['text'], 60)}" + (f"（感受：{m['feeling']}）" if m["feeling"] else ""))
        rv = journey.review(st, w["id"], 30)
        L.append("最近 30 天：" + rv["line"])
        for r in rv["reflections"][:3]:
            L.append(f"  - TA 写的回望（{_md(r['created_at'])}）：{clip(r['text'], 80)}")
        ins = journey.open_insight(st, w["id"])
        if ins:
            L.append(f"还没回答的小发现：{ins['text']}")

    elif area == "habits":
        hs = journey.habits(st, since=(today - timedelta(days=13)).isoformat())
        title = {w["id"]: w["title"] for w in journey.wishes(st)}
        if not hs:
            L.append("现在没有习惯。")
        for h in hs:
            streak = nudges._streak(h["days"], today)
            L.append(f"[{h['id']}] {h['title']}（{title.get(h['wish_id'], '')}）{h['freq_text']}，本周 {h['week']}/{h['need']}，"
                     f"今天{'已打卡' if h['today'] else ('先跳过了' if h['skipped'] else '还没打卡')}，累计 {h['total']} 次"
                     + (f"，连续 {streak} 天" if streak >= 2 else "")
                     + "；最近两周：" + ("、".join(d[5:] for d in h["days"]) or "没有"))
        gone = [h for h in journey.habits(st, include_archived=True) if h["archived"]]
        if gone:
            L.append("收起的习惯（可以找回）：" + "；".join(f"[{h['id']}] {h['title']}" for h in gone[:8]))

    elif area == "steps":
        steps = st.steps(200)
        for label, status, n in (("待做", "todo", 15), ("做完了", "done", 8), ("先放一放的", "dropped", 8)):
            xs = [s_ for s_ in steps if s_["status"] == status][:n]
            if xs:
                L.append(label + "：" + "；".join(
                    f"[{s_['id']}] {s_['title']}（{_md(s_.get('done_at') or s_['created_at'])}）" for s_ in xs))
        if not L:
            L.append("还没有小步。")

    elif area == "moments":
        ws = journey.wishes(st, include_archived=True)
        title = {w["id"]: w["title"] for w in ws}
        w = journey._pick(ws, q) if q else None
        ms = journey.moments(st, w["id"] if w else None, limit=15)
        if not ms:
            L.append("还没有留下瞬间。")
        for m in ms:
            L.append(f"[{m['id']}] {m['day']}「{title.get(m['wish_id'], '')}」{clip(m['text'], 60)}"
                     + (f"（感受：{m['feeling']}）" if m["feeling"] else ""))

    elif area == "good_news":
        recs = [r for r in st.records(300) if r["type"] in ("good", "meme")]
        week = (today - timedelta(days=today.weekday())).isoformat()
        good = [r for r in recs if r["type"] == "good"]
        L.append(f"小确幸一共 {len(good)} 条，这周 {sum(1 for r in good if r['day'] >= week)} 条；内心戏 {len(recs) - len(good)} 条。")
        for r in recs[:15]:
            L.append(f"[{r['id']}] {r['day']} {'小确幸' if r['type'] == 'good' else '内心戏'}：{clip(r['text'], 60)}")

    elif area == "rest":
        days = [r["day"] for r in st.records(300) if r["type"] == "rest"]
        L.append("最近的偷懒日：" + ("、".join(dict.fromkeys(days[:20])) or "没有"))
        L.append("今天" + ("是偷懒日" if journey.is_resting(st) else "不是偷懒日"))

    elif area == "memories":
        act = st.memories(statuses=("active",), limit=40)
        L += [f"[{m['id']}] {m['text']}（{m['kind']}，{m['created_at'][:10]}）" for m in act] or ["还没有长期记住的事。"]
        gs = st.memories(statuses=("guess",), limit=8)
        if gs:
            L.append("待确认的猜测：" + "；".join(f"[{m['id']}] {m['text']}" for m in gs))

    elif area == "notebook":
        nb = st.profile().get("notebook") or {}
        L.append(nb.get("text") or "笔记本还是空的。")
        if nb.get("updated_at"):
            L.append(f"（{nb['updated_at'][:16].replace('T', ' ')} 由{'TA 自己' if nb.get('by') == 'user' else '你'}改过）")

    elif area == "digests":
        for d in st.digests(7):
            L.append(f"{d['day']}：{d['summary']}")
        if not L:
            L.append("还没有夜里的小结。")

    elif area == "tasks":
        ts = tasks.list_for(st.uid)
        for t in ts:
            L.append(f"[{t['id']}] {t['title']}（{t['when']}，{'开着' if t['enabled'] else '关着'}，"
                     f"{'到点由你写一条消息' if t['kind'] == 'ai' else '到点提醒'}）" + (f"：{clip(t['message'], 40)}" if t["message"] else ""))
        if not ts:
            L.append("还没有定时任务。")

    elif area == "settings":
        p = st.profile()
        L += [f"TA 的称呼：{p.get('nickname') or '没填'}",
              f"你的名字：{p.get('agent_name') or '小光'}；性格：{PERSONA.get(p.get('persona') or 'gentle')}",
              f"主动消息：{PROACTIVE.get(p.get('proactive') or 'normal')}（23:00–08:00 不发）",
              f"互动偏好：{CARE.get(p.get('care_style') or '', '没选')}",
              f"宠物名字：{p.get('pet_name') or '小芽'}；页面氛围：{THEME.get(p.get('theme') or '', p.get('theme') or '默认')}",
              f"建档时最想靠近：{p.get('intent_primary') or '没填'}" + (f"（因为：{p['intent_why']}）" if p.get("intent_why") else ""),
              "别人常觉得 TA：" + ("、".join(p.get("traits") or []) or "没填"),
              f"作息：{p.get('schedule_hint') or '没填'}",
              "TA 的边界：" + ("、".join(x for x in (p.get("boundaries") or []) if x and x != "无") or "没填"),
              "自定义心情：" + ("、".join(p.get("custom_moods") or []) or "没有"),
              f"夜里整理：{'开着' if p.get('digest_on', True) else '关着'}"]

    elif area == "activity":
        for a in st.activity(30):
            L.append(f"{a['at'][5:16].replace('T', ' ')} {a['text']}")

    elif area == "growth":
        g = growth.state(st, consume=False)
        L.append(f"累计 {g['total']} 经验，Lv{g['level']['lv']}；{g['pet_name']}现在是{g['stage']['name']}"
                 + (f"，再 {g['to_next']} 经验到「{g['next']['name']}」" if g["next"] else ""))
        L.append(f"今天拿了 {g['today']['total']}/{g['today']['cap']}；今日任务：" + "；".join(
            f"{x['label']} {'✓' if x['done'] else f'{x['got']}/{x['need']}'}" for x in g["quests"]))
        got = [b["name"] for b in g["badges"] if b["earned"]]
        L.append("徽章：" + ("、".join(got) or "还没有"))
        L.append("规则：" + growth.rules_text())

    elif area == "report":
        for days in (14, 30):
            f = report.build(st, days, with_letter=False)["facts"]
            L.append(f"最近 {days} 天：好消息 {f['good']} 条，完成小步 {f['done']} 个，习惯打卡 {f['checkins']} 次，"
                     f"偷懒 {f['rest']} 天，经验 +{f['xp']}")
        L.append("完整的蜕变报告在蜕变计划页最下面的「蜕变报告」里。")

    elif area == "academy":
        read = st.read_ids()
        for a in academy.catalog():
            L.append(f"[{a['id']}] {a['title']}（{a['chapter']}，{a['minutes']} 分钟，{'读过' if a['id'] in read else '没读'}）")

    elif area == "ideas":
        done = {r[0]: r[1] for r in st.c.execute("SELECT scene, COUNT(*) FROM scene_run WHERE status='done' GROUP BY scene")}
        for k, v in SCENES.items():
            L.append(f"{k}：{v['title']}（{v['minutes']} 分钟，做过 {done.get(k, 0)} 次）— {v['desc']}")

    elif area == "attention":
        items = nudges.attention(st)
        L.append(nudges.as_text(items) if items else "现在没有特别要提醒的。")

    text = "\n".join(L)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n（后面还有，太长先省略）"
    return {"ok": True, "area": area, "text": text}
