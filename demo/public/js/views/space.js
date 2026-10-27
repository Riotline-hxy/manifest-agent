// 我的空间：档案 · 记忆（可改可删、带修订记录）· 夜里的整理 · 时间线 · 设置。
// 「重新认识我」不封在这里——它是点子里的体验；这里只看结果、随时改。
import { api } from "../api.js";
import { state, setData, go } from "../store.js";
import { esc, toast, sheet, h, confirmSheet, fmtDay } from "../ui.js";
import { art, burstAt } from "../fx.js";
import { mountBall } from "../ball.js";
import { startScene } from "../scene.js";

const KIND = { identity: "身份", intent: "愿景", preference: "偏好", boundary: "边界", insight: "新发现", event: "事件", good_news: "好消息" };
const SRC = (s) => s === "confirmed" ? "你确认过" : s === "onboarding" ? "建档时" : s?.startsWith("scene") ? "练习里" :
  s === "chat:explicit" ? "你让我记的" : s === "digest" ? "夜里整理" : "聊天里";
const TABS = [["memory", "记忆"], ["digest", "夜里整理"], ["timeline", "时间线"], ["settings", "设置"]];
const REASON = { user_corrected: "你在聊天里更正", user_edit: "你亲手修改", user_forget: "你让我忘掉", user_reject: "你说不对", edit: "修改" };

