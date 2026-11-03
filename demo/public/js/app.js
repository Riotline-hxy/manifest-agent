// 应用外壳：图标轨 / 主区 / 小光面板；主题与小光颜色；路由。
import { api } from "./api.js";
import { state, setData, go, subscribe } from "./store.js";
import { esc, icon, tile, toast, sheet, h, fmtDay } from "./ui.js";
import { countUp, burstAt, flyGain } from "./fx.js";
import { applyTheme, agentColor, lookOf, THEMES, AGENT_COLORS, themeOf } from "./theme.js";
import { mountBall, setAgentColor, setAgentLook, agentMini, MOOD_TEXT, celebrate } from "./ball.js";
import { townSVG, napSVG, townHint, affordable, COIN_SVG } from "./town.js";
import { catOf } from "./journey.js";
import { renderGate } from "./views/gate.js";
import { renderOnboarding } from "./views/onboarding.js";
import { takeCarry, dropCarry } from "./views/trial.js";
import { renderChat } from "./views/chat.js";
import { renderPlan } from "./views/plan.js";
import { renderTown } from "./views/town.js";
import { renderNews } from "./views/goodnews.js";
import { renderIdeas } from "./views/ideas.js";
import { renderAcademy, renderArticle } from "./views/academy.js";
import { renderReport } from "./views/report.js";
import { renderSpace } from "./views/space.js";
import { shouldSplash, showSplash } from "./views/splash.js";
import { isResting, openLazy } from "./rest.js";
import { routinesHTML, bindRoutines, startPulse } from "./tasks.js";
import { timelineHTML, nowIso } from "./timeline.js";
import { openRules } from "./rules.js";
import { syncPush } from "./push.js";

const NAV = [
  [["chat", "对话", "chat"], ["plan", "蜕变计划", "flag"], ["goodnews", "好消息", "star"], ["town", "我的小镇", "home"]],
  [["ideas", "点子", "bulb"], ["academy", "心灵学堂", "book"]],
];
const TITLES = { chat: "对话", plan: "蜕变计划", goodnews: "好消息", town: "我的小镇", ideas: "点子",
  academy: "心灵学堂", article: "心灵学堂", report: "蜕变报告", space: "我的空间" };
const VIEWS = { chat: renderChat, plan: renderPlan, goodnews: renderNews, town: renderTown, ideas: renderIdeas,
  academy: renderAcademy, article: renderArticle, report: renderReport, space: renderSpace };
const ALIAS = { growth: "town" };   // 旧链接：成长进化 → 我的小镇
const routeOf = (h) => ALIAS[h] || h;
// 每日任务的图标（点一下去哪儿做由后端的 go 决定）
const DAILY_TILE = { act: ["flag", "var(--c-orange)"], act3: ["flag", "var(--c-orange)"], wish2: ["compass", "var(--c-orange)"], habit2: ["clock", "var(--c-mint)"],
  good: ["star", "var(--c-lemon)"], meme: ["chat", "var(--c-pink)"], moment: ["sparkles", "var(--c-pink)"], record2: ["star", "var(--c-lemon)"],
  pick: ["wind", "var(--c-mint)"], practice: ["wind", "var(--c-mint)"], read: ["book", "var(--c-coral)"], plan: ["plus", "var(--c-sky)"], reflect: ["eye", "var(--c-violet)"] };

let root;
let drawnRoute = "";

export function mount(el) {
  root = el;
  applyTheme();
  window.addEventListener("hashchange", () => {
    const r = routeOf(location.hash.slice(1) || "chat");
    if (VIEWS[r] && r !== state.route) go(r);
  });
  window.addEventListener("xg:enter", boot);
  window.addEventListener("xg:redraw", () => drawView());
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible" || !state.ready) return;
    try {
      const before = state.data?.inbox?.length || 0;
      const data = await api.bootstrap();
      setData(data);
      if ((data.inbox?.length || 0) > before) toast("小光给你留了一句话");
    } catch {}
  });
  subscribe(() => {
    if (!state.ready || !root.querySelector(".app")) return;
    applyProfileLook();
    if (state.route !== drawnRoute) drawView();
    else { drawRail(); drawTop(); drawPanel(); }
  });
  boot();
}

