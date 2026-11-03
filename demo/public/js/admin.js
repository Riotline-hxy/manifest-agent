// 管理后台：登录 → 概览（数字、按天的图、漏斗、服务器）→ 用户列表 → 单个用户（含经验和金币的账、后台调整）；
// 「小镇」页：素材库里每样东西的价格、解锁等级、上下架，保存后所有人立刻生效。
import { get, post } from "./api.js";
import { esc, icon, tile, toast, sheet, h } from "./ui.js";
import { itemArt, setKinds, COIN_SVG } from "./town.js";

const C = { violet: "#7f70e0", mint: "#2a9c76" };  // 已在深色底上验证过（亮度带、色盲区分、对比度）
const KIND = { member: "注册", guest: "体验账号" };
const PERSONA = { gentle: "温柔", clear: "有条理", lively: "活泼" };
const CARE = { nudge: "轻轻提醒", analyze: "一起找原因", quiet: "先不提" };
const ACT = { onboarding: "建档", plan: "计划", record: "记录", memory: "记忆", profile: "资料", rest: "休息",
  proactive: "主动消息", task: "例行任务", wish: "愿望", habit: "习惯", scene: "引导", growth: "成长" };

const root = document.getElementById("admin");
let days = 30;
let users = [];
let filter = "all";
let query = "";
let page = "home";

const num = (n) => (n == null ? "—" : n >= 10000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1) + "K" : String(n));
const ago = (iso) => {
  if (!iso) return "—";
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 2) return "刚刚";
  if (m < 60) return `${Math.round(m)} 分钟前`;
  if (m < 1440) return `${Math.round(m / 60)} 小时前`;
  if (m < 1440 * 30) return `${Math.round(m / 1440)} 天前`;
  return iso.slice(0, 10);
};
const md = (d) => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;
const dur = (s) => (s < 3600 ? `${Math.round(s / 60)} 分钟` : s < 86400 ? `${(s / 3600).toFixed(1)} 小时` : `${(s / 86400).toFixed(1)} 天`);
const userName = (u) => u.username || `体验账号 ${u.id.slice(2, 8)}`;

async function start() {
  try {
    await load();
  } catch (e) {
    if (e.status === 401 || e.status === 404) login(e.status === 404 ? e.message : "");
    else root.innerHTML = `<div class="adm-empty">${esc(e.message)}</div>`;
  }
}

// ---------------------------------------------------------------- 登录 ----
function login(note) {
  root.innerHTML = `
    <form class="adm-login card">
      ${tile("lock", "var(--accent)", 48)}
      <h1>显伴后台</h1>
      <p>${esc(note || "输入管理口令。口令在服务器的 .env 里（MANIFEST_ADMIN_KEY）。")}</p>
      <input class="field" type="password" autocomplete="current-password" placeholder="管理口令" ${note ? "disabled" : ""}>
      <p class="adm-err"></p>
      <button class="btn btn-main btn-lg" ${note ? "disabled" : ""}>进入</button>
    </form>`;
  const f = root.querySelector("form");
  const inp = f.querySelector("input");
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await post("/api/admin/login", { key: inp.value });
      await load();
    } catch (err) {
      f.querySelector(".adm-err").textContent = err.message;
    }
  });
  inp.focus();
}

// ---------------------------------------------------------------- 主页 ----
async function load() {
  if (page === "town") return loadTown();
  const [ov, us] = await Promise.all([get(`/api/admin/overview?days=${days}`), get("/api/admin/users")]);
  if (page !== "home") return;            // 等的时候切到别的页了
  users = us.users;
  draw(ov);
}

const pages = () => `<nav class="adm-pages">${[["home", "概览"], ["town", "小镇"]].map(([k, l]) =>
  `<button class="chip ${page === k ? "on" : ""}" data-page="${k}">${l}</button>`).join("")}</nav>`;
function bindPages() {
  root.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => {
    if (page === b.dataset.page) return;
    if (page === "town" && Object.keys(edits).length && !confirm("有没保存的改动，确定离开？")) return;
    page = b.dataset.page;
    edits = {};
    load().catch(fail);
  }));
}

