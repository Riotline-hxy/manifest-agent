// 动效与庆祝：彩纸、经验飞入、数字滚动、进化 / 徽章 / 宝箱 全屏庆祝。
// 庆祝事件来自服务端的一次性标记（growth.evolved / growth.badges_new），
// 所以只会在真实发生时出现一次，不是前端自己演出来的。

import { esc } from "./ui.js";

export const art = (name) => `assets/art/${name}.webp`;

// ---------------------------------------------------------------- 彩纸 ----
let canvas, ctx, parts = [], running = false;
const COLORS = ["#f7cb4d", "#7ed957", "#ff93b5", "#8ccbf0", "#ae9dff", "#fffbe6"];

export function confetti(x = innerWidth / 2, y = innerHeight / 2, n = 90, spread = 1) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.className = "fx-canvas";
    Object.assign(canvas.style, { position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 500 });
    document.body.append(canvas);
    ctx = canvas.getContext("2d");
  }
  canvas.width = innerWidth * devicePixelRatio;
  canvas.height = innerHeight * devicePixelRatio;
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.1 * spread;
    const v = 6 + Math.random() * 9;
    parts.push({
      x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 2,
      w: 6 + Math.random() * 7, h: 4 + Math.random() * 6,
      r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4,
      c: COLORS[(Math.random() * COLORS.length) | 0], life: 0, star: Math.random() < 0.22,
    });
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
    if (p.star) {
      ctx.beginPath();
      for (let k = 0; k < 8; k++) {
        const rr = (k % 2 ? 2.5 : 7) * d, aa = (k * Math.PI) / 4;
        ctx.lineTo(Math.cos(aa) * rr, Math.sin(aa) * rr);
      }
      ctx.fill();
    } else {
      ctx.fillRect((-p.w / 2) * d, (-p.h / 2) * d, p.w * d, p.h * d);
    }
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

