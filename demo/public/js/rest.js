// 偷懒日：一个轻量、没有负担的休息模式。
// 一键选择 → 小光接住 → 用户自己决定：明天继续 / 调整一下计划 / 和小光聊聊天。
// 当天的习惯和小步都暂停，今天安排的小步挪到明天（不偷懒了会挪回来），所有进度保留，什么都不扣。
// 计划页、对话、面板共用这里的流程。
import { api } from "./api.js";
import { state, setData, go, aname } from "./store.js";
import { esc, icon, toast, sheet, h } from "./ui.js";
import { napSVG } from "./town.js";
import { agentMini } from "./ball.js";

const REASONS = ["有点累", "心情不太好", "今天太忙了", "就是想歇歇"];
const CHOICES = [
  ["rest", "今天休息，明天继续", ""],
  ["adjust", "这项任务有点难，想调整一下", "挑一件，调轻一点或先收起"],
  ["chat", "不想做任务，想和{name}聊聊天", "去对话里随便说说"],
];

// 今天安排了几件还没做的小步（偷懒时会挪到明天）
const plannedToday = () => (state.data?.steps || []).filter((s) => s.status === "todo" && s.scheduled_day === state.data?.journey?.today).length;
const backNote = (out) => (out?.rest_plan?.restored ? `醒啦，${out.rest_plan.restored} 个小步回到今天` : "醒啦，我们继续");

export const isResting = () => (state.data?.journey?.rest_days || []).includes(state.data?.journey?.today);
export const restedYesterday = () => {
  const J = state.data?.journey;
  if (!J) return false;
  const y = new Date(new Date(J.today + "T00:00:00Z").getTime() - 864e5).toISOString().slice(0, 10);
  return (J.rest_days || []).includes(y) && !isResting();
};

// 一键偷懒。onDone 在记好之后调用（用于刷新所在页面）
export function openLazy({ onDone } = {}) {
  if (isResting()) return restInfo({ onDone });
  let reason = "", choice = "rest";
  const n = plannedToday();
  const body = h("div", { class: "lazy", html: `
    <div class="lazy-scene">${napSVG()}</div>
    <div class="lazy-say"><span class="lazy-av">${agentMini()}</span>
      <p>收到！今天给自己放个假吧，小镇的灯会一直亮着等你。明天我们再继续。需要我帮你调整一下计划吗？</p></div>
    <div class="lbl">想歇歇的原因 <span class="muted">（可选）</span></div>
    <div class="lazy-reasons">${REASONS.map((r) => `<button type="button" class="chip" data-r="${r}">${r}</button>`).join("")}</div>
    <div class="lazy-choices" role="radiogroup">${CHOICES.map(([k, t, sub]) => `<button type="button" class="lazy-opt ${k === choice ? "on" : ""}" role="radio" aria-checked="${k === choice}" data-c="${k}">
      <i></i><span><b>${t.replace("{name}", aname())}</b><small>${k === "rest" ? (n ? `今天安排的 ${n} 个小步挪到明天` : "什么都不用调整") : sub}</small></span></button>`).join("")}</div>` });
  body.querySelectorAll("[data-r]").forEach((b) => b.addEventListener("click", () => {
    reason = reason === b.dataset.r ? "" : b.dataset.r;
    body.querySelectorAll("[data-r]").forEach((x) => x.classList.toggle("on", x.dataset.r === reason));
  }));
  body.querySelectorAll("[data-c]").forEach((b) => b.addEventListener("click", () => {
    choice = b.dataset.c;
    body.querySelectorAll("[data-c]").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); });
  }));
  const ok = async () => {
    try {
      const out = await api.record("rest", "今天偷个懒" + (reason ? "：" + reason : ""));
      setData(out);
      const moved = out.rest_plan?.postponed || 0;
      s.close();
      onDone?.();
      if (choice === "adjust") adjustSheet({ onDone });
      else if (choice === "chat") {
        state.autoSend = reason ? `今天${reason}，不太想做任务，想和你随便聊聊。` : "今天不太想做任务，想和你随便聊聊。";
        go("chat");
      } else toast(moved ? `好好休息，${moved} 个小步挪到明天了` : "好好休息，明天见", "", "moon");
    } catch (e) { toast(e.message, "err"); }
  };
  const s = sheet({ title: "今天偷个懒", body, sticker: "moon",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "算了，还是做吧"), h("button", { class: "btn btn-main", onclick: ok }, "就这样")] });
  s.panel.classList.add("lazy-sheet");
}

// 已经在偷懒时再点：看看状态，或者取消
function restInfo({ onDone } = {}) {
  const rec = (state.data.records || []).find((r) => r.type === "rest" && r.day === state.data.journey.today);
  const body = h("div", { class: "lazy", html: `
    <div class="lazy-scene">${napSVG()}</div>
    <p class="lazy-now">今天是偷懒日${rec && rec.text.includes("：") ? `（${esc(rec.text.split("：")[1])}）` : ""}。习惯和小步都先暂停，今天安排的挪到了明天，什么进度都不会少。</p>` });
  const s = sheet({ title: "今天在偷懒", body, sticker: "moon",
    footer: [
      h("button", { class: "btn btn-ghost", onclick: async () => {
        try { const out = await api.rest(true); setData(out); s.close(); onDone?.(); toast(backNote(out), "", "sun"); } catch (e) { toast(e.message, "err"); }
      } }, "不偷懒了"),
      h("button", { class: "btn btn-ghost", onclick: () => { s.close(); adjustSheet({ onDone }); } }, "调整一下计划"),
      h("button", { class: "btn btn-main", onclick: () => s.close() }, "继续睡"),
    ] });
  s.panel.classList.add("lazy-sheet");
}

