// 成长进化：宠物舞台 → 一眼看懂的进化图 → 亲和度（决定往哪长）→ 全功能徽章墙 → 账本。
// 所有数字来自后端账本；页面不做本地加成。
import { state } from "../store.js";
import { esc } from "../ui.js";
import { art, badgeArt, countUp } from "../fx.js";

const CATS = ["全部", "对话", "计划", "好消息", "练习", "记忆", "学堂", "报告", "陪伴", "成长"];
const AFF_ART = { action: "st-flag", good: "st-jar", practice: "st-lotus" };
const AFF_CLS = { action: "orange", good: "pink", practice: "sky" };

export function renderGrowth(root) {
  const g = state.data.growth;
  const span = g.next ? g.next.at - g.prev_at : 1;
  const pct = g.next ? Math.round(((g.total - g.prev_at) / span) * 100) : 100;
  const lean = g.leaning_info;
  const br = g.branch_info;

  root.innerHTML = `
    <div class="view-inner wide growth">
      <section class="pet-hero">
        <div class="ph-stage">
          <span class="ph-ray"></span><span class="ph-ray r2"></span>
          <span class="ph-glow"></span>
          <img class="ph-pet" src="${art(g.stage.art)}" alt="${esc(g.stage.name)}">
          <i class="sparkle" style="left:16%;top:22%"></i><i class="sparkle" style="left:80%;top:30%;animation-delay:-1.2s"></i>
          <i class="sparkle" style="left:70%;top:72%;animation-delay:-2.1s"></i>
        </div>
        <div class="ph-info">
          <div class="ph-tags"><span class="pill lamp">Lv ${g.level.lv}</span>
            ${br ? `<span class="pill" style="background:${br.color}33;color:${br.color}">${esc(br.name)} · ${esc(br.tag)}</span>` : `<span class="pill">还没分化</span>`}</div>
          <h1>${esc(g.pet_name)} · ${esc(g.stage.name)}</h1>
          <p class="ph-line">${esc(g.stage.line)}</p>
          <div class="ph-xp"><span class="num big" data-count="${g.total}">0</span><span>累计经验</span></div>
          <div class="bar lamp ph-bar"><i style="width:0" data-w="${pct}%"></i></div>
          <div class="ph-next">${g.next ? `再 <b>${g.to_next}</b> 经验，${g.next.id === "young" ? "小芽就会<b>分化</b>，长出自己的样子" : `到「${esc(g.next.name)}」`}` : "已经是成年形态了"}</div>
        </div>
      </section>

      <section class="section">
        <div class="sec-title">进化图 <span class="more">${g.branch ? "你的路已经走出来了" : "310 经验时，看你更常做哪类事来决定方向"}</span></div>
        <div class="evo-map card">
          <svg class="evo-lines" aria-hidden="true"></svg>
          <div class="evo-grid">
            ${node(g.tree.find((n) => n.id === "egg"), "egg")}
            ${node(g.tree.find((n) => n.id === "baby"), "baby")}
            ${["fox", "deer", "whale", "star"].map((b, row) => `
              ${node(g.tree.find((n) => n.id === b + "-1"), "young", row)}
              ${node(g.tree.find((n) => n.id === b + "-2"), "adult", row)}`).join("")}
          </div>
          <div class="evo-cols"><span>0</span><span>100</span><span>310 · 分化</span><span>650 · 成年</span></div>
        </div>
      </section>

      <section class="section aff">
        <div class="sec-title">它在往哪边长 <span class="more">${g.branch ? "分化时的比例" : "由累计经验的比例决定"}</span></div>
        <div class="aff-row">
          ${g.affinity.map((a) => `
            <div class="aff card ${(g.branch || g.leaning) === a.branch ? "lead" : ""}">
              <img src="${art(AFF_ART[a.id])}" alt="">
              <div class="aff-main">
                <div class="aff-t">${esc(a.label)}<span class="num">${Math.round(a.share * 100)}%</span></div>
                <div class="bar sm ${AFF_CLS[a.id]}"><i style="width:0" data-w="${Math.round(a.share * 100)}%"></i></div>
                <div class="aff-s">${a.xp} 经验 · 偏多会长成${g.branch === a.branch || (!g.branch && g.leaning === a.branch) ? `「${esc(g.branches.find((b) => b.id === a.branch).name)}」` : "？"}</div>
              </div>
            </div>`).join("")}
        </div>
        <p class="hint-line">${g.branch
          ? `小芽在 310 经验那天分化成了「${esc(br.young)}」。`
          : lean?.id === "star"
            ? "三样都差不多——这样下去，可能会遇见一个隐藏形态。"
            : `照现在的比例，它会长成<b>${esc(lean?.name || "")}</b>。想换方向，就多做另一类事。`}</p>
      </section>

      <section class="section">
        <div class="sec-title">徽章 <span class="more">${g.badges.filter((b) => b.earned).length}/${g.badges.length} 枚</span></div>
        <div class="badge-tabs">${CATS.map((c) => `<button class="chip ${state.badgeFilter === c ? "on" : ""}" data-cat="${c}">${c}</button>`).join("")}</div>
        <div class="badge-grid"></div>
      </section>

      <section class="section">
        <details class="ledger card">
          <summary><img src="${art("st-jar")}" alt="">经验账本 <span class="muted">· 每一笔都对得上</span></summary>
          <div class="ledger-list">
            ${g.ledger.map((r) => `<div class="lrow"><span class="d">${esc(r.created_at.slice(5, 10))}</span>
              <span class="pill ${AFF_CLS[r.source] || "leaf"}">${esc(r.label)}</span>
              <span class="n">${esc(r.note || "")}</span><span class="v num">+${r.amount}</span></div>`).join("") || "<p class='muted'>还没有记录。</p>"}
          </div>
          <p class="hint-line">行动 +10 · 好消息 +6 · 练习 +12 · 每天第一次来聊 +8；每类每天 30、总共 120 封顶；同一件事不重复计分。</p>
        </details>
      </section>
    </div>`;

  // 数字滚动 + 进度条长出来
  countUp(root.querySelector("[data-count]"), g.total, 1100);
  requestAnimationFrame(() => setTimeout(() => {
    root.querySelectorAll("[data-w]").forEach((i) => { i.style.width = i.dataset.w; });
  }, 120));

  drawBadges(root);
  root.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
    state.badgeFilter = b.dataset.cat;
    root.querySelectorAll("[data-cat]").forEach((x) => x.classList.toggle("on", x === b));
    drawBadges(root);
  }));

  const draw = () => drawLines(root);
  requestAnimationFrame(() => requestAnimationFrame(draw));
  const ro = new ResizeObserver(draw);
  ro.observe(root.querySelector(".evo-map"));
}

