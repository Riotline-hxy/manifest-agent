// 管理后台：登录 → 概览（数字、按天的图、漏斗、服务器）→ 用户列表 → 单个用户。只读。
import { get, post } from "./api.js";
import { esc, icon, tile, toast, sheet, h } from "./ui.js";

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
  const [ov, us] = await Promise.all([get(`/api/admin/overview?days=${days}`), get("/api/admin/users")]);
  users = us.users;
  draw(ov);
}

function draw(ov) {
  const u = ov.users, a = ov.active, s = ov.system;
  root.innerHTML = `
    <header class="adm-top">
      <b class="adm-logo">${icon("shield")}显伴后台</b>
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
        ${stat("今天活跃", a.today, "发过消息或做过操作")}
        ${stat("7 天活跃", a.week, "")}
        ${stat("30 天活跃", a.month, "")}
        ${stat("回访过", u.returning, "注册用户里活跃过 2 天以上的")}
        ${stat("今天的消息", ov.msgs_today, "用户发给小光的")}
        ${stat(`近 ${ov.days} 天模型调用`, ov.model.calls, `${num(ov.model.tokens)} tokens（缓存 ${num(ov.model.cached)}）· 失败 ${ov.model.errors}`)}
      </section>
      <section class="adm-grid">
        ${chartCard("new", "每天新用户", "注册用户和体验账号分开算")}
        ${chartCard("active", "每天活跃用户", "当天发过消息或做过操作的人数")}
        ${chartCard("msgs", "每天用户消息", "用户发给小光的条数")}
        ${chartCard("tokens", "每天模型 tokens", "对话、记忆整理、体验等所有调用；中转服务每次会带上约 2.7 万 token 的自带提示；从 2.8.0 开始统计")}
      </section>
      <section class="adm-grid">
        <div class="card adm-card"><h3>首页体验漏斗</h3><p class="adm-sub">近 ${ov.days} 天 · 从 2.8.0 开始统计</p><div class="hbars" data-h="funnel"></div></div>
        <div class="card adm-card"><h3>大家想靠近的</h3><p class="adm-sub">注册用户建档时选的方向</p><div class="hbars" data-h="intents"></div></div>
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
        </div>
      </section>
      <section class="card adm-card">
        <div class="adm-users-head">
          <h3>用户</h3>
          <div class="adm-range">${[["all", "全部"], ["member", "注册"], ["guest", "体验账号"]].map(([k, l]) =>
            `<button class="chip ${k === filter ? "on" : ""}" data-filter="${k}">${l}</button>`).join("")}</div>
          <span class="spacer"></span>
          <input class="field adm-search" type="search" placeholder="搜用户名" value="${esc(query)}">
        </div>
        <p class="adm-sub">按最近活跃排序。点一行看详情。这里只有数量和操作记录，看不到对话和记忆原文。</p>
        <div class="adm-table-wrap"><table class="adm-table"><thead><tr>
          <th>用户</th><th>类型</th><th>注册于</th><th>最近活跃</th><th class="r">活跃天数</th><th class="r">消息</th>
          <th class="r">一小步</th><th class="r">好消息</th><th class="r">记忆</th><th class="r">等级</th><th>想靠近</th>
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
  drawUsers();

  root.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => { days = +b.dataset.days; load().catch(fail); }));
  root.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
    filter = b.dataset.filter;
    root.querySelectorAll("[data-filter]").forEach((x) => x.classList.toggle("on", x === b));
    drawUsers();
  }));
  root.querySelector(".adm-search").addEventListener("input", (e) => { query = e.target.value.trim(); drawUsers(); });
  root.querySelector("[data-act=refresh]").addEventListener("click", () => load().then(() => toast("已刷新")).catch(fail));
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
      <td class="clip">${esc(u.profile?.intent_primary || "—")}</td>
    </tr>`).join("") : `<tr><td colspan="11" class="adm-none">没有符合的用户</td></tr>`;
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
  const body = h("div", { class: "adm-user" });
  body.innerHTML = `
    <div class="adm-sys">
      ${kv("类型", KIND[u.kind] || esc(u.kind))}
      ${kv("注册于", esc((u.created_at || "").slice(0, 16).replace("T", " ")))}
      ${kv("最近活跃", esc(ago(u.last_active)))}
      ${kv("活跃天数", `${u.days_active} 天${u.first_active ? `（第一次 ${esc(u.first_active)}）` : ""}`)}
      ${kv("登录中的设备", u.sessions)}
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
    <h4>近 30 天每天的消息</h4>
    <div class="chart chart-sm"></div>
    <h4>最近的操作记录</h4>
    <ul class="adm-acts">${(u.activity || []).map((x) => `<li><span class="pill">${esc(ACT[x.kind] || x.kind)}</span>
      <span class="t">${esc(x.text)}</span><time>${esc((x.at || "").slice(5, 16).replace("T", " "))}</time></li>`).join("") || `<li class="adm-none">还没有</li>`}</ul>`;
  sheet({ title: userName(u), sticker: "user", body });
  columns(body.querySelector(".chart"), u.series, [{ key: "msgs", label: "消息", color: C.violet }], 120);
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
function hbars(el, rows, empty) {
  if (!rows.length || rows.every((r) => !r.n)) {
    el.innerHTML = `<p class="adm-none">${esc(empty)}</p>`;
    return;
  }
  const max = Math.max(...rows.map((r) => r.n), 1);
  el.innerHTML = rows.map((r) => `<div class="hb"><span class="hb-l">${esc(r.label)}</span>
    <span class="hb-t"><i style="width:${Math.max(r.n ? 2 : 0, (r.n / max) * 100)}%;background:${C.violet}"></i><b class="num">${r.n}</b></span></div>`).join("");
}

let rz;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => root.querySelector(".adm") && load().catch(fail), 250); });

start();
