// 蜕变计划：一个愿望 = 一条从「定下那天」走到「计划实现那天」的轨迹 + 一条路（里程碑 · 习惯 · 小步）。
// 轨迹卡片里只有时间节点能点：起点、终点、做过事的日子、里程碑。点开是那几天具体做了什么。
// 下面是这条路本身：今天要做的习惯和小步、路上的里程碑，以及和小光一起规划的入口。
import { api } from "../api.js";
import { state, setData, go, xpNote } from "../store.js";
import { esc, toast, confirmSheet, icon, tile, sheet, h } from "../ui.js";
import { flyGain, burstAt, confetti } from "../fx.js";
import { agentMini, celebrate } from "../ball.js";
import { CATS, catOf, MOODS, curvePath, backdropSVG, figureSVG, visionSVG, playFx } from "../journey.js";
import { restBannerHTML, bindRestBanner } from "../rest.js";
import { openKick } from "../kick.js";

const WEEK = "日一二三四五六";
const BUCKETS = [1, 2, 3, 7, 14, 30];

// ---- 日期：一律以服务端给的「今天」为准做日历加减 ----
const D = (s) => new Date(s.slice(0, 10) + "T00:00:00Z");
const K = (d) => d.toISOString().slice(0, 10);
const addDays = (s, n) => K(new Date(D(s).getTime() + n * 864e5));
const diffDays = (a, b) => Math.round((D(a) - D(b)) / 864e5);
const md = (s) => `${+s.slice(5, 7)}月${+s.slice(8, 10)}日`;
const mdy = (s, ref) => (s.slice(0, 4) !== ref.slice(0, 4) ? `${s.slice(0, 4)}年` : "") + md(s);
const wk = (s) => "周" + WEEK[D(s).getUTCDay()];
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

let _path, _ro;
function measure(d) {
  if (!_path) _path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  _path.setAttribute("d", d);
  return _path;
}

// 这个愿望每天做过的事
function dayMap(w, J) {
  const m = new Map();
  const at = (d) => {
    if (!m.has(d)) m.set(d, { steps: [], habits: [], ms: [], moments: [] });
    return m.get(d);
  };
  for (const s of state.data.steps || []) if (s.wish_id === w.id && s.status === "done" && s.done_at) at(s.done_at.slice(0, 10)).steps.push(s);
  for (const hb of w.habits || []) for (const d of hb.days) at(d).habits.push(hb);
  for (const x of w.milestones || []) if (x.status === "done" && x.done_at) at(x.done_at.slice(0, 10)).ms.push(x);
  for (const x of J.moments || []) if (x.wish_id === w.id) at(x.day).moments.push(x);
  return m;
}
const countOf = (e) => e.steps.length + e.habits.length + e.ms.length + e.moments.length;

