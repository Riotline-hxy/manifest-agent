// 蜕变计划 = 成长轨迹看板（依据《显化成长轨迹看板设计文档》）。
// 每个愿望一张看板：左下「现在的我」，右上「向往的我」，中间一条固定的柔和曲线。
// 曲线是时间，不是进度：所选区间的日子从左到右排开，只有真的留下过瞬间的日子才亮。
// 没记录的日子什么都不画——没有空格子、没有断签、不清零。
import { api } from "../api.js";
import { state, setData, xpNote } from "../store.js";
import { esc, toast, confirmSheet, icon, tile, sheet, h } from "../ui.js";
import { flyXP, burstAt } from "../fx.js";
import { CATS, catOf, MOODS, CURVE, VIEW_W, VIEW_H, T0, T1, visionSVG, figureSVG, playFx } from "../journey.js";

const RANGES = [7, 15, 30, 60, 90];
const BUCKET = { 7: 1, 15: 1, 30: 1, 60: 2, 90: 3 };   // 长区间把相邻日子合成一个点，点开再展开
const WEEK = "日一二三四五六";
const EMPTY_LINE = "这段时间还没有留下记录。你可以从今天开始，也可以先看看之前的自己。";

// ---- 日期：一律按服务端给的「今天」（用户本地日）做日历运算，不受浏览器时区影响 ----
const D = (s) => new Date(s + "T00:00:00Z");
const K = (d) => d.toISOString().slice(0, 10);
const addDays = (s, n) => K(new Date(D(s).getTime() + n * 864e5));
const diffDays = (a, b) => Math.round((D(a) - D(b)) / 864e5);
const md = (s) => `${+s.slice(5, 7)}月${+s.slice(8, 10)}日`;
const wk = (s) => "周" + WEEK[D(s).getUTCDay()];

// 曲线上的点位（viewBox 坐标 → 百分比）
let _path;
function pointAt(t) {
  if (!_path) {
    _path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    _path.setAttribute("d", CURVE);
  }
  const p = _path.getPointAtLength(_path.getTotalLength() * t);
  return { x: (p.x / VIEW_W) * 100, y: (p.y / VIEW_H) * 100 };
}

function rangeDays() {
  return RANGES.includes(state.planRange) ? state.planRange : 30;
}