function draw(ov) {
  const u = ov.users, a = ov.active, s = ov.system;
  root.innerHTML = `
    <header class="adm-top">
      <b class="adm-logo">${icon("shield")}显伴后台</b>
      ${pages()}
      <div class="adm-range" role="group" aria-label="时间范围">
        ${[7, 30, 90].map((n) => `<button class="chip ${n === days ? "on" : ""}" data-days="${n}">近 ${n} 天</button>`).join("")}
      </div>
      <span class="spacer"></span>
      <span class="adm-stamp">更新于 ${new Date().toTimeString().slice(0, 5)}</span>
      <button class="btn btn-ghost btn-sm" data-act="refresh">刷新</button>
      <button class="btn btn-quiet btn-sm" data-act="logout">退出</button>
    </header>
    <main class="adm">
      <section class="adm-hero card">
        <div class="hero-n num">${num(u.members)}</div>
        <div class="hero-k">注册用户</div>
        <div class="hero-sub">已建档 ${u.onboarded} · 另有体验账号 ${u.guests}</div>
      </section>
      <section class="adm-stats">
        ${stat("今天活跃", a.today, "注册用户里发过消息或做过操作的")}
        ${stat("7 天活跃", a.week, "")}
        ${stat("30 天活跃", a.month, "")}
        ${stat("回访过", u.returning, "注册用户里活跃过 2 天以上的")}
        ${stat("今天的消息", ov.msgs_today, "注册用户发给小光的")}
        ${stat(`近 ${ov.days} 天模型调用`, ov.model.calls, `${num(ov.model.tokens)} tokens（缓存 ${num(ov.model.cached)}）· 失败 ${ov.model.errors}`)}
      </section>
      <section class="adm-grid">
        ${chartCard("new", "每天新用户", "注册用户和体验账号分开算")}
        ${chartCard("active", "每天活跃用户", "注册用户里当天发过消息或做过操作的；旧体验账号带示例数据，不算")}
        ${chartCard("msgs", "每天用户消息", "注册用户发给小光的条数")}
        ${chartCard("tokens", "每天模型 tokens", "对话、记忆整理、体验等所有调用；中转服务每次会带上约 2.7 万 token 的自带提示；从 2.8.0 开始统计")}
      </section>
      <section class="adm-grid">
        <div class="card adm-card"><h3>首页体验漏斗</h3><p class="adm-sub">近 ${ov.days} 天 · 从 2.8.0 开始统计</p><div class="hbars" data-h="funnel"></div></div>
        <div class="card adm-card"><h3>大家想靠近的</h3><p class="adm-sub">注册用户建档时选的方向</p><div class="hbars" data-h="intents"></div></div>
      </section>
      <section class="card adm-card">
        <h3>谁用的 token 最多</h3><p class="adm-sub">近 ${ov.days} 天 · 点名字看详情 · 从 2.8.1 开始按人统计（首页体验不算在任何人头上）</p>
        <div class="hbars" data-h="tokens"></div>
      </section>
      <section class="card adm-card">
        <h3>服务器</h3>
        <div class="adm-sys">
          ${kv("版本", `${esc(s.version)} · Python ${esc(s.python)}`)}
          ${kv("已运行", dur(s.uptime_s))}
          ${kv("进程内存", s.rss_mb != null ? `${s.rss_mb} MB` : "—")}
          ${kv("机器负载（1/5/15 分钟）", s.load ? `${s.load.map((x) => x.toFixed(2)).join(" / ")} · ${s.cpus} 核` : "—")}
          ${kv("用户数据", `${s.data_mb} MB · 磁盘剩余 ${s.disk_free_gb} GB`)}
          ${kv("今天请求", `${num(s.req_today)} 次 · 平均 ${s.req_avg_ms ?? "—"} ms（含等模型的接口）· 超过 1 秒 ${s.req_slow_today} 次`)}
          ${kv("今天对话", `${num(s.chat_today)} 轮 · 平均 ${s.chat_avg_s ?? "—"} 秒`)}
          ${kv("对话并发", `现在 ${s.chat_now} · 今天最高 ${s.chat_peak_today}`)}
          ${kv("开了手机通知", `${s.push_users} 人 · ${s.push_devices} 台设备`)}
        </div>
      </section>
      <section class="card adm-card">
        <div class="adm-users-head">
          <h3>用户</h3>
          <div class="adm-range">${[["all", "全部"], ["member", "注册"], ["guest", "体验账号"]].map(([k, l]) =>
            `<button class="chip ${k === filter ? "on" : ""}" data-filter="${k}">${l}</button>`).join("")}</div>
          <span class="spacer"></span>
          ${u.guests ? `<button class="btn btn-quiet btn-sm adm-danger-text" data-act="purge">清理 ${u.guests} 个体验账号</button>` : ""}
          <input class="field adm-search" type="search" placeholder="搜用户名" value="${esc(query)}">
        </div>
        <p class="adm-sub">按最近活跃排序。点一行看详情。这里只有数量和操作记录，看不到对话和记忆原文。</p>
        <div class="adm-table-wrap"><table class="adm-table"><thead><tr>
          <th>用户</th><th>类型</th><th>注册于</th><th>最近活跃</th><th class="r">活跃天数</th><th class="r">消息</th>
          <th class="r">一小步</th><th class="r">好消息</th><th class="r">记忆</th><th class="r">等级</th><th class="r">金币</th><th class="r">30 天 tokens</th><th>想靠近</th>
        </tr></thead><tbody></tbody></table></div>
      </section>
    </main>`;

  const series = ov.series;
  columns(root.querySelector('[data-c="new"]'), series, [
    { key: "new_member", label: "注册", color: C.violet }, { key: "new_guest", label: "体验账号", color: C.mint }]);
  columns(root.querySelector('[data-c="active"]'), series, [{ key: "active", label: "活跃用户", color: C.violet }]);
  columns(root.querySelector('[data-c="msgs"]'), series, [{ key: "msgs", label: "消息", color: C.violet }]);
  columns(root.querySelector('[data-c="tokens"]'), series.map((d) => ({ ...d, fresh: Math.max(0, d.tokens - d.cached) })), [
    { key: "fresh", label: "未缓存", color: C.violet }, { key: "cached", label: "缓存命中", color: C.mint }]);
  hbars(root.querySelector('[data-h="funnel"]'), ov.funnel, "还没有人试过");
  hbars(root.querySelector('[data-h="intents"]'), ov.intents, "还没有人建档");
  hbars(root.querySelector('[data-h="tokens"]'), ov.top_tokens, "还没有按人记录的用量", (r) => openUser(r.id));
  drawUsers();

  bindPages();
  root.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => { days = +b.dataset.days; load().catch(fail); }));
  root.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
    filter = b.dataset.filter;
    root.querySelectorAll("[data-filter]").forEach((x) => x.classList.toggle("on", x === b));
    drawUsers();
  }));
  root.querySelector(".adm-search").addEventListener("input", (e) => { query = e.target.value.trim(); drawUsers(); });
  root.querySelector("[data-act=refresh]").addEventListener("click", () => load().then(() => toast("已刷新")).catch(fail));
  root.querySelector("[data-act=purge]")?.addEventListener("click", () => purgeGuests(u.guests));
  root.querySelector("[data-act=logout]").addEventListener("click", async () => { await post("/api/admin/logout"); login(""); });
}