export function renderPlan(root, { fresh = "" } = {}) {
  _ro?.disconnect();
  const J = state.data.journey || { wishes: [], moments: [] };
  const wishes = J.wishes || [];
  if (!wishes.length) return renderStart(root, J);
  const w = wishes.find((x) => x.id === J.current) || wishes[0];
  const cat = catOf(w.category);
  const today = J.today;
  const days = dayMap(w, J);
  const active = [...days.keys()].sort();
  const start = [w.started.slice(0, 10), active[0] || w.started].sort()[0];
  const target = w.target_day;
  const walked = Math.max(0, diffDays(today, start));
  const left = diffDays(target, today);
  const activeDays = active.filter((d) => d <= today).length;
  const resting = (J.rest_days || []).includes(today);
  const steps = (state.data.steps || []).filter((s) => s.wish_id === w.id || (!s.wish_id && w.id === wishes[0].id));
  const todo = steps.filter((s) => s.status === "todo");
  const dropped = steps.filter((s) => s.status === "dropped");
  const hbs = w.habits || [];
  const mss = w.milestones || [];
  const insight = (J.insights || {})[w.id];

  root.innerHTML = `
    <div class="view-inner wide plan journey" style="--jc:${cat.color}">
      <div class="page-head"><div><h1>蜕变计划</h1><p>给每个愿望定一个日子，把路拆成里程碑、习惯和小步，一天一天走过去</p></div></div>

      <div class="wish-tabs" role="tablist" aria-label="切换愿望">
        ${wishes.map((x) => `<button class="wish-tab ${x.id === w.id ? "on" : ""}" role="tab" aria-selected="${x.id === w.id}" data-wish="${esc(x.id)}">
          ${tile(catOf(x.category).icon, catOf(x.category).color, 26)}<span>${esc(x.title)}</span></button>`).join("")}
        ${wishes.length < 6 ? `<button class="wish-tab add" id="newWish">${icon("plus")}<span>新的愿望</span></button>` : ""}
      </div>

      <section class="j-board card cat-${esc(w.category)}">
        <header class="j-head">
          <div class="j-title"><h2>${esc(w.title)}</h2>
            <p><span class="j-catname">${esc(cat.label)}</span>${w.vision_text ? `<span class="j-vis">${esc(w.vision_text)}</span>` : ""}</p></div>
          <div class="j-meta">
            <div class="j-dates">${mdy(start, today)} 定下 <i></i> 计划 ${mdy(target, today)}</div>
            <div class="j-count">${left > 0 ? `已经走了 <b>${walked}</b> 天 · 还有 <b>${left}</b> 天` : left === 0 ? `今天就是计划的日子` : `计划日已过 ${-left} 天 · 可以在编辑里换个日子`}</div>
          </div>
          <button class="icon-btn" id="editWish" title="编辑愿望" aria-label="编辑愿望">${icon("edit")}</button>
        </header>
        <div class="j-stage" aria-label="时间轨迹"></div>
        <footer class="j-foot">
          <span class="j-legend"><i></i>${activeDays ? `${walked + 1} 天里有 <b>${activeDays}</b> 天在为它做事` : "做过事的日子会在轨迹上亮起来"}<span class="j-k"></span></span>
          <div class="row">
            <button class="btn btn-ghost btn-sm" id="review">${icon("eye")}阶段回望</button>
            <button class="btn btn-main" data-compose>${icon("plus")}留下一个瞬间</button>
          </div>
        </footer>
      </section>

      <div class="j-path">
        <section class="card j-todayc ${resting ? "resting" : ""}">
          <header class="j-sec-h"><h3>今天</h3><span class="muted">${md(today)} ${wk(today)}</span>${resting ? `<span class="pill">${icon("moon")}偷懒日 · 暂停中</span>` : ""}</header>
          ${restBannerHTML()}
          ${hbs.length ? `<div class="j-group">习惯 <small>重复做的事</small></div>
            <div class="habits">${hbs.map((hb, i) => habitRow(hb, J, i)).join("")}</div>` : ""}
          <div class="j-group">小步 <small>做一次就完成的事</small></div>
          <div class="steps">${todo.map((s, i) => `<div class="step" style="--i:${i}">
            <button class="check" data-done="${esc(s.id)}" aria-label="完成「${esc(s.title)}」">${icon("check")}</button>
            <div class="step-main"><div class="st">${esc(s.title)}</div>${s.why ? `<div class="sw">${esc(s.why)}</div>` : ""}</div>
            <button class="icon-btn step-kick" data-kick="${esc(s.id)}" aria-label="两分钟启动「${esc(s.title)}」" title="两分钟启动">${icon("play")}</button>
            <button class="btn btn-quiet btn-sm" data-drop="${esc(s.id)}">先放一放</button></div>`).join("")
            || (steps.some((s) => s.status === "done")
              ? `<div class="j-cleared"><span>${icon("checkc")}这个愿望的小步都做完了。</span><button class="btn btn-sm btn-main" data-think>${icon("sparkles")}和小光想想下一步</button></div>`
              : `<p class="muted j-none">现在没有待做的小步。</p>`)}</div>
          <div class="j-adds">
            <button class="btn btn-ghost btn-sm" data-add="step">${icon("plus")}小步</button>
            <button class="btn btn-ghost btn-sm" data-add="habit">${icon("plus")}习惯</button>
            <button class="btn btn-ghost btn-sm" data-add="milestone">${icon("plus")}里程碑</button>
          </div>
          ${dropped.length ? `<details class="j-dropped"><summary>先放一放的 ${dropped.length} 件</summary>
            ${dropped.map((s) => `<div class="done-row dim"><span>${esc(s.title)}</span><button class="btn btn-sm btn-ghost" data-back="${esc(s.id)}">放回来</button></div>`).join("")}</details>` : ""}
        </section>

        <div class="j-side">
          <section class="card j-ms">
            <header class="j-sec-h"><h3>里程碑</h3><span class="muted">${mss.filter((m) => m.status === "done").length}/${mss.length} 到达</span></header>
            ${mss.length ? `<ol class="ms-list">${mss.map((m) => `<li class="ms ${m.status === "done" ? "done" : ""}">
              <button class="ms-dot" data-ms="${esc(m.id)}" aria-label="${m.status === "done" ? "改回还没到" : "标记为已到达"}：${esc(m.title)}">${icon("check")}</button>
              <div><b>${esc(m.title)}</b><small>${msWhen(m, today)}</small></div></li>`).join("")}</ol>`
              : `<p class="muted j-none">路上可以设几个看得见的站点，比如「能连续跑 5 公里」。</p>`}
            <button class="btn btn-quiet btn-sm" data-add="milestone">${icon("plus")}加一个里程碑</button>
          </section>

          <section class="card j-talk">
            <div class="talk-head"><span class="talk-av">${agentMini()}</span>
              <div><b>和小光聊聊这条路</b><p>说说你的情况，小光帮你拆成里程碑、习惯和小步，你来挑哪些加进来。</p></div></div>
            <div class="talk-chips">${talkChips(w).map(([l, m], i) => `<button class="chip" data-talk="${i}">${esc(l)}</button>`).join("")}</div>
          </section>
        </div>
      </div>

      <div class="j-more">
        ${insight ? `<section class="card j-insight">
          <div class="sec-title">${icon("sparkles")}小光的小发现 <span class="pill">猜的，你说了算</span></div>
          <p class="j-guess">${esc(insight.text)}</p>
          <div class="j-answers">${[["yes", "像我"], ["partly", "有一部分"], ["no", "不太像"], ["skip", "跳过"]].map(([a, l]) =>
            `<button class="btn btn-sm ${a === "yes" ? "btn-main" : "btn-ghost"}" data-answer="${a}">${l}</button>`).join("")}</div>
          <small class="muted">选「像我」或「有一部分」，小光会把它记成对你的了解。</small></section>` : ""}
        <details class="fold card j-list" ${state.planListOpen ? "open" : ""}><summary>${icon("list")}按日期看走过的每一天 <span class="muted">· ${activeDays} 天</span></summary>
          ${active.filter((d) => d <= today).reverse().map((d) => { const e = days.get(d); return `<button class="j-li" data-open-day="${d}">
            <span class="j-li-day"><b>${md(d)}</b><small>${wk(d)}</small></span><span class="j-li-sum">${daySummary(e)}</span></button>`; }).join("")
            || `<p class="muted" style="padding:6px 4px">这里会按日期列出你为它做过的事。</p>`}
        </details>
        <button class="report-entry card" data-go-report>${tile("report", "var(--c-pink)", 40)}<span class="re-txt"><b>蜕变报告</b><small>回头看看这段时间的你</small></span>${icon("arrow")}</button>
      </div>
    </div>`;

  // ---- 轨迹 ----
  const board = root.querySelector(".j-board");
  const stage = root.querySelector(".j-stage");
  const model = { w, cat, J, days, start, target, today, fresh };
  let lastW = 0;
  const draw = () => {
    if (Math.abs(stage.clientWidth - lastW) < 2) return;
    lastW = stage.clientWidth;
    drawStage(root, stage, board, model);
  };
  draw();
  _ro = new ResizeObserver(draw);
  _ro.observe(stage);

  // ---- 交互 ----
  root.querySelectorAll("[data-wish]").forEach((b) => b.addEventListener("click", async () => {
    if (b.dataset.wish === w.id) return;
    try { setData(await api.wish("select", { id: b.dataset.wish })); renderPlan(root); }
    catch (e) { toast(e.message, "err"); }
  }));
  root.querySelector("[data-go-report]").addEventListener("click", () => go("report"));
  root.querySelector("#newWish")?.addEventListener("click", () => wishSheet(root, null, J));
  root.querySelector("#editWish").addEventListener("click", () => wishSheet(root, w, J));
  root.querySelectorAll("[data-compose]").forEach((b) => b.addEventListener("click", () => composeSheet(root, w)));
  root.querySelector("#review").addEventListener("click", () => reviewSheet(w));
  root.querySelector(".j-list").addEventListener("toggle", (e) => { state.planListOpen = e.target.open; });
  root.querySelectorAll("[data-open-day]").forEach((b) => b.addEventListener("click", () => dayCard(root, model, [b.dataset.openDay])));
  root.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => addSheet(root, w, b.dataset.add)));
  root.querySelector("[data-think]")?.addEventListener("click", () => {
    state.autoSend = `「${w.title}」的小步都做完了。帮我想想接下来可以做的两三个小步吧，先问问我现在的情况。`;
    go("chat");
  });
  root.querySelectorAll("[data-talk]").forEach((b) => b.addEventListener("click", () => {
    state.autoSend = talkChips(w)[+b.dataset.talk][1];
    go("chat");
  }));

  bindRestBanner(root, () => renderPlan(root));
  root.querySelectorAll("[data-hskip]").forEach((b) => b.addEventListener("click", async () => {
    const hb = hbs.find((x) => x.id === b.dataset.hskip);
    try {
      setData(await api.habit(hb.skipped ? "unskip" : "skip", { id: hb.id }));
      if (!hb.skipped) toast(`「${hb.title}」今天先休息，明天见`, "", "moon");
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  }));

  root.querySelectorAll("[data-hcheck]").forEach((b) => b.addEventListener("click", async () => {
    const hb = hbs.find((x) => x.id === b.dataset.hcheck);
    const undo = hb.today;
    b.closest(".hrow").classList.toggle("done", !undo);
    try {
      const out = await api.habit(undo ? "uncheck" : "check", { id: hb.id });
      if (!undo) {
        burstAt(b, 26);
        flyGain(b, out.xp);
        celebrate();
      }
      setTimeout(() => { setData(out); renderPlan(root, { fresh: undo ? "" : today }); }, undo ? 0 : 420);
    } catch (e) { toast(e.message, "err"); renderPlan(root); }
  }));
  root.querySelectorAll("[data-hedit]").forEach((b) => b.addEventListener("click", () => habitSheet(root, hbs.find((x) => x.id === b.dataset.hedit))));

  root.querySelectorAll("[data-ms]").forEach((b) => b.addEventListener("click", async () => {
    const m = mss.find((x) => x.id === b.dataset.ms);
    if (m.status === "done") {
      if (!(await confirmSheet("改回还没到？", `「${m.title}」会回到待到达的状态。`, "改回", "flag"))) return;
      try { setData(await api.milestone("todo", { id: m.id })); renderPlan(root); } catch (e) { toast(e.message, "err"); }
      return;
    }
    try {
      const out = await api.milestone("done", { id: m.id });
      const r = b.getBoundingClientRect();
      confetti(r.left + r.width / 2, r.top + r.height / 2, 70, 0.8);
      flyGain(b, out.xp);
      celebrate(true);
      toast(`到达「${m.title}」`, "", "flag");
      setTimeout(() => { setData(out); renderPlan(root, { fresh: today }); }, 380);
    } catch (e) { toast(e.message, "err"); }
  }));

  root.querySelectorAll("[data-answer]").forEach((b) => b.addEventListener("click", async () => {
    try {
      const out = await api.insight({ insight_id: insight.id, answer: b.dataset.answer });
      setData(out);
      toast({ yes: "记下了", partly: "记下了，标着「只有一部分像」", no: "好，这条就不记了", skip: "先跳过" }[b.dataset.answer], "", "sparkles");
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  }));

  root.querySelectorAll("[data-done]").forEach((b) => b.addEventListener("click", async () => {
    const card = b.closest(".step");
    card.classList.add("checking");
    try {
      const out = await api.step("done", { id: b.dataset.done });
      burstAt(b, 30);
      celebrate();
      if (out.xp?.amount || out.xp?.coins > 0) flyGain(b, out.xp); else toast(xpNote(out.xp) || "完成了");
      setTimeout(() => { setData(out); renderPlan(root, { fresh: today }); }, 480);
    } catch (e) { card.classList.remove("checking"); toast(e.message, "err"); }
  }));
  root.querySelectorAll("[data-kick]").forEach((b) => b.addEventListener("click", () => {
    const s = (state.data.steps || []).find((x) => x.id === b.dataset.kick);
    if (s) openKick({ task: s.title, stepId: s.id });     // 从小步进来：任务填好，小光知道它挂在哪个愿望下
  }));
  root.querySelectorAll("[data-drop]").forEach((b) => b.addEventListener("click", async () => {
    setData(await api.step("drop", { id: b.dataset.drop }));
    toast("先放一放，想做的时候在下面放回来", "", "moon");
    renderPlan(root);
  }));
  root.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", async () => {
    setData(await api.step("todo", { id: b.dataset.back }));
    renderPlan(root);
  }));
}