export function renderPlan(root, { fresh = "" } = {}) {
  const J = state.data.journey || { wishes: [], moments: [], insights: {}, categories: [] };
  const wishes = J.wishes || [];
  if (!wishes.length) return renderStart(root, J);
  const w = wishes.find((x) => x.id === J.current) || wishes[0];
  const cat = catOf(w.category);
  const days = rangeDays();
  const today = J.today;
  const start = addDays(today, -(days - 1));
  const mine = (J.moments || []).filter((m) => m.wish_id === w.id);
  const inRange = mine.filter((m) => m.day >= start && m.day <= today);
  const byDay = new Map();
  for (const m of [...inRange].sort((a, b) => (a.created_at < b.created_at ? -1 : 1))) {
    if (!byDay.has(m.day)) byDay.set(m.day, []);
    byDay.get(m.day).push(m);
  }
  // 聚合：从今天往回每 k 天一组，点画在组里最近的那一天
  const k = BUCKET[days];
  const groups = new Map();
  for (const day of byDay.keys()) {
    const g = Math.floor(diffDays(today, day) / k);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(day);
  }
  const dots = [...groups.values()].map((ds) => {
    ds.sort();
    const last = ds[ds.length - 1];
    const i = days - 1 - diffDays(today, last);
    const t = days === 1 ? T1 : T0 + ((T1 - T0) * i) / (days - 1);
    const n = ds.reduce((s, d) => s + byDay.get(d).length, 0);
    return { days: ds, last, t, n, ...pointAt(t) };
  }).sort((a, b) => a.t - b.t);
  const hasToday = byDay.has(today) || dots.some((d) => T1 - d.t < 0.05);   // 太挤时不画「+ 今天」，下方按钮一样能记
  const lastEver = mine[0]?.day || "";
  const labels = [[T0, md(start)], [(T0 + T1) / 2, md(addDays(start, Math.floor((days - 1) / 2)))], [T1, "今天"]];
  const insight = (J.insights || {})[w.id];
  const steps = (state.data.steps || []).filter((s) => s.wish_id === w.id || (!s.wish_id && w.id === wishes[0].id));
  const todo = steps.filter((s) => s.status === "todo");
  const doneN = steps.filter((s) => s.status === "done").length;

  root.innerHTML = `
    <div class="view-inner wide plan journey" style="--jc:${cat.color}">
      <div class="page-head"><div><h1>蜕变计划</h1><p>每个愿望一张轨迹：从现在的我，走向想成为的自己</p></div></div>

      <div class="wish-tabs" role="tablist" aria-label="切换愿望">
        ${wishes.map((x) => `<button class="wish-tab ${x.id === w.id ? "on" : ""}" role="tab" aria-selected="${x.id === w.id}" data-wish="${esc(x.id)}" style="--jc:${catOf(x.category).color}">
          ${tile(catOf(x.category).icon, catOf(x.category).color, 26)}<span>${esc(x.title)}</span>${x.count ? `<small>${x.count}</small>` : ""}</button>`).join("")}
        ${wishes.length < 6 ? `<button class="wish-tab add" id="newWish">${icon("plus")}<span>新的愿望</span></button>` : ""}
      </div>

      <section class="j-board card cat-${esc(w.category)}">
        <div class="j-top">
          <div class="tabs j-range" role="tablist" aria-label="时间范围">${RANGES.map((r) => `<button class="${r === days ? "on" : ""}" data-range="${r}">${r} 天</button>`).join("")}<span class="ind"></span></div>
          <div class="j-sum">${inRange.length ? `${md(start)} – 今天 · <b>${byDay.size}</b> 天留下了 <b>${inRange.length}</b> 个瞬间` : `${md(start)} – 今天`}</div>
        </div>
        <div class="j-stage">
          <svg class="j-back" viewBox="0 0 ${VIEW_W} ${VIEW_H}" preserveAspectRatio="none" aria-hidden="true">${backdrop(w.category)}
            <path class="curve-base" d="${CURVE}"/><path class="curve" d="${CURVE}"/><path class="curve-lit" d="${CURVE}"/></svg>
          ${labels.map(([t, l], i) => { const p = pointAt(t); return `<span class="j-date ${i === 2 ? "end" : ""}" style="left:${p.x}%;top:${p.y}%">${l}</span>`; }).join("")}

          <button class="j-now" id="editNow" title="改一改现在的我">
            <span class="j-cap"><small>现在的我</small><b>${esc(w.now_text || "用一句话说说现在的自己")}</b></span>
            <svg class="j-fig" viewBox="0 0 200 110" aria-hidden="true">${figureSVG()}</svg>
          </button>
          <button class="j-vision" id="editVision" title="调整向往的样子">
            <span class="j-cap"><small>向往的我</small><b>${esc(w.vision_text || cat.label)}</b></span>
            <span class="j-orb">${visionSVG(w.category)}</span>
          </button>

          ${dots.map((d) => `<button class="j-dot ${d.days.includes(fresh) ? "fresh" : ""} ${d.n > 1 ? "multi" : ""}" style="left:${d.x}%;top:${d.y}%"
              data-days="${d.days.join(",")}" data-t="${d.t}"
              aria-label="${md(d.days[0])}${d.days.length > 1 ? ` 到 ${md(d.last)}` : ""}，${d.n} 个瞬间"
              title="${esc(md(d.last) + "：" + byDay.get(d.last)[0].text.slice(0, 24))}"><i></i>${d.n > 1 ? `<em>${d.n}</em>` : ""}</button>`).join("")}
          ${hasToday ? "" : (() => { const p = pointAt(T1); return `<button class="j-today" id="todayDot" style="left:${p.x}%;top:${p.y}%" aria-label="在今天留下一个瞬间">${icon("plus")}</button>`; })()}

          ${inRange.length ? "" : `<div class="j-empty"><p>${EMPTY_LINE}</p>
            <div class="row"><button class="btn btn-main btn-sm" data-compose>${icon("plus")}从今天开始</button>
            ${lastEver && lastEver < start ? `<button class="btn btn-ghost btn-sm" id="seePast">看看之前的自己</button>` : ""}</div></div>`}
          <div class="j-fx" aria-hidden="true"></div>
        </div>
        <div class="j-foot">
          <span class="j-legend"><i></i>亮点是你真实留下的瞬间 · 曲线代表时间，不是完成度${k > 1 ? ` · 相邻 ${k} 天合成一个点` : ""}</span>
          <div class="row">
            <button class="btn btn-ghost btn-sm" id="review">${icon("eye")}阶段回望</button>
            <button class="btn btn-ghost btn-sm" id="editWish">${icon("edit")}编辑愿望</button>
            <button class="btn btn-main" data-compose>${icon("plus")}留下一个瞬间</button>
          </div>
        </div>
      </section>

      <div class="j-cols">
        <section class="card j-insight">
          <div class="sec-title">${icon("sparkles")}小光的小发现 <span class="pill">推测，不是结论</span></div>
          ${insight ? `<p class="j-guess">${esc(insight.text)}</p>
            ${(insight.basis || []).length ? `<div class="j-basis">依据：${insight.basis.map((id) => { const m = mine.find((x) => x.id === id); return m ? `<button data-open-day="${m.day}">${md(m.day)}</button>` : ""; }).join("")}</div>` : ""}
            <div class="j-answers">${[["yes", "像我"], ["partly", "有一部分"], ["no", "不太像"], ["skip", "跳过"]].map(([a, l]) =>
              `<button class="btn btn-sm ${a === "yes" ? "btn-main" : "btn-ghost"}" data-answer="${a}">${l}</button>`).join("")}</div>
            <small class="muted">选「像我」或「有一部分」，小光才会把它当作对你的了解记下来；不确认就不会写成事实。</small>`
          : `<p class="muted">${mine.length >= 4 ? "小光可以读一读你留下的瞬间，提一个小小的观察或问题。" : `再留 ${4 - mine.length} 个瞬间，小光就能试着说说它看到的东西。`}</p>
            <button class="btn btn-ghost btn-sm" id="askInsight" ${mine.length >= 4 ? "" : "disabled"}>${icon("eye")}让小光看看</button>`}
        </section>

        <section class="card j-steps">
          <div class="sec-title">${icon("flag")}靠近它的小步 <span class="more">${todo.length} 件待做 · 完成 ${doneN}</span></div>
          <div class="steps">${todo.slice(0, 5).map((s, i) => `<div class="step" style="--i:${i}">
            <button class="check" data-done="${esc(s.id)}" aria-label="完成">${icon("check")}</button>
            <div class="step-main"><div class="st">${esc(s.title)}</div>${s.why ? `<div class="sw">${esc(s.why)}</div>` : ""}</div>
            <button class="btn btn-quiet btn-sm" data-drop="${esc(s.id)}">先放一放</button></div>`).join("")
            || `<p class="muted">还没有小步。可以加一条 5 分钟内能开始的事，或者在对话里让小光帮你想。</p>`}</div>
          <div class="add-row">
            <input class="field" id="newStep" placeholder="加一条 5 分钟内能开始的小步…" maxlength="40">
            <button class="btn btn-main" id="addStep" aria-label="加入">${icon("plus")}</button>
          </div>
        </section>
      </div>

      <section class="section">
        <details class="fold card j-list" ${state.planListOpen ? "open" : ""}><summary>${icon("list")}按日期看这段时间的记录 <span class="muted">· ${inRange.length} 条</span></summary>
          ${[...byDay.keys()].sort().reverse().map((day) => `<div class="j-li"><button class="j-li-day" data-open-day="${day}"><b>${md(day)}</b><small>${wk(day)}</small></button>
            <div>${byDay.get(day).map((m) => `<p>${esc(m.text)}${m.feeling ? `<span class="muted"> · ${esc(m.feeling)}</span>` : ""}</p>`).join("")}</div></div>`).join("")
            || `<p class="muted" style="padding:6px 4px">${EMPTY_LINE}</p>`}
        </details>
      </section>
    </div>`;

  // ---- 交互 ----
  const board = root.querySelector(".j-board");
  const tabs = root.querySelector(".j-range");
  const placeInd = () => {
    const on = tabs.querySelector("button.on");
    Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
  };
  requestAnimationFrame(placeInd);
  tabs.querySelectorAll("[data-range]").forEach((b) => b.addEventListener("click", () => {
    state.planRange = +b.dataset.range;
    renderPlan(root);
  }));
  root.querySelector("#seePast")?.addEventListener("click", () => {
    const back = diffDays(today, lastEver) + 1;
    state.planRange = RANGES.find((r) => r >= back) || 90;
    renderPlan(root);
  });
  root.querySelectorAll("[data-wish]").forEach((b) => b.addEventListener("click", async () => {
    if (b.dataset.wish === w.id) return;
    try { setData(await api.wish("select", { id: b.dataset.wish })); renderPlan(root); }
    catch (e) { toast(e.message, "err"); }
  }));
  root.querySelector("#newWish")?.addEventListener("click", () => wishSheet(root, null, J));
  root.querySelector("#editWish").addEventListener("click", () => wishSheet(root, w, J));
  root.querySelector("#editNow").addEventListener("click", () => wishSheet(root, w, J, "now_text"));
  root.querySelector("#editVision").addEventListener("click", () => wishSheet(root, w, J, "vision_text"));
  root.querySelectorAll("[data-compose]").forEach((b) => b.addEventListener("click", () => composeSheet(root, w)));
  root.querySelector("#todayDot")?.addEventListener("click", () => composeSheet(root, w));
  root.querySelector("#review").addEventListener("click", () => reviewSheet(w, days));
  root.querySelector(".j-list").addEventListener("toggle", (e) => { state.planListOpen = e.target.open; });

  const openDots = (dot) => {
    const ds = dot.dataset.days.split(",");
    const fx = cat.fx;
    const all = [...board.querySelectorAll(".j-dot")];
    const idx = all.indexOf(dot);
    dot.classList.remove("hit"); void dot.offsetWidth; dot.classList.add("hit");
    playFx(fx, board, dot, { frac: +dot.dataset.t, neighbors: [all[idx - 1], all[idx + 1]].filter(Boolean) });
    setTimeout(() => dayCard(root, w, ds, mine), reduced() ? 0 : 520);
  };
  root.querySelectorAll(".j-dot").forEach((b) => b.addEventListener("click", () => openDots(b)));
  root.querySelectorAll("[data-open-day]").forEach((b) => b.addEventListener("click", () => {
    const dot = [...board.querySelectorAll(".j-dot")].find((x) => x.dataset.days.split(",").includes(b.dataset.openDay));
    if (dot) { dot.scrollIntoView({ block: "center", behavior: "smooth" }); openDots(dot); }
    else dayCard(root, w, [b.dataset.openDay], mine);
  }));

  root.querySelector("#askInsight")?.addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    e.currentTarget.innerHTML = `${icon("eye")}小光在读…`;
    try {
      const out = await api.insight({ id: w.id });
      setData(out);
      if (!out.insight) toast(out.reason || "这次没看出特别的地方");
      renderPlan(root);
    } catch (err) { toast(err.message, "err"); renderPlan(root); }
  });
  root.querySelectorAll("[data-answer]").forEach((b) => b.addEventListener("click", async () => {
    try {
      const out = await api.insight({ insight_id: insight.id, answer: b.dataset.answer });
      setData(out);
      toast({ yes: "记下了，这是你认可的一点", partly: "记下了，标着「只有一部分像」", no: "好，这条不算数", skip: "先跳过" }[b.dataset.answer], "", "sparkles");
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  }));

  root.querySelectorAll("[data-done]").forEach((b) => b.addEventListener("click", async () => {
    const card = b.closest(".step");
    card.classList.add("checking");
    try {
      const out = await api.step("done", { id: b.dataset.done });
      burstAt(b, 30);
      if (out.xp?.amount) flyXP(b, out.xp.amount); else toast(xpNote(out.xp) || "完成了");
      setTimeout(() => { setData(out); renderPlan(root); }, 480);
    } catch (e) { card.classList.remove("checking"); toast(e.message, "err"); }
  }));
  root.querySelectorAll("[data-drop]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmSheet("先放一放？", "它不会消失，也不算失败。想做的时候随时放回来。", "放一放"))) return;
    setData(await api.step("drop", { id: b.dataset.drop }));
    renderPlan(root);
  }));
  const add = async () => {
    const inp = root.querySelector("#newStep");
    if (!inp.value.trim()) return inp.focus();
    try { setData(await api.step("add", { title: inp.value.trim(), wish_id: w.id })); toast("加进计划了", "", "flag"); renderPlan(root); }
    catch (e) { toast(e.message, "err"); }
  };
  root.querySelector("#addStep").addEventListener("click", add);
  root.querySelector("#newStep").addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });

  if (fresh) {
    const dot = board.querySelector(".j-dot.fresh");
    if (dot) setTimeout(() => playFx(cat.fx, board, dot, { frac: +dot.dataset.t, neighbors: [] }), 350);
  }
}

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// 每类一层很淡的背景纹理（文档 §四：主题靠少量图形区分，不叠加颜色）
function backdrop(c) {
  if (c === "calm") return `<g class="bd bd-calm">${[0, 1, 2, 3].map((i) =>
    `<path d="M-40,${410 + i * 30} q60,-14 120,0 t120,0 t120,0 t120,0 t120,0 t120,0 t120,0 t120,0 t120,0" style="--i:${i}"/>`).join("")}</g>`;
  if (c === "confidence") return `<g class="bd bd-stars">${[[120, 90], [260, 60], [420, 130], [560, 70], [700, 110], [330, 200], [930, 330], [610, 420]].map(([x, y], i) =>
    `<circle cx="${x}" cy="${y}" r="${i % 3 ? 2.5 : 3.5}" style="--i:${i}"/>`).join("")}</g>`;
  if (c === "wealth") return `<g class="bd bd-gold">${[[200, 120], [380, 90], [640, 140], [900, 420], [520, 450], [300, 250]].map(([x, y], i) =>
    `<circle cx="${x}" cy="${y}" r="3" style="--i:${i}"/>`).join("")}</g>`;
  if (c === "relation") return `<g class="bd bd-web"><path d="M100,150 L260,90 L420,170 L600,100 L760,160"/><path d="M180,300 L380,260 L560,330"/></g>`;
  if (c === "freedom") return `<g class="bd bd-beam"><path d="M1000,0 L620,520 L780,520 L1000,120z"/><path d="M1000,160 L860,520 L940,520 L1000,300z"/></g>`;
  if (c === "body") return `<g class="bd bd-hill"><path d="M-20,500 Q260,380 520,470 T1040,430 L1040,540 L-20,540z"/></g>`;
  return `<g class="bd bd-glow"><circle cx="880" cy="110" r="160"/></g>`;
}

