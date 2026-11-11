// 蜕变计划的日历：小步排期、走过的日子、当天详情。
// 只用 bootstrap 里的真实数据，不造日期或记录。小步的安排（scheduled_day）只是给自己的提醒：
// 安排在今天以前、还没做的，当成「还没安排」——过去的日子里只显示真正做过的事，没有逾期。
import { aname } from "./store.js";
import { api } from "./api.js";
import { esc, icon, sheet, h } from "./ui.js";
import { catOf } from "./journey.js";
import { photoURL } from "./moments.js";

const WEEK = "日一二三四五六";
const D = (s) => new Date(s.slice(0, 10) + "T00:00:00Z");
const K = (d) => d.toISOString().slice(0, 10);
export const addDays = (s, n) => K(new Date(D(s).getTime() + n * 864e5));
export const diffDays = (a, b) => Math.round((D(a) - D(b)) / 864e5);
export const md = (s) => `${+s.slice(5, 7)}月${+s.slice(8, 10)}日`;
export const wk = (s) => "周" + WEEK[D(s).getUTCDay()];
export const weekStart = (s) => addDays(s, -((D(s).getUTCDay() + 6) % 7));   // 一周从周一算
const monthEnd = (s) => K(new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7), 0)));
const shiftMonth = (s, n) => K(new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1 + n, 1)));
export const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// 还算数的安排日：没做，并且安排在今天或以后
export const planOf = (s, today) => (s.status === "todo" && s.scheduled_day && s.scheduled_day >= today ? s.scheduled_day : "");
export function planLabel(day, today) {
  const n = diffDays(day, today);
  return n === 0 ? "今天" : n === 1 ? "明天" : n > 1 && n < 7 ? wk(day) : md(day);
}

// ---------------------------------------------------------------- 数据 ----
export function planModel(data) {
  const J = data.journey || {};
  const wishes = J.wishes || [];
  const today = J.today;
  const first = wishes[0]?.id || "";
  const live = new Set(wishes.map((w) => w.id));
  const steps = (data.steps || []).map((s) => (s.wish_id ? s : { ...s, wish_id: first }));   // 没挂愿望的算第一个
  const todo = steps.filter((s) => s.status === "todo" && live.has(s.wish_id));
  const wishOf = (id) => wishes.find((w) => w.id === id);
  const color = (id) => (wishOf(id) ? catOf(wishOf(id).category).color : "var(--accent)");   // 不挂愿望的瞬间用强调色
  const push = (map, k, v) => (map.get(k) || map.set(k, []).get(k)).push(v);

  const days = new Map();
  const at = (d) => days.get(d) || days.set(d, { steps: [], habits: [], ms: [], moments: [] }).get(d);
  for (const s of steps) if (s.status === "done" && s.done_at) at(s.done_at.slice(0, 10)).steps.push(s);
  for (const w of wishes) {
    for (const hb of w.habits || []) for (const d of hb.days || []) at(d).habits.push({ ...hb, wish_id: w.id });
    for (const m of w.milestones || []) if (m.status === "done" && m.done_at) at(m.done_at.slice(0, 10)).ms.push({ ...m, wish_id: w.id });
  }
  for (const m of J.moments || []) at(m.day).moments.push(m);

  const planned = new Map(), due = new Map(), goals = new Map();
  for (const s of todo) { const p = planOf(s, today); if (p) push(planned, p, s); }
  for (const w of wishes) {
    for (const m of w.milestones || []) if (m.status !== "done" && m.due_day) push(due, m.due_day, { ...m, wish_id: w.id });
    if (w.target_day) push(goals, w.target_day, w);
  }
  // 小步列表：今天 → 之后（按日子）→ 还没安排（最早加的在前）
  const groups = { today: [], later: [], none: [] };
  for (const s of [...todo].reverse()) {
    const p = planOf(s, today);
    (p === today ? groups.today : p ? groups.later : groups.none).push(s);
  }
  groups.later.sort((a, b) => a.scheduled_day.localeCompare(b.scheduled_day));

  const dots = (d) => {
    const e = days.get(d);
    if (!e) return [];
    return [...new Set([...e.steps, ...e.habits, ...e.ms, ...e.moments].map((x) => color(x.wish_id)))].slice(0, 3);
  };
  const count = (d) => { const e = days.get(d); return e ? e.steps.length + e.habits.length + e.ms.length + e.moments.length : 0; };
  return { J, wishes, today, steps, todo, days, planned, due, goals, rest: new Set(J.rest_days || []), groups, wishOf, color, dots, count };
}