const fail = (e) => (e.status === 401 ? login("登录过期了，再输一次口令。") : toast(e.message, "err"));
const stat = (k, v, sub) => `<div class="card adm-stat"><div class="st-k">${esc(k)}</div><div class="st-v num">${num(v)}</div>${sub ? `<div class="st-sub">${esc(sub)}</div>` : ""}</div>`;
const kv = (k, v) => `<div class="kv"><span>${esc(k)}</span><b>${v}</b></div>`;
const chartCard = (id, title, sub) => `<div class="card adm-card"><h3>${esc(title)}</h3><p class="adm-sub">${esc(sub)}</p><div class="chart" data-c="${id}"></div></div>`;

function drawUsers() {
  const q = query.toLowerCase();
  const list = users.filter((u) => (filter === "all" || u.kind === filter) && (!q || (u.username || "").toLowerCase().includes(q)));
  const tb = root.querySelector(".adm-table tbody");
  tb.innerHTML = list.length ? list.map((u) => `
    <tr data-id="${esc(u.id)}" tabindex="0">
      <td><b>${esc(userName(u))}</b></td>
      <td><span class="pill ${u.kind === "member" ? "acc" : ""}">${KIND[u.kind] || esc(u.kind)}</span></td>
      <td>${esc((u.created_at || "").slice(0, 10))}</td>
      <td>${esc(ago(u.last_active))}</td>
      <td class="r num">${u.days_active}</td>
      <td class="r num">${u.msgs}</td>
      <td class="r num">${u.steps_done}/${u.steps}</td>
      <td class="r num">${u.good}</td>
      <td class="r num">${u.memories}</td>
      <td class="r num">${u.level}</td>
      <td class="r num">${num(u.coins)}</td>
      <td class="r num">${num(u.tokens_30d)}</td>
      <td class="clip">${esc(u.profile?.intent_primary || "—")}</td>
    </tr>`).join("") : `<tr><td colspan="13" class="adm-none">没有符合的用户</td></tr>`;
  tb.querySelectorAll("tr[data-id]").forEach((tr) => {
    const open = () => openUser(tr.dataset.id);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
  });
}

