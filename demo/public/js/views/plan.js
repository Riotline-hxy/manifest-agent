// 蜕变计划 · 成长日历。
// 上面：愿望卡（左右滑，一个愿望一张：愿景、站点线、习惯）+ 所有愿望的小步（今天 / 之后 / 还没安排）；
// 下面：日历「走过的日子」（周 / 月）+ 选中那天的详情。小步可以拖进日历，或者点日历按钮选一天。
// 页面订阅数据：面板、两分钟启动、偷懒、小光在对话里改了计划，这里都会就地更新，不跳回顶部。
import { api } from "../api.js";
import { state, setData, go, xpNote, subscribe } from "../store.js";
import { esc, toast, confirmSheet, icon, tile, sheet, h } from "../ui.js";
import { flyGain, burstAt, confetti } from "../fx.js";
import { mountBall, celebrate } from "../ball.js";
import { CATS, catOf, figureSVG, visionSVG, playFx } from "../journey.js";
import { restBannerHTML, bindRestBanner, openLazy } from "../rest.js";
import { openMoment, deleteMoment } from "../moments.js";
import { openKick } from "../kick.js";
import { addDays, diffDays, md, wk, planOf, planLabel, planModel, calendarHTML, dayHTML, shiftPeriod,
  scheduleSheet, pickSheet, bindDrag, bindSwipe, reduced } from "../plan-cal.js";

// 重画时保留：正在看哪个愿望、日历选中哪天、周还是月
const ui = { owner: null, wish: "", serverWish: "", day: "", mode: "week", data: null, fx: null, gain: null, flash: "" };
let mounted = null, subbed = false, ball = null, ctl = null, selTimer = 0;

function onData() {
  if (state.route !== "plan" || !mounted?.isConnected) { cleanup(); return; }
  if (state.data !== ui.data) renderPlan(mounted, { quiet: true });
}
function cleanup() {
  ctl?.abort(); ctl = null;
  ball?.destroy(); ball = null;
  clearTimeout(selTimer);
}

export function renderPlan(root, { quiet = false } = {}) {
  mounted = root;
  if (!subbed) { subbed = true; subscribe(onData); }
  cleanup();
  ctl = new AbortController();
  const signal = ctl.signal;
  const data = state.data;
  ui.data = data;
  if (ui.owner !== state.user?.id) Object.assign(ui, { owner: state.user?.id, wish: "", serverWish: "", day: "", mode: "week" });
  const J = data.journey || { wishes: [], moments: [] };
  if (!(J.wishes || []).length) return renderStart(root, J);
  const M = planModel(data);
  // 别处换了正在看的愿望（新开了一个、小光帮你收起了一个）：跟着换
  if (ui.serverWish && J.current !== ui.serverWish) ui.wish = J.current;
  ui.serverWish = J.current;
  if (!M.wishes.some((w) => w.id === ui.wish)) ui.wish = M.wishes.some((w) => w.id === J.current) ? J.current : M.wishes[0].id;
  if (!ui.day) ui.day = M.today;
  const top = root.scrollTop;
  root.innerHTML = pageHTML(M, quiet);
  if (quiet) root.scrollTop = top;

  mountCarousel(root, M, signal);
  bindRestBanner(root, () => {});
  bindDrag(root, { scroller: root, signal, onDrop: (id, day) => schedule(id, day) });
  const cal = root.querySelector(".pc-cal");
  bindSwipe(cal, (n) => { ui.day = shiftPeriod(ui, n); drawCal(root, M); }, signal);
  cal.addEventListener("keydown", (e) => {
    const b = e.target.closest("[data-day]");
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (!b || !step) return;
    e.preventDefault();
    ui.day = addDays(b.dataset.day, step);
    drawCal(root, M);
    root.querySelector(`.pc-date[data-day="${ui.day}"]`)?.focus();
  }, { signal });
  root.addEventListener("click", (e) => onClick(e, root, M), { signal });
  drawCal(root, M);
  afterRender(root, M);
}

// ---------------------------------------------------------------- 页面 ----
function pageHTML(M, quiet) {
  const resting = M.rest.has(M.today);
  const insight = (M.J.insights || {})[ui.wish];
  const month = M.today.slice(0, 7);
  const active = [...M.days.keys()].filter((d) => d.startsWith(month) && d <= M.today && M.count(d)).length;
  return `<div class="view-inner wide plan pl ${quiet ? "quiet" : ""}">
    <div class="page-head pl-head"><div><h1>蜕变计划</h1><p>每个愿望从一小步开始，做过的都会留在日子里</p></div>
      <div class="pl-acts">
        <button class="btn btn-ghost btn-sm pl-rest ${resting ? "on" : ""}" data-rest-me aria-pressed="${resting}">${icon("moon")}${resting ? "偷懒中" : "偷个懒"}</button>
        <button class="btn btn-main btn-sm" data-compose>${icon("plus")}留下一个瞬间</button></div></div>
    <div class="pl-top">${carouselHTML(M)}${stepsHTML(M, resting)}</div>
    <div class="pl-sec"><h2>走过的日子</h2><span class="muted">${active ? `这个月有 ${active} 天留下了记录` : "做过的每件小事，都会记在那一天"}</span></div>
    <div class="pl-journal">
      <section class="card pc-card"><div class="pc-cal"></div><div class="j-fx" aria-hidden="true"></div></section>
      <section class="card pd-card" aria-live="polite"></section>
    </div>
    ${insight ? `<div class="pl-more"><section class="card j-insight">
        <div class="sec-title">${icon("sparkles")}小光的小发现 <span class="pill">猜的，你说了算</span></div>
        <p class="j-guess">${esc(insight.text)}</p>
        <div class="j-answers">${[["yes", "像我"], ["partly", "有一部分"], ["no", "不太像"], ["skip", "跳过"]].map(([a, l]) =>
          `<button class="btn btn-sm ${a === "yes" ? "btn-main" : "btn-ghost"}" data-answer="${a}" data-insight="${esc(insight.id)}">${l}</button>`).join("")}</div>
        <small class="muted">选「像我」或「有一部分」，小光会把它记成对你的了解。</small></section></div>` : ""}
  </div>`;
}

