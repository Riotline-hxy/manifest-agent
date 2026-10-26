// 小光的形象：一枚自绘的光球。
// 刻意不依赖任何第三方角色素材（原先的 emotion-ball 仅限非商业使用），
// 用 SVG 渐变 + 呼吸节奏表达「在想 / 在说 / 在听」三种状态。

const STATES = {
  idle:    { breathe: 5.2, glow: 0.55, ripple: 0 },
  listen:  { breathe: 3.4, glow: 0.7, ripple: 0 },
  think:   { breathe: 2.2, glow: 0.85, ripple: 1 },
  speak:   { breathe: 1.6, glow: 1.0, ripple: 0 },
};

let uid = 0;

export function orb(state = "idle", { size = "md", hue } = {}) {
  const id = `orb${++uid}`;
  const cfg = STATES[state] || STATES.idle;
  const wrap = document.createElement("div");
  wrap.className = `orb-wrap ${size === "lg" ? "lg" : size === "sm" ? "sm" : ""}`;
  wrap.dataset.state = state;
  if (hue) wrap.style.setProperty("--orb-hue", hue);
  wrap.innerHTML = `
    <svg viewBox="0 0 120 120" width="100%" height="100%" role="img" aria-label="小光">
      <defs>
        <radialGradient id="${id}-core" cx="42%" cy="36%" r="70%">
          <stop offset="0%" stop-color="#8fb9a6"/>
          <stop offset="45%" stop-color="#3f7d68"/>
          <stop offset="100%" stop-color="#1f4a3c"/>
        </radialGradient>
        <radialGradient id="${id}-halo" cx="50%" cy="50%" r="50%">
          <stop offset="55%" stop-color="rgba(47,107,88,0.28)"/>
          <stop offset="100%" stop-color="rgba(47,107,88,0)"/>
        </radialGradient>
        <filter id="${id}-blur"><feGaussianBlur stdDeviation="2.4"/></filter>
      </defs>
      <circle cx="60" cy="60" r="56" fill="url(#${id}-halo)"/>
      <g class="orb-body" style="transform-origin:60px 60px;animation-duration:${cfg.breathe}s">
        <ellipse cx="60" cy="72" rx="30" ry="8" fill="rgba(26,24,20,.14)" filter="url(#${id}-blur)"/>
        <circle cx="60" cy="58" r="31" fill="url(#${id}-core)"/>
        <ellipse cx="50" cy="46" rx="11" ry="7.5" fill="rgba(255,255,255,.42)" transform="rotate(-22 50 46)"/>
        <ellipse cx="73" cy="68" rx="5" ry="3.4" fill="rgba(255,255,255,.16)"/>
        <circle class="orb-eye l" cx="53" cy="60" r="2.6" fill="rgba(250,247,241,.94)"/>
        <circle class="orb-eye r" cx="68" cy="60" r="2.6" fill="rgba(250,247,241,.94)"/>
        <path class="orb-mouth" d="M56 68q4.5 3.4 9 0" stroke="rgba(250,247,241,.8)" stroke-width="1.9"
              fill="none" stroke-linecap="round"/>
      </g>
      <circle class="orb-ripple" cx="60" cy="60" r="31" fill="none"
              stroke="rgba(47,107,88,.35)" stroke-width="1"
              style="transform-origin:60px 60px;opacity:${cfg.ripple ? 1 : 0}"/>
      <circle class="orb-spark" cx="96" cy="30" r="1.8" fill="#a87c38"/>
      <circle class="orb-spark s2" cx="24" cy="40" r="1.2" fill="#a87c38"/>
    </svg>`;
  return wrap;
}

const css = `
.orb-wrap { position: relative; aspect-ratio: 1; }
.orb-body { animation-name: orb-breathe; animation-timing-function: cubic-bezier(.4,0,.6,1); animation-iteration-count: infinite; }
@keyframes orb-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.045); } }
.orb-ripple { animation: orb-ripple 3.2s ease-out infinite; }
@keyframes orb-ripple { 0% { transform: scale(.82); opacity: .0; } 35% { opacity: .55; } 100% { transform: scale(1.35); opacity: 0; } }
.orb-spark { animation: orb-spark 4s ease-in-out infinite; }
.orb-spark.s2 { animation-delay: 1.7s; animation-duration: 5.2s; }
@keyframes orb-spark { 0%,100% { opacity: .25; transform: translateY(0); } 50% { opacity: .9; transform: translateY(-3px); } }
.orb-wrap[data-state="think"] .orb-eye { animation: orb-think-eye 1.4s ease-in-out infinite; }
@keyframes orb-think-eye { 50% { opacity: .45; } }
.orb-wrap[data-state="speak"] .orb-mouth { animation: orb-mouth .9s ease-in-out infinite; transform-origin: 60px 68px; }
@keyframes orb-mouth { 50% { transform: scaleY(.45); } }
`;

let installed = false;
export function installOrbStyles() {
  if (installed) return;
  installed = true;
  const el = document.createElement("style");
  el.textContent = css;
  document.head.append(el);
}
