"""生成宠物的 Rive 工程。

用法：python -I gen/gen_pets.py [宠物名 ...]   （不写名字就全部生成）

做法：整张原画作为贴图，铺一层三角网格，蒙皮到骨骼（地面 / 身体 / 头 / 耳朵、尾巴等部件），
所有动作都靠骨骼完成，所以造型和原画一模一样。眨眼、闭眼用“眼皮贴片”：
把眼睛位置补成周围毛色的小图，盖在眼睛上，从上往下（闭眼）或从下往上（笑眯眼）展开。

输入：gen/rigs.json（每只宠物的关键点）、art/<pet>.png（prep_art.py 整理过的原画）
输出：projects/<pet>/rive.yaml + scene.rml，art/<pet>-lidL.png / -lidR.png

状态机（宿主通过 view model「Pet」驱动，和旧版接口保持一致）：
  hovered（布尔）  指针移入：先打招呼，然后保持关注
  sleeping（布尔） 睡觉；改回 false 时自动播放醒来
  pet（触发器）    摸一摸
  celebrate（触发器）庆祝（完成任务、得经验）
  skill（触发器）  路线招式（只有分化后的形态有）
"""
import base64
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from riv import Anim, ang, app, fmt, inv, mat, smoothstep, wrap  # noqa: E402
from eyes import arc_line, crescent, eye_geometry, lid_rig  # noqa: E402
from motion import motion  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = os.path.join(ROOT, "art")
PROJ = os.path.join(ROOT, "projects")

AB = 500                 # 画板边长
GROUND_Y = 452           # 地面线
FIT_W, FIT_H = 430, 380  # 角色适配框
GRID = 20                # 网格间距（原画像素）
OUTLINE = "FF263235"     # 闭眼线颜色（接近原画描边）


class Ids:
    def __init__(self):
        self.n, self.m = 10, {}

    def __getitem__(self, k):
        if k not in self.m:
            self.m[k] = f"0:{self.n}"
            self.n += 1
        return self.m[k]


# ── 眼睛：找两块最大的深色瞳孔，再沿“不是暖色毛发”的像素扩到整只眼 ─────────
def find_eyes(rgba, head_poly):
    """找眼睛：头部区域里最大的两块深色瞳孔；再在瞳孔附近的小窗口里把深色描边围住的区域填满，
    得到整只眼（描边 + 眼白 + 虹膜）。填不出合理结果时，按瞳孔框放大估计。"""
    a = rgba.astype(float)
    R, G, B, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    lum = 0.299 * R + 0.587 * G + 0.114 * B
    hm = Image.new("L", (al.shape[1], al.shape[0]), 0)
    ImageDraw.Draw(hm).polygon([tuple(p) for p in head_poly], fill=255)
    head = np.array(hm) > 0
    dark = (lum < 115) & (al > 200)
    core = ndi.binary_opening(dark & head, structure=np.ones((7, 7)))
    lab, n = ndi.label(core)
    sizes = ndi.sum(core, lab, range(1, n + 1))
    eyes = []
    for k in np.argsort(sizes)[::-1][:2]:
        ys, xs = np.where(lab == k + 1)
        cx0, cx1, cy0, cy1 = xs.min(), xs.max(), ys.min(), ys.max()
        cw, ch = cx1 - cx0 + 1, cy1 - cy0 + 1
        # 小窗口里填洞
        X0, X1 = max(int(cx0 - cw), 0), min(int(cx1 + cw), al.shape[1])
        Y0, Y1 = max(int(cy0 - ch), 0), min(int(cy1 + ch), al.shape[0])
        win = ndi.binary_closing(dark[Y0:Y1, X0:X1], structure=np.ones((3, 3)))
        filled = ndi.binary_fill_holes(win)
        wl, _ = ndi.label(filled)
        comp = wl[int(ys.mean()) - Y0, int(xs.mean()) - X0]
        box, shape, full = None, None, None
        if comp:
            region = wl == comp
            fy, fx = np.where(region)
            bw, bh = fx.max() - fx.min() + 1, fy.max() - fy.min() + 1
            if cw * 1.05 <= bw <= cw * 2.6 and ch * 1.05 <= bh <= ch * 2.4:
                full = np.zeros(al.shape, bool)
                full[fy + Y0, fx + X0] = True
                full = convex_fill(full)
                body = eye_body(full)
                by, bx = np.where(body)
                bw2, bh2 = bx.max() - bx.min() + 1, by.max() - by.min() + 1
                if cw * 1.05 <= bw2 <= cw * 1.9 and ch * 1.05 <= bh2 <= ch * 1.8:
                    box = (int(bx.min()), int(by.min()), int(bx.max()), int(by.max()))
                    shape = body
        if box is None:  # 按瞳孔框估计整只眼
            mx, my = (cx0 + cx1) / 2, (cy0 + cy1) / 2 + ch * 0.06
            hw_, hh_ = cw * 1.3 / 2, ch * 1.28 / 2
            box = (int(mx - hw_), int(my - hh_), int(mx + hw_), int(my + hh_))
        eyes.append({"box": box, "core": (int(cx0), int(cy0), int(cx1), int(cy1)), "shape": shape, "full": full})
    eyes.sort(key=lambda e: e["box"][0])
    return eyes


