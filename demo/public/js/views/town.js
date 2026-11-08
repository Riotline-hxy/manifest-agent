// 我的小镇：上面是小镇本身（点建筑看它的故事，放大后可以拖动），下面是商店 / 仓库 / 成长账本。
// 买和放是一步：在商店点一样东西，再点一块空地。金币只在后端扣，同一次点击重发不会扣两次。
// 手机上点一块地先出现预览，再点一次（或点「放在这里」）才真的放下，免得手滑。
import { api } from "../api.js";
import { state, setData, subscribe } from "../store.js";
import { esc, icon, tile, toast, sheet, h, fmtDay } from "../ui.js";
import { confetti } from "../fx.js";
import { openRules } from "../rules.js";
import { agentMini } from "../ball.js";
import { townSVG, itemArt, townBox as boxOf, headroom, cellAt, cellPoint, COIN_SVG, guideLines, itemName, kindOf, cellsOf } from "../town.js";

// 小镇的取景框：上方的天空按最高的那栋留，不多留
const townBox = () => { const t = state.data.town; return boxOf(t.size, { top: headroom(t) }); };

const SHOP_CATS = [["all", "全部"], ["build", "建筑"], ["nature", "自然"], ["road", "道路"], ["decor", "装饰"]];
const KEEP_GOING = new Set(["nature", "road", "decor"]);   // 这些便宜的小东西可以连着放好几个
const SRC = { action: "行动", good: "瞬间", practice: "练习", checkin: "陪伴", daily: "每日任务", first: "礼物", migrate: "开镇", buy: "建造",
  milestone: "里程碑", record: "记录" };
const md = (s) => `${+s.slice(5, 7)}月${+s.slice(8, 10)}日`;
const coarse = () => matchMedia("(pointer: coarse)").matches;
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const ui = { tab: "shop", cat: "all", mode: null, ghost: null, fresh: "", view: null, size: 0, say: 0, busy: false, nonce: null,
  drawn: false, welcomed: false };
let mounted = null, subbed = false;

// 别处（面板里勾了一个小步、升级了……）改了数据，这一页跟着重画；只订阅一次，离开这一页就什么都不做
function onData() {
  if (state.route !== "town" || !mounted) { ui.drawn = false; ui.mode = null; ui.ghost = null; return; }
  if (state.data !== ui.data) renderTown(mounted);
}

export function renderTown(root) {
  mounted = root;
  if (!subbed) { subbed = true; subscribe(onData); }
  bindKeys();
  const d = state.data;
  ui.data = d;
  const t = d.town, g = d.growth;
  if (!t || !g) return;
  const key = townBox().join(",");
  if (ui.box !== key) { ui.view = null; ui.box = key; }
  root.innerHTML = `
    <div class="view-inner wide town-page ${ui.drawn ? "again" : ""}">
      <div class="page-head"><div><h1 class="tn-name">${esc(t.name)}<button class="icon-btn sm" data-rename aria-label="给小镇改名" title="改个名字">${icon("edit")}</button></h1>
        <p>做成的每件小事，都在这里盖起来</p></div>
        <button class="btn btn-ghost btn-sm" data-rules>${icon("list")}怎么算的</button></div>
      <div class="tn-stats">${statsHTML(t, g)}</div>
      <section class="tn-scene card">
        <div class="tn-stage"></div>
        <div class="tn-guide"><button class="tn-av" data-say aria-label="听小光说一句">${agentMini()}</button><p class="tn-bubble" aria-live="polite"></p></div>
        <div class="tn-zoom"><button class="icon-btn sm" data-zoom="1.5" aria-label="放大">${icon("plus")}</button><button class="icon-btn sm" data-zoom="0.66" aria-label="缩小">${icon("minus")}</button></div>
        <div class="tn-mode" aria-live="polite"></div>
      </section>
      <div class="tabs tn-tabs" role="tablist">${[["shop", "商店"], ["store", `仓库${t.warehouse.length ? ` · ${t.warehouse.length}` : ""}`], ["ledger", "成长账本"]]
        .map(([k, l]) => `<button role="tab" data-tab="${k}" class="${ui.tab === k ? "on" : ""}">${l}</button>`).join("")}<span class="ind"></span></div>
      <div class="tn-body"></div>
    </div>`;
  ui.drawn = true;
  drawStage(root);
  drawMode(root);
  drawGuide(root);
  drawBody(root);
  bindStage(root);
  const tabs = root.querySelector(".tn-tabs");
  requestAnimationFrame(() => placeTab(tabs));
  tabs.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    ui.tab = b.dataset.tab;
    tabs.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
    placeTab(tabs);
    drawBody(root);
  }));
  root.querySelector("[data-rename]").addEventListener("click", () => renameSheet());
  root.querySelector("[data-rules]").addEventListener("click", () => openRules());
  root.querySelector("[data-say]").addEventListener("click", () => { ui.say++; drawGuide(root, true); });
  root.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => zoomBy(root, +b.dataset.zoom)));
  if (t.welcome && !ui.welcomed) { ui.welcomed = true; setTimeout(() => welcomeSheet(t), 380); }
}