function talkChips(w) {
  const t = `「${w.title}」`;
  return [
    ["帮我规划这条路", `我想好好规划${t}这个愿望，计划在 ${md(w.target_day)} 前后实现。先问我几个问题，再帮我拆成里程碑、习惯和小步。`],
    ["这周怎么安排", `${t}这周怎么安排比较合适？看看我现在的习惯和小步，帮我排一排。`],
    ["我有点卡住了", `${t}这件事我最近有点卡住了，想跟你聊聊。`],
    ["看看我最近怎么样", `帮我回看一下${t}最近这段时间：我做了些什么，有什么变化？`],
  ];
}

function msWhen(m, today) {
  if (m.status === "done") return `${md(m.done_at.slice(0, 10))} 到达`;
  if (!m.due_day) return "还没定日子";
  const n = diffDays(m.due_day, today);
  return `${md(m.due_day)} · ${n > 0 ? `还有 ${n} 天` : n === 0 ? "就是今天" : `过了 ${-n} 天，不着急`}`;
}

function habitRow(hb, J, i) {
  const ws = J.week_start;
  const dots = Array.from({ length: 7 }, (_, k) => {
    const d = addDays(ws, k);
    const cls = hb.days.includes(d) ? "on" : (J.rest_days || []).includes(d) || (hb.skips || []).includes(d) ? "rest" : d === J.today ? "now" : d > J.today ? "later" : "";
    return `<i class="${cls}" title="${md(d)} ${wk(d)}"></i>`;
  }).join("");
  const met = hb.week >= hb.need;
  const resting = (J.rest_days || []).includes(J.today);
  return `<div class="hrow ${hb.today ? "done" : ""} ${hb.skipped && !hb.today ? "skipped" : ""}" style="--i:${i}">
    <button class="check" data-hcheck="${esc(hb.id)}" aria-pressed="${hb.today}" aria-label="${hb.today ? "撤销今天的打卡" : "今天做了"}：${esc(hb.title)}">${icon("check")}</button>
    <div class="h-main"><div class="h-t">${esc(hb.title)}</div>
      <div class="h-s">${esc(hb.freq_text)} · 本周 ${hb.week}/${hb.need}${met && hb.freq === "weekly" ? ` <span class="pill good">这周做到了</span>` : ""}${hb.skipped && !hb.today ? ` <span class="pill">${icon("moon")}今天先休息</span>` : ""}</div></div>
    <div class="h-week" aria-label="本周打卡">${dots}</div>
    ${hb.today || resting ? "" : `<button class="icon-btn sm ${hb.skipped ? "on" : ""}" data-hskip="${esc(hb.id)}" aria-label="${hb.skipped ? "取消：今天先不做" : "今天先不做"}：${esc(hb.title)}" title="${hb.skipped ? "取消今天先不做" : "今天先不做"}">${icon("moon")}</button>`}
    <button class="icon-btn sm" data-hedit="${esc(hb.id)}" aria-label="编辑习惯">${icon("settings")}</button>
  </div>`;
}

