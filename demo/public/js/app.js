// 应用外壳：图标轨 / 主区 / 小光面板；主题与小光颜色；路由。
import { api } from "./api.js";
import { state, setData, go, subscribe } from "./store.js";
import { esc, icon, tile, toast, sheet, h, fmtDay } from "./ui.js";
import { countUp } from "./fx.js";
import { applyTheme, agentColor, THEMES, AGENT_COLORS, themeOf } from "./theme.js";
import { mountBall, setAgentColor, agentMini, MOOD_TEXT } from "./ball.js";
import { petSVG, chestSVG } from "./pet.js";
import { renderGate } from "./views/gate.js";
import { renderOnboarding } from "./views/onboarding.js";
import { renderChat } from "./views/chat.js";
import { renderPlan } from "./views/plan.js";
import { renderGrowth } from "./views/growth.js";
import { renderNews } from "./views/goodnews.js";
import { renderIdeas } from "./views/ideas.js";
import { renderAcademy, renderArticle } from "./views/academy.js";
import { renderReport } from "./views/report.js";
import { renderSpace } from "./views/space.js";

const NAV = [
  [["chat", "对话", "chat"], ["plan", "蜕变计划", "flag"], ["goodnews", "好消息", "star"], ["growth", "成长进化", "sprout"]],
  [["ideas", "点子", "bulb"], ["academy", "心灵学堂", "book"], ["report", "蜕变报告", "report"], ["space", "我的空间", "user"]],
];
const TITLES = { chat: "对话", plan: "蜕变计划", goodnews: "好消息", growth: "成长进化", ideas: "点子",
  academy: "心灵学堂", article: "心灵学堂", report: "蜕变报告", space: "我的空间" };
const VIEWS = { chat: renderChat, plan: renderPlan, goodnews: renderNews, growth: renderGrowth, ideas: renderIdeas,
  academy: renderAcademy, article: renderArticle, report: renderReport, space: renderSpace };
export const QUEST_TILE = { action: ["flag", "var(--c-orange)"], good: ["star", "var(--c-lemon)"], practice: ["wind", "var(--c-mint)"], checkin: ["chat", "var(--c-sky)"] };

let root;
let drawnRoute = "";

export function mount(el) {
  root = el;
  applyTheme();
  window.addEventListener("hashchange", () => {
    const r = location.hash.slice(1) || "chat";
    if (VIEWS[r] && r !== state.route) go(r);
  });
  window.addEventListener("xg:enter", boot);
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
  setAgentColor(agentColor(p));
}

async function boot() {
  state.ready = false;
  const r = location.hash.slice(1);
  state.route = VIEWS[r] && r !== "article" ? r : "chat";
  try {
    const me = await api.me();
    if (!me.user) {
      setAgentColor(agentColor(null));
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
    state.ready = true;
    drawShell();
  } catch (e) {
    root.innerHTML = `<div class="empty" style="padding-top:20vh">${petSVG("egg", { cls: "alive" })}
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
    </div>`;
  drawView();
}

export function togglePanel(force) {
  const app = root.querySelector(".app");
  const on = force ?? !app.classList.contains("panel-open");
  app.classList.toggle("panel-open", on);
  localStorage.setItem("xg-panel", on ? "1" : "0");
  drawPanel(true);
  drawTop();
  window.dispatchEvent(new CustomEvent("xg:panel", { detail: on }));
}
export const panelOpen = () => !!root?.querySelector(".app.panel-open") && innerWidth > 1180;

// ---------------------------------------------------------------- 图标轨 ----
function drawRail() {
  const rail = root.querySelector(".rail");
  if (!rail) return;
  const d = state.data || {};
  const g = d.growth || {};
  const dot = {
    chat: (d.inbox || []).length,
    plan: (d.steps || []).filter((s) => s.status === "todo").length,
    space: (d.memories || []).filter((m) => m.status === "guess").length,
  };
  rail.innerHTML = `
    <div class="logo" title="显伴">${agentMini()}</div>
    ${NAV.map((grp, i) => `${i ? '<div class="nav-sep"></div>' : ""}${grp.map(([id, label, ic]) => {
      const on = state.route === id || (id === "academy" && state.route === "article");
      const badge = dot[id] ? `<span class="dot">${dot[id]}</span>` : id === "growth" && g.to_next && g.to_next <= 20 ? '<span class="dot soft"></span>' : "";
      return `<button class="nav-item ${on ? "active" : ""}" data-nav="${id}" aria-label="${label}">${icon(ic)}${badge}<span class="lbl">${label}</span></button>`;
    }).join("")}`).join("")}
    <div class="spacer"></div>
    <button class="nav-item theme-btn" data-act="theme" aria-label="氛围">${icon("palette")}<span class="lbl">氛围与小光的颜色</span></button>
    <button class="me-av" data-nav="space" title="${esc(d.profile?.nickname || "我")}">${esc((d.profile?.nickname || state.user?.username || "我").slice(0, 1))}</button>`;
  rail.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => go(b.dataset.nav)));
  rail.querySelector("[data-act=theme]").addEventListener("click", openThemeSheet);
}

