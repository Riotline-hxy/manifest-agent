// 应用外壳：路由、左侧导航、顶部状态、右侧「小窝」。
import { api } from "./api.js";
import { state, setData, go, subscribe } from "./store.js";
import { esc, toast } from "./ui.js";
import { art, buildScene, countUp } from "./fx.js";
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
  [
    { id: "chat", label: "对话", art: "" },
    { id: "plan", label: "蜕变计划", art: "st-flag" },
    { id: "goodnews", label: "好消息", art: "st-jar" },
    { id: "growth", label: "成长进化", art: "@pet" },
  ],
  [
    { id: "ideas", label: "点子", art: "st-compass" },
    { id: "academy", label: "心灵学堂", art: "st-book" },
    { id: "report", label: "蜕变报告", art: "st-letter" },
    { id: "space", label: "我的空间", art: "st-mirror" },
  ],
];

const TITLES = {
  chat: "和小光聊聊", plan: "蜕变计划", goodnews: "好消息", growth: "成长进化", ideas: "点子",
  academy: "心灵学堂", article: "心灵学堂", report: "蜕变报告", space: "我的空间",
};

const VIEWS = {
  chat: renderChat, plan: renderPlan, goodnews: renderNews, growth: renderGrowth, ideas: renderIdeas,
  academy: renderAcademy, article: renderArticle, report: renderReport, space: renderSpace,
};

let root;
let drawnRoute = "";

export function mount(el) {
  root = el;
  buildScene();
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
      if ((data.inbox?.length || 0) > before) toast("小光给你留了一句话", "", "st-letter");
    } catch {}
  });
  subscribe(() => {
    if (!state.ready || !root.querySelector(".app")) return;
    if (state.route !== drawnRoute) drawView();
    else { drawRail(); drawTop(); drawSide(); }
  });
  boot();
}

async function boot() {
  state.ready = false;
  const r = location.hash.slice(1);
  state.route = VIEWS[r] && r !== "article" ? r : "chat";
  try {
    const me = await api.me();
    if (!me.user) {
      root.innerHTML = "";
      renderGate(root);
      return;
    }
    state.user = me.user;
    const data = await api.bootstrap();
    setData(data, { silent: true });
    if (!data.profile?.onboarded) {
      root.innerHTML = "";
      renderOnboarding(root);
      return;
    }
    state.ready = true;
    drawShell();
  } catch (e) {
    root.innerHTML = `<div class="empty" style="padding-top:20vh"><img src="${art("st-moon")}" alt="">
      <h3>没连上</h3><p>${esc(e?.message || "加载失败")}</p><button class="btn btn-lamp" onclick="location.reload()">再试一次</button></div>`;
  }
}

function drawShell() {
  root.innerHTML = `
    <div class="app">
      <nav class="rail" aria-label="主导航"></nav>
      <main class="main">
        <header class="topbar"></header>
        <div class="view"></div>
      </main>
      <aside class="side" aria-label="小窝"></aside>
    </div>`;
  drawView();
}

function petArt() {
  return state.data?.growth?.stage?.art || "pet-egg";
}

function drawRail() {
  const rail = root.querySelector(".rail");
  if (!rail) return;
  const d = state.data || {};
  const g = d.growth || {};
  const todo = (d.steps || []).filter((s) => s.status === "todo").length;
  const guesses = (d.memories || []).filter((m) => m.status === "guess").length;
  const unseen = (d.inbox || []).length;
  const dot = { chat: unseen, plan: todo, space: guesses };
  rail.innerHTML = `
    <div class="logo"><img src="${art("st-seed")}" alt=""><b>显<em>伴</em></b></div>
    ${NAV.map((grp, gi) => `${gi ? '<div class="nav-sep"></div>' : ""}${grp.map((it) => {
      const on = state.route === it.id || (it.id === "academy" && state.route === "article");
      const ic = it.art === "" ? '<span class="mini-orb"></span>' : `<img src="${art(it.art === "@pet" ? petArt() : it.art)}" alt="">`;
      const badge = dot[it.id] ? `<span class="badge-dot">${dot[it.id]}</span>`
        : it.id === "growth" && g.to_next && g.to_next <= 20 ? `<span class="badge-dot lamp">快了</span>` : "";
      return `<button class="nav-item ${on ? "active" : ""}" data-nav="${it.id}"><span class="ic">${ic}</span><span>${it.label}</span>${badge}</button>`;
    }).join("")}`).join("")}
    <div class="rail-foot">
      <div class="me">
        <span class="av">${esc((d.profile?.nickname || state.user?.username || "我").slice(0, 1))}</span>
        <span class="grow"><div class="nm">${esc(d.profile?.nickname || state.user?.username || "体验账号")}</div>
          <div class="sub">${state.user?.kind === "guest" ? "体验账号" : "已登录"}</div></span>
        ${state.user?.kind === "guest" ? `<button data-act="claim">保存</button>` : `<button data-act="logout">退出</button>`}
      </div>
      <div class="credit">小光形象：Emotion Ball（非商业演示授权）</div>
    </div>`;
  rail.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => go(b.dataset.nav)));
  rail.querySelector("[data-act=logout]")?.addEventListener("click", async () => {
    await api.logout();
    location.hash = "";
    location.reload();
  });
  rail.querySelector("[data-act=claim]")?.addEventListener("click", claimSheet);
}