function placeTab(tabs) {
  const on = tabs?.querySelector("button.on");
  if (on) Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
}

function statsHTML(t, g) {
  const lv = g.level, nx = t.next;
  return `
    <div class="tn-stat lv"><span class="lvl" style="--p:${Math.round(lv.pct * 100)}"><b>${lv.lv}</b></span>
      <div><b>Lv ${lv.lv}</b><small>再 ${lv.to_next} 经验升级</small></div></div>
    <div class="tn-stat coin">${COIN_SVG}<div><b class="num">${g.coins}</b><small>金币${g.coins_today ? ` · 今天 +${g.coins_today}` : ""}</small></div></div>
    <div class="tn-stat next">${tile("sparkles", "var(--c-violet)", 32)}<div>${nx
      ? `<b>Lv ${nx.lv} 解锁</b><small>${esc([...nx.items, ...(nx.land ? [`${nx.land}×${nx.land} 的地`] : [])].join("、"))}</small>`
      : `<b>都解锁了</b><small>以后还会有新东西</small>`}</div></div>`;
}

// ---------------------------------------------------------------- 小镇舞台 ----
const inLand = (t, c) => c && c.x >= 0 && c.y >= 0 && c.x < t.size && c.y < t.size;
// 哪一样东西盖着这一格（大建筑占好几格）
const occupant = (t, c, skip = "") => (t.items || []).find((i) => i.id !== skip && cellsOf(i).some(([x, y]) => x === c.x && y === c.y));
const modeKind = (t) => ui.mode?.type === "buy" ? ui.mode.kind : (t.items.concat(t.warehouse).find((i) => i.id === ui.mode?.id) || {}).kind;
const square = (kind) => { const [w, d] = kindOf(kind).size; return w === d; };

function ghostFor(t) {
  if (!ui.mode || !ui.ghost || !inLand(t, ui.ghost)) return null;
  const g = { kind: modeKind(t), x: ui.ghost.x, y: ui.ghost.y, rot: ui.mode.rot || 0 };
  g.ok = cellsOf(g).every(([x, y]) => inLand(t, { x, y }) && !occupant(t, { x, y }, ui.mode.id || ""));
  return g;
}

function drawStage(root) {
  const t = state.data.town;
  const stage = root.querySelector(".tn-stage");
  if (!stage) return;
  const base = townBox();
  stage.innerHTML = townSVG(t, { ghost: ghostFor(t), grid: !!ui.mode, fresh: ui.fresh, hide: ui.mode?.type === "move" ? ui.mode.id : "", top: -base[1] - 16 });
  stage.style.aspectRatio = `${base[2]} / ${base[3]}`;
  if (!ui.view || ui.view.base !== base.join(",")) ui.view = Object.assign([...base], { base: base.join(",") });
  applyView(root);
  ui.fresh = "";
}

function applyView(root) {
  const svg = root.querySelector(".tn-stage svg");
  if (!svg || !ui.view) return;
  svg.setAttribute("viewBox", ui.view.slice(0, 4).map((n) => Math.round(n * 10) / 10).join(" "));
  const zoomed = ui.view[2] < townBox()[2] * 0.98;
  root.querySelector(".tn-stage").classList.toggle("zoomed", zoomed);
}

function clampView(v, base) {
  const w = Math.min(base[2], Math.max(base[2] / 3, v[2])), k = w / v[2], hgt = v[3] * k;
  const cx = Math.min(base[0] + base[2], Math.max(base[0], v[0] + v[2] / 2));
  const cy = Math.min(base[1] + base[3], Math.max(base[1], v[1] + v[3] / 2));
  return w >= base[2] ? [...base] : [cx - w / 2, cy - hgt / 2, w, hgt];
}

function svgPoint(root, cx, cy) {
  const svg = root.querySelector(".tn-stage svg");
  const m = svg?.getScreenCTM();
  if (!m) return null;
  const pt = svg.createSVGPoint();
  pt.x = cx; pt.y = cy;
  return pt.matrixTransform(m.inverse());
}