// ---------------------------------------------------------------- 愿望卡 ----
function carouselHTML(M) {
  const more = M.wishes.length < 6;
  const n = M.wishes.length + (more ? 1 : 0);
  return `<section class="pw" aria-roledescription="轮播" aria-label="我的愿望">
    <div class="pw-track" tabindex="0">${M.wishes.map((w) => wishCardHTML(w, M)).join("")}
      ${more ? `<article class="pw-card card pw-new" aria-label="开启新愿望"><div class="pw-new-in">${tile("plus", "var(--accent)", 44)}
        <b>开启新愿望</b><p>想靠近的另一种自己，也可以从今天开始。</p><button class="btn btn-main btn-sm" data-new-wish>新的愿望</button></div></article>` : ""}</div>
    ${n > 1 ? `<div class="pw-nav"><button class="icon-btn sm" data-pw="-1" aria-label="上一个愿望">${icon("back")}</button>
      <span class="pw-dots">${Array.from({ length: n }, (_, i) => `<button class="pw-dot" data-pw-i="${i}" aria-label="${i < M.wishes.length ? `看「${esc(M.wishes[i].title)}」` : "开启新愿望"}"></button>`).join("")}</span>
      <button class="icon-btn sm" data-pw="1" aria-label="下一个愿望">${icon("arrow")}</button></div>` : ""}
    <span class="pw-ball" role="button" tabindex="0" aria-label="和小光聊聊这条路" aria-expanded="false"></span>
    <div class="pw-say" hidden></div>
  </section>`;
}

function wishCardHTML(w, M) {
  const cat = catOf(w.category);
  const start = w.started.slice(0, 10);
  const walked = Math.max(0, diffDays(M.today, start)), left = diffDays(w.target_day, M.today);
  const pct = Math.min(100, Math.round((walked / Math.max(1, diffDays(w.target_day, start))) * 100));
  const mss = w.milestones || [];
  const next = mss.find((m) => m.status !== "done");
  const doneN = mss.filter((m) => m.status === "done").length;
  const hbs = w.habits || [];
  return `<article class="pw-card card" data-wish="${esc(w.id)}" style="--jc:${cat.color}" aria-label="${esc(w.title)}">
    <header class="pw-head">${tile(cat.icon, cat.color, 38)}<div class="pw-t"><h2>${esc(w.title)}</h2><span>${esc(cat.label)}</span></div></header>
    ${w.vision_text ? `<p class="pw-vision">${esc(w.vision_text)}</p>` : ""}
    ${w.now_text ? `<p class="pw-now">出发时：${esc(w.now_text)}</p>` : ""}
    <div class="pw-days"><span>走了 <b>${walked}</b> 天 · ${left > 0 ? `还有 <b>${left}</b> 天` : left === 0 ? "今天就是计划的日子" : "计划日已过，可以换个日子"}</span>
      <i class="pw-bar" aria-hidden="true"><i style="width:${pct}%"></i></i></div>
    <div class="pw-sec"><b>站点</b><small>${mss.length ? `${doneN}/${mss.length}${next ? ` · 下一站「${esc(next.title)}」` : " · 都到了"}` : "路上看得见的一站，比如「能连续跑 5 公里」"}</small></div>
    <div class="pw-ms">${mss.map((m, k) => `${k ? `<i class="pw-seg ${m.status === "done" ? "on" : ""}"></i>` : ""}<button class="pw-st ${m.status === "done" ? "done" : m === next ? "next" : ""}"
      data-ms="${esc(m.id)}" title="${esc(m.title)}" aria-label="站点「${esc(m.title)}」${m.status === "done" ? "，已到达" : ""}">${m.status === "done" ? icon("check") : ""}</button>`).join("")}
      ${mss.length ? `<i class="pw-seg add"></i>` : ""}<button class="pw-st add" data-add-ms aria-label="加一个站点" title="加一个站点">${icon("plus")}</button></div>
    <div class="pw-sec"><b>习惯</b><small></small><button class="btn btn-quiet btn-sm pw-add" data-add-habit>${icon("plus")}习惯</button></div>
    <div class="habits">${hbs.map((hb, i) => habitRow(hb, M.J, i)).join("") || `<p class="pw-none">还没有习惯，可以从一个舒服的节奏开始。</p>`}</div>
    <footer class="pw-foot"><button class="btn btn-quiet btn-sm" data-go-report>${icon("report")}蜕变报告</button><button class="btn btn-quiet btn-sm" data-edit-wish>${icon("edit")}编辑愿望</button></footer>
  </article>`;
}