function applyProfileLook() {
  const p = state.data?.profile;
  if (!p) return;
  applyTheme(p.theme);
  setAgentLook(lookOf(p));
}

async function boot() {
  state.ready = false;
  const r = routeOf(location.hash.slice(1));
  state.route = VIEWS[r] && r !== "article" ? r : "chat";
  try {
    const me = await api.me();
    if (!me.user) {
      setAgentLook(lookOf(null));
      root.innerHTML = "";
      renderGate(root);
      return;
    }
    state.user = me.user;
    const data = await api.bootstrap();
    setData(data, { silent: true });
    applyProfileLook();
    if (!data.profile?.onboarded) {
      root.innerHTML = "";
      renderOnboarding(root);
      return;
    }
    // 已有账号的人在首页体验完再登录：把那一小步和记住的话补进来
    const carry = takeCarry();
    if (carry) {
      dropCarry();
      try {
        await api.step("add", { title: carry.step, why: carry.why });
        for (const text of carry.remember || []) await api.memory("add", { text });
        setData(await api.bootstrap(), { silent: true });
        toast(`「${carry.step}」放进今天的计划了`);
      } catch {}
    }
    state.ready = true;
    const splash = shouldSplash();   // 每次打开 App 先见到小光（看的是进来时的地址，要在画外壳之前判断）
    drawShell();
    if (splash) showSplash();
    // 到点的提醒：页面开着就 30 秒问一次；在对话页时把新消息画出来
    startPulse(() => { if (state.route === "chat") drawView(); });
    syncPush();
  } catch (e) {
    root.innerHTML = `<div class="empty" style="padding-top:20vh"><div class="nap">${napSVG()}</div>
      <h3>没连上</h3><p>${esc(e?.message || "加载失败")}</p><button class="btn btn-main" onclick="location.reload()">再试一次</button></div>`;
  }
}

function panelWanted() {
  const saved = localStorage.getItem("xg-panel");
  return saved ? saved === "1" : innerWidth >= 1280;
}

function drawShell() {
  root.innerHTML = `
    <div class="app ${panelWanted() ? "panel-open" : ""}">
      <nav class="rail" aria-label="主导航"></nav>
      <main class="main"><header class="topbar"></header><div class="view"></div></main>
      <aside class="panel" aria-label="小光"></aside>
      <div class="m-scrim"></div>
      <nav class="m-drawer" aria-label="菜单"></nav>
    </div>`;
  root.querySelector(".m-scrim").addEventListener("click", () => toggleDrawer(false));
  drawView();
}

export function togglePanel(force) {
  const app = root.querySelector(".app");
  const on = force ?? !app.classList.contains("panel-open");
  app.classList.toggle("panel-open", on);
  if (on) cheerPick = null;
  localStorage.setItem("xg-panel", on ? "1" : "0");
  drawPanel(true);
  drawTop();
  window.dispatchEvent(new CustomEvent("xg:panel", { detail: on }));
}
// ---------------------------------------------------------------- 手机：抽屉菜单（参考 Muse） ----
export function toggleDrawer(on) {
  const app = root.querySelector(".app");
  if (!app) return;
  if (on) drawDrawer();
  app.classList.toggle("drawer-open", on);
}

