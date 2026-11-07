"""Draw the PWA icons from the favicon design (yellow 小光 ball, two eyes, a soft highlight).

Dev-only (needs Pillow); the PNGs it writes are committed, the server doesn't need Pillow.
    python tools/build_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "demo" / "public" / "icons"
BG = (15, 58, 44, 255)          # 森林夜，和 index.html 的 theme-color 一致
BALL = (247, 203, 77, 255)
EYE = (28, 28, 34, 255)
S = 1024                         # draw big, then downscale


def ball_layer(d: int, mono: bool = False) -> Image.Image:
    """The favicon (64-unit viewBox) drawn into a d×d transparent square."""
    u = d / 64
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    fill = (255, 255, 255, 255) if mono else BALL
    dr.ellipse([(32 - 26) * u, (34 - 26) * u, (32 + 26) * u, (34 + 26) * u], fill=fill)
    for cx, ang in ((25, -6), (39, 6)):
        eye = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(eye).rounded_rectangle([(cx - 3) * u, 27 * u, (cx + 3) * u, 39 * u], radius=3 * u,
                                              fill=(0, 0, 0, 255) if mono else EYE)
        eye = eye.rotate(-ang, center=(cx * u, 33 * u), resample=Image.BICUBIC)
        if mono:  # 单色角标：眼睛挖空
            im.putalpha(Image.eval(Image.composite(Image.new("L", (d, d), 0), im.getchannel("A"), eye.getchannel("A")), lambda v: v))
        else:
            im.alpha_composite(eye)
    if not mono:
        hl = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(hl).ellipse([(22 - 7) * u, (22 - 4) * u, (22 + 7) * u, (22 + 4) * u], fill=(255, 255, 255, 102))
        hl = hl.rotate(28, center=(22 * u, 22 * u), resample=Image.BICUBIC)
        im.alpha_composite(hl)
    return im


def on_bg(scale: float, rounded: bool) -> Image.Image:
    """Ball centred on the brand background. scale = ball layer size / icon size."""
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if rounded:
        ImageDraw.Draw(im).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=BG)
    else:
        im.paste(BG, [0, 0, S, S])
    d = int(S * scale)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([S / 2 - d * 0.42, S / 2 - d * 0.36, S / 2 + d * 0.42, S / 2 + d * 0.48], fill=(247, 203, 77, 70))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * 0.05)))
    b = ball_layer(d)
    im.alpha_composite(b, ((S - d) // 2, (S - d) // 2 - int(d * 0.03)))
    return im


def save(im: Image.Image, name: str, size: int, opaque: bool = False) -> None:
    out = im.resize((size, size), Image.LANCZOS)
    if opaque:
        out = out.convert("RGB")
    out.save(OUT / name, optimize=True)
    print("wrote", name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rounded = on_bg(0.86, rounded=True)       # 普通图标：圆角方块
    save(rounded, "icon-192.png", 192)
    save(rounded, "icon-512.png", 512)
    full = on_bg(0.66, rounded=False)         # 满版：安卓自适应图标的安全区内 / iOS 自己切圆角
    save(full, "maskable-512.png", 512)
    save(on_bg(0.8, rounded=False), "apple-touch-icon.png", 180, opaque=True)
    save(ball_layer(S, mono=True), "badge-96.png", 96)  # 安卓状态栏的单色小图标


if __name__ == "__main__":
    main()