function habitRow(hb, J, i) {
  const dots = Array.from({ length: 7 }, (_, k) => {
    const d = addDays(J.week_start, k);
    const cls = hb.days.includes(d) ? "on" : (J.rest_days || []).includes(d) || (hb.skips || []).includes(d) ? "rest" : d === J.today ? "now" : d > J.today ? "later" : "";
    return `<i class="${cls}" title="${md(d)} ${wk(d)}"></i>`;
  }).join("");
  const met = hb.week >= hb.need;
  const resting = (J.rest_days || []).includes(J.today);
  return `<div class="hrow ${hb.today ? "done" : ""} ${hb.skipped && !hb.today ? "skipped" : ""}" style="--i:${i}">
    <button class="check" data-hcheck="${esc(hb.id)}" aria-pressed="${hb.today}" aria-label="${hb.today ? "撤销今天的打卡" : "今天做了"}：${esc(hb.title)}">${icon("check")}</button>
    <div class="h-main"><div class="h-t">${esc(hb.title)}</div>
      <div class="h-s">${esc(hb.freq_text)}${hb.cue ? ` · ${esc(hb.cue)}` : ""} · 本周 ${hb.week}/${hb.need}${met && hb.freq === "weekly" ? ` <span class="pill good">这周做到了</span>` : ""}${hb.skipped && !hb.today ? ` <span class="pill">${icon("moon")}今天先休息</span>` : ""}</div></div>
    <div class="h-week" aria-label="本周打卡">${dots}</div>
    ${hb.today || resting ? "" : `<button class="icon-btn sm ${hb.skipped ? "on" : ""}" data-hskip="${esc(hb.id)}" aria-label="${hb.skipped ? "取消：今天先不做" : "今天先不做"}：${esc(hb.title)}" title="${hb.skipped ? "取消今天先不做" : "今天先不做"}">${icon("moon")}</button>`}
    <button class="icon-btn sm" data-hedit="${esc(hb.id)}" aria-label="编辑习惯：${esc(hb.title)}">${icon("settings")}</button>
  </div>`;
}

function mountCarousel(root, M, signal) {
  const track = root.querySelector(".pw-track");
  const cards = [...track.querySelectorAll(".pw-card")];
  const stride = () => (cards[1] ? cards[1].offsetLeft - cards[0].offsetLeft : track.clientWidth) || 1;
  let idx = Math.max(0, M.wishes.findIndex((w) => w.id === ui.wish));
  const paint = () => {
    cards.forEach((c, k) => { c.classList.toggle("on", k === idx); c.setAttribute("aria-hidden", String(k !== idx)); });
    root.querySelectorAll(".pw-dot").forEach((d, k) => d.setAttribute("aria-current", String(k === idx)));
    const [prev, next] = root.querySelectorAll("[data-pw]");
    if (prev) { prev.disabled = idx === 0; next.disabled = idx === cards.length - 1; }
  };
  track.scrollLeft = idx * stride();
  paint();
  // 停在哪个愿望上，它就是「正在看的愿望」：小光在对话里加小步、加习惯，默认放进这里
  const settle = () => {
    const w = M.wishes[idx];
    if (!w || w.id === ui.wish) return;
    ui.wish = w.id;
    ball?.pulse("bounce");
    clearTimeout(selTimer);
    selTimer = setTimeout(() => api.wish("select", { id: w.id })
      .then((out) => { ui.serverWish = w.id; setData(out, { silent: true }); ui.data = state.data; }).catch(() => {}), 220);
  };
  let t = 0;
  const land = (k) => {
    if (k !== idx) { idx = k; paint(); closeSay(root); }
    clearTimeout(t);
    t = setTimeout(settle, 160);
  };
  // 按钮、圆点、方向键：马上换到那一张（不等滚动事件），再平滑滑过去
  const goTo = (k) => {
    k = Math.max(0, Math.min(cards.length - 1, k));
    land(k);
    track.scrollTo({ left: k * stride(), behavior: reduced() ? "instant" : "smooth" });
  };
  track.addEventListener("scroll", () => land(Math.max(0, Math.min(cards.length - 1, Math.round(track.scrollLeft / stride())))),
    { passive: true, signal });
  root._pwGo = (k) => goTo(k === "+" ? idx + 1 : k === "-" ? idx - 1 : k);
  track.addEventListener("keydown", (e) => {
    if (e.target !== track) return;
    const k = { ArrowLeft: idx - 1, ArrowRight: idx + 1, Home: 0, End: cards.length - 1 }[e.key];
    if (k !== undefined) { e.preventDefault(); goTo(k); }
  }, { signal });
  // 手机上露出来的半张卡：点它就滑过去
  track.addEventListener("click", (e) => {
    const c = e.target.closest(".pw-card");
    const k = cards.indexOf(c);
    if (c && k !== idx) { e.preventDefault(); e.stopPropagation(); goTo(k); }
  }, { capture: true, signal });
  addEventListener("resize", () => { if (track.isConnected) track.scrollLeft = idx * stride(); }, { signal });

  // 小光：浮在愿望卡右上角，不跟着卡片滑走；点它聊聊这条路
  const holder = root.querySelector(".pw-ball");
  ball = mountBall(holder, { size: matchMedia("(max-width: 760px)").matches ? 52 : 62, interactive: false });
  const toggle = () => (root.querySelector(".pw-say").hidden ? openSay(root, M) : closeSay(root));
  holder.addEventListener("click", toggle, { signal });
  holder.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }, { signal });
  document.addEventListener("click", (e) => { if (!e.target.closest(".pw-say, .pw-ball")) closeSay(root); }, { signal });
}

function talkChips(w) {
  const t = `「${w.title}」`;
  return [
    ["帮我规划这条路", `我想好好规划${t}这个愿望，计划在 ${md(w.target_day)} 前后实现。先问我几个问题，再帮我拆成里程碑、习惯和小步。`],
    ["这周怎么安排", `${t}这周怎么安排比较合适？看看我现在的习惯和小步，帮我把小步排到这周的日子里。`],
    ["我有点卡住了", `${t}这件事我最近有点卡住了，想跟你聊聊。`],
  ];
}
function openSay(root, M) {
  const w = M.wishOf(ui.wish);
  const say = root.querySelector(".pw-say");
  if (!w || !say) return;
  say.innerHTML = `<p>想聊聊「${esc(w.title)}」的哪一块？</p><div>${talkChips(w).map(([l], i) => `<button class="chip" data-talk="${i}">${esc(l)}</button>`).join("")}</div>`;
  say.hidden = false;
  root.querySelector(".pw-ball").setAttribute("aria-expanded", "true");
  ball?.set("curious");
}
function closeSay(root) {
  const say = root.querySelector(".pw-say");
  if (!say || say.hidden) return;
  say.hidden = true;
  root.querySelector(".pw-ball")?.setAttribute("aria-expanded", "false");
}