// k > 1 放大。围着 (cx, cy) 这一点缩放；不给就围着中心
function zoomBy(root, k, cx, cy) {
  const base = townBox(), v = ui.view || base;
  const w = Math.min(base[2], Math.max(base[2] / 3, v[2] / k)), s = w / v[2];
  const r = root.querySelector(".tn-stage").getBoundingClientRect();
  const a = svgPoint(root, cx ?? r.left + r.width / 2, cy ?? r.top + r.height / 2) || { x: v[0] + v[2] / 2, y: v[1] + v[3] / 2 };
  ui.view = Object.assign(clampView([a.x - (a.x - v[0]) * s, a.y - (a.y - v[1]) * s, w, v[3] * s], base), { base: base.join(",") });
  applyView(root);
}

function bindStage(root) {
  const stage = root.querySelector(".tn-stage");
  const ptrs = new Map();
  let drag = null, pinch = null;
  const dist = () => { const [a, b] = [...ptrs.values()]; return Math.hypot(a.x - b.x, a.y - b.y) || 1; };
  stage.addEventListener("pointerdown", (e) => {
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (ptrs.size === 1) drag = { x: e.clientX, y: e.clientY, v: [...(ui.view || townBox())], moved: false };
    if (ptrs.size === 2 && stage.classList.contains("zoomed")) { pinch = { d: dist(), v: ui.view }; drag = null; }
  });
  stage.addEventListener("pointermove", (e) => {
    if (ptrs.has(e.pointerId)) ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      ui.view = pinch.v;
      zoomBy(root, dist() / pinch.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
      return;
    }
    if (drag && ptrs.size === 1) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) > 6 && stage.classList.contains("zoomed")) { drag.moved = true; stage.setPointerCapture?.(e.pointerId); }
      if (drag.moved) {
        const r = stage.getBoundingClientRect(), k = drag.v[2] / r.width;
        const base = townBox();
        ui.view = Object.assign(clampView([drag.v[0] - dx * k, drag.v[1] - dy * k, drag.v[2], drag.v[3]], base), { base: base.join(",") });
        applyView(root);
        return;
      }
    }
    if (ui.mode && e.pointerType === "mouse" && !ptrs.size) hover(root, e);
  });
  const end = (e) => {
    const wasTap = drag && !drag.moved && !pinch && ptrs.size === 1 && e.type === "pointerup";
    ptrs.delete(e.pointerId);
    if (ptrs.size < 2) pinch = null;
    if (wasTap) tap(root, e);
    if (!ptrs.size) drag = null;
  };
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
  stage.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && ui.mode && ui.ghost) { ui.ghost = null; drawStage(root); drawMode(root); } });
  stage.addEventListener("wheel", (e) => {   // 触控板捏合 / Ctrl + 滚轮才缩放，普通滚动照常翻页
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoomBy(root, Math.exp(-e.deltaY * 0.01), e.clientX, e.clientY);
  }, { passive: false });
}

function hover(root, e) {
  const t = state.data.town;
  const c = cellAt(root.querySelector(".tn-stage svg"), e.clientX, e.clientY);
  const next = inLand(t, c) ? c : null;
  if ((next?.x ?? -9) === (ui.ghost?.x ?? -9) && (next?.y ?? -9) === (ui.ghost?.y ?? -9)) return;
  ui.ghost = next;
  drawStage(root);
  drawMode(root);
}

function tap(root, e) {
  const t = state.data.town;
  if (ui.mode) {
    const c = cellAt(root.querySelector(".tn-stage svg"), e.clientX, e.clientY);
    if (!inLand(t, c)) return;
    const same = ui.ghost && ui.ghost.x === c.x && ui.ghost.y === c.y;
    if (e.pointerType !== "mouse" && !same) { ui.ghost = c; drawStage(root); drawMode(root); return; }
    ui.ghost = c;
    return placeAt(root, c);
  }
  const el = e.target.closest?.("[data-id]");
  if (el && el.dataset.id !== "ghost") return openItem(root, el.dataset.id);
  const c = cellAt(root.querySelector(".tn-stage svg"), e.clientX, e.clientY);   // 路贴在地上，没有自己的图，按格子找
  const hit = c && occupant(t, c);
  if (hit) openItem(root, hit.id);
}

