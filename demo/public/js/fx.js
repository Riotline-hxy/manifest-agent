// 动效与庆祝：彩纸、经验飞入、数字滚动、进化 / 徽章 / 宝箱 全屏庆祝。
// 庆祝事件来自服务端的一次性标记（growth.evolved / growth.badges_new），
// 只会在真实发生时出现一次，不是前端自己演出来的。
import { esc, icon } from "./ui.js";
import { petSVG, chestSVG } from "./pet.js";

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

// ---------------------------------------------------------- 经验飞入 ----
export function flyXP(from, amount, target = document.querySelector("[data-xp-target]")) {
  if (!amount) return;
  const a = from?.getBoundingClientRect?.() || { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };
  const b = target?.getBoundingClientRect?.();
  const el = document.createElement("div");
  el.className = "xp-fly";
  el.innerHTML = `+${amount}<small>XP</small>`;
  document.body.append(el);
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2;
  el.style.left = x0 + "px"; el.style.top = y0 + "px";
  if (!b || !b.width) {
    el.animate([{ transform: "translate(-50%,-50%) scale(.6)", opacity: 0 }, { transform: "translate(-50%,-140%) scale(1.15)", opacity: 1, offset: 0.35 },
      { transform: "translate(-50%,-260%) scale(1)", opacity: 0 }], { duration: 1300, easing: "cubic-bezier(.22,.61,.36,1)" }).onfinish = () => el.remove();
    return;
  }
  const dx = b.left + b.width / 2 - x0, dy = b.top + b.height / 2 - y0;
  el.animate([{ transform: "translate(-50%,-50%) scale(.5)", opacity: 0 }, { transform: "translate(-50%,-120%) scale(1.2)", opacity: 1, offset: 0.25 },
    { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(.6)`, opacity: 0.9 }], { duration: 1100, easing: "cubic-bezier(.5,0,.3,1)" })
    .onfinish = () => { el.remove(); target.classList.remove("bump"); void target.offsetWidth; target.classList.add("bump"); };
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

// ---------------------------------------------------------- 徽章外观 ----
export const CAT_COLOR = {
  对话: "var(--c-sky)", 计划: "var(--c-orange)", 好消息: "var(--c-lemon)", 练习: "var(--c-mint)", 记忆: "var(--c-violet)",
  学堂: "var(--c-coral)", 报告: "var(--c-pink)", 陪伴: "var(--c-sky)", 成长: "var(--c-mint)",
};
const BADGE_ICON = { chat: "chat", memory: "memory", moon: "moon", flag: "flag", star: "star", sun: "sun", lotus: "wind",
  compass: "compass", book: "book", report: "report", egg: "egg", spark: "sparkles" };
export function medal(b, big = false) {
  const p = b.earned ? 100 : Math.round(((b.got || 0) / (b.need || 1)) * 100);
  return `<div class="medal ${b.earned ? "earned" : ""} ${big ? "big" : ""}" style="--mc:${CAT_COLOR[b.cat] || "var(--accent)"};--p:${p}">
    <span class="medal-ring"></span><span class="medal-face">${b.hidden ? '<b>?</b>' : icon(BADGE_ICON[b.icon] || "star")}</span></div>`;
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
const close = (o, done) => { o.classList.add("out"); setTimeout(() => { o.remove(); done(); }, 320); };

function showEvolve(d, done) {
  const o = overlay(`
    <div class="evo-stage">
      <div class="evo-from">${petSVG(d.from === "egg" ? "egg" : d.from === "baby" ? "baby" : d.from)}</div>
      <div class="evo-to">${petSVG(d.art, { cls: "alive" })}</div>
      <div class="evo-flash"></div>
    </div>
    <div class="cel-kicker">进化</div>
    <h2>小芽长成了「${esc(d.name)}」</h2>
    <p>${d.branch_name ? `${esc(d.branch_name)} · ${esc(d.tag)}` : "它在悄悄长大。"}</p>
    <button class="btn btn-main btn-lg" data-ok>太好了</button>`, "evolve");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.42, 140, 1.3), 1500);
  o.querySelector("[data-ok]").addEventListener("click", () => close(o, done));
}

function showBadge(b, done) {
  const o = overlay(`
    <div class="pop-medal">${medal({ ...b, earned: true }, true)}</div>
    <div class="cel-kicker">新徽章 · ${esc(b.cat)}</div>
    <h2>${esc(b.name)}</h2>
    <p>${esc(b.how)}</p>
    <button class="btn btn-main btn-lg" data-ok>收下</button>`, "badge");
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.38, 70), 350);
  o.querySelector("[data-ok]").addEventListener("click", () => close(o, done));
}

function showChest(d, done) {
  const o = overlay(`
    <div class="chest-stage">${chestSVG()}</div>
    <div class="cel-kicker">今日任务</div>
    <h2>四件小事都做到了</h2>
    <p>行动、好消息、练习、来聊天——今天的小芽吃得很饱。</p>
    <button class="btn btn-main btn-lg" data-ok>明天见</button>`, "chest");
  setTimeout(() => o.querySelector(".chest")?.classList.add("open"), 700);
  setTimeout(() => confetti(innerWidth / 2, innerHeight * 0.4, 110), 950);
  o.querySelector("[data-ok]").addEventListener("click", () => close(o, done));
}
