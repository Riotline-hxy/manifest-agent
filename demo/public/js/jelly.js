// 小光的果冻形象：形状 / 颜色 / 质感 / 表情 / 动作，全部在一个 SVG 里用弹簧驱动。
// 设计稿（creative/jelly-hex/index.html）和网页 App 共用这一份代码。
// 性能：没有模糊滤镜；轮廓只在变形、捏的时候重算；平时每帧只改少量 transform；
// 静止的实例会休眠（awake = false），只有 alive 的实例有呼吸、眨眼、视线。
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const rad = d => d * Math.PI / 180;
const f1 = n => (Math.round(n * 10) / 10);
const f3 = n => (Math.round(n * 1000) / 1000);
const op = n => (Math.round(clamp(n, 0, 1) * 100) / 100);
const YB = 114, K = 84, RS = 98, RV = 60;

class Spring {
  constructor(v, k, c) { this.v = v; this.t = v; this.vel = 0; this.k = k; this.c = c; }
  step(dt) { this.vel += (this.k * (this.t - this.v) - this.c * this.vel) * dt; this.v += this.vel * dt; }
  get still() { return Math.abs(this.t - this.v) < .002 && Math.abs(this.vel) < .01; }
}

/* ---------- shapes: one outline of K points, any shape morphs into any other ---------- */
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]], add = (a, b) => [a[0] + b[0], a[1] + b[1]], mul = (a, s) => [a[0] * s, a[1] * s];
const nrm = a => { const l = Math.hypot(a[0], a[1]) || 1; return [a[0] / l, a[1] / l]; };
const ngon = (n, r, a0) => Array.from({ length: n }, (_, i) => { const a = rad(a0 + 360 / n * i); return [r * Math.cos(a), r * Math.sin(a)]; });
function roundedPoly(verts, r, seg = 16) {
  const out = [], n = verts.length;
  for (let i = 0; i < n; i++) {
    const V = verts[i], d1 = nrm(sub(verts[(i + n - 1) % n], V)), d2 = nrm(sub(verts[(i + 1) % n], V));
    const ang = Math.acos(clamp(d1[0] * d2[0] + d1[1] * d2[1], -1, 1));
    const C = add(V, mul(nrm(add(d1, d2)), r / Math.sin(ang / 2)));
    const T1 = add(V, mul(d1, r / Math.tan(ang / 2))), T2 = add(V, mul(d2, r / Math.tan(ang / 2)));
    const a1 = Math.atan2(T1[1] - C[1], T1[0] - C[0]); let da = Math.atan2(T2[1] - C[1], T2[0] - C[0]) - a1;
    while (da <= -Math.PI) da += TAU; while (da > Math.PI) da -= TAU;
    for (let k = 0; k <= seg; k++) { const a = a1 + da * k / seg; out.push([C[0] + r * Math.cos(a), C[1] + r * Math.sin(a)]); }
  }
  return out;
}
const param = f => Array.from({ length: 240 }, (_, i) => f(-Math.PI / 2 + TAU * i / 240));
const polar = f => param(t => { const r = f(t); return [r * Math.cos(t), r * Math.sin(t)]; });
const superellipse = (a, b, n) => param(t => { const c = Math.cos(t), s = Math.sin(t); return [a * Math.sign(c) * Math.abs(c) ** (2 / n), b * Math.sign(s) * Math.abs(s) ** (2 / n)]; });
function finishShape(poly, puff = 0) {
  let area = 0;
  for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; area += a[0] * b[1] - b[0] * a[1]; }
  if (area < 0) poly = poly.slice().reverse();
  if (puff) { const rm = Math.max(...poly.map(p => Math.hypot(p[0], p[1]))); poly = poly.map(p => mul(p, 1 + puff * (rm / Math.hypot(p[0], p[1]) - 1))); }
  let s = 0, best = 1e9;
  poly.forEach((p, i) => { if (p[1] < 0) { const d = Math.abs(Math.atan2(p[1], p[0]) + Math.PI / 2); if (d < best) { best = d; s = i; } } });
  poly = poly.slice(s).concat(poly.slice(0, s));
  const L = [0]; for (let i = 1; i <= poly.length; i++) L.push(L[i - 1] + Math.hypot(...sub(poly[i % poly.length], poly[i - 1])));
  const tot = L[poly.length], out = []; let j = 0;
  for (let i = 0; i < K; i++) {
    const d = tot * i / K; while (L[j + 1] < d) j++;
    const u = (d - L[j]) / (L[j + 1] - L[j] || 1), a = poly[j], b = poly[(j + 1) % poly.length];
    out.push([lerp(a[0], b[0], u), lerp(a[1], b[1], u)]);
  }
  const dy = YB - Math.max(...out.map(p => p[1]));
  return out.map(p => [p[0], p[1] + dy]);
}
// outline of several overlapping circles, seen from one centre (clouds)
const blobOf = (o, circles) => param(t => {
  const d = [Math.cos(t), Math.sin(t)]; let best = 0;
  for (const [cx, cy, r] of circles) {
    const q = [cx - o[0], cy - o[1]], b = d[0] * q[0] + d[1] * q[1], disc = r * r - (q[0] * q[0] + q[1] * q[1]) + b * b;
    if (disc >= 0) best = Math.max(best, b + Math.sqrt(disc));
  }
  return [o[0] + d[0] * best, o[1] + d[1] * best];
});
// even spacing along the outline, then a few relaxation passes: rounds tips and cusps without changing the overall shape
const uniform = (poly, n) => {
  const L = [0]; for (let i = 1; i <= poly.length; i++) L.push(L[i - 1] + Math.hypot(...sub(poly[i % poly.length], poly[i - 1])));
  const tot = L[poly.length], out = []; let j = 0;
  for (let i = 0; i < n; i++) { const d = tot * i / n; while (L[j + 1] < d) j++; const u = (d - L[j]) / (L[j + 1] - L[j] || 1), a = poly[j], b = poly[(j + 1) % poly.length]; out.push([lerp(a[0], b[0], u), lerp(a[1], b[1], u)]); }
  return out;
};
const relax = (poly, it) => {
  let p = poly; const n = p.length;
  for (let k = 0; k < it; k++) p = p.map((q, i) => { const a = p[(i - 1 + n) % n], b = p[(i + 1) % n]; return [q[0] + .5 * ((a[0] + b[0]) / 2 - q[0]), q[1] + .5 * ((a[1] + b[1]) / 2 - q[1])]; });
  return p;
};
const ellR = (a, b, t) => a * b / Math.hypot(b * Math.cos(t), a * Math.sin(t));
const SHAPES = {
  hex:     { n: '六边形', pts: () => finishShape(roundedPoly(ngon(6, 124, -90), 26), .05), faceY: 0, fs: 1 },
  mochi:   { n: '糯米团', pts: () => finishShape(param(t => [124 * Math.cos(t), (Math.sin(t) > 0 ? .86 : 1) * 110 * Math.sin(t)])), faceY: 8, fs: 1 },
  cube:    { n: '方糖', pts: () => finishShape(superellipse(108, 104, 4.2)), faceY: 2, fs: 1 },
  onigiri: { n: '饭团', pts: () => finishShape(roundedPoly(ngon(3, 160, -90), 44), .07), faceY: 24, fs: .86 },
  flower:  { n: '花朵', pts: () => finishShape(polar(t => 110 * (1 + .075 * Math.cos(6 * (t + Math.PI / 2))))), faceY: 2, fs: .95 },
  star:    { n: '星星', pts: () => finishShape(polar(t => 106 * (1 + .2 * Math.cos(5 * (t + Math.PI / 2))))), faceY: 10, fs: .86 },
  drop:    { n: '水滴', pts: () => finishShape(param(t => { const u = t + Math.PI / 2; return [126 * Math.sin(u) * Math.sin(u / 2) ** 1.15, -120 * Math.cos(u)]; })), faceY: 30, fs: .9 },
  heart:   { n: '爱心', pts: () => finishShape(relax(uniform(param(t => { const u = t + Math.PI / 2; return [7.3 * 16 * Math.sin(u) ** 3, -8.1 * (12 * Math.cos(u) - 4.6 * Math.cos(2 * u) - 2 * Math.cos(3 * u) - Math.cos(4 * u))]; }), 260), 160), .04), faceY: 6, fs: .9 },
  cloud:   { n: '云朵', pts: () => finishShape(relax(uniform(blobOf([0, 10], [[0, 26, 86], [-74, 34, 58], [74, 34, 58], [-38, -30, 56], [40, -40, 62]]).map(p => [p[0], p[1] > 50 ? 50 + (p[1] - 50) * .85 : p[1]]), 260), 30)), faceY: 12, fs: .92 },
  pudding: { n: '布丁', pts: () => finishShape(roundedPoly([[-74, -86], [74, -86], [116, 86], [-116, 86]], 30), .05), faceY: 14, fs: .95 },
  cat:     { n: '猫耳', pts: () => finishShape(polar(t => { let r = ellR(120, 100, t); for (const e of [-Math.PI / 2 - .74, -Math.PI / 2 + .74]) r += 50 * Math.max(0, 1 - Math.abs(Math.atan2(Math.sin(t - e), Math.cos(t - e))) / .36) ** 1.5; return r; })), faceY: 14, fs: .95 },
  gummy:   { n: '软糖', pts: () => finishShape(superellipse(134, 88, 2.6)), faceY: 4, fs: .95 },
};
for (const k in SHAPES) SHAPES[k].P = SHAPES[k].pts();