// ---------------------------------------------------------------- 放置 ----
function startMode(root, mode) {
  if (mode.type === "move" && mode.rot == null) {
    const t = state.data.town;
    mode.rot = (t.items.concat(t.warehouse).find((i) => i.id === mode.id) || {}).rot || 0;
  }
  ui.mode = mode;
  ui.ghost = null;
  drawStage(root);
  drawMode(root);
  const scene = root.querySelector(".tn-scene");
  const r = scene.getBoundingClientRect();
  if (r.top < 60 || r.bottom > innerHeight) scene.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
}

function endMode(root) {
  ui.mode = null;
  ui.ghost = null;
  drawStage(root);
  drawMode(root);
}

function drawMode(root) {
  const box = root.querySelector(".tn-mode");
  const scene = root.querySelector(".tn-scene");
  if (!box) return;
  scene.classList.toggle("placing", !!ui.mode);
  if (!ui.mode) { box.innerHTML = ""; return; }
  const t = state.data.town, m = ui.mode, kind = modeKind(t);
  const it = t.catalog.find((c) => c.id === kind);
  const g = ghostFor(t);
  const rot = m.rot || 0;
  const hint = g ? (g.ok ? (coarse() ? "再点一下就放下" : "点一下放下") : "这里有东西了") : "点一块空地";
  box.innerHTML = `<span class="tm-art">${itemArt(kind, { name: t.name, rot })}</span>
    <span class="tm-t"><b>${m.type === "buy" ? `${esc(it?.name || "")}<span class="tm-price">${COIN_SVG}${it?.price ?? ""}</span>` : `把「${esc(itemName(t, kind))}」放到哪儿？`}</b><small>${hint}</small></span>
    ${square(kind) ? "" : `<button class="icon-btn sm" data-turn title="转个方向（R）" aria-label="转个方向">${icon("turn")}</button>`}
    ${g?.ok && coarse() ? `<button class="btn btn-main btn-sm" data-place>放在这里</button>` : ""}
    <button class="btn btn-ghost btn-sm" data-cancel>${m.keep ? "完成" : "取消"}</button>`;
  box.querySelector("[data-cancel]").addEventListener("click", () => endMode(root));
  box.querySelector("[data-turn]")?.addEventListener("click", () => turn(root));
  box.querySelector("[data-place]")?.addEventListener("click", () => placeAt(root, ui.ghost));
}

const nonce = () => "n" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

// 长条的建筑可以转 90°
function turn(root) {
  if (!ui.mode || square(modeKind(state.data.town))) return;
  ui.mode = { ...ui.mode, rot: ui.mode.rot ? 0 : 1 };
  drawStage(root);
  drawMode(root);
}
let keysBound = false;
function bindKeys() {
  if (keysBound) return;
  keysBound = true;
  document.addEventListener("keydown", (e) => {
    if (state.route !== "town" || !ui.mode || !mounted || e.target.closest?.("input, textarea")) return;
    if (e.key === "r" || e.key === "R") turn(mounted);
    if (e.key === "Escape") endMode(mounted);
  });
}

async function placeAt(root, c) {
  const t = state.data.town, m = ui.mode;
  if (!m || ui.busy || !inLand(t, c)) return;
  const kind = modeKind(t);
  const g = { kind, x: c.x, y: c.y, rot: m.rot || 0 };
  if (!cellsOf(g).every(([x, y]) => inLand(t, { x, y }))) { toast("这块地放不下"); return; }
  if (cellsOf(g).some(([x, y]) => occupant(t, { x, y }, m.id || ""))) { toast("这里有东西了"); return; }
  ui.busy = true;
  try {
    let out;
    if (m.type === "buy") {
      const key = `${kind}@${c.x},${c.y}:${g.rot}`;   // 网络断了再点同一块地：沿用同一个请求号，后端只扣一次
      if (ui.nonce?.key !== key) ui.nonce = { key, v: nonce() };
      out = await api.town("buy", { kind, x: c.x, y: c.y, rot: g.rot, nonce: ui.nonce.v });
      ui.nonce = null;
      const item = t.catalog.find((x) => x.id === kind);
      const keep = KEEP_GOING.has(item.cat) && item.size[0] * item.size[1] === 1 && out.growth.coins >= item.price;   // 便宜的 1×1 小东西才连着放
      ui.mode = keep ? { ...m, keep: true } : null;
      ui.fresh = out.built.id;
      ui.sayNow = out.built.again ? "" : item.cat === "build"
        ? `「${item.name}」盖好了${out.built.story?.text ? `。这是你${out.built.story.text}之后盖的` : ""}。`
        : (!m.keep ? `「${item.name}」放好了。${keep ? "还想再放，就接着点空地。" : ""}` : "");
    } else {
      out = await api.town("move", { id: m.id, x: c.x, y: c.y, rot: g.rot });
      ui.mode = null;
      ui.fresh = out.moved.id;
      ui.sayNow = `「${itemName(t, kind)}」挪好了。`;
    }
    ui.ghost = null;
    setData(out);          // 这一页订阅了数据，会自己重画
    const svg = root.querySelector(".tn-stage svg");
    const p = cellPoint(svg, c.x, c.y, 18);
    const cat = t.catalog.find((x) => x.id === kind)?.cat;
    if (p && m.type === "buy" && !out.built.again) confetti(p.x, p.y, cat === "build" ? 70 : 18, cat === "build" ? 0.9 : 0.5);
  } catch (e) {
    if (e.status && e.status < 500) ui.nonce = null;
    toast(e.message, "err");
  } finally {
    ui.busy = false;
  }
}

