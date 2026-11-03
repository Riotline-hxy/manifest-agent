// 我的小镇：等距 2.5D 的小岛，全部是手写的 SVG（没有图片、没有引擎、没有滤镜）。
// 每样东西的画法在建筑素材库 buildings/<id>.js（服务器拼成 buildings/all.js 一次给过来），画具在 townkit.js。
// 这里只管把它们摆到地上：地面、道路、谁挡谁、放置时的预览、点在哪一格。
// 大建筑占好几格：(x, y) 是占地里 x、y 都最小的那一格，画在整块占地的中心；rot=1 时宽和深对调。
// 渐变 id 带每次渲染自己的前缀：页面上同时有好几张小镇（面板缩略图、商店图标）也不会互相串。
import { esc } from "./ui.js";
import { KIT, TW, TH, HW, HH, P, poly, line } from "./townkit.js";
import B from "./buildings/all.js";

export { P } from "./townkit.js";

// ---------------------------------------------------------------- 每样东西的元数据 ----
let KINDS = {};   // id → {name, cat, size, height, layer}，来自 bootstrap 的 town.kinds（后台里来自 admin 的 catalog）
export function setKinds(k) { if (k) KINDS = { ...KINDS, ...k }; }
export const kindOf = (kind) => KINDS[kind] || { name: kind, cat: "decor", size: [1, 1], height: 30, layer: "" };
export const footprint = (it) => { const [w, d] = kindOf(it.kind).size; return it.rot ? [d, w] : [w, d]; };
export function cellsOf(it) {
  const [w, d] = footprint(it), out = [];
  for (let i = 0; i < w; i++) for (let j = 0; j < d; j++) out.push([it.x + i, it.y + j]);
  return out;
}
const centerOf = (it) => { const [w, d] = footprint(it); return [it.x + (w - 1) / 2, it.y + (d - 1) / 2]; };
function drawKind(it, ctx) {
  const [w, d] = footprint(it);
  try { return (B[it.kind] || B.bush)({ ...KIT, w, d }, it, ctx); } catch { return ""; }
}

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

// 小镇上方要留多少天空：按最高、最靠后的那一样算
export function headroom(t) {
  let top = 24;
  for (const it of t.items || []) {
    const [cx, cy] = centerOf(it);
    top = Math.max(top, (kindOf(it.kind).height || 0) - (cx + cy) * HH + 6);
  }
  return Math.min(140, Math.ceil(top));
}

export function townBox(n, { top = 118 } = {}) {
  return [-n * HW - 26, -HH - top, n * TW + 52, n * TH + top + 52];
}

// 一样东西的图（商店、仓库、弹层、后台里用）：它的那块地 + 它自己
export function itemArt(kind, { name = "", cls = "", rot = 0 } = {}) {
  const id = `ti${++seq}-`;
  const it = { kind, x: 0, y: 0, rot };
  const [w, d] = footprint(it);
  const a = w / 2 - 0.04, b = d / 2 - 0.04;
  const ground = kindOf(kind).layer === "road"
    ? roadsSVG(new Set(["0,0"]))
    : poly([P(-a, -b), P(a, -b), P(a, b), P(-a, b)], "var(--t-grass-a)") + poly([P(-a, b), P(a, b), P(a, b, -5), P(-a, b, -5)], "var(--t-soil-a)")
      + poly([P(a, -b), P(a, b), P(a, b, -5), P(a, -b, -5)], "var(--t-soil-b)");
  const h = Math.max(14, kindOf(kind).height || 0);   // 矮的东西不留一大片空
  const half = (w + d) * 16 + 6;
  return `<svg class="town-svg item-art ${cls}" viewBox="${-half} ${-(h + 16)} ${half * 2} ${h + 16 + (w + d) * 8 + 12}" preserveAspectRatio="xMidYMax meet" aria-hidden="true">${defs(id)}${ground}<g class="tw-body">${drawKind(it, { name }).replaceAll("@@", id)}</g></svg>`;
}

