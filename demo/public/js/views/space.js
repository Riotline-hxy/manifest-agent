// 我的空间：档案 · 了解你（记忆分六类、小光的发现）· 夜里整理（笔记本、最近几晚）· 时间线 · 设置（含氛围与小光的颜色）。
// 「聊聊现在的你」不封在这里，它是点子里的体验；这里只看结果（记忆、设置里的陪伴偏好），随时改。
import { api } from "../api.js";
import { state, setData, go } from "../store.js";
import { esc, toast, sheet, h, confirmSheet, fmtDay, icon, tile } from "../ui.js";
import { burstAt } from "../fx.js";
import { mountBall, lookPicture, currentLook } from "../ball.js";
import { lookName } from "../jelly.js";
import { openLookSheet } from "../look.js";
import { townSVG, builtCount } from "../town.js";
import { timelineHTML, nowIso } from "../timeline.js";
import { THEMES, applyTheme, themeOf } from "../theme.js";
import { themeCard, placeInd } from "../app.js";
import { openAccount, logout } from "../account.js";
import { pushSupport, pushOn, enablePush, disablePush, installState, install, PUSH_WHY } from "../push.js";

const TABS = [["memory", "了解你"], ["digest", "夜里整理"], ["timeline", "时间线"], ["settings", "设置"]];
const REASON = { user_corrected: "你在聊天里更正", user_edit: "你亲手修改", user_forget: "你让我忘掉", user_reject: "你说不对", edit: "修改" };

