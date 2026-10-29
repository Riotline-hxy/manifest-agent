// 例行任务：小光的定时提醒 / 定时消息。面板里列出来（像 Grok 的 routines），可以开关、编辑、新建；
// 网页开着时每 30 秒轻轻问一次服务器，有新提醒就弹一句，并在允许时发浏览器通知。
import { api, get } from "./api.js";
import { state, setData } from "./store.js";
import { esc, icon, toast, sheet, h, confirmSheet } from "./ui.js";

const WEEK = "一二三四五六日";
const localDay = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

export function routinesHTML(d) {
  const ts = d.tasks || [];
  const rs = d.routines || [];
  const row = (t, builtin) => `<div class="rt ${t.enabled ? "" : "off"}" ${builtin ? "" : `data-task="${esc(t.id)}"`}>
      <span class="rt-ic">${icon(builtin ? (t.id === "digest" ? "moon" : t.id === "cheer" ? "leaf" : "letter") : t.kind === "ai" ? "sparkles" : "clock")}</span>
      <span class="rt-main"><b>${esc(t.title)}</b><small>${esc(t.when)}</small></span>
      ${t.fixed ? "" : `<button class="switch ${t.enabled ? "on" : ""}" role="switch" aria-checked="${t.enabled}" aria-label="${esc(t.title)}"
        ${builtin ? `data-routine="${esc(t.id)}"` : `data-toggle="${esc(t.id)}"`}><i></i></button>`}
    </div>`;
  return `<div class="routines">
    <div class="sec-title" style="margin-bottom:6px">例行任务 <span class="more"><button class="rt-add" data-task-new>${icon("plus")}新建</button></span></div>
    <div class="rt-list">${ts.map((t) => row(t, false)).join("")}${rs.map((r) => row(r, true)).join("")}</div>
    ${ts.length ? "" : `<p class="rt-hint">也可以直接跟小光说「明早 8 点提醒我交作业」「每天晚上陪我复盘一下」。</p>`}
  </div>`;
}

export function bindRoutines(body) {
  body.querySelectorAll("[data-toggle]").forEach((b) => b.addEventListener("click", async (e) => {
    e.stopPropagation();
    const on = !b.classList.contains("on");
    b.classList.toggle("on", on);
    try { setData(await api.task(on ? "on" : "off", { id: b.dataset.toggle })); }
    catch (err) { b.classList.toggle("on", !on); toast(err.message, "err"); }
  }));
  body.querySelectorAll("[data-routine]").forEach((b) => b.addEventListener("click", async (e) => {
    e.stopPropagation();
    const on = !b.classList.contains("on");
    b.classList.toggle("on", on);
    try { setData(await api.task("routine", { id: b.dataset.routine, on })); }
    catch (err) { b.classList.toggle("on", !on); toast(err.message, "err"); }
  }));
  body.querySelectorAll("[data-task]").forEach((r) => r.addEventListener("click", () => taskSheet((state.data.tasks || []).find((t) => t.id === r.dataset.task))));
  body.querySelector("[data-task-new]")?.addEventListener("click", () => taskSheet(null));
}