function drawDrawer() {
  const dr = root.querySelector(".m-drawer");
  if (!dr) return;
  const d = state.data || {};
  const p = d.profile || {};
  const name = p.nickname || state.user?.username || "我";
  const item = (id, label, ic, extra = "") => `<button class="md-item ${state.route === id ? "on" : ""}" data-nav="${id}">${icon(ic)}<span>${label}</span>${extra}</button>`;
  dr.innerHTML = `
    <div class="md-head"><span class="md-logo">${agentMini()}</span><b>显伴</b><span class="sp"></span>
      <button class="icon-btn" data-md-close aria-label="关闭菜单">${icon("close")}</button></div>
    <div class="md-scroll">
      <div class="md-sec">页面</div>
      ${NAV.flat().map(([id, label, ic]) => item(id, label, ic)).join("")}
    </div>
    <div class="md-foot">
      <button class="md-me ${state.route === "space" ? "on" : ""}" data-act="account"><span class="me-av">${esc(name.slice(0, 1))}</span><span>${esc(name)}</span><small>我的空间</small>${icon("arrow")}</button>
    </div>`;
  const close = () => toggleDrawer(false);
  dr.querySelector("[data-md-close]").addEventListener("click", close);
  dr.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => { close(); go(b.dataset.nav); }));
  dr.querySelector("[data-act=account]").addEventListener("click", () => { close(); go("space"); });
}

export const panelOpen = () => !!root?.querySelector(".app.panel-open") && innerWidth > 1180;

// ---------------------------------------------------------------- 图标轨 ----
function drawRail() {
  const rail = root.querySelector(".rail");
  if (!rail) return;
  const d = state.data || {};
  // 金币够盖一种还没盖过的建筑时，小镇那一格轻轻亮一下
  const canBuild = d.town && affordable(d.town, d.growth?.coins || 0).some((c) => !d.town.items.some((i) => i.kind === c.id));
  const dot = {
    chat: (d.inbox || []).length,
    plan: (d.steps || []).filter((s) => s.status === "todo").length,
    space: (d.memories || []).filter((m) => m.status === "guess").length,
  };
  rail.innerHTML = `
    <div class="logo" title="显伴">${agentMini()}</div>
    ${NAV.map((grp, i) => `${i ? '<div class="nav-sep"></div>' : ""}${grp.map(([id, label, ic], j) => {
      const on = state.route === id || (id === "academy" && state.route === "article");
      const badge = dot[id] ? `<span class="dot">${dot[id]}</span>` : id === "town" && canBuild ? '<span class="dot soft"></span>' : "";
      // 手机底栏只放五个：对话、计划、好消息、点子、我的空间（小镇从顶栏的金币和菜单进）
      const mHide = (i && j) || id === "town" ? "m-more" : "";
      return `<button class="nav-item ${on ? "active" : ""} ${mHide}" data-nav="${id}" aria-label="${label}">${icon(ic)}${badge}<span class="lbl">${label}</span></button>`;
    }).join("")}`).join("")}
    <button class="nav-item m-only ${state.route === "space" ? "active" : ""}" data-nav="space" aria-label="我的空间">${icon("user")}${dot.space ? `<span class="dot">${dot.space}</span>` : ""}<span class="lbl">我的空间</span></button>
    <div class="spacer"></div>
    <button class="me-av ${state.route === "space" ? "active" : ""}" data-act="account" title="我的空间" aria-label="我的空间">${esc((d.profile?.nickname || state.user?.username || "我").slice(0, 1))}</button>`;
  rail.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => go(b.dataset.nav)));
  rail.querySelector("[data-act=account]").addEventListener("click", () => go("space"));
}

