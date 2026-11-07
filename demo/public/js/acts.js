// 小光在聊天里做的事，统一成三种样子（服务端 core/acts.py 给出视图）：
//   entry 推荐：功能入口，所有功能同一个结构（图标 + 名字 + 一句介绍 + 开始）
//   slip  回执：气泡下面一行，「动词 + 是哪一项」，改了就写 旧 → 新；能撤销的带撤销
//   ask   待确认：小光提议，TA 点了才算；点完原地变成结果，重看聊天时也知道最后留没留
// 同一条回复里改了 3 处以上，回执收成一行「调整了 N 处 · 查看变化」。
import { api } from "./api.js";
import { state, setData, go } from "./store.js";
import { esc, icon, tile, toast } from "./ui.js";
import { flyGain, burstAt } from "./fx.js";
import { startScene } from "./scene.js";
import { openKick } from "./kick.js";
import { adjustSheet } from "./rest.js";
import { askNotify } from "./tasks.js";

const GO_LABEL = { plan: "去看看", goodnews: "去看看", panel: "去看看", space: "去看看", notebook: "看看笔记本", town: "去看看" };

function open(o = {}) {
  if (o.kick) return openKick({ task: o.task || "" });
  if (o.scene) return startScene(o.scene);
  if (o.article) return go("article", { id: o.article });
  if (o.go) return go(o.go);
}

function goTo(where) {
  if (where === "notebook") { state.spaceTab = "digest"; go("space"); return; }
  go(where);
}

function entryEl(v) {
  const el = document.createElement("div");
  el.className = "cact act-entry";
  el.innerHTML = `${tile(v.icon, v.color, 40)}
    <div class="act-main"><b>${esc(v.title)}</b><span>${esc(v.desc || "")}${v.minutes ? ` · ${v.minutes} 分钟` : ""}</span></div>
    <button class="btn btn-sm btn-main">${v.open?.go || v.open?.article ? "去看看" : "开始"}</button>`;
  el.querySelector("button").addEventListener("click", () => open(v.open));
  return el;
}

function slipText(v) {
  const verb = `<span class="act-verb">${esc(v.verb)}</span>`;
  if (v.old) return `${verb} <del>${esc(v.old)}</del><span class="act-arrow">→</span>${esc(v.new)}`;
  return v.new ? `${verb}${v.verb.endsWith("：") ? "" : "："}${esc(v.new)}` : verb;
}

function slipEl(v, i, ctx) {
  const el = document.createElement("div");
  const undone = v.state === "undone";
  el.className = `cact act-slip ${v.fail ? "fail" : ""} ${undone ? "undone" : ""}`;
  const canUndo = v.undo && !undone && ctx.msgId && Date.parse(v.undo.until || 0) > Date.now();
  const links = [];
  if (undone) links.push(`<span class="act-note">已撤销</span>`);
  else if (canUndo) links.push(`<button class="act-link" data-undo>撤销</button>`);
  if (!undone && v.adjust) links.push(`<button class="act-link" data-adjust>调整计划</button>`);
  if (!undone && v.notify && "Notification" in window && Notification.permission === "default") links.push(`<button class="act-link" data-notify>开启通知</button>`);
  if (!undone && !canUndo && v.go && GO_LABEL[v.go]) links.push(`<button class="act-link" data-go="${esc(v.go)}">${GO_LABEL[v.go]}</button>`);
  el.innerHTML = `<span class="act-ic" style="color:${v.fail ? "var(--danger)" : esc(v.color)}">${icon(v.icon)}</span>
    <span class="act-txt">${slipText(v)}</span>
    ${v.gain && !undone ? `<span class="act-gain">+${v.gain}</span>` : ""}${links.join("")}`;
  el.querySelector("[data-undo]")?.addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    try { setData(await api.act({ msg_id: ctx.msgId, i, op: "undo" })); toast("撤销了"); }
    catch (err) { toast(err.message, "err"); e.currentTarget.disabled = false; }
  });
  el.querySelector("[data-adjust]")?.addEventListener("click", () => adjustSheet());
  el.querySelector("[data-notify]")?.addEventListener("click", (e) => { askNotify(); e.currentTarget.remove(); });
  el.querySelector("[data-go]")?.addEventListener("click", (e) => goTo(e.currentTarget.dataset.go));
  return el;
}

