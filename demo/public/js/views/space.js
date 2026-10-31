// 我的空间：档案 · 记忆（可改可删、带修订记录）· 夜里的整理 · 时间线 · 设置（含氛围与小光的颜色）。
// 「重新认识我」不封在这里——它是点子里的体验；这里只看结果、随时改。
import { api } from "../api.js";
import { state, setData, go } from "../store.js";
import { esc, toast, sheet, h, confirmSheet, fmtDay, icon, tile } from "../ui.js";
import { burstAt } from "../fx.js";
import { mountBall, setAgentColor } from "../ball.js";
import { petSVG } from "../pet.js";
import { startScene } from "../scene.js";
import { THEMES, AGENT_COLORS, applyTheme, agentColor, themeOf } from "../theme.js";
import { themeCard, placeInd } from "../app.js";
import { openAccount, logout } from "../account.js";
import { pushSupport, pushOn, enablePush, disablePush, installState, install, PUSH_WHY } from "../push.js";

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
  const tab = state.spaceTab || "memory";
  root.innerHTML = `
    <div class="view-inner wide space">
      <section class="me-card card">
        <span class="me-av">${esc((p.nickname || state.user?.username || "我").slice(0, 1))}</span>
        <div class="me-main">
          <h1>${esc(p.nickname || state.user?.username || "你")}<button class="icon-btn sm me-edit" data-name-edit aria-label="改名字" title="改名字">${icon("edit")}</button></h1>
          <p>陪伴第 ${d.counts?.days || 1} 天 · 正在靠近「${esc(p.intent_primary || "还没想好")}」</p>
          <div class="me-stats">
            <span><b class="num">${mems.filter((m) => m.status === "active").length}</b>条记忆</span>
            <span><b class="num">${d.counts?.good || 0}</b>颗星</span>
            <span><b class="num">${d.counts?.done || 0}</b>个小步</span>
            <span><b class="num">${(g.badges || []).filter((b) => b.earned).length}</b>枚徽章</span>
          </div>
        </div>
        <div class="me-pet" data-go="growth">${petSVG(g.stage?.art || "pet-egg", { cls: "alive" })}</div>
      </section>
      <div class="tabs space-tabs">${TABS.map(([k, l]) => `<button class="${k === tab ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}<span class="ind"></span></div>
      <div class="space-body"></div>
    </div>`;
  root.querySelector("[data-name-edit]").addEventListener("click", () => nameSheet(root));
  const tabs = root.querySelector(".space-tabs");
  requestAnimationFrame(() => placeInd(tabs));
  tabs.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { state.spaceTab = b.dataset.tab; renderSpace(root); }));
  root.querySelector("[data-go]").addEventListener("click", () => go("growth"));
  ({ memory: memoryTab, digest: digestTab, timeline: timelineTab, settings: settingsTab })[tab](root.querySelector(".space-body"), root);
}

function memoryTab(body, root) {
  const mems = state.data.memories || [];
  const guesses = mems.filter((m) => m.status === "guess");
  const active = mems.filter((m) => m.status === "active");
  const revs = state.data.revisions || [];
  body.innerHTML = `
    ${guesses.length ? `<div class="sec-title">小光猜的，需要你点头<span class="more">点「对」才会用它理解你</span></div>
      <div class="mem-grid" style="margin-bottom:24px">${guesses.map((m) => `<div class="mem guess">
        <div class="mt">${esc(m.text)}</div>
        <div class="mm"><span class="pill acc">猜测</span><span class="muted">${esc(m.created_at.slice(5, 10))}</span></div>
        <div class="ma"><button class="btn btn-sm btn-good" data-act="confirm" data-id="${esc(m.id)}">对</button>
          <button class="btn btn-sm btn-ghost" data-act="reject" data-id="${esc(m.id)}">不太对</button></div></div>`).join("")}</div>` : ""}
    <div class="sec-title">小光记得的<span class="more">${active.length} 条</span></div>
    <div class="add-row" style="margin:0 0 14px">
      <input class="field" id="newMem" maxlength="120" placeholder="亲手写一条，比如「我喜欢吃寿司」">
      <button class="btn btn-main" id="addMem">写进去</button>
    </div>
    <div class="mem-grid">${active.map((m, i) => `<div class="mem" style="--i:${i}">
      <div class="mt">${esc(m.text)}</div>
      <div class="mm"><span class="pill good">${esc(KIND[m.kind] || "记忆")}</span><span class="pill">${esc(SRC(m.source))}</span><span class="muted">${esc(m.created_at.slice(5, 10))}</span></div>
      <div class="ma hover"><button class="icon-btn" title="改" data-act="edit" data-id="${esc(m.id)}">${icon("edit")}</button>
        <button class="icon-btn" title="忘掉" data-act="forget" data-id="${esc(m.id)}">${icon("trash")}</button></div>
    </div>`).join("") || `<div class="empty"><h3>还没有记住什么</h3><p>在对话里说「帮我记住……」，或者在上面亲手写一条。</p></div>`}</div>
    ${revs.length ? `<details class="fold card" style="margin-top:22px"><summary>${icon("clock")}修订记录 <span class="muted">· 每次改动都留着依据</span></summary>
      ${revs.map((r) => `<div class="rev"><span class="muted">${esc(r.at.slice(5, 16).replace("T", " "))}</span>
        <div><s>${esc(r.old_text || "")}</s>${r.new_text ? ` → <b>${esc(r.new_text)}</b>` : " <b>（已删除）</b>"}
        <small>${esc(r.reason?.startsWith("digest") ? "夜里整理" : REASON[r.reason] || r.reason)}${r.evidence ? `：「${esc(r.evidence)}」` : ""}</small></div></div>`).join("")}
    </details>` : ""}`;

  body.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    const { act, id } = b.dataset;
    const m = (state.data.memories || []).find((x) => x.id === id);
    if (act === "forget" && !(await confirmSheet("忘掉这条？", "会真正删除，以后不再用它理解你。修订记录里会留下一笔。", "忘掉", "trash"))) return;
    if (act === "edit") return editMem(m, root);
    try {
      setData(await api.memory(act, { id }));
      toast({ confirm: "记下了", reject: "删掉了，谢谢你纠正我", forget: "忘掉了" }[act]);
      renderSpace(root);
    } catch (e) { toast(e.message, "err"); }
  }));
  body.querySelector("#addMem").addEventListener("click", async () => {
    const inp = body.querySelector("#newMem");
    if (!inp.value.trim()) return inp.focus();
    setData(await api.memory("add", { text: inp.value.trim() }));
    toast("写进记忆了");
    renderSpace(root);
  });
}

function editMem(m, root) {
  const input = h("textarea", { class: "field", rows: "2", maxlength: "120" });
  input.value = m.text;
  const s = sheet({
    title: "改一条记忆", sticker: "edit", body: input,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"),
      h("button", { class: "btn btn-main", onclick: async () => {
        if (!input.value.trim()) return;
        setData(await api.memory("edit", { id: m.id, text: input.value.trim() }));
        s.close(); toast("改好了，旧的说法留在修订记录里"); renderSpace(root);
      } }, "保存")],
  });
  setTimeout(() => input.focus(), 60);
}

function digestTab(body, root) {
  const list = state.data.digests || [];
  const nb = state.data.profile?.notebook || {};
  body.innerHTML = `
    <section class="night card">
      <div class="night-ball"></div>
      <div class="night-copy">
        <h2>每天夜里，小光会安静地整理一遍</h2>
        <p>小光只挑真正发生的事来记：新的偏好、你的更正、值得留下的瞬间。你明确让它记住的，不会因为时间久了被偷偷忘掉；它猜的，要你点头才算数。</p>
        <button class="btn btn-main" data-run>${icon("moon")}现在整理一下今天</button>
      </div>
    </section>
    <section class="nb card">
      <div class="nb-head">${tile("book", "var(--c-violet)", 34)}<div><b>小光的笔记本</b>
        <small>${nb.updated_at ? `${esc(fmtDay(nb.updated_at))}${nb.by === "user" ? " · 你改过" : " · 夜里整理时更新"}` : "夜里整理时会开始写"}</small></div>
        <span class="sp"></span><button class="btn btn-sm btn-ghost" data-nb-edit>${icon("edit")}改一改</button></div>
      <p class="nb-why">小光平时只把最近三天的聊天原话放在心上；更早的，就靠这本笔记和每天的小结记得你。写错了可以直接改。</p>
      <div class="nb-text">${nb.text ? esc(nb.text) : '<span class="muted">还没有内容。</span>'}</div>
    </section>
    <div class="digests">${list.map((x, i) => `<div class="dg card" style="--i:${i}">
      <div class="dg-head">${tile("moon", "var(--c-violet)", 34)}<b>${esc(fmtDay(x.day + "T12:00:00+08:00"))}</b><span class="muted">${esc(x.day)}</span>
        ${x.by_model ? "" : '<span class="pill">模板小结</span>'}</div>
      <p class="dg-sum">${esc(x.summary)}</p>
      ${x.highlights?.length ? `<div class="dg-hl">${x.highlights.map((t) => `<span class="pill acc">${icon("sparkles")}${esc(t)}</span>`).join("")}</div>` : ""}
      ${x.ops?.length ? `<div class="dg-ops">${x.ops.map((o) => `<div class="op ${o.op.toLowerCase()} ${o.status === "guess" ? "guess" : ""}">
        <span class="op-k">${o.op === "ADD" ? (o.status === "guess" ? "猜了一条" : "新记住") : o.op === "UPDATE" ? "更新" : "删掉"}</span>
        <span>${o.op === "UPDATE" ? `<s>${esc(o.old)}</s> → ` : ""}${esc(o.text || o.old)}</span></div>`).join("")}</div>`
        : `<div class="muted" style="font-size:13px">这一天没有需要改动的记忆。</div>`}
    </div>`).join("")}</div>`;
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
  const ICON = { plan: "flag", record: "star", memory: "memory", scene: "wind", growth: "sprout", onboarding: "compass", profile: "settings", proactive: "letter", step: "flag" };
  body.innerHTML = `<div class="tl card">${(state.data.activity || []).map((a, i) => `<div class="act" style="--i:${i}">${icon(ICON[a.kind] || "checkc")}
    <div><div class="t">${esc(a.text)}</div><div class="w">${esc(fmtDay(a.at))} ${esc((a.at || "").slice(11, 16))}</div></div></div>`).join("")
    || `<div class="empty"><p>还没有动静。</p></div>`}</div>`;
}

function settingsTab(body, root) {
  const p = state.data.profile || {};
  const seg = (key, opts, cur) => `<div class="tabs seg" data-key="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${cur === v ? "on" : ""}">${l}</button>`).join("")}<span class="ind"></span></div>`;
  const cur = themeOf(p.theme).id;
  const col = agentColor(p);
  body.innerHTML = `
    <div class="sec-title">氛围<span class="more">适合不同的人，随时能换</span></div>
    <div class="theme-grid" style="margin-bottom:22px">${THEMES.map((t) => themeCard(t, t.id === cur)).join("")}</div>
    <div class="sec-title">小光的颜色</div>
    <div class="swatches" style="margin-bottom:28px">${AGENT_COLORS.map((c) => `<button class="swatch ${c === col ? "on" : ""}" data-color="${c}" style="background:${c}"></button>`).join("")}</div>
    <div class="settings card">
      <div class="set-row">${tile("chat", "var(--c-sky)", 40)}<div class="sl"><b>名字</b><small>小光叫你「${esc(p.nickname || state.user?.username || "你")}」${state.user?.kind === "member" ? ` · 登录用户名 ${esc(state.user.username)}` : ""}</small></div>
        <button class="btn btn-sm btn-ghost" data-name-edit2>修改</button></div>
      <div class="set-row">${tile("user", "var(--c-orange)", 40)}<div class="sl"><b>账号</b><small>${state.user?.kind === "guest" ? "现在是体验账号，注册后记录会一直留着" : `已登录：${esc(state.user?.username || "")}`}</small></div>
        <button class="btn btn-sm btn-ghost" data-account>${state.user?.kind === "guest" ? "注册 / 退出" : "退出登录"}</button></div>
      <div class="set-row">${tile("heart", "var(--c-pink)", 40)}<div class="sl"><b>小光的性格</b><small>说话的方式会跟着变，记得的事不变</small></div>
        ${seg("persona", [["gentle", "温柔"], ["clear", "有条理"], ["lively", "活泼"]], p.persona || "gentle")}</div>
      <div class="set-row">${tile("compass", "var(--c-mint)", 40)}<div class="sl"><b>中断的时候，你希望我</b><small>三天没动时小光的反应方式</small></div>
        ${seg("care_style", [["nudge", "轻轻提醒"], ["analyze", "一起找原因"], ["quiet", "先别提"]], p.care_style)}</div>
      <div class="set-row">${tile("letter", "var(--c-sky)", 40)}<div class="sl"><b>主动消息</b><small>23:00–08:00 不打扰；开了手机通知，网页关着也能收到</small></div>
        ${seg("proactive", [["more", "多"], ["normal", "刚好"], ["less", "少"], ["off", "不要"]], p.proactive || "normal")}</div>
      <div class="set-row">${tile("bell", "var(--c-lemon)", 40)}<div class="sl"><b>手机通知</b><small data-push-note>正在看这台设备……</small></div>
        <div class="set-acts" data-push-acts></div></div>
      <div class="set-row">${tile("phone", "var(--c-mint)", 40)}<div class="sl"><b>装到手机桌面</b><small data-install-note></small></div>
        <div class="set-acts" data-install-acts></div></div>
      <div class="set-row">${tile("sprout", "var(--c-orange)", 40)}<div class="sl"><b>宠物的名字</b><small>现在叫「${esc(p.pet_name || "小芽")}」</small></div>
        <button class="btn btn-sm btn-ghost" data-rename>改名</button></div>
      <div class="set-row">${tile("steps", "var(--c-violet)", 40)}<div class="sl"><b>再走一遍「重新认识我」</b><small>六个小问题，答完会更新上面的偏好</small></div>
        <button class="btn btn-sm btn-ghost" data-relearn>开始</button></div>
      <div class="set-row">${tile("download", "var(--c-coral)", 40)}<div class="sl"><b>导出我的数据</b><small>画像、记忆、计划、对话，全部是你的</small></div>
        <button class="btn btn-sm btn-ghost" data-export>导出</button></div>
      <div class="set-row">${tile("chat", "var(--c-pink)", 40)}<div class="sl"><b>演示：让小光现在说一句</b><small>正常由定时任务在合适的时候发</small></div>
        <button class="btn btn-sm btn-ghost" data-proactive>试一下</button></div>
    </div>
    <p class="hint-line">每个账号在服务器上是一个独立的数据库文件；接口只认登录会话，没有任何参数能读到别人的数据。删除记忆是真删除。</p>`;

  requestAnimationFrame(() => body.querySelectorAll(".seg").forEach(placeInd));
  bindDevice(body);
  const save = async (patch, msg) => {
    try { setData(await api.profile(patch)); if (msg) toast(msg); renderSpace(root); } catch (e) { toast(e.message, "err"); }
  };
  body.querySelectorAll("[data-theme-id]").forEach((b) => b.addEventListener("click", () => {
    const t = applyTheme(b.dataset.themeId);
    setAgentColor(t.agent);
    save({ theme: t.id, agent_hue: "" }, `换成「${t.name}」了`);
  }));
  body.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => {
    setAgentColor(b.dataset.color);
    save({ agent_hue: b.dataset.color }, "小光换好颜色了");
  }));
  body.querySelectorAll(".seg").forEach((sg) => sg.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => save({ [sg.dataset.key]: b.dataset.v }, "改好了"))));
  body.querySelector("[data-name-edit2]").addEventListener("click", () => nameSheet(root));
  body.querySelector("[data-account]").addEventListener("click", () => (state.user?.kind === "guest" ? openAccount() : confirmLogout()));
  body.querySelector("[data-relearn]").addEventListener("click", () => startScene("relearn", { onFinish: () => renderSpace(root) }));
  body.querySelector("[data-rename]").addEventListener("click", () => {
    const input = h("input", { class: "field", maxlength: "8" });
    input.value = p.pet_name || "小芽";
    const s = sheet({ title: "给宠物起个名字", sticker: "sprout", body: input, footer: [h("button", { class: "btn btn-main", onclick: async () => {
      s.close(); save({ pet_name: input.value.trim() || "小芽" });
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
    toast(out.sent ? "小光发了一句话，去对话里看看" : out.reason);
    if (out.sent) go("chat");
  });
}

// ---- 这台设备：手机通知 + 装到桌面 ----
function bindDevice(body) {
  const pNote = body.querySelector("[data-push-note]"), pActs = body.querySelector("[data-push-acts]");
  const iNote = body.querySelector("[data-install-note]"), iActs = body.querySelector("[data-install-acts]");
  const btn = (label, cls, fn) => h("button", { class: `btn btn-sm ${cls}`, onclick: fn }, label);

  async function drawPush() {
    const sup = pushSupport();
    const on = await pushOn();
    pActs.replaceChildren();
    if (on) {
      pNote.textContent = "已开启：小光的主动消息和到点提醒，网页关着也会推到这台设备";
      pActs.append(btn("发一条试试", "btn-ghost", testPush), btn("关闭", "btn-quiet", async () => {
        await disablePush(); toast("这台设备不再收通知了"); drawPush();
      }));
    } else if (sup === "ok") {
      pNote.textContent = "开了以后，网页关着也能收到小光的消息和提醒";
      pActs.append(btn("开启", "btn-main", async (e) => {
        e.currentTarget.classList.add("off");
        const r = await enablePush();
        toast(r.ok ? "开好了，点「发一条试试」看看" : PUSH_WHY[r.reason], r.ok ? "" : "err", r.ok ? "bell" : "");
        drawPush();
      }));
    } else {
      pNote.textContent = PUSH_WHY[sup];
      if (sup === "ios-home") pActs.append(btn("怎么添加", "btn-ghost", installGuide));
    }
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
  function drawInstall() {
    const st = installState();
    iActs.replaceChildren();
    iNote.textContent = {
      installed: "已经装好了，以后从桌面的「显伴」打开就行",
      prompt: "装好以后像 app 一样从桌面打开，也更容易收到通知",
      ios: "在 Safari 里点「分享」→「添加到主屏幕」",
      browser: "在浏览器菜单里找「添加到主屏幕」或「安装应用」",
    }[st];
    if (st === "prompt") iActs.append(btn("安装", "btn-main", async () => { if (await install()) toast("装好了，去桌面看看"); drawInstall(); }));
    else if (st !== "installed") iActs.append(btn("怎么装", "btn-ghost", installGuide));
  }
  drawPush();
  drawInstall();
  addEventListener("xg:installable", drawInstall, { once: true });
}

function installGuide() {
  const body = h("div", { class: "install-guide", html: `
    <h4>iPhone（用 Safari 打开）</h4>
    <ol><li>点屏幕底部的「分享」按钮（方框加向上的箭头）</li><li>往下滑，点「添加到主屏幕」，再点「添加」</li>
      <li>回到桌面，点「显伴」图标打开，登录后到「我的空间」开启手机通知</li></ol>
    <p class="hint">需要 iOS 16.4 或更新的版本；在微信里打开的页面不行，先用 Safari 打开。</p>
    <h4>安卓（用 Chrome 或手机自带浏览器）</h4>
    <ol><li>点右上角的「⋮」菜单</li><li>选「安装应用」或「添加到主屏幕」</li><li>从桌面图标打开，到「我的空间」开启手机通知</li></ol>
    <p class="hint">国内部分安卓手机的浏览器收不到网页通知（依赖谷歌的推送服务）；收不到时，消息会在你打开显伴时出现。</p>` });
  const s = sheet({ title: "装到手机桌面", sticker: "phone", body, footer: [h("button", { class: "btn btn-main", onclick: () => s.close() }, "知道了")] });
}

async function confirmLogout() {
  if (await confirmSheet("退出登录？", "下次用用户名和密码就能回来，记录都在。", "退出", "back")) logout();
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