function daySummary(e) {
  const parts = [];
  if (e.ms.length) parts.push(`到达「${esc(e.ms[0].title)}」`);
  if (e.habits.length) parts.push(e.habits.map((x) => esc(x.title)).join("、"));
  if (e.steps.length) parts.push(`完成 ${e.steps.length} 个小步`);
  if (e.moments.length) parts.push(`留下 ${e.moments.length} 个瞬间`);
  return parts.join(" · ");
}

// ---------------------------------------------------------------- 轨迹舞台 ----
function drawStage(root, stage, board, M) {
  const { w, cat, days, start, target, today, fresh } = M;
  const W = stage.clientWidth, H = stage.clientHeight;
  if (!W || !H) return;
  const d = curvePath(W, H);
  const path = measure(d);
  const L = path.getTotalLength();
  const end = target > today ? target : today;
  const span = Math.max(1, diffDays(end, start));
  const tOf = (day) => Math.min(1, Math.max(0, diffDays(day, start) / span));
  const P = (t) => { const p = path.getPointAtLength(L * t); return { x: p.x, y: p.y }; };
  const k = BUCKETS.find((b) => (L * b) / span >= 28) || 30;
  const tToday = tOf(today);

  // 按 k 天一组合并；第一组并进起点，靠近终点的并进终点
  const groups = new Map();
  for (const day of days.keys()) {
    if (day > today || day < start) continue;
    const g = Math.floor(diffDays(day, start) / k);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(day);
  }
  const startDays = groups.get(0) || [];
  groups.delete(0);
  const goalGap = Math.max(k, 2) / span;
  const goalDays = [];
  const nodes = [];
  for (const [g, ds] of groups) {
    ds.sort();
    const t = Math.min(1, (g * k + (k - 1) / 2) / span);
    if (t > 1 - goalGap) { goalDays.push(...ds); continue; }
    nodes.push({ days: ds, t, n: ds.reduce((s, x) => s + countOf(days.get(x)), 0), ...P(t) });
  }
  nodes.sort((a, b) => a.t - b.t);
  const flags = (w.milestones || []).filter((m) => m.due_day || m.done_at).map((m) => {
    const day = m.status === "done" ? m.done_at.slice(0, 10) : m.due_day;
    const t = Math.min(0.97, Math.max(0.03, tOf(day)));
    return { m, day, t, ...P(t) };
  });
  const S0 = P(0), S1 = P(1), T = P(tToday);
  const figW = W < 560 ? 52 : 70;
  const goalW = W < 560 ? 60 : 82;
  const freshHit = (ds) => fresh && ds.includes(fresh);

  stage.innerHTML = `
    <svg class="j-back" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">
      ${backdropSVG(w.category, W, H)}
      <path class="curve-future" d="${d}"/>
      <path class="curve-past" d="${d}" style="stroke-dasharray:${(L * tToday).toFixed(1)} ${L.toFixed(1)}"/>
      <path class="curve-lit" d="${d}"/>
    </svg>
    <div class="j-start" style="left:${Math.max(2, S0.x - figW * 0.9)}px;top:${S0.y - figW * 0.95}px;width:${figW}px">${figureSVG()}</div>
    <div class="j-goal" style="left:${S1.x - goalW / 2}px;top:${S1.y - goalW - 10}px;width:${goalW}px">${visionSVG(w.category)}</div>
    <span class="j-lbl start" style="left:${S0.x}px;top:${S0.y}px">${md(start)} · 出发</span>
    <span class="j-lbl goal" style="left:${S1.x}px;top:${S1.y}px"><b>向往的我</b>${md(target)}</span>
    ${tToday > 0.04 && tToday < 0.96 ? `<span class="j-now" style="left:${T.x}px;top:${T.y}px"><i></i><em>今天</em></span>` : ""}
    <button class="j-node j-node-start ${startDays.length ? "has" : ""} ${freshHit(startDays) ? "fresh" : ""}" data-kind="start" data-days="${[start, ...startDays].filter((x, i, a) => a.indexOf(x) === i).join(",")}" data-t="0"
      style="left:${S0.x}px;top:${S0.y}px" aria-label="起点：${md(start)} 定下这个愿望"><i></i></button>
    <button class="j-node j-node-goal ${goalDays.length ? "has" : ""} ${freshHit(goalDays) ? "fresh" : ""}" data-kind="goal" data-days="${goalDays.join(",")}" data-t="1"
      style="left:${S1.x}px;top:${S1.y}px" aria-label="终点：计划在 ${md(target)} 实现"><i></i></button>
    ${flags.map((f) => `<button class="j-flag ${f.m.status === "done" ? "done" : ""}" data-days="${f.day}" data-t="${f.t}" style="left:${f.x}px;top:${f.y}px"
      aria-label="里程碑「${esc(f.m.title)}」，${md(f.day)}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 15V2"/><path d="M3.5 2.5h8.5l-2 3 2 3H3.5"/></svg><em>${esc(f.m.title)}</em></button>`).join("")}
    ${nodes.map((n) => `<button class="j-node ${freshHit(n.days) ? "fresh" : ""}" data-days="${n.days.join(",")}" data-t="${n.t}" style="left:${n.x}px;top:${n.y}px"
      aria-label="${md(n.days[0])}${n.days.length > 1 ? ` 到 ${md(n.days[n.days.length - 1])}` : ""}，做了 ${n.n} 件事" title="${md(n.days[0])}${n.days.length > 1 ? " – " + md(n.days[n.days.length - 1]) : ""}"><i></i></button>`).join("")}
    <div class="j-fx" aria-hidden="true"></div>`;
  const kEl = board.querySelector(".j-k");
  if (kEl) kEl.textContent = k > 1 ? ` · 每个点是 ${k} 天` : "";

  const all = [...stage.querySelectorAll(".j-node")];
  const open = (b) => {
    const ds = b.dataset.days ? b.dataset.days.split(",").filter(Boolean) : [];
    b.classList.remove("hit"); void b.offsetWidth; b.classList.add("hit");
    const i = all.indexOf(b);
    playFx(cat.fx, board, b, { frac: +b.dataset.t, neighbors: [all[i - 1], all[i + 1]].filter(Boolean) });
    setTimeout(() => dayCard(root, M, ds, b.dataset.kind || ""), reduced() ? 0 : 480);
  };
  stage.querySelectorAll(".j-node, .j-flag").forEach((b) => b.addEventListener("click", () => open(b)));
  const fr = stage.querySelector(".j-node.fresh");
  if (fr) setTimeout(() => playFx(cat.fx, board, fr, { frac: +fr.dataset.t, neighbors: [] }), 350);
}

