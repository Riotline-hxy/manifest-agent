// 建档：一个入口页，三件事想先做哪件都行，做完回到入口页，随时可以进门。
//   认识小光   —— 它的样子、说话方式、几天没动时怎么陪你、名字
//   介绍一下你 —— 怎么叫你、作息节奏、像什么样的人、别对你做什么（小光会记住）
//   第一个愿望 —— 和首页体验一样：选一件想改变的事 → 和小光聊几句（真的模型）→ 小光把它拆成
//                 里程碑 · 习惯 · 小步，你勾想要的，进门时一起放进蜕变计划
// 每一个选择小光都会当场回应，不用读说明也知道它决定了什么。
import { api } from "../api.js";
import { esc, icon, tile, toast } from "../ui.js";
import { mountBall, setAgentLook, lookPicture, agentMini } from "../ball.js";
import { LOOKS, LOOK_DEFAULT, lookName } from "../jelly.js";
import { takeCarry, dropCarry, GOALS } from "./trial.js";

const ENTRIES = [
  { k: "agent", t: "认识小光", h: "它的样子、怎么跟你说话" },
  { k: "me", t: "介绍一下你", h: "让小光更懂你", ic: "user", c: "var(--c-sky)" },
  { k: "wish", t: "第一个愿望", h: "和小光聊聊，拆成小步", ic: "flag", c: "var(--c-orange)" },
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
const REVISE_HINTS = ["时间对不上", "太难了，再小一点", "换一个习惯", "小步再具体点"];
// 把用户手上的这一版（包括自己改过的字）讲给小光听，它在这个基础上改
const planText = (P) => `我拆的是：愿望「${P.title}」，${{ 30: "一个月", 90: "三个月", 180: "半年" }[P.days] || "一个月"}；`
  + P.rows.filter((x) => x.on && x.text.trim()).map((x) => `${{ ms: "里程碑", habit: "习惯", step: "小步" }[x.kind]}「${x.text.trim()}」`).join("，") + "。";
const ROW = { ms: ["flag", "var(--c-violet)", "里程碑"], habit: ["clock", "var(--c-mint)", "习惯"], step: ["steps", "var(--c-orange)", "小步"] };
const label = (list, v) => (list.find((x) => x[0] === v) || [])[1] || "";
// 「认识小光」入口的底色：和小光自己的颜色拉开对比
const tileFor = (look) => ({ dawn: "var(--c-sky)", lilac: "var(--c-sky)", night: "var(--c-sky)", sea: "var(--c-mint)", sky: "var(--c-mint)", mint: "var(--c-sky)" })[String(look).split(".")[1]] || "var(--c-violet)";

export function renderOnboarding(root) {
  const carry = takeCarry();
  const A = { agent_avatar_id: LOOK_DEFAULT, persona: "gentle", care_style: "nudge", agent_name: "小光",
    nickname: "", schedule_hint: "", traits: [], boundaries: [] };
  const done = { agent: false, me: false, wish: false };
  let W = null;                                  // 勾好的第一个愿望
  let remember = carry?.remember || [], whyGoal = carry?.why_goal || "";
  if (carry?.step) {                             // 从首页体验过来：那一小步已经定好了
    W = { title: carry.goal.replace(/^想/, ""), category: "", days: 30, due: 15, rows: [{ kind: "step", text: carry.step, on: true, locked: true }] };
    done.wish = true;
  }
  let busy = false;

  root.innerHTML = `
    <div class="ob">
      <header class="ob-head"><span class="ob-brand">${agentMini()}<b>显伴</b></span><span class="sp"></span>
        <button class="ob-out" data-out>先进去看看</button></header>
      <div class="ob-hero"><div class="ob-ball"></div><p class="ob-bubble"></p></div>
      <main class="ob-main"></main>
    </div>`;
  const $ = (s) => root.querySelector(s);
  const main = $(".ob-main");
  const ball = mountBall($(".ob-ball"), { size: innerWidth < 560 ? 92 : 108, agent: false, emotion: "01", look: A.agent_avatar_id, touch: {} });
  const bubble = $(".ob-bubble");
  const say = (text, face, move) => {
    bubble.textContent = text;
    bubble.classList.remove("pop"); void bubble.offsetWidth; bubble.classList.add("pop");
    if (face) ball.set(face, { force: true });
    if (move) ball.pulse(move);
  };
  const swap = (html) => { main.innerHTML = html; main.classList.remove("in"); void main.offsetWidth; main.classList.add("in"); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const chip = (k, [v, text, ic, color], on) => `<button class="ob-chip ${on ? "on" : ""}" data-k="${k}" data-v="${esc(v)}" style="--c:${color}">${icon(ic)}<span>${esc(text)}</span></button>`;
  const pageHead = (t) => `<div class="ob-page-h"><button class="ob-back" data-back>${icon("back")}返回</button><h2>${t}</h2></div>`;

  // ---------------------------------------------------------------- 入口页 ----
  const summary = {
    agent: () => `${lookName(A.agent_avatar_id)} · ${label(PERSONAS, A.persona)}`,
    me: () => [A.nickname, label(RHYTHMS, A.schedule_hint), ...A.traits].filter(Boolean).slice(0, 3).join(" · ") || "说了一些",
    wish: () => `${W.title} · ${W.rows.filter((r) => r.on).length} 件事`,
  };
  function hub(line) {
    const n = Object.values(done).filter(Boolean).length;
    swap(`
      <div class="ob-hub-t"><h1>欢迎来到显伴</h1><p>三件小事，从哪个开始都行</p></div>
      <div class="ob-entries">${ENTRIES.map((e, i) => `
        <button class="ob-entry ${done[e.k] ? "done" : ""}" data-open="${e.k}" style="--i:${i}">
          <span class="ob-e-ic">${e.k === "agent" ? `<span class="tile ob-tile-look" style="--tile:${tileFor(A.agent_avatar_id)};width:46px;height:46px">${lookPicture(A.agent_avatar_id)}</span>` : tile(e.ic, e.c, 46)}</span>
          <span class="ob-e-main"><b>${e.t}</b><small>${esc(done[e.k] ? summary[e.k]() : e.h)}</small></span>
          <span class="ob-e-st">${done[e.k] ? icon("check") : icon("arrow")}</span></button>`).join("")}</div>
      <button class="btn btn-main btn-lg ob-enter" data-enter>${n === 3 ? "都好了，进入显伴" : "进入显伴"}</button>
      ${n < 3 ? `<p class="ob-note">跳过的以后也能补</p>` : ""}`);
    say(line || (n === 3 ? "都好啦！进去看看吧。" : n ? "好啦～还想看看哪个？" : "嗨，我是小光。这三件事，从哪个开始都行～"), n === 3 ? "10" : "02", n === 3 ? "bounce" : null);
    main.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => open[b.dataset.open]()));
    main.querySelector("[data-enter]").addEventListener("click", () => finish());
  }

  // ---------------------------------------------------------------- 认识小光 · 介绍一下你 ----
  const open = {
    agent() {
      swap(`${pageHead("认识小光")}
        <div class="ob-fields">
          <div class="ob-field"><label>样子</label>
            <div class="ob-looks">${LOOKS.map((x) => `<button class="ob-look ${x.id === A.agent_avatar_id ? "on" : ""}" data-look="${x.id}" aria-label="${esc(x.n)}">${lookPicture(x.id)}</button>`).join("")}</div></div>
          <div class="ob-field"><label>说话</label><div class="ob-chips">${PERSONAS.map((o) => chip("persona", o, A.persona === o[0])).join("")}</div></div>
          <div class="ob-field"><label>几天没动时</label><div class="ob-chips">${CARES.map((o) => chip("care_style", o, A.care_style === o[0])).join("")}</div></div>
          <div class="ob-field"><label>名字</label><input class="ob-in ob-name" data-in="agent_name" maxlength="8" value="${esc(A.agent_name)}" aria-label="小光的名字"></div>
        </div>
        <div class="ob-foot"><button class="btn btn-main" data-ok>好了</button></div>`);
      say("先帮我挑个样子？", "35");
      bindFields("agent");
    },
    me() {
      swap(`${pageHead("介绍一下你")}
        <div class="ob-fields">
          <div class="ob-field"><label>怎么叫你</label><input class="ob-in" data-in="nickname" maxlength="12" placeholder="名字或昵称" value="${esc(A.nickname)}"></div>
          <div class="ob-field"><label>你的节奏</label><div class="ob-chips">${RHYTHMS.map((o) => chip("schedule_hint", o, A.schedule_hint === o[0])).join("")}</div></div>
          <div class="ob-field"><label>你更像<small>最多 3 个</small></label><div class="ob-chips">${TRAITS.map((t) => `<button class="ob-chip plain ${A.traits.includes(t) ? "on" : ""}" data-multi="traits" data-v="${t}">${t}</button>`).join("")}</div></div>
          <div class="ob-field"><label>别对我</label><div class="ob-chips">${NOPES.map(([v, l]) => `<button class="ob-chip plain ${A.boundaries.includes(v) ? "on" : ""}" data-multi="boundaries" data-v="${v}">${l}</button>`).join("")}</div></div>
        </div>
        <div class="ob-foot"><button class="btn btn-main" data-ok>好了</button></div>`);
      say("你呢？随便说说就好，我会记住的。", "35");
      bindFields("me");
    },
    wish() { goalPick(); },
  };

  function bindFields(k) {
    main.querySelector("[data-back]").addEventListener("click", () => hub());
    main.querySelector("[data-ok]").addEventListener("click", () => { done[k] = true; hub(); });
    main.querySelectorAll("[data-look]").forEach((b) => b.addEventListener("click", () => {
      A.agent_avatar_id = b.dataset.look;
      main.querySelectorAll("[data-look]").forEach((x) => x.classList.toggle("on", x === b));
      ball.setLook(A.agent_avatar_id);
      say(LOOKS.find((x) => x.id === A.agent_avatar_id).h + "。", "10", "bounce");
    }));
    main.querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => {
      const key = b.dataset.k, v = b.dataset.v;
      A[key] = A[key] === v && key === "schedule_hint" ? "" : v;
      main.querySelectorAll(`[data-k="${key}"]`).forEach((x) => x.classList.toggle("on", x.dataset.v === A[key]));
      const o = [...PERSONAS, ...CARES, ...RHYTHMS].find((x) => x[0] === v);
      const face = { lively: "10", clear: "16", gentle: "14", nudge: "35", analyze: "30", quiet: "15", "早起型": "13", "夜猫": "22", "不固定": "02" }[v];
      if (A[key]) say(o[4], face, v === "lively" ? "bounce" : null);
    }));
    main.querySelectorAll("[data-multi]").forEach((b) => b.addEventListener("click", () => {
      const key = b.dataset.multi, v = b.dataset.v, list = A[key];
      if (list.includes(v)) list.splice(list.indexOf(v), 1);
      else if (key === "traits" && list.length >= 3) return say("最多挑 3 个就好～", "11");
      else list.push(v);
      b.classList.toggle("on", list.includes(v));
      if (list.includes(v)) say(key === "traits" ? ["嗯，我懂一点了。", "记住啦。", "原来是这样的你。"][list.length - 1] : "收到，我不会这样的。", key === "traits" ? "35" : "19");
    }));
    main.querySelectorAll("[data-in]").forEach((inp) => {
      inp.addEventListener("input", () => { A[inp.dataset.in] = inp.value.trim(); });
      inp.addEventListener("change", () => {
        if (inp.dataset.in === "nickname" && A.nickname) say(`${A.nickname}，记住啦。`, "14");
        if (inp.dataset.in === "agent_name") say(`以后就叫我「${A.agent_name || "小光"}」吧。`, "10", "bounce");
      });
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); inp.blur(); } });
    });
  }

  // ---------------------------------------------------------------- 第一个愿望 ----
  // 1. 选一件想改变的事（和首页体验同一套选项）
  function goalPick() {
    swap(`${pageHead("第一个愿望")}
      <div class="trial-goals ob-goals">${GOALS.map((g, i) => `
        <button class="trial-goal" data-g="${g.id}" style="--i:${i}">${tile(g.ic, g.c, 42)}
          <span><b>${esc(g.t)}</b><small>${esc(g.sub)}</small></span></button>`).join("")}</div>
      <div class="trial-own"><input class="field" maxlength="30" placeholder="或者自己写一句"><button class="btn btn-main" disabled>就这个</button></div>`);
    say(carry?.goal ? `刚才说的「${carry.goal}」，要再聊细一点吗？也可以换一件。` : "最近有没有一件事，你想让自己慢慢变好一点？", "10");
    main.querySelector("[data-back]").addEventListener("click", () => hub());
    const own = main.querySelector(".trial-own input"), ok = main.querySelector(".trial-own button");
    own.addEventListener("input", () => { ok.disabled = !own.value.trim(); });
    own.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing && own.value.trim()) ok.click(); });
    ok.addEventListener("click", () => talk({ id: "own", t: own.value.trim(), hints: [], open: `「${own.value.trim()}」，好，我听着。现在大概是什么样子？随便说说就行。` }));
    main.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => talk(GOALS.find((g) => g.id === b.dataset.g))));
  }

  // 2. 和小光聊几句（真的模型；最多三轮，随时可以让它直接拆）
  function talk(goal) {
    swap(`${pageHead(esc(goal.t))}
      <div class="trial-chat ob-chat">
        <div class="trial-thread"></div>
        <div class="trial-composer">
          <div class="hints">${(goal.hints || []).map((t) => `<button class="chip" data-fill="${esc(t)}">${esc(t)}</button>`).join("")}</div>
          <div class="inbox"><textarea rows="1" maxlength="300" placeholder="说说看……"></textarea><button class="send" aria-label="发送">${icon("send")}</button></div>
          <div class="trial-meta"><span class="trial-left"></span><button class="btn btn-quiet btn-sm" data-act="finish" hidden>直接帮我拆好</button></div>
        </div>
      </div>`);
    say("不用想得很完整，像跟朋友吐槽那样说就行。", "35");
    main.querySelector("[data-back]").addEventListener("click", () => goalPick());
    const thread = main.querySelector(".trial-thread"), comp = main.querySelector(".trial-composer");
    const ta = comp.querySelector("textarea"), send = comp.querySelector(".send");
    const left = comp.querySelector(".trial-left"), finishBtn = comp.querySelector("[data-act=finish]");
    const history = [{ role: "assistant", content: goal.open }];
    let waiting = false, revising = null, revCard = null;   // revising：正在改的那一版路；revCard：它的卡片
    const scroll = () => requestAnimationFrame(() => thread.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "end" }));
    const msg = (role, text) => {
      const el = document.createElement("div");
      el.className = `msg ${role}`;
      el.innerHTML = role === "user" ? `<div class="bub">${esc(text)}</div>`
        : `${agentMini()}<div class="col"><div class="bub"><div class="txt">${text === null ? `<span class="dots"><i></i><i></i><i></i></span>` : esc(text)}</div></div></div>`;
      thread.append(el); scroll();
      return el;
    };
    const rounds = () => history.filter((m) => m.role === "user").length;
    const refresh = () => {
      const n = rounds();
      send.classList.toggle("ready", !waiting && !!ta.value.trim());
      left.textContent = n >= 3 || revising ? "" : `还能聊 ${3 - n} 句`;
      finishBtn.hidden = n < 1 || waiting || !!revising;
      ta.disabled = waiting;
    };
    async function ask(text, opts = {}) {
      if (waiting) return;
      waiting = true;
      const was = revising;
      if (was) { history.push({ role: "assistant", content: planText(was) }); opts = { ...opts, revise: true }; revCard?.classList.add("dim"); }
      if (text) { history.push({ role: "user", content: text }); msg("user", text); }
      comp.querySelector(".hints").classList.add("hide");
      ta.value = ""; refresh();
      ball.set("30", { force: true });
      const wait = msg("assistant", null);
      try {
        const r = await api.onboardPlan({ goal: goal.t, history, ...opts,
          about: { persona: A.persona, nickname: A.nickname, traits: A.traits, boundaries: A.boundaries } });
        history.push({ role: "assistant", content: r.reply });
        wait.querySelector(".txt").textContent = r.reply;
        if (r.plan) { comp.hidden = true; revising = null; revCard?.remove(); revCard = null; planCard(goal, r); }
        else ball.set("35", { force: true });
      } catch (e) {
        wait.remove();
        if (text) { history.pop(); ta.value = text; }
        if (was) { history.pop(); revCard?.classList.remove("dim"); }
        toast(e.message, "err");
        ball.set("12", { force: true });
      }
      waiting = false;
      refresh();
      if (!comp.hidden) ta.focus();
    }
    ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 140) + "px"; refresh(); });
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send.click(); } });
    send.addEventListener("click", () => { const t = ta.value.trim(); if (t) ask(t); });
    comp.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.fill)));
    finishBtn.addEventListener("click", () => {
      history.push({ role: "user", content: "我大概就是这样，帮我拆成一条能走的路吧。" });
      msg("user", "帮我拆成小步吧");
      ask("", { finish: true });
    });
    msg("assistant", goal.open);
    refresh();
    setTimeout(() => ta.focus(), 300);

    // 3. 小光拆好的路：勾想要的、改不合适的
    function planCard(goal, r) {
      const p = r.plan;
      const P = { title: p.title, category: p.category, days: p.days, due: p.due_in_days,
        rows: [
          ...(carry?.step && goal.t === carry.goal ? [{ kind: "step", text: carry.step, on: true, locked: true }] : []),
          ...p.milestones.map((text) => ({ kind: "ms", text, on: true })),
          ...p.habits.map((text) => ({ kind: "habit", text, on: true })),
          ...p.steps.map((text) => ({ kind: "step", text, on: true })),
        ] };
      say("我帮你拆了一下。不合适的直接改，不想要的点掉。", "19", "bounce");
      const card = document.createElement("div");
      card.className = "ob-plan";
      card.innerHTML = `
        <div class="ob-prow head"><span class="ob-tag" style="--c:var(--accent)">${icon("star")}愿望</span>
          <input class="ob-in" data-w="title" maxlength="30" value="${esc(P.title)}"></div>
        <div class="ob-spans">${SPANS.map(([d, l]) => `<button class="ob-chip plain sm ${P.days === d ? "on" : ""}" data-days="${d}">${l}</button>`).join("")}</div>
        ${P.rows.map((x, i) => { const [ic, col, tag] = ROW[x.kind]; return `<div class="ob-prow">
          <button class="ob-ck" data-row="${i}" ${x.locked ? "disabled" : ""} aria-label="要不要这一项">${icon("check")}</button>
          <span class="ob-tag" style="--c:${col}">${icon(ic)}${tag}</span>
          ${x.locked ? `<span class="ob-fixed">${esc(x.text)}<small>刚才定的</small></span>` : `<input class="ob-in" data-rowin="${i}" maxlength="40" value="${esc(x.text)}">`}</div>`; }).join("")}
        <div class="ob-plan-acts"><button class="btn btn-quiet btn-sm" data-again>换件事聊聊</button><span class="sp"></span>
          <button class="btn btn-ghost btn-sm" data-revise>${icon("edit")}让小光改改</button><button class="btn btn-main" data-take>放进计划</button></div>`;
      thread.append(card); scroll();
      card.querySelector("[data-w=title]").addEventListener("input", (e) => { P.title = e.target.value; });
      card.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
        P.days = +b.dataset.days;
        card.querySelectorAll("[data-days]").forEach((x) => x.classList.toggle("on", x === b));
      }));
      card.querySelectorAll("[data-row]").forEach((b) => b.addEventListener("click", () => { const x = P.rows[+b.dataset.row]; x.on = !x.on; b.closest(".ob-prow").classList.toggle("off", !x.on); }));
      card.querySelectorAll("[data-rowin]").forEach((inp) => inp.addEventListener("input", () => { P.rows[+inp.dataset.rowin].text = inp.value; }));
      card.querySelector("[data-again]").addEventListener("click", () => goalPick());
      const revBtn = card.querySelector("[data-revise]");
      revBtn.addEventListener("click", () => {
        if (revising === P) {          // 误触了：不改了，这一版照样能用
          revising = null; revCard = null;
          comp.hidden = true;
          revBtn.innerHTML = `${icon("edit")}让小光改改`;
          say("好，那就用这一版。", "19");
          refresh();
          return;
        }
        revising = P; revCard = card;
        revBtn.innerHTML = `${icon("close")}不改了`;
        comp.hidden = false;
        const hints = comp.querySelector(".hints");
        hints.innerHTML = REVISE_HINTS.map((t) => `<button class="chip" data-fill="${esc(t)}">${esc(t)}</button>`).join("");
        hints.classList.remove("hide");
        hints.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.fill)));
        ta.placeholder = "哪里不合适？比如：我想 1 点前睡就行";
        say("哪里不合适？跟我说说，我再改。", "35");
        refresh(); scroll(); setTimeout(() => ta.focus(), 200);
      });
      card.querySelector("[data-take]").addEventListener("click", () => {
        if (!P.title.trim()) return card.querySelector("[data-w=title]").focus();
        W = P; done.wish = true;
        remember = [...new Set([...(r.remember || []), ...remember])].slice(0, 3);
        whyGoal = r.why_goal || whyGoal;
        hub(`好，「${P.title.trim()}」这条路先记下了，进门后在蜕变计划里。`);
      });
    }
  }

  // ---------------------------------------------------------------- 进门 ----
  async function finish() {
    if (busy) return;
    busy = true;
    root.querySelectorAll("[data-enter], [data-out]").forEach((b) => (b.disabled = true));
    const answers = { ...A, theme: localStorage.getItem("xg-theme") || "forest", remember, intent_why: whyGoal };
    if (W?.title.trim()) {
      const rows = (kind) => W.rows.filter((x) => x.kind === kind && x.on && !x.locked && x.text.trim()).map((x) => x.text.trim());
      answers.wish = { title: W.title.trim(), category: W.category, days: W.days, due_in_days: W.due, milestones: rows("ms"), habits: rows("habit"), steps: rows("step") };
      answers.intent_primary = W.title.trim();
    }
    try {
      await api.onboard(answers, carry);
      dropCarry();
      setAgentLook(A.agent_avatar_id);
      say(answers.wish ? "好啦，路已经放进蜕变计划了。" : "好啦，我们开始吧！", "10", "spin");
      setTimeout(() => window.dispatchEvent(new CustomEvent("xg:enter")), 1100);
    } catch (e) {
      busy = false;
      root.querySelectorAll("[data-enter], [data-out]").forEach((b) => (b.disabled = false));
      say("没成功，再试一次？", "34");
      toast(e.message || "没保存上", "err");
    }
  }

  $("[data-out]").addEventListener("click", () => finish());
  hub();
  setTimeout(() => ball.set("02", { force: true }), 1200);
}
