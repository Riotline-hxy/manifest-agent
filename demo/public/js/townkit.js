// 小镇的画具：等距坐标、颜色、墙、屋顶、窗、门、影子、烟……每个建筑文件（buildings/*.js）都用这一套画。
// 坐标：一样东西画在自己的占地中心，x、y 是格子单位（1×1 的占地是 -0.5..0.5），z 是往上的像素高度。
// 光从左上来：顶面最亮、朝左下的面次之、朝右下的面最暗。窗户和灯的颜色走 town.css 的变量，深色氛围下会亮。
// 渐变 id 写成 url(#@@xxx)，渲染时换成每张图自己的前缀。
import { esc } from "./ui.js";

export const TW = 64, TH = 32;
export const HW = TW / 2, HH = TH / 2;
export const r1 = (n) => Math.round(n * 10) / 10;
export const P = (x, y, z = 0) => [r1((x - y) * HW), r1((x + y) * HH - z)];
export const pts = (l) => l.map((p) => p.join(",")).join(" ");
export const poly = (l, fill, extra = "") => `<polygon points="${pts(l)}" fill="${fill}"${extra}/>`;
export const line = (a, b, stroke, w = 1, extra = "") => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${stroke}" stroke-width="${w}" stroke-linecap="round"${extra}/>`;