// ---------------------------------------------------------------- 小步 ----
function stepsHTML(M, resting) {
  const G = M.groups;
  let i = 0;
  const row = (s) => {
    const p = planOf(s, M.today);
    return `<div class="step pstep ${ui.flash === s.id ? "pop" : ""}" data-drag="${esc(s.id)}" style="--i:${i++};--tc:${M.color(s.wish_id)}">
      <button class="check" data-done="${esc(s.id)}" aria-label="完成「${esc(s.title)}」">${icon("check")}</button>
      <div class="step-main"><div class="st">${esc(s.title)}</div><div class="sw"><i class="wdot"></i><span>${esc(M.wishOf(s.wish_id)?.title || "")}</span>${p ? `<b>· ${planLabel(p, M.today)}</b>` : ""}</div></div>
      <button class="icon-btn sm" data-kick="${esc(s.id)}" aria-label="两分钟启动「${esc(s.title)}」" title="两分钟启动">${icon("footsteps")}</button>
      <button class="icon-btn sm ${p ? "on" : ""}" data-plan="${esc(s.id)}" aria-label="「${esc(s.title)}」安排到哪天" title="安排到哪天">${icon("calendar")}</button></div>`;
  };
  const any = G.today.length || G.later.length;
  const group = (label, list) => (list.length ? `${label ? `<div class="ps-g">${label}</div>` : ""}<div class="steps">${list.map(row).join("")}</div>` : "");
  const live = new Set(M.wishes.map((w) => w.id));
  const cleared = M.wishes.filter((w) => !M.todo.some((s) => s.wish_id === w.id) && M.steps.some((s) => s.wish_id === w.id && s.status === "done"));
  const dropped = M.steps.filter((s) => s.status === "dropped" && live.has(s.wish_id));
  const fine = matchMedia("(pointer: fine)").matches;
  return `<section class="card ps-card ${resting ? "resting" : ""}">
    <header class="ps-h"><h3>小步</h3><span class="muted">${M.todo.length ? `${M.todo.length} 件待做` : ""}</span><span class="sp"></span>
      <button class="btn btn-ghost btn-sm" data-add-step>${icon("plus")}小步</button></header>
    ${resting ? restBannerHTML() : ""}
    <div class="ps-list">
      ${M.todo.length ? group("今天", G.today) + group("之后", G.later) + group(any ? "还没安排" : "", G.none)
        : `<p class="muted ps-none">现在没有待做的小步。</p>`}
      ${cleared.map((w) => `<button class="ps-clear" data-think="${esc(w.id)}">${icon("checkc")}<span>「${esc(w.title)}」的小步都做完了</span><b>和小光想想下一步</b></button>`).join("")}
    </div>
    ${M.todo.length && !any ? `<p class="ps-tip">${fine ? "把小步拖到下面的日历里，或者点日历按钮，给它选一天。" : "点日历按钮，给小步选一天。"}</p>` : ""}
    ${dropped.length ? `<details class="j-dropped"><summary>先放一放的 ${dropped.length} 件</summary>
      ${dropped.map((s) => `<div class="done-row dim"><span>${esc(s.title)}</span><button class="btn btn-sm btn-ghost" data-back="${esc(s.id)}">放回来</button></div>`).join("")}</details>` : ""}
  </section>`;
}

