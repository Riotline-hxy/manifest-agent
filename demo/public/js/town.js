// 我的小镇：等距 2.5D 的小岛和建筑，全部是手写的 SVG（没有图片、没有引擎、没有滤镜）。
// 坐标：格子 (i, j) 的中心在 P(i, j)；每样东西在自己格子里用 -0.5..0.5 的本地坐标，z 是往上的像素高度。
// 光从左上来：顶面最亮、朝左下的面次之、朝右下的面最暗。深色氛围是夜里，窗户和路灯会亮（颜色走 town.css 的变量）。
// 渐变 id 带每次渲染自己的前缀：页面上同时有好几张小镇（面板缩略图、商店图标）也不会互相串。
import { esc } from "./ui.js";

export const TW = 64, TH = 32;
const HW = TW / 2, HH = TH / 2;
const r1 = (n) => Math.round(n * 10) / 10;
export const P = (x, y, z = 0) => [r1((x - y) * HW), r1((x + y) * HH - z)];
const pts = (l) => l.map((p) => p.join(",")).join(" ");
const poly = (l, fill, extra = "") => `<polygon points="${pts(l)}" fill="${fill}"${extra}/>`;
const line = (a, b, stroke, w = 1, extra = "") => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${stroke}" stroke-width="${w}" stroke-linecap="round"${extra}/>`;

// ---- 颜色：变亮往白，变暗往一点点偏紫的深色（比纯黑柔和，更像微缩模型） ----
const rgb = (h) => { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
export function shade(h, t) {
  const to = t > 0 ? [255, 252, 245] : [44, 34, 64], k = Math.abs(t);
  return "#" + rgb(h).map((c, i) => Math.round(c + (to[i] - c) * k).toString(16).padStart(2, "0")).join("");
}

// ---- 基本形 ----
const lerp = (a, b, t) => [r1(a[0] + (b[0] - a[0]) * t), r1(a[1] + (b[1] - a[1]) * t)];
function inset(q, k) {
  const c = [q.reduce((s, p) => s + p[0], 0) / q.length, q.reduce((s, p) => s + p[1], 0) / q.length];
  return q.map((p) => lerp(p, c, k));
}
// 朝左下的墙（y = b 那一面）和朝右下的墙（x = a 那一面）上的一块：左下、右下、右上、左上
const faceL = (b, x0, x1, z0, z1, ox = 0, oy = 0) => [P(ox + x0, oy + b, z0), P(ox + x1, oy + b, z0), P(ox + x1, oy + b, z1), P(ox + x0, oy + b, z1)];
const faceR = (a, y0, y1, z0, z1, ox = 0, oy = 0) => [P(ox + a, oy + y0, z0), P(ox + a, oy + y1, z0), P(ox + a, oy + y1, z1), P(ox + a, oy + y0, z1)];

function box({ x = 0, y = 0, a, b, z = 0, h, c, l, r, t, top = true }) {
  const Q = (u, v, w) => P(x + u, y + v, w);
  const z1 = z + h;
  return poly([Q(-a, b, z), Q(a, b, z), Q(a, b, z1), Q(-a, b, z1)], l || c)
    + poly([Q(a, -b, z), Q(a, b, z), Q(a, b, z1), Q(a, -b, z1)], r || shade(c, -0.2))
    + (top ? poly([Q(-a, -b, z1), Q(a, -b, z1), Q(a, b, z1), Q(-a, b, z1)], t || shade(c, 0.16)) : "");
}

// 两坡屋顶，屋脊沿 x：朝左下那面是正坡，山墙在右边。mid 是夹在后坡和前坡之间要画的东西（烟囱）
function roofX({ a, b, z, rise, o = 0.05, c, wall, mid = "" }) {
  const A = a + o, B = b + o;
  return poly([P(-A, -B, z), P(A, -B, z), P(A, 0, z + rise), P(-A, 0, z + rise)], shade(c, 0.14)) + mid
    + poly([P(a, -b, z), P(a, b, z), P(a, 0, z + rise)], wall)
    + poly([P(-A, 0, z + rise), P(A, 0, z + rise), P(A, B, z), P(-A, B, z)], c)
    + poly([P(-A, B, z), P(A, B, z), P(A, B, z - 2.5), P(-A, B, z - 2.5)], shade(c, -0.25))
    + poly([P(A, 0, z + rise), P(A, B, z), P(A, B, z - 2.5), P(A, 0, z + rise - 2.5)], shade(c, -0.35))
    + line(P(-A, 0, z + rise), P(A, 0, z + rise), shade(c, 0.3), 1.2);
}
// 屋脊沿 y：左坡朝着光，右坡背光，山墙朝左下
function roofY({ a, b, z, rise, o = 0.05, c, wall, mid = "" }) {
  const A = a + o, B = b + o;
  return poly([P(-A, -B, z), P(0, -B, z + rise), P(0, B, z + rise), P(-A, B, z)], shade(c, 0.12)) + mid
    + poly([P(0, -B, z + rise), P(A, -B, z), P(A, B, z), P(0, B, z + rise)], shade(c, -0.16))
    + poly([P(-a, b, z), P(a, b, z), P(0, b, z + rise)], wall)
    + `<polyline points="${pts([P(-A, B, z - 1), P(0, B, z + rise), P(A, B, z - 1)])}" fill="none" stroke="${shade(c, -0.3)}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>`;
}

function win(q, frame = "#8a5d3b", { cross = true, cls = "tw-win" } = {}) {
  const g = inset(q, 0.22);
  return poly(q, frame) + poly(g, "var(--t-win)", ` class="${cls}"`)
    + (cross ? line(lerp(g[0], g[3], 0.5), lerp(g[1], g[2], 0.5), frame, 0.9) + line(lerp(g[0], g[1], 0.5), lerp(g[3], g[2], 0.5), frame, 0.9) : "")
    + line(lerp(g[3], g[2], 0.1), lerp(g[3], g[2], 0.45), "rgba(255,255,255,.55)", 0.8);
}
function door(q, c = "#8a5536") {
  const k = lerp(lerp(q[1], q[2], 0.45), lerp(q[0], q[3], 0.45), 0.2);
  return poly(q, shade(c, -0.25)) + poly(inset(q, 0.14), c) + `<circle cx="${k[0]}" cy="${k[1]}" r="1" fill="#f3d27a"/>`;
}
const shadow = (k = 1, dy = 2) => `<ellipse cx="0" cy="${dy}" rx="${r1(27 * k)}" ry="${r1(13.5 * k)}" fill="url(#@@sh)"/>`;
const smoke = (p) => `<g class="tw-smoke" aria-hidden="true">${[0, 1, 2].map((i) => `<circle cx="${p[0]}" cy="${p[1]}" r="${2.6 + i * 0.6}" style="animation-delay:${i * 1.1}s"/>`).join("")}</g>`;

// 圆柱：底面中心 (x, y)，半径 r（格子单位），从 z 起高 h
function cyl({ x = 0, y = 0, r, z = 0, h, c, top }) {
  const [sx, sy] = P(x, y, 0), rx = r1(r * 0.7071 * TW), ry = r1(r * 0.7071 * TH), yb = r1(sy - z), yt = r1(sy - z - h);
  const side = `M${sx - rx},${yt} L${sx - rx},${yb} A${rx} ${ry} 0 0 0 ${sx + rx},${yb} L${sx + rx},${yt} Z`;
  return `<path d="${side}" fill="${c}"/><path d="${side}" fill="url(#@@cyl)"/>`
    + `<ellipse cx="${sx}" cy="${yt}" rx="${rx}" ry="${ry}" fill="${top || shade(c, 0.18)}"/>`;
}
const blob = (cx, cy, r, fill) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}"/>`;

