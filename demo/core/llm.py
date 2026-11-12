"""OpenAI-compatible chat client with streaming + tool calls. Two providers: DeepSeek official and the ModelFlare relay.

Which provider / model / thinking level is used: config/llm.json is the default; the admin page can switch it at runtime
(saved in DATA/llm_choice.json, so a redeploy keeps it). Thinking levels are written once as none / low / medium / high
and translated per provider (PROVIDERS[...]["effort"]); None means "leave it out of the request".

Never leave the user without a reply: if a request fails with thinking on (DeepSeek's thinking mode currently 500s with tools,
and refuses a forced tool_choice), it is retried once with thinking off; a forced tool_choice the model refuses becomes "auto".

stream_chat() yields events:
  ("text", str)                      a content delta
  ("tool_calls", [ {id,name,arguments} ])   accumulated at end of a turn
  ("done", {"finish_reason":..., "usage":...})
Raises LLMError on HTTP / network failure.
"""
from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import metrics
from .util import DATA, ROOT, iso

CONFIG_PATH = ROOT.parent / "config" / "llm.json"
CHOICE_PATH = DATA / "llm_choice.json"     # 后台切换的模型（覆盖 config/llm.json）

EFFORTS = ["none", "low", "medium", "high"]          # 后台给的四档：不思考 / 低 / 中 / 高
EFFORT_LABEL = {"none": "不思考", "low": "低", "medium": "中", "high": "高"}
PROVIDERS = {
    "deepseek": {"name": "DeepSeek 官方", "baseUrl": "https://api.deepseek.com", "keyEnv": "DEEPSEEK_API_KEY",
                 "effort": {"none": "none", "low": "low", "medium": "high", "high": "max"},
                 "models": [["deepseek-flash", "DeepSeek V4.1 Flash"], ["deepseek-v4-pro", "DeepSeek V4 Pro"]],
                 "note": "官方接口偶尔会报 500（2026-11-07 实测，开不开思考都有），出错会自动重试、再退回不思考，回复不会断。"},
    "modelflare": {"name": "ModelFlare 中转", "baseUrl": "https://modelflare.dev/v1", "keyEnv": "MODELFLARE_API_KEY",
                   "effort": {"none": None, "low": "low", "medium": "medium", "high": "high"},
                   "models": [["gpt-6.1-sol", "gpt-6.1-sol"], ["claude-sonnet-5-5", "claude-sonnet-5-5"], ["kimi-k3", "kimi-k3"],
                              ["glm-5.3", "glm-5.3"], ["deepseek-v4.1-flash", "deepseek-v4.1-flash"], ["qwen3.8-max", "qwen3.8-max"]],
                   "note": "中转站每次调用会多算约 2.7 万 token；「不思考」时不传思考参数，用模型自己的默认。"},
}
_choice_cache: dict = {"mtime": None, "value": None}
FALLBACKS = [0]      # 这个进程里退回不思考 / 改 auto 的次数（后台「试一下」用来判断是不是靠退回才成功的）


def choice() -> dict | None:
    """后台选的 {provider, model, effort, at}；没有就是 None（用 config/llm.json）。"""
    try:
        m = CHOICE_PATH.stat().st_mtime
    except OSError:
        return None
    if _choice_cache["mtime"] != m:
        try:
            v = json.loads(CHOICE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            v = None
        _choice_cache.update(mtime=m, value=v if isinstance(v, dict) and v.get("provider") in PROVIDERS else None)
    return _choice_cache["value"]


def save_choice(provider: str, model: str, effort: str) -> dict:
    v = {"provider": provider, "model": model, "effort": effort, "at": iso()}
    CHOICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHOICE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CHOICE_PATH)
    return v


class LLMError(Exception):
    pass


def _provider_of(cfg: dict) -> str:
    if cfg.get("provider") in PROVIDERS:
        return cfg["provider"]
    return "deepseek" if "deepseek.com" in (cfg.get("baseUrl") or "") else "modelflare"