// ---------------------------------------------------------------- 日历 ----
function placeInd(tabs) {
  const on = tabs.querySelector("button.on"), ind = tabs.querySelector(".ind");
  if (on && ind) Object.assign(ind.style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
}
function drawCal(root, M) {
  const cal = root.querySelector(".pc-cal");
  cal.innerHTML = calendarHTML(M, ui);
  root.querySelector(".pd-card").innerHTML = dayHTML(M, ui.day);
  const tabs = cal.querySelector(".pc-mode");
  placeInd(tabs);
  requestAnimationFrame(() => placeInd(tabs));
}

function afterRender(root, M) {
  const card = root.querySelector(".pc-card");
  const cellOf = (d) => root.querySelector(`.pc-cell[data-cell="${d}"] .pc-date`);
  if (ui.fx) {
    const { day, wid } = ui.fx;
    ui.fx = null;
    const cell = cellOf(day), cat = catOf(M.wishOf(wid)?.category);
    if (cell) {
      card.style.setProperty("--jc", cat.color);
      cell.classList.add("lit");
      setTimeout(() => cell.isConnected && playFx(cat.fx, card, cell, { frac: 0.5, neighbors: [] }), 160);
    }
  }
  if (ui.gain) {
    const { day, xp } = ui.gain;
    ui.gain = null;
    const cell = cellOf(day);
    if (cell && (xp?.amount || xp?.coins > 0)) setTimeout(() => cell.isConnected && flyGain(cell, xp), 360);
  }
  ui.flash = "";
}

// ---------------------------------------------------------------- 点击 ----
const CLICK = "[data-done],[data-plan],[data-kick],[data-back],[data-think],[data-hcheck],[data-hskip],[data-hedit],[data-ms],[data-add-ms],"
  + "[data-add-habit],[data-add-step],[data-edit-wish],[data-new-wish],[data-rest-me],[data-compose],[data-compose-day],[data-pick-day],"
  + "[data-day],[data-mode],[data-period],[data-today],[data-tag],[data-go-report],[data-answer],[data-pw],[data-pw-i],[data-talk],[data-edit],[data-del]";

function onClick(e, root, M) {
  const t = e.target.closest(CLICK);
  if (!t || !root.contains(t) || t.disabled) return;
  const d = t.dataset;
  const wish = () => M.wishOf(ui.wish) || M.wishes[0];
  const wishById = (id) => M.wishOf(id) || wish();
  const stepById = (id) => M.steps.find((s) => s.id === id);
  const habitById = (id) => M.wishes.flatMap((w) => w.habits || []).find((x) => x.id === id);
  const cardWish = () => wishById(t.closest(".pw-card")?.dataset.wish);
  if ("done" in d) return doneStep(t, d.done, M);
  if ("plan" in d || "tag" in d) {
    const s = stepById(d.plan || d.tag);
    if (s) scheduleSheet(s, M.today, (out, kind) => afterSchedule(out, s, kind));
    return;
  }
  if ("kick" in d) { const s = stepById(d.kick); if (s) openKick({ task: s.title, stepId: s.id }); return; }   // 从小步进来：小光知道它挂在哪个愿望下
  if ("back" in d) return act(api.step("todo", { id: d.back }));
  if ("think" in d) {
    state.autoSend = `「${wishById(d.think).title}」的小步都做完了。帮我想想接下来可以做的两三个小步吧，先问问我现在的情况。`;
    return go("chat");
  }
  if ("hcheck" in d) return checkHabit(t, d.hcheck, M);
  if ("hskip" in d) {
    const hb = habitById(d.hskip);
    return act(api.habit(hb.skipped ? "unskip" : "skip", { id: hb.id }), hb.skipped ? "" : `「${hb.title}」今天先休息，明天见`, "moon");
  }
  if ("hedit" in d) return habitSheet(habitById(d.hedit));
  if ("ms" in d) return msSheet(root, cardWish(), d.ms);
  if ("addMs" in d) return addSheet(cardWish(), "milestone");
  if ("addHabit" in d) return addSheet(cardWish(), "habit");
  if ("addStep" in d) return addSheet(wish(), "step");
  if ("editWish" in d) return wishSheet(cardWish(), M.J);
  if ("newWish" in d) return wishSheet(null, M.J);
  if ("restMe" in d) return openLazy({});
  if ("compose" in d) return openMoment({ wish: wish(), onSaved: momentSaved });
  if ("composeDay" in d) return openMoment({ wish: wish(), day: d.composeDay, onSaved: momentSaved });
  if ("pickDay" in d) {
    const day = d.pickDay;
    return pickSheet(M, day, {
      onPick: (out, id) => { ui.day = day; ui.flash = id; setData(out); toast(`放进${planLabel(day, M.today)}了`, "", "calendar"); },
      onAdd: () => addSheet(wish(), "step", day),
    });
  }
  if ("day" in d) { ui.day = d.day; drawCal(root, M); return; }
  if ("mode" in d) { ui.mode = d.mode; drawCal(root, M); return; }
  if ("period" in d) { ui.day = shiftPeriod(ui, +d.period); drawCal(root, M); return; }
  if ("today" in d) { ui.day = M.today; drawCal(root, M); return; }
  if ("goReport" in d) return go("report");
  if ("answer" in d) {
    return act(api.insight({ insight_id: d.insight, answer: d.answer }),
      { yes: "记下了", partly: "记下了，标着「只有一部分像」", no: "好，这条就不记了", skip: "先跳过" }[d.answer], "sparkles");
  }
  if ("pw" in d) return root._pwGo?.(+d.pw > 0 ? "+" : "-");
  if ("pwI" in d) return root._pwGo?.(+d.pwI);
  if ("talk" in d) { state.autoSend = talkChips(wish())[+d.talk][1]; return go("chat"); }
  if ("edit" in d || "del" in d) {
    const m = (M.J.moments || []).find((x) => x.id === t.closest(".j-m")?.dataset.id);
    if (!m) return;
    if ("edit" in d) return openMoment({ moment: m, onSaved: (out) => { setData(out); toast("改好了", "", "camera"); } });
    return deleteMoment(m).then((out) => out && setData(out)).catch((e) => toast(e.message, "err"));
  }
}

// 改数据：成功后 setData，页面跟着订阅重画（保留滚动位置）
async function act(p, msg = "", ic = "") {
  try { setData(await p); if (msg) toast(msg, "", ic); }
  catch (e) { toast(e.message, "err"); }
}

async function doneStep(btn, id, M) {
  const row = btn.closest(".step");
  if (row?.classList.contains("checking")) return;
  row?.classList.add("checking");
  const s = M.steps.find((x) => x.id === id);
  try {
    const out = await api.step("done", { id });
    burstAt(btn, 30);
    celebrate();
    if (out.xp?.amount || out.xp?.coins > 0) flyGain(btn, out.xp); else toast(xpNote(out.xp) || "完成了");
    ui.day = M.today;
    ui.fx = { day: M.today, wid: s?.wish_id };
    setTimeout(() => setData(out), 480);
  } catch (e) { row?.classList.remove("checking"); toast(e.message, "err"); }
}

async function checkHabit(btn, id, M) {
  const w = M.wishes.find((x) => (x.habits || []).some((hb) => hb.id === id));
  const hb = (w?.habits || []).find((x) => x.id === id);
  if (!hb) return;
  const undo = hb.today;
  btn.closest(".hrow").classList.toggle("done", !undo);
  try {
    const out = await api.habit(undo ? "uncheck" : "check", { id });
    if (!undo) {
      burstAt(btn, 26);
      flyGain(btn, out.xp);
      celebrate();
      ui.fx = { day: M.today, wid: w.id };
    }
    setTimeout(() => setData(out), undo ? 0 : 420);
  } catch (e) { toast(e.message, "err"); btn.closest(".hrow")?.classList.toggle("done", undo); }
}

function schedule(id, day) {
  const s = (state.data.steps || []).find((x) => x.id === id);
  if (!s || planOf(s, state.data.journey.today) === day) return;
  api.step("schedule", { id, day }).then((out) => afterSchedule(out, s, day)).catch((e) => toast(e.message, "err"));
}
function afterSchedule(out, s, kind) {
  const today = state.data.journey.today;
  if (kind === "drop") { setData(out); toast("先放一放，想做的时候在「小步」下面放回来", "", "moon"); return; }
  ui.flash = s.id;
  if (kind) ui.day = kind;
  setData(out);
  toast(kind ? `「${s.title}」安排在${planLabel(kind, today)}` : `「${s.title}」先不安排日子`, "", "calendar");
}

// 站点（里程碑）：点开看它的日子，确认到达
function msWhen(m, today) {
  if (m.status === "done") return `${md(m.done_at.slice(0, 10))} 到达`;
  if (!m.due_day) return "还没定日子，想定的话可以跟小光说";
  const n = diffDays(m.due_day, today);
  return `计划 ${md(m.due_day)} 到 · ${n > 0 ? `还有 ${n} 天` : n === 0 ? "就是今天" : `过了 ${-n} 天，不着急`}`;
}
function msSheet(root, w, id) {
  const m = (w?.milestones || []).find((x) => x.id === id);
  if (!m) return;
  const today = state.data.journey.today;
  const done = m.status === "done";
  const body = h("div", { class: "pm-sheet" }, h("p", { class: "pm-when" }, msWhen(m, today)),
    h("p", { class: "muted pm-wish" }, `「${w.title}」路上的一站`));
  const s = sheet({ title: m.title, body, sticker: "flag", footer: [
    h("button", { class: "btn btn-ghost", onclick: () => s.close() }, done ? "先不动" : "还没到"),
    h("button", { class: "btn btn-main", onclick: async () => {
      s.close();
      if (done) return act(api.milestone("todo", { id: m.id }));
      const dot = root.querySelector(`[data-ms="${CSS.escape(m.id)}"]`);
      try {
        const out = await api.milestone("done", { id: m.id });
        if (dot) {
          const r = dot.getBoundingClientRect();
          confetti(r.left + r.width / 2, r.top + r.height / 2, 70, 0.8);
          dot.classList.add("done");
          flyGain(dot, out.xp);
        }
        celebrate(true);
        toast(`到达「${m.title}」`, "", "flag");
        ui.day = today;
        ui.fx = { day: today, wid: w.id };
        setTimeout(() => setData(out), 380);
      } catch (e) { toast(e.message, "err"); }
    } }, done ? "改回还没到" : "我到这一站了")] });
  s.panel.classList.add("j-sheet");
}

// 瞬间：和「瞬间」页同一张卡片；留下之后日历跳到那一天，那一格亮一下、经验金币从那儿飞出去
function momentSaved(out, { day, wish_id }) {
  ui.day = day;
  ui.fx = { day, wid: wish_id };
  if (out.xp?.amount || out.xp?.coins > 0) ui.gain = { day, xp: out.xp };
  else toast(xpNote(out.xp) ? `留下了 · ${xpNote(out.xp)}` : "留下了", "", "camera");
  setData(out);
}

// 有好几个愿望时：选放在哪个愿望下
function wishPick(cur, onPick) {
  const ws = state.data.journey.wishes || [];
  if (ws.length < 2) return null;
  const box = h("div", { class: "j-wishpick", role: "radiogroup", "aria-label": "放在哪个愿望下" });
  const draw = (id) => {
    box.innerHTML = ws.map((w) => `<button type="button" class="chip ${w.id === id ? "on" : ""}" data-w="${esc(w.id)}" role="radio" aria-checked="${w.id === id}">
      ${tile(catOf(w.category).icon, catOf(w.category).color, 20)}<span>${esc(w.title)}</span></button>`).join("");
    box.querySelectorAll("[data-w]").forEach((b) => b.addEventListener("click", () => { draw(b.dataset.w); onPick(ws.find((w) => w.id === b.dataset.w)); }));
  };
  draw(cur);
  return box;
}

// ---------------------------------------------------------------- 添加：小步 / 习惯 / 里程碑 ----
const TYPES = {
  step: ["flag", "var(--c-orange)", "小步", "做一次就完成的事", "比如：办好健身卡"],
  habit: ["clock", "var(--c-mint)", "习惯", "重复做的事，每天或每周几次", "比如：去健身房练 40 分钟"],
  milestone: ["star", "var(--c-violet)", "站点", "路上看得见的一站", "比如：能连续跑 5 公里"],
};

function addSheet(w0, type = "step", day = "") {
  let w = w0;
  const today = state.data.journey.today;
  let freq = "daily", per = 3, due = "", plan = day;
  const body = h("div", { class: "j-add" });
  const pick = wishPick(w.id, (nw) => { w = nw; });
  const draw = () => {
    const T = TYPES[type];
    body.innerHTML = `
      <div class="j-pickslot"></div>
      <div class="j-types">${Object.entries(TYPES).map(([k, t]) => `<button type="button" class="j-type ${k === type ? "on" : ""}" data-type="${k}">
        ${tile(t[0], t[1], 32)}<b>${t[2]}</b><small>${t[3]}</small></button>`).join("")}</div>
      <label class="lbl">${type === "habit" ? "要重复做的事" : type === "milestone" ? "这一站是什么" : "这一步是什么"}</label>
      <input class="field" id="aTitle" maxlength="${type === "step" ? 40 : 30}" placeholder="${T[4]}">
      ${type === "habit" ? `<label class="lbl">多久一次</label>
        <div class="j-days">${[["daily", 0, "每天"], ["weekly", 1, "每周 1 次"], ["weekly", 2, "每周 2 次"], ["weekly", 3, "每周 3 次"], ["weekly", 5, "每周 5 次"]].map(([f, n, l]) =>
          `<button type="button" class="chip ${f === freq && (f === "daily" || n === per) ? "on" : ""}" data-freq="${f}" data-per="${n}">${l}</button>`).join("")}</div>` : ""}
      ${type === "milestone" ? `<label class="lbl">大概什么时候到 <span class="muted">（可选）</span></label>
        <div class="j-days">${[[7, "一周后"], [30, "一个月后"], [diffDays(w.target_day, today), "计划日"]].filter(([n]) => n > 0).map(([n, l]) =>
          `<button type="button" class="chip ${due === addDays(today, n) ? "on" : ""}" data-due="${addDays(today, n)}">${l}</button>`).join("")}
          <input class="field field-date" type="date" min="${today}" value="${due}" aria-label="选日期"></div>` : ""}
      ${type === "step" ? `<label class="lbl">为什么做它 <span class="muted">（可选）</span></label><input class="field" id="aWhy" maxlength="60" placeholder="比如：先让自己走进健身房">
        ${plan ? `<div class="j-plan-on">${icon("calendar")}<span>安排在${planLabel(plan, today)}（${md(plan)}）</span><button type="button" class="btn btn-quiet btn-sm" data-unplan>不安排</button></div>` : ""}` : ""}`;
    if (pick) body.querySelector(".j-pickslot").append(h("div", { class: "lbl" }, "放在哪个愿望下"), pick);
    body.querySelectorAll("[data-type]").forEach((b) => b.addEventListener("click", () => { type = b.dataset.type; draw(); }));
    body.querySelectorAll("[data-freq]").forEach((b) => b.addEventListener("click", () => {
      freq = b.dataset.freq; per = +b.dataset.per || 3;
      body.querySelectorAll("[data-freq]").forEach((x) => x.classList.toggle("on", x === b));
    }));
    body.querySelectorAll("[data-due]").forEach((b) => b.addEventListener("click", () => {
      due = b.dataset.due; body.querySelector(".field-date").value = due;
      body.querySelectorAll("[data-due]").forEach((x) => x.classList.toggle("on", x === b));
    }));
    body.querySelector(".field-date")?.addEventListener("change", (e) => {
      due = e.target.value; body.querySelectorAll("[data-due]").forEach((x) => x.classList.remove("on"));
    });
    body.querySelector("[data-unplan]")?.addEventListener("click", () => { plan = ""; body.querySelector(".j-plan-on")?.remove(); });
    body.querySelector("#aTitle").addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
    setTimeout(() => body.querySelector("#aTitle")?.focus(), 40);
  };
  const save = async () => {
    const title = body.querySelector("#aTitle").value.trim();
    if (!title) return body.querySelector("#aTitle").focus();
    try {
      let out;
      if (type === "step") {
        out = await api.step("add", { title, why: body.querySelector("#aWhy")?.value || "", wish_id: w.id, day: plan });
        ui.flash = (out.steps || [])[0]?.id || "";
        if (plan) ui.day = plan;
      } else if (type === "habit") out = await api.habit("add", { wish_id: w.id, title, freq, per_week: per });
      else out = await api.milestone("add", { wish_id: w.id, title, due_day: due });
      s.close();
      setData(out);
      toast(`加进「${w.title}」了`, "", TYPES[type][0]);
    } catch (e) { toast(e.message, "err"); }
  };
  draw();
  const s = sheet({ title: "给这条路加点东西", body, sticker: "plus",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: save }, "加进去")] });
  s.panel.classList.add("j-sheet");
}