// ---- 颜色：变亮往白，变暗往一点点偏紫的深色（比纯黑柔和，更像微缩模型） ----
export const rgb = (h) => { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
export function shade(h, t) {
  const to = t > 0 ? [255, 252, 245] : [44, 34, 64], k = Math.abs(t);
  return "#" + rgb(h).map((c, i) => Math.round(c + (to[i] - c) * k).toString(16).padStart(2, "0")).join("");
}

// ---- 基本形 ----
export const lerp = (a, b, t) => [r1(a[0] + (b[0] - a[0]) * t), r1(a[1] + (b[1] - a[1]) * t)];
export function inset(q, k) {
  const c = [q.reduce((s, p) => s + p[0], 0) / q.length, q.reduce((s, p) => s + p[1], 0) / q.length];
  return q.map((p) => lerp(p, c, k));
}
// 墙、屋顶、圆柱这些要用坐标的画具由 shapes(P, m) 造出来：m=true 是「转过来」的那一套——
// x、y 对调（整样东西左右翻过来，门从朝左下变成朝右下），但光还是从左上来：
// 原来朝左下（亮一点）的那面翻到右边以后用暗的颜色，翻到左边的那面用亮的颜色。
function shapes(P, m) {
  // 朝左下的墙（y = b 那一面）和朝右下的墙（x = a 那一面）上的一块：左下、右下、右上、左上（转过来时左右跟着翻）
  const faceL = (b, x0, x1, z0, z1, ox = 0, oy = 0) => [P(ox + x0, oy + b, z0), P(ox + x1, oy + b, z0), P(ox + x1, oy + b, z1), P(ox + x0, oy + b, z1)];
  const faceR = (a, y0, y1, z0, z1, ox = 0, oy = 0) => [P(ox + a, oy + y0, z0), P(ox + a, oy + y1, z0), P(ox + a, oy + y1, z1), P(ox + a, oy + y0, z1)];

  function box({ x = 0, y = 0, a, b, z = 0, h, c, l, r, t, top = true }) {
    const Q = (u, v, w) => P(x + u, y + v, w);
    const z1 = z + h;
    const lit = l || c, dark = r || shade(c, -0.2);
    return poly([Q(-a, b, z), Q(a, b, z), Q(a, b, z1), Q(-a, b, z1)], m ? dark : lit)
      + poly([Q(a, -b, z), Q(a, b, z), Q(a, b, z1), Q(a, -b, z1)], m ? lit : dark)
      + (top ? poly([Q(-a, -b, z1), Q(a, -b, z1), Q(a, b, z1), Q(-a, b, z1)], t || shade(c, 0.16)) : "");
  }

  // 两坡屋顶，屋脊沿 x：朝左下那面是正坡，山墙在右边。mid 是夹在后坡和前坡之间要画的东西（烟囱）。x、y 是中心偏移
  function roofX({ x = 0, y = 0, a, b, z, rise, o = 0.05, c, wall, mid = "" }) {
    const A = a + o, B = b + o, Q = (u, v, w) => P(x + u, y + v, w);
    const front = m ? shade(c, -0.16) : c, gable = m ? shade(wall, 0.2) : wall;
    return poly([Q(-A, -B, z), Q(A, -B, z), Q(A, 0, z + rise), Q(-A, 0, z + rise)], shade(c, m ? 0.12 : 0.14)) + mid
      + poly([Q(a, -b, z), Q(a, b, z), Q(a, 0, z + rise)], gable)
      + poly([Q(-A, 0, z + rise), Q(A, 0, z + rise), Q(A, B, z), Q(-A, B, z)], front)
      + poly([Q(-A, B, z), Q(A, B, z), Q(A, B, z - 2.5), Q(-A, B, z - 2.5)], shade(c, m ? -0.35 : -0.25))
      + poly([Q(A, 0, z + rise), Q(A, B, z), Q(A, B, z - 2.5), Q(A, 0, z + rise - 2.5)], shade(c, m ? -0.25 : -0.35))
      + line(Q(-A, 0, z + rise), Q(A, 0, z + rise), shade(c, 0.3), 1.2);
  }
  // 屋脊沿 y：左坡朝着光，右坡背光，山墙朝左下
  function roofY({ x = 0, y = 0, a, b, z, rise, o = 0.05, c, wall, mid = "" }) {
    const A = a + o, B = b + o, Q = (u, v, w) => P(x + u, y + v, w);
    const back = m ? shade(c, -0.1) : shade(c, 0.12), front = m ? c : shade(c, -0.16), gable = m ? shade(wall, -0.16) : wall;
    return poly([Q(-A, -B, z), Q(0, -B, z + rise), Q(0, B, z + rise), Q(-A, B, z)], back) + mid
      + poly([Q(0, -B, z + rise), Q(A, -B, z), Q(A, B, z), Q(0, B, z + rise)], front)
      + poly([Q(-a, b, z), Q(a, b, z), Q(0, b, z + rise)], gable)
      + `<polyline points="${pts([Q(-A, B, z - 1), Q(0, B, z + rise), Q(A, B, z - 1)])}" fill="none" stroke="${shade(c, -0.3)}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>`;
  }

  // 圆柱：底面中心 (x, y)，半径 r（格子单位），从 z 起高 h
  function cyl({ x = 0, y = 0, r, z = 0, h, c, top }) {
    const [sx, sy] = P(x, y, 0), rx = r1(r * 0.7071 * TW), ry = r1(r * 0.7071 * TH), yb = r1(sy - z), yt = r1(sy - z - h);
    const side = `M${sx - rx},${yt} L${sx - rx},${yb} A${rx} ${ry} 0 0 0 ${sx + rx},${yb} L${sx + rx},${yt} Z`;
    return `<path d="${side}" fill="${c}"/><path d="${side}" fill="url(#@@cyl)"/>`
      + `<ellipse cx="${sx}" cy="${yt}" rx="${rx}" ry="${ry}" fill="${top || shade(c, 0.18)}"/>`;
  }
  return { P, faceL, faceR, box, roofX, roofY, cyl, mirror: m };
}
const S = shapes(P, false);
export const { faceL, faceR, box, roofX, roofY, cyl } = S;

export function win(q, frame = "#8a5d3b", { cross = true, cls = "tw-win" } = {}) {
  const g = inset(q, 0.22);
  return poly(q, frame) + poly(g, "var(--t-win)", ` class="${cls}"`)
    + (cross ? line(lerp(g[0], g[3], 0.5), lerp(g[1], g[2], 0.5), frame, 0.9) + line(lerp(g[0], g[1], 0.5), lerp(g[3], g[2], 0.5), frame, 0.9) : "")
    + line(lerp(g[3], g[2], 0.1), lerp(g[3], g[2], 0.45), "rgba(255,255,255,.55)", 0.8);
}
export function door(q, c = "#8a5536") {
  const k = lerp(lerp(q[1], q[2], 0.45), lerp(q[0], q[3], 0.45), 0.2);
  return poly(q, shade(c, -0.25)) + poly(inset(q, 0.14), c) + `<circle cx="${k[0]}" cy="${k[1]}" r="1" fill="#f3d27a"/>`;
}
export const shadow = (k = 1, dy = 2) => `<ellipse cx="0" cy="${dy}" rx="${r1(27 * k)}" ry="${r1(13.5 * k)}" fill="url(#@@sh)"/>`;
export const smoke = (p) => `<g class="tw-smoke" aria-hidden="true">${[0, 1, 2].map((i) => `<circle cx="${p[0]}" cy="${p[1]}" r="${2.6 + i * 0.6}" style="animation-delay:${i * 1.1}s"/>`).join("")}</g>`;

export const blob = (cx, cy, r, fill) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}"/>`;

// 给建筑文件用的一整套（draw(k, it, ctx) 里的 k）
export const KIT = { TW, TH, HW, HH, r1, pts, poly, line, shade, lerp, inset, win, door, shadow, smoke, blob, esc, ...S };
// 转过来的那一套：正方形的东西 rot=1 时用它画（x、y 对调 = 左右翻过来，光的方向不变）
export const KIT_TURNED = { ...KIT, ...shapes((x, y, z = 0) => P(y, x, z), true) };
