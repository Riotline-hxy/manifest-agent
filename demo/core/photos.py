"""瞬间的照片：每个瞬间最多一张，只有本人能看。

手机上先用 canvas 压好两份（大图长边 1600、小图长边 480，WebP 或 JPEG），base64 传上来；
这里只认真正的图片（看文件头），存在 DATA/u/<uid>/photos/<pid>.<ext> 和 <pid>_s.<ext>。
照片只会新增或删除，不会原地改；没挂到瞬间上的照片 24 小时后清掉。小光现在的模型看不到图。
"""
from __future__ import annotations

import base64
import re
import secrets
import time

PID_RE = re.compile(r"^ph_[0-9a-f]{12}$")
MAX_FULL = 3 * 1024 * 1024
MAX_THUMB = 400 * 1024
MAX_PER_USER = 600
ORPHAN_HOURS = 24
MIME = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}


def _dir(st):
    d = st.dir / "photos"
    d.mkdir(exist_ok=True)
    return d


def _kind(raw: bytes) -> str | None:
    """真正的图片格式（看文件头，不信文件名和前端说的类型）。"""
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return None


def _decode(data, limit: int, what: str) -> bytes:
    s = str(data or "")
    if s.startswith("data:"):
        s = s.split(",", 1)[-1]
    try:
        raw = base64.b64decode(s, validate=True)
    except (ValueError, TypeError):
        raise ValueError(f"{what}读不出来，换一张试试")
    if not raw:
        raise ValueError(f"没收到{what}")
    if len(raw) > limit:
        raise ValueError(f"{what}太大了，换一张小一点的")
    return raw


def files(st, pid: str) -> list:
    if not PID_RE.match(pid or ""):
        return []
    d = st.dir / "photos"
    return sorted(d.glob(pid + ".*")) + sorted(d.glob(pid + "_s.*")) if d.is_dir() else []


def exists(st, pid: str) -> bool:
    return bool(files(st, pid))


def path(st, pid: str, small: bool = False):
    """照片文件的路径；id 不对或者不存在返回 None。"""
    if not PID_RE.match(pid or ""):
        return None
    d = st.dir / "photos"
    for f in (d.glob(pid + ("_s.*" if small else ".*")) if d.is_dir() else []):
        if small or not f.stem.endswith("_s"):
            return f
    return None


def save(st, data, thumb) -> str:
    full = _decode(data, MAX_FULL, "照片")
    small = _decode(thumb, MAX_THUMB, "缩略图")
    kf, ks = _kind(full), _kind(small)
    if not kf or not ks:
        raise ValueError("只能放 JPG、PNG 或 WebP 照片")
    d = _dir(st)
    clean_orphans(st)
    if len([f for f in d.iterdir() if not f.stem.endswith("_s")]) >= MAX_PER_USER:
        raise ValueError(f"照片已经有 {MAX_PER_USER} 张了，先删掉一些旧的吧")
    pid = "ph_" + secrets.token_hex(6)
    (d / f"{pid}.{kf}").write_bytes(full)
    (d / f"{pid}_s.{ks}").write_bytes(small)
    return pid


def delete(st, pid: str) -> None:
    for f in files(st, pid):
        try:
            f.unlink()
        except OSError:
            pass


def clean_orphans(st) -> int:
    """传上来却没挂到任何瞬间上的照片：放了 24 小时还没用，就删掉。"""
    d = st.dir / "photos"
    if not d.is_dir():
        return 0
    used = {r[0] for r in st.c.execute("SELECT photo FROM moment WHERE photo != ''")}
    cutoff = time.time() - ORPHAN_HOURS * 3600
    n = 0
    for f in list(d.iterdir()):
        pid = f.stem[:-2] if f.stem.endswith("_s") else f.stem
        if pid not in used and f.stat().st_mtime < cutoff:
            try:
                f.unlink(); n += 1
            except OSError:
                pass
    return n