// 接口返回的数据是在记下状态之前取的：把这条消息里的状态补上再重画，不然按钮又会出来
function withState(out, ctx, i, state) {
  const m = (out?.messages || []).find((x) => x.id === ctx.msgId);
  if (m?.meta?.acts?.[i]) m.meta.acts[i].state = state;
  return out;
}

async function saveState(ctx, i, st) {
  withState(state.data, ctx, i, st);    // 本地的数据也改上，页面再重画时不会又冒出按钮
  if (!ctx.msgId) return;
  try { await api.act({ msg_id: ctx.msgId, i, op: "state", state: st }); } catch {}
}

function askMoment(el, v, i, ctx) {
  const p = v.proposal || {};
  const ws = v.wishes || [];
  const foot = el.querySelector(".act-foot");
  if (v.state === "kept") { foot.innerHTML = `<span class="act-done">${icon("check")}留在轨迹上了</span><button class="act-link" data-go="plan">去看看</button>`; }
  else if (v.state === "skipped") { foot.innerHTML = `<span class="act-note">这次没留</span>`; el.classList.add("dim"); }
  else {
    foot.innerHTML = `${ws.length > 1 ? `<select class="field field-sm" aria-label="留在哪个愿望下">${ws.map((w) =>
        `<option value="${esc(w.id)}" ${w.id === p.wish_id ? "selected" : ""}>${esc(w.title)}</option>`).join("")}</select>` : ""}
      <button class="btn btn-sm btn-main" data-keep>留下</button><button class="btn btn-sm btn-quiet" data-skip>不用</button>`;
    foot.querySelector("[data-skip]").addEventListener("click", () => { v.state = "skipped"; saveState(ctx, i, "skipped"); askMoment(el, v, i, ctx); });
    foot.querySelector("[data-keep]").addEventListener("click", async (e) => {
      const wid = foot.querySelector("select")?.value || p.wish_id;
      e.currentTarget.disabled = true;
      try {
        const out = await api.moment("add", { wish_id: wid, text: p.text, feeling: p.feeling, source: "chat" });
        v.state = "kept";
        await saveState(ctx, i, "kept");
        burstAt(el.querySelector(".act-ic"), 22);
        flyGain(el.querySelector(".act-ic"), out.xp);
        setData(withState(out, ctx, i, "kept"));
        if (el.isConnected) askMoment(el, v, i, ctx);   // 原地变成「留在轨迹上了」
      } catch (err) { e.currentTarget.disabled = false; toast(err.message, "err"); }
    });
  }
  foot.querySelector("[data-go]")?.addEventListener("click", () => go("plan"));
}

