// 瞬间：TA 留给自己的一个个瞬间（一句话，可以配一张照片），按月份贴成一面便利贴墙；有照片的像拍立得。
// 上面一排可以按愿望筛、只看有照片的；点开一张看大图、编辑、删除。以前的「好消息」换成了这里。
// 页面订阅数据：在计划页、对话里留下的瞬间，回到这里就是最新的。
import { state, setData, subscribe, xpNote } from "../store.js";
import { esc, toast, icon, tile, sheet, h } from "../ui.js";
import { burstAt, flyGain } from "../fx.js";
import { catOf } from "../journey.js";
import { openMoment, deleteMoment, photoURL, md } from "../moments.js";

// 便利贴的颜色：跟着主题的几种颜色走，每张按 id 固定一种，再歪一点点
const TINTS = ["var(--c-lemon)", "var(--c-mint)", "var(--c-sky)", "var(--c-pink)", "var(--c-violet)", "var(--c-orange)"];
const ui = { filter: "all", fresh: "", gain: null, data: null };
let mounted = null, subbed = false;

function seeded(id) {
  let x = 2166136261;
  for (const c of id) x = Math.imul(x ^ c.charCodeAt(0), 16777619);
  return () => ((x = Math.imul(x ^ (x >>> 15), 2246822507) >>> 0) / 4294967296);
}

function onData() {
  if (state.route !== "moments" || !mounted?.isConnected) return;
  if (state.data !== ui.data) renderMoments(mounted, { quiet: true });
}

const monthLabel = (ym, today) => (ym.slice(0, 4) !== today.slice(0, 4) ? `${ym.slice(0, 4)}年` : "") + `${+ym.slice(5, 7)}月`;

function note(m, i, wishes) {
  const rnd = seeded(m.id);
  const tint = TINTS[Math.floor(rnd() * TINTS.length)];
  const tilt = (rnd() * 2.4 - 1.2).toFixed(2);
  const w = wishes.find((x) => x.id === m.wish_id);
  return `<article class="note mo ${m.photo ? "has-photo" : ""} ${ui.fresh === m.id ? "fresh" : ""}" data-id="${esc(m.id)}" tabindex="0" role="button"
    aria-label="${esc(md(m.day))}：${esc(m.text)}" style="--tint:${tint};--tilt:${tilt}deg;--i:${Math.min(i, 14)}">
    ${m.photo ? `<div class="mo-img"><img src="${esc(photoURL(m.photo, true))}" alt="" loading="lazy" decoding="async"></div>` : ""}
    <p>${esc(m.text)}</p>
    <footer><time>${esc(md(m.day))}</time>${w ? `<span class="mo-w" style="--tc:${catOf(w.category).color}"><i></i>${esc(w.title)}</span>` : ""}</footer>
  </article>`;
}