def config(override: dict | None = None) -> dict:
    """生效的配置：config/llm.json ← 环境变量 ← 后台的选择（override 给「先试一下再切换」用）。
    reasoning 是统一的四档之一（none / low / medium / high）。"""
    cfg = {"baseUrl": "https://modelflare.dev/v1", "model": "gpt-6.1-sol", "reasoning": "low",
           "apiKeyEnv": "MODELFLARE_API_KEY", "timeout": 60}
    try:
        cfg.update(json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    cfg["baseUrl"] = os.environ.get("MODELFLARE_BASE_URL") or cfg["baseUrl"]
    cfg["model"] = os.environ.get("MODELFLARE_MODEL") or cfg["model"]
    cfg["reasoning"] = os.environ.get("MODELFLARE_REASONING") or cfg["reasoning"]
    ch = override or choice()
    if ch and ch.get("provider") in PROVIDERS:
        p = PROVIDERS[ch["provider"]]
        cfg.update(provider=ch["provider"], baseUrl=p["baseUrl"], apiKeyEnv=p["keyEnv"],
                   model=ch.get("model") or cfg["model"], reasoning=ch.get("effort") or "none")
    cfg["provider"] = _provider_of(cfg)
    if cfg["reasoning"] not in EFFORTS:            # 老配置里可能写着 minimal 之类
        cfg["reasoning"] = "none" if cfg["reasoning"] in ("", "minimal", "off") else "low"
    return cfg


def api_key(cfg: dict | None = None) -> str | None:
    cfg = cfg or config()
    return os.environ.get(cfg.get("apiKeyEnv") or "MODELFLARE_API_KEY")


def _effort_value(cfg: dict, effort: str | None):
    """统一的四档 → 这个服务商认的值；None = 请求里不带这个参数。"""
    e = effort if effort in EFFORTS else cfg.get("reasoning", "none")
    return PROVIDERS[cfg["provider"]]["effort"].get(e)


def _thinking_off(cfg: dict, body: dict) -> dict:
    b = {k: v for k, v in body.items() if k != "reasoning_effort"}
    off = PROVIDERS[cfg["provider"]]["effort"]["none"]
    if off is not None:
        b["reasoning_effort"] = off
    return b


def _open(cfg: dict, body: dict, stream: bool, timeout: float):
    key = api_key(cfg)
    if not key:
        raise LLMError("no api key")
    req = urllib.request.Request(
        cfg["baseUrl"].rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "text/event-stream" if stream else "application/json"},
        method="POST",
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise LLMError(f"HTTP {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"network: {e}") from None


def _request(body: dict, stream: bool, timeout: float, cfg: dict | None = None):
    """发请求；出错时按顺序换一种更稳的写法再试（最多三次），保证有回复：
    1) 原样；2) 思考打开着 → 关掉思考；3) 强制工具被拒 → 改成 auto。401 / 403 / 429 这类不重试。"""
    cfg = cfg or config()
    tries, b = [], dict(body)
    tries.append(b)
    thinking = b.get("reasoning_effort") not in (None, PROVIDERS[cfg["provider"]]["effort"]["none"])
    if thinking:
        b = _thinking_off(cfg, b)
        tries.append(b)
    if isinstance(b.get("tool_choice"), dict):
        tries.append({**b, "tool_choice": "auto"})
    last, retried = None, False
    i = 0
    while i < len(tries):
        t = tries[i]
        try:
            resp = _open(cfg, t, stream, timeout if i == 0 or not thinking else min(timeout, 40))
            if i:
                metrics.bump("llm_fallback")
                FALLBACKS[0] += 1
            return resp
        except LLMError as e:
            last = e
            msg = str(e)
            if msg.startswith(("HTTP 401", "HTTP 403", "HTTP 429", "no api key")):
                break
            # 服务商偶尔 500 / 断线（DeepSeek 2026-11-07 不论开不开思考都会间歇 500）：同一个请求马上再试一次
            if not retried and (msg.startswith(("HTTP 5", "network")) or "timed out" in msg):
                retried = True
                time.sleep(0.6)
                continue
            i += 1
    metrics.bump("llm_err")
    raise last


def _note_usage(usage, kind: str) -> None:
    """kind: chat（对话里的流式调用）| bg（记忆整理、主动消息、体验等一次性调用）。
    全站计数 + 当前用户的计数（没有当前用户时，比如首页体验，只记全站）。"""
    uid = metrics.current_user()
    u = usage if isinstance(usage, dict) else {}
    nums = {"llm_calls": 1, "llm_tokens": int(u.get("total_tokens") or 0), "llm_tokens_in": int(u.get("prompt_tokens") or 0),
            "llm_tokens_out": int(u.get("completion_tokens") or 0),
            "llm_tokens_cached": int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)}
    nums[f"llm_tokens_{kind}"] = nums["llm_tokens"]
    for k, n in nums.items():
        metrics.bump(k, n)
        if uid:
            metrics.bump_user(uid, k, n)


def _body(messages, tools=None, model=None, reasoning=None, stream=True, temperature=None, json_mode=False, tool_choice=None, cfg=None):
    cfg = cfg or config()
    body = {"model": model or cfg["model"], "messages": messages, "stream": stream}
    r = _effort_value(cfg, reasoning)
    if r is not None:
        body["reasoning_effort"] = r
    if tools:
        body["tools"] = tools
        body["tool_choice"] = {"type": "function", "function": {"name": tool_choice}} if tool_choice else "auto"
    if temperature is not None:
        body["temperature"] = temperature
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


def _lines(resp):
    """逐行读流；读到一半连接断了 / 超时，统一变成 LLMError（调用方据此保存已经收到的部分）。"""
    try:
        yield from resp
    except (OSError, TimeoutError, http.client.HTTPException) as e:
        metrics.bump("llm_err")
        raise LLMError(f"stream interrupted: {type(e).__name__}") from None


def stream_chat(messages, tools=None, model=None, reasoning=None, timeout=None, tool_choice=None, cfg=None):
    """tool_choice：工具名，要求这一轮必须先调它（router 判断 TA 明确要做这件事时用）。
    reasoning：none / low / medium / high；不传就用当前配置。cfg：临时用另一套配置（后台「试一下」）。"""
    cfg = cfg or config()
    resp = _request(_body(messages, tools, model, reasoning, True, tool_choice=tool_choice, cfg=cfg), True,
                    timeout or cfg.get("timeout", 60), cfg)
    calls: dict[int, dict] = {}
    finish, usage = None, None
    with resp:
        for raw in _lines(resp):
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            usage = chunk.get("usage") or usage
            for ch in chunk.get("choices") or []:
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    yield ("text", delta["content"])
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
    _note_usage(usage, "chat")
    if calls:
        yield ("tool_calls", [calls[i] for i in sorted(calls)])
    yield ("done", {"finish_reason": finish, "usage": usage})


def complete_json(messages, model=None, timeout=40, reasoning=None) -> dict | None:
    """Non-streaming call that must return a JSON object. Used by the memory
    write pipeline and proactive-copy generation. Returns None on failure.
    reasoning=None 跟着后台选的思考档；用户在等结果的地方（路由、两分钟启动、体验、练习结束页）传 "none"，保证快。"""
    try:
        resp = _request(_body(messages, model=model, reasoning=reasoning, stream=False, json_mode=True), False, timeout)
        with resp:
            d = json.loads(resp.read())
        _note_usage(d.get("usage"), "bg")
        text = d["choices"][0]["message"].get("content") or ""
    except (LLMError, KeyError, IndexError, ValueError):
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        out = json.loads(text[text.find("{"): text.rfind("}") + 1])
        return out if isinstance(out, dict) else None
    except ValueError:
        return None


def ping(timeout=15) -> dict:
    t0 = time.time()
    try:
        first = None
        for kind, _ in stream_chat([{"role": "user", "content": "回复：在"}], timeout=timeout):
            if kind == "text" and first is None:
                first = time.time() - t0
        return {"ok": True, "first_token_s": round(first or 0, 2), "total_s": round(time.time() - t0, 2)}
    except LLMError as e:
        return {"ok": False, "error": str(e)[:160]}


TRY_TOOL = [{"type": "function", "function": {"name": "propose_moment", "description": "提议把刚说的一件事留成一个瞬间",
             "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]


def try_settings(provider: str, model: str, effort: str, timeout: float = 60) -> dict:
    """后台切换前先试一下：用这套设置走一遍真实的「带工具的流式对话」。
    返回 ok、首字秒数，以及是不是靠退回不思考才成功的（fell_back）。"""
    cfg = config({"provider": provider, "model": model, "effort": effort})
    before = FALLBACKS[0]
    t0, first, called = time.time(), None, []
    try:
        for kind, val in stream_chat([{"role": "user", "content": "今天抢到了最后一份糖醋排骨！"}], tools=TRY_TOOL,
                                     timeout=timeout, cfg=cfg):
            if kind in ("text", "tool_calls") and first is None:
                first = time.time() - t0
            if kind == "tool_calls":
                called = [c["name"] for c in val]
    except LLMError as e:
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True, "first_s": round(first or 0, 2), "total_s": round(time.time() - t0, 2), "tool_called": bool(called),
            "fell_back": FALLBACKS[0] > before}