// ---------------------------------------------------------------- 每样东西 ----
const ART = {
  cottage() {
    const a = 0.27, b = 0.25, h = 20, wall = "#f3dcb6";
    const ch = box({ x: -0.12, y: -0.1, a: 0.045, b: 0.045, z: h + 4, h: 15, c: "#b9705a" });
    return shadow(0.85)
      + box({ a, b, h, c: wall, r: shade(wall, -0.16) })
      + line(P(-a, b, 7), P(a, b, 7), "rgba(140,90,50,.18)") + line(P(-a, b, 13), P(a, b, 13), "rgba(140,90,50,.18)")
      + door(faceL(b, -0.06, 0.09, 0, 12.5))
      + win(faceR(a, -0.13, 0.07, 8, 15.5))
      + roofX({ a, b, z: h, rise: 15, c: "#d4664a", wall: shade(wall, -0.16), mid: ch })
      + smoke(P(-0.12, -0.1, h + 22));
  },
  house() {
    const a = 0.31, b = 0.27, h = 26, wall = "#f6f1e8";
    return shadow(0.98)
      + box({ x: 0, y: 0, a: a + 0.02, b: b + 0.02, h: 3, c: "#c9c2b6" })
      + box({ a, b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.14) })
      + door(faceL(b, 0.06, 0.2, 3, 16), "#4f78b8")
      + win(faceL(b, -0.23, -0.07, 11, 20), "#ffffff")
      + `<g>${[0, 1, 2, 3].map((i) => { const p = P(-0.21 + i * 0.045, b + 0.03, 10.5); return blob(p[0], p[1], 1.5, i % 2 ? "#ff8fb1" : "#ffd166"); }).join("")}</g>`
      + win(faceR(a, -0.18, -0.03, 11, 20), "#ffffff") + win(faceR(a, 0.05, 0.19, 11, 20), "#ffffff")
      + roofX({ a, b, z: h, rise: 17, c: "#5b8fd9", wall: shade(wall, -0.14) });
  },
  bakery() {
    const a = 0.31, b = 0.28, h = 24, wall = "#f7d9a8";
    const stripes = [];
    for (let i = 0; i < 6; i++) {
      const x0 = -0.27 + i * 0.09, x1 = x0 + 0.09;
      stripes.push(poly([P(x0, b, 17), P(x1, b, 17), P(x1, b + 0.13, 11), P(x0, b + 0.13, 11)], i % 2 ? "#fff6ea" : "#e0574f"));
    }
    const sp = P(a, 0.02, 15);
    const ch = box({ x: 0.1, y: -0.12, a: 0.045, b: 0.045, z: h + 3, h: 16, c: "#a66a52" });
    return shadow(0.98)
      + box({ a, b, h, c: wall, r: shade(wall, -0.17) })
      + win(faceL(b, -0.24, 0.04, 3, 14), "#9a6340", { cross: false })
      + `<g>${[[-0.2, 5.5], [-0.12, 5.5], [-0.04, 5.5]].map(([x, z]) => { const p = P(x, b + 0.01, z); return `<ellipse cx="${p[0]}" cy="${p[1]}" rx="3" ry="1.8" fill="#d99a4e"/>`; }).join("")}</g>`
      + door(faceL(b, 0.1, 0.24, 0, 13), "#9a6340")
      + stripes.join("")
      + `<circle cx="${sp[0]}" cy="${sp[1]}" r="5" fill="#fff6ea" stroke="#9a6340" stroke-width="1.2"/>`
      + `<path d="M${sp[0] - 3},${sp[1] + 0.6} q3,-4.5 6,0" fill="none" stroke="#d99a4e" stroke-width="2" stroke-linecap="round"/>`
      + roofY({ a, b, z: h, rise: 15, c: "#a8643f", wall: shade(wall, 0.02), mid: ch })
      + smoke(P(0.1, -0.12, h + 23));
  },
  cafe() {
    const a = 0.31, b = 0.29, h = 24, wall = "#9fd8c8";
    const aw = [];
    for (let i = 0; i < 6; i++) {
      const x0 = -0.28 + i * 0.093, x1 = x0 + 0.093;
      aw.push(poly([P(x0, b, 18), P(x1, b, 18), P(x1, b + 0.12, 13), P(x0, b + 0.12, 13)], i % 2 ? "#fffaf0" : "#3fa27f"));
    }
    const cup = P(a, 0, 16);
    return shadow(1)
      + box({ a, b, h, c: wall, r: shade(wall, -0.18) })
      + win(faceL(b, -0.25, 0.05, 2, 13), "#ffffff")
      + door(faceL(b, 0.1, 0.24, 0, 13), "#3f7f6c")
      + aw.join("")
      + win(faceR(a, -0.2, 0.0, 6, 14), "#ffffff", { cross: false })
      + `<g transform="translate(${cup[0] + 7},${cup[1] - 1})"><rect x="-4" y="-3" width="7" height="6" rx="1.5" fill="#fffaf0"/><path d="M3,-1.5 q2.5,1.5 0,3" fill="none" stroke="#fffaf0" stroke-width="1.2"/></g>`
      + box({ a: a + 0.02, b: b + 0.02, z: h, h: 3, c: "#f5efe3" })
      + box({ x: -0.1, y: -0.06, a: 0.12, b: 0.1, z: h + 3, h: 4, c: "#e8e0d0" })
      + box({ x: -0.2, y: b - 0.01, a: 0.1, b: 0.015, z: h + 3, h: 7, c: "#f5efe3" });
  },
  library() {
    const a = 0.35, b = 0.3, h = 28, wall = "#ece4d4";
    const cols = [-0.25, -0.12, 0.01, 0.14, 0.27].map((x) => poly(faceL(b + 0.03, x - 0.025, x + 0.025, 3, h - 2), "#fffdf7")).join("");
    return shadow(1.08)
      + box({ a: a + 0.04, b: b + 0.06, h: 3, c: "#c8bfae" })
      + box({ a, b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.16) })
      + poly(faceL(b + 0.002, -0.3, 0.32, 5, h - 3), shade(wall, -0.1))
      + win(faceL(b + 0.005, -0.21, -0.05, 9, 21), "#7a5a3a") + door(faceL(b + 0.005, 0.05, 0.19, 3, 18), "#6b4a8a")
      + cols
      + poly(faceL(b + 0.04, -a, a, h - 3, h), "#fffdf7")
      + win(faceR(a, -0.22, -0.04, 10, 21), "#7a5a3a") + win(faceR(a, 0.04, 0.22, 10, 21), "#7a5a3a")
      + roofX({ a, b: b + 0.04, z: h, rise: 11, o: 0.03, c: "#7d6cc9", wall: "#fffdf7" });
  },
  greenhouse() {
    const a = 0.32, b = 0.28, h = 20;
    const plants = [[-0.15, 0.05, "#5cb768"], [0.05, -0.08, "#ff8fb1"], [0.12, 0.1, "#5cb768"], [-0.05, 0.15, "#ffd166"]]
      .map(([x, y, c]) => { const p = P(x, y, 10); return blob(p[0], p[1], 5.5, c === "#5cb768" ? "url(#@@leaf)" : c) + blob(p[0] - 3, p[1] + 3, 4, "url(#@@leaf)"); }).join("");
    const grid = [];
    for (const x of [-0.16, 0, 0.16]) grid.push(line(P(x, b, 3), P(x, b, h), "#ffffff", 1, ' opacity=".8"'));
    for (const y of [-0.14, 0, 0.14]) grid.push(line(P(a, y, 3), P(a, y, h), "#ffffff", 1, ' opacity=".8"'));
    const A = a + 0.03, B = b + 0.03, z = h, rise = 13;
    return shadow(1)
      + box({ a: a + 0.02, b: b + 0.02, h: 3, c: "#c97c5d" })
      + plants
      + poly(faceL(b, -a, a, 3, h), "url(#@@glass)") + poly(faceR(a, -b, b, 3, h), "url(#@@glass)", ' opacity=".85"')
      + grid.join("")
      + poly([P(-A, 0, z + rise), P(A, 0, z + rise), P(A, B, z), P(-A, B, z)], "url(#@@glass)")
      + poly([P(a, -b, z), P(a, b, z), P(a, 0, z + rise)], "url(#@@glass)")
      + `<polyline points="${pts([P(-A, B, z), P(-A, 0, z + rise), P(A, 0, z + rise), P(A, B, z), P(-A, B, z)])}" fill="none" stroke="#ffffff" stroke-width="1.4" stroke-linejoin="round"/>`
      + line(P(a, -b, z), P(a, 0, z + rise), "#ffffff", 1.2) + line(P(0, 0, z + rise), P(0, B, z), "#ffffff", 1);
  },
  windmill() {
    const a0 = 0.24, a1 = 0.15, h = 40, wall = "#f4ead8";
    const L = [P(-a0, a0, 0), P(a0, a0, 0), P(a1, a1, h), P(-a1, a1, h)];
    const R = [P(a0, -a0, 0), P(a0, a0, 0), P(a1, a1, h), P(a1, -a1, h)];
    const hub = P(0.02, a1 + 0.06, h - 6);
    const blade = (deg) => `<g transform="rotate(${deg})"><rect x="-1.2" y="-27" width="2.4" height="27" fill="#8a5d3b"/><rect x="1.2" y="-26" width="6.5" height="19" fill="#fffaf0" stroke="#c9b79b" stroke-width=".8"/></g>`;
    return shadow(0.85)
      + poly(L, wall) + poly(R, shade(wall, -0.18))
      + door(faceL(a0 - 0.02, -0.06, 0.08, 0, 11), "#8a5d3b")
      + win([P(-0.05, a1 + 0.035, 22), P(0.06, a1 + 0.035, 22), P(0.06, a1 + 0.04, 29), P(-0.05, a1 + 0.04, 29)], "#8a5d3b", { cross: false })
      + roofY({ a: a1, b: a1, z: h, rise: 16, o: 0.04, c: "#c35b4e", wall: shade(wall, -0.04) })
      + `<g transform="matrix(.894 .447 0 1 ${hub[0]} ${hub[1]})"><g class="tw-blades">${[0, 90, 180, 270].map(blade).join("")}<circle r="2.6" fill="#6b4a33"/></g></g>`;
  },
  tower() {
    const c = "#e1d8c6";
    const [sx, sy] = P(0, 0, 0);
    const rx = r1(0.25 * 0.7071 * TW), yt = sy - 50;
    return shadow(0.8)
      + cyl({ r: 0.29, h: 6, c: "#c9bfae" })
      + cyl({ r: 0.25, z: 6, h: 44, c })
      + `<path d="M${sx - 4},${sy - 18} v-6 a4 4 0 0 1 8 0 v6 z" fill="#7a5a3a"/><path d="M${sx - 2.8},${sy - 18.5} v-5.2 a2.8 2.8 0 0 1 5.6 0 v5.2 z" fill="var(--t-win)" class="tw-win"/>`
      + `<path d="M${sx + 4},${sy - 34} v-5 a3.4 3.4 0 0 1 6.8 0 v5 z" fill="#7a5a3a"/><path d="M${sx + 5.1},${sy - 34.4} v-4.4 a2.3 2.3 0 0 1 4.6 0 v4.4 z" fill="var(--t-win)" class="tw-win"/>`
      + `<ellipse cx="${sx}" cy="${yt}" rx="${rx + 3}" ry="${r1(rx * 0.5 + 1.5)}" fill="#a99a80"/>`
      + `<path d="M${sx - rx},${yt} A${rx} ${rx * 0.9} 0 0 1 ${sx + rx},${yt} A${rx} ${rx * 0.5} 0 0 1 ${sx - rx},${yt}Z" fill="url(#@@dome)"/>`
      + `<path d="M${sx - 3},${yt - rx * 0.88} A${rx * 0.4} ${rx * 0.9} 0 0 0 ${sx - 3},${yt + rx * 0.48}" fill="none" stroke="rgba(255,255,255,.28)" stroke-width="3"/>`
      + `<rect x="${sx + 2}" y="${yt - rx * 0.55}" width="13" height="4" rx="2" fill="#4a4f63" transform="rotate(-28 ${sx + 2} ${yt - rx * 0.4})"/>`
      + `<path class="tw-twinkle" d="M${sx + 18},${yt - 22} l1.4,3.2 3.2,1.4 -3.2,1.4 -1.4,3.2 -1.4,-3.2 -3.2,-1.4 3.2,-1.4z" fill="#ffe08a"/>`;
  },
  tree() {
    return shadow(0.62, 3) + box({ a: 0.05, b: 0.05, h: 13, c: "#9a6b4b" })
      + `<g class="tw-sway">${blob(-8, -20, 10, "url(#@@leaf)")}${blob(8, -22, 11, "url(#@@leaf)")}${blob(0, -30, 14, "url(#@@leaf)")}
        <ellipse cx="-5" cy="-37" rx="5" ry="3" fill="rgba(255,255,255,.28)"/></g>`;
  },
  pine() {
    const tier = (yb, w, ht) => `<path d="M0,${yb - ht} L${-w},${yb} L0,${yb + w * 0.32} Z" fill="#62ad72"/><path d="M0,${yb - ht} L${w},${yb} L0,${yb + w * 0.32} Z" fill="#3e8458"/>`;
    return shadow(0.55, 3) + box({ a: 0.04, b: 0.04, h: 9, c: "#8a5d3b" })
      + `<g class="tw-sway">${tier(-8, 15, 18)}${tier(-19, 12, 17)}${tier(-29, 8.5, 15)}</g>`;
  },
  bush() {
    return shadow(0.5, 2) + blob(-6, -5, 7, "url(#@@leaf)") + blob(6, -5, 7.5, "url(#@@leaf)") + blob(0, -10, 8.5, "url(#@@leaf)")
      + blob(-3, -12, 1.6, "#ff6b6b") + blob(5, -7, 1.6, "#ff6b6b") + blob(-7, -4, 1.4, "#ff6b6b")
      + `<ellipse cx="-3" cy="-14" rx="3.5" ry="2" fill="rgba(255,255,255,.25)"/>`;
  },
  flowers() {
    const spots = [[-10, 0, "#ff8fb1"], [-3, -4, "#ffd166"], [5, -2, "#ffffff"], [11, 1, "#b9a7ff"], [-5, 4, "#ffd166"], [3, 5, "#ff8fb1"], [9, -5, "#ff8fb1"]];
    return `<ellipse cx="0" cy="1" rx="17" ry="8.5" fill="#6fbe63" opacity=".55"/>`
      + spots.map(([x, y, c]) => `${line([x, y + 1], [x, y - 5], "#4f9a52", 1.2)}<circle cx="${x}" cy="${y - 6}" r="2.6" fill="${c}"/><circle cx="${x}" cy="${y - 6}" r="1" fill="#f7b93a"/>`).join("");
  },
  sakura() {
    const petal = (x, d) => `<ellipse class="tw-petal" cx="${x}" cy="-24" rx="1.6" ry="1.1" fill="#ffc0d3" style="animation-delay:${d}s"/>`;
    return shadow(0.62, 3)
      + `<path d="M-2,2 Q-1,-8 -4,-14 M0,-9 Q4,-14 6,-18" stroke="#8a5d4b" stroke-width="3.2" fill="none" stroke-linecap="round"/>`
      + `<g class="tw-sway">${blob(-9, -20, 10, "url(#@@pink)")}${blob(8, -23, 10.5, "url(#@@pink)")}${blob(-1, -31, 13, "url(#@@pink)")}
        <ellipse cx="-5" cy="-37" rx="5" ry="3" fill="rgba(255,255,255,.35)"/></g>` + petal(-6, 0) + petal(7, 1.8) + petal(1, 3.4);
  },
  pond() {
    const stones = [];
    for (let k = 0; k < 11; k++) {
      const t = (k / 11) * Math.PI * 2;
      stones.push(`<ellipse cx="${r1(Math.cos(t) * 24)}" cy="${r1(Math.sin(t) * 11.6)}" rx="4.2" ry="2.6" fill="${k % 2 ? "#cfc7b7" : "#bdb4a3"}"/>`);
    }
    return `<ellipse cx="0" cy="0" rx="26" ry="12.8" fill="#a99f8c"/>` + stones.join("")
      + `<ellipse cx="0" cy="0" rx="21.5" ry="10" fill="url(#@@water)"/>`
      + `<path class="tw-water" d="M-11,-2 q4,-2 8,0 M3,3 q4,-2 8,0" fill="none" stroke="rgba(255,255,255,.7)" stroke-width="1.2" stroke-linecap="round"/>`
      + `<path d="M6,-3 a5 2.6 0 1 0 0.1,0 l-2.5,1.6z" fill="#5cb768"/><circle cx="8" cy="-4.5" r="1.6" fill="#ff8fb1"/>`;
  },
  road() { return ""; },   // 路画在地面那一层（roadsSVG），这里只占格子
  lamp() {
    const top = P(0, 0, 30);
    return shadow(0.28, 1.5)
      + `<circle class="tw-glow" cx="${top[0]}" cy="${top[1] + 3}" r="16" fill="url(#@@glow)"/>`
      + box({ a: 0.035, b: 0.035, h: 4, c: "#4a4f63" }) + box({ a: 0.016, b: 0.016, z: 4, h: 22, c: "#585e75" })
      + box({ a: 0.055, b: 0.055, z: 26, h: 7, c: "#fff1bf", l: "var(--t-win)", r: "var(--t-win)", t: "#fff7da" })
      + `<path d="M${top[0] - 6},${top[1] - 3} L${top[0]},${top[1] - 9} L${top[0] + 6},${top[1] - 3} Z" fill="#4a4f63"/>`;
  },
  bench() {
    const wood = "#c98a4e";
    return shadow(0.5, 1.5)
      + box({ x: -0.18, y: 0, a: 0.02, b: 0.06, h: 6, c: "#585e75" }) + box({ x: 0.18, y: 0, a: 0.02, b: 0.06, h: 6, c: "#585e75" })
      + box({ x: 0, y: -0.06, a: 0.24, b: 0.012, z: 6, h: 9, c: shade(wood, -0.05) })
      + box({ a: 0.24, b: 0.08, z: 6, h: 2, c: wood });
  },
  mailbox() {
    const p = P(0, 0, 22);
    return shadow(0.3, 1.5) + box({ a: 0.025, b: 0.025, h: 14, c: "#585e75" })
      + box({ a: 0.08, b: 0.06, z: 14, h: 9, c: "#e0574f" })
      + `<ellipse cx="${p[0] + 0.7}" cy="${p[1] + 0.5}" rx="5.6" ry="3" fill="${shade("#e0574f", 0.15)}"/>`
      + poly(faceL(0.061, -0.05, 0.03, 18, 19.6), "#7a2b26")
      + `<rect x="${p[0] + 5}" y="${p[1] - 2}" width="1.2" height="7" fill="#ffd166"/><rect x="${p[0] + 5}" y="${p[1] - 2}" width="4" height="2.6" fill="#ffd166"/>`;
  },
  fountain() {
    const [sx, sy] = P(0, 0, 0);
    const spray = (d) => `<path class="tw-spray" d="M${sx},${sy - 22} q${d * 8},-6 ${d * 14},12" fill="none" stroke="#bfe6ff" stroke-width="1.6" stroke-linecap="round"/>`;
    return shadow(1, 2)
      + cyl({ r: 0.4, h: 7, c: "#cfd6e0" })
      + `<ellipse cx="${sx}" cy="${sy - 7}" rx="${r1(0.34 * 0.7071 * TW)}" ry="${r1(0.34 * 0.7071 * TH)}" fill="url(#@@water)"/>`
      + `<path class="tw-water" d="M${sx - 10},${sy - 6} q4,-2 8,0 M${sx + 3},${sy - 9} q4,-2 8,0" fill="none" stroke="rgba(255,255,255,.7)" stroke-width="1.1" stroke-linecap="round"/>`
      + cyl({ r: 0.05, z: 7, h: 12, c: "#dde3ec" })
      + `<ellipse cx="${sx}" cy="${sy - 19}" rx="8" ry="3.4" fill="#cfd6e0"/><ellipse cx="${sx}" cy="${sy - 19.6}" rx="6.4" ry="2.4" fill="url(#@@water)"/>`
      + spray(-1) + spray(1) + `<circle class="tw-spray" cx="${sx}" cy="${sy - 25}" r="1.6" fill="#dff3ff"/>`;
  },
  sign(it, ctx) {
    const name = (ctx?.name || "我的小镇").slice(0, 5);
    return shadow(0.45, 1.5) + box({ x: -0.14, a: 0.018, b: 0.018, h: 20, c: "#8a5d3b" }) + box({ x: 0.14, a: 0.018, b: 0.018, h: 20, c: "#8a5d3b" })
      + `<g transform="translate(0,-21)"><rect x="-21" y="-9" width="42" height="15" rx="3.5" fill="#a8744c"/><rect x="-19" y="-7.5" width="38" height="12" rx="2.5" fill="#e7c48f"/>
        <text x="0" y="1.6" text-anchor="middle" font-size="${name.length > 4 ? 6.4 : 7.6}" font-weight="800" fill="#6b4529">${esc(name)}</text></g>`;
  },
  arch() {
    // 两根柱子 + 一道半圆，立在朝左下的那个面里；花沿着拱一路开过去
    const arc = [];
    for (let k = 0; k <= 12; k++) {
      const t = Math.PI * (1 - k / 12);
      arc.push(P(0.21 * Math.cos(t), 0.02, 21 + 10 * Math.sin(t)));
    }
    const flowers = arc.filter((_, k) => k % 2 === 0).map((q, k) => blob(q[0], q[1], 3.2, ["#ff8fb1", "#fff4f7", "#ffd166"][k % 3])).join("");
    const leaves = arc.filter((_, k) => k % 2).map((q) => blob(q[0], q[1] + 1, 2.6, "#5cb768")).join("");
    return shadow(0.5, 1.5)
      + box({ x: -0.21, y: 0.02, a: 0.025, b: 0.025, h: 22, c: "#f1e6d2" }) + box({ x: 0.21, y: 0.02, a: 0.025, b: 0.025, h: 22, c: "#f1e6d2" })
      + `<polyline points="${pts(arc)}" fill="none" stroke="#e9dcc4" stroke-width="3.4" stroke-linecap="round"/>`
      + `<polyline points="${pts(arc)}" fill="none" stroke="#fff8ec" stroke-width="1.2" stroke-linecap="round" opacity=".8"/>`
      + leaves + flowers
      + blob(P(-0.21, 0.04, 2)[0], P(-0.21, 0.04, 2)[1], 4, "url(#@@leaf)") + blob(P(0.21, 0.04, 2)[0], P(0.21, 0.04, 2)[1], 4, "url(#@@leaf)");
  },
  balloon() {
    // 飘在自己那格上空：影子留在地上，球和吊篮一起慢慢上下。竖条纹用 clipPath 裁进球皮里
    const cy = -60;
    const shape = `M-16,${cy} A16 18 0 1 1 16,${cy} Q14,${cy + 10} 5,${cy + 19} L-5,${cy + 19} Q-14,${cy + 10} -16,${cy} Z`;
    const bands = ["#ff8a65", "#ffd166", "#ff8a65", "#7fd3c4", "#ff8a65", "#ffd166"]
      .map((c, k) => `<rect x="${-16 + k * 5.4}" y="${cy - 20}" width="5.6" height="40" fill="${c}"/>`).join("");
    return `<ellipse cx="0" cy="2" rx="12" ry="5.5" fill="url(#@@sh)" opacity=".7"/>`
      + `<g class="tw-float"><clipPath id="@@bl"><path d="${shape}"/></clipPath>`
      + `<g clip-path="url(#@@bl)">${bands}<rect x="-16" y="${cy - 20}" width="32" height="40" fill="url(#@@cyl)"/></g>`
      + `<path d="M-5,${cy + 19} L-4,${cy + 27} M5,${cy + 19} L4,${cy + 27}" stroke="#8a5d3b" stroke-width=".9"/>`
      + `<rect x="-5" y="${cy + 26}" width="10" height="7" rx="1.6" fill="#b27a4a"/><rect x="-5" y="${cy + 26}" width="10" height="2" rx="1" fill="#d39a62"/>`
      + `<ellipse cx="-7" cy="${cy - 9}" rx="3.6" ry="6" fill="rgba(255,255,255,.32)"/></g>`;
  },
  clocktower() {
    const a = 0.2, b = 0.2, h = 54, wall = "#e9dfcd";
    const face = (z0) => {   // 钟面贴在朝左下的墙上：在墙的平面里画一个圆
      const ring = [];
      for (let k = 0; k < 20; k++) {
        const t = (k / 20) * Math.PI * 2;
        ring.push(P(Math.cos(t) * 0.13, b + 0.005, z0 + Math.sin(t) * 6.6));
      }
      const c = P(0, b + 0.005, z0), up = P(0, b + 0.005, z0 + 4.6), side = P(0.08, b + 0.005, z0);
      return `<polygon points="${pts(ring)}" fill="#fffaf0" stroke="#8a6a3c" stroke-width="1.4"/>`
        + line(c, up, "#4a3a2a", 1.3) + line(c, side, "#4a3a2a", 1.3) + `<circle cx="${c[0]}" cy="${c[1]}" r="1" fill="#4a3a2a"/>`;
    };
    return shadow(0.66)
      + box({ a: a + 0.04, b: b + 0.04, h: 5, c: "#cbbfa9" })
      + box({ a, b, z: 5, h: h - 5, c: wall, r: shade(wall, -0.17) })
      + door(faceL(b, -0.06, 0.07, 5, 16), "#7a5236")
      + win(faceR(a, -0.07, 0.07, 22, 32), "#8a6a3c", { cross: false })
      + face(h - 12)
      + box({ a: a + 0.02, b: b + 0.02, z: h, h: 3, c: "#d6c9b1" })
      + poly([P(-a - 0.02, b + 0.02, h + 3), P(a + 0.02, b + 0.02, h + 3), P(0, 0, h + 27)], "#5e7fc9")
      + poly([P(a + 0.02, -b - 0.02, h + 3), P(a + 0.02, b + 0.02, h + 3), P(0, 0, h + 27)], shade("#5e7fc9", -0.2))
      + line(P(0, 0, h + 27), P(0, 0, h + 34), "#8a6a3c", 1.2) + `<path d="M${P(0, 0, h + 34)[0]},${P(0, 0, h + 34)[1]} l7,2 -7,2z" fill="#ff8a65"/>`;
  },
  monument() {
    const top = P(0, 0, 33);
    return shadow(0.55, 2)
      + box({ a: 0.17, b: 0.17, h: 5, c: "#c9c3d6" }) + box({ a: 0.11, b: 0.11, z: 5, h: 4, c: "#dcd6e6" })
      + poly([P(-0.07, 0.07, 9), P(0.07, 0.07, 9), P(0.035, 0.035, 30), P(-0.035, 0.035, 30)], "#ece7f3")
      + poly([P(0.07, -0.07, 9), P(0.07, 0.07, 9), P(0.035, 0.035, 30), P(0.035, -0.035, 30)], "#c9c1d9")
      + `<path class="tw-twinkle" d="M${top[0]},${top[1] - 6} l1.8,4 4,1.8 -4,1.8 -1.8,4 -1.8,-4 -4,-1.8 4,-1.8z" fill="#ffd166"/>`;
  },
};

