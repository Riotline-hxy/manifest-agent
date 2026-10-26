// 应用外壳：路由、左轨、右栏「此刻」、主题与可见性同步。
import { api } from "./api.js";
import { state, setData, setTheme, go, emit, subscribe } from "./store.js";
import { esc, icon, toast, h, fmtDay, fmtTime } from "./ui.js";
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
  { group: "陪你", items: [
    { id: "chat", label: "对话", icon: "chat" },
    { id: "plan", label: "蜕变计划", icon: "plan" },
    { id: "goodnews", label: "好消息", icon: "good" },
  ]},
  { group: "养成的", items: [
    { id: "growth", label: "成长进化", icon: "pet" },
  ]},
  { group: "探索", items: [
    { id: "ideas", label: "点子", icon: "spark" },
    { id: "academy", label: "心灵学堂", icon: "book" },
    { id: "report", label: "蜕变报告", icon: "report" },
    { id: "space", label: "我的空间", icon: "space" },
  ]},
];

const TITLES = {
  chat: "小光", plan: "蜕变计划", goodnews: "好消息", growth: "成长进化",
  ideas: "点子", academy: "心灵学堂", article: "心灵学堂", report: "蜕变报告", space: "我的空间",
};

let appEl;
let viewRoot;
let lastRendered = {};

export function mount(el) {
  appEl = el;
  document.documentElement.dataset.theme = state.theme === "dusk" ? "dusk" : "paper";
  window.addEventListener("hashchange", onRoute);
  // 任何视图只要改了 state.route / state.data，外壳都跟着重绘
  let pending = false;
  subscribe(() => {
    if (pending || !state.ready) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      if (!state.ready) return;
      const routeNow = state.route;
      const titleEl = appEl.querySelector(".topbar h1");
      if (!titleEl) { rerender(); return; }
      const want = TITLES[routeNow] || "显伴";
      if (titleEl.textContent !== want) { rerender(); return; }
      drawRail();
      drawCtx();
    });
  });
  window.addEventListener("xg:enter", boot);
  window.addEventListener("resize", scheduleCtx);
  // 回到标签页时同步一次，主动消息可能在这期间到达
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && state.user && state.data) {
      try {
        const data = await api.bootstrap();
        const unseen = data.inbox?.length || 0;
        setData(data);
        if (unseen) toast(`小光给你留了 ${unseen} 条消息`);
      } catch {}
    }
  });
  boot();
}

async function boot() {
  state.ready = false;
  const route = location.hash.slice(1) || "chat";
  state.route = route === "article" ? "academy" : route;
  try {
    const me = await api.me();
    if (!me.user) {
      state.user = null;
      drawGate();
      return;
    }
    state.user = me.user;
    const data = await api.bootstrap();
    setData(data);
    state.onboarding = data.onboarding;
    state.ready = true;
    if (!data.profile?.onboarded) {
      drawOnboarding();
      return;
    }
    drawApp();
    onRoute();
  } catch (e) {
    drawFatal(e);
  }
}

function drawFatal(e) {
  appEl.innerHTML = `<div class="page-inner"><div class="empty"><div class="glyph">…</div>
    <p>${esc(e?.message || "加载失败")}</p><button class="btn btn-ghost" onclick="location.reload()">重试</button></div></div>`;
}

function drawGate() {
  appEl.className = "";
  appEl.innerHTML = "";
  renderGate(appEl);
}

function drawOnboarding() {
  appEl.className = "";
  appEl.innerHTML = "";
  renderOnboarding(appEl);
}

function drawApp() {
  appEl.className = "app";
  appEl.innerHTML = `
    <nav class="rail" id="rail" aria-label="主导航"></nav>
    <main class="canvas" id="canvas"></main>
    <aside class="context" id="context" aria-label="此刻"></aside>`;
  viewRoot = appEl.querySelector("#canvas");
  drawRail();
  drawCtx();
}