export function renderSpace(root) {
  const d = state.data;
  const p = d.profile || {};
  const g = d.growth || {};
  const mems = d.memories || [];
  const earned = (g.badges || []).filter((b) => b.earned).length;
  const tab = state.spaceTab || "memory";

  root.innerHTML = `
    <div class="view-inner wide space">
      <section class="me-card">
        <span class="me-av">${esc((p.nickname || state.user?.username || "我").slice(0, 1))}</span>
        <div class="me-main">
          <h1>${esc(p.nickname || state.user?.username || "你")}</h1>
          <p>陪伴第 ${d.counts?.days || 1} 天 · 正在靠近「${esc(p.intent_primary || "还没想好")}」</p>
          <div class="me-stats">
            <span><b class="num">${mems.filter((m) => m.status === "active").length}</b>条记忆</span>
            <span><b class="num">${d.counts?.good || 0}</b>颗星</span>
            <span><b class="num">${d.counts?.done || 0}</b>个小步</span>
            <span><b class="num">${earned}</b>枚徽章</span>
          </div>
        </div>
        <img class="me-pet bob" src="${art(g.stage?.art || "pet-egg")}" alt="">
      </section>

      <div class="tabs space-tabs">${TABS.map(([k, l]) => `<button class="${k === tab ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}<span class="ind"></span></div>
      <div class="space-body"></div>
    </div>`;

  const tabs = root.querySelector(".space-tabs");
  requestAnimationFrame(() => {
    const on = tabs.querySelector(".on");
    Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
  });
  tabs.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { state.spaceTab = b.dataset.tab; renderSpace(root); }));
  const body = root.querySelector(".space-body");
  ({ memory: memoryTab, digest: digestTab, timeline: timelineTab, settings: settingsTab })[tab](body, root);
}

function memoryTab(body, root) {
  const mems = state.data.memories || [];
  const guesses = mems.filter((m) => m.status === "guess");
  const active = mems.filter((m) => m.status === "active");
  const revs = state.data.revisions || [];
  body.innerHTML = `
    ${guesses.length ? `<div class="sec-title">小光猜的，需要你点头 <span class="more">点「对」才会用它理解你</span></div>
      <div class="mem-grid">${guesses.map((m) => `<div class="mem guess">
        <div class="mt">${esc(m.text)}</div>
        <div class="mm"><span class="pill lamp">猜测</span><span class="muted">${esc(m.created_at.slice(5, 10))}</span></div>
        <div class="ma"><button class="btn btn-sm btn-leaf" data-act="confirm" data-id="${esc(m.id)}">对</button>
          <button class="btn btn-sm btn-ghost" data-act="reject" data-id="${esc(m.id)}">不太对</button></div></div>`).join("")}</div>` : ""}

    <div class="sec-title" style="margin-top:${guesses.length ? 26 : 0}px">小光记得的 <span class="more">${active.length} 条</span></div>
    <div class="add-row" style="margin-bottom:14px">
      <input class="field" id="newMem" maxlength="120" placeholder="亲手写一条，比如「我喜欢吃寿司」">
      <button class="btn btn-lamp" id="addMem">写进去</button>
    </div>
    <div class="mem-grid">${active.map((m, i) => `<div class="mem" style="--i:${i}">
      <div class="mt">${esc(m.text)}</div>
      <div class="mm"><span class="pill leaf">${esc(KIND[m.kind] || "记忆")}</span><span class="pill">${esc(SRC(m.source))}</span><span class="muted">${esc(m.created_at.slice(5, 10))}</span></div>
      <div class="ma hover"><button class="btn btn-sm btn-ghost" data-act="edit" data-id="${esc(m.id)}">改</button>
        <button class="btn btn-sm btn-quiet" data-act="forget" data-id="${esc(m.id)}">忘掉</button></div>
    </div>`).join("") || `<div class="empty"><img src="${art("st-mirror")}" alt=""><h3>还没有记住什么</h3><p>在对话里说「帮我记住……」，或者在上面亲手写一条。</p></div>`}</div>

    ${revs.length ? `<details class="card revs"><summary><img src="${art("st-book")}" alt="">修订记录 <span class="muted">· 每次改动都留着依据</span></summary>
      ${revs.map((r) => `<div class="rev"><span class="muted">${esc(r.at.slice(5, 16).replace("T", " "))}</span>
        <div><s>${esc(r.old_text || "")}</s>${r.new_text ? ` → <b>${esc(r.new_text)}</b>` : " <b>（已删除）</b>"}
        <small>${esc(r.reason?.startsWith("digest") ? "夜里整理" : REASON[r.reason] || r.reason)}${r.evidence ? `：「${esc(r.evidence)}」` : ""}</small></div></div>`).join("")}
    </details>` : ""}`;

  body.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    const { act, id } = b.dataset;
    const m = (state.data.memories || []).find((x) => x.id === id);
    if (act === "forget" && !(await confirmSheet("忘掉这条？", "会真正删除，以后不再用它理解你。修订记录里会留下一笔。", "忘掉", "st-mirror"))) return;
    if (act === "edit") return editMem(m, root);
    try {
      setData(await api.memory(act, { id }));
      toast({ confirm: "记下了", reject: "删掉了，谢谢你纠正我", forget: "忘掉了" }[act], "", "st-mirror");
      renderSpace(root);
    } catch (e) { toast(e.message, "err"); }
  }));
  body.querySelector("#addMem").addEventListener("click", async () => {
    const inp = body.querySelector("#newMem");
    if (!inp.value.trim()) return inp.focus();
    setData(await api.memory("add", { text: inp.value.trim() }));
    toast("写进记忆了", "", "st-mirror");
    renderSpace(root);
  });
}

function editMem(m, root) {
  const input = h("textarea", { class: "field", rows: "2", maxlength: "120" });
  input.value = m.text;
  const s = sheet({
    title: "改一条记忆", sticker: "st-mirror", body: input,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"),
      h("button", { class: "btn btn-lamp", onclick: async () => {
        if (!input.value.trim()) return;
        setData(await api.memory("edit", { id: m.id, text: input.value.trim() }));
        s.close(); toast("改好了，旧的说法留在修订记录里", "", "st-mirror"); renderSpace(root);
      } }, "保存")],
  });
  setTimeout(() => input.focus(), 60);
}

function digestTab(body, root) {
  const list = state.data.digests || [];
  body.innerHTML = `
    <section class="night card">
      <div class="night-ball"></div>
      <div class="night-copy">
        <h2>每天夜里，小光会安静地整理一遍</h2>
        <p>不是每句话都记。只挑真正发生的事：新的偏好、你的更正、值得留下的瞬间。你明确让它记住的，绝不会因为时间久了被偷偷忘掉；它猜的，要你点头才算数。</p>
        <button class="btn btn-sky btn-lg" data-run><img src="${art("st-moon")}" alt="">现在整理一下今天</button>
      </div>
    </section>
    <div class="digests">
      ${list.map((x, i) => `<div class="dg card" style="--i:${i}">
        <div class="dg-head"><img src="${art("st-moon")}" alt=""><b>${esc(fmtDay(x.day + "T12:00:00+08:00"))}</b><span class="muted">${esc(x.day)}</span>
          ${x.by_model ? "" : '<span class="pill">模板小结</span>'}</div>
        <p class="dg-sum">${esc(x.summary)}</p>
        ${x.highlights?.length ? `<div class="dg-hl">${x.highlights.map((t) => `<span class="pill lamp">✦ ${esc(t)}</span>`).join("")}</div>` : ""}
        ${x.ops?.length ? `<div class="dg-ops">${x.ops.map((o) => `<div class="op ${o.op.toLowerCase()} ${o.status === "guess" ? "guess" : ""}">
          <span class="op-k">${o.op === "ADD" ? (o.status === "guess" ? "猜了一条" : "新记住") : o.op === "UPDATE" ? "更新" : "删掉"}</span>
          <span>${o.op === "UPDATE" ? `<s>${esc(o.old)}</s> → ` : ""}${esc(o.text || o.old)}</span></div>`).join("")}</div>`
          : `<div class="muted" style="font-size:13px">这一天没有需要改动的记忆。</div>`}
      </div>`).join("") || ""}
    </div>`;
  const ball = mountBall(body.querySelector(".night-ball"), { size: 96, emotion: "00" });
  body.querySelector("[data-run]").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.classList.add("off"); b.lastChild.textContent = "正在整理…";
    ball.set("recall"); ball.pulse("spin");
    try {
      const out = await api.digest();
      setData(out);
      const dg = out.digest;
      if (dg.skipped) { toast("今天还没有可整理的内容", "", "st-moon"); ball.set("sleep"); }
      else {
        ball.set("done");
        burstAt(b, 40);
        toast(`整理好了：新记 ${dg.stats.added}，更新 ${dg.stats.updated}，待确认 ${dg.stats.guesses}`, "", "st-moon");
      }
      setTimeout(() => renderSpace(root), 900);
    } catch (err) {
      toast(err.message, "err"); ball.set("error");
      b.classList.remove("off"); b.lastChild.textContent = "现在整理一下今天";
    }
  });
}

function timelineTab(body) {
  const act = state.data.activity || [];
  const ART = { plan: "st-flag", record: "st-jar", memory: "st-mirror", scene: "st-lotus", growth: "st-seed", onboarding: "st-compass", profile: "st-compass", proactive: "st-letter", step: "st-flag" };
  body.innerHTML = `<div class="tl">${act.map((a, i) => `<div class="tl-row" style="--i:${i}">
    <img src="${art(ART[a.kind] || "st-seed")}" alt=""><div><div>${esc(a.text)}</div><span class="muted">${esc(fmtDay(a.at))} ${esc((a.at || "").slice(11, 16))}</span></div></div>`).join("")
    || `<div class="empty"><img src="${art("st-seed")}" alt=""><p>还没有动静。</p></div>`}</div>`;
}

function settingsTab(body, root) {
  const p = state.data.profile || {};
  const seg = (key, opts, cur) => `<div class="seg" data-key="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${cur === v ? "on" : ""}">${l}</button>`).join("")}</div>`;
  body.innerHTML = `
    <div class="card settings">
      <div class="set-row"><img src="${art("st-compass")}" alt=""><div class="sl"><b>中断的时候，你希望我</b><small>三天没动时小光的反应方式。也会写进「重新认识我」。</small></div>
        ${seg("care_style", [["nudge", "轻轻提醒"], ["analyze", "一起找原因"], ["quiet", "先别提"]], p.care_style)}</div>
      <div class="set-row"><img src="${art("st-letter")}" alt=""><div class="sl"><b>主动消息</b><small>只在网页里出现，第一版不做手机推送。23:00–08:00 不打扰。</small></div>
        ${seg("proactive", [["more", "多一点"], ["normal", "刚好"], ["less", "少一点"], ["off", "不要"]], p.proactive || "normal")}</div>
      <div class="set-row"><img src="${art("st-seed")}" alt=""><div class="sl"><b>宠物的名字</b><small>它现在叫「${esc(p.pet_name || "小芽")}」</small></div>
        <button class="btn btn-sm btn-ghost" data-rename>改名</button></div>
      <div class="set-row"><img src="${art("st-steps")}" alt=""><div class="sl"><b>再走一遍「重新认识我」</b><small>六个小问题，答完会更新上面的偏好</small></div>
        <button class="btn btn-sm btn-ghost" data-relearn>开始</button></div>
      <div class="set-row"><img src="${art("st-chest")}" alt=""><div class="sl"><b>导出我的数据</b><small>画像、记忆、计划、对话，全部是你的</small></div>
        <button class="btn btn-sm btn-ghost" data-export>导出 JSON</button></div>
      <div class="set-row"><img src="${art("st-letter")}" alt=""><div class="sl"><b>演示：让小光现在说一句</b><small>正常情况下由定时任务在合适的时候发</small></div>
        <button class="btn btn-sm btn-ghost" data-proactive>试一下</button></div>
    </div>
    <p class="hint-line">每个账号在服务器上是一个独立的数据库文件；接口只认登录会话，没有任何参数能读到别人的数据。删除记忆是真删除。</p>`;

  body.querySelectorAll(".seg").forEach((sg) => sg.querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    setData(await api.profile({ [sg.dataset.key]: b.dataset.v }));
    toast("改好了", "", "st-compass");
    renderSpace(root);
  })));
  body.querySelector("[data-relearn]").addEventListener("click", () => startScene("relearn", { onFinish: () => renderSpace(root) }));
  body.querySelector("[data-rename]").addEventListener("click", () => {
    const input = h("input", { class: "field", maxlength: "8" });
    input.value = p.pet_name || "小芽";
    const s = sheet({ title: "给宠物起个名字", sticker: "st-seed", body: input, footer: [h("button", { class: "btn btn-lamp", onclick: async () => {
      setData(await api.profile({ pet_name: input.value.trim() || "小芽" })); s.close(); renderSpace(root);
    } }, "就叫这个")] });
  });
  body.querySelector("[data-export]").addEventListener("click", async () => {
    const blob = new Blob([JSON.stringify(await api.exportAll(), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `xianban-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  body.querySelector("[data-proactive]").addEventListener("click", async () => {
    const out = await api.proactiveNow();
    setData(out);
    toast(out.sent ? "小光发了一句话，去对话里看看" : out.reason, "", "st-letter");
    if (out.sent) go("chat");
  });
}