/* ---------- colours: 小光's palette, each base colour turned into the same jelly material ---------- */
const hex2 = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const toHex = c => '#' + c.map(v => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')).join('');
const mixHex = (a, b, t) => { const B = hex2(b); return toHex(hex2(a).map((v, i) => lerp(v, B[i], t))); };
const luma = h => { const [r, g, b] = hex2(h); return (.299 * r + .587 * g + .114 * b) / 255; };
// same eye rule as 小光's orb: light body → dark eyes, dark body → light eyes
function makeTheme(n, base, o = {}) {
  const dark = luma(base) <= .55;
  return {
    n, base,
    f0: mixHex(base, '#ffffff', .6), f1: mixHex(base, '#ffffff', .3), f2: mixHex(base, '#000000', .05),
    side: mixHex(base, '#ffffff', .5), rimDark: mixHex(base, '#000000', .45), under: mixHex(base, '#ffffff', .85),
    ink: dark ? mixHex(base, '#ffffff', .92) : mixHex(base, '#05060a', .88), glint: dark ? mixHex(base, '#000000', .25) : '#ffffff',
    blush: '#ff8da2', shadow: mixHex(base, '#000000', .3), caustic: mixHex(base, '#ffffff', .2),
    accent: mixHex(base, '#000000', .18), glow: base, rimL: .65, shA: .28, ...o,
  };
}
const toHsl = h => {
  const [r, g, b] = hex2(h).map(v => v / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  if (!d) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  const hh = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [(hh * 60 + 360) % 360, s, l];
};
const fromHsl = (h, s, l) => {
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return toHex([r, g, b].map(v => (v + m) * 255));
};
// clean edge colour: same hue, richer and deeper — no grey
const cleanRim = base => { const [h, s, l] = toHsl(base); return fromHsl(h, clamp(s * 1.15 + .12, 0, 1), clamp(l * .58, .12, .6)); };
const THEMES = {
  origin: { n: '初见青', base: '#8fdfe3', f0: '#bdf3f5', f1: '#97e1e6', f2: '#77cfd6', side: '#c8f7f7', rimDark: '#2f9aa6', under: '#eaffff', ink: '#132022', glint: '#ffffff', blush: '#ff8da2', shadow: '#2c8c96', caustic: '#84e4e9', accent: '#4fb3bd', glow: '#5fd9e3', rimL: .7, shA: .3 },
  gold:   makeTheme('森林金', '#f7cb4d', { blush: '#ff8f70' }),
  moon:   makeTheme('月白', '#f2f2f4', { rimClean: '#8ea8f2', f0: '#ffffff', f1: '#f5f6fa', f2: '#cfd4e2', side: '#ffffff', rimDark: '#58607a', under: '#ffffff', shadow: '#6f7690', caustic: '#dfe4f2', accent: '#8a92a8', glow: '#b9c6ff', rimL: .85, shA: .24 }),
  dawn:   makeTheme('晨光紫', '#8b7cff'),
  sun:    makeTheme('暖阳橙', '#ff8a65', { blush: '#ff5f7a' }),
  mint:   makeTheme('薄荷绿', '#4fd1a5'),
  sea:    makeTheme('海雾蓝', '#5b9dff'),
  sakura: makeTheme('樱花粉', '#ff8fb1', { blush: '#ff5c8a' }),
  orange: makeTheme('柑橘', '#ffad4d', { blush: '#ff7f6e' }),
  sky:    makeTheme('天空蓝', '#6cb8ff'),
  lilac:  makeTheme('丁香', '#a99bff'),
  night:  { n: '夜光', base: '#6670bf', f0: '#a3abe6', f1: '#6d77c4', f2: '#454e98', side: '#bcc3f2', rimDark: '#1d2360', under: '#c3c9ff', ink: '#e4e1ff', glint: '#ffffff', blush: '#ffa3c6', shadow: '#3a4185', caustic: '#a7b0ff', accent: '#6d76c9', glow: '#a9b8ff', rimL: .5, shA: .32, halo: '#efeaff', haloA: .55 },
};
const XG_COLORS = ['gold', 'moon', 'dawn', 'sun', 'mint', 'sea', 'sakura'];   // the 7 colours 小光 already offers
const CK = ['f0', 'f1', 'f2', 'side', 'rimDark', 'rimClean', 'halo', 'under', 'ink', 'glint', 'blush', 'shadow', 'caustic', 'accent', 'glow'], NK = ['rimL', 'shA', 'haloA'];
const rgb = c => `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
const parseTheme = t => { t = { halo: '#ffffff', haloA: 0, ...t }; const o = {}; CK.forEach(k => o[k] = hex2(t[k])); NK.forEach(k => o[k] = t[k]); return o; };
const mixTheme = (a, b, m) => {
  const o = {};
  CK.forEach(k => { const mm = k === 'ink' || k === 'glint' ? sstep(.35, .65, m) : m; o[k] = a[k].map((v, i) => lerp(v, b[k][i], mm)); });  // eyes switch quickly so they never fade into the body
  NK.forEach(k => o[k] = lerp(a[k], b[k], m)); return o;
};
for (const k in THEMES) { const T = THEMES[k]; T.rimClean = T.rimClean || cleanRim(T.base); T.C = parseTheme(T); }

/* ---------- expressions (face units; yaw = head turn on the surface, pitch = look up/down) ---------- */
const BASE = {
  eyeSep: 36, eyeY: -2, rx: 12.5, ry: 17.5,
  oL: 1, oR: 1, kL: -.6, kR: -.6, sL: 1.06, sR: 1.06, tilt: 0,
  lookX: 0, lookY: 0, glint: .85, heart: 0,
  mx: 0, my: 11, mw: 3.4, m0: 0, m1: 1.6, m2: 2.2, m3: 1.6, m4: 0, a0: 0, a1: 0, a2: 0, a3: 0, a4: 0, ms: 1, mf: 0, md: 6,
  blush: 0, yaw: -8, pitch: 0, roll: 0, sx: 1, sy: 1, breath: 1, listen: 0,
  fx_zzz: 0, fx_tear: 0, fx_q: 0, fx_hearts: 0, fx_dots: 0, fx_anger: 0,
};
const EXPR = {
  idle:      { n: '平常', h: '安静陪着你' },
  happy:     { n: '开心', h: '替你高兴', oL: 0, oR: 0, kL: 1, kR: 1, m: [0, 2.6, 3.4, 2.6, 0], mw: 4.8, my: 11, blush: .45, yaw: -4, pitch: -4, act: 'hop' },
  wink:      { n: '眨眼', h: '跟你说个秘密', oR: 0, kR: 1, glint: 1, m: [0, 1.8, 2.2, 1.3, -.4], mw: 3.6, mx: 3, my: 11, yaw: -14, roll: 6, act: 'nudge' },
  surprised: { n: '惊讶', h: '诶？真的吗', sL: 1.18, sR: 1.18, eyeY: -5, glint: 1, m: [0, -1.9, -2.6, -1.9, 0], mw: 1.7, mf: 1, md: 5.6, my: 15, sx: .96, sy: 1.05, pitch: -7, yaw: -2, act: 'pop' },
  shy:       { n: '害羞', h: '被你夸到了', oL: .9, oR: .9, sL: .92, sR: .92, lookX: -4, lookY: 4, blush: 1, m: [1, -1, 1, -1, 1], mw: 4, my: 14, yaw: -28, roll: -5, pitch: 8 },
  love:      { n: '喜欢', h: '好喜欢这个', heart: 1, blush: .6, m: [0, 5.2, 7, 5.2, 0], mw: 6, my: 12, pitch: -4, fx_hearts: 1, act: 'bounce' },
  think:     { n: '思考', h: '让我想一想', oL: .85, oR: .85, lookX: 6, lookY: -7, m: [1, .5, 0, -.5, -1], mw: 3.2, mx: 7, my: 15, yaw: 18, pitch: -9, roll: 3, fx_dots: 1 },
  sleepy:    { n: '困了', h: '该睡啦，晚安', oL: 0, oR: 0, kL: -.25, kR: -.25, m: [0, -1, -1.4, -1, 0], mw: 1.3, mf: 1, md: 3.4, my: 16, pitch: 10, roll: 5, yaw: -6, sy: .97, sx: 1.02, breath: 2, fx_zzz: 1 },
  sad:       { n: '难过', h: '抱抱你', oL: .8, oR: .8, tilt: -.75, sL: .96, sR: .96, lookY: 3, m: [5, 1.5, 0, 1.5, 5], mw: 6, my: 15, pitch: 12, sy: .95, sx: 1.03, fx_tear: 1 },
  grumpy:    { n: '不服', h: '哼，再来一次', oL: .66, oR: .66, tilt: .62, lookX: -2, glint: .5, m: [3, .6, 0, .6, 3], mw: 4.5, my: 16, sx: 1.05, sy: .96, yaw: -16, fx_anger: 1, act: 'puff' },
  // innocent "嗯？": both eyes open and round (a half-lid or uneven eyes reads as 质疑/轻蔑), a head tilt, a glance up, a tiny round mouth
  confused:  { n: '疑惑', h: '嗯？没太懂', sL: 1.1, sR: 1.04, glint: 1, lookX: 3, lookY: -3, m: [0, -.8, -1.1, -.8, 0], mw: 1.5, mf: 1, md: 3.2, my: 14, roll: 13, yaw: 6, pitch: -4, fx_q: 1, act: 'nudge' },
  listen:    { n: '在听', h: '你说，我在听', sL: 1.08, sR: 1.08, glint: .8, m: [0, .7, .9, .7, 0], mw: 1.8, my: 12, pitch: 3, yaw: -2, listen: 1 },
};
const ORDER = Object.keys(EXPR);
function paramsOf(name) {
  const e = EXPR[name], p = { ...BASE };
  for (const k in e) if (k in BASE) p[k] = e[k];
  if (e.m) e.m.forEach((v, i) => p['m' + i] = v);
  if (e.a) e.a.forEach((v, i) => p['a' + i] = v);
  return p;
}
function springCfg(k) {
  if (k === 'yaw' || k === 'pitch' || k === 'roll') return [60, 14];
  if (k === 'sx' || k === 'sy') return [220, 13];
  if (k.startsWith('fx_') || k === 'blush' || k === 'breath' || k === 'listen') return [45, 13.4];
  if (k === 'heart') return [240, 17];
  return [190, 26];
}

/* ---------- eye geometry: real lids clipped to the eye (drawn around 0,0) ---------- */
function eyeShape(rx, ry, o, k, s) {
  const yC = x => k * ry * (.55 * (x / rx) ** 2 - .3) + s * x * .5;
  const yU = x => lerp(-1.12 * ry + s * x, yC(x), 1 - o);
  const yL = x => lerp(1.12 * ry, yC(x), clamp((.3 - o) / .3, 0, 1));
  const e = x => ry * Math.sqrt(Math.max(0, 1 - (x / rx) ** 2));
  const top = x => Math.max(-e(x), yU(x)), bot = x => Math.min(e(x), yL(x)), g = x => bot(x) - top(x);
  const M = 30, xs = [];
  for (let j = 0; j < M; j++) xs.push(-rx * Math.cos(Math.PI * j / (M - 1)));
  let j0 = -1, j1 = -1;
  for (let j = 0; j < M; j++) if (g(xs[j]) > 0) { if (j0 < 0) j0 = j; j1 = j; }
  let fill = '';
  if (j0 >= 0 && j1 > j0) {
    const bis = (a, b) => { for (let i = 0; i < 10; i++) { const m = (a + b) / 2; (g(m) > 0) === (g(b) > 0) ? b = m : a = m; } return (a + b) / 2; };
    const xl = j0 > 0 ? bis(xs[j0 - 1], xs[j0]) : xs[j0], xr = j1 < M - 1 ? bis(xs[j1 + 1], xs[j1]) : xs[j1];
    const T = [[xl, top(xl)]], B = [];
    for (let j = j0; j <= j1; j++) { T.push([xs[j], top(xs[j])]); B.push([xs[j], bot(xs[j])]); }
    T.push([xr, top(xr)]);
    fill = 'M' + T.concat(B.reverse()).map(p => f1(p[0]) + ',' + f1(p[1])).join('L') + 'Z';
  }
  const L = xs.filter(x => { const y = yU(x), h = e(x); return h > 0 && y >= -h - .01 && y <= h + .01; });
  const lash = L.length > 1 ? 'M' + L.map(x => f1(x) + ',' + f1(yU(x))).join('L') : '';
  return { fill, lash };
}
const HEART = 'M0,.72C-.12,.6-1,.08-1,-.38C-1,-.86-.44,-1.06 0,-.6C.44,-1.06 1,-.86 1,-.38C1,.08 .12,.6 0,.72Z';
const SPARK = 'M0,-1Q.12,-.12 1,0Q.12,.12 0,1Q-.12,.12-1,0Q-.12,-.12 0,-1Z';

/* ---------- the jelly ---------- */
let UID = 0;
const faceSet = s => `
<g data-f="${s}">
  <g class="bl0"><ellipse rx="11" ry="7" class="blush"/></g><g class="bl1"><ellipse rx="11" ry="7" class="blush"/></g>
  <g class="m"><path class="mouth inkS inkF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>
  ${[0, 1].map(i => `<g class="e${i}"><ellipse class="halo" rx="24" ry="27" opacity="0"/><path class="eye inkF"/><path class="lash inkS" fill="none" stroke-linecap="round" stroke-linejoin="round"/><ellipse class="gl"/><path class="heart inkF" d="${HEART}"/>${i === 0 ? '<path class="tear" opacity="0" d="M0,-7C2.5,-3 5,0 5,3A5,5 0 0 1 -5,3C-5,0 -2.5,-3 0,-7Z" fill="#f4feff" stroke="#5fbfc9" stroke-opacity=".55"/>' : ''}</g>`).join('')}
</g>`;

export class Jelly {
  constructor(svg, opt = {}) {
    this.svg = svg; this.alive = !!opt.alive; this.awake = true; this.quietT = 0;
    const id = 'j' + (++UID);
    svg.setAttribute('viewBox', '-200 -200 400 400');
    svg.innerHTML = `
<defs>
  <radialGradient id="${id}f" cx=".38" cy=".3" r=".85"><stop class="gf0" offset="0"/><stop class="gf1" offset=".5"/><stop class="gf2" offset="1"/></radialGradient>
  <radialGradient id="${id}rl" cx=".5" cy=".5" r=".5" fx=".6" fy=".64"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".72" stop-color="#fff" stop-opacity="0"/><stop class="grl" offset="1" stop-color="#fff"/></radialGradient>
  <radialGradient id="${id}rd" cx=".5" cy=".5" r=".5" fx=".4" fy=".34"><stop class="grd0" offset="0" stop-opacity="0"/><stop class="grd1" offset=".7" stop-opacity="0"/><stop class="grd2" offset="1" stop-opacity=".3"/></radialGradient>
  <radialGradient id="${id}ug"><stop class="gu0" offset="0" stop-opacity=".8"/><stop class="gu1" offset="1" stop-opacity="0"/></radialGradient>
  <radialGradient id="${id}sh"><stop class="gh0" offset="0"/><stop class="gh1" offset=".55"/><stop class="gh2" offset="1" stop-opacity="0"/></radialGradient>
  <radialGradient id="${id}ca"><stop class="gc0" offset="0" stop-opacity=".6"/><stop class="gc1" offset="1" stop-opacity="0"/></radialGradient>
  <radialGradient id="${id}hl"><stop class="gh_0" offset="0" stop-opacity=".55"/><stop class="gh_1" offset=".55" stop-opacity=".2"/><stop class="gh_2" offset="1" stop-opacity="0"/></radialGradient>
  <radialGradient id="${id}bl"><stop class="gb0" offset="0" stop-opacity=".8"/><stop class="gb1" offset="1" stop-opacity="0"/></radialGradient>
  <linearGradient id="${id}sn" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".75"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  <linearGradient id="${id}lq" x1="0" y1="0" x2="0" y2="1"><stop class="glq0" offset="0"/><stop class="glq1" offset="1"/></linearGradient>
  <clipPath id="${id}c"><path class="clip"/></clipPath>
</defs>
<ellipse class="caustic" cx="12" cy="131" rx="80" ry="11" fill="url(#${id}ca)"/>
<ellipse class="shadow" cx="0" cy="128" rx="90" ry="14" fill="url(#${id}sh)"/>
<g class="arcs" fill="none" stroke-linecap="round" opacity="0"><path class="a0" stroke-width="3.2"/><path class="a1" stroke-width="2"/></g>
<g class="body">
  <path class="side"/>
  <path class="bodyP" fill="url(#${id}f)"/>
  <g clip-path="url(#${id}c)">
    <ellipse cx="0" cy="72" rx="82" ry="40" fill="url(#${id}ug)"/>
    <path class="tint" opacity="0"/>
    <path class="liq" fill="url(#${id}lq)" opacity="0"/>
    <circle class="bub" r="3" fill="#fff" opacity="0"/><circle class="bub" r="2.2" fill="#fff" opacity="0"/>
    <path class="liqLine" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0"/>
    <path class="rl" fill="url(#${id}rl)"/>
    <path class="rd" fill="url(#${id}rd)"/>
    <g class="sheen" opacity="0"><rect x="-30" y="-240" width="60" height="480" fill="url(#${id}sn)" transform="rotate(16)"/></g>
    <g class="face">${faceSet(0)}${faceSet(1)}</g>
  </g>
  <g class="spec"><path class="streak" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" opacity=".95"/><circle class="dot" r="2.6" fill="#fff"/></g>
  <path class="edge" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="1.2"/>
</g>
<g class="fx" font-family="system-ui,sans-serif" font-weight="800">
  <text class="z0 acc" opacity="0">Z</text><text class="z1 acc" opacity="0">z</text><text class="z2 acc" opacity="0">z</text>
  <text class="q acc" opacity="0" font-size="34" text-anchor="middle">?</text>
  <circle class="d0 acc" r="3.6" opacity="0"/><circle class="d1 acc" r="3.6" opacity="0"/><circle class="d2 acc" r="3.6" opacity="0"/>
  <path class="ht0" opacity="0" d="${HEART}" fill="#ff7d96"/><path class="ht1" opacity="0" d="${HEART}" fill="#ff7d96"/><path class="ht2" opacity="0" d="${HEART}" fill="#ff7d96"/>
  <path class="anger" opacity="0" d="M-7,-2Q-2,-2-2,-7M2,-7Q2,-2 7,-2M7,2Q2,2 2,7M-2,7Q-2,2-7,2" fill="none" stroke="#ff6b6b" stroke-width="2.8" stroke-linecap="round"/>
  ${`<path class="spk" d="${SPARK}" opacity="0"/>`.repeat(6)}
</g>`;
    const q = s => svg.querySelector(s), qa = s => [...svg.querySelectorAll(s)];
    this.E = {};
    ['clip', 'side', 'bodyP', 'rl', 'rd', 'edge', 'tint', 'liq', 'liqLine', 'glq0', 'glq1', 'sheen', 'spec', 'streak', 'dot', 'shadow', 'caustic', 'arcs', 'a0', 'a1', 'body',
     'z0', 'z1', 'z2', 'q', 'd0', 'd1', 'd2', 'ht0', 'ht1', 'ht2', 'anger',
     'gf0', 'gf1', 'gf2', 'grl', 'grd0', 'grd1', 'grd2', 'gu0', 'gu1', 'gh0', 'gh1', 'gh2', 'gc0', 'gc1', 'gb0', 'gb1', 'gh_0', 'gh_1', 'gh_2'].forEach(c => this.E[c] = q('.' + c));
    this.outline = [this.E.clip, this.E.side, this.E.bodyP, this.E.rl, this.E.rd, this.E.edge, this.E.tint];
    this.sets = [0, 1].map(s => {
      const g = q(`[data-f="${s}"]`), gq = c => g.querySelector(c);
      return { bl: [gq('.bl0'), gq('.bl1')], m: gq('.m'), e: [gq('.e0'), gq('.e1')] };
    });
    this.Q = { eye: [0, 1].map(i => qa(`.e${i} .eye`)), lash: [0, 1].map(i => qa(`.e${i} .lash`)), gl: [0, 1].map(i => qa(`.e${i} .gl`)),
      heart: [0, 1].map(i => qa(`.e${i} .heart`)), mouth: qa('.mouth'), bub: qa('.bub'), halo: qa('.halo'), blush: qa('.blush'), tear: qa('.tear'),
      inkF: qa('.inkF'), inkS: qa('.inkS'), acc: qa('.acc'), spk: qa('.spk') };
    this.Q.blush.forEach(e => e.setAttribute('fill', `url(#${id}bl)`));
    this.Q.halo.forEach(e => e.setAttribute('fill', `url(#${id}hl)`));

    this.S = {};
    for (const k in BASE) { const [kk, c] = springCfg(k); this.S[k] = new Spring(BASE[k], kk, c); }
    this.shear = new Spring(0, 160, 9);
    this.gl = { x: new Spring(0, 30, 10.5), y: new Spring(0, 30, 10.5) };
    this.sac = { x: new Spring(0, 520, 44), y: new Spring(0, 520, 44) };
    this.acts = []; this.t = Math.random() * 10;
    this.nextBlink = this.t + 1 + Math.random() * 3; this.blinkT = -9; this.blink2 = false;
    this.nextSac = this.t + 1; this.nextGlance = this.t + 2 + Math.random() * 3; this.breathPh = Math.random() * TAU;
    this.prevYaw = null; this.speed = 0; this.flash = 0; this.burstT = -9; this.cache = {};
    const sh = SHAPES[opt.shape || 'hex'];
    this.shapeName = opt.shape || 'hex';
    this.shFrom = this.shTo = sh.P; this.fFrom = this.fTo = { faceY: sh.faceY, fs: sh.fs };
    this.shMix = new Spring(1, 140, 11); this.shapeDirty = true; this.basePts = sh.P;
    this.themeName = opt.theme || 'origin';
    this.thFrom = this.thTo = THEMES[this.themeName].C; this.thMix = new Spring(1, 40, 12.6); this.thDirty = true;
    // material: 'jelly' = one solid jelly; 'liquid' = jelly on top, a sloshing liquid below the face
    this.material = opt.material || 'jelly';
    this.liq = new Spring(this.material === 'liquid' ? 1 : 0, 26, 8.6);
    this.sl = { th: new Spring(0, 34, 2.6), w: new Spring(0, 58, 2.4) };
    this.prevYv = 0; this.prevAy = 0; this.prevVy = 0;
    this.pinch = { amt: new Spring(0, 240, 15), x: 0, y: -60, held: false };
    this.gz = { x: 0, y: 0 }; this.talking = false; this.lite = !!opt.lite;
    this.set(opt.expr || 'idle', { quiet: true });
  }

  setMaterial(name) {
    if (name === this.material) return;
    this.material = name; this.liq.t = name === 'liquid' ? 1 : 0;
    this.sl.w.vel += 26; this.wake();
  }

  wake() { this.awake = true; this.quietT = 0; }

  setShape(name) {
    if (name === this.shapeName) return;
    const m = this.shMix.v;
    this.fFrom = { faceY: lerp(this.fFrom.faceY, this.fTo.faceY, m), fs: lerp(this.fFrom.fs, this.fTo.fs, m) };
    this.shFrom = this.basePts; this.shTo = SHAPES[name].P; this.fTo = { faceY: SHAPES[name].faceY, fs: SHAPES[name].fs };
    this.shapeName = name; this.shMix.v = 0; this.shMix.vel = 0; this.shMix.t = 1; this.shapeDirty = true;
    this.impulse(.35); this.wake();
  }
  setTheme(name) {
    if (name === this.themeName) return;
    this.thFrom = mixTheme(this.thFrom, this.thTo, clamp(this.thMix.v, 0, 1));
    this.thTo = THEMES[name].C; this.themeName = name; this.thMix.v = 0; this.thMix.vel = 0; this.thDirty = true; this.wake();
  }
  set(name, o = {}) {
    this.name = name; this.P = paramsOf(name);
    if (o.quiet) { for (const k in this.P) this.S[k].v = this.S[k].t = this.P[k]; return; }
    this.react(o.calm);
  }
  react(calm = false) {
    const a = calm ? '' : EXPR[this.name].act;   // calm: change the face without the entrance move
    this.S.yaw.vel += (this.S.yaw.t > this.S.yaw.v ? 1 : -1) * 55;
    this.impulse(.25);
    if (a === 'hop') this.hop(34);
    else if (a === 'pop') this.hop(14, .12, .42);
    else if (a === 'bounce') this.hop(18, .18, .6);
    else if (a === 'nudge') this.S.roll.vel += 50;
    else if (a === 'puff') { this.S.sx.vel += 1.2; this.S.sy.vel -= .9; }
    this.wake();
  }
  impulse(a) {
    const sg = Math.random() < .5 ? -1 : 1;
    this.S.sy.vel -= a * 1.8; this.S.sx.vel += a * 1.2; this.shear.vel += a * .25 * sg;
    if (this.sl) { this.sl.w.vel += a * 22; this.sl.th.vel += a * .35 * sg; }
  }

  // squeeze at a point on the body (local units); release() lets it spring back
  squeeze(x, y) {
    const pc = this.pinch; pc.x = x; pc.y = y; pc.held = true; pc.amt.t = 1; this.wake();
    this.S.oL.vel -= 14; this.S.oR.vel -= 14; this.S.kL.vel += 14; this.S.kR.vel += 14;   // eyes squeeze shut quickly instead of lingering half-closed
  }
  release() {
    const pc = this.pinch; if (!pc.held) return;
    pc.held = false; pc.amt.t = 0; pc.amt.vel -= 2.5;              // overshoot past rest = the jelly bounce
    this.impulse(.55); this.S.yaw.vel += (pc.x > 0 ? -1 : 1) * 40;
  }
  pinchOnce(x = 64, y = -58) { this.squeeze(x, y); setTimeout(() => this.release(), 520); }
  // a single tap: dent exactly where it lands and spring back in ~0.45 s.
  // Near the face centre the whole body squashes instead, so the face never distorts.
  tap(x, y) {
    const F = this.face || { faceY: 0, fs: 1 }, near = Math.hypot(x, y - F.faceY) < (this.maxX || 110) * .42;
    if (near) { this.S.sy.vel -= 2.3; this.S.sx.vel += 1.6; this.sl.w.vel += 16; }
    else { const pc = this.pinch; pc.x = x; pc.y = y; pc.amt.t = 0; pc.amt.vel = 16; this.sl.th.vel += (x > 0 ? -1 : 1) * .3; }
    this.blinkT = this.t; this.wake();
  }
  gaze(x, y) { this.gz.x = clamp(x, -1, 1); this.gz.y = clamp(y, -1, 1); }
  setTalking(on) { this.talking = !!on; if (on) this.wake(); }
  setLook(look) { const L = parseLook(look) || parseLook(LOOK_DEFAULT); this.setShape(L.shape); this.setTheme(L.color); this.setMaterial(L.material); }

  hop(H = 34, ant = .2, air = .68) {
    this.acts.push({
      t0: this.t, dur: ant + air,
      f: t => {
        if (t < ant) { const e = Math.sin(t / ant * Math.PI / 2); return { y: 0, sy: 1 - .09 * e, sx: 1 + .06 * e }; }
        const p = (t - ant) / air, y = -H * Math.pow(Math.sin(p * Math.PI), .78);
        const st = .08 * Math.pow(1 - p, 3) + .035 * Math.pow(p, 4), r = sstep(0, .16, p);
        return { y, sy: lerp(.91, 1 + st, r), sx: lerp(1.06, 1 - st * .6, r) };
      },
      end: () => this.impulse(H / 40),
    });
    this.wake();
  }

  // the face travels once round the body: wind up, glide, settle with a soft overshoot
  spin() {
    if (this.acts.some(a => a.spin)) return;
    const dur = 1.25, wind = .2;
    this.hop(14, .24, dur - .2);
    this.acts.push({
      spin: true, t0: this.t, dur,
      f: t => {
        const p = t / dur;
        if (p < wind) { const u = p / wind; return { yaw: -14 * u * u * (3 - 2 * u), sx: 1 + .03 * u, sy: 1 - .04 * u }; }
        const q = (p - wind) / (1 - wind);
        const e = q < .5 ? 4 * q * q * q : 1 - Math.pow(-2 * q + 2, 3) / 2;
        const u = clamp((q - .5) / .5, 0, 1);
        const yaw = lerp(-14, 180, e) + 10 * Math.sin(Math.PI * u) ** 2;
        const mid = Math.sin(Math.PI * q);
        return { yaw, sx: lerp(1.03, 1, sstep(0, .2, q)) - .025 * mid, sy: lerp(.96, 1, sstep(0, .2, q)) + .03 * mid, sheen: q };
      },
      end: () => { this.burstT = this.t; this.impulse(.3); },
    });
    this.wake();
  }

  updateShape() {
    const m = clamp(this.shMix.v, -.15, 1.2), A = this.shFrom, B = this.shTo, pts = [];
    let minY = 1e9, maxX = 0;
    for (let i = 0; i < K; i++) { const p = [lerp(A[i][0], B[i][0], m), lerp(A[i][1], B[i][1], m)]; pts.push(p); minY = Math.min(minY, p[1]); maxX = Math.max(maxX, Math.abs(p[0])); }
    this.basePts = pts; this.minY = minY; this.maxX = maxX;
    let dp = pts;
    const pa = this.pinch ? this.pinch.amt.v : 0;
    if (Math.abs(pa) > .002) {
      const px = this.pinch.x, py = this.pinch.y;
      dp = pts.map(p => {
        const d2 = ((p[0] - px) ** 2 + (p[1] - py) ** 2) / (58 * 58), k = pa * 20 * Math.exp(-d2), n = nrm(sub([0, 10], p));
        return [p[0] + n[0] * k, p[1] + n[1] * k];
      });
    }
    let d = '';
    for (let i = 0; i < K; i++) {
      const p0 = dp[(i - 1 + K) % K], p1 = dp[i], p2 = dp[(i + 1) % K], p3 = dp[(i + 2) % K];
      if (!i) d = 'M' + f1(p1[0]) + ',' + f1(p1[1]);
      d += `C${f1(p1[0] + (p2[0] - p0[0]) / 6)},${f1(p1[1] + (p2[1] - p0[1]) / 6)} ${f1(p2[0] - (p3[0] - p1[0]) / 6)},${f1(p2[1] - (p3[1] - p1[1]) / 6)} ${f1(p2[0])},${f1(p2[1])}`;
    }
    d += 'Z';
    this.outline.forEach(el => el.setAttribute('d', d));
    this.face = { faceY: lerp(this.fFrom.faceY, this.fTo.faceY, m), fs: lerp(this.fFrom.fs, this.fTo.fs, m) };
    this.liqL = Math.max(lerp(minY, YB, .68), this.face.faceY + 36 * this.face.fs);   // waterline stays under the mouth
    const at = (fr, ins) => {
      const x = fr * K, i = Math.floor(x), u = x - i, a = pts[i % K], b = pts[(i + 1) % K];
      const p = [lerp(a[0], b[0], u), lerp(a[1], b[1], u)], dir = nrm(sub([0, 10], p));
      return [f1(p[0] + dir[0] * ins), f1(p[1] + dir[1] * ins)];
    };
    const s1 = at(.035, 14), s2 = at(.068, 14), s3 = at(.085, 14);
    this.E.streak.setAttribute('d', `M${s1}L${s2}`); this.E.dot.setAttribute('cx', s3[0]); this.E.dot.setAttribute('cy', s3[1]);
    // motion arcs on the trailing (left) side; mirrored when turning the other way
    const a = maxX + 20;
    this.E.a0.setAttribute('d', `M${f1(-a)},-46Q${f1(-a - 16)},4 ${f1(-a)},54`);
    this.E.a1.setAttribute('d', `M${f1(-a - 16)},-22Q${f1(-a - 28)},4 ${f1(-a - 16)},30`);
  }

  applyTheme(c) {
    const E = this.E, set = (el, a, v) => el.setAttribute(a, v);
    set(E.gf0, 'stop-color', rgb(c.f0)); set(E.gf1, 'stop-color', rgb(c.f1)); set(E.gf2, 'stop-color', rgb(c.f2));
    set(E.side, 'fill', rgb(c.side));
    set(E.tint, 'fill', rgb(c.f2));
    set(E.glq0, 'stop-color', rgb(c.f0.map(v => lerp(v, 255, .45)))); set(E.glq1, 'stop-color', rgb(c.f0.map((v, i) => lerp(v, c.f1[i], .25))));
    set(E.grl, 'stop-opacity', clamp(c.rimL * Jelly.rim.light, 0, 1).toFixed(2));
    const rim = c.rimDark.map((v, i) => lerp(v, c.rimClean[i], Jelly.rim.hue));
    [E.grd0, E.grd1, E.grd2].forEach(s => set(s, 'stop-color', rgb(rim)));
    set(E.grd2, 'stop-opacity', Jelly.rim.amt.toFixed(2));
    set(E.gu0, 'stop-color', rgb(c.under)); set(E.gu1, 'stop-color', rgb(c.under));
    [E.gh0, E.gh1, E.gh2].forEach(s => set(s, 'stop-color', rgb(c.shadow)));
    set(E.gh0, 'stop-opacity', c.shA.toFixed(2)); set(E.gh1, 'stop-opacity', (c.shA * .3).toFixed(2));
    set(E.gc0, 'stop-color', rgb(c.caustic)); set(E.gc1, 'stop-color', rgb(c.caustic));
    set(E.gb0, 'stop-color', rgb(c.blush)); set(E.gb1, 'stop-color', rgb(c.blush));
    [E.gh_0, E.gh_1, E.gh_2].forEach(s => set(s, 'stop-color', rgb(c.halo)));
    this.Q.halo.forEach(e => set(e, 'opacity', c.haloA.toFixed(2)));
    const ink = rgb(c.ink);
    this.Q.inkF.forEach(e => set(e, 'fill', ink)); this.Q.inkS.forEach(e => set(e, 'stroke', ink));
    this.Q.gl.flat().forEach(e => set(e, 'fill', rgb(c.glint)));
    this.Q.acc.forEach(e => set(e, 'fill', rgb(c.accent)));
    set(E.arcs, 'stroke', rgb(c.glow));
    this.Q.spk.forEach((e, i) => set(e, 'fill', i % 3 === 0 ? '#ffffff' : rgb(c.glow)));
  }

  frame(dt) {
    this.t += dt; const t = this.t, S = this.S, P = this.P;
    for (const k in S) S[k].t = P[k];
    if (this.gz.x || this.gz.y) { S.yaw.t += this.gz.x * 14; S.pitch.t += this.gz.y * 8; S.lookX.t += this.gz.x * 4; S.lookY.t += this.gz.y * 3; }
    if (this.talking) { S.mf.t = .3 + .7 * Math.abs(Math.sin(t * 8.5)) * (.6 + .4 * Math.sin(t * 2.3)); S.md.t = 3.6; }
    if (t < this.flash || this.pinch.held) { S.oL.t = 0; S.oR.t = 0; S.kL.t = 1; S.kR.t = 1; }
    if (this.alive) {
      // a little life: glances, eye darts, blinks
      if (t > this.nextGlance) {
        const out = Math.abs(this.gl.x.t) < 1;
        this.gl.x.t = out ? (Math.random() < .5 ? -1 : 1) * (8 + Math.random() * 10) : 0;
        this.gl.y.t = out ? (Math.random() * 2 - 1) * 5 : 0;
        this.nextGlance = t + (out ? 1.4 + Math.random() * 1.2 : 3 + Math.random() * 4);
      }
      if (t > this.nextSac) { this.nextSac = t + 1.3 + Math.random() * 2.4; this.sac.x.t = (Math.random() * 2 - 1) * 2.6; this.sac.y.t = (Math.random() * 2 - 1) * 1.6; }
      if (t > this.nextBlink) { this.blinkT = t; this.nextBlink = t + 2.6 + Math.random() * 3.6; this.blink2 = Math.random() < .2; }
    }
    const h = dt / 2;
    for (let i = 0; i < 2; i++) {
      for (const k in S) S[k].step(h);
      this.gl.x.step(h); this.gl.y.step(h); this.sac.x.step(h); this.sac.y.step(h);
      this.shMix.step(h); this.thMix.step(h); this.liq.step(h); this.sl.th.step(h); this.sl.w.step(h); this.pinch.amt.step(h);
    }

    let ay = 0, asx = 1, asy = 1, ayaw = 0, sheen = -1;
    this.acts = this.acts.filter(a => {
      const tt = t - a.t0;
      if (tt >= a.dur) { a.end && a.end(); return false; }
      const r = a.f(tt); ay += r.y || 0; asx *= r.sx || 1; asy *= r.sy || 1; ayaw += r.yaw || 0; if (r.sheen !== undefined) sheen = r.sheen; return true;
    });

    let b = 0, lis = 0;
    if (this.alive) {
      const br = Math.max(.4, S.breath.v);
      this.breathPh += dt * TAU / (3 * br);
      b = Math.sin(this.breathPh) * .012 * br;
      if (S.listen.v > .01) lis = S.listen.v * Math.abs(Math.sin(t * 6.1) * .6 + Math.sin(t * 9.3) * .4) * (.5 + .5 * Math.sin(t * 1.5));
    }
    const yaw = S.yaw.v + this.gl.x.v + ayaw, pitch = S.pitch.v + this.gl.y.v, roll = S.roll.v;
    const pa = this.pinch.amt.v, pv = Math.abs(this.pinch.y + 10) > Math.abs(this.pinch.x) ? 1 : 0;   // squeezed from top/bottom or from a side
    const sx = S.sx.v * asx * (1 - b * .6) * (1 + pa * (pv ? .07 : -.08)), sy = S.sy.v * asy * (1 + b + lis * .015) * (1 + pa * (pv ? -.09 : .06));
    let yv = 0;
    if (this.prevYaw !== null && dt > 0) yv = (yaw - this.prevYaw) / dt;
    this.prevYaw = yaw;
    this.speed += (sstep(80, 380, Math.abs(yv)) - this.speed) * Math.min(1, dt * 10);
    this.shear.t = clamp(-yv * .00012, -.05, .05); this.shear.step(dt);

    const E = this.E, w = Jelly.w;
    const pinching = Math.abs(this.pinch.amt.v) > .002 || !this.pinch.amt.still;
    if (this.shapeDirty || pinching || this._pinched) { this._pinched = pinching; if (this.shMix.still) { this.shMix.v = 1; this.shapeDirty = false; } this.updateShape(); }
    if (this.thDirty) {
      if (this.thMix.still) { this.thFrom = this.thTo; this.applyTheme(this.thTo); this.thDirty = false; }
      else this.applyTheme(mixTheme(this.thFrom, this.thTo, clamp(this.thMix.v, 0, 1)));
    }

    // body: squash anchored on the floor, a little lean, jelly shear while turning
    w(E.body, 'transform', `translate(0 ${f1(ay)}) rotate(${f1(roll * .7)} 0 ${YB - 40}) translate(0 ${YB}) matrix(${f3(sx)} 0 ${f3(this.shear.v)} ${f3(sy)} 0 0) translate(0 ${-YB})`);
    // liquid: stays level in the world (counter-tilts against the lean), sloshes when the body turns or hops
    const vy = dt > 0 ? (ay - this.prevAy) / dt : 0;
    this.sl.th.t = -rad(roll * .7);
    this.sl.th.vel += clamp(-(yv - this.prevYv) * .0028, -.5, .5);
    this.sl.w.vel += clamp(-(vy - this.prevVy) * .25, -30, 30);
    this.prevYv = yv; this.prevAy = ay; this.prevVy = vy;
    const lq = this.liq.v, liqOn = lq > .004 || this.liq.t > 0;
    if (liqOn || this._liq) {
      this._liq = liqOn;
      const L = lerp(YB + 28, this.liqL, clamp(lq, -.1, 1.15)), W = this.maxX + 16;
      const tt = Math.tan(clamp(this.sl.th.v, -.45, .45)), wa = clamp(this.sl.w.v, -9, 9), rip = this.alive ? .8 : 0;
      let line = '';
      for (let i = 0; i <= 16; i++) {
        const x = -W + 2 * W * i / 16, y = L + tt * x + wa * .6 * Math.cos(Math.PI * x / W) + rip * Math.sin(t * 1.7 + x * .045);
        line += (i ? 'L' : 'M') + f1(x) + ',' + f1(y);
      }
      w(E.liq, 'd', line + `L${f1(W)},${YB + 40}L${f1(-W)},${YB + 40}Z`); w(E.liqLine, 'd', line);
      w(E.liq, 'opacity', liqOn ? .92 : 0); w(E.liqLine, 'opacity', liqOn ? .85 : 0);
      w(E.tint, 'opacity', op(clamp(lq, 0, 1) * .34));
      this.Q.bub.forEach((el, i) => {
        if (!this.alive || this.lite || !liqOn) { w(el, 'opacity', 0); return; }
        const p = ((t + i * 2.1) / 4.2) % 1, bx = (i ? 30 : -40) + Math.sin(t * 2 + i) * 2.5;
        w(el, 'cx', f1(bx)); w(el, 'cy', f1(lerp(YB - 16, L + tt * bx + 5, p)));
        w(el, 'opacity', op(.5 * sstep(0, .12, p) * (1 - sstep(.86, 1, p)) * clamp(lq, 0, 1)));
      });
    }
    const yr = rad(yaw), s2 = Math.sin(2 * yr);
    w(E.side, 'transform', `translate(${f1(7 - 9 * s2)} ${f1(4 + pitch * .25)})`);
    w(E.spec, 'transform', `translate(${f1(-12 * s2)} ${f1(-pitch * .3)})`);
    const lift = clamp(-ay / 90, 0, .7), k = 1 - lift, sw = (this.maxX / 104) * k * sx;
    w(E.shadow, 'transform', `translate(0 128) scale(${f3(sw)} ${f3(k)}) translate(0 -128)`);
    w(E.shadow, 'opacity', op(k));
    w(E.caustic, 'transform', `translate(0 131) scale(${f3(sw)} ${f3(k)}) translate(0 -131)`);
    w(E.caustic, 'opacity', op(k * k));

    // spin effects: a light sweep across the jelly, two soft motion arcs, sparkles on landing
    w(E.sheen, 'opacity', sheen >= 0 ? op(Math.sin(Math.PI * sheen) * .9) : 0);
    if (sheen >= 0) w(E.sheen, 'transform', `translate(${f1(lerp(-180, 180, sheen))} 0)`);
    const sp = this.speed;
    w(E.arcs, 'opacity', op(sp * .8));
    if (sp > .01) w(E.arcs, 'transform', `translate(0 ${f1(ay)}) scale(${yv >= 0 ? 1 : -1} 1)`);
    const bp = (t - this.burstT) / .9, bOn = bp >= 0 && bp < 1;
    if (bOn || this._spk) {
      this._spk = bOn;
      const e = 1 - Math.pow(1 - clamp(bp, 0, 1), 3);
      this.Q.spk.forEach((el, i) => {
        const a = -Math.PI / 2 + (i - 2.5) * .5, r = 100 + 50 * e;
        w(el, 'transform', `translate(${f1(Math.cos(a) * r * 1.2)} ${f1(10 + Math.sin(a) * r + ay)}) scale(${f1(Math.sin(Math.PI * clamp(bp, 0, 1)) * (i % 2 ? 5 : 7))}) rotate(${f1(bp * 80)})`);
        w(el, 'opacity', bOn ? op(1 - sstep(.55, 1, bp)) : 0);
      });
    }

    // face: features ride a hidden sphere; a second copy waits on the far side, so there is never a blank back
    const v = k2 => S[k2].v, F = this.face, fs = F.fs;
    let bf = 0; const bt = t - this.blinkT;
    if (bt < .2) bf = Math.sin(bt / .2 * Math.PI);
    else if (this.blink2 && bt > .27 && bt < .47) bf = Math.sin((bt - .27) / .2 * Math.PI);
    const heart = Math.max(0, v('heart')), eyeK = Math.max(0, 1 - heart * 1.5), eb = 1 + lis * .14;
    const smear = 1 + sp * .35;
    const lx = v('lookX') + this.sac.x.v, ly = v('lookY') + this.sac.y.v;
    const py = RV * Math.sin(rad(pitch)), pc = Math.cos(rad(pitch));
    for (let i = 0; i < 2; i++) {
      const side = i ? 'R' : 'L', sg = i ? 1 : -1, sc = v('s' + side);
      const rx = v('rx') * sc * eyeK, ry = v('ry') * sc * eyeK * eb, o = clamp(v('o' + side), 0, 1) * (1 - bf);
      const key = [rx, ry, o, v('k' + side), v('tilt')].map(n => n.toFixed(2)).join();
      if (this.cache['e' + i] !== key) {        // eye outline is rebuilt only when it actually changes
        this.cache['e' + i] = key;
        const sh = rx > .5 ? eyeShape(rx, ry, o, v('k' + side), -sg * v('tilt')) : { fill: '', lash: '' };
        const lw = f1(Math.max(0, 6 * sstep(0, .55, 1 - o)) * sc * eyeK);
        this.Q.eye[i].forEach(e => e.setAttribute('d', sh.fill));
        this.Q.lash[i].forEach(e => { e.setAttribute('d', sh.lash); e.setAttribute('stroke-width', lw); });
        this.Q.gl[i].forEach(e => { e.setAttribute('cx', f1(rx * .34)); e.setAttribute('cy', f1(-ry * .42)); e.setAttribute('rx', f1(rx * .24)); e.setAttribute('ry', f1(rx * .28)); });
      }
      this.Q.gl[i].forEach(e => w(e, 'opacity', op(v('glint') * sstep(.7, .95, o))));
      const hs = heart * 15 * (1 + .06 * Math.sin(t * 6) * Math.min(1, heart));
      this.Q.heart[i].forEach(e => w(e, 'transform', `scale(${Math.max(.001, hs).toFixed(3)})`));
    }
    const breathe = this.name === 'sleepy' ? 1 + Math.sin(this.breathPh) * .22 : 1;
    const mkey = ['mw', 'm0', 'm1', 'm2', 'm3', 'm4', 'a0', 'a1', 'a2', 'a3', 'a4', 'ms', 'mf', 'md'].map(n => v(n).toFixed(2)).join() + breathe.toFixed(2);
    if (this.cache.m !== mkey) {
      // one mouth shape for every expression: a 5-point line, optionally opened into a small "o" below it.
      // switching expressions only moves these points, so mouths morph and never cross-fade
      this.cache.m = mkey;
      const mw = v('mw'), ms = clamp(v('ms'), 0, 1.2), mf = clamp(v('mf'), 0, 1.2), md = v('md') * mf * breathe;
      const top = [0, 1, 2, 3, 4].map(i => [(i - 2) * mw + v('a' + i), v('m' + i)]);
      const bot = top.map((p, i) => [p[0], p[1] + md * [0, .78, 1, .78, 0][i]]).reverse();
      const curve = pp => {
        let d = '';
        for (let i = 0; i < 4; i++) {
          const p0 = pp[Math.max(0, i - 1)], p1 = pp[i], p2 = pp[i + 1], p3 = pp[Math.min(4, i + 2)];
          d += `C${f1(p1[0] + (p2[0] - p0[0]) * ms / 6)},${f1(p1[1] + (p2[1] - p0[1]) * ms / 6)} ${f1(p2[0] - (p3[0] - p1[0]) * ms / 6)},${f1(p2[1] - (p3[1] - p1[1]) * ms / 6)} ${f1(p2[0])},${f1(p2[1])}`;
        }
        return d;
      };
      const d = 'M' + f1(top[0][0]) + ',' + f1(top[0][1]) + curve(top) + 'L' + f1(bot[0][0]) + ',' + f1(bot[0][1]) + curve(bot) + 'Z';
      this.Q.mouth.forEach(e => e.setAttribute('d', d));
    }
    this.Q.blush.forEach(e => w(e, 'opacity', op(v('blush') * .7)));
    const ft = v('fx_tear');
    if (ft > .003 || this._tear) {
      this._tear = ft > .003;
      const tp = (t * .38) % 1;
      this.Q.tear.forEach(e => { w(e, 'transform', `translate(-9 ${f1(14 + tp * 34)}) scale(${f1(.75 + tp * .2)})`); w(e, 'opacity', op(ft * sstep(0, .15, tp) * (1 - sstep(.7, 1, tp)))); });
    }
    const place = (g, x0, y0, sxl, syl, s) => {
      const lam = yr + Math.PI * s + x0 / RS, c = Math.cos(lam);
      if (c <= .02) { w(g, 'opacity', 0); return; }
      w(g, 'transform', `translate(${f1(RS * Math.sin(lam))} ${f1(y0)}) scale(${f3(c * sxl)} ${f3(syl)})`);
      w(g, 'opacity', op(sstep(.02, .3, c)));
    };
    for (let s = 0; s < 2; s++) {
      const set = this.sets[s];
      for (let i = 0; i < 2; i++) {
        const sg = i ? 1 : -1;
        place(set.e[i], (sg * v('eyeSep') + lx * .65) * fs, F.faceY + (v('eyeY') + ly * .65) * fs + py, fs * smear, fs * pc, s);
        place(set.bl[i], (sg * (v('eyeSep') + 9) + lx * .35) * fs, F.faceY + (v('eyeY') + 20 + ly * .35) * fs + py, fs, fs * pc, s);
      }
      place(set.m, (v('mx') + lx * .35) * fs, F.faceY + (v('my') + ly * .35) * fs + py, fs, fs * pc, s);
    }

    // expression effects sit above the body, away from the face
    const ax = this.maxX * .55, ay2 = this.minY * .8 + ay;
    const live = (key, val) => { const was = this['_' + key]; this['_' + key] = val > .003; return val > .003 || was; };
    const fz = clamp(v('fx_zzz'), 0, 1);
    if (live('z', fz)) [0, 1, 2].forEach(i => {
      const ph = (t * .3 + i / 3) % 1, el = E['z' + i];
      w(el, 'x', f1(ax + 6 + ph * 30 + Math.sin(ph * 6 + i) * 4)); w(el, 'y', f1(ay2 - 4 - ph * 52));
      w(el, 'font-size', f1(13 + ph * 11)); w(el, 'opacity', op(fz * Math.sin(ph * Math.PI)));
    });
    const fq = clamp(v('fx_q'), 0, 1);
    if (live('q', fq)) { w(E.q, 'transform', `translate(${f1(ax + 18)} ${f1(ay2 - 8 + Math.sin(t * 2.2) * 4)}) rotate(${f1(14 + Math.sin(t * 1.6) * 7)}) scale(${f1(.6 + .4 * fq)})`); w(E.q, 'opacity', op(fq)); }
    const fd = clamp(v('fx_dots'), 0, 1);
    if (live('d', fd)) [0, 1, 2].forEach(i => {
      const on = sstep(i * .33, i * .33 + .2, (t * .5) % 1.25), el = E['d' + i];
      w(el, 'cx', f1(ax + 4 + i * 12)); w(el, 'cy', f1(ay2 - 10 - i * 6 - on * 3)); w(el, 'opacity', op(fd * on));
    });
    const fh = clamp(v('fx_hearts'), 0, 1);
    if (live('h', fh)) [0, 1, 2].forEach(i => {
      const ph = (t * .26 + i / 3) % 1, el = E['ht' + i];
      w(el, 'transform', `translate(${f1(ax - 10 + i * 16 + Math.sin(ph * 5 + i * 2) * 6)} ${f1(ay2 - ph * 60)}) scale(${f1(5 + ph * 3)}) rotate(${f1(Math.sin(ph * 4 + i) * 12)})`);
      w(el, 'opacity', op(fh * Math.sin(ph * Math.PI)));
    });
    const fa = clamp(v('fx_anger'), 0, 1);
    if (live('a', fa)) { w(E.anger, 'transform', `translate(${f1(ax + 10)} ${f1(ay2 + 4)}) scale(${f1((1 + .1 * Math.max(0, Math.sin(t * 4.5))) * (.5 + .5 * fa))})`); w(E.anger, 'opacity', op(fa)); }

    // thumbnails go to sleep once nothing is moving
    if (!this.alive) {
      let busy = this.acts.length || this.shapeDirty || this.thDirty || this._spk || sp > .01 || !this.liq.still || !this.sl.th.still || !this.sl.w.still || pinching;
      if (!busy) for (const k2 in S) if (!S[k2].still) { busy = true; break; }
      this.quietT = busy ? 0 : this.quietT + dt;
      if (this.quietT > .3) this.awake = false;
    }
  }
}
// press-and-hold on a jelly to squeeze it (main stage only)
Jelly.prototype.bindSqueeze = function () {
  const svg = this.svg;
  const local = e => { const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse()); return [pt.x, pt.y - (this.prevAy || 0)]; };
  svg.addEventListener('pointerdown', e => {
    const [x, y] = local(e);
    if (!this.E.bodyP.isPointInFill(new DOMPoint(x, y))) return;
    svg.setPointerCapture(e.pointerId); svg.classList.add('squeezing'); this.squeeze(x, y);
  });
  svg.addEventListener('pointermove', e => {
    const [x, y] = local(e);
    if (!this.pinch.held) { svg.classList.toggle('over', this.E.bodyP.isPointInFill(new DOMPoint(x, y))); return; }
    this.pinch.x = lerp(this.pinch.x, x, .3); this.pinch.y = lerp(this.pinch.y, y, .3);
  });
  const up = () => { svg.classList.remove('squeezing'); this.release(); };
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
};
// big stages: tap = local dent, hold = squeeze, quick double tap = onDouble().
// The first tap only plays its short dent; a second tap within 280 ms cancels it and hands over to onDouble.
Jelly.prototype.bindTouch = function ({ onDouble, onTap } = {}) {
  const svg = this.svg;
  svg.style.touchAction = 'manipulation';
  const local = e => { const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse()); return [pt.x, pt.y - (this.prevAy || 0)]; };
  const inside = (x, y) => this.E.bodyP.isPointInFill(new DOMPoint(x, y));
  let holdTimer = 0, lastTap = 0, lastXY = [0, 0], down = null;
  svg.addEventListener('pointerdown', e => {
    const [x, y] = local(e);
    if (!inside(x, y)) return;
    svg.setPointerCapture(e.pointerId);
    const now = performance.now();
    if (now - lastTap < 280 && Math.hypot(x - lastXY[0], y - lastXY[1]) < 60) {
      lastTap = 0; down = null;
      this.pinch.amt.v *= .3; this.pinch.amt.vel = 0;      // let the first dent go quietly
      onDouble?.(); return;
    }
    down = { x, y }; lastTap = now; lastXY = [x, y];
    holdTimer = setTimeout(() => { if (down) { svg.classList.add('squeezing'); this.squeeze(down.x, down.y); } }, 200);
    this.tap(x, y); onTap?.();
  });
  svg.addEventListener('pointermove', e => {
    const [x, y] = local(e);
    if (!this.pinch.held) { svg.classList.toggle('over', inside(x, y)); return; }
    this.pinch.x = lerp(this.pinch.x, x, .3); this.pinch.y = lerp(this.pinch.y, y, .3);
  });
  const up = () => { clearTimeout(holdTimer); down = null; svg.classList.remove('squeezing'); this.release(); };
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
};
// edge shading shared by every jelly on the page: hue 0 = old grey edge, 1 = clean same-hue edge; amt = how strong
Jelly.rim = { hue: 1, amt: .24, light: 1 };
// write an attribute only when its value actually changes
Jelly.w = (el, a, v) => { const c = el.__c || (el.__c = {}); if (c[a] !== v) { c[a] = v; el.setAttribute(a, v); } };