def eye_body(full):
    """眼睛本体：对眼睛区域的外轮廓拟合一个倾斜椭圆（去掉最往外凸的点再拟合一次，翘出去的睫毛就不算），
    再只保留原形状落在椭圆里的部分——原画睫毛的形状保持不变，眼角翘出去的睫毛被切掉。"""
    cs, _ = cv2.findContours(full.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = max(cs, key=len).reshape(-1, 2).astype(np.float32)
    if len(pts) < 8:
        return full
    ell = cv2.fitEllipse(pts)
    for _ in range(2):
        (ex, ey), (ma, mb), ang = ell
        t = np.deg2rad(ang)
        dx, dy = pts[:, 0] - ex, pts[:, 1] - ey
        u = (dx * np.cos(t) + dy * np.sin(t)) / (ma / 2)
        v = (-dx * np.sin(t) + dy * np.cos(t)) / (mb / 2)
        r = np.sqrt(u * u + v * v)
        keep = r < np.quantile(r, 0.85)
        if keep.sum() < 8:
            break
        ell = cv2.fitEllipse(pts[keep])
    m = np.zeros(full.shape, np.uint8)
    cv2.ellipse(m, ell, 1, -1)
    m = ndi.binary_dilation(m.astype(bool), iterations=3)
    body = full & m
    lab, n = ndi.label(body)
    if n > 1:
        body = lab == (np.argmax(ndi.sum(body, lab, range(1, n + 1))) + 1)
    return body


def eye_mask(shape, box, grow=4):
    """眼睛区域的椭圆蒙版（比眼框大一圈，保证盖住描边）。"""
    m = Image.new("L", (shape[1], shape[0]), 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(m).ellipse([x0 - grow, y0 - grow, x1 + grow, y1 + grow], fill=255)
    return np.array(m) > 0


def convex_fill(mask):
    """眼睛是凸的椭圆：取凸包，把描边没围住的眼白缺口也算进眼睛。"""
    ys, xs = np.where(mask)
    hull = cv2.convexHull(np.stack([xs, ys], axis=1).astype(np.int32))
    out = np.zeros(mask.shape, np.uint8)
    cv2.fillPoly(out, [hull.reshape(-1, 2)], 1)
    return out.astype(bool) | mask


def cover_mask(rgba, body):
    """闭眼时要盖住的范围：眼睛本体 + 贴在眼睛上的睫毛（比如成年体眼角翘出去的睫毛）。
    连到画面外的长线（脸的描边）只算贴着眼睛的那一点，不会被抹掉。"""
    a = rgba.astype(float)
    lum = a[..., :3] @ [0.299, 0.587, 0.114]
    dark = (lum < 115) & (a[..., 3] > 150)
    ys, xs = np.where(body)
    P = 18
    X0, X1 = max(xs.min() - P, 0), min(xs.max() + P + 1, rgba.shape[1])
    Y0, Y1 = max(ys.min() - P, 0), min(ys.max() + P + 1, rgba.shape[0])
    win_dark = dark[Y0:Y1, X0:X1]
    near = ndi.binary_dilation(body, iterations=2)[Y0:Y1, X0:X1]
    near4 = ndi.binary_dilation(body, iterations=4)[Y0:Y1, X0:X1]
    lab, n = ndi.label(win_dark)
    extra = np.zeros_like(win_dark)
    for k in range(1, n + 1):
        comp = lab == k
        if not (comp & near).any():
            continue
        border = comp[0].any() or comp[-1].any() or comp[:, 0].any() or comp[:, -1].any()
        extra |= (comp & near4) if border else comp
    # 贴着眼睛的白色高光（眼白边、眼角反光）也算进来，不然闭眼后会剩一道白边
    sat = a[..., :3].max(axis=2) - a[..., :3].min(axis=2)
    win_white = ((sat < 22) & (lum > 228) & (a[..., 3] > 150))[Y0:Y1, X0:X1]
    near8 = ndi.binary_dilation(body, iterations=8)[Y0:Y1, X0:X1]
    wl, wn = ndi.label(win_white)
    for k in range(1, wn + 1):
        comp = wl == k
        if (comp & near).any() and (comp & ~near8).sum() < 60 and comp.sum() < body.sum() * 0.6:
            extra |= comp
    out = body.copy()
    out[Y0:Y1, X0:X1] |= ndi.binary_dilation(extra, iterations=1)
    return out


def make_lid_patch(rgba, eye, cover, path):
    """闭眼时盖在眼睛上的皮肤。
    范围：眼睛 + 睫毛再往外 5px（把原画眼睛外面那圈浅色光晕也盖住）。
    颜色：只从眼睛周围占多数的毛色里取，每个点取最近的毛色（毛色分界线会自然延伸过去，不会糊成一团）。
    眼睛外面的深色线条（眉毛、脸的描边）不盖。"""
    ys, xs = np.where(cover)
    M = 16
    X0, X1 = max(xs.min() - M, 0), min(xs.max() + M + 1, rgba.shape[1])
    Y0, Y1 = max(ys.min() - M, 0), min(ys.max() + M + 1, rgba.shape[0])
    crop = rgba[Y0:Y1, X0:X1].copy()
    cov = cover[Y0:Y1, X0:X1]
    region = ndi.binary_dilation(cov, iterations=5)
    c = crop[..., :3].astype(float)
    lum = c @ [0.299, 0.587, 0.114]
    sat = c.max(axis=2) - c.min(axis=2)
    dark, white, clear = lum < 130, (sat < 16) & (lum > 232), crop[..., 3] < 200
    usable = ~ndi.binary_dilation(region | dark | white, iterations=2) & ~clear
    # 补色来源：眼睛正上方和正下方的毛（上眼皮从上面来、下面接着脸颊），
    # 不用眼睛左右两侧——那里常常是鳃、耳朵或脸的边缘
    yy, xx = np.mgrid[0:crop.shape[0], 0:crop.shape[1]]
    ecx, ecy = (xs.min() + xs.max()) / 2 - X0, (ys.min() + ys.max()) / 2 - Y0
    hw_, hh_ = (xs.max() - xs.min()) / 2 + 1, (ys.max() - ys.min()) / 2 + 1
    vertical = np.abs((xx - ecx) / hw_) < 0.6 * np.abs((yy - ecy) / hh_) + 0.25
    good = usable & vertical & ndi.binary_dilation(region, iterations=16)
    if good.sum() < 40:
        good = usable
    # 先用最近的毛色铺满，再做扩散（固定住有效的毛色像素，其余反复取四邻平均），颜色交界变成柔和的过渡
    _, (iy, ix) = ndi.distance_transform_edt(~good, return_indices=True)
    fill = c[iy, ix].astype(np.float32)
    free = ~good
    for _ in range(400):
        avg = (np.roll(fill, 1, 0) + np.roll(fill, -1, 0) + np.roll(fill, 1, 1) + np.roll(fill, -1, 1)) / 4
        fill = np.where(free[..., None], avg, c.astype(np.float32))
    fill = cv2.GaussianBlur(fill, (0, 0), 1.2)
    rgb = np.where(region[..., None], fill, c)
    feather = np.clip(1 - ndi.distance_transform_edt(~region) / 3.0, 0, 1)
    feather = np.where(region | ~dark, feather, 0)
    alpha = feather * (crop[..., 3] / 255.0) * 255
    Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8)).save(path, optimize=True)
    return (X0, Y0, X1, Y1)


