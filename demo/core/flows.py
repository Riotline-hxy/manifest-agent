"""「许个愿」「让愿望落地」共用的流程：对话样子的全屏层（public/js/tune.js），问题和分支都在前端（public/js/flows.js），
这里只管四件事，都走 POST /api/flow：
- start：开一次练习（scene_run），给前端 TA 自己的记录（ctx）；
- suggest：TA 要建议、或者自己写了一句时调一次模型（让愿望落地：改小一点 / 再加一件 / 第一件事 / 听懂 TA 说的感觉 / 听懂卡在哪、给对症的调整）；
- finish：答完，算结尾（许个愿调一次模型写小光的话），存进 profile.flow_end，练习经验这时给；
  TA 在结尾点「上一步」改了答案再答完，同一次练习重新算，经验不重复给；
- save：只存勾了的。存完把这次的答案清掉，同一次不能存两遍。
中途关掉、或者结尾不存：和别的「聊聊」一样，这次的答案不留（/api/scene/cancel、/api/scene/discard）。
"""
from __future__ import annotations

import json

from . import relearn, wish_flow
from .store import Store

FLOWS = {"seven_steps_lite": wish_flow, "relearn": relearn}


def is_flow(sid: str) -> bool:
    return sid in FLOWS


def _run(store: Store, run_id: str, *, done_ok: bool = True) -> dict:
    run = store.get_scene(run_id)
    if not run or run["scene"] not in FLOWS or run["status"] not in (("open", "done") if done_ok else ("open",)):
        raise KeyError(run_id)
    return run


def start(store: Store, sid: str, wish_id: str = "") -> dict:
    if sid not in FLOWS:
        raise KeyError(sid)
    mod = FLOWS[sid]
    run = store.start_scene(sid)
    store.log("scene", f"开始「{mod.TITLE}」")
    return {"run": {"id": run["id"]}, "scene": {"id": sid, "title": mod.TITLE}, "ctx": mod.ctx(store, wish_id)}


def suggest(store: Store, run_id: str, kind: str, wish_id: str, ref: str = "", label: str = "", text: str = "") -> dict:
    run = _run(store, run_id)
    if run["scene"] != "relearn":
        raise ValueError("这里没有建议")
    return relearn.suggest(store, kind, wish_id, ref, label, text)


def _public(end: dict) -> dict:
    return {k: end.get(k) for k in ("say", "card", "keeps", "acts", "land", "now")}


def finish(store: Store, run_id: str, answers: dict) -> dict:
    run = _run(store, run_id)
    sid = run["scene"]
    mod = FLOWS[sid]
    a = mod.clean(store, answers if isinstance(answers, dict) else {})
    key = json.dumps(a, ensure_ascii=False, sort_keys=True)
    cache = store.profile().get("flow_end") or {}
    # 同一次、同样的答案（比如在结尾点了上一步又原样答完）：不再调模型
    end = cache["end"] if cache.get("run") == run_id and cache.get("key") == key else mod.ending(store, a)
    store.set_profile({"flow_end": {"run": run_id, "key": key, "end": end}})
    store.update_scene(run_id, 1, [a], "done")
    if run["status"] == "open":
        store.log("scene", f"做完「{mod.TITLE}」")
    return _public(end)


def save(store: Store, run_id: str, keys: list) -> dict:
    run = _run(store, run_id)
    if run["status"] != "done":
        raise KeyError(run_id)
    if not run["answers"]:
        raise ValueError("这次聊到的已经处理过了")
    sid = run["scene"]
    mod = FLOWS[sid]
    a = run["answers"][0]
    cache = store.profile().get("flow_end") or {}
    end = cache["end"] if cache.get("run") == run_id else mod.ending(store, a)
    allowed = {k["key"] for k in (end.get("keeps") or []) if not k.get("off")}
    picked = {str(k) for k in (keys or [])} & allowed
    if not picked:
        raise ValueError("还没有勾要存的")
    out = mod.save(store, a, end, picked)
    store.update_scene(run_id, run["step"], [], "done")
    store.set_profile({"flow_end": {}})
    if out.get("reply"):
        store.add_msg("assistant", out["reply"], {"scene": sid, "scene_done": True, "wrote": [w["label"] for w in out["wrote"]]})
    store.log("scene", f"保存了「{mod.TITLE}」里的 {len(out['wrote'])} 项")
    return out