function habitSheet(hb) {
  if (!hb) return;
  let freq = hb.freq, per = hb.freq === "weekly" ? hb.per_week : 3;
  const body = h("div", { class: "j-add", html: `
    <label class="lbl">名字</label><input class="field" id="hTitle" maxlength="30" value="${esc(hb.title)}">
    <label class="lbl">多久一次</label>
    <div class="j-days">${[["daily", 0, "每天"], ["weekly", 1, "每周 1 次"], ["weekly", 2, "每周 2 次"], ["weekly", 3, "每周 3 次"], ["weekly", 5, "每周 5 次"]].map(([f, n, l]) =>
      `<button type="button" class="chip ${f === freq && (f === "daily" || n === per) ? "on" : ""}" data-freq="${f}" data-per="${n}">${l}</button>`).join("")}</div>
    <p class="muted j-note">一共打卡 ${hb.total} 次。</p>
    <div class="j-archive"><button class="btn btn-quiet btn-sm" id="hArchive">${icon("moon")}收起这个习惯</button><small class="muted">打卡记录会留在日历上。</small></div>` });
  body.querySelectorAll("[data-freq]").forEach((b) => b.addEventListener("click", () => {
    freq = b.dataset.freq; per = +b.dataset.per || 3;
    body.querySelectorAll("[data-freq]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  body.querySelector("#hArchive").addEventListener("click", async () => {
    try { const out = await api.habit("edit", { id: hb.id, archived: true }); s.close(); setData(out); }
    catch (e) { toast(e.message, "err"); }
  });
  const s = sheet({ title: "编辑习惯", body, sticker: "clock",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: async () => {
      try { const out = await api.habit("edit", { id: hb.id, title: body.querySelector("#hTitle").value, freq, per_week: per }); s.close(); setData(out); }
      catch (e) { toast(e.message, "err"); }
    } }, "保存")] });
  s.panel.classList.add("j-sheet");
}