async function claimSheet() {
  const { sheet, h } = await import("./ui.js");
  const u = h("input", { class: "field", placeholder: "用户名（2–20 位）", maxlength: "20" });
  const p = h("input", { class: "field", type: "password", placeholder: "密码（至少 6 位）", style: "margin-top:10px" });
  const err = h("p", { style: "color:var(--danger);font-size:13px;min-height:18px;margin:8px 0 0" });
  const s = sheet({
    title: "把体验账号保存下来", sticker: "st-chest",
    body: h("div", {}, h("p", { style: "color:var(--text-2);margin:0 0 14px;font-size:14px" }, "之前的记录、宠物和徽章都会留着。"), u, p, err),
    footer: [h("button", {
      class: "btn btn-lamp", onclick: async () => {
        try {
          const out = await api.register(u.value.trim(), p.value);
          state.user = out.user;
          s.close();
          toast("账号保存好了", "", "st-chest-open");
          drawRail();
        } catch (e) { err.textContent = e.message; }
      },
    }, "保存")],
  });
}

function drawTop() {
  const top = root.querySelector(".topbar");
  if (!top) return;
  const d = state.data || {};
  const g = d.growth || {};
  const lv = g.level || { lv: 1, pct: 0, into: 0, need: 40 };
  const days = d.counts?.days || 1;
  const prev = top.querySelector("[data-xp-num]")?.dataset.v;
  const shown = prev ?? g.today?.total ?? 0;
  top.innerHTML = `
    <span class="title">${esc(TITLES[state.route] || "显伴")}</span>
    <span class="spacer"></span>
    <button class="stat"><img src="${art("st-seed")}" alt=""><span class="num">${days}</span>
      <span class="tip"><b>陪伴第 ${days} 天</b>偷懒日不会清零任何东西，这里只会往上加。</span></button>
    <button class="stat" data-xp-target><img src="${art("st-jar")}" alt="">
      <span class="num" data-xp-num data-v="${shown}">${shown}</span><span class="muted" style="font-size:12px">/120</span>
      <span class="tip"><b>今天的经验</b>行动、好消息、练习、陪伴四类各 30，一天最多 120。同一件事不会重复计分。</span></button>
    <button class="stat" data-nav="growth"><span class="lvl" style="--p:${Math.round(lv.pct * 100)}"><span>${lv.lv}</span></span>
      <span class="num">Lv${lv.lv}</span>
      <span class="tip"><b>等级 ${lv.lv}</b>每 40 经验升一级，这一级还差 ${lv.need - lv.into}。</span></button>
    <button class="btn btn-sm btn-ghost only-narrow" data-act="side"><img src="${art(petArt())}" alt="" style="width:22px;height:22px">小窝</button>`;
  // 经验飞入动画结束时再滚动数字，避免数字先变
  setTimeout(() => countUp(top.querySelector("[data-xp-num]"), g.today?.total ?? 0), prev != null && Number(prev) !== g.today?.total ? 950 : 0);
  top.querySelector("[data-nav]")?.addEventListener("click", () => go("growth"));
  top.querySelector("[data-act=side]")?.addEventListener("click", () => root.querySelector(".app").classList.toggle("side-open"));
}

const QUEST_ART = { action: "st-flag", good: "st-jar", practice: "st-lotus", checkin: "st-letter" };