// ---------------------------------------------------------------- 日期卡片 ----
function dayCard(root, w, days, mine) {
  const list = mine.filter((m) => days.includes(m.day)).sort((a, b) => (a.day + a.created_at < b.day + b.created_at ? -1 : 1));
  const body = h("div", { class: "j-day" });
  const draw = () => {
    body.innerHTML = list.length ? list.map((m, i) => `
      ${days.length > 1 && (i === 0 || list[i - 1].day !== m.day) ? `<div class="j-day-h">${md(m.day)} · ${wk(m.day)}</div>` : ""}
      <article class="j-m" data-id="${esc(m.id)}">
        <p class="j-m-t">${esc(m.text)}</p>
        ${m.feeling ? `<p class="j-m-f">当时的感受：${esc(m.feeling)}</p>` : ""}
        <div class="j-m-meta">${m.mood ? `<span class="pill">${esc(m.mood)}</span>` : ""}${m.source === "chat" ? `<span class="pill">${icon("chat")}来自和小光的对话</span>` : ""}
          <span class="sp"></span><button class="btn btn-quiet btn-sm" data-edit>${icon("edit")}编辑</button><button class="btn btn-quiet btn-sm" data-del>${icon("trash")}删除</button></div>
      </article>`).join("") : `<p class="muted">这一天的记录都删掉了。</p>`;
    body.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      const art = b.closest(".j-m");
      const m = list.find((x) => x.id === art.dataset.id);
      art.innerHTML = `<textarea class="field" rows="3" maxlength="300">${esc(m.text)}</textarea>
        <input class="field" placeholder="当时的感受（可选）" maxlength="80" value="${esc(m.feeling || "")}">
        <div class="row end"><button class="btn btn-ghost btn-sm" data-cancel>取消</button><button class="btn btn-main btn-sm" data-save>保存</button></div>`;
      art.querySelector("textarea").focus();
      art.querySelector("[data-cancel]").addEventListener("click", draw);
      art.querySelector("[data-save]").addEventListener("click", async () => {
        try {
          const out = await api.moment("edit", { id: m.id, text: art.querySelector("textarea").value, feeling: art.querySelector("input").value });
          setData(out);
          Object.assign(m, (out.journey.moments || []).find((x) => x.id === m.id) || {});
          draw(); renderPlan(root);
        } catch (e) { toast(e.message, "err"); }
      });
    }));
    body.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      const id = b.closest(".j-m").dataset.id;
      if (!(await confirmSheet("删掉这条记录？", "删掉后它会从轨迹和回望里一起消失。这一天如果没有别的记录，亮点也会消失。", "删掉", "trash"))) return;
      try {
        setData(await api.moment("delete", { id }));
        list.splice(list.findIndex((x) => x.id === id), 1);
        renderPlan(root);
        if (!list.length) s.close(); else draw();
      } catch (e) { toast(e.message, "err"); }
    }));
  };
  draw();
  const title = days.length > 1 ? `${md(days[0])} – ${md(days[days.length - 1])}` : `${md(days[0])} · ${wk(days[0])}`;
  const s = sheet({ title, body, sticker: catOf(w.category).icon,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "回到轨迹"),
      h("button", { class: "btn btn-main", onclick: () => { s.close(); composeSheet(root, w, days[days.length - 1]); } }, "这天再写一条")] });
  s.panel.classList.add("j-sheet");
}

