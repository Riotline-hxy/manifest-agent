"""Shared helpers: time (Asia/Shanghai, no DST), ids, JSON, CJK tokenizing for FTS."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))  # Asia/Shanghai has no DST; avoids tzdata on Windows

ROOT = Path(__file__).resolve().parent.parent          # demo/
DATA = Path(os.environ.get("MANIFEST_DATA") or (ROOT / "data")).resolve()
PUBLIC = ROOT / "public"


def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def day_key(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y-%m-%d")


def hours_since(s: str | None, ref: datetime | None = None) -> float | None:
    dt = parse_iso(s)
    if dt is None:
        return None
    return ((ref or now()) - dt).total_seconds() / 3600


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def load_dotenv(path: Path) -> None:
    """Minimal KEY=VALUE loader for local dev; never overrides real env."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


# ---- tokenizing for SQLite FTS5 -------------------------------------------
# Chinese has no spaces, so text is indexed as overlapping character bigrams
# plus lowercase latin words. Queries use the same function, which lets a
# two-character query like 「自信」 match 「更自信地表达」.
_CJK = re.compile(r"[㐀-鿿]+")
_WORD = re.compile(r"[a-z0-9]+")
STOP = set("的了是我你他她它们在和就也都很还要会这那有个吗呢吧啊哦嗯".replace("", " ").split())


def tokens(text: str) -> list[str]:
    text = (text or "").lower()
    out: list[str] = []
    for run in _CJK.findall(text):
        if len(run) == 1:
            if run not in STOP:
                out.append(run)
            continue
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
    out.extend(w for w in _WORD.findall(text) if len(w) > 1)
    return out


def fts_doc(text: str) -> str:
    return " ".join(tokens(text))


def fts_query(text: str, limit: int = 24) -> str | None:
    seen: list[str] = []
    for t in tokens(text):
        if t not in seen and not all(ch in STOP for ch in t):
            seen.append(t)
    if not seen:
        return None
    return " OR ".join('"%s"' % t.replace('"', "") for t in seen[:limit])


def clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"