// ---------------------------------------------------------------- 顶栏 ----
function drawTop() {
  const top = root.querySelector(".topbar");
  if (!top) return;
  const g = state.data?.growth || {};
  const lv = g.level || { lv: 1, pct: 0, into: 0, need: 40 };
  const prev = top.querySelector("[data-coin-num]")?.dataset.v;
  const shown = prev ?? g.coins ?? 0;
  const open = !!root.querySelector(".app.panel-open");
  top.innerHTML = `
    <button class="icon-btn m-menu" data-act="menu" aria-label="打开菜单">${icon("menu")}</button>
    ${state.route === "report" ? `<button class="icon-btn" data-back="plan" aria-label="回到蜕变计划" title="回到蜕变计划">${icon("back")}</button>` : ""}
    <span class="title">${esc(TITLES[state.route] || "显伴")}</span>
    <span class="spacer"></span>
    <button class="stat coin" data-coin-target data-nav="town" aria-label="金币 ${g.coins ?? 0}，去我的小镇">${COIN_SVG}<span class="num" data-coin-num data-v="${shown}">${shown}</span>
      <span class="tip"><b>金币 ${g.coins ?? 0}</b>用来在小镇里盖房子、种树、铺路。完成小步、习惯打卡、练习、记好消息和每日任务都会给；和小光聊天只给经验。</span></button>
    <button class="stat lvst" data-xp-target data-nav="town" aria-label="等级 ${lv.lv}"><span class="lvl" style="--p:${Math.round(lv.pct * 100)}"><b>${lv.lv}</b></span><span class="sub">Lv</span>
      <span class="tip"><b>等级 ${lv.lv}</b>再 ${lv.to_next ?? 0} 经验升到 Lv ${lv.lv + 1}。今天 +${g.today?.total ?? 0} 经验。前几级很快，往后每级多一点；升级会解锁新建筑和更大的地。</span></button>
    <button class="icon-btn ${open ? "on" : ""}" data-act="panel" title="${open ? "收起小光" : "打开小光"}">${icon("panel")}</button>`;
  setTimeout(() => countUp(top.querySelector("[data-coin-num]"), g.coins ?? 0), prev != null && Number(prev) !== g.coins ? 950 : 0);
  top.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => go("town")));
  top.querySelector("[data-act=panel]").addEventListener("click", () => togglePanel());
  top.querySelector("[data-act=menu]").addEventListener("click", () => toggleDrawer(true));
  top.querySelector("[data-back]")?.addEventListener("click", (e) => go(e.currentTarget.dataset.back));
}

// ---------------------------------------------------------------- 小光面板 ----
let panelTab = "today";
let panelBall = null;

function drawPanel(rebuild = false) {
  const panel = root.querySelector(".panel");
  if (!panel) return;
  const d = state.data || {};
  const p = d.profile || {};
  if (rebuild || !panel.querySelector(".panel-head")) {
    panel.innerHTML = `
      <div class="panel-head">
        <button class="icon-btn close" data-act="close" title="收起">${icon("close")}</button>
        <div class="p-ball"></div>
        <div class="nm">${esc(p.agent_name || "小光")}</div>
        <div class="st"><i></i><span data-agent-status>${MOOD_TEXT["02"]}</span></div>
      </div>
      <div class="panel-tabs"><div class="tabs">${[["today", "今天"], ["daily", "每日任务"], ["log", "动态"]].map(([k, l]) =>
        `<button data-tab="${k}" class="${panelTab === k ? "on" : ""}">${l}</button>`).join("")}<span class="ind"></span></div></div>
      <div class="panel-body"></div>`;
    panelBall = mountBall(panel.querySelector(".p-ball"), { size: 104 });
    panel.querySelector("[data-act=close]").addEventListener("click", () => togglePanel(false));
    panel.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
      panelTab = b.dataset.tab;
      panel.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
      placeInd(panel.querySelector(".tabs"));
      drawPanelBody(panel);
    }));
    requestAnimationFrame(() => placeInd(panel.querySelector(".tabs")));
  }
  drawPanelBody(panel);
}

export function placeInd(tabs) {
  const on = tabs?.querySelector("button.on");
  if (!on) return;
  Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
}

// 面板顶部的一句话：「最近的你」或「对自己说」的肯定语。每次打开面板随机一句，点一下换一句。
let cheerPick = null;
function pickCheer(d, prev = null) {
  const ch = d.cheer || {};
  const aff = (ch.affirm || []).filter((t) => t !== prev?.text);
  const you = ch.you?.text && prev?.kind !== "you" ? { kind: "you", text: ch.you.text } : null;
  if (you && (!aff.length || Math.random() < 0.4)) return you;
  return aff.length ? { kind: "affirm", text: aff[Math.floor(Math.random() * aff.length)] } : you;
}

// 「今天」：每个愿望一栏。收起时只露出下一个还没做的小步，点栏目展开看全部；小步没有期限，不按日期筛
const openWish = new Set();
let advanced = "";   // 刚勾掉一步的那个愿望：下一步滑进来