const FLAT = new Set(["road", "pond"]);

// ---------------------------------------------------------------- 整座小镇 ----
let seq = 0;
const hash = (i, j) => { let h = (i * 374761393 + j * 668265263) >>> 0; h = (h ^ (h >>> 13)) * 1274126177 >>> 0; return (h % 1000) / 1000; };

function defs(id) {
  return `<defs>
    <radialGradient id="${id}leaf" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#a8e38e"/><stop offset=".55" stop-color="#5cb768"/><stop offset="1" stop-color="#2f7d4f"/></radialGradient>
    <radialGradient id="${id}pink" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#ffe6ee"/><stop offset=".55" stop-color="#f7a9c2"/><stop offset="1" stop-color="#d9789b"/></radialGradient>
    <radialGradient id="${id}sh" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#1c1430" stop-opacity=".32"/><stop offset="1" stop-color="#1c1430" stop-opacity="0"/></radialGradient>
    <radialGradient id="${id}glow" cx=".5" cy=".5" r=".5"><stop offset="0" style="stop-color:var(--t-win)" stop-opacity=".75"/><stop offset="1" style="stop-color:var(--t-win)" stop-opacity="0"/></radialGradient>
    <linearGradient id="${id}water" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#aee4ff"/><stop offset="1" stop-color="#4b9fdc"/></linearGradient>
    <linearGradient id="${id}glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e6f8ff" stop-opacity=".7"/><stop offset="1" stop-color="#8ccbe8" stop-opacity=".42"/></linearGradient>
    <linearGradient id="${id}cyl" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#1c1430" stop-opacity=".24"/></linearGradient>
    <linearGradient id="${id}dome" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a99bff"/><stop offset="1" stop-color="#5a4bc0"/></linearGradient>
  </defs>`;
}

