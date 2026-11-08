// 管理后台。左边五页：概览、用户（点进去是单个用户）、小镇、模型（切换小光用的模型和思考档）、记录。地址栏记着在哪一页（#users、#user/<id>、#town、#log），能前进后退。
// 只看数量和操作记录，看不到对话和记忆原文。能改的：删用户、给用户加减经验和金币、小镇里每样东西的价格 / 解锁等级 / 上下架。
import { get, post } from "./api.js";
import { esc, icon, tile, toast, sheet, h } from "./ui.js";
import { itemArt, setKinds, COIN_SVG } from "./town.js";

const C = { violet: "#7f70e0", mint: "#2a9c76" };  // 已在深色底上验证过（亮度带、色盲区分、对比度）
const KIND = { member: "注册", guest: "体验账号" };
const PERSONA = { gentle: "温柔", clear: "有条理", lively: "活泼" };
const CARE = { nudge: "轻轻提醒", analyze: "一起找原因", quiet: "先不提" };
const ACT = { onboarding: "建档", plan: "计划", record: "记录", memory: "记忆", profile: "资料", rest: "休息",
  proactive: "主动消息", task: "例行任务", wish: "愿望", habit: "习惯", scene: "引导", growth: "成长" };
const LEDGER = { action: "行动", good: "瞬间", practice: "练习", checkin: "陪伴", daily: "每日任务", admin: "后台调整", first: "礼物",
  migrate: "开镇", buy: "建造", milestone: "里程碑", record: "记录", test: "测试" };
const NAV = [["overview", "概览", "report"], ["users", "用户", "user"], ["town", "小镇", "home"], ["model", "模型", "bolt"], ["log", "记录", "list"]];

const root = document.getElementById("admin");
const S = {
  days: 30, filter: "all", query: "", sort: { key: "last_active", dir: -1 },
  town: null, edits: {}, cat: "all",   // edits：id → {price, lv, enabled, name} | null（恢复默认）
  redraw: null,                        // 窗口宽度变了只重画图，不重新请求
};
let seq = 0;

// ---------------------------------------------------------------- 小工具 ----
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
const when = (iso) => (iso || "").slice(5, 16).replace("T", " ");
const md = (d) => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;
const dur = (s) => (s < 3600 ? `${Math.round(s / 60)} 分钟` : s < 86400 ? `${(s / 3600).toFixed(1)} 小时` : `${(s / 86400).toFixed(1)} 天`);
const signed = (n) => (n > 0 ? `+${n}` : String(n));
const userName = (u) => u.username || `体验账号 ${u.id.slice(2, 8)}`;
const disabled = (e) => e.status === 404 && String(e.message).startsWith("后台未开启");

const head = (title, sub = "", right = "") =>
  `<header class="adm-head"><div><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ""}</div>${right ? `<div class="adm-head-r">${right}</div>` : ""}</header>`;
const seg = (name, opts, on) => `<div class="adm-seg" role="group">${opts.map(([k, l]) =>
  `<button class="${String(k) === String(on) ? "on" : ""}" data-${name}="${k}">${esc(l)}</button>`).join("")}</div>`;
const kpi = (k, v, sub = "") => `<div class="card adm-kpi"><span>${esc(k)}</span><b class="num">${typeof v === "number" ? num(v) : esc(v)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`;
const kv = (k, v) => `<div class="kv"><span>${esc(k)}</span><b>${v}</b></div>`;
const card = (title, sub, inner, cls = "") => `<div class="card adm-card ${cls}"><h3>${esc(title)}</h3>${sub ? `<p class="adm-sub">${esc(sub)}</p>` : ""}${inner}</div>`;
const chartCard = (id, title, sub = "") => card(title, sub, `<div class="chart" data-c="${id}"></div>`);
const on = (sel, ev, fn) => root.querySelectorAll(sel).forEach((el) => el.addEventListener(ev, fn));

const fail = (e) => (e.status === 401 ? login("登录过期了，再输一次口令。") : toast(e.message, "err"));

// ---------------------------------------------------------------- 外框和路由 ----
function route(hash = location.hash) {
  const [page, arg = ""] = hash.replace(/^#\/?/, "").split("/");
  return { page: PAGES[page] ? page : "overview", arg: decodeURIComponent(arg) };
}

function shell() {
  if (!root.querySelector(".adm-shell")) {
    root.innerHTML = `
      <div class="adm-shell">
        <aside class="adm-side">
          <b class="adm-logo">${icon("shield")}显伴后台</b>
          <nav>${NAV.map(([k, l, ic]) => `<a href="#${k}" data-nav="${k}">${icon(ic)}<span>${l}</span></a>`).join("")}</nav>
          <button class="adm-out" data-act="logout">退出</button>
        </aside>
        <main class="adm-main"></main>
      </div>`;
    root.querySelector("[data-act=logout]").addEventListener("click", async () => {
      if (dirty() && !confirm("小镇有改动还没保存，确定退出？")) return;
      await post("/api/admin/logout").catch(() => {});
      S.edits = {};
      login("");
    });
  }
  const r = route();
  const cur = r.page === "user" ? "users" : r.page;
  root.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === cur));
  return root.querySelector(".adm-main");
}