// ---------------------------------------------------------------- 小光的气泡 ----
function drawGuide(root, bump = false) {
  const el = root.querySelector(".tn-bubble");
  if (!el) return;
  const lines = guideLines(state.data.town, state.data.growth);
  const text = ui.sayNow || lines[ui.say % lines.length];
  ui.sayNow = "";
  el.textContent = text;
  if (bump) { el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop"); }
}

// ---------------------------------------------------------------- 下面三栏 ----
function drawBody(root) {
  const body = root.querySelector(".tn-body");
  if (!body) return;
  ({ shop: shopTab, store: storeTab, ledger: ledgerTab })[ui.tab](body, root);
}

function shopTab(body, root) {
  const t = state.data.town, coins = state.data.growth.coins;
  const list = t.catalog.filter((c) => ui.cat === "all" || c.cat === ui.cat)
    .sort((a, b) => (a.unlocked === b.unlocked ? 0 : a.unlocked ? -1 : 1) || a.lv - b.lv || a.price - b.price);
  body.innerHTML = `
    <div class="tn-cats">${SHOP_CATS.map(([k, l]) => `<button class="chip ${ui.cat === k ? "on" : ""}" data-cat="${k}">${l}</button>`).join("")}</div>
    <div class="shop-grid">${list.map((c, i) => {
      const poor = c.unlocked && c.price > coins;
      return `<button class="shop-it ${c.unlocked ? "" : "locked"} ${poor ? "poor" : ""} ${ui.mode?.kind === c.id ? "on" : ""}" data-kind="${c.id}" style="--i:${i}" title="${esc(c.desc)}">
        <span class="si-art">${itemArt(c.id, { name: t.name })}</span>
        <b>${esc(c.name)}</b>${c.size[0] * c.size[1] > 1 ? `<span class="si-size">${c.size[0]}×${c.size[1]}</span>` : ""}
        ${c.unlocked ? `<span class="si-price">${COIN_SVG}${c.price}</span>` : `<span class="si-lock">${icon("lock")}Lv ${c.lv}</span>`}
      </button>`;
    }).join("")}</div>
`;
  body.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => { ui.cat = b.dataset.cat; shopTab(body, root); }));
  body.querySelectorAll("[data-kind]").forEach((b) => b.addEventListener("click", () => {
    const c = t.catalog.find((x) => x.id === b.dataset.kind);
    if (!c.unlocked) return toast(`「${c.name}」到 Lv${c.lv} 就能建了`, "", "lock");
    if (c.price > state.data.growth.coins) return toast(`还差 ${c.price - state.data.growth.coins} 金币`, "", "sparkles");
    startMode(root, { type: "buy", kind: c.id });
    shopTab(body, root);
  }));
}

function storeTab(body, root) {
  const t = state.data.town;
  body.innerHTML = t.warehouse.length ? `<div class="shop-grid">${t.warehouse.map((it) => `
      <button class="shop-it" data-out="${esc(it.id)}"><span class="si-art">${itemArt(it.kind, { name: t.name })}</span>
        <b>${esc(it.name)}</b><span class="si-note">${esc(it.note || md(it.created_at))}</span><span class="si-price">放出来</span></button>`).join("")}</div>`
    : `<div class="empty sm"><p>还是空的。到达里程碑时，会收到一块刻着名字的纪念碑。</p></div>`;
  body.querySelectorAll("[data-out]").forEach((b) => b.addEventListener("click", () => startMode(root, { type: "move", id: b.dataset.out })));
}

