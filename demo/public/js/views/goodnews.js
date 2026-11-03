// 好消息：记下每天的小确幸，和脑子里冒出来的内心戏。
// 小确幸会变成夜空里的一颗星；内心戏是一个个小气泡。休息日放在蜕变计划里。
import { api } from "../api.js";
import { state, setData, xpNote } from "../store.js";
import { esc, fmtDay, toast, icon, tile } from "../ui.js";
import { flyGain, burstAt } from "../fx.js";
import { jarSVG } from "../art.js";

const KIND = {
  good: { ic: "star", color: "var(--c-lemon)", label: "小确幸", ph: "今天有什么让你嘴角上扬的小事？再小也算。" },
  meme: { ic: "chat", color: "var(--c-pink)", label: "内心戏", ph: "此刻脑子里在上演什么？吐槽、碎碎念、离谱的想法都可以。" },
  find: { ic: "sparkles", color: "var(--c-mint)", label: "新发现" },
};
const isStar = (r) => r.type === "good" || r.type === "find";

function seeded(id) {
  let h = 2166136261;
  for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0) / 4294967296);
}

export function renderNews(root, { fresh = "" } = {}) {
  const all = (state.data.records || []).filter((r) => KIND[r.type]);
  const stars = all.filter(isStar);
  const memes = all.filter((r) => r.type === "meme");
  const kind = state.newsKind || "good";
  const filter = state.newsFilter || "all";
  const shown = all.filter((r) => filter === "all" || (filter === "good" ? isStar(r) : r.type === "meme"));
  const groups = [];
  for (const r of shown) {
    const k = fmtDay(r.created_at || r.day);
    let g = groups.find((x) => x.k === k);
    if (!g) groups.push((g = { k, items: [] }));
    g.items.push(r);
  }

  root.innerHTML = `
    <div class="view-inner wide news">
      <div class="page-head"><div><h1>好消息</h1><p>记下今天的小确幸，和脑子里冒出来的内心戏</p></div></div>
      <section class="night-sky">
        <div class="sky-field">${stars.slice(0, 60).map((r, i) => {
          const rnd = seeded(r.id);
          const x = 6 + rnd() * 72, y = 10 + rnd() * 74;
          const tip = `${y < 46 ? "tip-down" : ""} ${x < 20 ? "tip-l" : x > 64 ? "tip-r" : ""}`;
          return `<button class="star ${r.id === fresh ? "new" : ""} ${tip}" style="left:${x}%;top:${y}%;--s:${14 + rnd() * 14}px;--d:${-rnd() * 4}s;--i:${i}">
            <span class="tip"><b>${esc(fmtDay(r.created_at))}</b>${esc(r.text)}</span></button>`;
        }).join("")}</div>
        <div class="sky-count"><div class="sky-jar">${jarSVG(stars.length)}</div><div><span class="num">${stars.length}</span><small>件小确幸</small></div></div>
        ${stars.length ? "" : `<div class="sky-empty">第一颗星还没亮。随便写一件小事试试。</div>`}
      </section>

      <section class="compose card">
        <div class="tabs news-kind">${["good", "meme"].map((k) => `<button class="${k === kind ? "on" : ""}" data-kind="${k}">${icon(KIND[k].ic)}${KIND[k].label}</button>`).join("")}<span class="ind"></span></div>
        <textarea class="field" id="newsText" rows="2" maxlength="200" placeholder="${KIND[kind].ph}"></textarea>
        <div class="compose-acts">
          <span class="muted compose-hint">${kind === "good" ? "每一件都会变成夜空里的一颗星" : "写下来就好，没人会评判"}</span>
          <button class="btn btn-main" id="newsSave">${icon("check")}记下来</button>
        </div>
      </section>

      <section class="section">
        <div class="news-filter">${[["all", "全部", all.length], ["good", "小确幸", stars.length], ["meme", "内心戏", memes.length]].map(([k, l, n]) =>
          `<button class="chip ${k === filter ? "on" : ""}" data-filter="${k}">${l}<small>${n}</small></button>`).join("")}</div>
        ${groups.map((g, gi) => `<div class="news-day">${esc(g.k)}</div><div class="news-list">
          ${g.items.map((r, i) => `<div class="news-item ${r.type}" style="--i:${gi * 3 + i}">${tile(KIND[r.type].ic, KIND[r.type].color, 38)}
            <div><div class="nt">${esc(r.text)}</div><div class="nm">${esc(KIND[r.type].label)} · ${esc((r.created_at || "").slice(11, 16))}</div></div></div>`).join("")}
        </div>`).join("") || `<div class="empty"><p>${filter === "meme" ? "还没有内心戏。脑子里吵起来的时候，来这里写两句。" : "还没有记录。"}</p></div>`}
        <p class="hint-line">这里只有你自己看得到；做成分享卡之前会先给你预览，由你决定公开哪些细节。</p>
      </section>
    </div>`;

  const tabs = root.querySelector(".news-kind");
  requestAnimationFrame(() => {
    const on = tabs.querySelector("button.on");
    Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
  });
  const ta = root.querySelector("#newsText");
  tabs.querySelectorAll("[data-kind]").forEach((b) => b.addEventListener("click", () => {
    const keep = ta.value;
    state.newsKind = b.dataset.kind;
    renderNews(root);
    const t2 = root.querySelector("#newsText");
    t2.value = keep; t2.focus();
  }));
  root.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => { state.newsFilter = b.dataset.filter; renderNews(root); }));
  root.querySelectorAll(".star").forEach((s) => s.addEventListener("click", () => {
    root.querySelectorAll(".star.open").forEach((x) => x !== s && x.classList.remove("open"));
    s.classList.toggle("open");
  }));
  const save = async () => {
    const text = ta.value.trim();
    if (!text) { toast("写一句就好"); ta.focus(); return; }
    const btn = root.querySelector("#newsSave");
    try {
      const out = await api.record(kind, text);
      setData(out);
      flyGain(btn, out.xp);
      burstAt(btn, kind === "good" ? 36 : 18);
      toast(kind === "good" ? `收下了${xpNote(out.xp) ? " · " + xpNote(out.xp) : ""}` : "收下这段内心戏了", "", KIND[kind].ic);
      renderNews(root, { fresh: out.record?.id || "" });
    } catch (e) { toast(e.message, "err"); }
  };
  root.querySelector("#newsSave").addEventListener("click", save);
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); });
}