async function render() {
  const my = ++seq;
  const live = () => my === seq;
  const r = route();
  const main = shell();
  S.redraw = null;
  const wait = setTimeout(() => { if (live()) main.innerHTML = `<p class="adm-loading">正在读…</p>`; }, 180);
  try {
    await PAGES[r.page](main, r.arg, live);
  } catch (e) {
    if (!live()) return;
    if (e.status === 401 || disabled(e)) login(disabled(e) ? e.message : "");
    else main.innerHTML = `<div class="adm-empty">${esc(e.message)}</div>`;
  } finally {
    clearTimeout(wait);
  }
}

const dirty = () => Object.keys(S.edits).length > 0;
let lastHash = location.hash;
addEventListener("hashchange", () => {
  if (route(lastHash).page === "town" && route().page !== "town") {
    if (dirty() && !confirm("小镇有改动还没保存，确定离开？")) { history.replaceState(null, "", lastHash || "#town"); return; }
    S.edits = {};
  }
  lastHash = location.hash;
  scrollTo(0, 0);
  render();
});
addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
let rz;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => S.redraw?.(), 200); });

// ---------------------------------------------------------------- 登录 ----
function login(note) {
  seq++;
  root.innerHTML = `
    <form class="adm-login card">
      ${tile("lock", "var(--accent)", 48)}
      <h1>显伴后台</h1>
      <p>${esc(note || "输入管理口令。口令在服务器的 .env 里（MANIFEST_ADMIN_KEY）。")}</p>
      <input class="field" type="password" autocomplete="current-password" placeholder="管理口令" ${note && !note.startsWith("登录过期") ? "disabled" : ""}>
      <p class="adm-err"></p>
      <button class="btn btn-main btn-lg" ${note && !note.startsWith("登录过期") ? "disabled" : ""}>进入</button>
    </form>`;
  const f = root.querySelector("form");
  const inp = f.querySelector("input");
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await post("/api/admin/login", { key: inp.value });
      root.innerHTML = "";
      await render();
    } catch (err) {
      f.querySelector(".adm-err").textContent = err.message;
    }
  });
  inp.focus();
}

// ---------------------------------------------------------------- 概览 ----
async function overview(main, _, live) {
  const ov = await get(`/api/admin/overview?days=${S.days}`);
  if (!live()) return;
  const u = ov.users, a = ov.active, s = ov.system, m = ov.model;
  main.innerHTML = head("概览", `更新于 ${new Date().toTimeString().slice(0, 5)} · ${esc(s.version)}`,
    `${seg("days", [[7, "7 天"], [30, "30 天"], [90, "90 天"]], S.days)}<button class="btn btn-ghost btn-sm" data-act="refresh">刷新</button>`) + `
    <section class="adm-kpis">
      ${kpi("注册用户", u.members, `已建档 ${u.onboarded} · 体验账号 ${u.guests}`)}
      ${kpi("今天活跃", a.today, `7 天 ${a.week} · 30 天 ${a.month}`)}
      ${kpi("回访过", u.returning, "活跃过 2 天以上")}
      ${kpi("今天的消息", ov.msgs_today, "注册用户发给小光的")}
      ${kpi(`${ov.days} 天模型调用`, m.calls, `${num(m.tokens)} tokens · 失败 ${m.errors}`)}
    </section>
    <section class="adm-grid">
      ${chartCard("new", "每天新用户")}
      ${chartCard("active", "每天活跃用户", "注册用户里当天发过消息或做过操作的")}
      ${chartCard("msgs", "每天用户消息")}
      ${chartCard("tokens", "每天模型 tokens", "中转每次自带约 2.7 万 token 的提示，也算在里面")}
      ${card("首页体验漏斗", `近 ${ov.days} 天`, `<div class="hbars" data-h="funnel"></div>`)}
      ${card("大家想靠近的", "建档时选的方向", `<div class="hbars" data-h="intents"></div>`)}
      ${card("谁用的 token 最多", `近 ${ov.days} 天 · 点名字看这个人`, `<div class="hbars" data-h="tokens"></div>`)}
      ${card("服务器", "", `<div class="adm-kv">
        ${kv("版本", `${esc(s.version)} · Python ${esc(s.python)}`)}
        ${kv("已运行", dur(s.uptime_s))}
        ${kv("进程内存", s.rss_mb != null ? `${s.rss_mb} MB` : "—")}
        ${kv("负载 1/5/15 分钟", s.load ? `${s.load.map((x) => x.toFixed(2)).join(" / ")} · ${s.cpus} 核` : "—")}
        ${kv("用户数据", `${s.data_mb} MB · 磁盘剩 ${s.disk_free_gb} GB`)}
        ${kv("今天请求", `${num(s.req_today)} 次 · 平均 ${s.req_avg_ms ?? "—"} ms · 超 1 秒 ${s.req_slow_today} 次`)}
        ${kv("今天对话", `${num(s.chat_today)} 轮 · 平均 ${s.chat_avg_s ?? "—"} 秒`)}
        ${kv("对话并发", `现在 ${s.chat_now} · 今天最高 ${s.chat_peak_today}`)}
        ${kv("手机通知", `${s.push_users} 人 · ${s.push_devices} 台设备`)}
      </div>`)}
    </section>`;
  const charts = () => {
    const series = ov.series;
    columns(main.querySelector('[data-c="new"]'), series, [
      { key: "new_member", label: "注册", color: C.violet }, { key: "new_guest", label: "体验账号", color: C.mint }]);
    columns(main.querySelector('[data-c="active"]'), series, [{ key: "active", label: "活跃用户", color: C.violet }]);
    columns(main.querySelector('[data-c="msgs"]'), series, [{ key: "msgs", label: "消息", color: C.violet }]);
    columns(main.querySelector('[data-c="tokens"]'), series.map((d) => ({ ...d, fresh: Math.max(0, d.tokens - d.cached) })), [
      { key: "fresh", label: "未缓存", color: C.violet }, { key: "cached", label: "缓存命中", color: C.mint }]);
  };
  charts();
  S.redraw = charts;
  hbars(main.querySelector('[data-h="funnel"]'), ov.funnel, "还没有人试过");
  hbars(main.querySelector('[data-h="intents"]'), ov.intents, "还没有人建档");
  hbars(main.querySelector('[data-h="tokens"]'), ov.top_tokens, "还没有按人记的用量", (r) => { location.hash = `#user/${encodeURIComponent(r.id)}`; });
  on("[data-days]", "click", (e) => { S.days = +e.currentTarget.dataset.days; render(); });
  on("[data-act=refresh]", "click", () => render().then(() => toast("已刷新")));
}