// ---------------------------------------------------------------- 留下一个瞬间 ----
function composeSheet(root, w, day = "") {
  const cat = catOf(w.category);
  const today = state.data.journey.today;
  const opts = [[today, "今天"], [addDays(today, -1), "昨天"], [addDays(today, -2), "前天"]];
  let pickDay = day || today;
  let mood = "";
  const body = h("div", { class: "j-compose", html: `
    <div class="j-prompts">${cat.prompts.map((p) => `<button class="chip" type="button">${esc(p)}</button>`).join("")}</div>
    <label class="lbl">发生了什么</label>
    <textarea class="field" id="mText" rows="4" maxlength="300" placeholder="一两句就好，比如：今天开完会有些紧张，我给自己留了十分钟，安静地喝了一杯茶。"></textarea>
    <label class="lbl">当时的感受 <span class="muted">（可选）</span></label>
    <input class="field" id="mFeel" maxlength="80" placeholder="比如：慢慢放松了一些">
    <div class="j-moods">${MOODS.map((m) => `<button class="chip" type="button" data-mood="${m}">${m}</button>`).join("")}</div>
    <label class="lbl">哪一天</label>
    <div class="j-days">${opts.map(([d, l]) => `<button class="chip ${d === pickDay ? "on" : ""}" type="button" data-day="${d}">${l}</button>`).join("")}
      <input class="field field-date" type="date" max="${today}" min="${addDays(today, -365)}" value="${opts.some(([d]) => d === pickDay) ? "" : pickDay}" aria-label="选一个更早的日期"></div>
    <p class="muted j-note">${icon("shield")}只有你写下的才会出现在轨迹上；小光不会替你补记。</p>` });
  const ta = body.querySelector("#mText");
  body.querySelectorAll(".j-prompts .chip").forEach((b) => b.addEventListener("click", () => {
    ta.placeholder = b.textContent;
    body.querySelectorAll(".j-prompts .chip").forEach((x) => x.classList.toggle("on", x === b));
    ta.focus();
  }));
  body.querySelectorAll("[data-mood]").forEach((b) => b.addEventListener("click", () => {
    mood = mood === b.dataset.mood ? "" : b.dataset.mood;
    body.querySelectorAll("[data-mood]").forEach((x) => x.classList.toggle("on", x.dataset.mood === mood));
  }));
  const dateIn = body.querySelector(".field-date");
  body.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => {
    pickDay = b.dataset.day; dateIn.value = "";
    body.querySelectorAll("[data-day]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  dateIn.addEventListener("change", () => {
    if (!dateIn.value) return;
    pickDay = dateIn.value;
    body.querySelectorAll("[data-day]").forEach((x) => x.classList.remove("on"));
  });
  const save = async () => {
    if (!ta.value.trim()) { ta.focus(); return toast("写一句发生了什么就好"); }
    btn.disabled = true;
    try {
      const out = await api.moment("add", { wish_id: w.id, text: ta.value, feeling: body.querySelector("#mFeel").value, mood, day: pickDay });
      s.close();
      setData(out);
      // 选的日子不在当前区间里时，自动放宽到能看见它的区间
      const back = diffDays(today, pickDay) + 1;
      if (back > rangeDays()) state.planRange = RANGES.find((r) => r >= back) || 90;
      renderPlan(root, { fresh: pickDay });
      const dot = root.querySelector(".j-dot.fresh");
      if (out.xp?.amount && dot) setTimeout(() => flyXP(dot, out.xp.amount), 500);
      else toast(xpNote(out.xp) ? `留下了 · ${xpNote(out.xp)}` : "留下了", "", "sparkles");
    } catch (e) { btn.disabled = false; toast(e.message, "err"); }
  };
  const btn = h("button", { class: "btn btn-main", onclick: save }, "留在轨迹上");
  const s = sheet({ title: `留下一个瞬间 · ${w.title}`, body, sticker: cat.icon,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "先不写"), btn] });
  s.panel.classList.add("j-sheet");
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); });
  setTimeout(() => ta.focus(), 60);
}