// ---------------------------------------------------------------- 日历 ----
export function calendarHTML(M, ui) {
  const { today } = M, sel = ui.day, week = ui.mode === "week";
  const start = week ? weekStart(sel) : weekStart(sel.slice(0, 8) + "01");
  const count = week ? 7 : Math.ceil((diffDays(monthEnd(sel), start) + 1) / 7) * 7;
  const end = addDays(start, 6);
  const yr = (s) => (s.slice(0, 4) !== today.slice(0, 4) ? `<small>${s.slice(0, 4)} 年</small>` : "");
  const title = week
    ? (start.slice(0, 7) === end.slice(0, 7) ? `${+start.slice(5, 7)}月${+start.slice(8)} – ${+end.slice(8)}日` : `${md(start)} – ${md(end)}`) + yr(end)
    : `${+sel.slice(5, 7)}月${yr(sel)}`;
  let cells = "";
  for (let i = 0; i < count; i++) {
    const d = addDays(start, i);
    const plans = M.planned.get(d) || [];
    const rest = M.rest.has(d), due = M.due.get(d), goal = M.goals.get(d), n = M.count(d);
    const marks = M.dots(d).map((c) => `<i style="--dc:${c}"></i>`).join("")
      + (rest ? `<span class="mk rest">${icon("moon")}</span>` : "")
      + (due ? `<span class="mk due">${icon("flag")}</span>` : "")
      + (goal ? `<span class="mk goal">${icon("star")}</span>` : "");
    const label = `${md(d)} ${wk(d)}${d === today ? "，今天" : ""}${n ? `，${n} 条记录` : ""}${plans.length ? `，安排了 ${plans.length} 件小步` : ""}${rest ? "，偷懒日" : ""}`;
    cells += `<div class="pc-cell ${d < today ? "past" : ""} ${d === today ? "today" : ""} ${d === sel ? "sel" : ""} ${!week && d.slice(0, 7) !== sel.slice(0, 7) ? "other" : ""} ${rest ? "rest" : ""}"
      data-cell="${d}" ${d >= today ? `data-drop="${d}"` : ""}>
      <button class="pc-date" data-day="${d}" tabindex="${d === sel ? 0 : -1}" aria-pressed="${d === sel}" ${d === today ? 'aria-current="date"' : ""} aria-label="${label}">
        <b>${+d.slice(8)}</b><span class="pc-marks">${marks}</span>${plans.length ? `<span class="pc-n">${plans.length}</span>` : ""}</button>
      ${week ? `<div class="pc-tags">${plans.map((s) => `<button class="pc-tag ${ui.flash === s.id ? "pop" : ""}" data-drag="${esc(s.id)}" data-tag="${esc(s.id)}"
        style="--tc:${M.color(s.wish_id)}" title="${esc(s.title)}">${esc(s.title)}</button>`).join("")}</div>` : ""}
    </div>`;
  }
  return `<div class="pc-top">
      <div class="tabs pc-mode" role="group" aria-label="日历视图"><button class="${week ? "on" : ""}" data-mode="week" aria-pressed="${week}">周</button><button class="${week ? "" : "on"}" data-mode="month" aria-pressed="${!week}">月</button><span class="ind"></span></div>
      <h3 class="pc-title">${title}</h3>
      <div class="pc-nav"><button class="icon-btn sm" data-period="-1" aria-label="${week ? "上一周" : "上个月"}">${icon("back")}</button>
        <button class="btn btn-quiet btn-sm" data-today ${sel === today ? "disabled" : ""}>今天</button>
        <button class="icon-btn sm" data-period="1" aria-label="${week ? "下一周" : "下个月"}">${icon("arrow")}</button></div>
    </div>
    <div class="pc-wk" aria-hidden="true">${"一二三四五六日".split("").map((x) => `<span>${x}</span>`).join("")}</div>
    <div class="pc-grid ${week ? "is-week" : "is-month"}">${cells}</div>
    <div class="pc-legend"><span><i></i>做过事</span><span class="mk rest">${icon("moon")}偷懒日</span><span class="mk due">${icon("flag")}站点的日子</span><span class="mk goal">${icon("star")}愿望计划实现</span></div>`;
}

