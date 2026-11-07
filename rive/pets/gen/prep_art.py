"""把概念图整理成 Rive 用的贴图：去白底（只去和边缘连通的白色）、裁边、缩放。
用法：python -I prep_art.py <源目录> <输出目录>
"""
import sys
from collections import deque
import numpy as np
from PIL import Image, ImageFilter

SRC, OUT = sys.argv[1], sys.argv[2]
PETS = {  # 输出名: 源文件
    "baby": "baby.png", "sprout": "sprout.png",
    "fox-young": "fox-young.png", "fox-adult": "fox-adult.png",
    "deer-young": "deer-young.png", "deer-adult": "deer-adult.png",
    "water-young": "water-young.png", "water-adult": "water-adult-v2.png",
    "star-young": "star-young.png", "star-adult": "star-adult.png",
}
MAX_SIDE = 720  # 贴图最长边（在 app 里宠物最大约 320pt 显示，2x 屏够用）


def remove_white_bg(rgb):
    """从图片边缘开始泛洪，把和边缘连通的近白色当背景；边缘半透明像素按“白色转透明”还原。"""
    h, w, _ = rgb.shape
    mn = rgb.min(axis=2).astype(np.int16)
    mx = rgb.max(axis=2).astype(np.int16)
    whiteish = (mn > 228) & (mx - mn < 22)
    bg = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if whiteish[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if whiteish[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not bg[ny, nx] and whiteish[ny, nx]:
                bg[ny, nx] = True; q.append((ny, nx))
    alpha = np.where(bg, 0.0, 1.0)
    # 紧贴背景的 3px 边：按离白色的距离给 alpha，并去掉混进去的白色
    edge = np.array(Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))) > 0
    edge &= ~bg
    f = rgb.astype(np.float64)
    a_est = np.clip((255.0 - f.min(axis=2)) / 255.0 * 1.6, 0, 1)
    alpha = np.where(edge, np.maximum(a_est, 0.0), alpha)
    out = f.copy()
    safe = np.maximum(alpha, 1e-3)[..., None]
    unblend = np.clip((f - (1 - alpha[..., None]) * 255.0) / safe, 0, 255)
    out = np.where(edge[..., None], unblend, out)
    return np.dstack([out, alpha * 255]).astype(np.uint8)


for name, src in PETS.items():
    im = Image.open(f"{SRC}/{src}")
    if im.mode != "RGBA":
        rgba = Image.fromarray(remove_white_bg(np.array(im.convert("RGB"))), "RGBA")
    else:
        rgba = im
    a = np.array(rgba)[..., 3]
    ys, xs = np.where(a > 6)
    pad = 12
    box = (max(xs.min() - pad, 0), max(ys.min() - pad, 0), min(xs.max() + pad + 1, rgba.width), min(ys.max() + pad + 1, rgba.height))
    rgba = rgba.crop(box)
    k = MAX_SIDE / max(rgba.size)
    if k < 1:
        rgba = rgba.resize((round(rgba.width * k), round(rgba.height * k)), Image.LANCZOS)
    rgba.save(f"{OUT}/{name}.png", optimize=True)
    print(name, rgba.size)