/* ---------- looks: shape.color.material ---------- */
export const MATERIALS = {
  jelly:  { n: '整块果冻', h: '干净通透' },
  liquid: { n: '晃晃水', h: '下半身会晃' },
};
export const LOOK_DEFAULT = 'cloud.moon.jelly';
export const LOOKS = [
  { id: 'cloud.moon.jelly', n: '云朵 · 月白', h: '软软地陪着你' },
  { id: 'hex.origin.jelly', n: '六边形 · 初见青', h: '最初的样子' },
  { id: 'mochi.sun.jelly', n: '糯米团 · 暖阳橙', h: '软乎乎' },
  { id: 'cat.lilac.jelly', n: '猫耳 · 丁香', h: '歪头看你' },
  { id: 'heart.sakura.jelly', n: '爱心 · 樱花粉', h: '被你暖到' },
  { id: 'star.night.jelly', n: '星星 · 夜光', h: '晚上也陪你' },
  { id: 'drop.sea.liquid', n: '水滴 · 海雾蓝', h: '慢慢来' },
  { id: 'cube.gold.jelly', n: '方糖 · 森林金', h: '甜一点' },
  { id: 'pudding.orange.liquid', n: '布丁 · 柑橘', h: '弹一下' },
  { id: 'onigiri.mint.jelly', n: '饭团 · 薄荷绿', h: '有点机灵' },
  { id: 'flower.dawn.jelly', n: '花朵 · 晨光紫', h: '温柔一点' },
  { id: 'gummy.sky.jelly', n: '软糖 · 天空蓝', h: '圆滚滚' },
];
export function parseLook(s) {
  const [shape, color, material] = String(s || '').split('.');
  return SHAPES[shape] && THEMES[color] && MATERIALS[material] ? { shape, color, material } : null;
}
export const lookName = s => { const L = parseLook(s) || parseLook(LOOK_DEFAULT); return `${SHAPES[L.shape].n} · ${THEMES[L.color].n}`; };
export const lookBase = s => THEMES[(parseLook(s) || parseLook(LOOK_DEFAULT)).color].base;
export const lookOpts = s => { const L = parseLook(s) || parseLook(LOOK_DEFAULT); return { shape: L.shape, theme: L.color, material: L.material }; };