export function shiftPeriod(ui, n) {
  if (ui.mode === "week") return addDays(ui.day, 7 * n);
  const m = shiftMonth(ui.day, n);
  const day = Math.min(+ui.day.slice(8), +monthEnd(m).slice(8));
  return m.slice(0, 8) + String(day).padStart(2, "0");
}

// ---------------------------------------------------------------- 当天详情 ----
export function dayHTML(M, day) {
  const { today } = M;
  const e = M.days.get(day) || { steps: [], habits: [], ms: [], moments: [] };
  const plans = M.planned.get(day) || [];
  const due = M.due.get(day) || [], goals = M.goals.get(day) || [];
  const rest = M.rest.has(day);
  const records = e.steps.length + e.habits.length + e.ms.length + e.moments.length;
  const wishT = (id) => esc(M.wishOf(id)?.title || "");
  let html = `<header class="pd-h"><h3>${md(day)}</h3><span>${wk(day)}${day === today ? " · 今天" : ""}</span></header>`;
  if (rest) html += `<div class="j-it rest">${icon("moon")}<span>${day === today ? "今天是偷懒日，安心歇一歇" : "这天给自己放了假"}</span></div>`;
  if (plans.length) {
    html += `<div class="pd-lbl">安排在这天</div><div class="steps pd-plans">${plans.map((s) => `<div class="step pd-plan" style="--tc:${M.color(s.wish_id)}">
      <button class="check" data-done="${esc(s.id)}" aria-label="完成「${esc(s.title)}」">${icon("check")}</button>
      <div class="step-main"><div class="st">${esc(s.title)}</div><div class="sw"><i class="wdot"></i>${wishT(s.wish_id)}</div></div>
      <button class="btn btn-quiet btn-sm" data-plan="${esc(s.id)}">改天</button></div>`).join("")}</div>`;
  }
  if (due.length || goals.length) {
    html += due.map((m) => `<div class="j-it due">${icon("flag")}<span>计划这天到达「${esc(m.title)}」</span></div>`).join("")
      + goals.map((w) => `<div class="j-it goal">${icon("star")}<span>「${esc(w.title)}」计划实现的日子</span></div>`).join("");
  }
  if (records) {
    html += `<div class="pd-lbl">${day === today ? "今天留下的" : "这天留下的"}</div>`;
    html += e.ms.map((m) => `<div class="j-it ms">${icon("flag")}<span>到达站点「${esc(m.title)}」</span></div>`).join("");
    if (e.habits.length) html += `<div class="j-it">${icon("checkc")}<span>习惯打卡：${e.habits.map((x) => esc(x.title)).join("、")}</span></div>`;
    html += e.steps.map((s) => `<div class="j-it">${icon("check")}<span>完成小步「${esc(s.title)}」</span></div>`).join("");
    html += e.moments.map((m) => `<article class="j-m ${m.photo ? "has-photo" : ""}" data-id="${esc(m.id)}" style="--tc:${M.color(m.wish_id)}">
      ${m.photo ? `<img class="j-m-img" src="${esc(photoURL(m.photo, true))}" alt="" loading="lazy">` : ""}
      <p class="j-m-t">${esc(m.text)}</p>
      ${m.feeling ? `<p class="j-m-f">当时的感受：${esc(m.feeling)}</p>` : ""}
      <div class="j-m-meta"><span class="pill"><i class="wdot"></i>${wishT(m.wish_id) || "瞬间"}</span>${m.mood ? `<span class="pill">${esc(m.mood)}</span>` : ""}${m.source === "chat" ? `<span class="pill">${icon("chat")}来自和${aname()}的对话</span>` : m.source === "scene" ? `<span class="pill">${icon("sparkles")}显化你的愿望</span>` : ""}
        <span class="sp"></span><button class="btn btn-quiet btn-sm" data-edit>${icon("edit")}编辑</button><button class="btn btn-quiet btn-sm" data-del>${icon("trash")}删除</button></div>
    </article>`).join("");
  }
  if (!records && !plans.length && !rest && !due.length && !goals.length) {
    const [t, p] = day > today ? ["这一天还空着", "可以先安排一件小步，到时候再看心情。"]
      : day === today ? ["今天还空着", "做完一件小事、打个卡，都会记在这里。"]
        : ["这天没留下记录", "也是好好过的一天。"];
    html += `<div class="pd-empty"><b>${t}</b><p>${p}</p></div>`;
  }
  const acts = [];
  if (day <= today && day >= addDays(today, -365)) acts.push(`<button class="btn btn-ghost btn-sm" data-compose-day="${day}">${icon("plus")}这天记一笔</button>`);
  if (day >= today) acts.push(`<button class="btn btn-ghost btn-sm" data-pick-day="${day}">${icon("calendar")}安排一件小步</button>`);
  return html + (acts.length ? `<div class="pd-gap"></div><div class="pd-acts">${acts.join("")}</div>` : "");
}