function drawSide() {
  const side = root.querySelector(".side");
  if (!side) return;
  const d = state.data || {};
  const g = d.growth || {};
  if (!g.stage) return;
  const span = g.next ? g.next.at - g.prev_at : 1;
  const pct = g.next ? Math.round(((g.total - g.prev_at) / span) * 100) : 100;
  const guesses = (d.memories || []).filter((m) => m.status === "guess").slice(0, 2);
  const inbox = (d.inbox || [])[0];
  const lastDigest = (d.digests || [])[0];
  side.innerHTML = `
    <div class="nook" data-nav="growth" title="去看成长">
      <div class="head"><span class="pill lamp">Lv ${g.level.lv}</span><span class="pill">${esc(g.branch_info?.name || "还没分化")}</span></div>
      <div class="stage-art"><span class="pedestal"></span><img src="${art(g.stage.art)}" alt=""></div>
      <div class="nm">${esc(g.pet_name)} · ${esc(g.stage.name)}</div>
      <div class="ln">${esc(g.stage.line)}</div>
      <div class="bar lamp"><i style="width:${pct}%"></i></div>
      <div class="to">${g.next ? `再 <b>${g.to_next}</b> 经验到「${esc(g.next.name)}」` : "已经是成年形态了"}</div>
    </div>

    <div class="card quests">
      <div class="sec-title" style="margin-bottom:4px">今日任务 <span class="more">${g.quests_done}/4</span></div>
      ${g.quests.map((q) => `
        <div class="q ${q.done ? "done" : ""}">
          <img src="${art(QUEST_ART[q.id])}" alt="">
          <div><div class="t">${q.done ? "✓ " : ""}${esc(q.label)}<span>${Math.min(q.got, q.need)}/${q.need}</span></div>
          <div class="bar sm ${q.done ? "" : "lamp"}"><i style="width:${Math.min(100, (q.got / q.need) * 100)}%"></i></div></div>
        </div>`).join("")}
      <div class="chest ${g.quests_done === 4 ? "open" : ""}"><img src="${art(g.quests_done === 4 ? "st-chest-open" : "st-chest")}" alt="">
        ${g.quests_done === 4 ? "今天四件小事都做到了。" : `再完成 ${4 - g.quests_done} 件，宝箱就开了。`}</div>
    </div>

    ${inbox ? `<div class="card"><div class="sec-title">小光留了话</div><div class="note">${esc(inbox.text)}</div></div>` : ""}

    ${guesses.length ? `<div class="card"><div class="sec-title">小光猜的，对吗？</div>
      ${guesses.map((m) => `<div class="guess" style="margin-bottom:8px">${esc(m.text)}
        <div class="acts"><button class="btn btn-sm btn-leaf" data-confirm="${esc(m.id)}">对</button>
        <button class="btn btn-sm btn-ghost" data-reject="${esc(m.id)}">不太对</button></div></div>`).join("")}</div>` : ""}

    ${lastDigest ? `<div class="card" data-nav="space" data-tab="digest" style="cursor:pointer">
      <div class="sec-title"><img src="${art("st-moon")}" alt="" style="width:26px;height:26px">夜里整理了 <span class="more">${esc(lastDigest.day.slice(5))}</span></div>
      <div class="note">${esc(lastDigest.summary)}</div></div>` : ""}`;

  side.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
    root.querySelector(".app").classList.remove("side-open");
    if (b.dataset.tab) state.spaceTab = b.dataset.tab;
    if (state.route === b.dataset.nav) drawView();
    else go(b.dataset.nav);
  }));
  side.querySelectorAll("[data-confirm],[data-reject]").forEach((b) => b.addEventListener("click", async (e) => {
    e.stopPropagation();
    const action = b.dataset.confirm ? "confirm" : "reject";
    try {
      setData(await api.memory(action, { id: b.dataset.confirm || b.dataset.reject }));
      toast(action === "confirm" ? "记下了，以后会用它理解你" : "删掉了，谢谢你纠正我", "", "st-mirror");
    } catch (err) { toast(err.message, "err"); }
  }));
}

function drawView() {
  const view = root.querySelector(".view");
  if (!view) return;
  drawnRoute = state.route;
  root.querySelector(".app")?.classList.remove("side-open");
  view.scrollTop = 0;
  view.innerHTML = "";
  (VIEWS[state.route] || renderChat)(view);
  drawRail();
  drawTop();
  drawSide();
}

export function redrawView() {
  drawView();
}
