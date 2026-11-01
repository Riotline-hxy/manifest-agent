"""按时间序列渲染宠物动画帧（多进程并行调用 rive CLI），再拼成 GIF / 胶片条。

用法：
  python -I gen/render_seq.py strip <pet> <seq> <起始帧> <结束帧> <间隔>   → review/strips/<pet>-<seq>.png
  python -I gen/render_seq.py gif <pet> [fps]                              → review/gif/<pet>.gif（完整演示）
截图用 projects-preview/<pet>（带浅色背景的预览版工程，gen_pets.py 一起生成）。
"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIVE = os.path.expanduser("~/.rive/bin/rive.exe")
FONT = "C:/Windows/Fonts/msyh.ttc"

# 演示顺序：(标签, 步骤)。步骤是 ("adv", 帧数) 或 ("data", "名字=值")
DEMO = [
    ("待机", [("adv", 150)]),
    ("打招呼 · 关注", [("data", "hovered=true"), ("adv", 110)]),
    ("摸一摸", [("data", "hovered=false"), ("adv", 20), ("data", "pet=1"), ("adv", 175)]),
    ("庆祝", [("data", "celebrate=1"), ("adv", 125)]),
    ("招式", [("data", "skill=1"), ("adv", 150)]),
    ("睡觉", [("data", "sleeping=true"), ("adv", 200)]),
    ("醒来", [("data", "sleeping=false"), ("adv", 130)]),
]
SEQS = {
    "celebrate": [("adv", 30), ("data", "celebrate=1"), ("adv", 120)],
    "pet": [("adv", 30), ("data", "pet=1"), ("adv", 170)],
    "wake": [("data", "sleeping=true"), ("adv", 90), ("data", "sleeping=false"), ("adv", 120)],
    "greet": [("adv", 20), ("data", "hovered=true"), ("adv", 100)],
    "skill": [("adv", 20), ("data", "skill=1"), ("adv", 140)],
    "idle": [("adv", 480)],
}


def flatten(demo):
    steps, labels, t = [], [], 0
    for label, ss in demo:
        labels.append((t, label))
        for kind, v in ss:
            steps.append((kind, v))
            if kind == "adv":
                t += v
    return steps, labels, t


def args_at(steps, t):
    """渲染第 t 帧需要的参数：把序列走到 t 为止。"""
    out, now, started = [], 0, False
    for kind, v in steps:
        if kind == "adv":
            take = min(v, t - now)
            if take <= 0:
                break
            out.append(f"--advance={take}")
            now += take
            started = True
        else:
            if now > t:
                break
            if not started:  # 开头的 data 是初始值，第一帧前先走 1 帧让它变成步骤也行，这里直接当初始值
                out.append(f"--data={v}")
            else:
                out.append(f"--data={v}")
    if not out or not out[-1].startswith("--advance"):
        out.append("--advance=1")
    return out


def render(pet, steps, frames, outdir, workers=8):
    """每个并行进程用自己的一份工程副本（同时构建同一个工程会互相覆盖 build/ 里的文件）。"""
    import queue
    import shutil
    os.makedirs(outdir, exist_ok=True)
    src = os.path.join(ROOT, "projects-preview", pet)
    slots = queue.Queue()
    for i in range(workers):
        wd = os.path.join(ROOT, "projects-preview", f"{pet}-w{i}")
        os.makedirs(wd, exist_ok=True)
        for fn in ("scene.rml", "rive.yaml"):
            shutil.copyfile(os.path.join(src, fn), os.path.join(wd, fn))
        slots.put(wd)

    def one(t):
        path = os.path.join(outdir, f"f{t:05d}.png")
        if not os.path.exists(path):
            wd = slots.get()
            try:
                for _ in range(3):
                    r = subprocess.run([RIVE, wd, f"--screenshot={path}", "--quiet"] + args_at(steps, t),
                                       capture_output=True, text=True, encoding="utf8", errors="replace")
                    if os.path.exists(path):
                        break
                else:
                    print("failed", t, r.stderr[-300:])
            finally:
                slots.put(wd)
        return path

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, frames))


def strip(pet, seq, f0, f1, step):
    steps = SEQS[seq]
    frames = list(range(f0, f1 + 1, step))
    paths = render(pet, steps, frames, os.path.join(ROOT, "build-frames", pet, seq))
    cell = 220
    cols = min(len(paths), 8)
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (246, 243, 236))
    d = ImageDraw.Draw(sheet)
    for i, (p, f) in enumerate(zip(paths, frames)):
        im = Image.open(p).convert("RGB").resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * cell, (i // cols) * cell))
        d.text(((i % cols) * cell + 4, (i // cols) * cell + 2), str(f), fill=(120, 110, 100))
    os.makedirs(os.path.join(ROOT, "review", "strips"), exist_ok=True)
    out = os.path.join(ROOT, "review", "strips", f"{pet}-{seq}.png")
    sheet.save(out)
    print(out)


def gif(pet, fps=15, size=320, name=None, skill=None):
    demo = [(f"招式 · {skill}" if lb == "招式" else lb, ss) for lb, ss in DEMO if lb != "招式" or skill]
    steps, labels, total = flatten(demo)
    every = round(60 / fps)
    frames = list(range(0, total, every))
    paths = render(pet, steps, frames, os.path.join(ROOT, "build-frames", pet, "demo"))
    font = ImageFont.truetype(FONT, 15)
    out_frames = []
    for p, f in zip(paths, frames):
        im = Image.open(p).convert("RGB").resize((size, size), Image.LANCZOS)
        label = [lb for t, lb in labels if t <= f][-1]
        d = ImageDraw.Draw(im)
        d.text((12, size - 26), label, font=font, fill=(120, 108, 96))
        if name:
            d.text((12, 8), name, font=font, fill=(90, 80, 70))
        out_frames.append(im.quantize(colors=200, method=Image.MEDIANCUT, dither=Image.NONE))
    os.makedirs(os.path.join(ROOT, "review", "gif"), exist_ok=True)
    out = os.path.join(ROOT, "review", "gif", f"{pet}.gif")
    out_frames[0].save(out, save_all=True, append_images=out_frames[1:], duration=round(1000 / fps), loop=0, optimize=True)
    print(out, len(out_frames), "frames", os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "strip":
        strip(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]))
    elif cmd == "gif":
        import json
        spec = json.load(open(os.path.join(ROOT, "gen", "rigs.json"), encoding="utf8"))[sys.argv[2]]
        skills = {"fox": "余温", "deer": "留芳", "water": "回澜", "star": "连星"}
        gif(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 15, name=spec["name"], skill=skills.get(spec.get("route")))