// ---------------------------------------------------------- 经验飞入 ----
export function flyXP(from, amount, target = document.querySelector("[data-xp-target]")) {
  if (!amount) return;
  const a = from?.getBoundingClientRect?.() || { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };
  const b = target?.getBoundingClientRect?.();
  const el = document.createElement("div");
  el.className = "xp-fly";
  el.innerHTML = `<span>+${amount}</span><small>XP</small>`;
  document.body.append(el);
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2;
  el.style.left = x0 + "px"; el.style.top = y0 + "px";
  if (!b) {
    el.animate([{ transform: "translate(-50%,-50%) scale(.6)", opacity: 0 }, { transform: "translate(-50%,-140%) scale(1.15)", opacity: 1, offset: 0.35 }, { transform: "translate(-50%,-260%) scale(1)", opacity: 0 }],
      { duration: 1300, easing: "cubic-bezier(.22,.61,.36,1)" }).onfinish = () => el.remove();
    return;
  }
  const dx = b.left + b.width / 2 - x0, dy = b.top + b.height / 2 - y0;
  el.animate([
    { transform: "translate(-50%,-50%) scale(.5)", opacity: 0 },
    { transform: "translate(-50%,-120%) scale(1.25)", opacity: 1, offset: 0.25 },
    { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(.6)`, opacity: 0.9 },
  ], { duration: 1100, easing: "cubic-bezier(.5,0,.3,1)" }).onfinish = () => {
    el.remove();
    target.classList.remove("bump"); void target.offsetWidth; target.classList.add("bump");
  };
}

// ---------------------------------------------------------- 数字滚动 ----
export function countUp(el, to, ms = 900) {
  if (!el) return;
  const from = Number(el.dataset.v ?? el.textContent.replace(/\D/g, "")) || 0;
  el.dataset.v = to;
  if (from === to) { el.textContent = to; return; }
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / ms);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (to - from) * e);
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
  const fn = { evolve: showEvolve, badge: showBadge, chest: showChest }[item.kind];
  fn ? fn(item.data, () => setTimeout(next, 250)) : next();
}

function overlay(inner, cls = "") {
  const o = document.createElement("div");
  o.className = `celebrate ${cls}`;
  o.innerHTML = `<div class="cel-rays"></div><div class="cel-body">${inner}</div>`;
  document.body.append(o);
  return o;
}

function closeOverlay(o, done) {
  o.classList.add("out");
  setTimeout(() => { o.remove(); done(); }, 320);
}

function showEvolve(d, done) {
  const from = d.from === "egg" ? "pet-egg" : d.from === "baby" ? "pet-baby" : `pet-${d.from}`;
  const o = overlay(`
    <div class="evo-stage">
      <img class="evo-from" src="${art(from)}" alt="">
      <img class="evo-to" src="${art(d.art)}" alt="">
      <div class="evo-flash"></div>
    </div>
    <div class="cel-kicker">进化</div>
    <h2>小芽长成了「${esc(d.name)}」</h2>
    ${d.branch_name ? `<p>${esc(d.branch_name)} · ${esc(d.tag)}</p>` : `<p>它在悄悄长大。</p>`}
    <button class="btn btn-lamp btn-lg btn-shine" data-ok>太好了</button>`, "evolve");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.42, 140, 1.3), 1500);
  o.querySelector("[data-ok]").addEventListener("click", () => closeOverlay(o, done));
}

const BADGE_ART = {
  chat: "st-letter", memory: "st-mirror", moon: "st-moon", flag: "st-flag", star: "st-jar", sun: "st-seed",
  lotus: "st-lotus", compass: "st-compass", book: "st-book", report: "st-letter", egg: "pet-egg", spark: "st-steps",
};
export const badgeArt = (icon) => art(BADGE_ART[icon] || "st-seed");

function showBadge(b, done) {
  const o = overlay(`
    <div class="medal big earned pop-medal"><span class="medal-ring"></span><img src="${badgeArt(b.icon)}" alt=""></div>
    <div class="cel-kicker">新徽章 · ${esc(b.cat)}</div>
    <h2>${esc(b.name)}</h2>
    <p>${esc(b.how)}</p>
    <button class="btn btn-lamp btn-lg" data-ok>收下</button>`, "badge");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.38, 70), 350);
  o.querySelector("[data-ok]").addEventListener("click", () => closeOverlay(o, done));
}

function showChest(d, done) {
  const o = overlay(`
    <div class="chest-stage"><img class="chest-closed" src="${art("st-chest")}" alt=""><img class="chest-open" src="${art("st-chest-open")}" alt=""></div>
    <div class="cel-kicker">今日任务</div>
    <h2>四件小事都做到了</h2>
    <p>行动、好消息、练习、来聊天——今天的小芽吃得很饱。</p>
    <button class="btn btn-lamp btn-lg" data-ok>明天见</button>`, "chest");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.4, 110), 900);
  o.querySelector("[data-ok]").addEventListener("click", () => closeOverlay(o, done));
}

// ---------------------------------------------------------- 背景场景 ----
export function buildScene() {
  if (document.querySelector(".scene")) return;
  const s = document.createElement("div");
  s.className = "scene";
  s.setAttribute("aria-hidden", "true");
  let html = '<div class="ray r1"></div><div class="ray r2"></div><div class="ray r3"></div><div class="ray r4"></div>'
    + '<div class="hill h1"></div><div class="hill h2"></div>';
  for (let i = 0; i < 26; i++) {
    const left = Math.random() * 100, bottom = Math.random() * 40 - 10;
    const dur = 14 + Math.random() * 18, delay = -Math.random() * dur;
    html += `<i class="dust" style="left:${left}%;bottom:${bottom}%;--dx:${(Math.random() - 0.5) * 120}px;animation-duration:${dur}s;animation-delay:${delay}s;opacity:${0.3 + Math.random() * 0.6}"></i>`;
  }
  const sp = [[63, 13], [70, 34], [86, 30], [92, 62], [55, 52], [12, 20]];
  for (const [l, t] of sp) html += `<i class="sparkle" style="left:${l}%;top:${t}%;animation-delay:${-Math.random() * 3}s"></i>`;
  s.innerHTML = html;
  document.body.prepend(s);
}
