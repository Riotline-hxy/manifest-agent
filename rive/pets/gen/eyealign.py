"""闭眼对齐检查（静态）：把生成器算出来的眼皮皮肤和闭眼线直接画到原画上，和睁眼并排。
python -I gen/eyealign.py → review/strips/eyealign.png"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eyes import arc_line  # noqa: E402
from gen_pets import make_lid_patch, prepare_eyes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rigs = json.load(open(os.path.join(ROOT, "gen", "rigs.json"), encoding="utf8"))
pets = sys.argv[1:] or [k for k in rigs if not k.startswith("_")]
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
Z = 3


def closed_face(rgba, eyes, kind):
    im = Image.fromarray(rgba).convert("RGBA")
    for e in eyes:  # 先在原尺寸上把皮肤贴上去，再放大（避免缩放带透明边产生光圈）
        X0, Y0, X1, Y1 = e["patch"]
        im.alpha_composite(Image.open(e["patch_path"]).convert("RGBA"), (X0, Y0))
    big = im.resize((im.width * Z, im.height * Z), Image.LANCZOS)
    layer = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for e in eyes:
        g, lr = e["geo"], e["lid"]
        line = lr["shut"] if kind == "shut" else lr["joy"]
        pts = arc_line(line["xm"], line["sag"] if kind == "shut" else line["arch"], line["t"], up=(kind == "joy"))
        t = lr["tilt"]
        ox, oy = -math.sin(t) * line["oy"], math.cos(t) * line["oy"]
        out = []
        for x, y in pts:
            rx, ry = x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)
            out.append(((g["cx"] + ox + rx) * Z, (g["cy"] + oy + ry) * Z))
        c = g["color"]
        d.polygon(out, fill=(int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16), 255))
    big.alpha_composite(layer)
    return big


tiles = []
for pet in pets:
    spec = rigs[pet]
    rgba = np.array(Image.open(os.path.join(ROOT, "art", f"{pet}.png")).convert("RGBA"))
    eyes = prepare_eyes(rgba, spec, symmetric=not pet.endswith("-adult"))
    for i, e in enumerate(eyes):
        e["patch_path"] = os.path.join(ROOT, "build-frames", f"_patch_{pet}_{i}.png")
        os.makedirs(os.path.dirname(e["patch_path"]), exist_ok=True)
        e["patch"] = make_lid_patch(rgba, e, e["cover"], e["patch_path"])
    xs = [v for e in eyes for v in (e["box"][0], e["box"][2])]
    ys = [v for e in eyes for v in (e["box"][1], e["box"][3])]
    pad = (max(xs) - min(xs)) * 0.18
    box = [int((min(xs) - pad) * Z), int((min(ys) - pad) * Z), int((max(xs) + pad) * Z), int((max(ys) + pad) * Z)]
    openf = Image.fromarray(rgba).convert("RGBA").resize((rgba.shape[1] * Z, rgba.shape[0] * Z), Image.LANCZOS).crop(box)
    row = [openf, closed_face(rgba, eyes, "shut").crop(box), closed_face(rgba, eyes, "joy").crop(box)]
    tiles.append((spec["name"], row))

cw = 380
rows = []
for name, row in tiles:
    hh = int(cw * row[0].height / row[0].width)
    rows.append((name, [t.resize((cw, hh), Image.LANCZOS) for t in row], hh))
H = sum(h for _, _, h in rows)
sheet = Image.new("RGB", (100 + cw * 3, H), (246, 243, 236))
d = ImageDraw.Draw(sheet)
y = 0
for name, row, hh in rows:
    d.text((6, y + 6), name, font=font, fill=(90, 80, 70))
    for c, t in enumerate(row):
        bg = Image.new("RGBA", t.size, (246, 243, 236, 255))
        bg.alpha_composite(t)
        sheet.paste(bg.convert("RGB"), (100 + c * cw, y))
    y += hh
out = os.path.join(ROOT, "review", "strips", "eyealign.png")
sheet.save(out)
print(out, sheet.size)