function wishStepsHTML(d) {
  const ws = d.journey?.wishes || [];
  if (!ws.length) return `<div class="wg-empty">还没有愿望。<button class="btn btn-sm btn-ghost" data-go="plan">去定一个</button></div>`;
  const all = [...(d.steps || [])].reverse();   // 服务端是新的在前；这里按加进来的先后，最早的那步排第一
  const html = ws.map((w) => {
    const mine = all.filter((s) => s.wish_id === w.id || (!s.wish_id && w.id === ws[0].id));
    const todo = mine.filter((s) => s.status === "todo");
    const done = mine.filter((s) => s.status === "done").sort((a, b) => (b.done_at || "").localeCompare(a.done_at || ""));
    const open = openWish.has(w.id), total = todo.length + done.length, cat = catOf(w.category);
    const rows = (open ? todo : todo.slice(0, 1)).map((s, i) => `<div class="ws" style="--i:${i}">
      <button class="ck" data-step-done="${esc(s.id)}" aria-label="完成「${esc(s.title)}」">${icon("check")}</button><span class="t">${esc(s.title)}</span></div>`).join("");
    const more = open
      ? `${done.slice(0, 6).map((s) => `<div class="ws done">${icon("check")}<span class="t">${esc(s.title)}</span></div>`).join("")}
         ${done.length > 6 ? `<div class="ws-note">还有 ${done.length - 6} 个完成的，在蜕变计划里</div>` : ""}
         <form class="ws-add" data-wg-add="${esc(w.id)}"><input class="field" maxlength="40" placeholder="加一个小步" aria-label="给「${esc(w.title)}」加一个小步"><button class="icon-btn sm" aria-label="加进去">${icon("plus")}</button></form>`
      : todo.length > 1 ? `<button class="ws-more" data-wg-toggle="${esc(w.id)}">还有 ${todo.length - 1} 个小步</button>` : "";
    return `<section class="wg ${open ? "open" : ""} ${advanced === w.id ? "advanced" : ""}" data-wg="${esc(w.id)}">
      <button class="wg-h" data-wg-toggle="${esc(w.id)}" aria-expanded="${open}">${tile(cat.icon, cat.color, 28)}<span class="wg-t">${esc(w.title)}</span>
        ${total ? `<span class="wg-n">${done.length}/${total}</span>` : ""}<span class="wg-chev">${icon("chevron")}</span></button>
      ${total ? `<span class="wg-bar" aria-hidden="true"><i style="width:${Math.round((done.length / total) * 100)}%;background:${cat.color}"></i></span>` : ""}
      <div class="wg-list">${rows}${!todo.length ? `<div class="ws-all">${total ? `${icon("checkc")}这个愿望的小步都做完了` : "还没有小步"}</div>
` : ""}${more}</div>
    </section>`;
  }).join("");
  advanced = "";
  return html;
}

function dailyHTML(d) {
  const g = d.growth, t = d.town, dl = g.daily;
  return `
    <button class="town-entry" data-go="town">
      <span class="te-thumb">${townSVG(t, { still: true })}</span>
      <span class="te-main"><b>${esc(t.name)}</b><span class="te-meta"><span class="te-lv">Lv ${g.level.lv}</span>${COIN_SVG}<b class="num">${g.coins}</b></span>
        <small>${esc(townHint(t, g))}</small></span>${icon("arrow")}</button>
    <div class="dq-head"><div><b>今天的每日任务</b><small>${dl.done}/${dl.of} 件 · 0 点换新</small></div>
      <button class="dq-rules" data-rules>怎么算的</button></div>
    <div class="dq-total"><span>已拿到</span><b>${dl.got.xp}/${dl.max.xp}</b><small>经验</small><b>${dl.got.coins}/${dl.max.coins}</b>${COIN_SVG}<i style="width:${Math.round((dl.got.coins / (dl.max.coins || 1)) * 100)}%"></i></div>
    <div class="dq-list">${dl.tasks.map((q) => { const [ic, col] = DAILY_TILE[q.id] || ["sparkles", "var(--accent)"]; return `<button class="dq ${q.done ? "done" : ""} ${q.rest ? "rest" : ""}" data-go="${q.go}">
      ${q.rest ? tile("moon", "var(--c-violet)", 34) : tile(ic, col, 34)}
      <span class="dq-main"><b>${esc(q.label)}</b>${q.rest ? "<small>今天休息，先放着</small>" : ""}</span>
      <span class="dq-r">${q.done ? icon("check") : q.rest ? "休息中" : `<span>+${q.xp} 经验</span><span>+${q.coins}${COIN_SVG}</span>`}</span></button>`; }).join("")}</div>
    <div class="dq-bonus ${dl.bonus.done ? "done" : ""}"><span class="dq-dots">${dl.tasks.map((q) => `<i class="${q.done || q.rest ? "on" : ""}"></i>`).join("")}</span>
      <span>${dl.bonus.done ? "四件都做到了" : "四件都做到"}</span><b>+${dl.bonus.xp} 经验 · +${dl.bonus.coins}${COIN_SVG}</b></div>`;
}