// ---------------------------------------------------------------- 单个用户 ----
async function openUser(id) {
  let u;
  try { u = await get(`/api/admin/user?id=${encodeURIComponent(id)}`); } catch (e) { return fail(e); }
  const p = u.profile || {};
  const t30 = u.tokens.d30;
  const body = h("div", { class: "adm-user" });
  body.innerHTML = `
    <div class="adm-sys">
      ${kv("类型", KIND[u.kind] || esc(u.kind))}
      ${kv("注册于", esc((u.created_at || "").slice(0, 16).replace("T", " ")))}
      ${kv("最近活跃", esc(ago(u.last_active)))}
      ${kv("活跃天数", `${u.days_active} 天${u.first_active ? `（第一次 ${esc(u.first_active)}）` : ""}`)}
      ${kv("登录中的设备", u.sessions)}
      ${kv("开了手机通知", u.push_devices ? `${u.push_devices} 台设备` : "没开")}
      ${kv("数据大小", `${(u.bytes / 1024).toFixed(0)} KB`)}
    </div>
    <h4>建档</h4>
    <div class="adm-sys">
      ${kv("想靠近", esc(p.intent_primary || "—"))}
      ${kv("为什么", esc(p.intent_why || "—"))}
      ${kv("伙伴名字", esc(p.agent_name || "—"))}
      ${kv("性格 / 中断时", `${PERSONA[p.persona] || "—"} · ${CARE[p.care_style] || "—"}`)}
    </div>
    <h4>做了多少</h4>
    <div class="adm-mini-stats">
      ${[["消息", u.msgs], ["一小步完成", `${u.steps_done}/${u.steps}`], ["好消息", u.good], ["记忆", u.memories], ["习惯", u.habits], ["经验", u.xp]]
        .map(([k, v]) => `<div><b class="num">${v}</b><span>${k}</span></div>`).join("")}
    </div>
    <h4>经验和金币</h4>
    <div class="adm-growth" data-growth><p class="adm-sub">正在读…</p></div>
    <h4>近 30 天每天的消息</h4>
    <div class="chart chart-sm" data-u="msgs"></div>
    <h4>模型用量</h4>
    <div class="adm-mini-stats">
      ${[["近 30 天 tokens", num(t30.tokens)], ["近 30 天调用", num(t30.calls)], ["其中对话", num(t30.tokens_chat)],
         ["其中后台", num(t30.tokens_bg)], ["缓存命中", t30.tokens_in ? `${Math.round((t30.tokens_cached / t30.tokens_in) * 100)}%` : "—"],
         ["累计 tokens", num(u.tokens.all.tokens)]].map(([k, v]) => `<div><b class="num">${v}</b><span>${k}</span></div>`).join("")}
    </div>
    <p class="adm-sub adm-note">对话 = 和小光聊天时的调用；后台 = 夜里整理记忆、主动消息、例行任务等。从 2.8.1 开始记录。</p>
    <div class="chart chart-sm" data-u="tokens"></div>
    <h4>最近的操作记录</h4>
    <ul class="adm-acts">${(u.activity || []).map((x) => `<li><span class="pill">${esc(ACT[x.kind] || x.kind)}</span>
      <span class="t">${esc(x.text)}</span><time>${esc((x.at || "").slice(5, 16).replace("T", " "))}</time></li>`).join("") || `<li class="adm-none">还没有</li>`}</ul>
    <div class="adm-danger">
      <div><b>删除这个用户</b><span>账号、对话、记忆、计划、例行任务和用量记录全部删掉，不能恢复。</span></div>
      <button class="btn btn-danger btn-sm" data-act="del">删除…</button>
    </div>`;
  const s = sheet({ title: userName(u), sticker: "user", body });
  columns(body.querySelector('[data-u="msgs"]'), u.series, [{ key: "msgs", label: "消息", color: C.violet }], 120);
  columns(body.querySelector('[data-u="tokens"]'), u.series, [
    { key: "t_tokens_chat", label: "对话", color: C.violet }, { key: "t_tokens_bg", label: "后台", color: C.mint }], 120);
  body.querySelector("[data-act=del]").addEventListener("click", () => deleteUser(u, s));
  drawGrowth(body.querySelector("[data-growth]"), u);
}

// ---------------------------------------------------------------- 单个用户：经验和金币 ----
const KINDNOTE = { action: "行动", good: "记录", practice: "练习", checkin: "陪伴", daily: "每日任务", admin: "后台调整", first: "礼物",
  migrate: "开镇", buy: "建造", milestone: "里程碑", record: "记录", test: "测试" };