// ---------------------------------------------------------------- 时间节点卡片 ----
function dayCard(root, M, ds, kind = "") {
  const { w, J, today } = M;
  const recs = state.data.records || [];
  const list = [...new Set(ds)].sort();
  const body = h("div", { class: "j-day" });
  const draw = () => {
    const fresh = dayMap((state.data.journey.wishes || []).find((x) => x.id === w.id) || w, state.data.journey);
    let html = "";
    if (kind === "start") {
      html += `<div class="j-dk start">${tile("flag", "var(--accent)", 34)}<div><b>这一天，你定下了「${esc(w.title)}」</b>
        ${w.now_text ? `<p>那时的你：${esc(w.now_text)}</p>` : `<p class="muted">可以在「编辑愿望」里写下出发时的自己。</p>`}</div></div>`;
    }
    if (kind === "goal") {
      const left = diffDays(w.target_day, today);
      const todoMs = (w.milestones || []).filter((m) => m.status !== "done");
      html += `<div class="j-dk goal"><span class="j-dk-v" style="color:${catOf(w.category).color}">${visionSVG(w.category)}</span><div>
        <b>${md(w.target_day)}，计划实现的日子</b><p>${esc(w.vision_text || catOf(w.category).label)}</p>
        <p class="muted">${left > 0 ? `还有 ${left} 天` : left === 0 ? "就是今天" : `已经过了 ${-left} 天，可以在编辑里换个日子`}${todoMs.length ? ` · 路上还有 ${todoMs.length} 个里程碑` : ""}</p></div></div>`;
    }
    for (const d of list) {
      const e = fresh.get(d) || { steps: [], habits: [], ms: [], moments: [] };
      const dueMs = (w.milestones || []).filter((m) => m.status !== "done" && m.due_day === d);
      const good = recs.filter((r) => r.day === d && ["good", "find"].includes(r.type));
      const rest = (J.rest_days || []).includes(d);
      const any = countOf(e) || dueMs.length || good.length || rest;
      if (!any && kind) continue;
      if (list.length > 1 || kind) html += `<div class="j-day-h">${md(d)} · ${wk(d)}</div>`;
      if (!any) { html += `<p class="muted">这一天还没有记录。</p>`; continue; }
      if (e.ms.length) html += e.ms.map((m) => `<div class="j-it ms">${icon("flag")}<span>到达里程碑「${esc(m.title)}」</span></div>`).join("");
      if (dueMs.length) html += dueMs.map((m) => `<div class="j-it due">${icon("flag")}<span>计划在这天到达「${esc(m.title)}」</span></div>`).join("");
      if (e.habits.length) html += `<div class="j-it">${icon("checkc")}<span>习惯打卡：${e.habits.map((x) => esc(x.title)).join("、")}</span></div>`;
      if (e.steps.length) html += e.steps.map((s) => `<div class="j-it">${icon("check")}<span>完成小步「${esc(s.title)}」</span></div>`).join("");
      if (rest) html += `<div class="j-it rest">${icon("moon")}<span>这天给自己放了假</span></div>`;
      html += e.moments.map((m) => `<article class="j-m" data-id="${esc(m.id)}">
        <p class="j-m-t">${esc(m.text)}</p>
        ${m.feeling ? `<p class="j-m-f">当时的感受：${esc(m.feeling)}</p>` : ""}
        <div class="j-m-meta">${m.mood ? `<span class="pill">${esc(m.mood)}</span>` : ""}${m.source === "chat" ? `<span class="pill">${icon("chat")}来自和小光的对话</span>` : m.source === "scene" ? `<span class="pill">${icon("sparkles")}聊聊你的愿望</span>` : ""}
          <span class="sp"></span><button class="btn btn-quiet btn-sm" data-edit>${icon("edit")}编辑</button><button class="btn btn-quiet btn-sm" data-del>${icon("trash")}删除</button></div>
      </article>`).join("");
      if (good.length) html += `<div class="j-good"><div class="lbl">那天的好消息</div>${good.map((r) => `<p>${icon("star")}${esc(r.text)}</p>`).join("")}</div>`;
    }
    body.innerHTML = html || `<p class="muted">这里还没有记录。</p>`;
    body.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      const art = b.closest(".j-m");
      const m = (state.data.journey.moments || []).find((x) => x.id === art.dataset.id);
      art.innerHTML = `<textarea class="field" rows="3" maxlength="300">${esc(m.text)}</textarea>
        <input class="field" placeholder="当时的感受（可选）" maxlength="80" value="${esc(m.feeling || "")}">
        <div class="row end"><button class="btn btn-ghost btn-sm" data-cancel>取消</button><button class="btn btn-main btn-sm" data-save>保存</button></div>`;
      art.querySelector("textarea").focus();
      art.querySelector("[data-cancel]").addEventListener("click", draw);
      art.querySelector("[data-save]").addEventListener("click", async () => {
        try {
          setData(await api.moment("edit", { id: m.id, text: art.querySelector("textarea").value, feeling: art.querySelector("input").value }));
          draw(); renderPlan(root);
        } catch (e) { toast(e.message, "err"); }
      });
    }));
    body.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      const id = b.closest(".j-m").dataset.id;
      if (!(await confirmSheet("删掉这条记录？", "删掉后，它会从轨迹和回望里一起消失。", "删掉", "trash"))) return;
      try { setData(await api.moment("delete", { id })); draw(); renderPlan(root); }
      catch (e) { toast(e.message, "err"); }
    }));
  };
  draw();
  const title = kind === "start" ? `${md(list[0] || w.started)} · 出发` : kind === "goal" ? "向往的我"
    : list.length > 1 ? `${md(list[0])} – ${md(list[list.length - 1])}` : `${md(list[0])} · ${wk(list[0])}`;
  const last = list.filter((d) => d <= today).pop();
  const s = sheet({ title, body, sticker: kind === "goal" ? catOf(w.category).icon : "clock",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "回到轨迹"),
      last ? h("button", { class: "btn btn-main", onclick: () => { s.close(); composeSheet(root, w, last); } }, "这天再记一笔") : null] });
  s.panel.classList.add("j-sheet");
}