export function renderMoments(root, { quiet = false } = {}) {
  mounted = root;
  if (!subbed) { subbed = true; subscribe(onData); }
  ui.data = state.data;
  const J = state.data.journey || {};
  const today = J.today || new Date().toISOString().slice(0, 10);
  const wishes = J.wishes || [];
  const all = J.moments || [];
  if (!["all", "photo"].includes(ui.filter) && !wishes.some((w) => w.id === ui.filter)) ui.filter = "all";
  const list = all.filter((m) => (ui.filter === "all" ? true : ui.filter === "photo" ? !!m.photo : m.wish_id === ui.filter));

  // 按月份分组；这个月一定有一组（第一张是「留下一个瞬间」的空便利贴）
  const groups = new Map([[today.slice(0, 7), []]]);
  for (const m of list) (groups.get(m.day.slice(0, 7)) || groups.set(m.day.slice(0, 7), []).get(m.day.slice(0, 7))).push(m);
  let i = 0;
  const wall = [...groups].map(([ym, ms], gi) => `<section class="mo-month">
      <div class="wall-head"><h2>${monthLabel(ym, today)}</h2>${ms.length ? `<span>${ms.length} 个瞬间</span>` : ""}</div>
      <div class="wall">
        ${gi === 0 ? `<button class="note note-add" data-add aria-label="留下一个瞬间">${icon("camera")}<span>${all.length ? "留下一个瞬间" : "留下第一个瞬间"}</span></button>` : ""}
        ${ms.map((m) => note(m, i++, wishes)).join("")}
      </div></section>`).join("");
  const filters = all.length ? `<div class="mo-filters" role="group" aria-label="筛选">
      <button class="chip ${ui.filter === "all" ? "on" : ""}" data-f="all">全部 <small>${all.length}</small></button>
      ${all.some((m) => m.photo) ? `<button class="chip ${ui.filter === "photo" ? "on" : ""}" data-f="photo">${icon("camera")}有照片</button>` : ""}
      ${wishes.filter((w) => all.some((m) => m.wish_id === w.id)).map((w) => `<button class="chip ${ui.filter === w.id ? "on" : ""}" data-f="${esc(w.id)}">
        ${tile(catOf(w.category).icon, catOf(w.category).color, 20)}<span>${esc(w.title)}</span></button>`).join("")}
    </div>` : "";

  root.innerHTML = `
    <div class="view-inner wide moments ${quiet ? "quiet" : ""}">
      <div class="page-head"><div><h1>瞬间</h1><p>把正在变好的自己留下来。一句话，或者一张照片。</p></div>
        <button class="btn btn-main mo-add" data-add>${icon("plus")}留下一个瞬间</button></div>
      ${filters}
      ${!all.length ? `<p class="mo-empty">今天哪一刻，你想记住？</p>` : !list.length ? `<p class="mo-empty">这里还没有瞬间。</p>` : ""}
      ${wall}
      <p class="hint-line">这面墙只有你自己看得到，照片也是。</p>
    </div>`;

  root.querySelectorAll(".mo-img img").forEach((img) => img.addEventListener("error", () => img.closest(".mo-img")?.remove()));
  root.querySelectorAll("[data-f]").forEach((b) => b.addEventListener("click", () => { ui.filter = b.dataset.f; renderMoments(root, { quiet: true }); }));
  root.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => add(wishes)));
  root.querySelectorAll(".note.mo").forEach((el) => {
    const open = () => detail(all.find((m) => m.id === el.dataset.id), wishes);
    el.addEventListener("click", open);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });

  // 刚留下的那一张：贴上去的时候轻轻一闪，经验和金币从它那儿飞出去
  if (ui.fresh) {
    const el = root.querySelector(`.note[data-id="${CSS.escape(ui.fresh)}"]`);
    const xp = ui.gain;
    ui.fresh = ""; ui.gain = null;
    if (el) setTimeout(() => { if (!el.isConnected) return; burstAt(el, 26); if (xp) flyGain(el, xp); }, 420);
  }
}

function add(wishes) {
  openMoment({
    wish: wishes.find((w) => w.id === ui.filter) || null,
    onSaved: (out) => {
      ui.fresh = out.moment?.id || "";
      ui.gain = out.xp?.amount || out.xp?.coins > 0 ? out.xp : null;
      if (ui.filter !== "all" && ui.filter !== out.moment?.wish_id) ui.filter = "all";
      if (!ui.gain) toast(xpNote(out.xp) ? `留下了 · ${xpNote(out.xp)}` : "留下了", "", "camera");
      setData(out);
    },
  });
}

// 点开一张：大图、整句话、感受、心情、愿望、日子；编辑、删除
function detail(m, wishes) {
  if (!m) return;
  const w = wishes.find((x) => x.id === m.wish_id);
  const body = h("div", { class: "mo-detail", html: `
    ${m.photo ? `<div class="mo-big"><img src="${esc(photoURL(m.photo))}" alt="这个瞬间的照片"></div>` : ""}
    <p class="mo-text">${esc(m.text)}</p>
    ${m.feeling ? `<p class="mo-feel">当时的感受：${esc(m.feeling)}</p>` : ""}
    <div class="mo-meta">
      <span class="pill">${icon("calendar")}${esc(md(m.day))}</span>
      ${w ? `<span class="pill mo-w" style="--tc:${catOf(w.category).color}"><i></i>${esc(w.title)}</span>` : ""}
      ${m.mood ? `<span class="pill">${esc(m.mood)}</span>` : ""}
      ${m.source === "chat" ? `<span class="pill">${icon("chat")}和小光聊到的</span>` : ""}
    </div>` });
  body.querySelector(".mo-big img")?.addEventListener("error", (e) => e.target.closest(".mo-big")?.remove());
  const s = sheet({ title: "这个瞬间", body, sticker: "camera", footer: [
    h("button", { class: "btn btn-quiet", onclick: async () => {
      try {
        const out = await deleteMoment(m);
        if (!out) return;
        s.close();
        setData(out);
        toast("删掉了", "", "trash");
      } catch (e) { toast(e.message, "err"); }
    } }, "删除"),
    h("button", { class: "btn btn-main", onclick: () => {
      s.close();
      openMoment({ moment: m, onSaved: (out) => { setData(out); toast("改好了", "", "camera"); } });
    } }, "编辑"),
  ] });
  s.panel.classList.add("j-sheet", "mo-detail-panel");
}