// ---------------------------------------------------------------- 愿望：新建 / 编辑 ----
function catGrid(sel) {
  return `<div class="j-cats">${Object.entries(CATS).map(([id, c]) => `<button type="button" class="j-cat ${id === sel ? "on" : ""}" data-cat="${id}" style="--jc:${c.color}">
    <span class="j-cat-v">${visionSVG(id)}</span><b>${c.label}</b></button>`).join("")}</div>`;
}

function wishSheet(w, J) {
  const isNew = !w;
  const today = J.today;
  const base = isNew ? today : w.started.slice(0, 10);
  let cat = w?.category || "";
  let target = w?.target_day || addDays(today, 14);
  const vis = (id) => (J.categories || []).find((c) => c.id === id)?.vision || "";
  const spans = [[14, "14 天"], [30, "30 天"], [90, "90 天"]];
  const custom = !spans.some(([n]) => addDays(base, n) === target);
  const body = h("div", { class: "j-wish", html: `
    ${isNew ? `<p class="muted">选一个方向。分类只是帮你起个头，名字和愿景都可以自己写。</p>` : ""}
    ${catGrid(cat)}
    <label class="lbl">愿望的名字</label>
    <input class="field" id="wTitle" maxlength="30" value="${esc(w?.title || "")}" placeholder="比如：更敢开口表达">
    <label class="lbl">计划什么时候实现</label>
    <div class="j-days">${spans.map(([n, l]) => `<button type="button" class="chip ${addDays(base, n) === target ? "on" : ""}" data-span="${n}">${l}</button>`).join("")}
      <button type="button" class="chip ${custom ? "on" : ""}" data-span-custom>自定义</button>
      <input class="field field-date" type="date" min="${addDays(base, 1)}" value="${target}" aria-label="计划实现的日期" ${custom ? "" : "hidden"}></div>
    <small class="muted j-span-note">${diffDays(target, base)} 天后，${md(target)}</small>
    <label class="lbl">出发时的我 <span class="muted">（一句话，没人会评判）</span></label>
    <input class="field" id="wNow" maxlength="80" value="${esc(w?.now_text || "")}" placeholder="比如：开会时总是不敢说出自己的想法">
    <label class="lbl">向往的我</label>
    <input class="field" id="wVision" maxlength="80" value="${esc(w?.vision_text || "")}" placeholder="比如：更相信自己，愿意表达">
    ${isNew ? "" : `<div class="j-archive"><button class="btn btn-quiet btn-sm" id="wArchive">${icon("moon")}先收起这个愿望</button><small class="muted">收起后，记录都还在。</small></div>`}` });
  const t = body.querySelector("#wTitle"), v = body.querySelector("#wVision"), dIn = body.querySelector(".field-date");
  body.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
    const prev = cat;
    cat = b.dataset.cat;
    body.querySelectorAll("[data-cat]").forEach((x) => x.classList.toggle("on", x === b));
    if (!t.value || t.value === CATS[prev]?.label) t.value = CATS[cat].label;
    if (!v.value || v.value === vis(prev)) v.value = vis(cat);
  }));
  const note = () => { body.querySelector(".j-span-note").textContent = target ? `${diffDays(target, base)} 天后，${md(target)}` : ""; };
  body.querySelectorAll("[data-span]").forEach((b) => b.addEventListener("click", () => {
    target = addDays(base, +b.dataset.span); dIn.value = target; dIn.hidden = true;
    body.querySelectorAll("[data-span], [data-span-custom]").forEach((x) => x.classList.toggle("on", x === b));
    note();
  }));
  body.querySelector("[data-span-custom]").addEventListener("click", (e) => {
    body.querySelectorAll("[data-span], [data-span-custom]").forEach((x) => x.classList.toggle("on", x === e.currentTarget));
    dIn.hidden = false; dIn.focus(); dIn.showPicker?.();
  });
  dIn.addEventListener("change", () => { target = dIn.value; body.querySelectorAll("[data-span]").forEach((x) => x.classList.remove("on")); note(); });
  const save = async () => {
    if (isNew && !cat) return toast("先选一个方向");
    const payload = { title: t.value.trim(), category: cat, now_text: body.querySelector("#wNow").value, vision_text: v.value, target_day: target };
    try {
      const out = isNew ? await api.wish("add", payload) : await api.wish("edit", { id: w.id, ...payload });
      s.close();
      setData(out);
      toast(isNew ? "新的旅程开始了" : "改好了", "", catOf(cat).icon);
    } catch (e) { toast(e.message, "err"); }
  };
  body.querySelector("#wArchive")?.addEventListener("click", async () => {
    if (!(await confirmSheet("先收起这个愿望？", "它会从这里移走，做过的事和瞬间都保留在你的数据里。", "收起"))) return;
    try { const out = await api.wish("edit", { id: w.id, archived: true }); s.close(); setData(out); }
    catch (e) { toast(e.message, "err"); }
  });
  const s = sheet({ title: isNew ? "开启一个新愿望" : "编辑愿望", body, sticker: "flag",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: save }, isNew ? "开始这段旅程" : "保存")] });
  s.panel.classList.add("j-sheet");
}

// 还没有任何愿望：直接在页面上选方向
function renderStart(root, J) {
  root.innerHTML = `<div class="view-inner wide plan journey">
    <div class="page-head"><div><h1>蜕变计划</h1><p>给每个愿望定一个日子，把路拆成站点、习惯和小步，一天一天走过去</p></div></div>
    <section class="card j-startcard">
      <div class="j-start-art">${figureSVG()}</div>
      <h2>你最想靠近哪一种自己？</h2>
      <p class="muted">选一个方向，定一个想实现的日子。之后小光会陪你把路拆开，你每做一件事，日历上就多一个小圆点。</p>
      ${catGrid("")}
    </section></div>`;
  root.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
    wishSheet(null, J);
    document.querySelector(`.j-wish [data-cat="${b.dataset.cat}"]`)?.click();
  }));
}