// ---------------------------------------------------------------- 用户 ----
const COLS = [
  { key: "name", label: "用户" },
  { key: "last_active", label: "最近活跃", v: (u) => u.last_active || u.created_at || "" },
  { key: "days_active", label: "活跃天数", r: 1 },
  { key: "msgs", label: "消息", r: 1 },
  { key: "steps_done", label: "一小步", r: 1 },
  { key: "moments", label: "瞬间", r: 1 },
  { key: "memories", label: "记忆", r: 1 },
  { key: "level", label: "等级", r: 1 },
  { key: "coins", label: "金币", r: 1 },
  { key: "tokens_30d", label: "30 天 tokens", r: 1 },
  { key: "intent", label: "想靠近" },
];

async function usersPage(main, _, live) {
  const { users } = await get("/api/admin/users");
  if (!live()) return;
  const guests = users.filter((u) => u.kind === "guest").length;
  main.innerHTML = head("用户", `${users.length - guests} 个注册${guests ? ` · ${guests} 个体验账号` : ""}`,
    guests ? `<button class="btn btn-quiet btn-sm adm-danger-text" data-act="purge">清理体验账号</button>` : "") + `
    <section class="card adm-card adm-flush">
      <div class="adm-toolbar">
        ${seg("filter", [["all", "全部"], ["member", "注册"], ["guest", "体验账号"]], S.filter)}
        <span class="spacer"></span>
        <input class="field adm-search" type="search" placeholder="搜用户名" value="${esc(S.query)}">
      </div>
      <div class="adm-table-wrap"><table class="adm-table adm-users"><thead><tr>
        ${COLS.map((c) => `<th class="${c.r ? "r" : ""}" ${c.key !== "name" && c.key !== "intent" ? `data-sort="${c.key}"` : ""}>${c.label}</th>`).join("")}
      </tr></thead><tbody></tbody></table></div>
    </section>`;

  const draw = () => {
    const q = S.query.toLowerCase();
    const col = COLS.find((c) => c.key === S.sort.key);
    const val = col.v || ((u) => u[col.key] ?? 0);
    const list = users.filter((u) => (S.filter === "all" || u.kind === S.filter) && (!q || (u.username || "").toLowerCase().includes(q)))
      .sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * S.sort.dir; });
    main.querySelectorAll("th[data-sort]").forEach((th) => {
      th.classList.toggle("on", th.dataset.sort === S.sort.key);
      th.dataset.dir = th.dataset.sort === S.sort.key ? (S.sort.dir < 0 ? "↓" : "↑") : "";
    });
    const tb = main.querySelector("tbody");
    tb.innerHTML = list.length ? list.map((u) => `
      <tr data-id="${esc(u.id)}" tabindex="0">
        <td class="adm-who"><b>${esc(userName(u))}</b><small>注册于 ${esc((u.created_at || "").slice(0, 10))}</small></td>
        <td>${esc(ago(u.last_active))}</td>
        <td class="r num">${u.days_active}</td>
        <td class="r num">${num(u.msgs)}</td>
        <td class="r num">${u.steps_done}<span class="muted">/${u.steps}</span></td>
        <td class="r num">${u.moments}</td>
        <td class="r num">${u.memories}</td>
        <td class="r num">${u.level}</td>
        <td class="r num">${num(u.coins)}</td>
        <td class="r num">${num(u.tokens_30d)}</td>
        <td class="clip">${esc(u.profile?.intent_primary || "—")}</td>
      </tr>`).join("") : `<tr><td colspan="${COLS.length}" class="adm-none">没有符合的用户</td></tr>`;
  };
  draw();

  const tb = main.querySelector("tbody");
  const open = (tr) => { if (tr?.dataset.id) location.hash = `#user/${encodeURIComponent(tr.dataset.id)}`; };
  tb.addEventListener("click", (e) => open(e.target.closest("tr")));
  tb.addEventListener("keydown", (e) => { if (e.key === "Enter") open(e.target.closest("tr")); });
  on("[data-filter]", "click", (e) => {
    S.filter = e.currentTarget.dataset.filter;
    main.querySelectorAll("[data-filter]").forEach((b) => b.classList.toggle("on", b === e.currentTarget));
    draw();
  });
  on("th[data-sort]", "click", (e) => {
    const k = e.currentTarget.dataset.sort;
    S.sort = { key: k, dir: S.sort.key === k ? -S.sort.dir : -1 };
    draw();
  });
  main.querySelector(".adm-search").addEventListener("input", (e) => { S.query = e.target.value.trim(); draw(); });
  main.querySelector("[data-act=purge]")?.addEventListener("click", () => purgeGuests(guests));
}