function drawRail() {
  const rail = appEl.querySelector("#rail");
  if (!rail) return;
  const d = state.data || {};
  const g = d.growth || {};
  const guesses = (d.memories || []).filter((m) => m.status === "guess").length;
  const todo = (d.steps || []).filter((s) => s.status === "todo").length;
  const unseen = (d.inbox || []).length;

  rail.innerHTML = `
    <div class="brand">
      <svg class="brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <circle cx="16" cy="16" r="9" fill="var(--jade)"/>
        <circle cx="13" cy="14" r="3" fill="#fff" opacity=".38"/>
        <circle cx="16" cy="16" r="14" stroke="var(--jade)" stroke-opacity=".28"/>
      </svg>
      <div>
        <div class="brand-name">显伴</div>
        <div class="brand-sub">MANIFEST</div>
      </div>
    </div>
    ${NAV.map((sec) => `
      <div class="nav-group">
        <div class="nav-label">${sec.group}</div>
        ${sec.items.map((it) => {
          const active = state.route === it.id || (it.id === "academy" && state.route === "article");
          let badge = "";
          if (it.id === "growth" && g.needs_branch) badge = `<span class="dot gold">!</span>`;
          if (it.id === "plan" && todo) badge = `<span class="dot">${todo}</span>`;
          if (it.id === "space" && guesses) badge = `<span class="dot gold">${guesses}</span>`;
          if (it.id === "chat" && unseen) badge = `<span class="dot">${unseen}</span>`;
          return `<button class="nav-item ${active ? "active" : ""}" data-nav="${it.id}">${icon(it.icon)}<span>${it.label}</span>${badge}</button>`;
        }).join("")}
      </div>`).join("")}
    <div class="rail-spacer"></div>
    <button class="rail-pet" data-nav="growth">
      <img src="assets/pets/${esc(g.stage?.art || "stage0")}.webp" alt="">
      <span>
        <span class="name">${esc(g.pet_name || "小芽")}</span><br>
        <span class="stage">${esc(g.stage?.name || "")} · ${g.total ?? 0} 经验</span>
      </span>
    </button>
    <div class="rail-user">
      <span class="avatar">${esc((d.profile?.nickname || state.user?.username || "我").slice(0, 1))}</span>
      <span class="grow">${esc(d.profile?.nickname || state.user?.username || "体验账号")}</span>
      ${state.user?.kind === "guest"
        ? `<button data-act="claim">保存账号</button>`
        : `<button data-act="logout">退出</button>`}
    </div>`;

  rail.querySelectorAll("[data-nav]").forEach((b) =>
    b.addEventListener("click", () => {
      state.sceneStep = state.route === "chat" ? state.sceneStep : state.sceneStep;
      go(b.dataset.nav);
    }));
  rail.querySelector("[data-act=logout]")?.addEventListener("click", async () => {
    await api.logout();
    location.reload();
  });
  rail.querySelector("[data-act=claim]")?.addEventListener("click", async () => {
    const u = prompt("起一个用户名（2–20 位）")?.trim();
    if (!u) return;
    const p = prompt("设一个密码（至少 6 位）");
    if (!p) return;
    try {
      const out = await api.register(u, p);
      state.user = out.user;
      toast("账号已保存，之前的记录都在");
      drawRail();
    } catch (e) {
      toast(e.message, "err");
    }
  });
}

function drawCtx() {
  const ctx = appEl.querySelector("#context");
  if (!ctx) return;
  const d = state.data || {};
  const g = d.growth || {};
  const steps = (d.steps || []).filter((s) => s.status === "todo").slice(0, 4);
  const guesses = (d.memories || []).filter((m) => m.status === "guess").slice(0, 2);
  const inbox = (d.inbox || [])[0];

  ctx.innerHTML = `
    <div class="c-card pet-card">
      <div class="c-head">此刻 <span class="more" data-nav="growth">成长 →</span></div>
      <div class="pet-frame">
        <img src="assets/pets/${esc(g.stage?.art || "stage0")}.webp" alt="">
        <div class="whisper">${esc(g.stage?.line || "还在等第一件事发生")}</div>
      </div>
      <div class="pet-meta">
        <span class="nm">${esc(g.pet_name || "小芽")}</span>
        <span class="st">${esc(g.stage?.name || "")}</span>
      </div>
      ${g.next ? `<div class="growth-next">再 <b>${g.to_next}</b> 到${esc(g.next.name)}</div>` : `<div class="growth-next">${g.needs_branch ? "<b>可以化形了</b>" : "当前最高形态"}</div>`}
    </div>

    ${inbox ? `<div class="c-card">
      <div class="c-head">小光留了话</div>
      <p style="font-size:13px;line-height:1.75;margin:0">${esc(inbox.text)}</p>
    </div>` : ""}

    <div class="c-card">
      <div class="c-head">今天的小步 <span class="more" data-nav="plan">全部 →</span></div>
      ${steps.length ? steps.map((s) => `
        <div class="today-step">
          <button class="box" data-done="${esc(s.id)}" aria-label="完成">${icon("check")}</button>
          <div><div class="t">${esc(s.title)}</div></div>
        </div>`).join("") : `<p style="font-size:12px;color:var(--ink-3);margin:0">还没有待做的小步。</p>`}
    </div>

    ${guesses.length ? `<div class="c-card">
      <div class="c-head">等你确认</div>
      ${guesses.map((m) => `<div class="guess-card" style="margin-bottom:8px">
        <div class="q">${esc(m.text)}</div>
        <div class="acts"><button class="yes" data-confirm="${esc(m.id)}">对</button>
        <button data-reject="${esc(m.id)}">不太对</button></div>
      </div>`).join("")}
    </div>` : ""}

    <div class="c-card">
      <div class="c-head">快捷</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px">
        <button class="chip" data-quick="good">记一件好事</button>
        <button class="chip" data-quick="rest">今天偷懒日</button>
        <button class="chip" data-quick="relearn">重新认识我</button>
      </div>
    </div>`;

  ctx.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => go(b.dataset.nav)));
  ctx.querySelectorAll("[data-done]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        const out = await api.step("done", { id: b.dataset.done });
        setData(out);
        if (out.xp?.amount) toast(`+${out.xp.amount} 经验`);
        drawCtx();
        drawRail();
        rerender();
      } catch (e) {
        toast(e.message, "err");
      }
    }));
  ctx.querySelectorAll("[data-confirm]").forEach((b) =>
    b.addEventListener("click", () => memAct("confirm", b.dataset.confirm)));
  ctx.querySelectorAll("[data-reject]").forEach((b) =>
    b.addEventListener("click", () => memAct("reject", b.dataset.reject)));
  ctx.querySelectorAll("[data-quick]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (b.dataset.quick === "good") {
        const text = prompt("记一件好事（再小也算）")?.trim();
        if (!text) return;
        const out = await api.record("good", text);
        setData(out);
        toast(out.xp?.amount ? `+${out.xp.amount} 经验` : "记住了");
        rerender();
      } else if (b.dataset.quick === "rest") {
        const out = await api.record("rest", "今天想休息");
        setData(out);
        toast("今天是偷懒日，什么都不会清零");
        rerender();
      } else {
        const out = await api.sceneStart("relearn");
        state.sceneStep = { ...out.step, title: out.scene.title };
        state.sceneRunId = out.run?.id;
        setData({ scene: out.run });
        go("chat");
      }
    }));
}