const tile = (i, j, k = 0.5) => [P(i - k, j - k), P(i + k, j - k), P(i + k, j + k), P(i - k, j + k)];

function roadsSVG(roads) {
  const has = (i, j) => roads.has(i + "," + j);
  const parts = (i, j) => {
    const w = 0.29, out = [[-w, w, -w, w]];
    if (has(i + 1, j)) out.push([0, 0.5, -w, w]);
    if (has(i - 1, j)) out.push([-0.5, 0, -w, w]);
    if (has(i, j + 1)) out.push([-w, w, 0, 0.5]);
    if (has(i, j - 1)) out.push([-w, w, -0.5, 0]);
    return out;
  };
  const quad = (i, j, [x0, x1, y0, y1], g) => [P(i + x0 - g, j + y0 - g), P(i + x1 + g, j + y0 - g), P(i + x1 + g, j + y1 + g), P(i + x0 - g, j + y1 + g)];
  let edge = "", fill = "", stones = "";
  for (const k of roads) {
    const [i, j] = k.split(",").map(Number);
    for (const r of parts(i, j)) { edge += poly(quad(i, j, r, 0.045), "var(--t-path-edge)"); fill += poly(quad(i, j, r, 0), "var(--t-path)"); }
    for (let s = 0; s < 3; s++) {
      const p = P(i + (hash(i + s, j) - 0.5) * 0.4, j + (hash(i, j + s * 7) - 0.5) * 0.4);
      stones += `<ellipse cx="${p[0]}" cy="${p[1]}" rx="3.2" ry="1.6" fill="var(--t-path-stone)"/>`;
    }
  }
  return `<g class="tw-roads">${edge}${fill}${stones}</g>`;
}

