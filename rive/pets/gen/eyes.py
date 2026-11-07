"""眼睛几何：从原画里量出每只眼的真实轮廓，给眼皮、睫毛、闭眼线用。

坐标都是相对眼睛中心的原画像素（x 向右，y 向下）。
  top(x)   上轮廓（睫毛线的上沿）
  bot(x)   下轮廓
  lash     睫毛粗细（中间粗、两头细）和颜色，取自原画
"""
import numpy as np
from scipy import ndimage as ndi

N = 15  # 每条轮廓的采样点数


def _smooth(v, k=5):
    pad = np.pad(v, k // 2, mode="edge")
    return np.convolve(pad, np.ones(k) / k, mode="valid")


def eye_geometry(rgba, mask):
    """mask：整只眼（描边 + 眼白 + 虹膜）的布尔图。"""
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cols = np.arange(x0, x1 + 1)
    top = np.array([ys[xs == c].min() for c in cols], float)
    bot = np.array([ys[xs == c].max() for c in cols], float)
    top, bot = _smooth(top), _smooth(bot)
    # 两端各收一点，避免眼角尖处的噪点
    trim = max(1, int(len(cols) * 0.04))
    cols, top, bot = cols[trim:-trim], top[trim:-trim], bot[trim:-trim]
    xs_s = np.linspace(cols[0], cols[-1], N)
    top_s = np.interp(xs_s, cols, top)
    bot_s = np.interp(xs_s, cols, bot)

    # 睫毛粗细：中间一段，从上轮廓往下数连续的深色像素
    a = rgba.astype(float)
    lum = a[..., :3] @ [0.299, 0.587, 0.114]
    sat = a[..., :3].max(axis=2) - a[..., :3].min(axis=2)
    lashy = (lum < 95) & (sat < 60)
    runs, colors = [], []
    for c, t in zip(cols, top):
        if abs(c - cx) > (x1 - x0) * 0.32:
            continue
        y = int(round(t))
        n = 0
        while y + n < rgba.shape[0] and lashy[y + n, c] and n < 40:
            colors.append(a[y + n, c, :3])
            n += 1
        if n:
            runs.append(n)
    h = y1 - y0
    thick = float(np.clip(np.median(runs) if runs else h * 0.09, h * 0.06, h * 0.16))
    # 眼睛中段的宽度（不算眼角翘出去的睫毛），闭眼线按这个宽度来
    rows = [r for r in range(int(cy - h * 0.12), int(cy + h * 0.12) + 1) if (ys == r).any()]
    w_mid = float(np.median([xs[ys == r].max() - xs[ys == r].min() for r in rows])) if rows else float(x1 - x0)
    color = np.median(np.array(colors), axis=0) if colors else np.array([38, 50, 53])

    return {
        "cx": cx, "cy": cy, "a": (x1 - x0) / 2, "b": (y1 - y0) / 2, "w_mid": w_mid,
        "xs": xs_s - cx, "top": top_s - cy, "bot": bot_s - cy,
        "thick": thick, "color": "FF%02X%02X%02X" % tuple(int(v) for v in color),
    }


def crescent(xs, edge, thick, down=True, taper=0.75):
    """沿一条轮廓画一条“月牙”睫毛：中间粗、两头细。down=True 往下长粗（上睫毛），False 往上（闭眼线）。"""
    n = len(xs)
    u = np.linspace(0, 1, n)
    t = thick * (np.sin(np.pi * u) ** taper)
    t = np.maximum(t, thick * 0.18)
    other = edge + t if down else edge - t
    pts = list(zip(xs, edge)) + list(zip(xs[::-1], other[::-1]))
    return pts


def fit_arch(xs, ys):
    """把一条轮廓拟合成抛物线 y = k*x^2 + m，返回 (k, m)，用来做和眼睛弧度一致的眼皮边。"""
    k, _, m = np.polyfit(xs, ys, 2)
    return k, m


def eye_tilt(g):
    """眼睛的倾斜：上轮廓两端（眼角）连线的角度，限制在 ±0.4 弧度。"""
    dx = g["xs"][-1] - g["xs"][0]
    dy = g["top"][-1] - g["top"][0]
    return float(np.clip(np.arctan2(dy, dx), -0.4, 0.4))


def lid_rig(g, tilt, tall=None):
    """眼皮的全部尺寸（眼睛局部坐标，原画像素）。

    闭眼的过程：睫毛（按原画上轮廓做的月牙）往下走，它上面的部分盖上皮肤（裁剪成只在眼睛里），
    走到底后淡入一条“闭着的眼睛线”：∪ 是放松（摸一摸、睡觉），∩ 是开心（庆祝）。
    edge 是皮肤裁剪边相对上轮廓往下移的距离；lash 是睫毛月牙往下移的距离。
    """
    a, b, t = g["a"], g["b"], g["thick"]
    top_mid = float(np.interp(0, g["xs"], g["top"]))
    # 角度：两只眼共用脸的角度（两眼中心连线），不按各自的椭圆歪
    # 位置：竖长的大眼睛合在 58% 高度左右，偏圆的成年眼睛更靠中间
    xm = g["w_mid"] * 0.45
    tall = (b > a * 1.15) if tall is None else tall
    shut = {"xm": xm, "sag": xm * (0.22 if tall else 0.14), "oy": b * (0.15 if tall else -0.06), "t": t * 0.95}
    joy = {"xm": xm * 0.96, "arch": xm * (0.40 if tall else 0.34), "oy": b * (0.02 if tall else -0.1), "t": t * 0.95}
    d_full = float(np.max(g["bot"] - g["top"])) + 8
    lash_shut = shut["oy"] + shut["sag"] * 0.6 - top_mid - t / 2
    lash_joy = joy["oy"] - joy["arch"] * 0.4 - top_mid - t / 2
    return {
        "tilt": tilt, "shut": shut, "joy": joy, "thick": t, "top_mid": top_mid,
        "edge_open": -3.0, "edge_full": d_full,
        "lash_shut": float(lash_shut), "lash_joy": float(lash_joy),
        "cover": t * 0.85,  # 裁剪边比睫毛上沿低多少，刚好藏在睫毛下面
        "lash_c0": top_mid + t / 2,  # 睫毛月牙的中心（节点原点放这里，压扁时绕中心）
    }


def arc_line(xm, h, thick, up):
    """闭眼线：up=False 是 ∪（中间往下），up=True 是 ∩（中间往上）。返回月牙多边形的点。"""
    xs = np.linspace(-xm, xm, N)
    u = xs / xm
    if up:
        edge = -h * (1 - u ** 2)      # ∩，线的上沿
        return crescent(xs, edge, thick, down=True)
    edge = h * (1 - u ** 2)           # ∪，线的下沿
    return crescent(xs, edge, thick, down=False)