export function renderSpace(root) {
  const d = state.data;
  const p = d.profile || {};
  const t = d.town;
  const mems = d.memories || [];
  const tab = state.spaceTab || "memory";
  root.innerHTML = `
    <div class="view-inner wide space">
      <section class="me-card card">
        <span class="me-av">${esc((p.nickname || state.user?.username || "我").slice(0, 1))}</span>
        <div class="me-main">
          <h1>${esc(p.nickname || state.user?.username || "你")}<button class="icon-btn sm me-edit" data-name-edit aria-label="改名字" title="改名字">${icon("edit")}</button></h1>
          <p>陪伴第 ${d.counts?.days || 1} 天 · 正在靠近「${esc(p.intent_primary || "还没想好")}」</p>
          <div class="me-stats">
            <span><b class="num">${mems.filter((m) => m.status === "active").length}</b>件事</span>
            <span><b class="num">${d.counts?.good || 0}</b>颗星</span>
            <span><b class="num">${d.counts?.done || 0}</b>个小步</span>
            <span><b class="num">${t ? builtCount(t) : 0}</b>栋房子</span>
          </div>
        </div>
        ${t ? `<button class="me-town" data-go="town" aria-label="去我的小镇">${townSVG(t, { still: true })}</button>` : ""}
      </section>
      <div class="tabs space-tabs">${TABS.map(([k, l]) => `<button class="${k === tab ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}<span class="ind"></span></div>
      <div class="space-body"></div>
    </div>`;
  root.querySelector("[data-name-edit]").addEventListener("click", () => nameSheet(root));
  const tabs = root.querySelector(".space-tabs");
  requestAnimationFrame(() => placeInd(tabs));
  tabs.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { state.spaceTab = b.dataset.tab; renderSpace(root); }));
  root.querySelector("[data-go]")?.addEventListener("click", () => go("town"));
  ({ memory: memoryTab, digest: digestTab, timeline: timelineTab, settings: settingsTab })[tab](root.querySelector(".space-body"), root);
}

// ---- 了解你（原来的「记忆」）：一句话 → 六个大类 → 小光的发现 → 猜测 --------------------------
// 记忆一条不少：每条都在某一类里（core/portrait.py），点开一类能看全、能改、能删、能加；
// 最底下「按时间看全部」是平铺的完整清单和修订记录。

function catCard(c) {
  const items = c.items || [];
  const shown = items.slice(0, 3);
  return `<button class="card cat" data-cat="${esc(c.id)}">
    <div class="cat-h">${tile(c.icon, c.color, 34)}<b>${esc(c.name)}</b><span class="n">${items.length ? `${items.length} 件` : ""}</span></div>
    ${shown.length ? `<ul>${shown.map((i) => `<li>${esc(i.text)}${i.fixed ? `<small>你定的</small>` : ""}</li>`).join("")}</ul>`
      : `<p class="cat-empty">还没有。点开告诉小光一件</p>`}
    <div class="more">${items.length > 3 ? `还有 ${items.length - 3} 件 · ` : ""}全部 ›</div></button>`;
}

function findRow(f, i) {
  const sub = f.ready ? `${f.src}${f.fb === "yes" ? " · 你说像" : " · 等你说像不像"}` : `正在积累 · 还差 ${f.left} ${f.unit}`;
  return `<button class="row ${f.ready ? "" : "wait"}" data-find="${i}" style="--i:${i}">${tile(f.icon, f.ready ? f.color : "var(--surface-3)", 42)}
    <span class="row-main"><b>${esc(f.ready ? f.a : f.q)}</b><span>${esc(sub)}</span></span><span class="row-go">${icon("arrow")}</span></button>`;
}

function memoryTab(body, root) {
  const d = state.data;
  const about = d.about || [];
  const pt = d.portrait || {};
  const ins = d.insights || [];
  const guesses = (d.memories || []).filter((m) => m.status === "guess");
  const total = about.reduce((n, c) => n + c.items.filter((i) => !i.fixed).length, 0);
  body.innerHTML = `
    <section class="card portrait">${tile("sparkles", "var(--c-violet)", 46)}
      <div class="pt-main"><div class="pt-k">小光眼中的你</div>
        <div class="pt-t">${esc(pt.text || "")}</div>
        <div class="pt-m">${pt.by === "user" ? "你写的 · 小光会照这个认识你" : pt.by === "early" ? "认识满一周后，小光每晚整理时会写一句" : `认识第 ${pt.days} 天 · 每晚整理时更新`}</div></div>
      ${pt.by === "early" ? "" : `<button class="icon-btn" data-pt-edit title="改这句话">${icon("edit")}</button>`}</section>
    <div class="sec-title">关于你<span class="more">6 类 · ${total} 件事，点开能看全、能改</span></div>
    <div class="cats">${about.map(catCard).join("")}</div>
    <div class="sec-title">小光的发现<span class="more">从你做过的事里算出来的 · ${ins.filter((f) => f.ready).length} / ${ins.length}</span></div>
    <div class="finds rows">${ins.map(findRow).join("")}</div>
    ${guesses.map((g) => `<div class="mem guess guess-row"><div class="mt">小光猜：${esc(g.text)}</div>
      <button class="btn btn-sm btn-good" data-act="confirm" data-id="${esc(g.id)}">对</button>
      <button class="btn btn-sm btn-ghost" data-act="reject" data-id="${esc(g.id)}">不太对</button></div>`).join("")}
    <button class="all-link" data-all>${icon("list")}按时间看全部 ${total} 件事和修订记录</button>`;

  body.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => catSheet(b.dataset.cat, root)));
  body.querySelectorAll("[data-find]").forEach((b) => b.addEventListener("click", () => findSheet(ins[+b.dataset.find], root)));
  body.querySelector("[data-all]").addEventListener("click", () => allSheet(root));
  body.querySelector("[data-pt-edit]")?.addEventListener("click", () => portraitSheet(pt, root));
  body.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    try {
      setData(await api.memory(b.dataset.act, { id: b.dataset.id }));
      toast(b.dataset.act === "confirm" ? "记下了" : "删掉了，谢谢你纠正我");
      renderSpace(root);
    } catch (e) { toast(e.message, "err"); }
  }));
}

function refreshAnd(root, then) {
  renderSpace(root);
  if (then) then();
}

// 点开一类：这一类的全部记忆，每件从哪来、改过的写「原来是」，能改、能删、能加
function catSheet(cid, root) {
  const c = (state.data.about || []).find((x) => x.id === cid);
  if (!c) return;
  const body = h("div", { class: "cat-sheet" });
  body.innerHTML = `<p class="why">${esc(c.why)}</p>
    ${c.items.map((i) => `<div class="it"><div class="tx"><b>${esc(i.text)}</b>
      <small>${esc(i.src)}${i.day ? ` · ${esc(i.day.slice(5))}` : ""}${i.was ? ` · 原来是 <s>${esc(i.was)}</s>` : ""}</small></div>
      ${i.fixed ? "" : `<button class="icon-btn" data-edit="${esc(i.id)}" title="改">${icon("edit")}</button>
        <button class="icon-btn" data-forget="${esc(i.id)}" title="忘掉">${icon("trash")}</button>`}</div>`).join("")
      || `<p class="muted" style="margin:6px 0 4px">这一类还没有。写一件告诉小光吧。</p>`}
    <div class="sheet-add"><input class="field" maxlength="120" placeholder="告诉小光一件"><button class="btn btn-main" data-add>写进去</button></div>`;
  const s = sheet({ title: c.name, sticker: c.icon, body });
  const again = () => { s.close(); refreshAnd(root, () => catSheet(cid, root)); };
  body.querySelector("[data-add]").addEventListener("click", async () => {
    const inp = body.querySelector(".sheet-add input");
    if (!inp.value.trim()) return inp.focus();
    try { setData(await api.memory("add", { text: inp.value.trim(), cat: cid })); toast("写进去了"); again(); }
    catch (e) { toast(e.message, "err"); }
  });
  body.querySelectorAll("[data-forget]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmSheet("忘掉这件？", "会真正删除，以后不再用它理解你。修订记录里会留下一笔。", "忘掉", "trash"))) return;
    try { setData(await api.memory("forget", { id: b.dataset.forget })); toast("忘掉了"); again(); }
    catch (e) { toast(e.message, "err"); }
  }));
  body.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
    const m = c.items.find((i) => i.id === b.dataset.edit);
    s.close();
    editMem(m, cid, root);
  }));
}

// 改一件：改说法，也能挪到别的类
function editMem(m, cid, root) {
  const input = h("textarea", { class: "field", rows: "2", maxlength: "120" });
  input.value = m.text;
  const pick = h("div", { class: "tabs seg cat-pick" });
  pick.innerHTML = (state.data.about || []).map((c) => `<button data-c="${c.id}" class="${c.id === cid ? "on" : ""}">${esc(c.name)}</button>`).join("");
  let to = cid;
  pick.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    to = b.dataset.c;
    pick.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  }));
  const s = sheet({
    title: "改一件", sticker: "edit", body: h("div", {}, input, h("div", { class: "pick-k" }, "放在哪一类"), pick),
    footer: [h("button", { class: "btn btn-ghost", onclick: () => { s.close(); catSheet(cid, root); } }, "取消"),
      h("button", { class: "btn btn-main", onclick: async () => {
        if (!input.value.trim()) return;
        try {
          setData(await api.memory("edit", { id: m.id, text: input.value.trim(), cat: to }));
          s.close(); toast("改好了，旧的说法留在修订记录里"); refreshAnd(root, () => catSheet(to, root));
        } catch (e) { toast(e.message, "err"); }
      } }, "保存")],
  });
  setTimeout(() => input.focus(), 60);
}

// 一个发现：问题 → 答案 → 图和依据 → 像我 / 不太像
function findSheet(f, root) {
  const body = h("div", { class: "find-sheet" });
  const max = Math.max(1, ...(f.chart || [1]));
  const top = (f.chart || []).indexOf(max);
  body.innerHTML = `<div class="fq">${esc(f.q)}</div>
    ${f.ready ? `<div class="fa">${esc(f.a)}</div>
      ${f.chart ? `<div class="panel"><div class="pk">最近 4 周，每天打卡和完成小步的次数</div>
        <div class="chart">${f.chart.map((n, i) => `<i class="${i === top ? "hi" : ""}" style="height:${Math.max(6, Math.round(n / max * 100))}%"></i>`).join("")}</div>
        <div class="xl">${"一二三四五六日".split("").map((x) => `<span>${x}</span>`).join("")}</div></div>` : ""}
      <div class="panel"><div class="pk">小光是怎么看出来的</div>${(f.evidence || []).map((e) => `<div class="ev">${esc(e)}</div>`).join("")}</div>`
    : `<div class="fa wait">还在积累</div>
      <div class="panel"><div class="pk">还差 ${f.left} ${esc(f.unit)}</div>
        <div class="prog"><i style="width:${Math.round(Math.min(f.have, f.need) / f.need * 100)}%"></i></div>
        <div class="ev">记录够了，小光会把算出来的结论放在这里，带着依据，等你说像不像。</div></div>`}`;
  const footer = f.ready ? [
    h("button", { class: "btn btn-ghost", onclick: () => save("no") }, "不太像"),
    h("button", { class: `btn ${f.fb === "yes" ? "btn-good" : "btn-main"}`, onclick: () => save("yes") }, f.fb === "yes" ? "你说过像" : "像我")] : null;
  const s = sheet({ title: "小光的发现", sticker: f.icon, body, footer });
  async function save(fb) {
    try {
      setData(await api.discovery(f.id, fb));
      s.close(); toast(fb === "yes" ? "记下了，小光以后照这个来" : "好，这条不再出现"); renderSpace(root);
    } catch (e) { toast(e.message, "err"); }
  }
}

function portraitSheet(pt, root) {
  const input = h("textarea", { class: "field", rows: "2", maxlength: "60" });
  input.value = pt.text || "";
  const s = sheet({
    title: "小光眼中的你", sticker: "sparkles",
    body: h("div", {}, h("p", { class: "muted", style: "margin:0 0 8px;font-size:13px" }, "写成你觉得像自己的样子。改过以后，夜里整理不会再覆盖；清空就交还给小光写。"), input),
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"),
      h("button", { class: "btn btn-main", onclick: async () => {
        try { setData(await api.portrait(input.value.trim())); s.close(); toast("改好了"); renderSpace(root); }
        catch (e) { toast(e.message, "err"); }
      } }, "保存")],
  });
  setTimeout(() => input.focus(), 60);
}

// 按时间看全部：平铺的完整清单（带类别）、修订记录、两分钟启动记忆
function allSheet(root) {
  const d = state.data;
  const catName = {};
  (d.about || []).forEach((c) => c.items.forEach((i) => { if (i.id) catName[i.id] = c.name; }));
  const mems = (d.memories || []).filter((m) => m.status === "active");
  const revs = d.revisions || [];
  const kicks = d.kick_memories || [];
  const body = h("div", { class: "cat-sheet" });
  body.innerHTML = `${mems.map((m) => `<div class="it"><div class="tx"><b>${esc(m.text)}</b>
      <small>${esc(catName[m.id] || "")} · ${esc((m.updated_at || m.created_at || "").slice(5, 10))}</small></div></div>`).join("")}
    ${revs.length ? `<div class="pick-k" style="margin-top:16px">修订记录 · 每次改动都留着依据</div>
      ${revs.map((r) => `<div class="it"><div class="tx"><b>${r.new_text ? `<s>${esc(r.old_text || "")}</s> → ${esc(r.new_text)}` : `<s>${esc(r.old_text || "")}</s>（已删除）`}</b>
        <small>${esc(r.at.slice(5, 16).replace("T", " "))} · ${esc(r.reason?.startsWith("digest") ? "夜里整理" : REASON[r.reason] || r.reason || "")}${r.evidence ? `：「${esc(r.evidence)}」` : ""}</small></div></div>`).join("")}` : ""}
    ${kicks.length ? `<div class="pick-k" style="margin-top:16px">两分钟启动记忆 · 你勾了「让小光记住」的</div>
      ${kicks.map((k) => `<div class="it"><div class="tx"><b>${esc(k.task || "")}</b><small>${esc(k.day || "")}</small></div>
        <button class="icon-btn" data-kick-forget="${esc(k.id)}" title="删掉">${icon("trash")}</button></div>`).join("")}` : ""}`;
  const s = sheet({ title: `全部 ${mems.length} 件事`, sticker: "list", body });
  body.querySelectorAll("[data-kick-forget]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmSheet("删掉这次的启动记忆？", "会真正删除，小光以后查不到这一次了。", "删掉", "trash"))) return;
    try {
      const out = await api.kick("forget", { id: b.dataset.kickForget });
      if (out.state) setData(out.state);
      toast("删掉了"); s.close(); refreshAnd(root, () => allSheet(root));
    } catch (e) { toast(e.message, "err"); }
  }));
}

// ---- 夜里整理：整理说明 → 小光的笔记本（分行）→ 最近几晚（一晚一行，点开看变化）-----------

function nbRows(text) {
  return (text || "").split(/\n+/).map((l) => l.trim()).filter(Boolean).map((l) => {
    const m = l.match(/^([^：:]{2,8})[：:]\s*(.+)$/);
    return m ? `<div class="nb-row"><i>${esc(m[1])}</i><span>${esc(m[2])}</span></div>` : `<div class="nb-row"><i></i><span>${esc(l)}</span></div>`;
  }).join("");
}

function nightLabel(day) {
  const y = new Date(Date.now() - 864e5).toISOString().slice(0, 10);
  return day === y ? "昨天" : day.slice(5);
}

function digestTab(body, root) {
  const list = state.data.digests || [];
  const nb = state.data.profile?.notebook || {};
  const catOf = {};
  (state.data.about || []).forEach((c) => c.items.forEach((i) => { catOf[i.text] = c.name; }));
  body.innerHTML = `
    <section class="night card">
      <div class="night-ball"></div>
      <div class="night-copy">
        <h2>每天夜里，小光会安静地整理一遍</h2>
        <p>把这一天里值得记住的，写进笔记本、归进「了解你」的六类里。你让它记的不会被忘掉；它猜的，要你点头。</p>
        <button class="btn btn-main" data-run>${icon("moon")}现在整理一下今天</button>
      </div>
    </section>
    <section class="nb card">
      <div class="nb-head">${tile("book", "var(--c-violet)", 34)}<div><b>小光的笔记本</b>
        <small>${nb.updated_at ? `${esc(fmtDay(nb.updated_at))}${nb.by === "user" ? " · 你改过" : " · 夜里整理时更新"}` : "夜里整理时会开始写"}</small></div>
        <span class="sp"></span><button class="btn btn-sm btn-ghost" data-nb-edit>${icon("edit")}改一改</button></div>
      <div class="nb-text">${nb.text ? `<div class="nb-rows">${nbRows(nb.text)}</div>` : '<p class="muted" style="margin:10px 0 0">还没有内容。聊过几天以后，小光会在这里写下关于你的事。</p>'}</div>
    </section>
    ${list.length ? `<div class="sec-title" style="margin-top:26px">最近几晚<span class="more">只写变了什么，点开看细节</span></div>
    <section class="card nights">${list.map((x) => {
      const st = x.stats || {};
      const chips = [st.added ? `<span class="pill good">新记 ${st.added}</span>` : "", st.guesses ? `<span class="pill acc">猜 ${st.guesses}</span>` : "",
        st.updated ? `<span class="pill">改 ${st.updated}</span>` : "", st.deleted ? `<span class="pill">删 ${st.deleted}</span>` : ""].join("");
      return `<details class="night-row"><summary><span class="d">${esc(nightLabel(x.day))}</span><span class="s">${esc(x.summary)}</span><span class="c">${chips}</span></summary>
        <div class="night-open">${(x.ops || []).map((o) => `<div class="chg"><span class="k">${o.op === "ADD" ? (o.status === "guess" ? "猜了一件" : "新记住") : o.op === "UPDATE" ? "改了" : "删掉"}</span>
          <span class="tx">${o.op === "UPDATE" ? `<s>${esc(o.old)}</s> → ` : ""}${esc(o.text || o.old)}</span>${catOf[o.text] ? `<span class="to">→ ${esc(catOf[o.text])}</span>` : ""}</div>`).join("")
          || `<div class="muted" style="font-size:13px">这一晚没有改动记忆。</div>`}</div></details>`;
    }).join("")}</section>` : ""}`;
  body.querySelector("[data-nb-edit]").addEventListener("click", () => {
    const box = body.querySelector(".nb-text");
    box.innerHTML = `<textarea class="field" rows="10" maxlength="1600">${esc(nb.text || "")}</textarea>
      <div class="row end" style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px"><button class="btn btn-ghost btn-sm" data-nb-cancel>取消</button><button class="btn btn-main btn-sm" data-nb-save>保存</button></div>`;
    box.querySelector("textarea").focus();
    box.querySelector("[data-nb-cancel]").addEventListener("click", () => renderSpace(root));
    box.querySelector("[data-nb-save]").addEventListener("click", async () => {
      try { setData(await api.notebook(box.querySelector("textarea").value)); toast("改好了，小光会照这个记"); renderSpace(root); }
      catch (e) { toast(e.message, "err"); }
    });
  });
  const ball = mountBall(body.querySelector(".night-ball"), { size: 92, emotion: "00", agent: false });
  body.querySelector("[data-run]").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.classList.add("off");
    ball.set("recall"); ball.pulse("spin");
    try {
      const out = await api.digest();
      setData(out);
      const dg = out.digest;
      if (dg.skipped) { toast("今天还没有可整理的内容"); ball.set("sleep"); }
      else { ball.set("done"); burstAt(b, 36); toast(`整理好了：新记 ${dg.stats.added}，更新 ${dg.stats.updated}，待确认 ${dg.stats.guesses}`); }
      setTimeout(() => renderSpace(root), 900);
    } catch (err) { toast(err.message, "err"); ball.set("error"); b.classList.remove("off"); }
  });
}