// ---------------------------------------------------------------- 单个用户 ----
async function userPage(main, id, live) {
  let u, g;
  try {
    [u, g] = await Promise.all([get(`/api/admin/user?id=${encodeURIComponent(id)}`), get(`/api/admin/user/growth?id=${encodeURIComponent(id)}`)]);
  } catch (e) {
    if (e.status !== 404 || disabled(e)) throw e;
    if (live()) main.innerHTML = `<a class="adm-back" href="#users">${icon("back")}用户</a><div class="adm-empty">没有这个用户，可能已经删了</div>`;
    return;
  }
  if (!live()) return;
  const p = u.profile || {};
  const t30 = u.tokens.d30;
  const hit = t30.tokens_in ? `${Math.round((t30.tokens_cached / t30.tokens_in) * 100)}%` : "—";
  const lv = g.level;
  main.innerHTML = `<a class="adm-back" href="#users">${icon("back")}用户</a>` +
    head(esc(userName(u)),
      `注册于 ${esc((u.created_at || "").slice(0, 16).replace("T", " "))} · 最近活跃 ${esc(ago(u.last_active))}`,
      `<button class="btn btn-main btn-sm" data-act="adjust">调整经验和金币</button>`) + `
    <section class="adm-kpis">
      ${kpi("活跃天数", u.days_active, u.first_active ? `第一次 ${u.first_active}` : "")}
      ${kpi("消息", u.msgs)}
      ${kpi("一小步", `${u.steps_done} / ${u.steps}`, "完成 / 全部")}
      ${kpi("瞬间", u.moments)}
      ${kpi("记忆", u.memories)}
      ${kpi("习惯", u.habits)}
    </section>
    <section class="adm-grid">
      ${card("成长", "", `
        <div class="adm-growth">
          <div class="ag-lv"><b>Lv ${lv.lv}</b><span>${g.floor > 1 ? `保底 Lv ${g.floor} · ` : ""}经验 ${num(g.xp)}，离下一级 ${lv.to_next}</span>
            <div class="bar sm"><i style="width:${Math.round((lv.pct || 0) * 100)}%"></i></div></div>
          <div class="ag-row">
            <div><span>金币</span><b class="num">${COIN_SVG}${num(g.coins)}</b></div>
            <div><span>小镇</span><b class="num">${g.town.size}×${g.town.size}</b></div>
            <div><span>摆着</span><b class="num">${g.town.placed} 样</b></div>
            <div><span>仓库</span><b class="num">${g.town.warehouse} 样</b></div>
          </div>
        </div>
        ${g.adjustments.length ? `<h4>后台调整过</h4><ul class="adm-acts">${g.adjustments.map((a) => `<li>
          <span class="pill acc">${[a.xp ? `${signed(a.xp)} 经验` : "", a.coins ? `${signed(a.coins)} 金币` : ""].filter(Boolean).join(" · ")}</span>
          <span class="t">${esc(a.reason)}</span><time>${esc(when(a.at))}</time></li>`).join("")}</ul>` : ""}`)}
      ${card("资料", "", `<div class="adm-kv">
        ${kv("想靠近", esc(p.intent_primary || "—"))}
        ${kv("为什么", esc(p.intent_why || "—"))}
        ${kv("伙伴名字", esc(p.agent_name || "—"))}
        ${kv("性格", PERSONA[p.persona] || "—")}
        ${kv("中断时", CARE[p.care_style] || "—")}
        ${kv("登录中的设备", u.sessions)}
        ${kv("手机通知", u.push_devices ? `${u.push_devices} 台设备` : "没开")}
        ${kv("数据大小", `${(u.bytes / 1024).toFixed(0)} KB`)}
      </div>`)}
    </section>
    <section class="card adm-card adm-flush">
      <div class="adm-card-h"><h3>账本</h3><p class="adm-sub">经验和金币的每一笔，最近 ${g.ledger.length} 笔</p></div>
      <div class="adm-table-wrap adm-scroll"><table class="adm-table adm-plain"><thead><tr>
        <th>时间</th><th>类别</th><th>内容</th><th class="r">经验</th><th class="r">金币</th></tr></thead><tbody>
        ${g.ledger.map((r) => `<tr><td class="muted">${esc(when(r.at))}</td><td><span class="pill">${esc(LEDGER[r.kind] || r.kind)}</span></td>
          <td class="clip wide">${esc(r.note || "")}</td><td class="r num">${r.xp ? signed(r.xp) : ""}</td>
          <td class="r num ${r.coins < 0 ? "neg" : ""}">${r.coins ? signed(r.coins) : ""}</td></tr>`).join("")
          || `<tr><td colspan="5" class="adm-none">还没有</td></tr>`}
      </tbody></table></div>
    </section>
    <section class="adm-grid">
      ${chartCard("u-msgs", "近 30 天每天的消息")}
      ${chartCard("u-tokens", "近 30 天模型 tokens", `共 ${num(t30.tokens)} · ${num(t30.calls)} 次调用 · 缓存命中 ${hit} · 累计 ${num(u.tokens.all.tokens)}`)}
    </section>
    ${card("最近的操作", "", `<ul class="adm-acts">${(u.activity || []).map((x) => `<li><span class="pill">${esc(ACT[x.kind] || x.kind)}</span>
      <span class="t">${esc(x.text)}</span><time>${esc(when(x.at))}</time></li>`).join("") || `<li class="adm-none">还没有</li>`}</ul>`)}
    <section class="adm-danger">
      <div><b>删除这个用户</b><span>账号、对话、记忆、计划、例行任务和用量记录全部删掉，不能恢复。</span></div>
      <button class="btn btn-danger btn-sm" data-act="del">删除…</button>
    </section>`;
  const charts = () => {
    columns(main.querySelector('[data-c="u-msgs"]'), u.series, [{ key: "msgs", label: "消息", color: C.violet }], 140);
    columns(main.querySelector('[data-c="u-tokens"]'), u.series, [
      { key: "t_tokens_chat", label: "对话", color: C.violet }, { key: "t_tokens_bg", label: "后台", color: C.mint }], 140);
  };
  charts();
  S.redraw = charts;
  on("[data-act=adjust]", "click", () => adjustSheet(u, g));
  on("[data-act=del]", "click", () => deleteUser(u));
}