// 每样东西大概高出地面多少（像素），用来算小镇上方要留多少天空
const HEIGHT = { cottage: 44, house: 48, bakery: 44, cafe: 36, library: 44, greenhouse: 38, windmill: 70, tower: 82, tree: 46, pine: 48,
  sakura: 48, lamp: 40, bench: 18, mailbox: 28, fountain: 30, sign: 32, monument: 42, flowers: 12, bush: 20,
  arch: 36, balloon: 82, clocktower: 96 };
export function headroom(t) {
  let top = 24;
  for (const it of t.items || []) top = Math.max(top, (HEIGHT[it.kind] || 0) - (it.x + it.y) * HH + 6);
  return Math.min(118, Math.ceil(top));
}

export function townBox(n, { top = 118 } = {}) {
  return [-n * HW - 26, -HH - top, n * TW + 52, n * TH + top + 52];
}

// 一样东西的图（商店、仓库、弹层里用）：小块地 + 它自己
export function itemArt(kind, { name = "", cls = "" } = {}) {
  const id = `ti${++seq}-`;
  const ground = kind === "road"
    ? roadsSVG(new Set(["0,0"]))
    : poly(tile(0, 0, 0.46), "var(--t-grass-a)") + poly([P(-0.46, 0.46), P(0.46, 0.46), P(0.46, 0.46, -5), P(-0.46, 0.46, -5)], "var(--t-soil-a)")
      + poly([P(0.46, -0.46), P(0.46, 0.46), P(0.46, 0.46, -5), P(0.46, -0.46, -5)], "var(--t-soil-b)");
  const art = (ART[kind] || ART.bush)({}, { name });
  const h = Math.max(14, HEIGHT[kind] || 0);   // 矮的东西不留一大片空
  return `<svg class="town-svg item-art ${cls}" viewBox="-38 ${-(h + 16)} 76 ${h + 42}" preserveAspectRatio="xMidYMax meet" aria-hidden="true">${defs(id)}${ground}<g class="tw-body">${art.replaceAll("@@", id)}</g></svg>`;
}

