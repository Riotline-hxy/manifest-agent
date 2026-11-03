// 小光的脸：果冻形象（js/jelly.js）的适配层。对外的函数和以前一样，各页面不用改。
//
// - 外貌（形状 · 颜色 · 质感）跟着用户的选择（设置 → 外貌），换的时候形状和颜色会顺滑变过去
// - 页面上所有「小光」共享同一个心情：setAgentMood() 一处调用，处处更新
// - 心情有优先级：用户点它 > 完成小步、里程碑等事件 > 聊天里的情景表情 > 待机时自己的小动作
//   开心和情景表情停留约 1 分钟后回到待机；刷新页面也回到待机（心情不存）
// - 消息头像 / toast 用同一个形象的静态快照，全站只有一种形象
import { Jelly, track, untrack, snapshot, parseLook, LOOK_DEFAULT, lookBase, lookOpts } from "./jelly.js";

export const MOOD = {
  idle: "02", curious: "03", happy: "10", puzzled: "11", sad: "12", surprised: "13", shy: "14",
  tired: "15", focused: "16", satisfied: "19", thinking: "30", receiving: "31", busy: "32",
  done: "33", error: "34", listening: "35", recall: "37", replying: "39", searching: "40",
  sleep: "00", wake: "01", love: "20", grumpy: "21", wink: "22",
};

export const MOOD_TEXT = {
  "02": "在这儿陪着你", "03": "有点好奇", "10": "替你开心", "11": "嗯？没太懂", "13": "哇", "14": "有点不好意思",
  "15": "陪你慢一点", "16": "认真听着", "19": "嗯，记下了", "30": "想一想…", "31": "收到",
  "32": "在忙", "33": "写好了", "34": "嗯？出了点小问题", "35": "在听你说", "37": "在翻我们的回忆",
  "39": "正在回你", "40": "在找资料", "12": "有点心疼你", "00": "睡着了", "01": "醒啦",
  "20": "被你暖到了", "21": "哼，再来一次", "22": "跟你说个秘密",
};

// 心情 → 果冻表情（第二项是附加动作：calm = 不带入场动作，talk = 嘴巴在动，tilt = 歪一下头）
const FACE = {
  "00": ["sleepy"], "01": ["surprised"], "02": ["idle"], "03": ["listen", "tilt"], "10": ["happy"], "11": ["confused"],
  "12": ["sad"], "13": ["surprised"], "14": ["shy"], "15": ["sleepy", "calm"], "16": ["listen"], "19": ["happy", "calm"],
  "30": ["think"], "31": ["listen", "calm"], "32": ["think"], "33": ["happy"], "34": ["confused"], "35": ["listen"],
  "37": ["think"], "39": ["idle", "talk"], "40": ["think"], "20": ["love"], "21": ["grumpy"], "22": ["wink"],
};

let agentLook = localStorage.getItem("xg-look") || LOOK_DEFAULT;
const live = new Set();
const agents = new Set();
let mood = "02";

// 视图框：大的留出跳起来和头顶小特效的空间；小头像裁紧一点，身体更饱满
const VIEW = (size) => (size < 70 ? "-138 -150 276 286" : "-162 -176 324 324");

export function mountBall(el, { size = 96, emotion = null, interactive = true, agent = true, touch = null, look = null } = {}) {
  el.classList.add("ball");
  el.style.width = el.style.height = size + "px";
  el.innerHTML = `<div class="host"><svg class="jelly-svg"></svg></div>`;
  const host = el.querySelector(".host");
  const svg = host.querySelector("svg");
  const h = { el, size, agent, emotion: emotion || (agent ? mood : "02"), lockUntil: 0, followLook: !look };
  const code0 = MOOD[h.emotion] || h.emotion;
  const j = new Jelly(svg, { ...lookOpts(look || agentLook), expr: (FACE[code0] || FACE["02"])[0], alive: true, lite: size < 70 });
  svg.setAttribute("viewBox", VIEW(size));
  track(j);
  h.jelly = j;
  el.style.setProperty("--agent", lookBase(look || agentLook));

  h.set = (id, { force = false } = {}) => {
    id = MOOD[id] || id;
    if (!force && id === h.emotion) return;
    if (!force && h.lockUntil > Date.now()) { h.after = id; return; }   // 用户刚点过它：先把这个表情演完
    h.emotion = id;
    const [face, extra] = FACE[id] || FACE["02"];
    j.set(face, { calm: extra === "calm" });
    j.setTalking(extra === "talk");
    if (extra === "tilt") j.S.roll.vel += 60;
    if (id === "33") j.spin();
  };
  h.pulse = (kind = "bounce") => {
    if (kind === "bounce") j.hop(30);
    else j.spin();                     // spin / burst：转一圈，落地冒一圈小星光
  };
  h.gaze = (x, y) => j.gaze(x * 0.8, y * 0.8);
  h.setLook = (look) => { j.setLook(look); el.style.setProperty("--agent", lookBase(look)); };
  h.rebuild = () => h.setLook(agentLook);
  h.destroy = () => { untrack(j); live.delete(h); agents.delete(h); };

  if (touch) {
    // 开屏页：单击局部凹陷，按住捏一捏，快速双击换一个表情或动作
    j.bindTouch({ onDouble: () => { h.lockUntil = 0; playRandom(h, 2600); touch.onDouble?.(); }, onTap: touch.onTap });
  } else if (interactive) {
    // 侧边栏：单击随机换一个表情或转一圈（保留原来的玩法）
    host.addEventListener("click", () => playRandom(h, 2400));
  }
  live.add(h);
  if (agent) agents.add(h);
  return h;
}