/* ---------- one animation loop for every jelly on the page ---------- */
const LIVE = new Set();
let lastT = 0, rafId = 0;
const io = typeof IntersectionObserver !== 'undefined'
  ? new IntersectionObserver(es => es.forEach(e => { const j = e.target.__jelly; if (j) j.visible = e.isIntersecting; })) : null;
function tick(now) {
  const dt = Math.min(.034, (now - lastT) / 1000); lastT = now;
  for (const j of LIVE) {
    if (!j.svg.isConnected) { untrack(j); continue; }
    if (j.visible && (j.alive || j.awake)) j.frame(dt);
  }
  rafId = LIVE.size ? requestAnimationFrame(tick) : 0;
}
export function track(j) {
  j.visible = true; j.svg.__jelly = j; LIVE.add(j); io?.observe(j.svg);
  if (!rafId) { lastT = performance.now(); rafId = requestAnimationFrame(tick); }
  return j;
}
export function untrack(j) { LIVE.delete(j); io?.unobserve(j.svg); }

/* ---------- a still frame as SVG markup (message avatars, toasts, pickers) ---------- */
const NS = 'http://www.w3.org/2000/svg';
export function snapshot(look, expr = 'idle', { crop = true, ground = false } = {}) {
  const svg = document.createElementNS(NS, 'svg');
  const j = new Jelly(svg, { ...lookOpts(look), expr });
  for (let i = 0; i < 2; i++) j.frame(1 / 60);
  if (!ground) [j.E.shadow, j.E.caustic].forEach(e => e.setAttribute('opacity', 0));
  if (crop) svg.setAttribute('viewBox', '-142 -146 284 284');
  svg.setAttribute('aria-hidden', 'true');
  return svg.outerHTML;
}

export { SHAPES, THEMES, EXPR, ORDER, XG_COLORS, clamp, lerp };