// ---------------------------------------------------------------- 安排到哪天 ----
// 一点就存：今天起 7 天，更晚的自己选；也能「先放一放」或者「不安排了」
export function scheduleSheet(step, today, onDone) {
  const cur = planOf(step, today);
  const days = Array.from({ length: 7 }, (_, i) => addDays(today, i));
  const late = cur && cur >= addDays(today, 7) ? cur : "";
  const body = h("div", { class: "ps-sheet", html: `
    <p class="ps-step">${esc(step.title)}</p>
    <div class="ps-days">${days.map((d, i) => `<button type="button" class="ps-day ${d === cur ? "on" : ""}" data-d="${d}" aria-label="${md(d)} ${wk(d)}">
      <small>${i === 0 ? "今天" : i === 1 ? "明天" : wk(d)}</small><b>${+d.slice(8)}</b></button>`).join("")}</div>
    <label class="ps-more">更晚一点<input class="field field-date" type="date" min="${addDays(today, 7)}" max="${addDays(today, 730)}" value="${late}"></label>
    <p class="ps-err" role="alert"></p>` });
  let busy = false;
  const err = body.querySelector(".ps-err");
  const run = async (fn, kind) => {
    if (busy) return;
    busy = true;
    try { const out = await fn(); s.close(); onDone?.(out, kind); }
    catch (e) { busy = false; err.textContent = e.message; }
  };
  const save = (day) => run(() => api.step("schedule", { id: step.id, day }), day);
  body.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => save(b.dataset.d)));
  body.querySelector(".field-date").addEventListener("change", (e) => e.target.value && save(e.target.value));
  const footer = [h("button", { class: "btn btn-quiet", onclick: () => run(() => api.step("drop", { id: step.id }), "drop") }, "先放一放")];
  if (cur) footer.push(h("button", { class: "btn btn-ghost", onclick: () => save("") }, "不安排了"));
  const s = sheet({ title: cur ? `安排在${planLabel(cur, today)}` : "哪天做？", body, sticker: "calendar", footer });
  s.panel.classList.add("j-sheet");
}

// 从日历上的某一天出发：挑一件小步放进来，或者新加一件
export function pickSheet(M, day, { onPick, onAdd }) {
  const list = [...M.groups.none, ...M.groups.today, ...M.groups.later].filter((s) => planOf(s, M.today) !== day);
  const body = h("div", { class: "ps-sheet", html: `
    ${list.length ? `<div class="ps-picks">${list.map((s) => { const p = planOf(s, M.today); return `<button class="ps-pick" data-id="${esc(s.id)}" style="--tc:${M.color(s.wish_id)}">
      <i class="wdot"></i><span>${esc(s.title)}</span><small>${p ? `现在在${planLabel(p, M.today)}` : ""}</small></button>`; }).join("")}</div>`
      : `<p class="muted">还没有待做的小步。</p>`}
    <p class="ps-err" role="alert"></p>` });
  let busy = false;
  body.querySelectorAll("[data-id]").forEach((b) => b.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    try { const out = await api.step("schedule", { id: b.dataset.id, day }); s.close(); onPick?.(out, b.dataset.id); }
    catch (e) { busy = false; body.querySelector(".ps-err").textContent = e.message; }
  }));
  const s = sheet({ title: `放进${planLabel(day, M.today)}`, body, sticker: "calendar",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "算了"),
      h("button", { class: "btn btn-main", onclick: () => { s.close(); onAdd?.(day); } }, "新加一个小步")] });
  s.panel.classList.add("j-sheet");
}