const PICKS = ["10", "14", "19", "03", "13", "22", "20"];
function playRandom(h, ms) {
  const before = h.emotion;
  const pick = PICKS.filter((p) => p !== before)[Math.floor(Math.random() * (PICKS.length - 1))];
  h.lockUntil = 0;
  h.set(pick, { force: true });
  const r = Math.random();
  if (r < 0.35) h.pulse("spin"); else if (r < 0.7) h.pulse("bounce");
  h.lockUntil = Date.now() + ms;
  clearTimeout(h.lockTimer);
  h.lockTimer = setTimeout(() => {
    h.lockUntil = 0;
    h.set(h.after || (h.agent ? mood : before), { force: true });
    h.after = null;
  }, ms);
}

/* ---------- 心情：优先级 + 停留 ---------- */
const PRIO = { auto: 0, feel: 1, event: 2 };
let cur = { code: "02", prio: 0, until: 0 };

function show(code) {
  mood = code;
  for (const h of agents) {
    if (!h.el.isConnected) { h.destroy(); continue; }
    h.set(code);
  }
  document.querySelectorAll("[data-agent-status]").forEach((n) => { n.textContent = MOOD_TEXT[code] || "在这儿陪着你"; });
}

// 页面上所有小光一起换心情。prio：feel（默认）/ event；hold：停留多久（毫秒），之后回到待机
export function setAgentMood(id, { prio = "feel", hold = 0 } = {}) {
  const code = MOOD[id] || id;
  const p = PRIO[prio] ?? 1, now = Date.now();
  if (cur.until > now && p < cur.prio) return;         // 更重要的表情还在停留，先不打断
  cur = { code, prio: p, until: hold ? now + hold : 0 };
  autoUntil = 0;
  show(code);
}
// 用户自己开口了（发消息）：之前停留的表情让位
export function clearAgentHold() { cur = { ...cur, prio: 0, until: 0 }; }
// 完成小步、里程碑、记下好消息：开心 + 轻跳，停留 1 分钟
export function celebrate(big = false) {
  setAgentMood("happy", { prio: "event", hold: 60000 });
  pulseAgent(big ? "spin" : "bounce");
}
// 聊完之后的情景表情：有就停留 1 分钟，没有就回到待机
export function settleAgent(code) {
  if (code) setAgentMood(code, { prio: "feel", hold: 60000 });
  else if (!(cur.until > Date.now() && cur.prio >= PRIO.event)) setAgentMood("idle");
}
export function pulseAgent(kind) {
  for (const h of agents) if (h.el.isConnected && h.lockUntil < Date.now()) h.pulse(kind);
}

// 情景表情：只看用户这句话里的字眼，不额外请求模型、不多花 token
const FEEL_RULES = [
  ["20", /喜欢你|爱你|抱抱|想你了|你真好|有你真好|最喜欢/],
  ["12", /难过|伤心|想哭|哭了|委屈|失落|好累|累死|崩溃|焦虑|压力好大|失眠|孤独|不开心|沮丧|失败了|没考好|搞砸|emo/i],
  ["10", /开心|高兴|太好了|做到了|成功了|通过了|拿到了|好耶|终于|顺利|赢了|哈哈|嘿嘿|棒/],
  ["13", /居然|竟然|没想到|天哪|震惊|不敢相信/],
  ["14", /谢谢|感谢|被夸|夸我|不好意思|害羞/],
  ["21", /不服|气死|烦死|凭什么|不甘心|再来一次/],
  ["15", /好困|想睡|睡了|晚安|熬夜/],
  ["11", /为什么|怎么办|不懂|不明白|搞不懂|啥意思|什么意思|？{2,}|\?{2,}/],
];
export function feelOf(text = "", tools = []) {
  if (tools.some((t) => ["complete_step", "log_good_news", "checkin_habit"].includes(t.name) && t.result?.ok !== false)) return "10";
  for (const [code, re] of FEEL_RULES) if (re.test(text)) return code;
  return "";
}

