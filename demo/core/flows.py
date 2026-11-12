"""「显化你的愿望」「调整现有计划」共用的流程：对话样子的全屏层（public/js/tune.js），问题在前端（public/js/flows.js），
这里只管四件事，都走 POST /api/flow：
- start：开一次练习（scene_run），给前端 TA 自己的记录（ctx）；
- step：答完一题调一次模型（显化：每一步接着 TA 的回答说、给出这一步的收获；调整计划：TA 说了哪里不对，按意见重新调）；
- finish：答完，算结尾（显化：小光的小纸条 + 显化卡；调整计划：一份调整方案），存进 profile.flow_end，练习经验这时给；
  TA 在结尾点「上一步」改了答案再答完，同一次练习重新算，经验不重复给；
- save：只存勾了的。存完把这次的答案清掉，同一次不能存两遍。
中途关掉、或者结尾不存：和别的「聊聊」一样，这次的答案不留（/api/scene/cancel、/api/scene/discard）。
"""
from __future__ import annotations

import json

from . import manifest_flow, relearn
from .store import Store
from .util import agent_name, named

FLOWS = {"seven_steps_lite": manifest_flow, "relearn": relearn}


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


def _key(a: dict) -> str:
    return json.dumps(a, ensure_ascii=False, sort_keys=True)


def step(store: Store, run_id: str, kind: str, answers: dict, text: str = "") -> dict:
    run = _run(store, run_id)
    mod = FLOWS[run["scene"]]
    a = mod.clean(store, answers if isinstance(answers, dict) else {})
    if run["scene"] == "seven_steps_lite":
        return manifest_flow.step(store, kind, a)
    if kind != "revise":
        raise ValueError("不认识的一步")
    cache = store.profile().get("flow_end") or {}
    if cache.get("run") != run_id or not cache.get("end"):
        raise ValueError("先看看方案，再说哪里不对")
    end = relearn.revise(store, a, cache["end"], text)
    store.set_profile({"flow_end": {**cache, "end": end}})      # 之后「一键调整」照这一版改
    return _public(end, store)


def _public(end: dict, store: Store | None = None) -> dict:
    out = {k: end.get(k) for k in ("say", "letter", "intro", "card", "changes", "keeps", "acts", "now")}
    if store is not None:      # 「让小光记着」这类说法用 TA 起的名字
        out["keeps"] = named(out["keeps"], agent_name(store.profile()))
    return out


def finish(store: Store, run_id: str, answers: dict) -> dict:
    run = _run(store, run_id)
    sid = run["scene"]
    mod = FLOWS[sid]
    a = mod.clean(store, answers if isinstance(answers, dict) else {})
    key = _key(a)
    cache = store.profile().get("flow_end") or {}
    # 同一次、同样的答案（比如在结尾点了上一步又原样答完）：不再调模型
    end = cache["end"] if cache.get("run") == run_id and cache.get("key") == key else mod.ending(store, a)
    store.set_profile({"flow_end": {"run": run_id, "key": key, "end": end}})
    store.update_scene(run_id, 1, [a], "done")
    if run["status"] == "open":
        store.log("scene", f"做完「{mod.TITLE}」")
    return _public(end, store)


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
