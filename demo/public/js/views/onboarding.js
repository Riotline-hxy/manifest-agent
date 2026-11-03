// 建档：三段，每段一屏，都能跳过。
//   小光 —— 它的样子、说话方式、几天没动时怎么陪你、名字
//   你   —— 怎么叫你、作息节奏、像什么样的人、别对你做什么（小光会记住）
//   第一个愿望 —— 选个方向，给一条现成的路（里程碑 · 小步 · 习惯），能改能删，直接放进蜕变计划
// 每一个选择小光都会当场回应，不用读说明也知道它决定了什么。
import { api } from "../api.js";
import { state } from "../store.js";
import { esc, icon, tile, toast } from "../ui.js";
import { mountBall, setAgentLook, lookPicture } from "../ball.js";
import { LOOKS, LOOK_DEFAULT } from "../jelly.js";
import { CATS } from "../journey.js";
import { takeCarry, dropCarry } from "./trial.js";

const SECS = [
  { n: "小光", t: "先认识一下小光", h: "决定它的样子和说话方式", hi: "嗨，我是小光。先帮我挑个样子？" },
  { n: "你", t: "说说你自己", h: "小光会记住，聊天更懂你", hi: "你呢？随便说说就好。" },
  { n: "第一个愿望", t: "定一个想靠近的样子", h: "拆成小步，放进蜕变计划", hi: "最后一件事：想往哪儿走？" },
];
// [值, 文字, 图标, 颜色, 小光当场说的话]
const PERSONAS = [["gentle", "温柔", "heart", "var(--c-pink)", "不急，我在这儿，慢慢说。"],
  ["clear", "有条理", "list", "var(--c-sky)", "好，先把这件事拆成三步。"],
  ["lively", "活泼", "sparkles", "var(--c-lemon)", "冲！今天也给你记一朵小红花～"]];
const CARES = [["nudge", "轻轻提醒", "bell", "var(--c-sky)", "三天没动啦，来个最小的一步？"],
  ["analyze", "陪我找原因", "compass", "var(--c-mint)", "最近是不是被什么拖住了？说说看。"],
  ["quiet", "先别提", "moon", "var(--c-violet)", "不提啦，你想说的时候我都在。"]];
const RHYTHMS = [["早起型", "早起型", "sun", "var(--c-lemon)", "早起的人，厉害。"],
  ["夜猫", "夜猫子", "moon", "var(--c-violet)", "那我晚上多陪你一会儿。"],
  ["不固定", "看心情", "wind", "var(--c-mint)", "好，跟着你的节奏来。"]];
const TRAITS = ["想得多", "理性派", "行动派", "拖延但爆发", "需要被提醒", "喜欢独处"];
const NOPES = [["别说教", "说教"], ["别鸡血催促", "鸡血催促"], ["别追问太多", "追问太多"]];
const SPANS = [[30, "一个月"], [90, "三个月"], [180, "半年"]];
// 六个方向，各带一条现成的路
const WISHES = {
  confidence: { n: "更敢表达", title: "敢在人前开口", ms: "在课上或会上主动发言一次", steps: ["今天主动跟一个人打招呼", "写下一句想说却没说出口的话"], habit: "每天说一句真心话" },
  body: { n: "身体和作息", title: "早睡早起", ms: "连续 7 天 12 点前睡着", steps: ["今晚把手机放到床外面", "定一个 23:30 的睡前提醒"], habit: "23:30 放下手机" },
  calm: { n: "心里平静点", title: "心里平静一点", ms: "一周有 3 个晚上安心入睡", steps: ["写下现在最担心的一件事", "找一首能让自己静下来的歌"], habit: "每天发呆 5 分钟" },
  wealth: { n: "学业和事业", title: "把想做的事做出来", ms: "完成第一个小版本", steps: ["列出这周最想推进的一件事", "只做它，专注 25 分钟"], habit: "每天专注 25 分钟" },
  relation: { n: "关系更舒服", title: "关系里更自在", ms: "和一个重要的人好好聊一次", steps: ["给想念的人发一句问候", "写下一个自己的需要"], habit: "每天说一次谢谢" },
  freedom: { n: "活得更自在", title: "多做喜欢的事", ms: "去一个想去很久的地方", steps: ["列 3 件最近想做的小事", "这周留出半天给自己"], habit: "每天给自己留 20 分钟" },
};
const GUESS = [["confidence", /自信|表达|开口|勇敢|发言|社交/], ["body", /睡|早起|作息|健康|运动|身材|跑|减/], ["calm", /平静|焦虑|放松|压力|情绪/],
  ["wealth", /学|考|工作|事业|作品|项目|钱/], ["relation", /关系|朋友|家人|恋|沟通/], ["freedom", /自由|生活|旅行|喜欢/]];