// 偷懒日的小插画：夜里亮着灯的小木屋
export function napSVG() {
  const id = `tn${++seq}-`;
  return `<svg class="town-svg nap-art tw-night" viewBox="-44 -84 88 104" aria-hidden="true">${defs(id)}
    <path d="M30,-74 a9 9 0 1 0 6,15 a7 7 0 1 1 -6,-15z" fill="#ffe7a3"/>
    <path class="tw-twinkle" d="M-26,-70 l1,2.3 2.3,1 -2.3,1 -1,2.3 -1,-2.3 -2.3,-1 2.3,-1z" fill="#fff3c4"/>
    ${poly(tile(0, 0, 0.5), "var(--t-grass-a)")}${poly([P(-0.5, 0.5), P(0.5, 0.5), P(0.5, 0.5, -6), P(-0.5, 0.5, -6)], "var(--t-soil-a)")}
    ${poly([P(0.5, -0.5), P(0.5, 0.5), P(0.5, 0.5, -6), P(0.5, -0.5, -6)], "var(--t-soil-b)")}
    <g class="tw-body">${drawKind({ kind: "cottage", x: 0, y: 0 }, {}).replaceAll("@@", id)}</g>
    <g class="zzz"><text x="-30" y="-50">z</text><text x="-22" y="-60">z</text><text x="-12" y="-70">Z</text></g></svg>`;
}

/**
 * 整座小镇的 SVG。
 * t：bootstrap 里的 town；ghost：{kind, x, y, rot, ok}（放置时的预览）；grid：放置时显示格子；
 * still：静态（缩略图，不动）；fresh：刚建好的那一个 id（落下来的动画）；hide：正在挪的那一个 id。
 */
export function townSVG(t, { ghost = null, grid = false, still = false, fresh = "", hide = "", cls = "", top = headroom(t) } = {}) {
  setKinds(t.kinds);
  const id = `tw${++seq}-`;
  const n = t.size;
  const items = (t.items || []).filter((it) => it.id !== hide);
  const layer = (it) => kindOf(it.kind).layer;
  const roads = new Set(items.filter((it) => layer(it) === "road").map((it) => it.x + "," + it.y));
  const taken = new Set(items.flatMap((it) => cellsOf(it).map(([i, j]) => i + "," + j)));
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
  const mark = ghost ? cellsOf(ghost).map(([i, j]) => poly(tile(i, j, 0.47), ghost.ok ? "var(--t-ok)" : "var(--t-bad)", ' class="tw-mark"')).join("") : "";
  const depth = (it) => { const [cx, cy] = centerOf(it); return cx + cy; };
  const order = items.filter((it) => !layer(it)).sort((a, b) => depth(a) - depth(b) || a.x - b.x);
  const piece = (it, extra = "") => {
    const [sx, sy] = P(...centerOf(it));
    return `<g class="ti ${it.id === fresh ? "drop" : ""} ${extra}" data-id="${esc(it.id)}" transform="translate(${sx},${sy})"><g class="tw-body">${drawKind(it, { name: t.name })}</g></g>`;
  };
  const flats = items.filter((it) => layer(it) === "ground").map((it) => piece(it)).join("");
  const ghostRoad = ghost && ghost.ok && kindOf(ghost.kind).layer === "road" ? roadsSVG(new Set([ghost.x + "," + ghost.y])) : "";
  const ghostSVG = ghost ? piece({ id: "ghost", kind: ghost.kind, x: ghost.x, y: ghost.y, rot: ghost.rot }, `ghost ${ghost.ok ? "ok" : "bad"}`) : "";
  const body = `${defs(id)}${under}${sides}<g class="tw-ground">${g}</g>${roadsSVG(roads)}${ghostRoad}${gridSVG}${mark}${flats}${order.map((it) => piece(it)).join("")}${ghostSVG}`;
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
export const itemName = (t, kind) => (t.catalog || []).find((c) => c.id === kind)?.name || kindOf(kind).name || kind;
export const affordable = (t, coins) => (t.catalog || []).filter((c) => c.unlocked && c.cat === "build" && c.price <= coins)
  .sort((a, b) => b.price - a.price);
export const builtCount = (t) => (t.items || []).filter((i) => kindOf(i.kind).cat === "build").length;

// 面板入口下面那一行小字
export function townHint(t, g) {
  setKinds(t.kinds);
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
  for (const i of (t.items || []).filter((x) => x.story?.text && kindOf(x.kind).layer !== "road").slice(-3).reverse()) {
    out.push(i.kind === "monument" ? `这块纪念碑上刻着「${i.note}」。` : `「${i.name}」是你${i.story.text}之后盖的。`);
  }
  if ((t.warehouse || []).length) out.push(`仓库里还有 ${t.warehouse.length} 样东西。`);
  if (out.length < 2) out.push("小镇一直在这儿，不着急。");
  return out;
}