// 偷懒日的小插画：夜里亮着灯的小木屋
export function napSVG() {
  const id = `tn${++seq}-`;
  return `<svg class="town-svg nap-art tw-night" viewBox="-44 -84 88 104" aria-hidden="true">${defs(id)}
    <path d="M30,-74 a9 9 0 1 0 6,15 a7 7 0 1 1 -6,-15z" fill="#ffe7a3"/>
    <path class="tw-twinkle" d="M-26,-70 l1,2.3 2.3,1 -2.3,1 -1,2.3 -1,-2.3 -2.3,-1 2.3,-1z" fill="#fff3c4"/>
    ${poly(tile(0, 0, 0.5), "var(--t-grass-a)")}${poly([P(-0.5, 0.5), P(0.5, 0.5), P(0.5, 0.5, -6), P(-0.5, 0.5, -6)], "var(--t-soil-a)")}
    ${poly([P(0.5, -0.5), P(0.5, 0.5), P(0.5, 0.5, -6), P(0.5, -0.5, -6)], "var(--t-soil-b)")}
    <g class="tw-body">${ART.cottage().replaceAll("@@", id)}</g>
    <g class="zzz"><text x="-30" y="-50">z</text><text x="-22" y="-60">z</text><text x="-12" y="-70">Z</text></g></svg>`;
}

