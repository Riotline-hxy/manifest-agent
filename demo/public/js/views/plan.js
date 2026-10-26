// 蜕变计划：愿望 → 小步 → 复盘。完成一步种一棵树（专注森林的思路），
// 但不做连续签到惩罚——偷懒日不清零。
import { api } from "../api.js";
import { state, setData, xpNote } from "../store.js";
import { esc, h, fmtDay, toast, icon, confirmSheet } from "../ui.js";

const TREE_HEIGHTS = [16, 24, 20, 30, 22, 34, 26, 38, 28, 40];

function tree(i) {
  const hgt = TREE_HEIGHTS[i % TREE_HEIGHTS.length];
  const w = 8 + (i % 4) * 3;
  return `<span class="tree" style="height:${hgt}px;animation-delay:${i * 40}ms">
    <svg viewBox="0 0 20 60" preserveAspectRatio="xMidYMax meet" style="height:100%;width:${w}px">
      <path d="M10 58V26" stroke="#5c7a62" stroke-width="1.4" fill="none"/>
      <ellipse cx="10" cy="20" rx="8" ry="12" fill="${i % 3 === 0 ? "#6f9a7c" : i % 3 === 1 ? "#88ac8d" : "#5d8a6c"}"/>
      <ellipse cx="10" cy="26" rx="6" ry="8" fill="${i % 2 ? "#7ba287" : "#94b699"}"/>
    </svg></span>`;
}

export function renderPlan(root) {
  const data = state.data;
  const p = data.profile || {};
  const steps = data.steps || [];
  const todo = steps.filter((s) => s.status === "todo");
  const done = steps.filter((s) => s.status === "done");
  const dropped = steps.filter((s) => s.status === "dropped");

  root.innerHTML = `
    <div class="page-inner">
      <div class="plan-hero">
        <div style="min-width:0">
          <div class="eyebrow">蜕变计划</div>
          <h2 class="wish">${esc(p.intent_primary || "还没有定下想靠近的东西")}</h2>
          ${p.intent_why ? `<div class="why">因为：${esc(p.intent_why)}</div>` : `<div class="why">可以在聊天里告诉小光，或者去「重新认识我」慢慢说。</div>`}
        </div>
        <div class="spacer"></div>
        <div style="text-align:right">
          <div class="tag jade">${todo.length} 件待做</div>
        </div>
      </div>

      <div class="garden">
        <div class="soil"></div>
        <div class="label">这棵树来自你完成的小步 · <b>${done.length}</b></div>
        ${done.slice(0, 10).reverse().map((_, i) => tree(i)).join("")}
        ${done.length === 0 ? `<span style="color:var(--ink-3);font-size:12px;z-index:1">第一棵树还没有种下</span>` : ""}
      </div>

      <div class="plan-group">
        <div class="pg-head">今天与之后</div>
        ${todo.length ? todo.map(stepRow).join("") : `<div class="empty"><div class="glyph">小步</div><p>还没有待做的小步。可以在下面加一条，或者回到聊天里说「帮我定一个今天能开始的小步」。</p></div>`}
        <div class="add-step">
          <input class="field" id="newStep" placeholder="加一条 5 分钟内能开始的小步" maxlength="40">
          <button class="btn btn-ink" id="addStep">${icon("plus")}加入计划</button>
        </div>
      </div>

      ${done.length ? `<div class="plan-group">
        <div class="pg-head">已完成 · ${done.length}</div>
        ${done.slice(0, 30).map(stepRow).join("")}
      </div>` : ""}

      ${dropped.length ? `<div class="plan-group">
        <div class="pg-head">先放一放 · ${dropped.length}</div>
        ${dropped.map(stepRow).join("")}
      </div>` : ""}

      <p style="font-size:11.5px;color:var(--ink-4);line-height:1.8">
        计划页读的是和后端同一份状态：聊天里完成的一步，这里立刻会打勾。
        中断不会清零，也没有连续签到惩罚——「偷懒日」是记录，不是欠账。
      </p>
    </div>`;

  root.querySelectorAll("[data-done]").forEach((b) => {
    b.addEventListener("click", async () => {
      try {
        const out = await api.step("done", { id: b.dataset.done });
        setData(out);
        const note = xpNote(out.xp);
        toast(note || "完成了");
        renderPlan(root);
      } catch (e) {
        toast(e.message, "err");
      }
    });
  });
  root.querySelectorAll("[data-drop]").forEach((b) => {
    b.addEventListener("click", async () => {
      const ok = await confirmSheet("先放一放？", "它不会消失，也不会被当成失败。你随时可以放回待办。", "放一放");
      if (!ok) return;
      try {
        const out = await api.step("drop", { id: b.dataset.drop });
        setData(out);
        renderPlan(root);
      } catch (e) {
        toast(e.message, "err");
      }
    });
  });
  root.querySelectorAll("[data-back]").forEach((b) => {
    b.addEventListener("click", async () => {
      const out = await api.step("todo", { id: b.dataset.back });
      setData(out);
      renderPlan(root);
    });
  });

  const add = async () => {
    const inp = root.querySelector("#newStep");
    const title = inp.value.trim();
    if (!title) return;
    try {
      const out = await api.step("add", { title });
      setData(out);
      renderPlan(root);
      toast("加进计划了");
    } catch (e) {
      toast(e.message, "err");
    }
  };
  root.querySelector("#addStep").addEventListener("click", add);
  root.querySelector("#newStep").addEventListener("keydown", (e) => {
    if (e.key === "Enter") add();
  });
}

function stepRow(s) {
  const isDone = s.status === "done";
  const isDropped = s.status === "dropped";
  return `<div class="step-row ${isDone ? "done" : ""}">
    <button class="box" ${isDone || isDropped ? "disabled" : `data-done="${esc(s.id)}" aria-label="完成"`}>
      ${icon("check")}</button>
    <div>
      <div class="title">${esc(s.title)}</div>
      ${s.why ? `<div class="why">${esc(s.why)}</div>` : ""}
      ${isDone && s.done_at ? `<div class="done-at">${esc(fmtDay(s.done_at))}完成</div>` : ""}
    </div>
    <div class="acts">
      ${isDone ? "" : isDropped
        ? `<button data-back="${esc(s.id)}">放回</button>`
        : `<button data-drop="${esc(s.id)}">先放一放</button>`}
    </div>
  </div>`;
}
