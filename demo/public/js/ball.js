// 小光的脸：Emotion Ball 的适配层。
// 上游 github.com/sam70361/emotion-ball：引擎非商业免费，球形角色外观禁止商用；
// 本 demo 为竞赛展示，商用前换形象只需要改这个文件。引擎没加载时退回纯色圆，页面不坏。
//
// - 颜色跟着主题或用户的选择（Settings → 小光的颜色）
// - 页面上所有「小光」共享同一个心情：setAgentMood() 一处调用，处处更新
// - 消息头像 / toast 用同一颗球的静态快照，保证全站只有一种形象

const EB = () => window.EmotionBall;

export const MOOD = {
  idle: "02", curious: "03", happy: "10", puzzled: "11", sad: "12", surprised: "13", shy: "14",
  tired: "15", focused: "16", satisfied: "19", thinking: "30", receiving: "31", busy: "32",
  done: "33", error: "34", listening: "35", recall: "37", replying: "39", searching: "40",
  sleep: "00", wake: "01",
};

export const MOOD_TEXT = {
  "02": "在这儿陪着你", "03": "有点好奇", "10": "替你开心", "13": "哇", "14": "有点不好意思",
  "15": "陪你慢一点", "16": "认真听着", "19": "嗯，记下了", "30": "想一想…", "31": "收到",
  "32": "在忙", "33": "写好了", "34": "出了点小问题", "35": "在听你说", "37": "在翻我们的回忆",
  "39": "正在回你", "40": "在找资料", "12": "有点心疼你", "00": "睡着了", "01": "醒啦",
};

let agentColor = "#f7cb4d";
export const eyeFor = (c) => (luma(c) > 0.55 ? "#1c1c22" : "#ffffff");
function luma(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
}

const live = new Set();
const agents = new Set();
let mood = "02";

export function mountBall(el, { size = 96, emotion = null, idle = false, interactive = true, halo = true, agent = true } = {}) {
  el.classList.add("ball");
  el.style.width = el.style.height = size + "px";
  el.innerHTML = `${halo ? '<span class="halo"></span>' : ""}<div class="host"></div>`;
  const host = el.querySelector(".host");
  const h = { el, size, agent, emotion: emotion || (agent ? mood : "02"), engine: null };

  function build() {
    host.innerHTML = "";
    h.engine = null;
    if (EB()?.create) {
      try {
        h.engine = EB().create(host, {
          emotion: h.emotion, shape: "blob", color: agentColor, eyeColor: eyeFor(agentColor),
          eyeScale: size < 70 ? 1.4 : 1, lite: size < 70,
          idle: idle ? { standbyAfter: 90000, sleepAfter: 600000 } : false, label: "小光",
        });
        el.dataset.engine = "emotion-ball";
      } catch (e) {
        console.warn("[ball] engine failed", e);
      }
    }
    if (!h.engine) host.innerHTML = `<span class="ball-fallback" style="background:${agentColor}"></span>`;
    el.style.setProperty("--agent", agentColor);
  }
  build();

  h.set = (id) => {
    id = MOOD[id] || id;
    if (id === h.emotion) return;
    h.emotion = id;
    if (!h.engine) return;
    h.engine.setEmotion(id);
    if (id === "30") h.engine.spin(1);
    if (id === "33") h.engine.burst(24);
  };
  h.pulse = (kind = "bounce") => {
    if (!h.engine) return;
    if (kind === "bounce") h.engine.bounce();
    else if (kind === "spin") h.engine.spin(2);
    else if (kind === "burst") { h.engine.burst(30); h.engine.spin(2); }
  };
  h.gaze = (x, y) => h.engine?.setGaze(x, y);
  h.rebuild = () => { h.engine?.destroy(); build(); };
  h.destroy = () => { h.engine?.destroy(); live.delete(h); agents.delete(h); };

  if (interactive) {
    host.addEventListener("click", () => {
      const pick = ["10", "14", "19", "03", "13"][Math.floor(Math.random() * 5)];
      h.pulse(Math.random() > 0.5 ? "bounce" : "spin");
      const before = h.emotion;
      h.set(pick);
      setTimeout(() => { if (h.emotion === pick) h.set(before === pick ? "02" : before); }, 2400);
    });
  }
  live.add(h);
  if (agent) agents.add(h);
  io?.observe(el);
  return h;
}

// 页面上所有小光一起换心情；名字下面的状态文字也一起换
export function setAgentMood(id) {
  id = MOOD[id] || id;
  mood = id;
  for (const h of agents) {
    if (!h.el.isConnected) { agents.delete(h); continue; }
    h.set(id);
  }
  document.querySelectorAll("[data-agent-status]").forEach((n) => { n.textContent = MOOD_TEXT[id] || "在这儿陪着你"; });
}
export function pulseAgent(kind) {
  for (const h of agents) if (h.el.isConnected) h.pulse(kind);
}

export function setAgentColor(c) {
  if (!c || c === agentColor) return;
  agentColor = c;
  snapshot = null;
  document.documentElement.style.setProperty("--agent", c);
  for (const h of live) {
    if (!h.el.isConnected) { live.delete(h); continue; }
    h.rebuild();
  }
  document.querySelectorAll(".agent-mini").forEach((n) => { n.innerHTML = agentMini(true); });
}

// 静态快照：同一颗球，渲染一次，到处复用（消息头像、toast）
let snapshot = null;
let miniSeq = 0;
export function agentMini(inner = false) {
  if (!snapshot) {
    const tmp = document.createElement("div");
    tmp.style.cssText = "position:fixed;left:-999px;top:0;width:64px;height:64px";
    document.body.append(tmp);
    try {
      const e = EB()?.create?.(tmp, { emotion: "02", shape: "blob", color: agentColor, eyeColor: eyeFor(agentColor), lite: true, autostart: false, eyeScale: 1.4 });
      // 每份拷贝都要有自己的 id：渐变若引用到 display:none 里的同名定义，Chrome 会画不出来
      snapshot = tmp.innerHTML.replace(/id="([^"]+)"/g, 'id="__U__$1"').replace(/url\(#([^)]+)\)/g, "url(#__U__$1)");
      e?.destroy?.();
    } catch {
      snapshot = "";
    }
    tmp.remove();
    if (!snapshot) snapshot = `<span class="ball-fallback" style="background:${agentColor}"></span>`;
  }
  const html = snapshot.replaceAll("__U__", `m${++miniSeq}_`);
  return inner ? html : `<span class="agent-mini">${html}</span>`;
}
window.__agentMini = () => agentMini();

let raf = 0, px = 0, py = 0;
window.addEventListener("pointermove", (e) => {
  px = e.clientX; py = e.clientY;
  if (raf) return;
  raf = requestAnimationFrame(() => {
    raf = 0;
    for (const h of live) {
      if (!h.el.isConnected) { live.delete(h); continue; }
      const r = h.el.getBoundingClientRect();
      if (!r.width) continue;
      h.gaze(Math.max(-1, Math.min(1, (px - (r.left + r.width / 2)) / (innerWidth / 2))),
        Math.max(-1, Math.min(1, (py - (r.top + r.height / 2)) / (innerHeight / 2))));
    }
  });
}, { passive: true });

const io = "IntersectionObserver" in window
  ? new IntersectionObserver((es) => {
      for (const e of es) for (const h of live) if (h.el === e.target) { try { h.engine?.setActive(e.isIntersecting); } catch {} }
    })
  : null;