function drawPanelBody(panel) {
  const body = panel.querySelector(".panel-body");
  const d = state.data || {};
  const g = d.growth || {};
  if (!g.level || !d.town) return;
  if (panelTab === "today") {
    const guesses = (d.memories || []).filter((m) => m.status === "guess").slice(0, 2);
    cheerPick = cheerPick || pickCheer(d);
    const L = cheerPick;
    body.innerHTML = `
      ${L ? `<div class="cheer say-${L.kind} flip" data-say-next role="button" tabindex="0" aria-label="换一句">
        <div class="k">${icon(L.kind === "you" ? "leaf" : "heart")}${L.kind === "you" ? "最近的你" : "对自己说"}</div>
        <div class="t">${esc(L.text)}</div></div>` : ""}
      ${isResting() ? `<button class="p-rest" data-rest-panel>${napSVG()}<span><b>今天是偷懒日</b>小步都先放着，不着急</span></button>` : ""}
      <div class="sec-title p-sec">愿望的小步</div>
      <div class="wg-wrap">${wishStepsHTML(d)}</div>
      ${routinesHTML(d)}
      ${guesses.map((m) => `<div class="p-card"><div class="k">小光猜的，对吗？</div><div class="t">${esc(m.text)}</div>
        <div class="guess-acts"><button class="btn btn-sm btn-good" data-confirm="${esc(m.id)}">对</button>
        <button class="btn btn-sm btn-ghost" data-reject="${esc(m.id)}">不太对</button></div></div>`).join("")}`;
  } else if (panelTab === "daily") {
    body.innerHTML = dailyHTML(d);
  } else {
    body.innerHTML = `<div class="tl panel-tl">${timelineHTML(d.activity, { sums: g.day_totals, tasks: d.tasks, today: d.journey?.today, now: nowIso() })}</div>`;
  }
  body.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  body.querySelector("[data-rules]")?.addEventListener("click", () => openRules());
  body.querySelector("[data-rest-panel]")?.addEventListener("click", () => openLazy({ onDone: drawView }));
  bindRoutines(body);
  bindWishSteps(panel, body);
  // 点一下换一句
  const card = body.querySelector("[data-say-next]");
  const next = () => { cheerPick = pickCheer(d, cheerPick); drawPanelBody(panel); body.querySelector(".cheer")?.classList.add("swap"); };
  card?.addEventListener("click", next);
  card?.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); next(); } });
  body.querySelector("[data-go-digest]")?.addEventListener("click", () => { state.spaceTab = "digest"; state.route === "space" ? drawView() : go("space"); });
  body.querySelectorAll("[data-confirm],[data-reject]").forEach((b) => b.addEventListener("click", async () => {
    const action = b.dataset.confirm ? "confirm" : "reject";
    try {
      setData(await api.memory(action, { id: b.dataset.confirm || b.dataset.reject }));
      toast(action === "confirm" ? "记下了，以后会用它理解你" : "删掉了，谢谢你纠正我");
    } catch (e) { toast(e.message, "err"); }
  }));
}

