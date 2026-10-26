#!/usr/bin/env python3
"""显伴·小光 demo 本机代理：静态托管 + ModelFlare 流式 + 记忆 v0.1 落盘。

密钥只读环境变量 MODELFLARE_API_KEY，绝不写进前端或日志。
技术钩子 emotion：请求发出(前端)→30；首 token→39；结束→02；审批 chip→35。
SSE 只在状态变时推 event: emotion，不在每个 token 推。

记忆 v0.1（按用户隔离）::
  demo/data/users/{user_id}/user_profile.json
  demo/data/users/{user_id}/memory_entry.jsonl
  demo/data/users/{user_id}/plan_step.jsonl

主动问候 v0.1::
  last_chat_at 空闲≥24h 才推；静默窗 23:00–08:00（Asia/Shanghai）不推；
  proactive_enabled 可关；近 72h lazy_day → 文案套 B，否则意图套 A；emotion→35。

蜕变分享卡 v0.1::
  GET /api/share → 9:16 卡文案字段（intent/高光/诚实账/surprise_line）。

晋升 / incentive v0.1::
  profile.incentive = { xp, rank: mengya|weiguang|xiaoguang, badges[] }
  阈值 0/30/90；plan_step→done → +10xp；当日首完成发 badge today_one_step；
  POST /api/demo/promote 造数灌满。
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEMO_DIR = Path(__file__).resolve().parent
DATA_ROOT = DEMO_DIR / "data" / "users"
CONFIG_PATH = DEMO_DIR.parent / "config" / "llm.json"
DEFAULT_PORT = 8765
HOST = "127.0.0.1"
DEFAULT_USER = "demo"
TZ8 = timezone(timedelta(hours=8))
USER_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
MEMORY_TOP_K = 5
IDLE_HOURS = 24
LAZY_DAY_LOOKBACK_HOURS = 72
SILENT_START = 23  # inclusive
SILENT_END = 8    # exclusive; 23:00–08:00
# 注入优先 kind；lazy_day 可进摘要但文案侧不作鸡血催促
KIND_PRIORITY = {"insight": 0, "good_news": 1, "boundary": 2, "preference": 3, "lazy_day": 4}

# 晋升：段位阈值与文案
RANK_ORDER = ("mengya", "weiguang", "xiaoguang")
RANK_THRESHOLD = {"mengya": 0, "weiguang": 30, "xiaoguang": 90}
RANK_LABEL = {"mengya": "萌芽", "weiguang": "微光", "xiaoguang": "小光"}
XP_PER_DONE = 10
BADGE_TODAY = "today_one_step"
BADGE_LABEL = {"today_one_step": "今日一小步"}


def default_incentive() -> dict:
    return {"xp": 0, "rank": "mengya", "badges": [], "last_badge_day": ""}


def rank_for_xp(xp: int) -> str:
    xp = max(0, int(xp or 0))
    cur = "mengya"
    for rid in RANK_ORDER:
        if xp >= RANK_THRESHOLD[rid]:
            cur = rid
    return cur


def normalize_incentive(raw: Any) -> dict:
    base = default_incentive()
    if not isinstance(raw, dict):
        return base
    try:
        xp = int(raw.get("xp") or 0)
    except (TypeError, ValueError):
        xp = 0
    xp = max(0, min(xp, 9999))
    badges = raw.get("badges") or []
    if isinstance(badges, str):
        badges = [badges]
    if not isinstance(badges, list):
        badges = []
    clean_badges: list[str] = []
    for b in badges:
        s = str(b).strip()[:64]
        if s and s not in clean_badges:
            clean_badges.append(s)
    rank = str(raw.get("rank") or "").strip()
    if rank not in RANK_THRESHOLD:
        rank = rank_for_xp(xp)
    # 以 xp 为准校正段位（防脏数据）
    rank = rank_for_xp(xp)
    day = str(raw.get("last_badge_day") or "").strip()[:16]
    return {"xp": xp, "rank": rank, "badges": clean_badges[:20], "last_badge_day": day}


def incentive_public(inc: dict) -> dict:
    """前端展示用字段。"""
    inc = normalize_incentive(inc)
    xp = inc["xp"]
    rank = inc["rank"]
    # 段内进度：相对下一档
    idx = RANK_ORDER.index(rank)
    cur_th = RANK_THRESHOLD[rank]
    if idx + 1 < len(RANK_ORDER):
        next_rank = RANK_ORDER[idx + 1]
        next_th = RANK_THRESHOLD[next_rank]
        span = max(1, next_th - cur_th)
        prog = max(0.0, min(1.0, (xp - cur_th) / span))
        next_label = RANK_LABEL[next_rank]
        xp_to_next = max(0, next_th - xp)
    else:
        next_rank = None
        next_label = None
        prog = 1.0
        xp_to_next = 0
    return {
        "xp": xp,
        "rank": rank,
        "rank_label": RANK_LABEL.get(rank, rank),
        "badges": list(inc["badges"]),
        "badge_labels": [BADGE_LABEL.get(b, b) for b in inc["badges"]],
        "last_badge_day": inc.get("last_badge_day") or "",
        "bar_progress": round(prog, 4),
        "next_rank": next_rank,
        "next_rank_label": next_label,
        "xp_to_next": xp_to_next,
        "thresholds": dict(RANK_THRESHOLD),
        "chain": [{"id": r, "label": RANK_LABEL[r], "at": RANK_THRESHOLD[r]} for r in RANK_ORDER],
    }


def today_key(now: datetime | None = None) -> str:
    n = now or datetime.now(TZ8)
    return n.astimezone(TZ8).strftime("%Y-%m-%d")


def apply_xp_gain(user_id: str, gain: int = XP_PER_DONE, *, grant_today_badge: bool = True) -> dict:
    """+xp，可能升段、发当日勋章。返回 events + incentive。"""
    profile = read_profile(user_id)
    before = normalize_incentive(profile.get("incentive"))
    xp = before["xp"] + max(0, int(gain))
    rank_before = before["rank"]
    rank_after = rank_for_xp(xp)
    badges = list(before["badges"])
    day = today_key()
    badge_new = None
    last_badge_day = before.get("last_badge_day") or ""
    if grant_today_badge and last_badge_day != day:
        # 当日首完成 → 发 today_one_step（已有则只刷新 day，不重复事件）
        if BADGE_TODAY not in badges:
            badges.append(BADGE_TODAY)
            badge_new = BADGE_TODAY
        last_badge_day = day

    after = normalize_incentive({
        "xp": xp,
        "rank": rank_after,
        "badges": badges,
        "last_badge_day": last_badge_day,
    })
    merge_profile(user_id, {"incentive": after})
    rank_up = rank_after != rank_before
    if rank_up:
        toast_sub = "进入「%s」" % RANK_LABEL.get(rank_after, rank_after)
    elif badge_new:
        toast_sub = "解锁勋章「%s」" % BADGE_LABEL.get(badge_new, badge_new)
    else:
        toast_sub = "+%d XP" % max(0, int(gain))
    events = {
        "xp_gained": max(0, int(gain)),
        "rank_up": rank_up,
        "rank_before": rank_before,
        "rank_after": rank_after,
        "badge_unlocked": badge_new,
        "toast_title": "又近了一点",
        "toast_sub": toast_sub,
    }
    return {"incentive": incentive_public(after), "events": events, "incentive_raw": after}


def seed_promote(user_id: str) -> dict:
    """路演造数：灌满至小光 + 今日一小步。"""
    ensure_user_dir(user_id)
    filled = normalize_incentive({
        "xp": RANK_THRESHOLD["xiaoguang"],
        "rank": "xiaoguang",
        "badges": [BADGE_TODAY],
        "last_badge_day": today_key(),
    })
    merge_profile(user_id, {"incentive": filled})
    # 可选：补一条已完成微步，方便计划区有内容
    plans = read_plans(user_id)
    if not any(str(p.get("status")) in ("done", "completed", "ok") for p in plans):
        try:
            append_plan(
                user_id,
                {
                    "title": "晚上：30 秒自我介绍（造数）",
                    "status": "done",
                    "source": "demo_promote",
                },
            )
        except ValueError:
            pass
    return {
        "ok": True,
        "user_id": user_id,
        "incentive": incentive_public(filled),
        "events": {
            "xp_gained": RANK_THRESHOLD["xiaoguang"],
            "rank_up": True,
            "rank_before": "mengya",
            "rank_after": "xiaoguang",
            "badge_unlocked": BADGE_TODAY,
            "toast_title": "又近了一点",
            "toast_sub": "进入「小光」",
            "seeded": True,
        },
    }


def rewrite_plans(user_id: str, items: list[dict]) -> None:
    write_jsonl(user_dir(user_id) / "plan_step.jsonl", items)


def mark_plan_done(user_id: str, plan_id: str | None = None, title: str | None = None) -> dict:
    """将某 plan_step 标为 done；若已是 done 则不重复发奖。可无 id 时新建一条 done。"""
    ensure_user_dir(user_id)
    plans = read_plans(user_id)
    target = None
    if plan_id:
        for p in plans:
            if str(p.get("id")) == str(plan_id):
                target = p
                break
    if target is None and title:
        # 找同 title 且 todo 的
        for p in plans:
            if str(p.get("title") or "") == title and str(p.get("status") or "todo") not in ("done", "completed", "ok"):
                target = p
                break
    already = False
    if target is None:
        created = append_plan(
            user_id,
            {
                "title": (title or "今日微步").strip()[:200] or "今日微步",
                "status": "done",
                "source": "checkin",
            },
        )
        target = created
        reward = apply_xp_gain(user_id, XP_PER_DONE, grant_today_badge=True)
        return {"plan": target, "already_done": False, **reward}

    st = str(target.get("status") or "todo")
    if st in ("done", "completed", "ok"):
        already = True
        profile = read_profile(user_id)
        return {
            "plan": target,
            "already_done": True,
            "incentive": incentive_public(profile.get("incentive")),
            "events": {
                "xp_gained": 0,
                "rank_up": False,
                "rank_before": normalize_incentive(profile.get("incentive"))["rank"],
                "rank_after": normalize_incentive(profile.get("incentive"))["rank"],
                "badge_unlocked": None,
                "toast_title": "又近了一点",
                "toast_sub": "今天这步已经记过了",
            },
        }

    # 改写 status
    new_items = []
    for p in plans:
        if str(p.get("id")) == str(target.get("id")):
            p = dict(p)
            p["status"] = "done"
            p["done_at"] = now_iso()
            target = p
        new_items.append(p)
    rewrite_plans(user_id, new_items)
    reward = apply_xp_gain(user_id, XP_PER_DONE, grant_today_badge=True)
    return {"plan": target, "already_done": False, **reward}



def now_iso() -> str:
    return datetime.now(TZ8).replace(microsecond=0).isoformat()


def load_config() -> dict:
    cfg = {
        "baseUrl": "https://modelflare.dev/v1",
        "model": "gpt-6.1-sol",
        "reasoning": "low",
        "apiKeyEnv": "MODELFLARE_API_KEY",
    }
    if CONFIG_PATH.is_file():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(
                    {
                        k: data[k]
                        for k in ("baseUrl", "model", "reasoning", "apiKeyEnv")
                        if k in data
                    }
                )
        except Exception as e:
            print(f"[warn] 读取 llm.json 失败，使用默认: {e}", file=sys.stderr)
    return cfg


CFG = load_config()


def get_api_key() -> str | None:
    env_name = CFG.get("apiKeyEnv") or "MODELFLARE_API_KEY"
    key = os.environ.get(env_name) or os.environ.get("MODELFLARE_API_KEY")
    if not key or not str(key).strip():
        return None
    return str(key).strip()


def sanitize_user_id(raw: Any) -> str | None:
    """合法 user_id 原样返回；缺省/非法返回 None（禁止静默落到 demo）。"""
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if not USER_ID_RE.match(s):
        return None
    if s in (".", "..") or "/" in s or "\\" in s:
        return None
    return s


def user_dir(user_id: str) -> Path:
    return DATA_ROOT / user_id


def ensure_user_dir(user_id: str) -> Path:
    d = user_dir(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_profile(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "agent_name": "小光",
        "agent_avatar_id": "xiaoguang_capsule_v1",
        "intent_primary": "",
        "intent_why": "",
        "intent_sub": "",
        "schedule_hint": "",
        "traits": [],
        "mbti_hint": "",
        "boundaries": [],
        "values": [],
        "preferred_address": "小光",
        "last_chat_at": "",
        "last_proactive_at": "",
        "proactive_enabled": True,
        "incentive": default_incentive(),
        "updated_at": now_iso(),
    }


def read_profile(user_id: str) -> dict:
    path = user_dir(user_id) / "user_profile.json"
    if not path.is_file():
        return default_profile(user_id)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_profile(user_id)
        base = default_profile(user_id)
        base.update(data)
        base["user_id"] = user_id
        return base
    except Exception:
        return default_profile(user_id)


def write_profile(user_id: str, profile: dict) -> dict:
    ensure_user_dir(user_id)
    out = default_profile(user_id)
    out.update({k: v for k, v in profile.items() if k != "user_id"})
    out["user_id"] = user_id
    out["updated_at"] = now_iso()
    # 规范化列表字段
    for key in ("traits", "boundaries", "values"):
        val = out.get(key) or []
        if isinstance(val, str):
            val = [v.strip() for v in val.split(",") if v.strip()]
        if not isinstance(val, list):
            val = []
        out[key] = [str(x)[:80] for x in val][:20]
    # proactive flags
    pe = out.get("proactive_enabled", True)
    if isinstance(pe, str):
        pe = pe.strip().lower() not in ("0", "false", "no", "off")
    out["proactive_enabled"] = bool(pe)
    for ts_key in ("last_chat_at", "last_proactive_at"):
        v = out.get(ts_key) or ""
        out[ts_key] = str(v)[:40] if v else ""
    out["incentive"] = normalize_incentive(out.get("incentive"))
    path = user_dir(user_id) / "user_profile.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out


def merge_profile(user_id: str, patch: dict) -> dict:
    cur = read_profile(user_id)
    for k, v in patch.items():
        if k == "user_id":
            continue
        if v is None:
            continue
        cur[k] = v
    return write_profile(user_id, cur)


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    items: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    items.append(obj)
    except Exception:
        return []
    return items


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, obj: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return obj


def read_memories(user_id: str) -> list[dict]:
    return read_jsonl(user_dir(user_id) / "memory_entry.jsonl")


def read_plans(user_id: str) -> list[dict]:
    return read_jsonl(user_dir(user_id) / "plan_step.jsonl")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def append_memory(user_id: str, entry: dict) -> dict:
    ensure_user_dir(user_id)
    text = str(entry.get("text") or "").strip()[:500]
    if not text:
        raise ValueError("memory text 不能为空")
    kind = str(entry.get("kind") or "insight").strip()[:32] or "insight"
    obj = {
        "id": str(entry.get("id") or new_id("mem")),
        "kind": kind,
        "text": text,
        "source": str(entry.get("source") or "manual")[:64],
        "created_at": entry.get("created_at") or now_iso(),
    }
    return append_jsonl(user_dir(user_id) / "memory_entry.jsonl", obj)


def append_plan(user_id: str, entry: dict) -> dict:
    ensure_user_dir(user_id)
    title = str(entry.get("title") or "").strip()[:200]
    if not title:
        raise ValueError("plan title 不能为空")
    status = str(entry.get("status") or "todo").strip()[:32] or "todo"
    obj = {
        "id": str(entry.get("id") or new_id("plan")),
        "title": title,
        "status": status,
        "source": str(entry.get("source") or "manual")[:64],
        "created_at": entry.get("created_at") or now_iso(),
    }
    return append_jsonl(user_dir(user_id) / "plan_step.jsonl", obj)


def delete_memory(user_id: str, mem_id: str) -> bool:
    path = user_dir(user_id) / "memory_entry.jsonl"
    items = read_jsonl(path)
    kept = [x for x in items if str(x.get("id")) != mem_id]
    if len(kept) == len(items):
        return False
    write_jsonl(path, kept)
    return True


def select_memories_for_inject(items: list[dict], k: int = MEMORY_TOP_K) -> list[dict]:
    """优先 insight/good_news；lazy_day 可进但不作鸡血素材。近 Top-k。"""
    if not items:
        return []

    def sort_key(m: dict) -> tuple:
        kind = str(m.get("kind") or "")
        pri = KIND_PRIORITY.get(kind, 9)
        created = str(m.get("created_at") or "")
        return (pri, created)

    # 先按时间倒序取较新的候选，再按 kind 优先级
    by_time = sorted(items, key=lambda m: str(m.get("created_at") or ""), reverse=True)
    candidates = by_time[: max(k * 3, k)]
    ranked = sorted(candidates, key=sort_key)
    return ranked[:k]


def build_memory_system_addon(user_id: str) -> str:
    """拼进 system：硬带 intent_primary / boundaries / agent_name；无命中不编造。"""
    profile = read_profile(user_id)
    lines: list[str] = []
    agent = (profile.get("agent_name") or "小光").strip() or "小光"
    lines.append(f"你的名字是{agent}。")

    intent = (profile.get("intent_primary") or "").strip()
    if intent:
        lines.append(f"用户当前显化意图（intent_primary）：{intent}")
    why = (profile.get("intent_why") or "").strip()
    if why:
        lines.append(f"为何重要：{why}")
    sub = (profile.get("intent_sub") or "").strip()
    if sub:
        lines.append(f"次意图：{sub}")

    boundaries = profile.get("boundaries") or []
    if isinstance(boundaries, list) and boundaries:
        btxt = "、".join(str(b) for b in boundaries if str(b).strip())
        if btxt:
            lines.append(f"边界（务必遵守）：{btxt}")

    addr = (profile.get("preferred_address") or "").strip()
    if addr and addr != agent:
        lines.append(f"用户偏好称呼你为「{addr}」。")

    mems = select_memories_for_inject(read_memories(user_id), MEMORY_TOP_K)
    if mems:
        lines.append("已记住的要点（仅用下列事实，无命中勿编造）：")
        for m in mems:
            kind = str(m.get("kind") or "insight")
            text = str(m.get("text") or "").strip()
            if not text:
                continue
            if kind == "lazy_day":
                # 不作鸡血催促：只作背景事实
                lines.append(f"- [{kind}] {text}（提及则温柔，勿催促）")
            else:
                lines.append(f"- [{kind}] {text}")
    else:
        lines.append("尚无落盘记忆条目；不要假装记得用户没说过的事。")

    # 今日一小步（最近一条 todo）
    plans = read_plans(user_id)
    todos = [p for p in plans if str(p.get("status")) == "todo"]
    if todos:
        latest = sorted(todos, key=lambda p: str(p.get("created_at") or ""), reverse=True)[0]
        title = str(latest.get("title") or "").strip()
        if title:
            lines.append(f"今日一小步（plan_step）：{title}")

    body = "\n".join(lines)
    # 控制 token：截断
    if len(body) > 1200:
        body = body[:1200] + "…"
    return "【记忆摘要】\n" + body



def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    try:
        # support ...+08:00 / Z / naive
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ8)
        return dt.astimezone(TZ8)
    except Exception:
        return None


def hours_since(ts: str | None, now: datetime | None = None) -> float | None:
    dt = parse_iso(ts)
    if dt is None:
        return None
    now = now or datetime.now(TZ8)
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def in_silent_window(now: datetime | None = None, simulate_hour: int | None = None) -> bool:
    """静默窗 23:00–08:00（Asia/Shanghai）。simulate_hour 覆写当前小时便于评审。"""
    if simulate_hour is not None:
        h = int(simulate_hour) % 24
    else:
        now = now or datetime.now(TZ8)
        h = now.hour
    # 23,0,1,...,7
    return h >= SILENT_START or h < SILENT_END


def recent_lazy_day(user_id: str, now: datetime | None = None) -> dict | None:
    """近 72h 内最新一条 lazy_day；没有则 None。"""
    now = now or datetime.now(TZ8)
    cutoff = now - timedelta(hours=LAZY_DAY_LOOKBACK_HOURS)
    best: dict | None = None
    best_dt: datetime | None = None
    for m in read_memories(user_id):
        if str(m.get("kind") or "") != "lazy_day":
            continue
        dt = parse_iso(m.get("created_at"))
        if dt is None or dt < cutoff:
            continue
        if best_dt is None or dt > best_dt:
            best = m
            best_dt = dt
    return best


def pick_proactive_topic(user_id: str) -> dict:
    """选题：优先 intent_primary；否则一条 insight/good_news；禁 lazy 催促。"""
    profile = read_profile(user_id)
    intent = (profile.get("intent_primary") or "").strip()
    if intent:
        return {"kind": "intent", "text": intent, "source": "profile"}
    mems = select_memories_for_inject(read_memories(user_id), MEMORY_TOP_K)
    for m in mems:
        kind = str(m.get("kind") or "")
        if kind in ("insight", "good_news"):
            text = str(m.get("text") or "").strip()
            if text:
                return {"kind": kind, "text": text, "source": "memory", "id": m.get("id")}
    # 今日一小步兜底
    plans = read_plans(user_id)
    todos = [p for p in plans if str(p.get("status")) == "todo"]
    if todos:
        latest = sorted(todos, key=lambda p: str(p.get("created_at") or ""), reverse=True)[0]
        title = str(latest.get("title") or "").strip()
        if title:
            return {"kind": "plan_step", "text": title, "source": "plan"}
    return {"kind": "none", "text": "", "source": "none"}


def build_proactive_copy(user_id: str, now: datetime | None = None) -> dict:
    """统一模板选择器（模拟主动 / 真推送共用）。
    近 72h lazy_day → 套 B；否则意图套 A。
    """
    now = now or datetime.now(TZ8)
    lazy = recent_lazy_day(user_id, now)
    topic = pick_proactive_topic(user_id)
    if lazy is not None:
        text = "慢下来也没关系，要不要抽一张灵感卡？"
        return {
            "template": "lazy_gentle",
            "text": text,
            "emotion_id": "35",
            "topic": topic,
            "lazy_ref": {"id": lazy.get("id"), "text": lazy.get("text")},
        }
    intent = ""
    if topic.get("kind") == "intent":
        intent = topic.get("text") or ""
    else:
        # 无 intent 时仍用套 A，占位用 topic 或默认
        intent = (topic.get("text") or "").strip() or "想成为的人"
    # 意图过长截断
    intent_short = intent if len(intent) <= 24 else intent[:22] + "…"
    text = f"还在靠近「{intent_short}」吗？今天一小步就够。"
    return {
        "template": "intent",
        "text": text,
        "emotion_id": "35",
        "topic": topic,
        "lazy_ref": None,
    }


def evaluate_proactive(
    user_id: str,
    *,
    force: bool = False,
    simulate_hour: int | None = None,
    now: datetime | None = None,
) -> dict:
    """返回是否该主动 + 原因 + 文案草稿。force 跳过 idle/静默，不跳过开关。"""
    now = now or datetime.now(TZ8)
    profile = read_profile(user_id)
    copy = build_proactive_copy(user_id, now)
    enabled = bool(profile.get("proactive_enabled", True))
    last_chat = profile.get("last_chat_at") or ""
    last_pro = profile.get("last_proactive_at") or ""
    idle_h = hours_since(last_chat, now)
    # 从未聊过：视为「足够空闲」（demo 可推）；有记录则比 24h
    idle_ok = idle_h is None or idle_h >= IDLE_HOURS
    silent = in_silent_window(now, simulate_hour)
    reasons: list[str] = []
    if not enabled:
        reasons.append("主动问候已关闭（proactive_enabled=false）")
    if not idle_ok:
        left = IDLE_HOURS - (idle_h or 0)
        reasons.append(
            "未满 %dh 空闲（距上次聊天约 %.1fh，还需约 %.1fh）"
            % (IDLE_HOURS, idle_h or 0, max(0.0, left))
        )
    if silent:
        h = int(simulate_hour) % 24 if simulate_hour is not None else now.hour
        reasons.append("静默窗 23:00–08:00 内不推（当前小时 %02d:00）" % h)

    # force 跳过 idle/静默，但不跳过开关（关主动时模拟/强制都不推）
    should = enabled and (force or (idle_ok and not silent))
    result = {
        "ok": True,
        "user_id": user_id,
        "should_push": should,
        "forced": bool(force),
        "proactive_enabled": enabled,
        "idle_hours": None if idle_h is None else round(idle_h, 2),
        "idle_required_hours": IDLE_HOURS,
        "last_chat_at": last_chat or None,
        "last_proactive_at": last_pro or None,
        "in_silent_window": silent,
        "simulate_hour": simulate_hour,
        "now": now.replace(microsecond=0).isoformat(),
        "reasons": reasons,
        "message": copy["text"] if should else None,
        "template": copy["template"],
        "emotion_id": "35",
        "topic": copy["topic"],
        "lazy_ref": copy.get("lazy_ref"),
    }
    if not should:
        result["block_reason"] = "；".join(reasons) if reasons else "不满足主动条件"
    return result


def touch_last_chat(user_id: str) -> dict:
    return merge_profile(user_id, {"last_chat_at": now_iso()})


def mark_proactive_sent(user_id: str) -> dict:
    return merge_profile(user_id, {"last_proactive_at": now_iso()})


def build_share_card(user_id: str, now: datetime | None = None) -> dict:
    """蜕变分享卡数据：从 profile / memory_entry / plan_step 抽取。

    surprise_line 优先级：
      ① good_news≥3 → 点主题
      ② 有 lazy 仍完成 →「慢的日子也走了 X 步」
      ③ 否则 day1 why × dayN 计划反差
    """
    now = now or datetime.now(TZ8)
    profile = read_profile(user_id)
    memories = read_memories(user_id)
    plans = read_plans(user_id)

    agent = (profile.get("agent_name") or "小光").strip() or "小光"
    intent = (profile.get("intent_primary") or "").strip()
    intent_why = (profile.get("intent_why") or "").strip()
    intent_sub = (profile.get("intent_sub") or "").strip()

    good_news = [
        m for m in memories
        if str(m.get("kind") or "") == "good_news" and str(m.get("text") or "").strip()
    ]
    lazies = [
        m for m in memories
        if str(m.get("kind") or "") == "lazy_day" and str(m.get("text") or "").strip()
    ]
    insights = [
        m for m in memories
        if str(m.get("kind") or "") == "insight" and str(m.get("text") or "").strip()
    ]

    # 天数：最早记忆/计划 → 今天；无数据则为 0（不编造）
    stamps: list[datetime] = []
    for m in memories:
        dt = parse_iso(m.get("created_at"))
        if dt:
            stamps.append(dt)
    for p in plans:
        dt = parse_iso(p.get("created_at"))
        if dt:
            stamps.append(dt)
    if stamps:
        days = max(1, (now.date() - min(stamps).date()).days + 1)
    else:
        days = 0

    # 今日 / 最近一小步
    plans_sorted = sorted(plans, key=lambda p: str(p.get("created_at") or ""), reverse=True)
    latest_plan = plans_sorted[0] if plans_sorted else None
    step_title = ""
    if latest_plan:
        step_title = str(latest_plan.get("title") or "").strip()
    done_plans = [
        p for p in plans
        if str(p.get("status") or "") in ("done", "completed", "ok")
    ]
    # 无明确 done 时，有 plan 条数也算「走了」
    steps_walked = len(done_plans) if done_plans else len(plans)

    empty = not bool(intent or memories or plans)

    # 前后意图（空用户不编造）
    before_intent = intent_why or intent or ""
    after_intent = step_title or intent_sub or intent or ""

    # 高光句：最新 good_news，否则 insight；空则留空
    highlight = ""
    if good_news:
        g_sorted = sorted(good_news, key=lambda m: str(m.get("created_at") or ""), reverse=True)
        highlight = str(g_sorted[0].get("text") or "").strip()
    elif insights:
        i_sorted = sorted(insights, key=lambda m: str(m.get("created_at") or ""), reverse=True)
        highlight = str(i_sorted[0].get("text") or "").strip()

    # 偷懒诚实账（只陈述；无则空）
    lazy_line = ""
    if lazies:
        l_sorted = sorted(lazies, key=lambda m: str(m.get("created_at") or ""), reverse=True)
        lazy_line = str(l_sorted[0].get("text") or "").strip()

    # surprise_line：有数据才生成；空用户给 empty hint
    rule = "empty"
    surprise = ""
    if empty:
        surprise = ""
        rule = "empty"
    elif len(good_news) >= 3:
        snippets = [str(m.get("text") or "").strip() for m in good_news[:3]]
        theme = " · ".join(s[:18] + ("…" if len(s) > 18 else "") for s in snippets if s)
        surprise = f"这 {days} 天，好消息叠了 {len(good_news)} 次：{theme}"
        rule = "good_news_theme"
    elif lazies and steps_walked > 0:
        surprise = f"慢的日子也走了 {steps_walked} 步——偷懒被看见，脚步没消失。"
        rule = "lazy_still_walked"
    elif before_intent or after_intent:
        b = before_intent if len(before_intent) <= 20 else before_intent[:18] + "…"
        a = (after_intent if len(after_intent) <= 20 else after_intent[:18] + "…") or "今天能走的一小步"
        surprise = f"从「{b}」到「{a}」——反差就是蜕变。"
        rule = "contrast"
    else:
        surprise = f"这 {days} 天，已记下 {len(memories)} 条记忆、{steps_walked} 步微步。"
        rule = "stats"

    surprise = (surprise or "").strip()
    if surprise and surprise == (highlight or "").strip():
        surprise = f"这 {days} 天，意图从模糊走到可执行——反差就是蜕变。"
        rule = "contrast_safe"

    date_str = now.strftime("%Y.%m.%d")
    empty_hint = "还没有蜕变记录。先完成建档或走一小步，再来看报告。"
    if empty:
        share_text = (
            f"【显伴·{agent}】蜕变报告\n"
            f"{empty_hint}\n"
            f"— {date_str}"
        )
    else:
        share_text = (
            f"【显伴·{agent}】{days} 天蜕变\n"
            f"意图：{intent or before_intent or '（未设定）'}\n"
            f"今日一小步：{after_intent or '（暂无）'}\n"
            f"高光：{highlight or '（暂无）'}\n"
            f"诚实账：{lazy_line or '（暂无）'}\n"
            f"{surprise}\n"
            f"— {date_str}"
        )

    return {
        "ok": True,
        "user_id": user_id,
        "agent_name": agent,
        "agent_avatar_id": profile.get("agent_avatar_id") or "xiaoguang_capsule_v1",
        "days": days,
        "date": date_str,
        "intent_primary": intent,
        "before_intent": before_intent,
        "after_intent": after_intent,
        "highlight": highlight,
        "lazy_line": lazy_line,
        "surprise_line": surprise,
        "surprise_rule": rule,
        "good_news_count": len(good_news),
        "lazy_count": len(lazies),
        "steps_walked": steps_walked,
        "share_text": share_text,
        "placeholder": empty,
        "empty": empty,
        "empty_hint": empty_hint if empty else "",
    }



XG_BASE_SYSTEM = (
    "你是小光，用户的显化陪伴——只帮你把「想成为的人」收成今天能走的一小步，不做万能助理。"
    "只用简体中文。短句、温柔、不说教。不要列长清单；每次只收成一个今天可走的小动作。"
    "不扮演万能助手（不写代码、不查资料、不闲聊八卦），把话题轻轻拉回显化与当下一步。"
)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DEMO_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code: int, message: str) -> None:
        self._json_response(code, {"error": message})

    def _parse_path(self) -> tuple[str, dict]:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        flat = {k: (v[0] if isinstance(v, list) and v else "") for k, v in qs.items()}
        return parsed.path, flat

    def _user_from(self, qs: dict, payload: dict | None = None) -> str | None:
        raw = None
        if payload and isinstance(payload, dict):
            raw = payload.get("user_id")
        if raw is None or raw == "":
            raw = qs.get("user_id")
        return sanitize_user_id(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path, qs = self._parse_path()
        if path == "/api/memory":
            self._get_memory(qs)
            return
        if path == "/api/plan":
            self._get_plan(qs)
            return
        if path == "/api/health":
            self._json_response(
                200,
                {
                    "ok": True,
                    "model": CFG.get("model"),
                    "has_key": bool(get_api_key()),
                    "memory": "v0.1",
                    "proactive": "v0.1",
                    "share": "v0.1",
                    "incentive": "v0.1",
                },
            )
            return
        if path == "/api/proactive":
            self._get_proactive(qs)
            return
        if path == "/api/share":
            self._get_share(qs)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path, qs = self._parse_path()
        if path == "/api/chat":
            self._handle_chat(qs)
            return
        if path == "/api/memory":
            self._post_memory(qs)
            return
        if path == "/api/plan":
            self._post_plan(qs)
            return
        if path == "/api/proactive":
            self._post_proactive(qs)
            return
        if path == "/api/activity":
            self._post_activity(qs)
            return
        if path == "/api/demo/promote":
            self._post_demo_promote(qs)
            return
        self._json_error(404, "未知接口")

    def do_DELETE(self) -> None:
        path, qs = self._parse_path()
        # DELETE /api/memory/{id}
        m = re.match(r"^/api/memory/([^/]+)$", path)
        if not m:
            self._json_error(404, "未知接口")
            return
        mem_id = urllib.parse.unquote(m.group(1))
        user_id = self._user_from(qs)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        if not mem_id or mem_id in (".", ".."):
            self._json_error(400, "id 非法")
            return
        ok = delete_memory(user_id, mem_id)
        if not ok:
            self._json_error(404, "记忆不存在")
            return
        self._json_response(200, {"ok": True, "deleted": mem_id, "user_id": user_id})

    def _get_memory(self, qs: dict) -> None:
        user_id = self._user_from(qs)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        profile = read_profile(user_id)
        memories = read_memories(user_id)
        # 新→旧
        memories = sorted(memories, key=lambda m: str(m.get("created_at") or ""), reverse=True)
        self._json_response(
            200,
            {
                "user_id": user_id,
                "profile": profile,
                "memories": memories,
                "empty_hint": "小光还没记住什么",
            },
        )

    def _get_plan(self, qs: dict) -> None:
        user_id = self._user_from(qs)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        plans = read_plans(user_id)
        plans = sorted(plans, key=lambda p: str(p.get("created_at") or ""), reverse=True)
        profile = read_profile(user_id)
        self._json_response(
            200,
            {
                "user_id": user_id,
                "plans": plans,
                "incentive": incentive_public(profile.get("incentive")),
            },
        )

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 512_000:
            self._json_error(400, "请求体无效或过大")
            return None
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json_error(400, "JSON 解析失败")
            return None
        if not isinstance(payload, dict):
            self._json_error(400, "JSON 须为对象")
            return None
        return payload

    def _post_memory(self, qs: dict) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        user_id = self._user_from(qs, payload)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        result: dict[str, Any] = {"user_id": user_id}

        # 部分字段合并写 profile
        if "profile" in payload and isinstance(payload["profile"], dict):
            result["profile"] = merge_profile(user_id, payload["profile"])
        elif any(
            k in payload
            for k in (
                "intent_primary",
                "intent_why",
                "intent_sub",
                "boundaries",
                "agent_name",
                "preferred_address",
                "traits",
                "values",
                "mbti_hint",
                "schedule_hint",
                "agent_avatar_id",
            )
        ):
            result["profile"] = merge_profile(user_id, payload)

        # 追加 memory_entry（单条或列表）
        created_mems: list[dict] = []
        if "memory" in payload and isinstance(payload["memory"], dict):
            try:
                created_mems.append(append_memory(user_id, payload["memory"]))
            except ValueError as e:
                self._json_error(400, str(e))
                return
        if "memories" in payload and isinstance(payload["memories"], list):
            for m in payload["memories"]:
                if isinstance(m, dict):
                    try:
                        created_mems.append(append_memory(user_id, m))
                    except ValueError as e:
                        self._json_error(400, str(e))
                        return
        if created_mems:
            result["memories_created"] = created_mems

        # 灵感结束可顺带写 plan_step
        created_plans: list[dict] = []
        if "plan" in payload and isinstance(payload["plan"], dict):
            try:
                created_plans.append(append_plan(user_id, payload["plan"]))
            except ValueError as e:
                self._json_error(400, str(e))
                return
        if "plans" in payload and isinstance(payload["plans"], list):
            for p in payload["plans"]:
                if isinstance(p, dict):
                    try:
                        created_plans.append(append_plan(user_id, p))
                    except ValueError as e:
                        self._json_error(400, str(e))
                        return
        if created_plans:
            result["plans_created"] = created_plans

        if "profile" not in result:
            result["profile"] = read_profile(user_id)
        result["ok"] = True
        self._json_response(200, result)

    def _post_plan(self, qs: dict) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        user_id = self._user_from(qs, payload)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        action = str(payload.get("action") or "").strip().lower()
        # 完成微步 → 持久化 done + incentive
        if action in ("complete", "done", "checkin") or str(payload.get("status") or "").strip() in (
            "done",
            "completed",
        ) and payload.get("id"):
            plan_id = payload.get("id") or payload.get("plan_id")
            title = payload.get("title")
            if isinstance(payload.get("plan"), dict):
                plan_id = plan_id or payload["plan"].get("id")
                title = title or payload["plan"].get("title")
            result = mark_plan_done(user_id, plan_id=str(plan_id) if plan_id else None, title=str(title) if title else None)
            self._json_response(
                200,
                {
                    "ok": True,
                    "user_id": user_id,
                    "plan": result.get("plan"),
                    "already_done": bool(result.get("already_done")),
                    "incentive": result.get("incentive"),
                    "events": result.get("events"),
                },
            )
            return
        entry = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        try:
            created = append_plan(user_id, entry)
        except ValueError as e:
            self._json_error(400, str(e))
            return
        # 直接以 done 新建也发奖
        reward = None
        if str(created.get("status") or "") in ("done", "completed", "ok"):
            reward = apply_xp_gain(user_id, XP_PER_DONE, grant_today_badge=True)
        out: dict[str, Any] = {"ok": True, "user_id": user_id, "plan": created}
        if reward:
            out["incentive"] = reward["incentive"]
            out["events"] = reward["events"]
        else:
            out["incentive"] = incentive_public(read_profile(user_id).get("incentive"))
        self._json_response(200, out)

    def _post_demo_promote(self, qs: dict) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        user_id = self._user_from(qs, payload)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        result = seed_promote(user_id)
        self._json_response(200, result)

    def _get_proactive(self, qs: dict) -> None:
        user_id = self._user_from(qs)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        force = str(qs.get("force") or "").strip().lower() in ("1", "true", "yes")
        simulate_hour = None
        if qs.get("simulate_hour") not in (None, ""):
            try:
                simulate_hour = int(qs.get("simulate_hour"))
            except ValueError:
                self._json_error(400, "simulate_hour 须为 0–23 整数")
                return
            if simulate_hour < 0 or simulate_hour > 23:
                self._json_error(400, "simulate_hour 须为 0–23")
                return
        result = evaluate_proactive(
            user_id, force=force, simulate_hour=simulate_hour
        )
        self._json_response(200, result)


    def _get_share(self, qs: dict) -> None:
        user_id = self._user_from(qs)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        self._json_response(200, build_share_card(user_id))

    def _post_proactive(self, qs: dict) -> None:
        """评审/演示：按规则检查（可 force），通过则标记 last_proactive_at 并回文案。"""
        payload = self._read_json_body()
        if payload is None:
            return
        user_id = self._user_from(qs, payload)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        force = bool(payload.get("force")) or str(qs.get("force") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        simulate_hour = payload.get("simulate_hour", qs.get("simulate_hour"))
        sim = None
        if simulate_hour not in (None, ""):
            try:
                sim = int(simulate_hour)
            except (TypeError, ValueError):
                self._json_error(400, "simulate_hour 须为 0–23 整数")
                return
            if sim < 0 or sim > 23:
                self._json_error(400, "simulate_hour 须为 0–23")
                return
        # 可选：写入开关
        if "proactive_enabled" in payload:
            merge_profile(user_id, {"proactive_enabled": payload.get("proactive_enabled")})
        result = evaluate_proactive(user_id, force=force, simulate_hour=sim)
        if result["should_push"]:
            profile = mark_proactive_sent(user_id)
            result["last_proactive_at"] = profile.get("last_proactive_at")
            result["delivered"] = True
        else:
            result["delivered"] = False
        self._json_response(200, result)

    def _post_activity(self, qs: dict) -> None:
        """前端交互心跳：更新 last_chat_at（对话发送时调用）。"""
        payload = self._read_json_body()
        if payload is None:
            return
        user_id = self._user_from(qs, payload)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return
        profile = touch_last_chat(user_id)
        self._json_response(
            200,
            {
                "ok": True,
                "user_id": user_id,
                "last_chat_at": profile.get("last_chat_at"),
            },
        )

    def _emit_emotion(self, eid: str) -> None:
        payload = (
            "event: emotion\ndata: "
            + json.dumps({"emotion_id": eid}, ensure_ascii=False)
            + "\n\n"
        ).encode("utf-8")
        self.wfile.write(payload)
        self.wfile.flush()

    def _handle_chat(self, qs: dict) -> None:
        key = get_api_key()
        if not key:
            self._json_error(
                503,
                "未配置 MODELFLARE_API_KEY。请在启动前 export，或 MODELFLARE_API_KEY=… python3 server.py",
            )
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 512_000:
            self._json_error(400, "请求体无效或过大")
            return
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json_error(400, "JSON 解析失败")
            return
        if not isinstance(payload, dict):
            self._json_error(400, "JSON 须为对象")
            return

        user_id = self._user_from(qs, payload)
        if not user_id:
            self._json_error(400, "user_id 非法")
            return

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            self._json_error(400, "messages 必须是非空数组")
            return
        clean = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if role not in ("system", "user", "assistant") or not isinstance(content, str):
                continue
            clean.append({"role": role, "content": content[:8000]})
        if not clean:
            self._json_error(400, "messages 无有效条目")
            return

        # 用户发了消息 → 刷新 last_chat_at（主动空闲计时重置）
        try:
            touch_last_chat(user_id)
        except Exception:
            pass

        # 注入记忆摘要：合并/替换 system
        mem_addon = build_memory_system_addon(user_id)
        full_system = XG_BASE_SYSTEM + "\n\n" + mem_addon
        if clean and clean[0]["role"] == "system":
            # 前端可能已带人设；以服务端为准，避免丢记忆硬字段
            clean[0] = {"role": "system", "content": full_system}
        else:
            clean.insert(0, {"role": "system", "content": full_system})

        upstream = {
            "model": CFG.get("model") or "gpt-6.1-sol",
            "messages": clean,
            "stream": True,
        }
        reasoning = CFG.get("reasoning")
        if reasoning:
            upstream["reasoning"] = reasoning
            upstream["reasoning_effort"] = reasoning

        url = (CFG.get("baseUrl") or "https://modelflare.dev/v1").rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(upstream).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        try:
            upstream_resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            msg = "上游模型错误 HTTP %s" % e.code
            if err_body:
                try:
                    ej = json.loads(err_body)
                    if isinstance(ej, dict) and ej.get("error"):
                        err = ej["error"]
                        if isinstance(err, dict) and err.get("message"):
                            msg = str(err["message"])[:200]
                        elif isinstance(err, str):
                            msg = err[:200]
                except Exception:
                    msg = (msg + ": " + err_body[:120]).strip()
            self._json_error(502, msg)
            return
        except Exception as e:
            self._json_error(502, "无法连接模型服务: %s" % type(e).__name__)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        # 调试：把本轮注入长度放进响应头（不含内容）
        self.send_header("X-Memory-User", user_id)
        self.send_header("X-Memory-Inject-Chars", str(len(mem_addon)))
        self._cors()
        self.end_headers()

        saw_content = False
        finished = False
        buf = b""
        try:
            while True:
                chunk = upstream_resp.read(1024)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    raw_line = line.decode("utf-8", errors="replace").rstrip("\r")
                    self.wfile.write(line + b"\n")
                    self.wfile.flush()

                    if not raw_line.startswith("data:"):
                        continue
                    data_str = raw_line[5:].strip()
                    if data_str == "[DONE]":
                        if not finished:
                            self._emit_emotion("02")
                            finished = True
                        continue
                    if not data_str:
                        continue
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        continue
                    try:
                        delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content")
                    except Exception:
                        content = None
                    if content and not saw_content:
                        saw_content = True
                        self._emit_emotion("39")
            if buf:
                self.wfile.write(buf)
                self.wfile.flush()
            if not finished:
                self._emit_emotion("02")
                finished = True
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc(file=sys.stderr)
        finally:
            try:
                upstream_resp.close()
            except Exception:
                pass


def main() -> None:
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("用法: python3 server.py [port]", file=sys.stderr)
            sys.exit(2)

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    key = get_api_key()
    key_status = "已设置 (len=%d)" % len(key) if key else "未设置 — /api/chat 会 503"
    print("显伴·小光 demo")
    print("  目录: %s" % DEMO_DIR)
    print("  数据: %s/{user_id}/" % DATA_ROOT)
    print("  模型: %s @ %s" % (CFG.get("model"), CFG.get("baseUrl")))
    print("  密钥: %s" % key_status)
    print("  预览: http://%s:%d/" % (HOST, port))
    print("  聊天: POST /api/chat")
    print("  记忆: GET|POST /api/memory  DELETE /api/memory/{id}")
    print("  计划: GET|POST /api/plan")
    print("  主动: GET|POST /api/proactive  POST /api/activity")
    print("  晋升: POST /api/plan action=complete  ·  POST /api/demo/promote 造数")
    print("  emotion: 首token→39 · 结束→02（请求发出由前端→30）")

    httpd = ThreadingHTTPServer((HOST, port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        httpd.server_close()


if __name__ == "__main__":
    main()
