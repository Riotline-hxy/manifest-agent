// 小光的脸：Emotion Ball 的薄适配层。
// 上游：github.com/sam70361/emotion-ball（非商业免费；球形角色视觉禁止商用——
// 本 demo 为竞赛展示，正式商用前需换成自研形象，见 vendor/emotion-ball/NOTICE.md）。
// 引擎没加载成功时退回 CSS 小球，页面不会因此坏掉。

const EB = () => window.EmotionBall;

// 产品状态 → 引擎表情 id（上游稳定的公开约定）
export const MOOD = {
  idle: "02", curious: "03", happy: "10", puzzled: "11", sad: "12", surprised: "13", shy: "14",
  tired: "15", focused: "16", satisfied: "19", thinking: "30", receiving: "31", busy: "32",
  done: "33", error: "34", listening: "35", recall: "37", replying: "39", searching: "40",
  sleep: "00", wake: "01",
};

// 每个表情给一句状态，用在小光名字下面
export const MOOD_TEXT = {
  "02": "在这儿陪着你", "03": "有点好奇", "10": "替你开心", "13": "哇", "14": "有点不好意思",
  "15": "陪你慢一点", "16": "认真听着", "19": "嗯，记下了", "30": "想一想…", "31": "收到",
  "33": "写好了", "34": "出了点小问题", "35": "在听你说", "37": "在翻我们的回忆", "39": "正在回你",
  "40": "在找资料", "12": "有点心疼你", "00": "睡着了", "01": "醒啦",
};

export const COLOR = "#f7cb4d";
const EYES = "#2b2208";

const live = new Set();

export function mountBall(el, { size = 96, emotion = "02", idle = false, interactive = true, halo = true } = {}) {
  el.classList.add("ball");
  el.style.width = el.style.height = size + "px";
  el.innerHTML = `${halo ? '<span class="halo"></span>' : ""}<div class="host"></div>`;
  const host = el.querySelector(".host");
  let engine = null;
  let cur = emotion;
  const listeners = new Set();

  if (EB()?.create) {
    try {
      engine = EB().create(host, {
        emotion, shape: "blob", color: COLOR, eyeColor: EYES,
        eyeScale: size < 70 ? 1.5 : 1, lite: size < 70,
        idle: idle ? { standbyAfter: 90000, sleepAfter: 600000 } : false,
        label: "小光",
      });
      el.dataset.engine = "emotion-ball";
    } catch (e) {
      console.warn("[ball] engine failed, falling back", e);
      engine = null;
    }
  }
  if (!engine) host.innerHTML = `<div class="mini-orb" style="width:100%;height:100%"></div>`;

  const h = {
    el,
    _engine: engine,
    get emotion() { return cur; },
    set(id) {
      id = MOOD[id] || id;
      if (!engine || id === cur) return;
      cur = id;
      engine.setEmotion(id);
      if (id === "30") engine.spin(1);
      if (id === "33") engine.burst(24);
      listeners.forEach((fn) => fn(id));
    },
    pulse(kind = "bounce") {
      if (!engine) return;
      if (kind === "bounce") engine.bounce();
      else if (kind === "spin") engine.spin(2);
      else if (kind === "burst") { engine.burst(30); engine.spin(2); }
    },
    gaze(x, y) { engine?.setGaze(x, y); },
    tour(ids, ms = 2600) { engine?.startTour(ids.map((i) => MOOD[i] || i), ms); },
    stopTour() { engine?.stopTour(); },
    onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    destroy() { engine?.destroy(); live.delete(h); },
  };

  if (interactive) {
    // 点一下：跳一下，然后随机给个好心情
    host.addEventListener("click", () => {
      const pick = ["10", "14", "19", "03", "13"][Math.floor(Math.random() * 5)];
      h.pulse(Math.random() > 0.5 ? "bounce" : "spin");
      const before = cur;
      h.set(pick);
      setTimeout(() => { if (cur === pick) h.set(before === pick ? "02" : before); }, 2400);
    });
  }
  live.add(h);
  if (io) io.observe(el);
  return h;
}

// 一个监听器驱动所有球的视线，相对各自中心
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
      const nx = (px - (r.left + r.width / 2)) / (innerWidth / 2);
      const ny = (py - (r.top + r.height / 2)) / (innerHeight / 2);
      h.gaze(Math.max(-1, Math.min(1, nx)), Math.max(-1, Math.min(1, ny)));
    }
  });
}, { passive: true });

// 看不见的球暂停动画
const io = "IntersectionObserver" in window
  ? new IntersectionObserver((es) => {
      for (const e of es) {
        for (const h of live) {
          if (h.el === e.target) {
            try { h._engine?.setActive(e.isIntersecting); } catch {}
          }
        }
      }
    })
  : null;