function adjustSheet(u, g) {
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
    h("label", {}, "经验（减就写负数）"), xp, h("label", {}, "金币（减就写负数）"), coins, h("label", {}, "原因（会写进 TA 的账本）"), why, after, err);
  const ok = h("button", { class: "btn btn-main" }, "确认调整");
  const s = sheet({ title: `调整 ${userName(u)}`, sticker: "bolt", body, footer: [h("button", { class: "btn btn-quiet", onclick: () => s.close() }, "算了"), ok] });
  ok.addEventListener("click", async () => {
    ok.disabled = true;
    try {
      await post("/api/admin/user/adjust", { id: u.id, xp: +xp.value || 0, coins: +coins.value || 0, reason: why.value });
      s.close();
      toast("调整好了");
      render();
    } catch (e) { err.textContent = e.message; ok.disabled = false; }
  });
  setTimeout(() => xp.focus(), 60);
}

// ---------------------------------------------------------------- 小镇：全局调价格和解锁等级 ----
const FIELDS = ["name", "price", "lv", "enabled"];
const cur = (it) => (S.edits[it.id] === null ? { ...it, ...it.default } : { ...it, ...(S.edits[it.id] || {}) });
const byId = (id) => S.town.items.find((i) => i.id === id);

async function townPage(main, _, live) {
  const d = await get("/api/admin/town");
  if (!live()) return;
  S.town = d;
  setKinds(Object.fromEntries(d.items.map((i) => [i.id, i])));
  drawTown(main);
}

