"""生成 RML 用的小工具：数字格式、2D 矩阵、关键帧动画、正弦摆动。"""
import math

import numpy as np


def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ── 2D 仿射矩阵（和 Rive 的 Mat2D 一样：xx, xy, yx, yy, tx, ty）────────
def mat(angle, tx, ty):
    c, s = math.cos(angle), math.sin(angle)
    return (c, s, -s, c, tx, ty)


def mul(a, b):
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def inv(m):
    det = m[0] * m[3] - m[1] * m[2]
    a, b, c, d = m[3] / det, -m[1] / det, -m[2] / det, m[0] / det
    return (a, b, c, d, -(a * m[4] + c * m[5]), -(b * m[4] + d * m[5]))


def app(m, p):
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def ang(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ── 动画 ────────────────────────────────────────────────────────────
EASES = {
    "io": (0.42, 0, 0.58, 1), "sio": (0.37, 0, 0.63, 1),
    "sout": (0.61, 1, 0.88, 1), "sin": (0.12, 0, 0.39, 0),
    "out": (0.22, 1, 0.36, 1), "outs": (0.33, 1, 0.68, 1),
    "in": (0.55, 0.055, 0.675, 0.19), "ins": (0.32, 0, 0.67, 0),
}


class Anim:
    def __init__(self, name, dur, loop="oneShot"):
        self.name, self.dur, self.loop, self.tracks = name, dur, loop, {}

    def key(self, obj, prop, keys, ease="io"):
        by_frame = {}
        for k in keys:  # 同一帧只留最后一个，按帧排序
            f = min(max(int(round(k[0])), 0), self.dur)
            by_frame[f] = (f, k[1], k[2] if len(k) > 2 else ease)
        self.tracks.setdefault(obj, {})[prop] = [by_frame[f] for f in sorted(by_frame)]
        return self

    def rml(self, ids):
        body = []
        for obj, props in self.tracks.items():
            kp = []
            for prop, keys in props.items():
                kf = []
                for f, v, e in keys:
                    if e in ("linear", "hold"):
                        kf.append(f'<KeyFrameDouble frame="{f}" value="{fmt(v)}" interpolationType="{e}"/>')
                    else:
                        x1, y1, x2, y2 = EASES[e]
                        kf.append(f'<KeyFrameDouble frame="{f}" value="{fmt(v)}" interpolationType="cubic">'
                                  f'<CubicEaseInterpolator x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/></KeyFrameDouble>')
                kp.append(f'<KeyedProperty property="{prop}">{"".join(kf)}</KeyedProperty>')
            body.append(f'<KeyedObject objectId="{ids[obj]}">{"".join(kp)}</KeyedObject>')
        return (f'<LinearAnimation loopValue="{self.loop}" fps="60" duration="{self.dur}" name="{self.name}" '
                f'id="{ids["anim:" + self.name]}">{"".join(body)}</LinearAnimation>')


def wave(base, amp, period, lag, start, end, env=None):
    """正弦摆动 base + amp*sin(2π(t-lag)/period)，只在峰值和过零点打关键帧，
    中间用正弦缓动，所以曲线和真正的正弦一致。period 要能被 4 整除。env(t) 是振幅包络。"""
    q = period // 4

    def val(t):
        return base + amp * (env(t) if env else 1) * math.sin(2 * math.pi * (t - lag) / period)

    times = [start]
    k = math.ceil((start - lag) / q)
    while lag + k * q < end:
        if lag + k * q > start:
            times.append(lag + k * q)
        k += 1
    times.append(end)
    keys = []
    for i, t in enumerate(times):
        if i + 1 < len(times):
            nxt = times[i + 1]
            # 下一个四分点是峰值 → 正在加速离开过零点后减速到峰 → 正弦 ease-out；否则 ease-in
            on_q = (t - lag) % q == 0
            idx = round((t - lag) / q) % 4 if on_q else math.ceil((t - lag) / q) % 4
            if on_q:
                ease = "sout" if idx in (0, 2) else "sin"
            else:
                ease = "sout" if idx in (1, 3) else "sin"
        else:
            ease = "io"
        keys.append((t, val(t), ease))
    return keys
