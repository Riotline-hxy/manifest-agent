// 蜕变计划：愿望 → 小步 → 完成。每完成一步，浮岛上长出一株植物（专注森林的感觉），
// 但没有连续打卡惩罚：偷懒日不清零，「先放一放」也不算失败。
import { api } from "../api.js";
import { state, setData, xpNote } from "../store.js";
import { esc, fmtDay, toast, confirmSheet, icon } from "../ui.js";
import { art, flyXP, burstAt } from "../fx.js";

const PLANTS = ["plant-sprout", "plant-tulip", "plant-bush", "plant-tree", "plant-glow"];

// 岛面是一个椭圆：中心 (50%, 25%)，半径 (36%, 9%)。按黄金角铺开，按 y 排序保证前后遮挡正确。
function plantSpots(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const r = Math.sqrt((i + 0.6) / Math.max(n, 6));
    const a = i * 2.39996;
    out.push({ x: 50 + Math.cos(a) * r * 36, y: 31 + Math.sin(a) * r * 9, i });
  }
  return out.sort((p, q) => p.y - q.y);
}

export function renderPlan(root, { fresh = "" } = {}) {
  const d = state.data;
  const p = d.profile || {};
  const steps = d.steps || [];
  const todo = steps.filter((s) => s.status === "todo");
  const done = steps.filter((s) => s.status === "done");
  const dropped = steps.filter((s) => s.status === "dropped");
  const shown = done.slice(0, 24).reverse();   // oldest first so each plant keeps its spot
  const spots = plantSpots(shown.length);

  root.innerHTML = `
    <div class="view-inner wide plan">
      <div class="page-title"><img src="${art("st-flag")}" alt=""><div><h1>蜕变计划</h1><p>把愿望拆成 5 分钟内能开始的小步</p></div></div>

      <section class="plan-hero">
        <div class="wish card">
          <div class="pill lamp">正在靠近</div>
          <h2>${esc(p.intent_primary || "还没定下想靠近的东西")}</h2>
          <p>${p.intent_why ? `因为：${esc(p.intent_why)}` : "可以在聊天里告诉小光，或者去「说清想要的」慢慢说。"}</p>
          <div class="next-step"><small>下一小步</small>${todo[0] ? esc(todo[0].title) : "还没有，加一条吧"}</div>
          <div class="wish-stats">
            <div><span class="num">${done.length}</span><small>已完成</small></div>
            <div><span class="num">${todo.length}</span><small>待做</small></div>
            <div><span class="num">${dropped.length}</span><small>放一放</small></div>
          </div>
        </div>
        <div class="garden">
          <div class="garden-island">
            <img class="island" src="${art("garden-island")}" alt="">
            ${spots.map((s, k) => {
              const st = shown[s.i];
              const isNew = st.id === fresh;
              return `<img class="plant ${isNew ? "new" : ""}" src="${art(PLANTS[s.i % PLANTS.length])}" alt=""
                title="${esc(st.title)}" style="left:${s.x}%;top:${s.y}%;--d:${isNew ? 0 : k * 45}ms">`;
            }).join("")}
          </div>
          <div class="garden-cap">${done.length ? `已种下 <b>${done.length}</b> 株 · 每完成一小步，岛上多一株` : "完成第一小步，岛上会长出第一株芽"}</div>
        </div>
      </section>

      <section class="section">
        <div class="sec-title">今天和之后 <span class="more">${todo.length} 件</span></div>
        <div class="steps">
          ${todo.map((s, i) => stepCard(s, i)).join("") || `<div class="empty"><img src="${art("st-seed")}" alt=""><h3>没有待做的小步</h3><p>在下面加一条，或者在对话里说「帮我定一个今天能开始的小步」。</p></div>`}
        </div>
        <div class="add-row">
          <input class="field" id="newStep" placeholder="加一条 5 分钟内能开始的小步…" maxlength="40">
          <button class="btn btn-lamp" id="addStep">${icon("plus")}加入</button>
        </div>
      </section>

      ${done.length ? `<section class="section"><details class="done-list card">
        <summary>已完成 ${done.length} 个小步 <span class="muted">· 展开看看走过的路</span></summary>
        ${done.slice(0, 40).map((s) => `<div class="done-row"><span class="ck">${icon("check")}</span><span>${esc(s.title)}</span><span class="muted">${esc(fmtDay(s.done_at))}</span></div>`).join("")}
      </details></section>` : ""}

      ${dropped.length ? `<section class="section"><div class="sec-title">先放一放</div>
        ${dropped.map((s) => `<div class="done-row dim"><span>${esc(s.title)}</span><button class="btn btn-sm btn-ghost" data-back="${esc(s.id)}">放回待办</button></div>`).join("")}</section>` : ""}
    </div>`;

  root.querySelectorAll("[data-done]").forEach((b) => b.addEventListener("click", async () => {
    const card = b.closest(".step");
    card.classList.add("checking");
    try {
      const out = await api.step("done", { id: b.dataset.done });
      burstAt(b, 36);
      if (out.xp?.amount) flyXP(b, out.xp.amount);
      else toast(xpNote(out.xp) || "完成了", "", "st-flag");
      setTimeout(() => { setData(out); renderPlan(root, { fresh: b.dataset.done }); }, 520);
    } catch (e) {
      card.classList.remove("checking");
      toast(e.message, "err");
    }
  }));
  root.querySelectorAll("[data-drop]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmSheet("先放一放？", "它不会消失，也不算失败。想做的时候随时放回来。", "放一放"))) return;
    setData(await api.step("drop", { id: b.dataset.drop }));
    renderPlan(root);
  }));
  root.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", async () => {
    setData(await api.step("todo", { id: b.dataset.back }));
    renderPlan(root);
  }));
  const add = async () => {
    const inp = root.querySelector("#newStep");
    const title = inp.value.trim();
    if (!title) return inp.focus();
    try {
      setData(await api.step("add", { title }));
      toast("加进计划了", "", "st-flag");
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  };
  root.querySelector("#addStep").addEventListener("click", add);
  root.querySelector("#newStep").addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
  if (fresh) setTimeout(() => burstAt(root.querySelector(".plant.new"), 26), 500);
}

function stepCard(s, i) {
  return `<div class="step" style="--i:${i}">
    <button class="check" data-done="${esc(s.id)}" aria-label="完成">${icon("check")}</button>
    <div class="step-main">
      <div class="st">${esc(s.title)}</div>
      ${s.why ? `<div class="sw">${esc(s.why)}</div>` : ""}
    </div>
    <span class="pill lamp">+10</span>
    <button class="btn btn-quiet btn-sm" data-drop="${esc(s.id)}">先放一放</button>
  </div>`;
}