def prepare_eyes(rgba, spec, symmetric=False):
    """找眼睛、量轮廓、算眼皮。两只眼的闭眼线共用脸的角度。
    symmetric：两只眼闭上后的线一样长、一样粗、一样高（幼年形态用；原画是微侧脸，两眼本身大小不一，
    闭上后按各自尺寸画会显得一大一小）。"""
    eyes = find_eyes(rgba, spec["head"])
    if spec.get("eyes"):
        for e, box in zip(eyes, spec["eyes"]):
            e["box"], e["shape"] = tuple(box), None
    for e in eyes:
        body = e["shape"] if e.get("shape") is not None else eye_mask(rgba.shape, e["box"], grow=1)
        e["body"] = convex_fill(body)
        e["geo"] = eye_geometry(rgba, e["body"])
        e["cover"] = cover_mask(rgba, e["body"])
        if e.get("full") is not None:
            e["cover"] |= e["full"]
    l, r = eyes[0]["geo"], eyes[-1]["geo"]
    tilt = float(np.clip(0.6 * math.atan2(r["cy"] - l["cy"], r["cx"] - l["cx"]), -0.25, 0.25))
    if symmetric:
        avg = {k: (eyes[0]["geo"][k] + eyes[-1]["geo"][k]) / 2 for k in ("a", "b", "thick", "w_mid")}
        for e in eyes:
            e["lid"] = lid_rig({**e["geo"], **avg}, tilt, tall=True)  # 幼年形态都是竖长的大眼睛
    else:
        for e in eyes:
            e["lid"] = lid_rig(e["geo"], tilt)
    return eyes