/**
 * 整座小镇的 SVG。
 * t：bootstrap 里的 town；ghost：{kind, x, y, ok, name}（放置时的预览）；grid：放置时显示格子；
 * still：静态（缩略图，不动）；fresh：刚建好的那一个 id（落下来的动画）；hide：正在挪的那一个 id。
 */
export function townSVG(t, { ghost = null, grid = false, still = false, fresh = "", hide = "", cls = "", top = headroom(t) } = {}) {
  const id = `tw${++seq}-`;
  const n = t.size;
  const items = (t.items || []).filter((it) => it.id !== hide);
  const roads = new Set(items.filter((it) => it.kind === "road").map((it) => it.x + "," + it.y));
  const taken = new Set(items.map((it) => it.x + "," + it.y));
  const [bx, by, bw, bh] = townBox(n, { top });
  const D = 22;
  let g = "";
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    g += poly(tile(i, j), (i + j) % 2 ? "var(--t-grass-b)" : "var(--t-grass-a)");
    if (!taken.has(i + "," + j) && hash(i, j) > 0.62) {   // 空地上的几簇小草，让地看起来是活的
      const p = P(i + (hash(j, i) - 0.5) * 0.5, j + (hash(i + 3, j) - 0.5) * 0.5);
      g += `<path d="M${p[0] - 3},${p[1]} l1.2,-3.6 M${p[0]},${p[1]} l0,-4.4 M${p[0] + 3},${p[1]} l-1.2,-3.6" stroke="var(--t-tuft)" stroke-width="1.3" stroke-linecap="round"/>`;
    }
  }
  const e = n - 0.5, s = -0.5;
  const sides = poly([P(s, e), P(e, e), P(e, e, -D), P(s, e, -D)], "var(--t-soil-a)")
    + poly([P(e, s), P(e, e), P(e, e, -D), P(e, s, -D)], "var(--t-soil-b)")
    + poly([P(s, e), P(e, e), P(e, e, -4), P(s, e, -4)], "var(--t-lip)") + poly([P(e, s), P(e, e), P(e, e, -4), P(e, s, -4)], "var(--t-lip-2)")
    + `<g class="tw-strata">${[9, 15].map((z) => line(P(s, e, -z), P(e, e, -z), "rgba(0,0,0,.08)", 1.5) + line(P(e, s, -z), P(e, e, -z), "rgba(0,0,0,.08)", 1.5)).join("")}</g>`;
  const under = `<ellipse cx="0" cy="${(n - 1) * HH + D * 0.7}" rx="${n * HW + 8}" ry="${n * HH + 6}" fill="url(#${id}sh)" opacity=".75"/>`;
  const gridSVG = grid ? `<g class="tw-grid">${Array.from({ length: n * n }, (_, k) => poly(tile(Math.floor(k / n), k % n, 0.47), "none")).join("")}</g>` : "";
  const mark = ghost ? poly(tile(ghost.x, ghost.y, 0.47), ghost.ok ? "var(--t-ok)" : "var(--t-bad)", ' class="tw-mark"') : "";
  const order = items.filter((it) => !FLAT.has(it.kind)).sort((a, b) => a.x + a.y - (b.x + b.y) || a.x - b.x);
  const piece = (it, extra = "") => {
    const [sx, sy] = P(it.x, it.y);
    return `<g class="ti ${it.id === fresh ? "drop" : ""} ${extra}" data-id="${esc(it.id)}" transform="translate(${sx},${sy})"><g class="tw-body">${(ART[it.kind] || ART.bush)(it, { name: t.name })}</g></g>`;
  };
  const ponds = items.filter((it) => it.kind === "pond").map((it) => piece(it)).join("");
  const ghostSVG = ghost ? piece({ id: "ghost", kind: ghost.kind, x: ghost.x, y: ghost.y }, `ghost ${ghost.ok ? "ok" : "bad"}`) : "";
  const body = `${defs(id)}${under}${sides}<g class="tw-ground">${g}</g>${roadsSVG(roads)}${ghost?.kind === "road" && ghost.ok ? roadsSVG(new Set([ghost.x + "," + ghost.y])) : ""}${gridSVG}${mark}${ponds}${order.map((it) => piece(it)).join("")}${ghostSVG}`;
  return `<svg class="town-svg ${still ? "still" : ""} ${cls}" viewBox="${bx} ${by} ${bw} ${bh}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(t.name)}，${n}×${n} 的地，${items.length} 样东西">${body.replaceAll("@@", id)}</svg>`;
}

