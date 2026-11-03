// 外貌：选一个推荐的样子，或者自己搭（形状 · 颜色 · 质感）。上面的小光可以点、可以看不同表情。
import { api } from "./api.js";
import { setData } from "./store.js";
import { sheet, h, toast, esc } from "./ui.js";
import { mountBall, setAgentLook, currentLook, lookPicture } from "./ball.js";
import { LOOKS, SHAPES, THEMES, MATERIALS, XG_COLORS, parseLook, lookName } from "./jelly.js";

const FACES = [["02", "平常"], ["10", "开心"], ["14", "害羞"], ["35", "在听"], ["15", "困了"], ["20", "喜欢"]];
const pics = new Map();
const pic = (id) => pics.get(id) || (pics.set(id, lookPicture(id)), pics.get(id));
// 形状按钮上的小剪影
const silhouette = (k) => `<svg viewBox="-140 -140 280 280" aria-hidden="true"><path d="M${SHAPES[k].P.map((p) => p[0].toFixed(0) + "," + (p[1] - 6).toFixed(0)).join("L")}Z"/></svg>`;

export function openLookSheet({ onSaved } = {}) {
  let look = currentLook(), tab = parseLook(look) && LOOKS.some((l) => l.id === look) ? "preset" : "diy";
  const body = h("div", { class: "lk" });
  body.innerHTML = `
    <div class="lk-stage">
      <div class="lk-ball"></div>
      <div class="lk-name"></div>
      <div class="lk-faces">${FACES.map(([c, n], i) => `<button class="${i ? "" : "on"}" data-face="${c}">${n}</button>`).join("")}</div>
    </div>
    <div class="tabs lk-tabs">${[["preset", "推荐"], ["diy", "自己搭"]].map(([k, l]) => `<button data-tab="${k}" class="${k === tab ? "on" : ""}">${l}</button>`).join("")}<span class="ind"></span></div>
    <div class="lk-body"></div>`;
  const ball = mountBall(body.querySelector(".lk-ball"), { size: 168, agent: false, look, touch: {} });
  const name = body.querySelector(".lk-name");
  const tabs = body.querySelector(".lk-tabs");
  const placeInd = () => { const on = tabs.querySelector("button.on"); if (on) Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" }); };

  const pick = (next) => {
    if (!parseLook(next) || next === look) return;
    look = next;
    ball.setLook(look);
    draw();
  };
  const draw = () => {
    name.textContent = lookName(look);
    const L = parseLook(look);
    const lb = body.querySelector(".lk-body");
    if (tab === "preset") {
      lb.innerHTML = `<div class="lk-grid">${LOOKS.map((x) => `<button class="lk-card ${x.id === look ? "on" : ""}" data-look="${x.id}">
        <span class="lk-pic">${pic(x.id)}</span><b>${esc(x.n)}</b><small>${esc(x.h)}</small></button>`).join("")}</div>`;
    } else {
      const sw = (keys) => keys.map((k) => { const T = THEMES[k]; return `<button class="lk-sw ${k === L.color ? "on" : ""}" data-color="${k}" style="--a:${T.f0};--b:${T.f1};--c:${T.f2}"><i></i><span>${esc(T.n)}</span></button>`; }).join("");
      lb.innerHTML = `
        <div class="lk-sec">形状</div>
        <div class="lk-shapes">${Object.keys(SHAPES).map((k) => `<button class="${k === L.shape ? "on" : ""}" data-shape="${k}">${silhouette(k)}<span>${esc(SHAPES[k].n)}</span></button>`).join("")}</div>
        <div class="lk-sec">颜色 <small>小光同款</small></div>
        <div class="lk-sws">${sw(XG_COLORS)}</div>
        <div class="lk-sec">颜色 <small>更多</small></div>
        <div class="lk-sws">${sw(Object.keys(THEMES).filter((k) => !XG_COLORS.includes(k)))}</div>
        <div class="lk-sec">质感</div>
        <div class="lk-mats">${Object.keys(MATERIALS).map((k) => `<button class="${k === L.material ? "on" : ""}" data-mat="${k}"><b>${esc(MATERIALS[k].n)}</b><small>${esc(MATERIALS[k].h)}</small></button>`).join("")}</div>`;
    }
    lb.querySelectorAll("[data-look]").forEach((b) => b.addEventListener("click", () => pick(b.dataset.look)));
    lb.querySelectorAll("[data-shape]").forEach((b) => b.addEventListener("click", () => pick(`${b.dataset.shape}.${L.color}.${L.material}`)));
    lb.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => pick(`${L.shape}.${b.dataset.color}.${L.material}`)));
    lb.querySelectorAll("[data-mat]").forEach((b) => b.addEventListener("click", () => pick(`${L.shape}.${L.color}.${b.dataset.mat}`)));
  };
  tabs.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    tab = b.dataset.tab;
    tabs.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
    placeInd(); draw();
  }));
  body.querySelectorAll("[data-face]").forEach((b) => b.addEventListener("click", () => {
    body.querySelectorAll("[data-face]").forEach((x) => x.classList.toggle("on", x === b));
    ball.set(b.dataset.face, { force: true });
  }));
  draw();
  requestAnimationFrame(placeInd);

  const save = h("button", { class: "btn btn-main", onclick: async () => {
    s.close();
    if (look === currentLook()) return;
    setAgentLook(look);
    try { setData(await api.profile({ agent_avatar_id: look })); toast("小光换好外貌了"); onSaved?.(look); }
    catch (e) { toast(e.message, "err"); }
  } }, "就它了");
  const s = sheet({ title: "小光的外貌", sticker: "sparkles", body, footer: [save], onClose: () => ball.destroy() });
  s.panel.classList.add("sheet-look");
  return s;
}