function drawTown(main) {
  const D = S.town;
  main.innerHTML = head("小镇", `<span data-onsale></span>${D.updated_at ? ` · 上次保存 ${esc(when(D.updated_at))}` : ""}`) + `
    <div class="adm-town-layout">
      <section class="card adm-card adm-flush">
        <div class="adm-toolbar">${seg("cat", [["all", "全部"], ...Object.entries(D.cats), ["off", "未上架"]], S.cat)}</div>
        <div class="adm-table-wrap"><table class="adm-table adm-town"><thead><tr>
          <th></th><th>名字</th><th>占地</th><th class="r">价格</th><th class="r">解锁</th><th class="c">上架</th><th></th>
        </tr></thead><tbody></tbody></table></div>
        <p class="adm-foot">新东西放进 <code>demo/public/js/buildings/</code>，部署后在这里定价、上架。</p>
      </section>
      <aside class="card adm-card adm-rhythm-card"><h3>解锁节奏</h3><p class="adm-sub">按现在填的值，每一级能买到什么</p><div class="adm-rhythm"></div></aside>
    </div>
    <div class="adm-savebar"><span></span><span class="spacer"></span>
      <button class="btn btn-quiet btn-sm" data-act="discard">放弃</button><button class="btn btn-main btn-sm" data-act="save">保存</button></div>`;
  drawRows(main);
  townChanged(main);

  on("[data-cat]", "click", (e) => {
    S.cat = e.currentTarget.dataset.cat;
    main.querySelectorAll("[data-cat]").forEach((b) => b.classList.toggle("on", b === e.currentTarget));
    drawRows(main);
  });
  const tb = main.querySelector(".adm-town tbody");
  // 改数字只更新这一行的状态，不重画输入框：Tab 到下一格时焦点不会丢
  tb.addEventListener("change", (e) => {
    const inp = e.target.closest("input[data-f]");
    if (!inp) return;
    const it = byId(inp.closest("tr").dataset.id);
    const f = inp.dataset.f;
    let v = inp.type === "number" ? Math.round(+inp.value || 0) : inp.value.trim();
    if (f === "price") v = Math.max(0, v);
    if (f === "lv") v = Math.max(1, v);
    if (f === "name" && !v) v = cur(it).name;
    inp.value = v;
    setEdit(it, f, v);
    syncRow(main, it, false);
  });
  tb.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    const it = byId(tr.dataset.id);
    if (e.target.closest("[data-f=enabled]")) setEdit(it, "enabled", !cur(it).enabled);
    else if (e.target.closest("[data-reset]")) S.edits[it.id] = null;
    else if (e.target.closest("[data-undo]")) delete S.edits[it.id];
    else return;
    syncRow(main, it, true);
  });
  on("[data-act=discard]", "click", () => { S.edits = {}; drawRows(main); townChanged(main); });
  on("[data-act=save]", "click", () => saveTown(main));
}

function setEdit(it, f, v) {
  const e = S.edits[it.id] === null ? Object.fromEntries(FIELDS.map((k) => [k, it.default[k]])) : { ...(S.edits[it.id] || {}) };
  e[f] = v;
  if (FIELDS.every((k) => (k in e ? e[k] : it[k]) === it[k])) delete S.edits[it.id];
  else S.edits[it.id] = e;
}

function shown(it) {
  return S.cat === "all" || (S.cat === "off" ? !cur(it).enabled && !it.gift : it.cat === S.cat);
}

function drawRows(main) {
  const list = S.town.items.filter(shown);
  main.querySelector(".adm-town tbody").innerHTML = list.map(rowHTML).join("")
    || `<tr><td colspan="7" class="adm-none">${S.cat === "off" ? "都上架了" : "这一类还没有东西"}</td></tr>`;
}

function rowHTML(it) {
  const e = cur(it);
  const lock = it.gift ? "disabled" : "";
  return `<tr data-id="${esc(it.id)}" class="${rowClass(it)}">
    <td class="adm-prev">${itemArt(it.id)}</td>
    <td class="adm-name"><input class="adm-in" data-f="name" maxlength="10" value="${esc(e.name)}" aria-label="名字"><small>${esc(it.id)} · ${esc(S.town.cats[it.cat] || it.cat)}</small></td>
    <td class="muted">${it.size.join("×")}</td>
    <td class="r"><label class="adm-num">${COIN_SVG}<input type="number" min="0" max="100000" data-f="price" value="${e.price}" ${lock} aria-label="价格"></label></td>
    <td class="r"><label class="adm-num"><span>Lv</span><input type="number" min="1" max="200" data-f="lv" value="${e.lv}" ${lock} aria-label="解锁等级"></label></td>
    <td class="c">${it.gift ? `<span class="pill">礼物</span>` : `<button class="switch ${e.enabled ? "on" : ""}" data-f="enabled" aria-label="上架" aria-pressed="${e.enabled}"><i></i></button>`}</td>
    <td class="adm-state">${stateHTML(it)}</td>
  </tr>`;
}

const rowClass = (it) => `${it.id in S.edits ? "dirty" : ""} ${cur(it).enabled || it.gift ? "" : "off"}`;

function stateHTML(it) {
  if (it.id in S.edits) return `<span class="pill acc">${S.edits[it.id] === null ? "将恢复默认" : "未保存"}</span><button class="adm-link" data-undo>撤销</button>`;
  if (it.fresh) return `<span class="pill good">新</span>`;
  if (Object.keys(it.override).length) {
    const d = it.default;
    return `<button class="adm-link" data-reset title="默认：${esc(d.name)} · ${d.price} 金币 · Lv${d.lv} · ${d.enabled ? "上架" : "不上架"}">恢复默认</button>`;
  }
  return "";
}

function syncRow(main, it, full) {
  const tr = main.querySelector(`.adm-town tr[data-id="${CSS.escape(it.id)}"]`);
  if (tr && full) tr.outerHTML = rowHTML(it);
  else if (tr) {
    tr.className = rowClass(it);
    tr.querySelector(".adm-state").innerHTML = stateHTML(it);
  }
  townChanged(main);
}

