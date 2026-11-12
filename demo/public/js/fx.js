// 动效与庆祝：彩纸、经验和金币飞入、数字滚动、升级的全屏庆祝。
// 升级来自服务端的一次性标记（growth.level_up），只会在真的升级时出现一次，不是前端自己演出来的。
import { aname } from "./store.js";
import { esc } from "./ui.js";
import { itemArt, COIN_SVG } from "./town.js";
import { visionSVG, catOf } from "./journey.js";

// ---------------------------------------------------------------- 彩纸 ----
let canvas, ctx, parts = [], running = false;
const COLORS = ["#f7cb4d", "#4fd1a5", "#ff8fb1", "#6cb8ff", "#a99bff", "#ffad4d"];

export function confetti(x = innerWidth / 2, y = innerHeight / 2, n = 90, spread = 1) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!canvas) {
    canvas = document.createElement("canvas");
    Object.assign(canvas.style, { position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 500 });
    document.body.append(canvas);
    ctx = canvas.getContext("2d");
  }
  canvas.width = innerWidth * devicePixelRatio;
  canvas.height = innerHeight * devicePixelRatio;
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.1 * spread;
    const v = 6 + Math.random() * 9;
    parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 2, w: 6 + Math.random() * 7, h: 4 + Math.random() * 6,
      r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: COLORS[(Math.random() * COLORS.length) | 0], life: 0, round: Math.random() < 0.3 });
  }
  if (!running) { running = true; requestAnimationFrame(step); }
}

function step() {
  const d = devicePixelRatio;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  parts = parts.filter((p) => p.life < 160 && p.y < innerHeight + 40);
  for (const p of parts) {
    p.life++; p.vy += 0.28; p.vx *= 0.985; p.x += p.vx; p.y += p.vy; p.r += p.vr;
    ctx.save();
    ctx.globalAlpha = Math.max(0, 1 - p.life / 160);
    ctx.translate(p.x * d, p.y * d); ctx.rotate(p.r); ctx.fillStyle = p.c;
    if (p.round) { ctx.beginPath(); ctx.arc(0, 0, 3.5 * d, 0, Math.PI * 2); ctx.fill(); }
    else ctx.fillRect((-p.w / 2) * d, (-p.h / 2) * d, p.w * d, p.h * d);
    ctx.restore();
  }
  if (parts.length) requestAnimationFrame(step);
  else { running = false; ctx.clearRect(0, 0, canvas.width, canvas.height); }
}

export function burstAt(el, n = 40) {
  const r = el?.getBoundingClientRect?.();
  if (!r) return confetti(undefined, undefined, n);
  confetti(r.left + r.width / 2, r.top + r.height / 2, n, 0.8);
}