function node(n, kind, row = 0) {
  if (!n) return "";
  const cls = [
    "evo-node", kind, n.state, n.current ? "current" : "", n.silhouette ? "sil" : "", n.hidden ? "secret" : "",
    n.leaning ? "leaning" : "",
  ].join(" ");
  const style = kind === "young" || kind === "adult" ? `grid-row:${row + 1}` : "";
  return `<div class="${cls}" style="${style}" data-id="${n.id}">
    <div class="disc">${n.hidden ? '<span class="q">?</span>' : `<img src="${art(n.art)}" alt="">`}
      ${n.silhouette && !n.hidden ? '<span class="q small">?</span>' : ""}</div>
    <div class="nm">${n.current ? "现在 · " : ""}${esc(n.state === "done" || n.current || !n.silhouette ? n.name : n.hidden ? "？？？" : "？？？")}</div>
    ${n.leaning ? '<div class="tag-lean">可能是它</div>' : ""}
  </div>`;
}

function drawLines(root) {
  const map = root.querySelector(".evo-map");
  const svg = root.querySelector(".evo-lines");
  if (!map || !svg) return;
  const box = map.getBoundingClientRect();
  svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
  const c = (id) => {
    const el = map.querySelector(`[data-id="${id}"] .disc`);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2, r: r.width / 2 };
  };
  const g = state.data.growth;
  const link = (a, b, cls) => {
    const p = c(a), q = c(b);
    if (!p || !q) return "";
    const x1 = p.x + p.r, x2 = q.x - q.r, mx = (x1 + x2) / 2;
    return `<path class="${cls}" d="M${x1},${p.y} C${mx},${p.y} ${mx},${q.y} ${x2},${q.y}"/>`;
  };
  const lineCls = (b, tier) => {
    if (g.branch === b) return g.tree.find((n) => n.id === `${b}-${tier}`)?.state === "done" ? "on" : "next";
    if (g.branch) return "off";
    return g.leaning === b ? "lean" : "maybe";
  };
  let html = link("egg", "baby", g.total >= 100 ? "on" : "next");
  for (const b of ["fox", "deer", "whale", "star"]) {
    html += link("baby", `${b}-1`, lineCls(b, 1));
    html += link(`${b}-1`, `${b}-2`, lineCls(b, 2));
  }
  svg.innerHTML = html;
}

function drawBadges(root) {
  const g = state.data.growth;
  const f = state.badgeFilter || "全部";
  const list = g.badges.filter((b) => f === "全部" || b.cat === f);
  root.querySelector(".badge-grid").innerHTML = list.map((b, i) => `
    <div class="bdg ${b.earned ? "earned" : ""}" style="--i:${i}" title="${esc(b.how)}">
      <div class="medal ${b.earned ? "earned" : ""}" style="--p:${Math.round((b.got / b.need) * 100)}">
        <span class="medal-ring"></span><img src="${badgeArt(b.icon)}" alt="">
      </div>
      <div class="bn">${esc(b.name)}</div>
      <div class="bh">${b.earned ? `${esc(b.at.slice(5, 10).replace("-", "/"))} 获得` : b.hidden ? "隐藏" : `${b.got}/${b.need}`}</div>
      <div class="bt">${esc(b.how)}</div>
    </div>`).join("");
}