function townChanged(main) {
  const sale = S.town.items.filter((i) => !i.gift && cur(i).enabled);
  main.querySelector("[data-onsale]").textContent = `${sale.length} 样在售`;
  const n = Object.keys(S.edits).length;
  const bar = main.querySelector(".adm-savebar");
  bar.classList.toggle("on", n > 0);
  bar.firstElementChild.innerHTML = `<b>${n}</b> 样改了还没保存`;
  main.querySelector(".adm-rhythm").innerHTML = rhythmHTML(sale);
}

function rhythmHTML(sale) {
  const D = S.town;
  const lvs = [...new Set([...sale.map((i) => cur(i).lv), ...D.land.map((l) => l.lv)])].sort((a, b) => a - b);
  return `<ol class="rh">${lvs.map((lv) => {
    const its = sale.filter((i) => cur(i).lv === lv).sort((a, b) => cur(a).price - cur(b).price);
    const land = D.land.find((l) => l.lv === lv);
    return `<li><b class="rh-lv">Lv ${lv}</b><div class="rh-its">
      ${its.map((i) => `<span class="rh-it ${i.id in S.edits ? "dirty" : ""}">${itemArt(i.id)}<span>${esc(cur(i).name)}</span><em>${COIN_SVG}${cur(i).price}</em></span>`).join("")}
      ${land ? `<span class="rh-land">土地 ${land.size}×${land.size}</span>` : ""}</div></li>`;
  }).join("")}</ol>
  <div class="rh-xp"><h4>到这一级的累计经验</h4><div>${D.levels.map((l) => `<span><b>Lv ${l.lv}</b>${num(l.xp)}</span>`).join("")}</div>
  <p class="adm-sub">每级经验和土地大小写在代码里（growth.py、town.py）。</p></div>`;
}

async function saveTown(main) {
  const btn = main.querySelector("[data-act=save]");
  btn.disabled = true;
  try {
    S.town = await post("/api/admin/town", { items: S.edits });
    S.edits = {};
    setKinds(Object.fromEntries(S.town.items.map((i) => [i.id, i])));
    drawTown(main);
    toast("保存好了，所有人立刻生效");
  } catch (e) {
    btn.disabled = false;
    fail(e);
  }
}

// ---------------------------------------------------------------- 模型 ----
// 切换小光用的服务商、模型和思考档。点「试一下并切换」：服务器用新设置真跑一次带工具的对话，通了才切，不通就保持原样。
async function modelPage(main, _, live) {
  const d = await get("/api/admin/llm");
  if (!live()) return;
  const cur = d.current;
  const pick = { provider: cur.provider, model: cur.model, effort: cur.effort };
  const provName = (id) => d.providers.find((p) => p.id === id)?.name || id;
  const effName = (id) => d.efforts.find((e) => e.id === id)?.name || id;
  const draw = () => {
    const p = d.providers.find((x) => x.id === pick.provider) || d.providers[0];
    if (!p.models.some((m) => m.id === pick.model)) pick.model = p.models[0]?.id || "";
    const same = pick.provider === cur.provider && pick.model === cur.model && pick.effort === cur.effort;
    main.innerHTML = head("模型", "小光聊天用哪个模型、想多久再回。切换前会先真跑一次，跑不通就不切。") + `
      <div class="adm-grid2">
        ${card("现在在用", `${cur.by}${cur.at ? " · " + when(cur.at) : ""}`, `<div class="adm-kv">
          ${kv("服务商", esc(provName(cur.provider)))}${kv("模型", esc(cur.model))}${kv("思考", esc(effName(cur.effort)))}
          ${kv("今天", `调用 ${num(d.today.llm_calls)} 次 · 退回不思考 ${num(d.today.llm_fallback)} 次 · 失败 ${num(d.today.llm_err)} 次`)}</div>`)}
        ${card("切换", "", `
          <h4>服务商</h4>${seg("prov", d.providers.map((x) => [x.id, x.name + (x.has_key ? "" : "（没配 key）")]), pick.provider)}
          <p class="adm-sub adm-llm-note">${esc(p.note || "")}</p>
          <h4>模型</h4>${p.has_key ? `<select class="field adm-llm-model">${p.models.map((m) =>
            `<option value="${esc(m.id)}" ${m.id === pick.model ? "selected" : ""}>${esc(m.name === m.id ? m.id : `${m.name}（${m.id}）`)}</option>`).join("")}</select>`
            : `<p class="adm-sub">服务器的 .env 里还没有这个服务商的 key。</p>`}
          <h4>思考</h4>${seg("eff", d.efforts.map((e) => [e.id, e.name]), pick.effort)}
          <p class="adm-sub adm-llm-note">不思考最快（首字一两秒）；思考越多回得越慢，也更费钱。路由判断、两分钟启动、练习结束页一直用不思考，不受这里影响。
            思考出错时会自动退回不思考，回复不会断。</p>
          <div class="adm-llm-act"><button class="btn btn-main" data-switch ${same || !p.has_key ? "disabled" : ""}>试一下并切换</button>
            <span class="adm-llm-res muted"></span></div>`)}
      </div>`;
    main.querySelectorAll("[data-prov]").forEach((b) => b.addEventListener("click", () => { pick.provider = b.dataset.prov; draw(); }));
    main.querySelectorAll("[data-eff]").forEach((b) => b.addEventListener("click", () => { pick.effort = b.dataset.eff; draw(); }));
    main.querySelector(".adm-llm-model")?.addEventListener("change", (e) => { pick.model = e.target.value; draw(); });
    main.querySelector("[data-switch]")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const res = main.querySelector(".adm-llm-res");
      btn.disabled = true;
      res.textContent = "正在用新设置跑一次…（开着思考可能要几十秒）";
      try {
        const out = await post("/api/admin/llm", pick);
        Object.assign(d, out);
        Object.assign(cur, out.current);
        toast(`切换好了：${out.current.model} · ${effName(out.current.effort)}`);
        draw();
        main.querySelector(".adm-llm-res").textContent = `试跑首字 ${out.test.first_s} 秒` + (out.test.tool_called ? " · 工具调用正常" : "")
          + (out.test.fell_back ? " · 注意：这次是退回不思考才成功的，这个模型现在开思考不稳定" : "");
      } catch (err) {
        res.textContent = err.message;
        btn.disabled = false;
      }
    });
  };
  draw();
}