// ---------------------------------------------------------------- 留下一个瞬间 ----
function composeSheet(root, w, day = "") {
  const cat = catOf(w.category);
  const today = state.data.journey.today;
  const opts = [[today, "今天"], [addDays(today, -1), "昨天"], [addDays(today, -2), "前天"]];
  let pickDay = day || today;
  let mood = "";
  let mine = [...(w.prompts || [])];
  let moods = [...(state.data.profile?.custom_moods || [])];
  const PH = "想写什么都行，一两句就好。比如：今天开完会有些紧张，我给自己留了十分钟，安静地喝了一杯茶。";
  const body = h("div", { class: "j-compose", html: `
    <div class="lbl">不知道写什么？从一个问题开始 <span class="muted">（也可以直接写）</span></div>
    <div class="j-prompts"></div>
    <label class="lbl">发生了什么</label>
    <textarea class="field" id="mText" rows="4" maxlength="300" placeholder="一两句就好，比如：今天开完会有些紧张，我给自己留了十分钟，安静地喝了一杯茶。"></textarea>
    <label class="lbl">当时的感受 <span class="muted">（可选）</span></label>
    <input class="field" id="mFeel" maxlength="80" placeholder="比如：慢慢放松了一些">
    <div class="j-moods"></div>
    <label class="lbl">哪一天</label>
    <div class="j-days">${opts.map(([d, l]) => `<button class="chip ${d === pickDay ? "on" : ""}" type="button" data-day="${d}">${l}</button>`).join("")}
      <input class="field field-date" type="date" max="${today}" min="${addDays(today, -365)}" value="${opts.some(([d]) => d === pickDay) ? "" : pickDay}" aria-label="选一个更早的日期"></div>` });
  const ta = body.querySelector("#mText");
  ta.placeholder = PH;
  // 一个可以加自己内容的小标签行：预设 + 自己的（带 ×）+「自己写一个」
  const chipRow = (box, { items, custom, on, pick, add, remove, addLabel, max, maxLen, ph }) => {
    const draw = () => {
      box.innerHTML = items().map((t) => `<button class="chip ${on() === t ? "on" : ""}" type="button" data-t="${esc(t)}">${esc(t)}</button>`).join("")
        + custom().map((t) => `<span class="chip mine ${on() === t ? "on" : ""}"><button type="button" data-t="${esc(t)}">${esc(t)}</button><button type="button" class="x" data-rm="${esc(t)}" aria-label="删掉「${esc(t)}」">×</button></span>`).join("")
        + (custom().length < max ? `<button class="chip add" type="button" data-add>${icon("plus")}${addLabel}</button>` : "");
      box.querySelectorAll("[data-t]").forEach((b) => b.addEventListener("click", () => { pick(b.dataset.t); draw(); }));
      box.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", async () => { await remove(b.dataset.rm); draw(); }));
      box.querySelector("[data-add]")?.addEventListener("click", () => {
        const a = box.querySelector("[data-add]");
        const inp = h("input", { class: "field chip-input", maxlength: String(maxLen), placeholder: ph });
        a.replaceWith(inp);
        inp.focus();
        let fired = false;
        const done = async () => { if (fired) return; fired = true; const v = inp.value.trim(); if (v) { await add(v); pick(v); } draw(); };
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); done(); } if (e.key === "Escape") draw(); });
        inp.addEventListener("blur", done);
      });
    };
    draw();
  };
  let promptOn = "";
  const savePrompts = async () => { try { setData(await api.wish("edit", { id: w.id, prompts: mine })); w.prompts = [...mine]; } catch (e) { toast(e.message, "err"); } };
  chipRow(body.querySelector(".j-prompts"), {
    items: () => cat.prompts, custom: () => mine, on: () => promptOn, max: 6, maxLen: 30, addLabel: "我自己的问题", ph: "写一个你常想问自己的问题",
    pick: (t) => { promptOn = promptOn === t ? "" : t; ta.placeholder = promptOn || PH; ta.focus(); },
    add: async (t) => { if (!mine.includes(t)) { mine.push(t); await savePrompts(); } },
    remove: async (t) => { mine = mine.filter((x) => x !== t); if (promptOn === t) { promptOn = ""; ta.placeholder = PH; } await savePrompts(); },
  });
  const saveMoods = async () => { try { setData(await api.profile({ custom_moods: moods })); } catch (e) { toast(e.message, "err"); } };
  chipRow(body.querySelector(".j-moods"), {
    items: () => MOODS, custom: () => moods, on: () => mood, max: 8, maxLen: 8, addLabel: "别的心情", ph: "比如：松了口气",
    pick: (t) => { mood = mood === t ? "" : t; },
    add: async (t) => { if (!moods.includes(t) && !MOODS.includes(t)) { moods.push(t); await saveMoods(); } },
    remove: async (t) => { moods = moods.filter((x) => x !== t); if (mood === t) mood = ""; await saveMoods(); },
  });
  const dateIn = body.querySelector(".field-date");
  body.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => {
    pickDay = b.dataset.day; dateIn.value = "";
    body.querySelectorAll("[data-day]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  dateIn.addEventListener("change", () => {
    if (!dateIn.value) return;
    pickDay = dateIn.value;
    body.querySelectorAll("[data-day]").forEach((x) => x.classList.remove("on"));
  });
  const save = async () => {
    if (!ta.value.trim()) { ta.focus(); return toast("写一句发生了什么就好"); }
    btn.disabled = true;
    try {
      const out = await api.moment("add", { wish_id: w.id, text: ta.value, feeling: body.querySelector("#mFeel").value, mood, day: pickDay });
      s.close();
      setData(out);
      renderPlan(root, { fresh: pickDay });
      const dot = root.querySelector(".j-node.fresh");
      if ((out.xp?.amount || out.xp?.coins > 0) && dot) setTimeout(() => flyGain(dot, out.xp), 500);
      else toast(xpNote(out.xp) ? `留下了 · ${xpNote(out.xp)}` : "留下了", "", "sparkles");
    } catch (e) { btn.disabled = false; toast(e.message, "err"); }
  };
  const btn = h("button", { class: "btn btn-main", onclick: save }, "留在轨迹上");
  const s = sheet({ title: `留下一个瞬间 · ${w.title}`, body, sticker: cat.icon,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "先不写"), btn] });
  s.panel.classList.add("j-sheet");
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); });
  setTimeout(() => ta.focus(), 60);
}