// 哪件事有点难：习惯可以调轻一档 / 先收起 / 让小光拆小；小步可以先放一放 / 让小光拆小
export function adjustSheet({ onDone } = {}) {
  const body = h("div", { class: "adjust" });
  const draw = () => {
    const J = state.data.journey || {};
    const groups = (J.wishes || []).map((w) => ({
      w, habits: w.habits || [],
      steps: (state.data.steps || []).filter((x) => x.status === "todo" && x.wish_id === w.id),
    })).filter((g) => g.habits.length || g.steps.length);
    body.innerHTML = groups.length ? `<p class="muted">挑一件觉得有点难的，换个轻一点的做法。</p>` + groups.map((g) => `
      <div class="adj-g"><div class="lbl">${esc(g.w.title)}</div>
        ${g.habits.map((x) => `<div class="adj-it"><div><b>${esc(x.title)}</b><small>习惯 · ${esc(x.freq_text)}</small></div>
          <div class="adj-acts">${x.freq === "weekly" && +x.per_week <= 1 ? "" : `<button class="btn btn-sm btn-ghost" data-ease="${esc(x.id)}">调轻一档</button>`}
            <button class="btn btn-sm btn-quiet" data-pause="${esc(x.id)}">先收起</button>
            <button class="btn btn-sm btn-quiet" data-ask="${esc(x.title)}" data-kind="habit">让${aname()}拆小</button></div></div>`).join("")}
        ${g.steps.map((x) => `<div class="adj-it"><div><b>${esc(x.title)}</b><small>小步</small></div>
          <div class="adj-acts"><button class="btn btn-sm btn-ghost" data-drop="${esc(x.id)}">先放一放</button>
            <button class="btn btn-sm btn-quiet" data-ask="${esc(x.title)}" data-kind="step">让${aname()}拆小</button></div></div>`).join("")}
      </div>`).join("") : `<p class="muted">现在计划里没有要做的事，好好休息就行。</p>`;
    const act = (fn, msg) => async (e) => {
      e.currentTarget.disabled = true;
      try { const out = await fn(); setData(out); toast(typeof msg === "function" ? msg(out) : msg, "", "leaf"); draw(); onDone?.(); }
      catch (err) { toast(err.message, "err"); draw(); }
    };
    body.querySelectorAll("[data-ease]").forEach((b) => b.addEventListener("click", act(() => api.habit("ease", { id: b.dataset.ease }), (o) => `调成${o.eased}了`)));
    body.querySelectorAll("[data-pause]").forEach((b) => b.addEventListener("click", act(() => api.habit("edit", { id: b.dataset.pause, archived: true }), "先收起了，打卡记录都在")));
    body.querySelectorAll("[data-drop]").forEach((b) => b.addEventListener("click", act(() => api.step("drop", { id: b.dataset.drop }), "先放一放，想做时随时放回来")));
    body.querySelectorAll("[data-ask]").forEach((b) => b.addEventListener("click", () => {
      s.close();
      state.autoSend = b.dataset.kind === "habit"
        ? `「${b.dataset.ask}」最近有点难坚持，帮我把它调整得更容易开始一点。`
        : `「${b.dataset.ask}」这一步有点难，帮我拆成更小的一步。`;
      go("chat");
    }));
  };
  draw();
  const s = sheet({ title: "调整一下计划", body, sticker: "leaf",
    footer: [h("button", { class: "btn btn-main", onclick: () => s.close() }, "好了")] });
  s.panel.classList.add("lazy-sheet");
}

// 偷懒日：夜里亮着灯的小屋 + 调整 / 聊聊 / 不偷懒了（计划页的「小步」卡片顶上）；平时的那句提醒现在不用了
export function restBannerHTML() {
  if (isResting()) {
    const rec = (state.data.records || []).find((r) => r.type === "rest" && r.day === state.data.journey.today);
    const why = rec && rec.text.includes("：") ? rec.text.split("：")[1] : "";
    return `<div class="rest-on">
      <div class="rest-pet">${napSVG()}</div>
      <div class="rest-txt"><b>今天是偷懒日${why ? ` · ${esc(why)}` : ""}</b><p>习惯和小步都先暂停，今天安排的挪到了明天。经验、金币、小镇都不会少。</p>
        <div class="rest-acts"><button class="btn btn-sm btn-ghost" data-rest-adjust>${icon("leaf")}调整一下计划</button>
          <button class="btn btn-sm btn-ghost" data-rest-chat>${icon("chat")}和${aname()}聊聊</button>
          <button class="btn btn-sm btn-quiet" data-rest-off>不偷懒了</button></div></div></div>`;
  }
  return `<div class="rest-off">${restedYesterday() ? `<span>昨天好好歇了一天。今天从哪件小事开始？</span>` : `<span>不用每一天都拼尽全力。</span>`}
    <button class="btn btn-sm btn-ghost" data-lazy>${icon("moon")}今天偷个懒</button></div>`;
}

export function bindRestBanner(root, rerender) {
  root.querySelector("[data-lazy]")?.addEventListener("click", () => openLazy({ onDone: rerender }));
  root.querySelector("[data-rest-adjust]")?.addEventListener("click", () => adjustSheet({ onDone: rerender }));
  root.querySelector("[data-rest-chat]")?.addEventListener("click", () => { state.autoSend = "今天在偷懒，不太想做任务，想和你随便聊聊。"; go("chat"); });
  root.querySelector("[data-rest-off]")?.addEventListener("click", async () => {
    try { const out = await api.rest(true); setData(out); toast(backNote(out), "", "sun"); rerender(); } catch (e) { toast(e.message, "err"); }
  });
}