async function drawGrowth(box, u, g = null) {
  try { g = g || await get(`/api/admin/user/growth?id=${encodeURIComponent(u.id)}`); } catch (e) { box.innerHTML = `<p class="adm-err">${esc(e.message)}</p>`; return; }
  box.innerHTML = `
    <div class="adm-mini-stats">
      ${[["经验", g.xp], [g.floor > 1 ? `等级 · 保底 ${g.floor}` : "等级", `Lv ${g.level.lv}`], ["离下一级", g.level.to_next], ["金币", g.coins],
         ["小镇", `${g.town.size}×${g.town.size} · ${g.town.placed} 样`], ["仓库", g.town.warehouse]].map(([k, v]) => `<div><b class="num">${v}</b><span>${k}</span></div>`).join("")}
    </div>
    <div class="adm-growth-acts"><button class="btn btn-main btn-sm" data-adjust>调整经验和金币</button></div>
    ${g.adjustments.length ? `<p class="adm-sub">后台给 TA 做过的调整</p><ul class="adm-acts">${g.adjustments.map((a) => `<li><span class="pill">${a.xp ? `${a.xp > 0 ? "+" : ""}${a.xp} 经验` : ""}${a.xp && a.coins ? " · " : ""}${a.coins ? `${a.coins > 0 ? "+" : ""}${a.coins} 金币` : ""}</span>
      <span class="t">${esc(a.reason)}</span><time>${esc((a.at || "").slice(5, 16).replace("T", " "))}</time></li>`).join("")}</ul>` : ""}
    <details class="adm-ledger"><summary>账本 · 最近 ${g.ledger.length} 笔</summary>
      <table class="adm-table"><thead><tr><th>时间</th><th>类别</th><th>内容</th><th class="r">经验</th><th class="r">金币</th></tr></thead><tbody>
      ${g.ledger.map((r) => `<tr><td>${esc((r.at || "").slice(5, 16).replace("T", " "))}</td><td><span class="pill">${esc(KINDNOTE[r.kind] || r.kind)}</span></td>
        <td class="clip">${esc(r.note || "")}</td><td class="r num">${r.xp || ""}</td><td class="r num ${r.coins < 0 ? "neg" : ""}">${r.coins || ""}</td></tr>`).join("")
        || `<tr><td colspan="5" class="adm-none">还没有</td></tr>`}</tbody></table></details>`;
  box.querySelector("[data-adjust]").addEventListener("click", () => adjustSheet(box, u, g));
}

function adjustSheet(box, u, g) {
  const xp = h("input", { class: "field", type: "number", step: "1", placeholder: "0" });
  const coins = h("input", { class: "field", type: "number", step: "1", placeholder: "0" });
  const why = h("input", { class: "field", maxlength: "60", placeholder: "比如：活动奖励 / 补偿上次的 bug" });
  const after = h("p", { class: "adm-sub" });
  const err = h("p", { class: "adm-err" });
  const show = () => {
    const dx = +xp.value || 0, dc = +coins.value || 0;
    after.textContent = `调整后：经验 ${g.xp} → ${g.xp + dx}，金币 ${g.coins} → ${g.coins + dc}`;
  };
  [xp, coins].forEach((i) => i.addEventListener("input", show));
  show();
  const body = h("div", { class: "adm-adjust" },
    h("label", {}, "经验（减就写负数）"), xp, h("label", {}, "金币（减就写负数）"), coins, h("label", {}, "原因（会写进 TA 的成长账本）"), why, after, err);
  const ok = h("button", { class: "btn btn-main" }, "确认调整");
  const s = sheet({ title: `调整 ${userName(u)}`, sticker: "bolt", body, footer: [h("button", { class: "btn btn-quiet", onclick: () => s.close() }, "算了"), ok] });
  ok.addEventListener("click", async () => {
    ok.disabled = true;
    try {
      const out = await post("/api/admin/user/adjust", { id: u.id, xp: +xp.value || 0, coins: +coins.value || 0, reason: why.value });
      s.close();
      toast("调整好了");
      drawGrowth(box, u, out);
    } catch (e) { err.textContent = e.message; ok.disabled = false; }
  });
  setTimeout(() => xp.focus(), 60);
}

// ---------------------------------------------------------------- 小镇：全局调价格和解锁等级 ----
let townData = null;
let edits = {};          // id → {price, lv, enabled, name} | null（恢复默认）
let townCat = "all";

async function loadTown() {
  const data = await get("/api/admin/town");
  if (page !== "town") return;
  townData = data;
  setKinds(Object.fromEntries(townData.items.map((i) => [i.id, i])));
  drawTown();
}

const cur = (it) => (edits[it.id] === null ? { ...it, ...it.default } : { ...it, ...(edits[it.id] || {}) });