// 屏幕上的一点落在哪一格
export function cellAt(svg, clientX, clientY) {
  const m = svg?.getScreenCTM?.();
  if (!m) return null;
  const pt = svg.createSVGPoint();
  pt.x = clientX; pt.y = clientY;
  const p = pt.matrixTransform(m.inverse());
  const u = p.x / HW, v = p.y / HH;
  return { x: Math.round((v + u) / 2), y: Math.round((v - u) / 2) };
}

// 一格在屏幕上的位置（放彩纸、对准气泡用）
export function cellPoint(svg, x, y, z = 14) {
  const m = svg?.getScreenCTM?.();
  if (!m) return null;
  const pt = svg.createSVGPoint();
  [pt.x, pt.y] = P(x, y, z);
  const p = pt.matrixTransform(m);
  return { x: p.x, y: p.y };
}

export const COIN_SVG = `<svg class="coin-ic" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10.6" r="8" fill="#d99a1c"/><circle cx="10" cy="9.4" r="8" fill="#ffd24a"/><circle cx="10" cy="9.4" r="5.6" fill="none" stroke="#e8a92a" stroke-width="1.4"/><path d="M6.4 6.2a4.6 4.6 0 0 1 4.2-1.6" stroke="#fff6cf" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`;

// ---------------------------------------------------------------- 说给 TA 听的一句 ----
const GIFT_NAME = { sign: "小镇路牌", monument: "纪念碑" };
export const itemName = (t, kind) => (t.catalog || []).find((c) => c.id === kind)?.name || GIFT_NAME[kind] || kind;
const catOfKind = (t, kind) => (t.catalog || []).find((c) => c.id === kind)?.cat || "decor";
export const affordable = (t, coins) => (t.catalog || []).filter((c) => c.unlocked && c.cat === "build" && c.price <= coins)
  .sort((a, b) => b.price - a.price);
export const builtCount = (t) => (t.items || []).filter((i) => catOfKind(t, i.kind) === "build").length;

// 面板入口下面那一行小字
export function townHint(t, g) {
  const coins = g?.coins ?? t.coins;
  const can = affordable(t, coins).find((c) => !(t.items || []).some((i) => i.kind === c.id)) || affordable(t, coins)[0];
  if (!builtCount(t) && !can) return "做完一件小事，就能盖第一栋小木屋";
  if (can) return `金币够盖「${can.name}」了`;
  if (t.next) return `Lv${t.next.lv} 解锁${t.next.items[0] ? `「${t.next.items[0]}」` : ` ${t.next.land}×${t.next.land} 的地`}`;
  return "去看看你的小镇";
}

// 小镇里小光的气泡：只说真实的数字和真实的故事
export function guideLines(t, g) {
  const out = [];
  const list = affordable(t, g.coins);
  const can = list.find((c) => !(t.items || []).some((i) => i.kind === c.id)) || list[0];
  if (!builtCount(t) && !can) out.push("做完一件小事，比如一个小步或一次打卡，就能盖第一栋小木屋。");
  if (can) out.push(`金币够盖「${can.name}」了。想把它放在哪儿？`);
  if (t.next) {
    const need = Math.max(1, t.next.xp - g.total);
    out.push(`再 ${need} 经验到 Lv${t.next.lv}，会解锁${t.next.items.length ? t.next.items.map((x) => `「${x}」`).join("") : ""}${t.next.land ? `${t.next.items.length ? "，还有" : ""} ${t.next.land}×${t.next.land} 的地` : ""}。`);
  }
  for (const i of (t.items || []).filter((x) => x.story?.text && x.kind !== "road").slice(-3).reverse()) {
    out.push(i.kind === "monument" ? `这块纪念碑上刻着「${i.note}」。` : `「${i.name}」是你${i.story.text}之后盖的。`);
  }
  if ((t.warehouse || []).length) out.push(`仓库里还有 ${t.warehouse.length} 样东西。`);
  if (out.length < 2) out.push("小镇一直在这儿，不着急。");
  return out;
}