function askPlan(el, v, i, ctx) {
  const plan = v.plan || {};
  const foot = el.querySelector(".act-foot");
  if (v.state === "added") { foot.innerHTML = `<span class="act-done">${icon("check")}加进计划了</span><button class="act-link" data-go="plan">去看看</button>`; }
  else if (v.state === "skipped") { foot.innerHTML = `<span class="act-note">这次先不加</span>`; el.classList.add("dim"); }
  else {
    const groups = [["milestones", "里程碑"], ["habits", "习惯"], ["steps", "小步"]];
    foot.classList.add("act-pick");
    foot.innerHTML = `${v.why ? `<p class="act-why">${esc(v.why)}</p>` : ""}
      ${groups.filter(([k]) => (plan[k] || []).length).map(([k, label]) => plan[k].map((it, n) => `<label class="act-it"><input type="checkbox" checked data-k="${k}" data-i="${n}">
        <span><small>${label}</small>${esc(it.title)}</span><em>${k === "habits" ? (it.freq === "weekly" ? `每周 ${it.per_week || 3} 次` : "每天") : k === "milestones" && it.due_in_days ? `约 ${it.due_in_days} 天后` : ""}</em></label>`).join("")).join("")}
      <div class="act-btns"><button class="btn btn-sm btn-main" data-apply>加进计划</button><button class="btn btn-sm btn-quiet" data-skip>先不加</button></div>`;
    foot.querySelector("[data-skip]").addEventListener("click", () => { v.state = "skipped"; foot.classList.remove("act-pick"); saveState(ctx, i, "skipped"); askPlan(el, v, i, ctx); });
    foot.querySelector("[data-apply]").addEventListener("click", async (e) => {
      const pick = { milestones: [], habits: [], steps: [] };
      foot.querySelectorAll("input:checked").forEach((c) => pick[c.dataset.k].push(plan[c.dataset.k][+c.dataset.i]));
      if (!pick.milestones.length && !pick.habits.length && !pick.steps.length) return toast("至少勾一项");
      e.currentTarget.disabled = true;
      try {
        const out = await api.planApply({ wish_id: v.wish_id, ...pick });
        v.state = "added";
        foot.classList.remove("act-pick");
        await saveState(ctx, i, "added");
        burstAt(el.querySelector(".act-ic"), 26);
        setData(withState(out, ctx, i, "added"));
        if (el.isConnected) { foot.classList.remove("act-pick"); askPlan(el, v, i, ctx); }
      } catch (err) { e.currentTarget.disabled = false; toast(err.message, "err"); }
    });
  }
  foot.querySelector("[data-go]")?.addEventListener("click", () => go("plan"));
}

function askEl(v, i, ctx) {
  const el = document.createElement("div");
  el.className = "cact act-ask";
  el.innerHTML = `<div class="act-q"><span class="act-ic" style="color:${esc(v.color)}">${icon(v.icon)}</span><span>${esc(v.question)}</span></div>
    ${v.text ? `<div class="act-quote">${esc(v.text)}</div>` : ""}<div class="act-foot"></div>`;
  (v.ask === "plan" ? askPlan : askMoment)(el, v, i, ctx);
  return el;
}

export function actEl(v, i, ctx) {
  if (!v) return null;
  if (v.type === "entry") return entryEl(v);
  if (v.type === "slip") return slipEl(v, i, ctx);
  if (v.type === "ask") return askEl(v, i, ctx);
  return null;
}

// 一条回复里的全部动作（重看聊天时用）。回执 3 条以上收成一行。
export function actsBlock(acts, ctx) {
  const box = document.createElement("div");
  box.className = "acts";
  const slips = acts.map((v, i) => [v, i]).filter(([v]) => v?.type === "slip");
  const group = slips.length >= 3 ? document.createElement("details") : null;
  if (group) {
    group.className = "cact act-group";
    group.innerHTML = `<summary><span class="act-ic" style="color:var(--good)">${icon("check")}</span><span class="act-txt"><span class="act-verb">调整了 ${slips.length} 处</span></span><span class="act-link">查看变化</span></summary>`;
  }
  acts.forEach((v, i) => {
    const el = actEl(v, i, ctx);
    if (!el) return;
    if (group && v.type === "slip") { group.append(el); if (!group.isConnected) box.append(group); }
    else box.append(el);
  });
  return box.childElementCount ? box : null;
}

// 正在回复时，一个动作刚做完：画出来，顺手飞一下经验
export function liveAct(v, i, ctx, gainFrom) {
  const el = actEl(v, i, ctx);
  if (!el) return null;
  if (v.type === "slip" && v.gain) setTimeout(() => flyGain(el.querySelector(".act-gain") || el, gainFrom || { amount: v.gain }), 250);
  if (v.type === "slip" && ["star", "check"].includes(v.icon)) setTimeout(() => burstAt(el.querySelector(".act-ic"), 22), 150);
  return el;
}