function drawTown() {
  const D = townData;
  const list = D.items.filter((i) => townCat === "all" || (townCat === "off" ? !cur(i).enabled && !i.gift : i.cat === townCat));
  const n = Object.keys(edits).length;
  root.innerHTML = `
    <header class="adm-top">
      <b class="adm-logo">${icon("shield")}显伴后台</b>
      ${pages()}
      <span class="spacer"></span>
      <button class="btn btn-quiet btn-sm" data-act="logout">退出</button>
    </header>
    <main class="adm">
      <section class="card adm-card">
        <div class="adm-users-head"><h3>小镇里的东西</h3>
          <div class="adm-range">${[["all", "全部"], ...Object.entries(D.cats), ["off", "未上架"]].map(([k, l]) =>
            `<button class="chip ${townCat === k ? "on" : ""}" data-cat="${k}">${esc(l)}</button>`).join("")}</div></div>
        <p class="adm-sub">素材库：<code>demo/public/js/buildings/</code>。新放进来的默认不上架；改完点「保存」，所有人立刻生效。${D.updated_at ? ` 上次保存 ${esc(D.updated_at.slice(0, 16).replace("T", " "))}` : ""}</p>
        <div class="adm-table-wrap"><table class="adm-table adm-town"><thead><tr>
          <th></th><th>名字</th><th>占地</th><th>类别</th><th class="r">价格</th><th class="r">解锁等级</th><th>上架</th><th>状态</th>
        </tr></thead><tbody>${list.map(row).join("")}</tbody></table></div>
      </section>
      <section class="card adm-card"><h3>解锁节奏</h3><p class="adm-sub">按现在填的值算；土地和每级经验是代码里定的</p>
        <div class="adm-rhythm">${rhythm()}</div></section>
    </main>
    <div class="adm-savebar ${n ? "on" : ""}"><span>${n} 样有改动</span><span class="spacer"></span>
      <button class="btn btn-quiet btn-sm" data-act="discard">放弃</button><button class="btn btn-main btn-sm" data-act="save">保存</button></div>`;
  bindPages();
  root.querySelector("[data-act=logout]").addEventListener("click", async () => { await post("/api/admin/logout"); login(""); });
  root.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => { townCat = b.dataset.cat; drawTown(); }));
  root.querySelectorAll("tr[data-id]").forEach((tr) => {
    const it = D.items.find((i) => i.id === tr.dataset.id);
    const set = (f, v) => {
      const e = edits[it.id] === null ? {} : { ...(edits[it.id] || {}) };
      e[f] = v;
      const same = ["price", "lv", "enabled", "name"].every((k) => (k in e ? e[k] : it[k]) === it[k]);
      if (same) delete edits[it.id]; else edits[it.id] = e;
      drawTown();
    };
    tr.querySelectorAll("input[data-f]").forEach((inp) => inp.addEventListener("change", () =>
      set(inp.dataset.f, inp.type === "number" ? Math.max(0, Math.round(+inp.value || 0)) : inp.value.trim())));
    tr.querySelector("[data-f=enabled]")?.addEventListener("click", () => set("enabled", !cur(it).enabled));
    tr.querySelector("[data-reset]")?.addEventListener("click", () => { edits[it.id] = null; drawTown(); });
  });
  root.querySelector("[data-act=discard]").addEventListener("click", () => { edits = {}; drawTown(); });
  root.querySelector("[data-act=save]").addEventListener("click", saveTown);
}

function row(it) {
  const e = cur(it);
  const changed = it.id in edits;
  const status = it.gift ? "礼物，不卖" : changed ? (edits[it.id] === null ? "将恢复默认" : "改了，没保存") : it.fresh ? "新放进来" : Object.keys(it.override).length ? "后台改过" : "默认";
  const lock = it.gift ? "disabled" : "";
  return `<tr data-id="${esc(it.id)}" class="${changed ? "dirty" : ""} ${e.enabled || it.gift ? "" : "off"}">
    <td class="adm-prev">${itemArt(it.id)}</td>
    <td><input class="field adm-in" data-f="name" maxlength="10" value="${esc(e.name)}"><small class="muted">${esc(it.id)}</small></td>
    <td>${it.size.join("×")}</td><td>${esc(townData.cats[it.cat] || it.cat)}</td>
    <td class="r"><input class="field adm-in num" type="number" min="0" data-f="price" value="${e.price}" ${lock}></td>
    <td class="r"><input class="field adm-in num" type="number" min="1" data-f="lv" value="${e.lv}" ${lock}></td>
    <td>${it.gift ? "—" : `<button class="switch ${e.enabled ? "on" : ""}" data-f="enabled" aria-label="上架"><i></i></button>`}</td>
    <td><span class="pill ${changed ? "acc" : it.fresh ? "good" : ""}">${status}</span>${Object.keys(it.override).length && !changed ? `<button class="adm-link" data-reset>恢复默认</button>` : ""}</td>
  </tr>`;
}