/* ---------- 待机：自己在「平常、困了、思考、在听」之间慢慢切换，偶尔轻跳或转一圈 ---------- */
let autoUntil = 0, nextAuto = Date.now() + 18000, nextMove = Date.now() + 45000;
setInterval(() => {
  const now = Date.now();
  if (cur.until && now > cur.until) { cur = { code: "02", prio: 0, until: 0 }; show("02"); return; }
  if (cur.until > now || document.hidden || !agents.size) return;
  if (autoUntil && now > autoUntil) { autoUntil = 0; nextAuto = now + 20000 + Math.random() * 25000; show("02"); return; }
  if (!autoUntil && cur.code === "02" && now > nextAuto) {
    const r = Math.random();
    const code = r < 0.35 ? "35" : r < 0.65 ? "30" : r < 0.85 ? "15" : "03";
    autoUntil = now + 7000 + Math.random() * 7000;
    show(code);
  }
  if (now > nextMove) {
    nextMove = now + 45000 + Math.random() * 50000;
    if (mood === "02" || autoUntil) pulseAgent(Math.random() < 0.7 ? "bounce" : "spin");
  }
}, 1000);

/* ---------- 外貌 ---------- */
export function setAgentLook(look) {
  look = parseLook(look) ? look : LOOK_DEFAULT;
  if (look === agentLook) return;
  agentLook = look;
  localStorage.setItem("xg-look", look);
  snap = null;
  document.documentElement.style.setProperty("--agent", lookBase(look));
  for (const h of live) {
    if (!h.el.isConnected) { h.destroy(); continue; }
    if (h.followLook) h.setLook(look);
  }
  document.querySelectorAll(".agent-mini").forEach((n) => { n.innerHTML = agentMini(true); });
}
export const currentLook = () => agentLook;
// 旧接口：以前按颜色换。现在颜色是外貌的一部分，这里只认小光原有的 7 种颜色
const HEX_TO_COLOR = { "#f7cb4d": "gold", "#f2f2f4": "moon", "#8b7cff": "dawn", "#ff8a65": "sun", "#4fd1a5": "mint", "#5b9dff": "sea", "#ff8fb1": "sakura" };
export function setAgentColor(c) {
  const key = HEX_TO_COLOR[c];
  if (!key) return;
  const L = parseLook(agentLook);
  setAgentLook(`${L.shape}.${key}.${L.material}`);
}

// 静态快照：同一个形象，画一次，到处复用（消息头像、toast）
let snap = null;
let miniSeq = 0;
export function agentMini(inner = false) {
  if (!snap) {
    try {
      // 每份拷贝都要有自己的 id：渐变若引用到别处同名的定义，Chrome 可能画不出来
      snap = snapshot(agentLook).replace(/id="([^"]+)"/g, 'id="__U__$1"').replace(/url\(#([^)]+)\)/g, "url(#__U__$1)");
    } catch {
      snap = `<span class="ball-fallback" style="background:${lookBase(agentLook)}"></span>`;
    }
  }
  const html = snap.replaceAll("__U__", `m${++miniSeq}_`);
  return inner ? html : `<span class="agent-mini">${html}</span>`;
}
window.__agentMini = () => agentMini();

// 任意外貌的一张静态小图（外貌选择、建档时的选项）
export function lookPicture(look, expr = "idle") {
  return snapshot(look, expr).replace(/id="([^"]+)"/g, (m, a) => `id="lp${++miniSeq}_${a}"`)
    .replace(/url\(#([^)]+)\)/g, (m, a) => `url(#lp${miniSeq}_${a})`);
}

let raf = 0, px = 0, py = 0;
window.addEventListener("pointermove", (e) => {
  px = e.clientX; py = e.clientY;
  if (raf) return;
  raf = requestAnimationFrame(() => {
    raf = 0;
    for (const h of live) {
      if (!h.el.isConnected) { h.destroy(); continue; }
      const r = h.el.getBoundingClientRect();
      if (!r.width) continue;
      h.gaze(Math.max(-1, Math.min(1, (px - (r.left + r.width / 2)) / (innerWidth / 2))),
        Math.max(-1, Math.min(1, (py - (r.top + r.height / 2)) / (innerHeight / 2))));
    }
  });
}, { passive: true });