async function memAct(action, id) {
  try {
    await api.memory(action, { id });
    const data = await api.bootstrap();
    setData(data);
    drawCtx();
    drawRail();
    rerender();
  } catch (e) {
    toast(e.message, "err");
  }
}

function scheduleCtx() {
  // 窄屏时右栏是抽屉；这里只处理移动端顶部按钮的显隐
  const btn = appEl?.querySelector("#ctxToggle");
  if (btn) btn.style.display = window.innerWidth <= 1200 ? "inline-flex" : "none";
}

function onRoute() {
  if (!state.ready || !viewRoot) return;
  const raw = location.hash.slice(1) || "chat";
  if (raw === "article" || state.route === "article") {
    state.route = "article";
  } else {
    state.route = raw;
  }
  rerender();
}

function rerender() {
  if (!state.ready || !viewRoot) return;
  const route = state.route;
  const d = state.data || {};
  const title = TITLES[route] || "显伴";

  viewRoot.innerHTML = `
    <header class="topbar">
      <h1>${esc(title)}</h1>
      <span class="crumb" id="crumb"></span>
      <span class="spacer"></span>
      <button class="tbtn" id="ctxToggle">${icon("menu")}此刻</button>
      <button class="tbtn" id="themeBtn">${icon(state.theme === "dusk" ? "sun" : "moon")}</button>
      ${route !== "chat" ? `<button class="tbtn" data-gochat>${icon("chat")}回到对话</button>` : ""}
    </header>
    <div class="page" id="page"></div>`;

  const page = viewRoot.querySelector("#page");
  const crumb = viewRoot.querySelector("#crumb");
  if (route === "article") {
    crumb.textContent = "心灵学堂";
  } else if (route === "growth") {
    crumb.textContent = `${d.growth?.stage?.name || ""} · ${d.growth?.total ?? 0} 经验`;
  } else if (route === "plan") {
    crumb.textContent = `${(d.steps || []).filter((s) => s.status === "todo").length} 件待做`;
  }

  viewRoot.querySelector("#themeBtn")?.addEventListener("click", () => {
    setTheme(state.theme === "dusk" ? "paper" : "dusk");
    rerender();
  });
  viewRoot.querySelector("#ctxToggle")?.addEventListener("click", () => {
    appEl.classList.toggle("ctx-open");
  });
  viewRoot.querySelector("[data-gochat]")?.addEventListener("click", () => go("chat"));

  switch (route) {
    case "chat": renderChat(page); break;
    case "plan": renderPlan(page); break;
    case "goodnews": renderNews(page); break;
    case "growth": renderGrowth(page); break;
    case "ideas": renderIdeas(page); break;
    case "academy": renderAcademy(page); break;
    case "article": renderArticle(page); break;
    case "report": renderReport(page); break;
    case "space": renderSpace(page); break;
    default: renderChat(page);
  }
  drawRail();
  drawCtx();
  scheduleCtx();
}

// 供其他模块在动作后刷新外壳
export { rerender, drawRail, drawCtx, drawApp };
