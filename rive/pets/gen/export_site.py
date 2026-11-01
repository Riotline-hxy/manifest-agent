"""把宠物发布到网站：python -I gen/export_site.py
  - .riv → demo/public/pets/<id>.riv（成长页的实时动画）
  - Rive 网页运行时 → demo/public/vendor/rive/
  - 静态图 → demo/public/pets/img/<id>.webp 和 <id>-sleep.webp（其他地方显示宠物用；睡着那张的眼皮和闭眼线和动画同一套）
"""
import json
import math
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eyes import arc_line  # noqa: E402
from gen_pets import ART, make_lid_patch, prepare_eyes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.abspath(os.path.join(ROOT, "..", "..", "demo", "public"))
MAX = 360  # 静态图最长边


def sleep_still(rgba, eyes, Z=4):
    """原画 + 眼皮皮肤 + 放松的闭眼线（∪）。先在原尺寸贴皮肤，放大后再画线，最后缩回去。"""
    im = Image.fromarray(rgba).convert("RGBA")
    tmp = os.path.join(ROOT, "projects-preview", "_lid.png")
    for e in eyes:
        X0, Y0, X1, Y1 = make_lid_patch(rgba, e, e["cover"], tmp)
        im.alpha_composite(Image.open(tmp).convert("RGBA"), (X0, Y0))
    os.remove(tmp)
    big = im.resize((im.width * Z, im.height * Z), Image.LANCZOS)
    layer = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for e in eyes:
        g, L = e["geo"], e["lid"]
        line = L["shut"]
        t = L["tilt"]
        ox, oy = -math.sin(t) * line["oy"], math.cos(t) * line["oy"]
        pts = []
        for x, y in arc_line(line["xm"], line["sag"], line["t"], up=False):
            rx, ry = x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)
            pts.append(((g["cx"] + ox + rx) * Z, (g["cy"] + oy + ry) * Z))
        c = g["color"]
        d.polygon(pts, fill=(int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16), 255))
    big.alpha_composite(layer)
    return big.resize(im.size, Image.LANCZOS)


def save_small(im, path):
    k = MAX / max(im.size)
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    im.save(path, "WEBP", quality=88, method=6)


def main():
    rigs = json.load(open(os.path.join(ROOT, "gen", "rigs.json"), encoding="utf8"))
    pets = [k for k in rigs if not k.startswith("_")]
    os.makedirs(os.path.join(SITE, "pets", "img"), exist_ok=True)
    os.makedirs(os.path.join(SITE, "vendor", "rive"), exist_ok=True)
    for f in ("rive.js", "rive.wasm", "rive_fallback.wasm"):
        shutil.copyfile(os.path.join(ROOT, "review", "vendor", f), os.path.join(SITE, "vendor", "rive", f))
    for pet in pets:
        shutil.copyfile(os.path.join(ROOT, "projects", pet, "build", f"{pet}.riv"), os.path.join(SITE, "pets", f"{pet}.riv"))
        rgba = np.array(Image.open(os.path.join(ART, f"{pet}.png")).convert("RGBA"))
        eyes = prepare_eyes(rgba, rigs[pet], symmetric=not pet.endswith("-adult"))
        save_small(Image.fromarray(rgba), os.path.join(SITE, "pets", "img", f"{pet}.webp"))
        save_small(sleep_still(rgba, eyes), os.path.join(SITE, "pets", "img", f"{pet}-sleep.webp"))
        print(pet, "ok")
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(os.path.join(SITE, "pets")) for f in fs)
    print("site/pets", total // 1024, "KB")


if __name__ == "__main__":
    main()