function rhythm() {
  const D = townData;
  const sale = D.items.filter((i) => !i.gift && cur(i).enabled);
  const lvs = [...new Set([...sale.map((i) => cur(i).lv), ...D.land.map((l) => l.lv)])].sort((a, b) => a - b);
  return lvs.map((lv) => {
    const names = sale.filter((i) => cur(i).lv === lv).map((i) => `${cur(i).name}${COIN_SVG}${cur(i).price}`);
    const land = D.land.find((l) => l.lv === lv);
    return `<div class="adm-rh"><b>Lv ${lv}</b><span>${names.join("、") || ""}${land ? `${names.length ? "；" : ""}土地 ${land.size}×${land.size}` : ""}</span></div>`;
  }).join("") + `<p class="adm-sub">累计经验：${D.levels.map((l) => `Lv${l.lv} ${l.xp}`).join(" · ")}</p>`;
}

async function saveTown() {
  try {
    townData = await post("/api/admin/town", { items: edits });
    edits = {};
    setKinds(Object.fromEntries(townData.items.map((i) => [i.id, i])));
    drawTown();
    toast("保存好了，所有人立刻生效");
  } catch (e) { toast(e.message, "err"); }
}

// ---------------------------------------------------------------- 删除 ----
// 必须手打一遍确认内容，后端也会再核对一次
function confirmTyped({ title, text, phrase, okLabel }) {
  return new Promise((resolve) => {
    const inp = h("input", { class: "field", placeholder: phrase, autocomplete: "off" });
    const err = h("p", { class: "adm-err" });
    const ok = h("button", { class: "btn btn-danger", disabled: true }, okLabel);
    const cancel = h("button", { class: "btn btn-quiet" }, "算了");
    const body = h("div", {}, h("p", { class: "adm-confirm-text" }, text),
      h("p", { class: "adm-confirm-text" }, "请输入 ", h("b", {}, phrase), " 确认："), inp, err);
    let done = false;
    const s = sheet({ title, sticker: "trash", body, footer: [cancel, ok], onClose: () => { if (!done) resolve(null); } });
    inp.addEventListener("input", () => { ok.disabled = inp.value.trim() !== phrase; });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !ok.disabled) ok.click(); });
    cancel.addEventListener("click", () => s.close());
    ok.addEventListener("click", () => { done = true; resolve({ value: inp.value.trim(), close: s.close, err }); });
    setTimeout(() => inp.focus(), 60);
  });
}

async function deleteUser(u, detail) {
  const phrase = u.username || u.id;
  const r = await confirmTyped({
    title: `删除 ${userName(u)}`, phrase, okLabel: "永久删除",
    text: `会删掉 TA 的账号和全部数据（${u.msgs} 条消息、${u.memories} 条记忆、${u.steps} 个一小步），TA 会立刻被登出。不能恢复。`,
  });
  if (!r) return;
  try {
    await post("/api/admin/user/delete", { id: u.id, confirm: r.value });
    r.close();
    detail.close();
    toast(`已删除 ${userName(u)}`);
    await load();
  } catch (e) { r.err.textContent = e.message; }
}

async function purgeGuests(n) {
  const phrase = `删除 ${n} 个体验账号`;
  const r = await confirmTyped({
    title: "清理体验账号", phrase, okLabel: "全部删除",
    text: `体验账号是旧版首页「先体验一下」建的，里面大多是示例数据。会删掉全部 ${n} 个，注册用户不受影响。不能恢复。`,
  });
  if (!r) return;
  try {
    const out = await post("/api/admin/guests/delete", { confirm: r.value });
    r.close();
    toast(`删掉了 ${out.deleted} 个体验账号`);
    await load();
  } catch (e) { r.err.textContent = e.message; }
}