// 面板里勾小步、加小步：和蜕变计划是同一份数据，计划页开着就一起重画
function bindWishSteps(panel, body) {
  const synced = (out) => { setData(out); if (state.route === "plan") drawView(); };
  body.querySelectorAll("[data-wg-toggle]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.wgToggle;
    openWish.has(id) ? openWish.delete(id) : openWish.add(id);
    drawPanelBody(panel);
    if (openWish.has(id)) body.querySelector(`[data-wg="${CSS.escape(id)}"] .ws-add input`)?.focus({ preventScroll: true });
  }));
  body.querySelectorAll("[data-step-done]").forEach((b) => b.addEventListener("click", async () => {
    const row = b.closest(".ws");
    if (row.classList.contains("checking")) return;
    row.classList.add("checking");
    const wid = b.closest("[data-wg]").dataset.wg;
    try {
      const out = await api.step("done", { id: b.dataset.stepDone });
      burstAt(b, 18);
      flyGain(b, out.xp);
      celebrate();
      setTimeout(() => { advanced = wid; synced(out); }, 420);
    } catch (e) { row.classList.remove("checking"); toast(e.message, "err"); }
  }));
  body.querySelectorAll("[data-wg-add]").forEach((f) => f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = f.querySelector("input");
    const title = input.value.trim();
    if (!title) return input.focus();
    try {
      synced(await api.step("add", { title, wish_id: f.dataset.wgAdd }));
      panel.querySelector(`[data-wg="${CSS.escape(f.dataset.wgAdd)}"] .ws-add input`)?.focus({ preventScroll: true });
    } catch (err) { toast(err.message, "err"); }
  }));
}

// ---------------------------------------------------------------- 主题 ----
export function themeCard(t, on) {
  return `<button class="theme-card ${on ? "on" : ""}" data-theme-id="${t.id}">
    <div class="prev" style="background:linear-gradient(160deg, ${t.swatch[0]}, ${t.swatch[1]})">
      <span class="b" style="background:${t.agent}"></span>
      <span class="l1" style="background:${t.dark ? "rgba(255,255,255,.22)" : "rgba(0,0,0,.12)"}"></span>
      <span class="l2" style="background:${t.dark ? "rgba(255,255,255,.14)" : "rgba(0,0,0,.08)"}"></span></div>
    <div class="cap"><b>${esc(t.name)}</b><small>${esc(t.for)}</small></div></button>`;
}

function openThemeSheet() {
  const p = state.data?.profile || {};
  const body = h("div", {});
  const draw = () => {
    const cur = themeOf(p.theme).id;
    const col = agentColor(p);
    body.innerHTML = `
      <div class="sec-title">氛围</div>
      <div class="theme-grid">${THEMES.map((t) => themeCard(t, t.id === cur)).join("")}</div>
      <div class="sec-title" style="margin-top:22px">小光的颜色</div>
      <div class="swatches">${AGENT_COLORS.map((c) => `<button class="swatch ${c === col ? "on" : ""}" data-color="${c}" style="background:${c}" aria-label="${c}"></button>`).join("")}</div>`;
    body.querySelectorAll("[data-theme-id]").forEach((b) => b.addEventListener("click", () => save({ theme: b.dataset.themeId, agent_hue: "" })));
    body.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => save({ agent_hue: b.dataset.color })));
  };
  const save = async (patch) => {
    Object.assign(p, patch);
    applyTheme(p.theme);
    setAgentColor(agentColor(p));
    draw();
    try { setData(await api.profile(patch)); } catch (e) { toast(e.message, "err"); }
  };
  draw();
  sheet({ title: "氛围与小光的颜色", sticker: "palette", body, footer: [] });
}

// ---------------------------------------------------------------- 视图 ----
function drawView() {
  const view = root.querySelector(".view");
  if (!view) return;
  drawnRoute = state.route;
  view.scrollTop = 0;
  view.innerHTML = "";
  (VIEWS[state.route] || renderChat)(view);
  drawRail();
  drawTop();
  drawPanel(!root.querySelector(".panel-head"));
}

export function redrawView() { drawView(); }