// ---------------------------------------------------------------- 顶栏 ----
function drawTop() {
  const top = root.querySelector(".topbar");
  if (!top) return;
  const g = state.data?.growth || {};
  const lv = g.level || { lv: 1, pct: 0, into: 0, need: 40 };
  const prev = top.querySelector("[data-xp-num]")?.dataset.v;
  const shown = prev ?? g.today?.total ?? 0;
  const open = !!root.querySelector(".app.panel-open");
  top.innerHTML = `
    <span class="title">${esc(TITLES[state.route] || "显伴")}</span>
    <span class="spacer"></span>
    <button class="stat" data-xp-target>${icon("bolt")}<span class="num" data-xp-num data-v="${shown}">${shown}</span><span class="sub">/120</span>
      <span class="tip"><b>今天的经验</b>行动、好消息、练习、陪伴四类各 30，一天最多 120。同一件事不会重复计分。</span></button>
    <button class="stat" data-nav="growth"><span class="lvl" style="--p:${Math.round(lv.pct * 100)}"><b>${lv.lv}</b></span><span class="sub">Lv</span>
      <span class="tip"><b>等级 ${lv.lv}</b>每 40 经验升一级，这一级还差 ${lv.need - lv.into}。</span></button>
    <button class="icon-btn ${open ? "on" : ""}" data-act="panel" title="${open ? "收起小光" : "打开小光"}">${icon("panel")}</button>`;
  setTimeout(() => countUp(top.querySelector("[data-xp-num]"), g.today?.total ?? 0), prev != null && Number(prev) !== g.today?.total ? 950 : 0);
  top.querySelector("[data-nav]").addEventListener("click", () => go("growth"));
  top.querySelector("[data-act=panel]").addEventListener("click", () => togglePanel());
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
      <div class="panel-tabs"><div class="tabs">${[["today", "今天"], ["pet", "小芽"], ["log", "动态"]].map(([k, l]) =>
        `<button data-tab="${k}" class="${panelTab === k ? "on" : ""}">${l}</button>`).join("")}<span class="ind"></span></div></div>
      <div class="panel-body"></div>`;
    panelBall = mountBall(panel.querySelector(".p-ball"), { size: 104, idle: true });
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

function drawPanelBody(panel) {
  const body = panel.querySelector(".panel-body");
  const d = state.data || {};
  const g = d.growth || {};
  if (!g.stage) return;
  if (panelTab === "today") {
    const inbox = (d.inbox || [])[0];
    const guesses = (d.memories || []).filter((m) => m.status === "guess").slice(0, 2);
    const digest = (d.digests || [])[0];
    body.innerHTML = `
      <div class="sec-title" style="margin-bottom:2px">今日任务 <span class="more">${g.quests_done}/4</span></div>
      ${g.quests.map((q) => `<div class="quest ${q.done ? "done" : ""}">${tile(QUEST_TILE[q.id][0], QUEST_TILE[q.id][1], 34)}
        <div class="q-main"><div class="q-t">${q.done ? "✓ " : ""}${esc(q.label)}<span>${Math.min(q.got, q.need)}/${q.need}</span></div>
        <div class="bar sm ${q.done ? "good" : ""}"><i style="width:${Math.min(100, (q.got / q.need) * 100)}%"></i></div></div></div>`).join("")}
      <div class="chest-row">${chestSVG(g.quests_done === 4)}<span>${g.quests_done === 4 ? "今天四件小事都做到了。" : `再完成 ${4 - g.quests_done} 件，宝箱就开了。`}</span></div>
      ${inbox ? `<div class="p-card"><div class="k">小光留了话</div><div class="t">${esc(inbox.text)}</div></div>` : ""}
      ${guesses.map((m) => `<div class="p-card"><div class="k">小光猜的，对吗？</div><div class="t">${esc(m.text)}</div>
        <div class="guess-acts"><button class="btn btn-sm btn-good" data-confirm="${esc(m.id)}">对</button>
        <button class="btn btn-sm btn-ghost" data-reject="${esc(m.id)}">不太对</button></div></div>`).join("")}
      ${digest ? `<div class="p-card" data-go-digest style="cursor:pointer"><div class="k">夜里整理了 · ${esc(digest.day.slice(5))}</div><div class="t">${esc(digest.summary)}</div></div>` : ""}`;
  } else if (panelTab === "pet") {
    const span = g.next ? g.next.at - g.prev_at : 1;
    const pct = g.next ? Math.round(((g.total - g.prev_at) / span) * 100) : 100;
    body.innerHTML = `<div class="pet-mini">
      <div data-go="growth">${petSVG(g.stage.art, { cls: "alive" })}</div>
      <div class="nm">${esc(g.pet_name)} · ${esc(g.stage.name)}</div>
      <div class="ln">${esc(g.stage.line)}</div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="to">${g.next ? `再 <b>${g.to_next}</b> 经验到「${esc(g.next.name)}」` : "已经是成年形态了"}</div>
      <button class="btn btn-sm btn-ghost" data-go="growth" style="margin-top:14px">看进化图</button></div>`;
  } else {
    const ICON = { plan: "flag", record: "star", memory: "memory", scene: "wind", growth: "sprout", onboarding: "compass", profile: "settings", proactive: "letter", step: "flag" };
    body.innerHTML = (d.activity || []).slice(0, 30).map((a, i) => `<div class="act" style="--i:${i}">${icon(ICON[a.kind] || "checkc")}
      <div><div class="t">${esc(a.text)}</div><div class="w">${esc(fmtDay(a.at))} ${esc((a.at || "").slice(11, 16))}</div></div></div>`).join("")
      || `<div class="empty"><p>还没有动静。</p></div>`;
  }
  body.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  body.querySelector("[data-go-digest]")?.addEventListener("click", () => { state.spaceTab = "digest"; state.route === "space" ? drawView() : go("space"); });
  body.querySelectorAll("[data-confirm],[data-reject]").forEach((b) => b.addEventListener("click", async () => {
    const action = b.dataset.confirm ? "confirm" : "reject";
    try {
      setData(await api.memory(action, { id: b.dataset.confirm || b.dataset.reject }));
      toast(action === "confirm" ? "记下了，以后会用它理解你" : "删掉了，谢谢你纠正我");
    } catch (e) { toast(e.message, "err"); }
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