// ---------------------------------------------------------------- 添加：小步 / 习惯 / 里程碑 ----
const TYPES = {
  step: ["flag", "var(--c-orange)", "小步", "做一次就完成的事", "比如：办好健身卡"],
  habit: ["clock", "var(--c-mint)", "习惯", "重复做的事，每天或每周几次", "比如：去健身房练 40 分钟"],
  milestone: ["star", "var(--c-violet)", "里程碑", "路上看得见的一个站点", "比如：能连续跑 5 公里"],
};

function addSheet(root, w, type = "step") {
  const today = state.data.journey.today;
  let freq = "daily", per = 3, due = "";
  const body = h("div", { class: "j-add" });
  const draw = () => {
    const T = TYPES[type];
    body.innerHTML = `
      <div class="j-types">${Object.entries(TYPES).map(([k, t]) => `<button type="button" class="j-type ${k === type ? "on" : ""}" data-type="${k}">
        ${tile(t[0], t[1], 32)}<b>${t[2]}</b><small>${t[3]}</small></button>`).join("")}</div>
      <label class="lbl">${type === "habit" ? "要重复做的事" : type === "milestone" ? "这个站点是什么" : "这一步是什么"}</label>
      <input class="field" id="aTitle" maxlength="${type === "step" ? 40 : 30}" placeholder="${T[4]}">
      ${type === "habit" ? `<label class="lbl">多久一次</label>
        <div class="j-days">${[["daily", 0, "每天"], ["weekly", 1, "每周 1 次"], ["weekly", 2, "每周 2 次"], ["weekly", 3, "每周 3 次"], ["weekly", 5, "每周 5 次"]].map(([f, n, l]) =>
          `<button type="button" class="chip ${f === freq && (f === "daily" || n === per) ? "on" : ""}" data-freq="${f}" data-per="${n}">${l}</button>`).join("")}</div>` : ""}
      ${type === "milestone" ? `<label class="lbl">大概什么时候到 <span class="muted">（可选）</span></label>
        <div class="j-days">${[[7, "一周后"], [30, "一个月后"], [diffDays(w.target_day, today), "计划日"]].filter(([n]) => n > 0).map(([n, l]) =>
          `<button type="button" class="chip ${due === addDays(today, n) ? "on" : ""}" data-due="${addDays(today, n)}">${l}</button>`).join("")}
          <input class="field field-date" type="date" min="${today}" value="${due}" aria-label="选日期"></div>` : ""}
      ${type === "step" ? `<label class="lbl">为什么做它 <span class="muted">（可选）</span></label><input class="field" id="aWhy" maxlength="60" placeholder="比如：先让自己走进健身房">` : ""}`;
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
    body.querySelector("#aTitle").addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
    setTimeout(() => body.querySelector("#aTitle").focus(), 40);
  };
  const save = async () => {
    const title = body.querySelector("#aTitle").value.trim();
    if (!title) return body.querySelector("#aTitle").focus();
    try {
      if (type === "step") setData(await api.step("add", { title, why: body.querySelector("#aWhy")?.value || "", wish_id: w.id }));
      else if (type === "habit") setData(await api.habit("add", { wish_id: w.id, title, freq, per_week: per }));
      else setData(await api.milestone("add", { wish_id: w.id, title, due_day: due }));
      s.close();
      toast(`加进「${w.title}」了`, "", TYPES[type][0]);
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  };
  draw();
  const s = sheet({ title: "给这条路加点东西", body, sticker: "plus",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: save }, "加进去")] });
  s.panel.classList.add("j-sheet");
}