// ---------------------------------------------------------------- 记录 ----
async function logPage(main, _, live) {
  const [lg, t] = await Promise.all([get("/api/admin/log"), S.town ? Promise.resolve(S.town) : get("/api/admin/town")]);
  if (!live()) return;
  S.town = t;
  const name = (id) => t.items.find((i) => i.id === id)?.name || id;
  const what = (e) => {
    if (e.type === "adjust") {
      const parts = [e.xp ? `${signed(e.xp)} 经验` : "", e.coins ? `${signed(e.coins)} 金币` : ""].filter(Boolean).join("、");
      return `给 <a href="#user/${encodeURIComponent(e.uid)}">${esc(e.user || e.uid)}</a> ${parts}<span class="muted">：${esc(e.reason)}</span>`;
    }
    if (e.type === "town") {
      return Object.entries(e.changes || {}).map(([id, c]) => {
        if (c === null) return `${esc(name(id))} 恢复默认`;
        const bits = [c.name != null && c.name !== name(id) ? `改名「${esc(c.name)}」` : "", c.price != null ? `${c.price} 金币` : "",
          c.lv != null ? `Lv${c.lv}` : "", c.enabled != null ? (c.enabled ? "上架" : "下架") : ""].filter(Boolean);
        return `${esc(name(id))} ${bits.join(" · ")}`;
      }).join("；") || "—";
    }
    if (e.type === "llm") return `${esc(e.from?.model || "")}（${esc(e.from?.effort || "")}）→ <b>${esc(e.to?.model || "")}</b>（${esc(e.to?.effort || "")}）<span class="muted">：试跑首字 ${esc(String(e.first_s))} 秒${e.fell_back ? "，靠退回不思考" : ""}</span>`;
    return esc(e.type);
  };
  main.innerHTML = head("记录", "后台加减经验金币、改小镇的每一次，最近 100 条") + `
    <section class="card adm-card adm-flush"><div class="adm-table-wrap"><table class="adm-table adm-plain adm-log"><thead><tr>
      <th>时间</th><th>类型</th><th>内容</th></tr></thead><tbody>
      ${lg.entries.map((e) => `<tr><td class="muted" title="${esc(e.ip || "")}">${esc(when(e.at))}</td>
        <td><span class="pill ${e.type === "adjust" ? "acc" : "good"}">${e.type === "adjust" ? "经验金币" : e.type === "town" ? "小镇" : e.type === "llm" ? "模型" : esc(e.type)}</span></td>
        <td class="wrap">${what(e)}</td></tr>`).join("") || `<tr><td colspan="3" class="adm-none">还没有</td></tr>`}
    </tbody></table></div></section>`;
}

const PAGES = { overview, users: usersPage, user: userPage, town: townPage, model: modelPage, log: logPage };

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

async function deleteUser(u) {
  const phrase = u.username || u.id;
  const r = await confirmTyped({
    title: `删除 ${userName(u)}`, phrase, okLabel: "永久删除",
    text: `会删掉 TA 的账号和全部数据（${u.msgs} 条消息、${u.memories} 条记忆、${u.steps} 个一小步），TA 会立刻被登出。不能恢复。`,
  });
  if (!r) return;
  try {
    await post("/api/admin/user/delete", { id: u.id, confirm: r.value });
    r.close();
    toast(`已删除 ${userName(u)}`);
    location.hash = "#users";
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
    render();
  } catch (e) { r.err.textContent = e.message; }
}

// ---------------------------------------------------------------- 图 ----
// 柱状图（可堆叠）：柱宽 ≤24px、顶端 4px 圆角、段之间 2px 间隙；悬停 / 聚焦出提示；下面能展开数据表。
function columns(el, data, series, height = 180) {
  if (!el) return;
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
    const top = document.createElement("div");
    top.className = "tip-d";
    top.textContent = d.day;
    tip.append(top);
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

render();