// ---------------------------------------------------------------- 图 ----
// 柱状图（可堆叠）：柱宽 ≤24px、顶端 4px 圆角、段之间 2px 间隙；悬停 / 聚焦出提示；下面能展开数据表。
function columns(el, data, series, height = 180) {
  const W = Math.max(280, el.clientWidth || 520);
  const H = height, padL = 34, padB = 22, padT = 8;
  const total = (d) => series.reduce((s, x) => s + (d[x.key] || 0), 0);
  const max = niceMax(Math.max(1, ...data.map(total)));
  const band = (W - padL) / data.length;
  const bw = Math.min(24, Math.max(3, band - 2));
  const y = (v) => padT + (H - padT - padB) * (1 - v / max);
  const ticks = [0, max / 2, max];
  const lastDay = data.length - 1;
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(series.map((s) => s.label).join("、"))}">`;
  for (const t of ticks) {
    svg += `<line x1="${padL}" x2="${W}" y1="${y(t)}" y2="${y(t)}" class="grid"/><text x="${padL - 6}" y="${y(t) + 4}" class="tick" text-anchor="end">${num(Math.round(t))}</text>`;
  }
  data.forEach((d, i) => {
    const x = padL + band * i + (band - bw) / 2;
    let base = y(0);
    const segs = series.filter((s) => d[s.key] > 0);
    segs.forEach((s, j) => {
      const gap = j > 0 ? 2 : 0;
      const hgt = Math.max(1, y(0) - y(d[s.key]) - gap);
      const yy = base - gap - hgt;
      const r = j === segs.length - 1 ? Math.min(4, hgt, bw / 2) : 0;
      svg += `<path d="${roundTop(x, yy, bw, hgt, r)}" fill="${s.color}"/>`;
      base = yy;
    });
    svg += `<rect class="hit" x="${padL + band * i}" y="${padT}" width="${band}" height="${H - padT - padB}" data-i="${i}" tabindex="0"/>`;
    if (i === 0 || i === lastDay || i === Math.floor(lastDay / 2)) {
      svg += `<text x="${padL + band * i + band / 2}" y="${H - 6}" class="tick" text-anchor="${i === 0 ? "start" : i === lastDay ? "end" : "middle"}">${md(d.day)}</text>`;
    }
  });
  svg += `</svg>`;
  const legend = series.length > 1
    ? `<div class="legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("")}</div>` : "";
  el.innerHTML = `${legend}<div class="plot">${svg}<div class="tip" hidden></div></div>
    <details class="adm-data"><summary>看数据表</summary><table><thead><tr><th>日期</th>${series.map((s) => `<th class="r">${esc(s.label)}</th>`).join("")}</tr></thead>
    <tbody>${data.slice().reverse().map((d) => `<tr><td>${esc(d.day)}</td>${series.map((s) => `<td class="r num">${d[s.key] || 0}</td>`).join("")}</tr>`).join("")}</tbody></table></details>`;

  const plot = el.querySelector(".plot");
  const tip = el.querySelector(".tip");
  const show = (rect) => {
    const d = data[+rect.dataset.i];
    el.querySelectorAll(".hit.on").forEach((r) => r.classList.remove("on"));
    rect.classList.add("on");
    tip.replaceChildren();
    const head = document.createElement("div");
    head.className = "tip-d";
    head.textContent = d.day;
    tip.append(head);
    for (const s of series) {
      const row = document.createElement("div");
      row.className = "tip-r";
      const key = document.createElement("i");
      key.style.background = s.color;
      const v = document.createElement("b");
      v.textContent = String(d[s.key] || 0);
      const l = document.createElement("span");
      l.textContent = s.label;
      row.append(key, v, l);
      tip.append(row);
    }
    tip.hidden = false;
    const pr = plot.getBoundingClientRect(), rr = rect.getBoundingClientRect();
    const left = rr.left - pr.left + rr.width / 2;
    tip.style.left = `${Math.min(Math.max(left, 60), pr.width - 60)}px`;
  };
  const hide = () => { tip.hidden = true; el.querySelectorAll(".hit.on").forEach((r) => r.classList.remove("on")); };
  el.querySelectorAll(".hit").forEach((r) => {
    r.addEventListener("pointerenter", () => show(r));
    r.addEventListener("focus", () => show(r));
    r.addEventListener("blur", hide);
  });
  plot.addEventListener("pointerleave", hide);
}

function roundTop(x, y, w, h, r) {
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return Math.max(m * p, 2);
  return v;
}

// 横向条：值写在条的末端
function hbars(el, rows, empty, onPick) {
  if (!rows.length || rows.every((r) => !r.n)) {
    el.innerHTML = `<p class="adm-none">${esc(empty)}</p>`;
    return;
  }
  const max = Math.max(...rows.map((r) => r.n), 1);
  el.innerHTML = rows.map((r, i) => `<div class="hb ${onPick ? "pick" : ""}" data-i="${i}" ${onPick ? 'tabindex="0" role="button"' : ""}><span class="hb-l">${esc(r.label)}</span>
    <span class="hb-t"><i style="width:${Math.max(r.n ? 2 : 0, (r.n / max) * 100)}%;background:${C.violet}"></i><b class="num">${num(r.n)}</b></span></div>`).join("");
  if (onPick) el.querySelectorAll(".hb").forEach((b) => {
    const go = () => onPick(rows[+b.dataset.i]);
    b.addEventListener("click", go);
    b.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  });
}

let rz;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => root.querySelector(".adm") && load().catch(fail), 250); });

start();