function habitSheet(root, hb) {
  let freq = hb.freq, per = hb.freq === "weekly" ? hb.per_week : 3;
  const body = h("div", { class: "j-add", html: `
    <label class="lbl">名字</label><input class="field" id="hTitle" maxlength="30" value="${esc(hb.title)}">
    <label class="lbl">多久一次</label>
    <div class="j-days">${[["daily", 0, "每天"], ["weekly", 1, "每周 1 次"], ["weekly", 2, "每周 2 次"], ["weekly", 3, "每周 3 次"], ["weekly", 5, "每周 5 次"]].map(([f, n, l]) =>
      `<button type="button" class="chip ${f === freq && (f === "daily" || n === per) ? "on" : ""}" data-freq="${f}" data-per="${n}">${l}</button>`).join("")}</div>
    <p class="muted j-note">一共打卡 ${hb.total} 次。</p>
    <div class="j-archive"><button class="btn btn-quiet btn-sm" id="hArchive">${icon("moon")}收起这个习惯</button><small class="muted">打卡记录会留在轨迹上。</small></div>` });
  body.querySelectorAll("[data-freq]").forEach((b) => b.addEventListener("click", () => {
    freq = b.dataset.freq; per = +b.dataset.per || 3;
    body.querySelectorAll("[data-freq]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  body.querySelector("#hArchive").addEventListener("click", async () => {
    try { setData(await api.habit("edit", { id: hb.id, archived: true })); s.close(); renderPlan(root); }
    catch (e) { toast(e.message, "err"); }
  });
  const s = sheet({ title: "编辑习惯", body, sticker: "clock",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: async () => {
      try { setData(await api.habit("edit", { id: hb.id, title: body.querySelector("#hTitle").value, freq, per_week: per })); s.close(); renderPlan(root); }
      catch (e) { toast(e.message, "err"); }
    } }, "保存")] });
  s.panel.classList.add("j-sheet");
}

// ---------------------------------------------------------------- 阶段回望 ----
function reviewSheet(w) {
  let days = 15;
  const body = h("div", { class: "j-review" });
  const s = sheet({ title: "阶段回望", body, sticker: "eye" });
  s.panel.classList.add("j-sheet");
  const draw = (r) => {
    body.innerHTML = `
      <div class="tabs j-rtabs">${[7, 15, 30, 90].map((n) => `<button class="${n === days ? "on" : ""}" data-days="${n}">${n} 天</button>`).join("")}<span class="ind"></span></div>
      <p class="j-r-line">${esc(r.line)}</p>
      ${r.count ? `<div class="j-r-stats">
          <div><span class="num">${r.count}</span><small>个瞬间</small></div>
          <div><span class="num">${r.active_days}</span><small>天有记录</small></div>
          ${r.top ? `<div><span class="num">${r.top.count}</span><small>次提到「${esc(r.top.word)}」</small></div>` : ""}
        </div>
        <div class="j-r-quotes">${r.quotes.map((q) => `<div class="j-r-q"><small>${md(q.day)}</small><p>${esc(q.text)}</p>${q.feeling ? `<p class="muted">感受：${esc(q.feeling)}</p>` : ""}</div>`).join("")}</div>
        <label class="lbl">你觉得这段时间有什么变化？</label>
        <textarea class="field" rows="3" maxlength="300" placeholder="写给自己的一两句"></textarea>
        <div class="row end"><button class="btn btn-main btn-sm" data-save>留给自己</button></div>` : ""}
      ${r.reflections.length ? `<div class="j-r-past"><div class="lbl">之前写下的回望</div>${r.reflections.map((x) =>
        `<p><small>${md(x.created_at.slice(0, 10))} · ${x.days} 天</small>${esc(x.text)}</p>`).join("")}</div>` : ""}`;
    const tabs = body.querySelector(".j-rtabs");
    requestAnimationFrame(() => {
      const on = tabs.querySelector("button.on");
      Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
    });
    tabs.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => { days = +b.dataset.days; load(); }));
    body.querySelector("[data-save]")?.addEventListener("click", async () => {
      const ta = body.querySelector("textarea");
      if (!ta.value.trim()) return ta.focus();
      try { draw(await api.wishReflect(w.id, days, ta.value)); toast("收好了", "", "heart"); }
      catch (e) { toast(e.message, "err"); }
    });
  };
  const load = async () => {
    try { draw(await api.wishReview(w.id, days)); }
    catch (e) { body.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  };
  body.innerHTML = `<p class="muted">正在翻这段时间的记录…</p>`;
  load();
}

// ---------------------------------------------------------------- 愿望：新建 / 编辑 ----
function catGrid(sel) {
  return `<div class="j-cats">${Object.entries(CATS).map(([id, c]) => `<button type="button" class="j-cat ${id === sel ? "on" : ""}" data-cat="${id}" style="--jc:${c.color}">
    <span class="j-cat-v">${visionSVG(id)}</span><b>${c.label}</b></button>`).join("")}</div>`;
}

function wishSheet(root, w, J) {
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
      setData(isNew ? await api.wish("add", payload) : await api.wish("edit", { id: w.id, ...payload }));
      s.close();
      toast(isNew ? "新的旅程开始了" : "改好了", "", catOf(cat).icon);
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  };
  body.querySelector("#wArchive")?.addEventListener("click", async () => {
    if (!(await confirmSheet("先收起这个愿望？", "它会从这里移走，记录和回望都保留在你的数据里。", "收起"))) return;
    try { setData(await api.wish("edit", { id: w.id, archived: true })); s.close(); renderPlan(root); }
    catch (e) { toast(e.message, "err"); }
  });
  const s = sheet({ title: isNew ? "开启一个新愿望" : "编辑愿望", body, sticker: "flag",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: save }, isNew ? "开始这段旅程" : "保存")] });
  s.panel.classList.add("j-sheet");
}

// 还没有任何愿望：直接在页面上选方向
function renderStart(root, J) {
  root.innerHTML = `<div class="view-inner wide plan journey">
    <div class="page-head"><div><h1>蜕变计划</h1><p>给每个愿望定一个日子，把路拆成里程碑、习惯和小步，一天一天走过去</p></div></div>
    <section class="card j-startcard">
      <div class="j-start-art">${figureSVG()}</div>
      <h2>你最想靠近哪一种自己？</h2>
      <p class="muted">选一个方向，定一个想实现的日子。之后小光会陪你把路拆开，你每做一件事，轨迹上就亮一个点。</p>
      ${catGrid("")}
    </section></div>`;
  root.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
    wishSheet(root, null, J);
    document.querySelector(`.j-wish [data-cat="${b.dataset.cat}"]`)?.click();
  }));
}