// ---------------------------------------------------------------- 拖进日历 ----
// 只给鼠标：小步那一行、日历里的小步标签都能拖到今天或以后的某一格。手机上点日历按钮选日子。
export function bindDrag(root, { scroller, onDrop, signal }) {
  let p = null, frame = 0, suppress = false;
  const targetAt = (x, y) => document.elementsFromPoint(x, y).map((e) => e.closest?.("[data-drop]")).find((e) => e && root.contains(e));
  const clear = () => root.querySelectorAll(".pc-over").forEach((e) => e.classList.remove("pc-over"));
  const place = () => {
    if (!p?.ghost) return;
    p.ghost.style.transform = `translate(${p.x + 14}px, ${p.y + 10}px)`;
    const t = targetAt(p.x, p.y);
    if (t !== p.target) { clear(); t?.classList.add("pc-over"); p.target = t; }
  };
  const edge = () => {
    if (!p?.ghost) return;
    const r = scroller.getBoundingClientRect();
    if (p.y > r.bottom - 70) scroller.scrollBy(0, 14);
    else if (p.y < r.top + 70) scroller.scrollBy(0, -14);
    place();
    frame = requestAnimationFrame(edge);
  };
  const end = (cancel) => {
    if (!p) return;
    const old = p;
    p = null;
    cancelAnimationFrame(frame);
    clear();
    document.body.classList.remove("pc-dragging");
    old.src.classList.remove("dragging");
    if (!old.ghost) return;
    old.ghost.remove();
    suppress = true;
    setTimeout(() => { suppress = false; }, 0);
    if (!cancel && old.target) onDrop(old.id, old.target.dataset.drop);
  };
  root.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    const src = e.target.closest("[data-drag]");
    const btn = e.target.closest("button, a, input, textarea");
    if (!src || (btn && btn !== src)) return;
    p = { id: src.dataset.drag, src, x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, ghost: null, target: null };
  }, { signal });
  document.addEventListener("pointermove", (e) => {
    if (!p) return;
    p.x = e.clientX; p.y = e.clientY;
    if (!p.ghost && Math.hypot(p.x - p.x0, p.y - p.y0) > 6) {
      const title = p.src.querySelector(".st")?.textContent || p.src.textContent;
      p.ghost = h("div", { class: "pc-ghost" }, title.trim());
      document.body.append(p.ghost);
      document.body.classList.add("pc-dragging");
      p.src.classList.add("dragging");
      frame = requestAnimationFrame(edge);
    }
    if (p.ghost) { e.preventDefault(); place(); }
  }, { signal, passive: false });
  document.addEventListener("pointerup", () => end(false), { signal });
  document.addEventListener("pointercancel", () => end(true), { signal });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") end(true); }, { signal });
  root.addEventListener("click", (e) => { if (suppress) { e.preventDefault(); e.stopPropagation(); } }, { signal, capture: true });
  signal.addEventListener("abort", () => { p?.ghost?.remove(); document.body.classList.remove("pc-dragging"); cancelAnimationFrame(frame); });
}

// 手机上在日历上左右滑：换一周 / 一个月
export function bindSwipe(el, onSwipe, signal) {
  let x0 = 0, y0 = 0, on = false;
  el.addEventListener("touchstart", (e) => { const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; on = true; }, { passive: true, signal });
  el.addEventListener("touchend", (e) => {
    if (!on) return;
    on = false;
    const t = e.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0;
    if (Math.abs(dx) > 56 && Math.abs(dy) < 40) onSwipe(dx < 0 ? 1 : -1);
  }, { passive: true, signal });
}