const guess = (t) => (GUESS.find(([, re]) => re.test(t)) || ["other"])[0];

export function renderOnboarding(root) {
  const carry = takeCarry();
  const A = { agent_avatar_id: LOOK_DEFAULT, persona: "gentle", care_style: "nudge", agent_name: "小光",
    nickname: "", schedule_hint: "", traits: [], boundaries: [] };
  // 第一个愿望：从首页体验过来的，方向和那一小步已经有了
  const W = { on: false, cat: "", title: "", days: 30, why: carry?.why_goal || "", rows: [] };
  if (carry?.goal) pickWish(guess(carry.goal), carry.goal.replace(/^想/, ""));
  let sec = 0, seen = 0, busy = false;

  root.innerHTML = `
    <div class="ob">
      <header class="ob-head">
        <div class="ob-prog">${SECS.map((s, i) => `<button class="ob-dot" data-sec="${i}"><i></i><span>${s.n}</span></button>`).join("")}</div>
        <button class="ob-out" data-out>先进去看看</button>
      </header>
      <div class="ob-title"><h1></h1><p></p></div>
      <div class="ob-hero"><div class="ob-ball"></div><p class="ob-bubble"></p></div>
      <main class="ob-body"></main>
      <footer class="ob-foot"><button class="ob-skip" data-skip>跳过这段</button><button class="btn btn-main ob-next" data-next>下一步</button></footer>
    </div>`;
  const $ = (s) => root.querySelector(s);
  const ball = mountBall($(".ob-ball"), { size: innerWidth < 560 ? 92 : 108, agent: false, emotion: "01", look: A.agent_avatar_id, touch: {} });
  const bubble = $(".ob-bubble");
  const say = (text, face, move) => {
    bubble.textContent = text;
    bubble.classList.remove("pop"); void bubble.offsetWidth; bubble.classList.add("pop");
    if (face) ball.set(face, { force: true });
    if (move) ball.pulse(move);
  };
  const chip = (k, [v, label, ic, color], on) => `<button class="ob-chip ${on ? "on" : ""}" data-k="${k}" data-v="${esc(v)}" style="--c:${color}">${icon(ic)}<span>${esc(label)}</span></button>`;

  function pickWish(cat, title) {
    const T = WISHES[cat];
    W.on = true; W.cat = cat in WISHES ? cat : ""; W.title = title ?? T?.title ?? "";
    W.rows = [
      ...(carry?.step ? [{ kind: "step", text: carry.step, on: true, locked: true }] : []),
      { kind: "ms", text: T?.ms || "", on: true },
      ...(T?.steps || ["", ""]).slice(0, carry?.step ? 1 : 2).map((text) => ({ kind: "step", text, on: true })),
      { kind: "habit", text: T?.habit || "", on: true },
    ];
  }

  // ---------------------------------------------------------------- 三段 ----
  const draw = {
    0() {
      return `
        <div class="ob-field"><label>样子</label>
          <div class="ob-looks">${LOOKS.slice(0, 6).map((x) => `<button class="ob-look ${x.id === A.agent_avatar_id ? "on" : ""}" data-look="${x.id}" aria-label="${esc(x.n)}">${lookPicture(x.id)}</button>`).join("")}</div></div>
        <div class="ob-field"><label>说话</label><div class="ob-chips">${PERSONAS.map((o) => chip("persona", o, A.persona === o[0])).join("")}</div></div>
        <div class="ob-field"><label>几天没动时</label><div class="ob-chips">${CARES.map((o) => chip("care_style", o, A.care_style === o[0])).join("")}</div></div>
        <div class="ob-field"><label>名字</label><input class="ob-in ob-name" data-in="agent_name" maxlength="8" value="${esc(A.agent_name)}" aria-label="小光的名字"></div>`;
    },
    1() {
      return `
        <div class="ob-field"><label>怎么叫你</label><input class="ob-in" data-in="nickname" maxlength="12" placeholder="名字或昵称" value="${esc(A.nickname)}"></div>
        <div class="ob-field"><label>你的节奏</label><div class="ob-chips">${RHYTHMS.map((o) => chip("schedule_hint", o, A.schedule_hint === o[0])).join("")}</div></div>
        <div class="ob-field"><label>你更像<small>最多 3 个</small></label><div class="ob-chips">${TRAITS.map((t) => `<button class="ob-chip plain ${A.traits.includes(t) ? "on" : ""}" data-multi="traits" data-v="${t}">${t}</button>`).join("")}</div></div>
        <div class="ob-field"><label>别对我</label><div class="ob-chips">${NOPES.map(([v, l]) => `<button class="ob-chip plain ${A.boundaries.includes(v) ? "on" : ""}" data-multi="boundaries" data-v="${v}">${l}</button>`).join("")}</div></div>`;
    },
    2() {
      const rowLabel = { ms: ["flag", "var(--c-violet)", "里程碑", "走到一半是什么样子"], step: ["steps", "var(--c-orange)", "小步", "第一步可以是……"], habit: ["clock", "var(--c-mint)", "习惯", "每天能做的一件小事"] };
      return `
        <div class="ob-wishes ${W.on ? "picked" : ""}">${Object.entries(WISHES).map(([k, x]) => `<button class="ob-wish ${W.on && W.cat === k ? "on" : ""}" data-wish="${k}">${tile(CATS[k].icon, CATS[k].color, 36)}<span>${x.n}</span></button>`).join("")}
          <button class="ob-wish ${W.on && !W.cat ? "on" : ""}" data-wish="">${tile("edit", "var(--c-coral)", 36)}<span>自己写</span></button></div>
        ${W.on ? `<div class="ob-plan">
          <div class="ob-prow head"><span class="ob-tag" style="--c:var(--accent)">${icon("star")}愿望</span>
            <input class="ob-in" data-w="title" maxlength="30" placeholder="想靠近什么样子" value="${esc(W.title)}"></div>
          <div class="ob-spans">${SPANS.map(([d, l]) => `<button class="ob-chip plain sm ${W.days === d ? "on" : ""}" data-days="${d}">${l}</button>`).join("")}</div>
          ${W.rows.map((r, i) => { const [ic, col, tag, ph] = rowLabel[r.kind]; return `<div class="ob-prow ${r.on ? "" : "off"}">
            <button class="ob-ck" data-row="${i}" ${r.locked ? "disabled" : ""} aria-label="${r.on ? "不要这一项" : "要这一项"}">${icon("check")}</button>
            <span class="ob-tag" style="--c:${col}">${icon(ic)}${tag}</span>
            ${r.locked ? `<span class="ob-fixed">${esc(r.text)}<small>刚才定的</small></span>` : `<input class="ob-in" data-rowin="${i}" maxlength="40" placeholder="${ph}" value="${esc(r.text)}">`}</div>`; }).join("")}
          ${W.whyOpen || W.why ? `<input class="ob-in ob-why" data-w="why" maxlength="40" placeholder="为什么想要它？一句话就好" value="${esc(W.why)}">`
            : `<button class="ob-why-add" data-why>${icon("plus")}说说为什么</button>`}
        </div>` : ""}`;
    },
  };

  function render(dir = 0) {
    const S = SECS[sec];
    root.querySelector(".ob").dataset.sec = sec;
    $(".ob-title h1").textContent = S.t;
    $(".ob-title p").textContent = S.h;
    root.querySelectorAll(".ob-dot").forEach((d, i) => { d.classList.toggle("on", i === sec); d.classList.toggle("done", i < sec); d.disabled = i > seen; });
    const body = $(".ob-body");
    body.innerHTML = draw[sec]();
    if (dir) { body.classList.remove("in-l", "in-r"); void body.offsetWidth; body.classList.add(dir > 0 ? "in-r" : "in-l"); }
    $("[data-next]").textContent = sec < 2 ? "下一步" : W.on ? "就从这里开始" : "先进去";
    $("[data-skip]").textContent = sec < 2 ? "跳过这段" : "先不定";
    bind(body);
  }

  function bind(body) {
    body.querySelectorAll("[data-look]").forEach((b) => b.addEventListener("click", () => {
      A.agent_avatar_id = b.dataset.look;
      body.querySelectorAll("[data-look]").forEach((x) => x.classList.toggle("on", x === b));
      ball.setLook(A.agent_avatar_id);
      say(LOOKS.find((x) => x.id === A.agent_avatar_id).h + "。", "10", "bounce");
    }));
    body.querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.k, v = b.dataset.v;
      A[k] = A[k] === v && k === "schedule_hint" ? "" : v;
      body.querySelectorAll(`[data-k="${k}"]`).forEach((x) => x.classList.toggle("on", x.dataset.v === A[k]));
      const o = [...PERSONAS, ...CARES, ...RHYTHMS].find((x) => x[0] === v);
      const face = { lively: "10", clear: "16", gentle: "14", nudge: "35", analyze: "30", quiet: "15", "早起型": "13", "夜猫": "22", "不固定": "02" }[v];
      if (A[k]) say(o[4], face, v === "lively" ? "bounce" : null);
    }));
    body.querySelectorAll("[data-multi]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.multi, v = b.dataset.v, list = A[k];
      if (list.includes(v)) list.splice(list.indexOf(v), 1);
      else if (k === "traits" && list.length >= 3) return say("最多挑 3 个就好～", "11");
      else list.push(v);
      b.classList.toggle("on", list.includes(v));
      if (list.includes(v)) say(k === "traits" ? ["嗯，我懂一点了。", "记住啦。", "原来是这样的你。"][list.length - 1] : "收到，我不会这样的。", k === "traits" ? "35" : "19");
    }));
    body.querySelectorAll("[data-in]").forEach((inp) => {
      inp.addEventListener("input", () => { A[inp.dataset.in] = inp.value.trim(); });
      inp.addEventListener("change", () => {
        if (inp.dataset.in === "nickname" && A.nickname) say(`${A.nickname}，记住啦。`, "14");
        if (inp.dataset.in === "agent_name") say(`以后就叫我「${A.agent_name || "小光"}」吧。`, "10", "bounce");
      });
    });
    body.querySelectorAll("[data-wish]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.wish;
      pickWish(k, k ? undefined : "");
      render();
      if (k) say(`好，就从「${WISHES[k].title}」开始。`, "10", "bounce");
      else { say("你想靠近什么样子？", "35"); $("[data-w=title]")?.focus(); }
    }));
    body.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
      W.days = +b.dataset.days;
      body.querySelectorAll("[data-days]").forEach((x) => x.classList.toggle("on", x === b));
      say({ 30: "一个月，刚刚好。", 90: "三个月，慢慢来。", 180: "半年，够我们走很远了。" }[W.days], "19");
    }));
    body.querySelectorAll("[data-row]").forEach((b) => b.addEventListener("click", () => { const r = W.rows[+b.dataset.row]; r.on = !r.on; b.closest(".ob-prow").classList.toggle("off", !r.on); }));
    body.querySelectorAll("[data-rowin]").forEach((inp) => inp.addEventListener("input", () => { W.rows[+inp.dataset.rowin].text = inp.value; }));
    body.querySelectorAll("[data-w]").forEach((inp) => inp.addEventListener("input", () => { W[inp.dataset.w] = inp.value; }));
    body.querySelector("[data-why]")?.addEventListener("click", () => { W.whyOpen = true; render(); $("[data-w=why]")?.focus(); });
    body.querySelectorAll("input").forEach((inp) => inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); inp.blur(); } }));
  }

  const go = (to) => {
    if (busy) return;
    const dir = to > sec ? 1 : -1;
    sec = to; seen = Math.max(seen, sec);
    render(dir);
    say(SECS[sec].hi, sec === 2 ? "30" : "35");
  };

  async function finish(skipWish = false) {
    if (busy) return;
    busy = true;
    root.querySelectorAll(".ob-foot button, [data-out]").forEach((b) => (b.disabled = true));
    const answers = { ...A, theme: localStorage.getItem("xg-theme") || "forest" };
    const rows = (kind) => W.rows.filter((r) => r.kind === kind && r.on && !r.locked && r.text.trim()).map((r) => r.text.trim());
    if (W.on && !skipWish && W.title.trim()) {
      answers.wish = { title: W.title.trim(), category: W.cat || guess(W.title), days: W.days, milestones: rows("ms"), steps: rows("step"), habits: rows("habit") };
      answers.intent_primary = W.title.trim();
      answers.intent_why = W.why.trim();
    } else if (carry?.goal) {
      answers.intent_primary = carry.goal.replace(/^想/, "");
      answers.intent_why = carry.why_goal || "";
    }
    try {
      await api.onboard(answers, carry);
      dropCarry();
      setAgentLook(A.agent_avatar_id);
      say(answers.wish ? "好啦，路已经放进蜕变计划了。" : "好啦，我们开始吧！", "10", "spin");
      setTimeout(() => window.dispatchEvent(new CustomEvent("xg:enter")), 1100);
    } catch (e) {
      busy = false;
      root.querySelectorAll(".ob-foot button, [data-out]").forEach((b) => (b.disabled = false));
      say("没成功，再试一次？", "34");
      toast(e.message || "没保存上", "err");
    }
  }

  root.querySelectorAll(".ob-dot").forEach((d) => d.addEventListener("click", () => { const i = +d.dataset.sec; if (i <= seen && i !== sec) go(i); }));
  $("[data-next]").addEventListener("click", () => (sec < 2 ? go(sec + 1) : finish()));
  $("[data-skip]").addEventListener("click", () => (sec < 2 ? go(sec + 1) : finish(true)));
  $("[data-out]").addEventListener("click", () => finish(sec < 2));
  render();
  say(SECS[0].hi, "02");
  setTimeout(() => ball.set("02", { force: true }), 1200);
}
