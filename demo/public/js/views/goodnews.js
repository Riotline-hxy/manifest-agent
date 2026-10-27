// 好消息：每一条都是夜空里的一颗星。不打卡、不连胜；偷懒日是记录，不是欠账。
import { api } from "../api.js";
import { state, setData, xpNote } from "../store.js";
import { esc, fmtDay, toast } from "../ui.js";
import { art, flyXP, burstAt } from "../fx.js";

const KIND = {
  good: { art: "st-jar", label: "好消息", cls: "lamp" },
  rest: { art: "st-moon", label: "偷懒日", cls: "sky" },
  find: { art: "st-seed", label: "新发现", cls: "leaf" },
};

// 稳定的伪随机：同一条好消息永远在同一个位置
function seeded(id) {
  let h = 2166136261;
  for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0) / 4294967296);
}

export function renderNews(root, { fresh = "" } = {}) {
  const recs = state.data.records || [];
  const good = recs.filter((r) => r.type === "good");
  const groups = [];
  for (const r of recs) {
    const k = fmtDay(r.created_at || r.day);
    let g = groups.find((x) => x.k === k);
    if (!g) groups.push((g = { k, items: [] }));
    g.items.push(r);
  }

  root.innerHTML = `
    <div class="view-inner wide news">
      <div class="page-title"><img src="${art("st-jar")}" alt=""><div><h1>好消息</h1><p>不写日记也没关系，聊天里说过的好事也会落到这里</p></div></div>

      <section class="night-sky card">
        <div class="sky-field">
          ${good.slice(0, 60).map((r, i) => {
            const rnd = seeded(r.id);
            const x = 6 + rnd() * 74, y = 10 + rnd() * 74, s = 14 + rnd() * 14;
            return `<button class="star ${r.id === fresh ? "new" : ""}" style="left:${x}%;top:${y}%;--s:${s}px;--d:${-rnd() * 4}s;--i:${i}" data-id="${esc(r.id)}">
              <span class="tip"><b>${esc(fmtDay(r.created_at))}</b>${esc(r.text)}</span></button>`;
          }).join("")}
        </div>
        <div class="sky-count">
          <img class="sticker bob" src="${art("st-jar")}" alt="">
          <div><span class="num">${good.length}</span><small>颗星</small></div>
        </div>
        ${good.length ? "" : `<div class="sky-empty">第一颗星还没亮。随便写一件小事试试。</div>`}
      </section>

      <section class="compose card">
        <textarea class="field" id="newsText" rows="2" maxlength="200" placeholder="今天发生了什么值得留下来的？再小也算。"></textarea>
        <div class="compose-acts">
          <button class="btn btn-lamp" data-kind="good"><img src="${art("st-jar")}" alt="">收下这颗星</button>
          <button class="btn btn-ghost" data-kind="find"><img src="${art("st-seed")}" alt="">一个新发现</button>
          <span style="flex:1"></span>
          <button class="btn btn-ghost" data-kind="rest"><img src="${art("st-moon")}" alt="">今天是偷懒日</button>
        </div>
      </section>

      <section class="section">
        ${groups.map((g, gi) => `
          <div class="news-day">${esc(g.k)}</div>
          <div class="news-list">
            ${g.items.map((r, i) => `<div class="news-item ${KIND[r.type]?.cls || ""}" style="--i:${gi * 3 + i}">
              <img src="${art(KIND[r.type]?.art || "st-jar")}" alt="">
              <div><div class="nt">${esc(r.text)}</div><div class="nm"><span class="pill ${KIND[r.type]?.cls}">${KIND[r.type]?.label}</span>${esc((r.created_at || "").slice(11, 16))}</div></div>
            </div>`).join("")}
          </div>`).join("") || ""}
        <p class="hint-line">好消息默认只有你自己看得到；做成分享卡之前会先给你预览，由你决定公开哪些细节。</p>
      </section>
    </div>`;

  root.querySelectorAll(".star").forEach((s) => s.addEventListener("click", () => {
    root.querySelectorAll(".star.open").forEach((x) => x !== s && x.classList.remove("open"));
    s.classList.toggle("open");
  }));
  root.querySelectorAll("[data-kind]").forEach((b) => b.addEventListener("click", async () => {
    const ta = root.querySelector("#newsText");
    const kind = b.dataset.kind;
    const text = ta.value.trim();
    if (!text && kind !== "rest") { toast("写一句就好", "", "st-letter"); ta.focus(); return; }
    try {
      const out = await api.record(kind, text || "今天想休息");
      setData(out);
      if (out.xp?.amount) flyXP(b, out.xp.amount);
      burstAt(b, kind === "good" ? 40 : 14);
      toast(kind === "rest" ? "今天是偷懒日，什么都不会清零" : kind === "good" ? (xpNote(out.xp) ? `收下了 · ${xpNote(out.xp)}` : "收下了") : "记下了",
        "", KIND[kind].art);
      const newest = (out.records || [])[0];
      renderNews(root, { fresh: kind === "good" ? newest?.id : "" });
    } catch (e) { toast(e.message, "err"); }
  }));
}
