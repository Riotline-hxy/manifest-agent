"""脸部特写胶片条：检查眼皮开合。python -I gen/closeup.py <pet> <序列名> <起始帧> <结束帧> <间隔>
序列名见 render_seq.SEQS。输出 review/strips/<pet>-<序列>-face.png"""
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_seq import SEQS, render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEQS.update({
    "pet-eyes": [("adv", 20), ("data", "pet=1"), ("adv", 200)],
    "doze": [("adv", 20), ("data", "sleeping=true"), ("adv", 260)],
    "wake-eyes": [("data", "sleeping=true"), ("adv", 300), ("data", "sleeping=false"), ("adv", 160)],
    "joy": [("adv", 20), ("data", "celebrate=1"), ("adv", 180)],
    "blink": [("adv", 300)],
})

pet, seq, f0, f1, step = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
spec = json.load(open(os.path.join(ROOT, "gen", "rigs.json"), encoding="utf8"))[pet]
img = Image.open(os.path.join(ROOT, "art", f"{pet}.png"))
w, h = img.size
s = min(430 / w, 380 / h)
cx, cy = 250, 452 - s * (spec["ground"][1] - h / 2)
W = lambda p: (cx + s * (p[0] - w / 2), cy + s * (p[1] - h / 2))
xs = [W(p)[0] for p in spec["head"]]
ys = [W(p)[1] for p in spec["head"]]
fx0, fx1 = min(xs), max(xs)
crown, neck = W(spec["crown"]), W(spec["neck"])
mid_y = (crown[1] + neck[1]) / 2
half = (fx1 - fx0) * 0.42
box = (int((fx0 + fx1) / 2 - half), int(mid_y - half * 0.62), int((fx0 + fx1) / 2 + half), int(mid_y + half * 0.62))

frames = list(range(f0, f1 + 1, step))
paths = render(pet, SEQS[seq], frames, os.path.join(ROOT, "build-frames", pet, seq))
cw = 300
chh = int(cw * (box[3] - box[1]) / (box[2] - box[0]))
cols = 6
rows = (len(paths) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cw, rows * chh), (246, 243, 236))
d = ImageDraw.Draw(sheet)
for i, (p, f) in enumerate(zip(paths, frames)):
    im = Image.open(p).convert("RGB").crop(box).resize((cw, chh), Image.LANCZOS)
    sheet.paste(im, ((i % cols) * cw, (i // cols) * chh))
    d.text(((i % cols) * cw + 4, (i // cols) * chh + 2), str(f), fill=(150, 60, 60))
out = os.path.join(ROOT, "review", "strips", f"{pet}-{seq}-face.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
sheet.save(out)
print(out)