# ── 主流程 ──────────────────────────────────────────────────────────
def build(pet, spec):
    ids = Ids()
    img = Image.open(os.path.join(ART, f"{pet}.png")).convert("RGBA")
    rgba = np.array(img)
    w, h = img.size
    s = min(FIT_W / w, FIT_H / h)
    cx = AB / 2
    cy = GROUND_Y - s * (spec["ground"][1] - h / 2)

    def W(p):
        return (cx + s * (p[0] - w / 2), cy + s * (p[1] - h / 2))

    # ── 骨骼 ──
    bones = []  # dict(name, parent, kind, origin, angle, length, rel, local)

    def add(name, parent, p0, p1, root_in=None):
        o, t = W(p0), W(p1)
        a = ang(o, t)
        b = {"name": name, "parent": parent, "origin": o, "angle": a, "length": math.dist(o, t),
             "world": mat(a, *o)}
        if root_in is None:  # Bone：接在父骨骼末端
            pa = next(x for x in bones if x["name"] == parent)["angle"] if parent else 0
            b["kind"], b["rel"] = ("RootBone" if parent is None else "Bone"), wrap(a - pa)
            if parent is None:
                b["local"] = o
        else:
            pb = next(x for x in bones if x["name"] == root_in)
            b["kind"], b["rel"], b["local"] = "RootBone", wrap(a - pb["angle"]), app(inv(pb["world"]), o)
        bones.append(b)
        return b

    root = add("Root", None, spec["ground"], spec["hip"])
    add("Body", "Root", spec["hip"], spec["neck"])
    head = add("Head", "Body", spec["neck"], spec["crown"])
    chains = []
    for ap in spec.get("appendages", []):
        pts, names = ap["points"], []
        for i in range(len(pts) - 1):
            nm = f'{ap["name"]}{i}'
            if i == 0:
                add(nm, ap["parent"], pts[0], pts[1], root_in=ap["parent"])
            else:
                add(nm, names[-1], pts[i], pts[i + 1])
            names.append(nm)
        up = wrap(-math.pi / 2 - ang(W(pts[0]), W(pts[-1])))
        length = sum(math.dist(W(pts[i]), W(pts[i + 1])) for i in range(len(pts) - 1))
        chains.append({**ap, "bones": names, "perk": 1 if up > 0 else -1, "length": length})
    bidx = {b["name"]: i for i, b in enumerate(bones)}

    # ── 网格 + 权重 ──
    alpha = rgba[..., 3] > 4
    dil = ndi.binary_dilation(alpha, iterations=6)

    def soft(poly, sigma):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
        return ndi.gaussian_filter(np.array(m).astype(float) / 255, sigma)

    head_m = soft(spec["head"], 7)
    for ch in chains:
        ch["mask"] = soft(ch["poly"], 6)
    cols = sorted(set(list(range(0, w, GRID)) + [w]))
    rows = sorted(set(list(range(0, h, GRID)) + [h]))
    vid, verts, tris = {}, [], []

    def vx(ci, ri):
        if (ci, ri) not in vid:
            vid[(ci, ri)] = len(verts)
            verts.append((cols[ci], rows[ri]))
        return vid[(ci, ri)]

    for ri in range(len(rows) - 1):
        for ci in range(len(cols) - 1):
            if dil[rows[ri]:rows[ri + 1], cols[ci]:cols[ci + 1]].any():
                a0, a1, a2, a3 = vx(ci, ri), vx(ci + 1, ri), vx(ci + 1, ri + 1), vx(ci, ri + 1)
                tris += [a0, a1, a2, a0, a2, a3]

    hip, neck = np.array(spec["hip"], float), np.array(spec["neck"], float)
    bd = (neck - hip) / np.linalg.norm(neck - hip)

    def sample(m, x, y):
        return float(m[min(int(y), h - 1), min(int(x), w - 1)])

    # 透明区域的顶点沿用最近的有颜色像素的权重，这样轮廓外的空白跟着部件一起动，边缘不会被拉扯
    dist, (iy, ix) = ndi.distance_transform_edt(~alpha, return_indices=True)

    def weight_at(x, y):
        p = np.array([x, y], float)
        wb = float(smoothstep(-28, 28, np.dot(p - hip, bd)))
        mh = sample(head_m, x, y)
        wt = {bidx["Head"]: mh, bidx["Body"]: (1 - mh) * wb, bidx["Root"]: (1 - mh) * (1 - wb)}
        for ch in chains:
            m = sample(ch["mask"], x, y)
            if m < 0.004:
                continue
            pts = np.array(ch["points"], float)
            best = None
            for k in range(len(pts) - 1):
                a_, b_ = pts[k], pts[k + 1]
                t = np.clip(np.dot(p - a_, b_ - a_) / np.dot(b_ - a_, b_ - a_), 0, 1)
                d = np.linalg.norm(p - (a_ + t * (b_ - a_)))
                if best is None or d < best[0]:
                    best = (d, k + t)
            n = len(ch["bones"])
            sp = min(best[1], n - 0.5)
            cw = {bidx[ch["parent"]]: max(0.0, 0.5 - sp)}
            for i, nm in enumerate(ch["bones"]):
                cw[bidx[nm]] = cw.get(bidx[nm], 0) + max(0.0, 1 - abs(sp - (i + 0.5)))
            tot = sum(cw.values())
            wt = {k: v * (1 - m) for k, v in wt.items()}
            for k, v in cw.items():
                wt[k] = wt.get(k, 0) + m * v / tot
        return wt

    weights = []
    for (x, y) in verts:
        xi, yi = min(int(x), w - 1), min(int(y), h - 1)
        if dist[yi, xi] > 2:
            wt = weight_at(ix[yi, xi], iy[yi, xi])
        else:
            wt = weight_at(x, y)
        top = sorted(((v, k) for k, v in wt.items() if v > 0.003), reverse=True)[:4]
        tot = sum(v for v, _ in top)
        q = [max(1, round(v / tot * 255)) for v, _ in top]
        q[0] += 255 - sum(q)
        idx = sum((k + 1) << (8 * i) for i, (_, k) in enumerate(top))
        val = sum(v << (8 * i) for i, v in enumerate(q))
        weights.append((idx, val))

    # 调试图：每个顶点按主要骨骼上色，再画出区域多边形和骨骼点
    dbg = Image.new("RGBA", (w, h), (240, 240, 244, 255))
    dbg.alpha_composite(img)
    dd = ImageDraw.Draw(dbg)
    pal = [(120, 120, 120), (60, 140, 255), (255, 170, 0), (230, 40, 160), (0, 200, 120), (140, 60, 255),
           (255, 90, 60), (0, 170, 220), (200, 200, 0), (255, 0, 0), (0, 120, 60), (120, 0, 200)]
    for (x, y), (idx, val) in zip(verts, weights):
        b0 = (idx & 255) - 1
        c = pal[b0 % len(pal)]
        dd.ellipse([x - 3, y - 3, x + 3, y + 3], fill=c + (255,))
    dd.line([tuple(spec["ground"]), tuple(spec["hip"]), tuple(spec["neck"]), tuple(spec["crown"])], fill=(0, 0, 0, 255), width=3)
    dd.polygon([tuple(p) for p in spec["head"]], outline=(60, 140, 255, 255))
    for ch in chains:
        dd.polygon([tuple(p) for p in ch["poly"]], outline=(230, 40, 160, 255))
        dd.line([tuple(p) for p in ch["points"]], fill=(0, 0, 0, 255), width=3)
    os.makedirs(os.path.join(ROOT, "review", "rig"), exist_ok=True)
    dbg.convert("RGB").save(os.path.join(ROOT, "review", "rig", f"{pet}.png"))

    def varuint(n):
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | (0x80 if n else 0))
            if not n:
                return bytes(out)

    tri_b64 = base64.b64encode(b"".join(varuint(i) for i in tris)).decode()

    # ── 眼睛（挂在头骨上）──
    # 每只眼一个节点，里面：闭眼线 ∪ / ∩、往下走的睫毛、裁剪出来的皮肤、裁剪边。
    # 动作层（Hold）和眨眼层（Blink）各一套，互不干扰。
    eyes = prepare_eyes(rgba, spec, symmetric=not pet.endswith("-adult"))
    HI = inv(head["world"])
    face = []

    def poly(pts, name):
        vs = "".join(f'<StraightVertex x="{fmt(x)}" y="{fmt(y)}"/>' for x, y in pts)
        return f'<PointsPath isClosed="true" name="{name}">{vs}</PointsPath>'

    for side, e in zip("LR", eyes):
        g, lr = e["geo"], e["lid"]
        lid = f"{pet}-lid{side}.png"
        X0, Y0, X1, Y1 = make_lid_patch(rgba, e, e["cover"], os.path.join(ART, lid))
        ecx, ecy = g["cx"], g["cy"]
        e.update(geo=g, lid=lr, cx=ecx, cy=ecy, w=2 * g["a"], h=2 * g["b"])
        pos = app(HI, W((ecx, ecy)))
        col, tilt = g["color"], lr["tilt"]

        def at(oy):
            return (-math.sin(tilt) * oy, math.cos(tilt) * oy)

        fill = f'<Fill name="F"><SolidColor colorValue="{col}" name="C"/></Fill>'
        kids = []
        for nm, line, pts in (("HoldShut", lr["shut"], arc_line(lr["shut"]["xm"], lr["shut"]["sag"], lr["shut"]["t"], up=False)),
                              ("HoldJoy", lr["joy"], arc_line(lr["joy"]["xm"], lr["joy"]["arch"], lr["joy"]["t"], up=True))):
            x_, y_ = at(line["oy"])
            kids.append(f'<Node x="{fmt(x_)}" y="{fmt(y_)}" rotation="{fmt(tilt)}" opacity="0" name="{nm}{side}" id="{ids[nm + side]}">'
                        f'<Shape name="{nm}Shape{side}">{poly(pts, "P")}{fill}</Shape></Node>')
        c0 = lr["lash_c0"]
        lash = [(x, y - c0) for x, y in crescent(g["xs"], g["top"], lr["thick"])]
        pcx, pcy = (X0 + X1) / 2 - ecx, (Y0 + Y1) / 2 - ecy

        def lash_node(k):
            return (f'<Node y="{fmt(c0)}" opacity="0" name="{k}Lash{side}" id="{ids[k + "Lash" + side]}">'
                    f'<Shape name="{k}LashShape{side}">{poly(lash, "P")}{fill}</Shape></Node>')

        def lid_node(k):
            return (f'<Node name="{k}Lid{side}" id="{ids[k + "Lid" + side]}">'
                    f'<Image assetId="{ids["asset:" + lid]}" x="{fmt(pcx)}" y="{fmt(pcy)}" name="{k}Skin{side}"/>'
                    f'<ClippingShape sourceId="{ids[k + "Cut" + side]}" name="Clip"/></Node>')

        kids.append(lash_node("Hold"))
        # 眨眼那一套包在 BlinkSet 里：动作层闭眼 / 半闭眼时把它整个藏起来，免得在闭着的眼睛上再眨一次
        kids.append(f'<Node name="BlinkSet{side}" id="{ids["BlinkSet" + side]}">{lash_node("Blink")}{lid_node("Blink")}</Node>')
        kids.append(lid_node("Hold"))
        xs, top, B2 = g["xs"], g["top"], g["b"]
        cut = ([(xs[0] - 18, top[0] - 5 * B2), (xs[-1] + 18, top[-1] - 5 * B2), (xs[-1] + 18, top[-1])]
               + list(zip(xs[::-1], top[::-1])) + [(xs[0] - 18, top[0])])
        for k in ("Hold", "Blink"):
            kids.append(f'<Node y="{fmt(lr["edge_open"])}" name="{k}Edge{side}" id="{ids[k + "Edge" + side]}">'
                        f'<Shape name="{k}Cut{side}" id="{ids[k + "Cut" + side]}">{poly(cut, "P")}</Shape></Node>')
        face.append(f'<Node x="{fmt(pos[0])}" y="{fmt(pos[1])}" rotation="{fmt(-head["angle"])}" scaleX="{fmt(s)}" '
                    f'scaleY="{fmt(s)}" name="Eye{side}" id="{ids["Eye" + side]}">{"".join(kids)}</Node>')
        # 腮红
        ew, eh = 2 * g["a"], 2 * g["b"]
        out = -1 if side == "L" else 1
        bl = app(HI, W((ecx + out * ew * 0.18, ecy + g["b"] + eh * 0.22)))
        face.append(f'<Node x="{fmt(bl[0])}" y="{fmt(bl[1])}" rotation="{fmt(-head["angle"])}" opacity="0" name="Blush{side}" id="{ids["Blush" + side]}">'
                    f'<Shape name="BlushShape"><Ellipse width="{fmt(ew * 0.95 * s)}" height="{fmt(eh * 0.32 * s)}" '
                    f'originX="0.5" originY="0.5" name="Path"/><Fill fillRule="clockwise" name="F">'
                    f'<SolidColor colorValue="99FF8C9C" name="C"/><Feather strength="{fmt(eh * 0.12 * s)}" name="Fe"/></Fill></Shape></Node>')

    # ── 骨骼 RML ──
    def bone_rml(b):
        kids = [bone_rml(c) for c in bones if c["parent"] == b["name"]]
        if b["name"] == "Head":
            kids = face + kids
        attrs = f'length="{fmt(b["length"])}" rotation="{fmt(b["rel"])}"'
        if b["kind"] == "RootBone":
            attrs = f'x="{fmt(b["local"][0])}" y="{fmt(b["local"][1])}" ' + attrs
        return f'<{b["kind"]} {attrs} name="{b["name"]}" id="{ids[b["name"]]}">{"".join(kids)}</{b["kind"]}>'

    skeleton = bone_rml(bones[0])

    mesh_v = "".join(
        f'<MeshVertex x="{fmt(x - w / 2)}" y="{fmt(y - h / 2)}" u="{fmt(min(x / w, 1))}" v="{fmt(min(y / h, 1))}">'
        f'<Weight values="{val}" indices="{idx}"/></MeshVertex>'
        for (x, y), (idx, val) in zip(verts, weights))
    tendons = "".join(
        f'<Tendon boneId="{ids[b["name"]]}" xx="{fmt(b["world"][0])}" xy="{fmt(b["world"][1])}" '
        f'yx="{fmt(b["world"][2])}" yy="{fmt(b["world"][3])}" tx="{fmt(b["world"][4])}" ty="{fmt(b["world"][5])}" name="T{b["name"]}"/>'
        for b in bones)
    art = (f'<Image assetId="{ids["asset:" + pet + ".png"]}" x="{fmt(cx)}" y="{fmt(cy)}" scaleX="{fmt(s)}" scaleY="{fmt(s)}" '
           f'name="Art" id="{ids["Art"]}"><Mesh triangleIndexBytes="{tri_b64}" name="Mesh">{mesh_v}'
           f'<Skin xx="{fmt(s)}" yy="{fmt(s)}" tx="{fmt(cx)}" ty="{fmt(cy)}" name="Skin">{tendons}</Skin></Mesh></Image>')

    ctx = dict(pet=pet, spec=spec, s=s, W=W, bones={b["name"]: b for b in bones}, chains=chains, eyes=eyes,
               head=head, root=root, h_world=s * (spec["ground"][1] - min(p[1] for p in spec["head"])))
    fx, anims, sm, vm = motion(ctx, ids)

    shadow_w = s * w * 0.62
    g = W(spec["ground"])
    shadow = (f'<Node x="{fmt(g[0])}" y="{fmt(GROUND_Y + 4)}" name="Shadow" id="{ids["Shadow"]}"><Shape name="ShadowShape">'
              f'<Ellipse width="{fmt(shadow_w)}" height="{fmt(shadow_w * 0.12)}" originX="0.5" originY="0.5" name="Path"/>'
              f'<Fill fillRule="clockwise" name="F"><SolidColor colorValue="2E3A2A1E" name="C"/>'
              f'<Feather strength="10" name="Fe"/></Fill></Shape></Node>')

    assets = [f'<ImageAsset file="../../art/{pet}.png" name="{pet}" id="{ids["asset:" + pet + ".png"]}"/>']
    for side in "LR":
        lid = f"{pet}-lid{side}.png"
        assets.append(f'<ImageAsset file="../../art/{lid}" name="{pet}-lid{side}" id="{ids["asset:" + lid]}"/>')

    rml = (f'<Rive version="1" kind="fragment">\n'
           f'<Artboard defaultStateMachineId="{ids["SM"]}" viewModelId="{ids["VM"]}" viewModelInstanceId="{ids["VMI"]}" '
           f'styleId="{ids["Style"]}" width="{AB}" height="{AB}" name="{pet}" id="{ids["Artboard"]}">\n'
           f'<LayoutComponentStyle name="Artboard Style" id="{ids["Style"]}"/>\n{sm}\n{fx}\n{skeleton}\n{art}\n{shadow}\n'
           + "\n".join(a.rml(ids) for a in anims) +
           f'\n</Artboard>\n{vm}\n' + "\n".join(assets) + "\n</Rive>\n")
    d = os.path.join(PROJ, pet)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "scene.rml"), "w", encoding="utf8") as f:
        f.write(rml)
    with open(os.path.join(d, "rive.yaml"), "w", encoding="utf8") as f:
        f.write(f"name: {pet}\nlogs:\n  file: build/rive.log\n  problems: build/problems.log\n")
    # 预览版：同一场景加浅色背景，只用来截图 / 做 GIF，不进 app
    pd = os.path.join(ROOT, "projects-preview", pet)
    os.makedirs(pd, exist_ok=True)
    bg = '<Fill name="Background"><SolidColor colorValue="FFF6F3EC" name="C"/></Fill>\n'
    marker = f'<LayoutComponentStyle name="Artboard Style" id="{ids["Style"]}"/>\n'
    with open(os.path.join(pd, "scene.rml"), "w", encoding="utf8") as f:
        f.write(rml.replace(marker, marker + bg, 1))
    with open(os.path.join(pd, "rive.yaml"), "w", encoding="utf8") as f:
        f.write(f"name: {pet}\nlogs:\n  file: build/rive.log\n  problems: build/problems.log\n")
    print(f"{pet}: {len(verts)} verts, {len(tris) // 3} tris, {len(bones)} bones, eyes {[e['box'] for e in eyes]}")



if __name__ == "__main__":
    rigs = json.load(open(os.path.join(HERE, "rigs.json"), encoding="utf8"))
    names = sys.argv[1:] or [k for k in rigs if not k.startswith("_")]
    for n in names:
        build(n, rigs[n])