function ledgerTab(body) {
  const rows = state.data.growth.ledger || [];
  const days = [];
  for (const r of rows) {
    const k = fmtDay(r.at);
    (days.find((x) => x.k === k) || days[days.push({ k, items: [] }) - 1]).items.push(r);
  }
  body.innerHTML = rows.length ? `<div class="ledger card">${days.map((d) => `<div class="lg-day">${esc(d.k)}</div>${d.items.map((r) => `
      <div class="lg-row"><span class="pill">${esc(SRC[r.kind] || "成长")}</span><span class="lg-n">${esc(r.note || "")}</span>
        ${r.xp ? `<span class="lg-xp num">+${r.xp}<small>经验</small></span>` : ""}
        ${r.coins ? `<span class="lg-c num ${r.coins < 0 ? "neg" : ""}">${r.coins > 0 ? "+" : "−"}${Math.abs(r.coins)}${COIN_SVG}</span>` : ""}</div>`).join("")}`).join("")}</div>`
    : `<div class="empty sm"><p>还没有记录。</p></div>`;
}

// ---------------------------------------------------------------- 弹层 ----
function openItem(root, id) {
  const t = state.data.town;
  const it = t.items.find((x) => x.id === id);
  if (!it) return;
  const c = t.catalog.find((x) => x.id === it.kind) || kindOf(it.kind);
  const built = it.created_at.slice(0, 10);
  const st = it.story || {};
  let story = "";
  if (it.kind === "monument") story = `刻着「${esc(it.note)}」。${st.day ? `${md(st.day)}，你到达了这个里程碑。` : ""}`;
  else if (it.kind === "sign") story = "小镇开张那天就立在这儿了。";
  else if (st.text) story = st.day === built ? `那天你${esc(st.text)}。` : `盖它之前，你最近做成的一件事是 ${md(st.day)} ${esc(st.text)}。`;
  const body = h("div", { class: "ti-sheet", html: `
    <div class="ti-art">${itemArt(it.kind, { name: t.name, rot: it.rot })}</div>
    <p class="ti-when">${it.source === "gift" && it.kind !== "monument" ? "小镇送的" : `${md(built)} 建的`}${c ? ` · ${esc(c.desc)}` : ""}</p>
    ${story ? `<p class="ti-story">${story}</p>` : ""}` });
  const s = sheet({ title: it.name, body, sticker: "home", footer: [
    h("button", { class: "btn btn-ghost", onclick: async () => {
      try { s.close(); setData(await api.town("store", { id })); toast(`「${it.name}」收进仓库了`, "", "box"); } catch (e) { toast(e.message, "err"); }
    } }, "收进仓库"),
    h("button", { class: "btn btn-main", onclick: () => { s.close(); startMode(root, { type: "move", id }); } }, "挪个位置"),
  ] });
}

function renameSheet() {
  const t = state.data.town;
  const input = h("input", { class: "field", maxlength: "10", placeholder: "比如：晴天镇" });
  input.value = t.name === "我的小镇" ? "" : t.name;
  const save = async () => {
    try { s.close(); setData(await api.town("rename", { name: input.value })); toast("改好了", "", "home"); } catch (e) { toast(e.message, "err"); }
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
  const s = sheet({ title: "给小镇起个名字", sticker: "home", body: input,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "先不改"), h("button", { class: "btn btn-main", onclick: save }, "就叫这个")] });
  setTimeout(() => input.focus(), 60);
}

function welcomeSheet(t) {
  const w = t.welcome || {};
  const old = w.kind === "migrated";
  const body = h("div", { class: "tn-welcome", html: `
    <div class="tw-hero">${townSVG(t, { still: true })}</div>
    ${old ? `<p>小芽和徽章收起来了，换成了你自己的小镇。你的 <b>${w.xp}</b> 经验都在，小镇现在是 <b>Lv ${w.lv}</b>，过去的经验还换成了 <b>${w.coins}</b> 金币。</p>`
      : `<p>现在只是一小块地。</p>`}
    <p>每做成一件小事，都会得到经验和金币：经验让小镇升级，金币用来盖东西。${old ? "" : "做成第一件，就够盖一栋小木屋。"}</p>` });
  const done = () => api.town("welcome_seen").then((out) => setData(out, { silent: true })).catch(() => {});
  const s = sheet({ title: old ? "欢迎来到你的小镇" : "这是你的小镇", sticker: "home", body, onClose: done,
    footer: [h("button", { class: "btn btn-main", onclick: () => s.close() }, "好，去看看")] });
}
