"""OpenAI-compatible chat client (ModelFlare relay) with streaming + tool calls.

stream_chat() yields events:
  ("text", str)                      a content delta
  ("tool_calls", [ {id,name,arguments} ])   accumulated at end of a turn
  ("done", {"finish_reason":..., "usage":...})
Raises LLMError on HTTP / network failure.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .util import ROOT

CONFIG_PATH = ROOT.parent / "config" / "llm.json"


class LLMError(Exception):
    pass


def config() -> dict:
    cfg = {"baseUrl": "https://modelflare.dev/v1", "model": "gpt-6.1-sol", "reasoning": "low",
           "apiKeyEnv": "MODELFLARE_API_KEY", "timeout": 60}
    try:
        cfg.update(json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    cfg["baseUrl"] = os.environ.get("MODELFLARE_BASE_URL") or cfg["baseUrl"]
    cfg["model"] = os.environ.get("MODELFLARE_MODEL") or cfg["model"]
    cfg["reasoning"] = os.environ.get("MODELFLARE_REASONING") or cfg["reasoning"]
    return cfg


def api_key() -> str | None:
    cfg = config()
    return os.environ.get(cfg.get("apiKeyEnv") or "MODELFLARE_API_KEY") or os.environ.get("MODELFLARE_API_KEY")


def _request(body: dict, stream: bool, timeout: float):
    cfg = config()
    key = api_key()
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


def _body(messages, tools=None, model=None, reasoning=None, stream=True, temperature=None, json_mode=False):
    cfg = config()
    body = {"model": model or cfg["model"], "messages": messages, "stream": stream}
    r = reasoning if reasoning is not None else cfg.get("reasoning")
    if r:
        body["reasoning_effort"] = r
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if temperature is not None:
        body["temperature"] = temperature
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


def stream_chat(messages, tools=None, model=None, reasoning=None, timeout=None):
    cfg = config()
    resp = _request(_body(messages, tools, model, reasoning, True), True, timeout or cfg.get("timeout", 60))
    calls: dict[int, dict] = {}
    finish, usage = None, None
    with resp:
        for raw in resp:
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
    if calls:
        yield ("tool_calls", [calls[i] for i in sorted(calls)])
    yield ("done", {"finish_reason": finish, "usage": usage})


def complete_json(messages, model=None, timeout=40) -> dict | None:
    """Non-streaming call that must return a JSON object. Used by the memory
    write pipeline and proactive-copy generation. Returns None on failure."""
    try:
        resp = _request(_body(messages, model=model, reasoning="low", stream=False, json_mode=True), False, timeout)
        with resp:
            d = json.loads(resp.read())
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
