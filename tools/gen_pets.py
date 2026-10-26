"""Generate the pet evolution art with the openlux image endpoint.

Run from the repo root:  python tools/gen_pets.py
Writes PNGs into demo/public/assets/pets/. Idempotent: skips files that exist
unless --force is passed. The key comes from OPENLUX_API_KEY (never committed).
"""
import base64
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.openlux.ai/v1"
KEY = os.environ.get("OPENLUX_API_KEY", "")
OUT = pathlib.Path(__file__).resolve().parent.parent / "demo" / "public" / "assets" / "pets"

STYLE = ("soft gouache children's book illustration, muted palette of warm cream paper, "
         "jade green, ink black and lantern gold, fine paper grain, gentle light, "
         "one single creature centered, generous empty margin, no text, no letters, "
         "no watermark, no frame, storybook cover art")

PETS = [
    ("stage0", "一颗刚刚发芽的种子，蜷成小球，外壳半透明像细胞，里面有一点暖金色的光"),
    ("stage1", "一只小小的墨绿色蝌蚪精灵，身体半透明，尾巴拖着星尘，头顶有一粒金色光点"),
    ("stage2", "一只掌心大小的雏龟，背甲像湿润的青玉，甲上长着一小片苔藓和两片嫩芽，眼神好奇"),
    ("qinglong_juvenile", "一条幼年青龙，身体修长如溪水，鳞片是青玉色，角还是软软的芽，盘成一团"),
    ("qinglong_adult", "一条东方青龙，鳞甲青玉，鬃毛如云，身周有细雨与云气，庄严而温和"),
    ("jiuwei_juvenile", "一只幼年九尾狐，三条尾巴，毛色是暖白与杏金，眼睛明亮，坐在石头上"),
    ("jiuwei_adult", "一只成年九尾狐，九条尾巴如火焰与晚霞散开，额间一点朱砂，优雅神秘"),
    ("baize_juvenile", "一只幼年白泽，像小鹿与麒麟的混合，白色绒毛，额上有一只小角，身边漂浮着发光的符号"),
    ("baize_adult", "一只成年白泽，通体雪白，额生玉角，脚踏云雾，身旁漂浮着古老的光纹，智慧而宁静"),
]

COVERS = [
    ("report-cover", "黎明时分的层叠山峦与薄雾，山脊上有一粒微小的暖金色光点正在升起，极简，大量留白，纵向构图"),
    ("garden", "一片很小的手绘森林，六七棵不同高度的树，嫩绿与墨绿，晨光，横向构图，大量留白"),
]


def gen(name: str, subject: str, size="1024x1024", tries=3) -> bool:
    dest = OUT / f"{name}.png"
    if dest.exists() and "--force" not in sys.argv:
        print("skip", name)
        return True
    body = {"model": "gpt-image-2", "prompt": f"{subject}. {STYLE}", "n": 1, "size": size}
    req = urllib.request.Request(
        BASE + "/images/generations",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            item = d["data"][0]
            raw = base64.b64decode(item["b64_json"]) if item.get("b64_json") else None
            if raw is None and item.get("url"):
                with urllib.request.urlopen(item["url"], timeout=120) as rr:
                    raw = rr.read()
            if not raw:
                raise ValueError("no image in response")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            print("ok", name, len(raw) // 1024, "KB")
            return True
        except Exception as e:  # noqa: BLE001 - one bad image must not stop the batch
            print("retry", name, attempt + 1, type(e).__name__, str(e)[:160])
            time.sleep(4 * (attempt + 1))
    print("FAILED", name)
    return False


def main() -> int:
    if not KEY:
        print("OPENLUX_API_KEY missing")
        return 2
    ok = True
    for name, subject in PETS:
        ok &= gen(name, subject)
    for name, subject in COVERS:
        ok &= gen(name, subject, size="1024x1536")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