// 新建 / 编辑
export function taskSheet(t) {
  const isNew = !t;
  let kind = t?.kind || "remind";
  let repeat = t?.repeat || "once";
  let days = (t?.days || "").split(",").filter(Boolean).map(Number);
  const now = new Date();
  const hm = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const body = h("div", { class: "task-form" });
  const draw = () => {
    body.innerHTML = `
      <div class="tf-kinds">
        <button type="button" class="tf-kind ${kind === "remind" ? "on" : ""}" data-kind="remind">${icon("clock")}<b>到点提醒我</b><small>小光到点叫你一声</small></button>
        <button type="button" class="tf-kind ${kind === "ai" ? "on" : ""}" data-kind="ai">${icon("sparkles")}<b>到点让小光说点什么</b><small>比如每天早上一句鼓励</small></button>
      </div>
      <label class="lbl">叫什么</label>
      <input class="field" id="tTitle" maxlength="30" value="${esc(t?.title || "")}" placeholder="${kind === "ai" ? "比如：早安鼓励" : "比如：开会、喝水、交作业"}">
      <label class="lbl">${kind === "ai" ? "到点想让小光做什么" : "到点要补一句吗"} <span class="muted">（可选）</span></label>
      <input class="field" id="tMsg" maxlength="120" value="${esc(t?.message || "")}" placeholder="${kind === "ai" ? "比如：结合我最近的事，给我一句今天的鼓励" : "比如：带上电脑和充电器"}">
      <label class="lbl">什么时候</label>
      <div class="j-days">${isNew ? [["once", "一次"], ["daily", "每天"], ["weekdays", "工作日"], ["weekly", "每周"]].map(([k, l]) =>
        `<button type="button" class="chip ${repeat === k ? "on" : ""}" data-rep="${k}">${l}</button>`).join("") : `<span class="muted">${esc(t.when)}</span>`}</div>
      <div class="tf-when">
        ${repeat === "once" && isNew ? `<div class="j-days">${[[5, "5 分钟后"], [30, "半小时后"], [60, "1 小时后"]].map(([m, l]) => `<button type="button" class="chip" data-in="${m}">${l}</button>`).join("")}
            <span class="muted">或</span><input class="field field-date" type="date" id="tDate" value="${localDay(now)}"></div>` : ""}
        ${repeat === "weekly" ? `<div class="j-days">${[1, 2, 3, 4, 5, 6, 7].map((n) => `<button type="button" class="chip ${days.includes(n) ? "on" : ""}" data-day="${n}">周${WEEK[n - 1]}</button>`).join("")}</div>` : ""}
        <input class="field field-date" type="time" id="tTime" value="${t?.time || hm(new Date(now.getTime() + 60 * 60e3))}">
      </div>
      ${isNew ? "" : `<div class="j-archive"><button class="btn btn-quiet btn-sm" id="tDel">${icon("trash")}删掉这个任务</button></div>`}
      <p class="muted j-note">${icon("letter")}到点后会出现在和小光的对话里；网页开着时还会弹一条通知。</p>`;
    body.querySelectorAll("[data-kind]").forEach((b) => b.addEventListener("click", () => { kind = b.dataset.kind; draw(); }));
    body.querySelectorAll("[data-rep]").forEach((b) => b.addEventListener("click", () => { repeat = b.dataset.rep; draw(); }));
    body.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => {
      const n = +b.dataset.day;
      days = days.includes(n) ? days.filter((x) => x !== n) : [...days, n];
      b.classList.toggle("on", days.includes(n));
    }));
    body.querySelectorAll("[data-in]").forEach((b) => b.addEventListener("click", () => save(+b.dataset.in)));
    body.querySelector("#tDel")?.addEventListener("click", async () => {
      s.close();
      if (!(await confirmSheet("删掉这个例行任务？", `「${t.title}」以后不会再响了。`, "删掉", "trash"))) return;
      try { setData(await api.task("delete", { id: t.id })); toast("删掉了"); } catch (e) { toast(e.message, "err"); }
    });
  };
  const save = async (inMinutes) => {
    const title = body.querySelector("#tTitle").value.trim();
    if (!title) { body.querySelector("#tTitle").focus(); return toast("写一下叫什么"); }
    const payload = { title, kind, message: body.querySelector("#tMsg").value, repeat, time: body.querySelector("#tTime").value, days };
    if (repeat === "once" && isNew) {
      if (inMinutes) payload.in_minutes = inMinutes;
      else payload.date = body.querySelector("#tDate")?.value || "";
    }
    try {
      const out = isNew ? await api.task("add", payload) : await api.task("edit", { id: t.id, ...payload });
      setData(out);
      s.close();
      toast(isNew ? `安排好了 · ${out.task?.when || ""}` : "改好了", "", "clock");
      askNotify();
    } catch (e) { toast(e.message, "err"); }
  };
  draw();
  const s = sheet({ title: isNew ? "新的例行任务" : "编辑例行任务", body, sticker: "clock",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: () => save() }, isNew ? "安排上" : "保存")] });
  s.panel.classList.add("j-sheet");
}

// 浏览器通知：只在用户刚安排完任务（有点击）时问一次
export function askNotify() {
  if (!("Notification" in window) || Notification.permission !== "default") return;
  try { Notification.requestPermission(); } catch {}
}

let timer = null;
let seenLatest = "";
export function startPulse(onNew) {
  stopPulse();
  seenLatest = (state.data?.inbox || []).map((i) => i.created_at).sort().pop() || "";
  const tick = async () => {
    if (!state.ready) return;
    try {
      const p = await get("/api/pulse");
      if (p.latest && p.latest > seenLatest) {
        seenLatest = p.latest;
        const data = await api.bootstrap();
        setData(data);
        const item = (data.inbox || []).filter((i) => i.created_at === p.latest)[0] || (data.inbox || []).slice(-1)[0];
        if (item) {
          toast(item.text);
          if ("Notification" in window && Notification.permission === "granted") {
            try { new Notification(data.profile?.agent_name || "小光", { body: item.text, icon: "/favicon.svg" }); } catch {}
          }
          onNew?.(item);
        }
      }
    } catch {}
  };
  timer = setInterval(tick, 30000);
}
export function stopPulse() { if (timer) clearInterval(timer); timer = null; }