// ---------------------------------------------------------- 经验 / 金币飞入 ----
function fly(from, html, cls, target) {
  const a = from?.getBoundingClientRect?.() || { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };
  const b = target?.getBoundingClientRect?.();
  const el = document.createElement("div");
  el.className = cls;
  el.innerHTML = html;
  document.body.append(el);
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2;
  el.style.left = x0 + "px"; el.style.top = y0 + "px";
  if (!b || !b.width) {   // 目标不在屏幕上（手机上没有等级圈）：原地往上飘
    el.animate([{ transform: "translate(-50%,-50%) scale(.6)", opacity: 0 }, { transform: "translate(-50%,-140%) scale(1.15)", opacity: 1, offset: 0.35 },
      { transform: "translate(-50%,-260%) scale(1)", opacity: 0 }], { duration: 1300, easing: "cubic-bezier(.22,.61,.36,1)" }).onfinish = () => el.remove();
    return;
  }
  const dx = b.left + b.width / 2 - x0, dy = b.top + b.height / 2 - y0;
  el.animate([{ transform: "translate(-50%,-50%) scale(.5)", opacity: 0 }, { transform: "translate(-50%,-120%) scale(1.2)", opacity: 1, offset: 0.25 },
    { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(.6)`, opacity: 0.9 }], { duration: 1100, easing: "cubic-bezier(.5,0,.3,1)" })
    .onfinish = () => { el.remove(); target.classList.remove("bump"); void target.offsetWidth; target.classList.add("bump"); };
}

export function flyXP(from, amount, target = document.querySelector("[data-xp-target]")) {
  if (amount) fly(from, `+${amount}<small>XP</small>`, "xp-fly", target);
}
export function flyCoins(from, amount, target = document.querySelector("[data-coin-target]")) {
  if (amount > 0) fly(from, `${COIN_SVG}+${amount}`, "xp-fly coin-fly", target);
}
// 一次奖励（growth.award 的回执）：经验飞向等级，金币稍后飞向金币
export function flyGain(from, r) {
  if (!r) return;
  const xp = r.amount_total ?? r.amount;
  if (xp) flyXP(from, xp);
  if (r.coins > 0) setTimeout(() => flyCoins(from, r.coins), xp ? 240 : 0);
}

// ---------------------------------------------------------- 数字滚动 ----
export function countUp(el, to, ms = 900) {
  if (!el) return;
  const from = Number(el.dataset.v ?? (el.textContent.replace(/\D/g, "") || 0)) || 0;
  el.dataset.v = to;
  if (from === to) { el.textContent = to; return; }
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / ms);
    el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ---------------------------------------------------------- 庆祝队列 ----
const queue = [];
let showing = false;
const shownKeys = new Set();

export function celebrate(kind, data, key) {
  if (key) {
    if (shownKeys.has(key)) return;
    shownKeys.add(key);
  }
  queue.push({ kind, data });
  if (!showing) next();
}

function next() {
  const item = queue.shift();
  if (!item) { showing = false; return; }
  showing = true;
  const fn = { level: showLevel, cleared: showCleared }[item.kind];
  fn ? fn(item.data, () => setTimeout(next, 250)) : next();
}

function overlay(inner, cls = "") {
  const o = document.createElement("div");
  o.className = `celebrate ${cls}`;
  o.innerHTML = `<div class="cel-rays"></div><div class="cel-body">${inner}</div>`;
  document.body.append(o);
  return o;
}
const close = (o, done) => { o.classList.add("out"); setTimeout(() => { o.remove(); done(); }, 320); };

// 一个愿望的小步都做完了：两个选择，现在就和小光想下一步，或者之后再说
function showCleared(d, done) {
  const cat = catOf(d.category);
  const o = overlay(`
    <div class="clr-art" style="color:${cat.color}">${visionSVG(d.category)}</div>
    <div class="cel-kicker">一段路走完了</div>
    <h2>「${esc(d.title)}」的小步都做完了</h2>
    <p>${d.done > 1 ? `${d.done} 步，都是你自己走完的。` : ""}要和${aname()}想想接下来几步吗？</p>
    <div class="cel-acts"><button class="btn btn-ghost btn-lg" data-ok>之后再说</button><button class="btn btn-main btn-lg" data-go>想想新的小步</button></div>`, "cleared");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.38, 90), 300);
  o.querySelector("[data-ok]").addEventListener("click", () => close(o, done));
  o.querySelector("[data-go]").addEventListener("click", () => { close(o, done); d.onNext?.(); });
}

// 升级：等级圈 + 新解锁的第一样东西
function showLevel(d, done) {
  const first = (d.unlocks || []).find((x) => x.cat === "build") || (d.unlocks || [])[0];
  const names = (d.unlocks || []).map((x) => `「${esc(x.name)}」`).join("");
  const o = overlay(`
    <div class="lv-stage"><div class="lv-ring"><small>Lv</small><b>${d.to}</b></div>${first ? `<div class="lv-art">${itemArt(first.id)}</div>` : ""}</div>
    <div class="cel-kicker">升级</div>
    <h2>小镇长到 Lv ${d.to} 了</h2>
    <p>${names ? `解锁了${names}。` : "又往前走了一步。"}${d.land ? `土地扩到了 ${d.land[1]}×${d.land[1]}。` : ""}</p>
    <div class="cel-acts"><button class="btn btn-ghost btn-lg" data-ok>好</button><button class="btn btn-main btn-lg" data-go>去小镇看看</button></div>`, "level");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.4, 110), 450);
  o.querySelector("[data-ok]").addEventListener("click", () => close(o, done));
  o.querySelector("[data-go]").addEventListener("click", () => { close(o, done); location.hash = "town"; });
}