// ---------------------------------------------------------------- 阶段回望 ----
async function reviewSheet(w, days) {
  const body = h("div", { class: "j-review", html: `<p class="muted">正在翻这 ${days} 天的记录…</p>` });
  const s = sheet({ title: `阶段回望 · 过去 ${days} 天`, body, sticker: "eye" });
  s.panel.classList.add("j-sheet");
  const draw = (r) => {
    body.innerHTML = `
      <p class="j-r-line">${esc(r.line)}</p>
      ${r.count ? `<div class="j-r-stats">
          <div><span class="num">${r.count}</span><small>个瞬间</small></div>
          <div><span class="num">${r.active_days}</span><small>天有记录</small></div>
          ${r.top ? `<div><span class="num">${r.top.count}</span><small>次提到「${esc(r.top.word)}」</small></div>` : ""}
        </div>
        <div class="j-r-quotes">${r.quotes.map((q) => `<div class="j-r-q"><small>${md(q.day)}</small><p>${esc(q.text)}</p>${q.feeling ? `<p class="muted">感受：${esc(q.feeling)}</p>` : ""}</div>`).join("")}</div>
        <p class="muted j-note">${icon("shield")}这里的数字只来自你在这 ${days} 天里真实留下的记录。</p>
        <label class="lbl">你觉得这段时间有什么变化？</label>
        <textarea class="field" rows="3" maxlength="300" placeholder="写给自己的一两句"></textarea>
        <div class="row end"><button class="btn btn-main btn-sm" data-save>留给自己</button></div>` : ""}
      ${r.reflections.length ? `<div class="j-r-past"><div class="lbl">之前写下的回望</div>${r.reflections.map((x) =>
        `<p><small>${md(x.created_at.slice(0, 10))} · ${x.days} 天</small>${esc(x.text)}</p>`).join("")}</div>` : ""}`;
    body.querySelector("[data-save]")?.addEventListener("click", async () => {
      const ta = body.querySelector("textarea");
      if (!ta.value.trim()) return ta.focus();
      try { draw(await api.wishReflect(w.id, days, ta.value)); toast("收好了", "", "heart"); }
      catch (e) { toast(e.message, "err"); }
    });
  };
  try { draw(await api.wishReview(w.id, days)); }
  catch (e) { body.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

// ---------------------------------------------------------------- 愿望：新建 / 编辑 ----
function catGrid(sel) {
  return `<div class="j-cats">${Object.entries(CATS).map(([id, c]) => `<button type="button" class="j-cat ${id === sel ? "on" : ""}" data-cat="${id}" style="--jc:${c.color}">
    <span class="j-cat-v">${visionSVG(id)}</span><b>${c.label}</b></button>`).join("")}</div>`;
}

function wishSheet(root, w, J, focus = "") {
  const isNew = !w;
  let cat = w?.category || "";
  const vis = (id) => (J.categories || []).find((c) => c.id === id)?.vision || "";
  const body = h("div", { class: "j-wish", html: `
    ${isNew ? `<p class="muted">选一个方向。分类只是帮你起个头，名字和愿景都可以自己写。</p>` : ""}
    ${catGrid(cat)}
    <label class="lbl">愿望的名字</label>
    <input class="field" id="wTitle" maxlength="30" value="${esc(w?.title || "")}" placeholder="比如：更敢开口表达">
    <label class="lbl">现在的我 <span class="muted">（一句话，没人会评判）</span></label>
    <input class="field" id="wNow" maxlength="80" value="${esc(w?.now_text || "")}" placeholder="比如：开会时总是不敢说出自己的想法">
    <label class="lbl">向往的我 <span class="muted">（是愿景，不是要求）</span></label>
    <input class="field" id="wVision" maxlength="80" value="${esc(w?.vision_text || "")}" placeholder="比如：更相信自己，愿意表达">
    ${isNew ? "" : `<div class="j-archive"><button class="btn btn-quiet btn-sm" id="wArchive">${icon("moon")}先收起这个愿望</button><small class="muted">收起后记录都还在。</small></div>`}` });
  const t = body.querySelector("#wTitle"), v = body.querySelector("#wVision");
  body.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
    const prev = cat;
    cat = b.dataset.cat;
    body.querySelectorAll("[data-cat]").forEach((x) => x.classList.toggle("on", x === b));
    if (!t.value || t.value === CATS[prev]?.label) t.value = CATS[cat].label;
    if (!v.value || v.value === vis(prev)) v.value = vis(cat);
  }));
  const save = async () => {
    if (isNew && !cat) return toast("先选一个方向");
    const payload = { title: t.value.trim(), category: cat, now_text: body.querySelector("#wNow").value, vision_text: v.value };
    try {
      setData(isNew ? await api.wish("add", payload) : await api.wish("edit", { id: w.id, ...payload }));
      s.close();
      toast(isNew ? "新的轨迹开始了" : "改好了", "", catOf(cat).icon);
      renderPlan(root);
    } catch (e) { toast(e.message, "err"); }
  };
  body.querySelector("#wArchive")?.addEventListener("click", async () => {
    if (!(await confirmSheet("先收起这个愿望？", "它会从看板上移走，记录和回望都保留在你的数据里。", "收起"))) return;
    try { setData(await api.wish("edit", { id: w.id, archived: true })); s.close(); renderPlan(root); }
    catch (e) { toast(e.message, "err"); }
  });
  const s = sheet({ title: isNew ? "开启一个新愿望" : "编辑愿望", body, sticker: "flag",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: save }, isNew ? "开始这段轨迹" : "保存")] });
  s.panel.classList.add("j-sheet");
  if (focus) setTimeout(() => body.querySelector(focus === "now_text" ? "#wNow" : "#wVision").focus(), 60);
}

// 还没有任何愿望：直接在页面上选方向
function renderStart(root, J) {
  root.innerHTML = `<div class="view-inner wide plan journey">
    <div class="page-head"><div><h1>蜕变计划</h1><p>每个愿望一张轨迹：从现在的我，走向想成为的自己</p></div></div>
    <section class="card j-start">
      <div class="j-start-art"><svg viewBox="0 0 ${VIEW_W} ${VIEW_H}" preserveAspectRatio="none" aria-hidden="true"><path class="curve" d="${CURVE}"/></svg>
        <svg class="j-fig" viewBox="0 0 200 110">${figureSVG()}</svg></div>
      <h2>你最想靠近哪一种自己？</h2>
      <p class="muted">选一个方向，看板就会出现：左下是现在的你，右上是你向往的样子。之后每留下一个真实的瞬间，轨迹上就亮一个点。</p>
      ${catGrid("")}
    </section></div>`;
  root.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
    wishSheet(root, null, J);
    document.querySelector(`.j-wish [data-cat="${b.dataset.cat}"]`)?.click();
  }));
}