function timelineTab(body) {
  const d = state.data;
  body.innerHTML = `<div class="tl space-tl card">${timelineHTML(d.activity, { sums: d.growth?.day_totals, tasks: d.tasks, today: d.journey?.today, now: nowIso(), limit: 80 })}</div>`;
}

function settingsTab(body, root) {
  const p = state.data.profile || {};
  const seg = (key, opts, cur) => `<div class="tabs seg" data-key="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${cur === v ? "on" : ""}">${l}</button>`).join("")}<span class="ind"></span></div>`;
  const cur = themeOf(p.theme).id;
  const look = currentLook();
  const guest = state.user?.kind === "guest";
  body.innerHTML = `
    <div class="sec-title set-sec">${icon("sparkles")}小光<span class="more">它怎么说话、什么时候来找你</span></div>
    <div class="settings card">
      <div class="set-row">${tile("heart", "var(--c-pink)", 40)}<div class="sl"><b>性格</b><small>说话的方式会跟着变，记得的事不变</small></div>
        ${seg("persona", [["gentle", "温柔"], ["clear", "有条理"], ["lively", "活泼"]], p.persona || "gentle")}</div>
      <div class="set-row">${tile("compass", "var(--c-mint)", 40)}<div class="sl"><b>中断的时候</b><small>三天没动时，小光怎么反应</small></div>
        ${seg("care_style", [["nudge", "轻轻提醒"], ["analyze", "一起找原因"], ["quiet", "先别提"]], p.care_style)}</div>
      <div class="set-row">${tile("chat", "var(--c-violet)", 40)}<div class="sl"><b>陪伴偏好</b><small>${esc(prefLine(p))}</small></div>
        <button class="btn btn-sm btn-ghost" data-prefs>修改</button></div>
      <div class="set-row">${tile("letter", "var(--c-sky)", 40)}<div class="sl"><b>主动消息</b><small>23:00–08:00 不打扰 · <button class="set-link" data-proactive>让它现在说一句</button></small></div>
        ${seg("proactive", [["more", "多"], ["normal", "刚好"], ["less", "少"], ["off", "不要"]], p.proactive || "normal")}</div>
      <div class="set-row">${tile("palette", "var(--c-lemon)", 40)}<div class="sl"><b>外貌</b><small>${esc(lookName(look))}</small></div>
        <button class="set-look" data-look aria-label="换小光的外貌"><span class="set-look-pic">${lookPicture(look)}</span><span>换一换</span></button></div>
    </div>

    <div class="sec-title set-sec">${icon("user")}我<span class="more">账号和这台手机</span></div>
    <div class="settings card">
      <div class="set-row">${tile("chat", "var(--c-sky)", 40)}<div class="sl"><b>名字</b><small>小光叫你「${esc(p.nickname || state.user?.username || "你")}」${!guest ? ` · 登录用户名 ${esc(state.user?.username || "")}` : ""}</small></div>
        <button class="btn btn-sm btn-ghost" data-name-edit2>修改</button></div>
      <div class="set-row">${tile("user", "var(--c-orange)", 40)}<div class="sl"><b>账号</b><small>${guest ? "现在是体验账号，注册后记录会一直留着" : `已登录：${esc(state.user?.username || "")}`}</small></div>
        <button class="btn btn-sm btn-ghost" data-account>${guest ? "注册 / 退出" : "退出登录"}</button></div>
      <div class="set-row">${tile("home", "var(--c-mint)", 40)}<div class="sl"><b>小镇的名字</b><small>现在叫「${esc(state.data.town?.name || "我的小镇")}」</small></div>
        <button class="btn btn-sm btn-ghost" data-rename>改名</button></div>
      <div class="set-row">${tile("bell", "var(--c-lemon)", 40)}<div class="sl"><b>手机通知</b><small data-push-note>正在看这台设备……</small></div>
        <div class="set-acts" data-push-acts></div></div>
    </div>

    <div class="sec-title set-sec">${icon("palette")}氛围<span class="more">整个页面的样子，随时能换</span></div>
    <div class="theme-grid">${THEMES.map((t) => themeCard(t, t.id === cur)).join("")}</div>
    <p class="hint-line">每个账号在服务器上是一个独立的数据库文件；接口只认登录会话，没有任何参数能读到别人的数据。删除记忆是真删除。</p>`;

  requestAnimationFrame(() => body.querySelectorAll(".seg").forEach(placeInd));
  bindDevice(body);
  const save = async (patch, msg) => {
    try { setData(await api.profile(patch)); if (msg) toast(msg); renderSpace(root); } catch (e) { toast(e.message, "err"); }
  };
  body.querySelectorAll("[data-theme-id]").forEach((b) => b.addEventListener("click", () => {
    const t = applyTheme(b.dataset.themeId);
    save({ theme: t.id }, `换成「${t.name}」了`);
  }));
  body.querySelector("[data-look]").addEventListener("click", () => openLookSheet({ onSaved: () => renderSpace(root) }));
  body.querySelectorAll(".seg").forEach((sg) => sg.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => save({ [sg.dataset.key]: b.dataset.v }, "改好了"))));
  body.querySelector("[data-name-edit2]").addEventListener("click", () => nameSheet(root));
  body.querySelector("[data-prefs]").addEventListener("click", () => prefsSheet(root));
  body.querySelector("[data-account]").addEventListener("click", () => (guest ? openAccount() : confirmLogout()));
  body.querySelector("[data-rename]").addEventListener("click", () => {
    const input = h("input", { class: "field", maxlength: "10", placeholder: "比如：晴天镇" });
    input.value = state.data.town?.name === "我的小镇" ? "" : state.data.town?.name || "";
    const s = sheet({ title: "给小镇起个名字", sticker: "home", body: input, footer: [h("button", { class: "btn btn-main", onclick: async () => {
      s.close();
      try { setData(await api.town("rename", { name: input.value })); toast("改好了"); renderSpace(root); } catch (e) { toast(e.message, "err"); }
    } }, "就叫这个")] });
  });
  body.querySelector("[data-proactive]").addEventListener("click", async () => {
    const out = await api.proactiveNow();
    setData(out);
    toast(out.sent ? "小光发了一句话，去对话里看看" : out.reason);
    if (out.sent) go("chat");
  });
}

// ---- 手机通知：开推送；能一键装到桌面时顺便给个「装到桌面」；iPhone 没装时先教怎么装 ----
function bindDevice(body) {
  const note = body.querySelector("[data-push-note]"), acts = body.querySelector("[data-push-acts]");
  const btn = (label, cls, fn) => h("button", { class: `btn btn-sm ${cls}`, onclick: fn }, label);

  async function draw() {
    const sup = pushSupport();
    const on = await pushOn();
    const inst = installState();
    acts.replaceChildren();
    if (on) {
      note.textContent = "已开启：主动消息和到点提醒，网页关着也会推到这台设备";
      acts.append(btn("发一条试试", "btn-ghost", testPush), btn("关闭", "btn-quiet", async () => {
        await disablePush(); toast("这台设备不再收通知了"); draw();
      }));
    } else if (sup === "ok") {
      note.textContent = "开了以后，网页关着也能收到小光的消息和提醒";
      acts.append(btn("开启", "btn-main", async (e) => {
        e.currentTarget.classList.add("off");
        const r = await enablePush();
        toast(r.ok ? "开好了，点「发一条试试」看看" : PUSH_WHY[r.reason], r.ok ? "" : "err", r.ok ? "bell" : "");
        draw();
      }));
    } else {
      note.textContent = PUSH_WHY[sup];
      if (sup === "ios-home" || sup === "unsupported") acts.append(btn("怎么开", "btn-ghost", installGuide));
    }
    if (inst === "prompt") acts.append(btn("装到桌面", "btn-ghost", async () => { if (await install()) toast("装好了，去桌面看看"); draw(); }));
  }
  async function testPush(e) {
    const b = e.currentTarget;
    b.classList.add("off");
    try {
      const r = await api.pushTest();
      toast(r.sent ? "发出去了，几秒内手机上会响一下（网页开着时也会弹）" : "没发出去，等会儿再试，或者关掉再开一次", r.sent ? "" : "err", "bell");
    } catch (err) { toast(err.message, "err"); }
    b.classList.remove("off");
  }
  draw();
  addEventListener("xg:installable", draw, { once: true });
}

function installGuide() {
  const body = h("div", { class: "install-guide", html: `
    <h4>iPhone（用 Safari 打开）</h4>
    <ol><li>点屏幕底部的「分享」按钮（方框加向上的箭头）</li><li>往下滑，点「添加到主屏幕」，再点「添加」</li>
      <li>回到桌面，点「显伴」图标打开，登录后到「我的空间 → 设置」开启手机通知</li></ol>
    <p class="hint">需要 iOS 16.4 或更新的版本；在微信里打开的页面不行，先用 Safari 打开。</p>
    <h4>安卓（用 Chrome 或手机自带浏览器）</h4>
    <ol><li>点右上角的「⋮」菜单</li><li>选「安装应用」或「添加到主屏幕」</li><li>从桌面图标打开，到「我的空间 → 设置」开启手机通知</li></ol>
    <p class="hint">国内部分安卓手机的浏览器收不到网页通知（依赖谷歌的推送服务）；收不到时，消息会在你打开显伴时出现。</p>` });
  const s = sheet({ title: "在手机上开通知", sticker: "bell", body, footer: [h("button", { class: "btn btn-main", onclick: () => s.close() }, "知道了")] });
}

async function confirmLogout() {
  if (await confirmSheet("退出登录？", "下次用用户名和密码就能回来，记录都在。", "退出", "back")) logout();
}

// 陪伴偏好：在「聊聊现在的你」里确认的三样，这里看、改、清空（再点一下选中的就是不设）
const PREFS = [["chat_style", "聊天时，希望我"], ["remind_pref", "想坚持的事，多久提醒一次"], ["energy_time", "一天里比较有精神的时候"]];

function prefLine(p) {
  const parts = [p.chat_style, p.remind_pref && `提醒：${p.remind_pref}`, p.energy_time && `${p.energy_time}比较有精神`].filter(Boolean);
  return parts.join(" · ") || "还没选，可以去点子里「聊聊现在的你」";
}

function prefsSheet(root) {
  const p = state.data.profile || {};
  const opts = state.data.prefs?.options || {};
  const cur = Object.fromEntries(PREFS.map(([k]) => [k, p[k] || ""]));
  const body = h("div", { class: "j-add prefs", html: PREFS.map(([k, label]) => {
    const list = [...(opts[k] || [])];
    if (cur[k] && !list.includes(cur[k])) list.push(cur[k]);     // 自己改过的说法也留着
    return `<label class="lbl">${esc(label)}</label><div class="ob-chips">${list.map((v) =>
      `<button class="chip ${cur[k] === v ? "on" : ""}" data-k="${k}" data-v="${esc(v)}">${esc(v)}</button>`).join("")}</div>`;
  }).join("") + `<p class="muted j-note">提醒频率只是偏好，不会自己开提醒；真要提醒时，小光会先问你提醒什么、几点。</p>` });
  body.querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => {
    const { k, v } = b.dataset;
    cur[k] = cur[k] === v ? "" : v;
    body.querySelectorAll(`[data-k="${k}"]`).forEach((x) => x.classList.toggle("on", x.dataset.v === cur[k]));
  }));
  const s = sheet({ title: "陪伴偏好", sticker: "chat", body,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: async () => {
      try { setData(await api.profile(cur)); s.close(); toast("改好了"); renderSpace(root); } catch (e) { toast(e.message, "err"); }
    } }, "保存")] });
  s.panel.classList.add("j-sheet");
}

// 改名字：称呼（小光怎么叫你、页面上显示的名字）；正式账号还可以改登录用户名
function nameSheet(root) {
  const p = state.data.profile || {};
  const member = state.user?.kind === "member";
  const body = h("div", { class: "j-add", html: `
    <label class="lbl">小光怎么叫你</label>
    <input class="field" id="nNick" maxlength="20" value="${esc(p.nickname || "")}" placeholder="比如：林夏、小鱼">
    ${member ? `<label class="lbl">登录用户名 <span class="muted">（下次登录用这个）</span></label>
      <input class="field" id="nUser" maxlength="20" value="${esc(state.user.username || "")}">` : `<p class="muted j-note">体验账号还没有登录用户名，注册后就能设置。</p>`}` });
  const s = sheet({ title: "改名字", body, sticker: "edit",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"), h("button", { class: "btn btn-main", onclick: async () => {
      const nick = body.querySelector("#nNick").value.trim();
      if (!nick) return body.querySelector("#nNick").focus();
      try {
        if (member) {
          const un = body.querySelector("#nUser").value.trim();
          if (un && un !== state.user.username) state.user = (await api.rename(un)).user;
        }
        setData(await api.profile({ nickname: nick }));
        s.close();
        toast(`好，以后叫你「${nick}」`);
        renderSpace(root);
      } catch (e) { toast(e.message, "err"); }
    } }, "保存")] });
  s.panel.classList.add("j-sheet");
  setTimeout(() => body.querySelector("#nNick").select(), 60);
}
