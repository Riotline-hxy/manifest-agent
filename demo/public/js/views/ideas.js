// 点子：点一个，小光带你做一遍。上面一张「今日推荐」，下面按分组排成干净的列表（Muse 式）。
// 每一项背后都是真实可玩的场景（或真实的一轮对话），不是展示图。
import { state, go } from "../store.js";
import { esc, icon, tile } from "../ui.js";
import { mountBall } from "../ball.js";
import { startScene } from "../scene.js";

const META = {
  relearn: ["compass", "var(--c-violet)"], "know-me": ["eye", "var(--c-violet)"],
  clarify: ["flag", "var(--c-orange)"], seven_steps_lite: ["steps", "var(--c-orange)"],
  meditation: ["wind", "var(--c-sky)"], gratitude: ["heart", "var(--c-pink)"],
};
const GROUPS = [["默契", "让小光更懂你"], ["愿望", "把想要的说清楚"], ["日常", "几分钟就能做完"]];

export function renderIdeas(root) {
  const ideas = state.data.ideas || [];
  const counts = state.data.scene_counts || {};
  const fresh = ideas.filter((i) => i.scene && !counts[i.scene]);
  const pool = fresh.length ? fresh : ideas.filter((i) => i.scene);
  const pick = pool[new Date().getDate() % pool.length];
  const unread = (state.data.academy || []).filter((a) => !a.read).slice(0, 3);

  root.innerHTML = `
    <div class="view-inner ideas">
      <div class="page-head"><div><h1>点子</h1><p>不知道聊什么的时候，点一个，小光带你做一遍</p></div></div>

      <section class="feature card">
        <div class="ft-copy">
          <span class="pill acc">${icon("sparkles")}今日推荐 · ${esc(pick.group)}</span>
          <h2>${esc(pick.title)}</h2>
          <p>${esc(pick.desc)}</p>
          <div class="ft-meta"><span class="pill">${icon("clock")}约 ${pick.minutes} 分钟</span>
            <span class="pill">${counts[pick.scene] ? `做过 ${counts[pick.scene]} 次` : "还没试过"}</span><span class="pill acc">完成 +12 经验</span></div>
          <button class="btn btn-main btn-lg" data-idea="${esc(pick.id)}">开始 ${icon("arrow")}</button>
        </div>
        <div class="ft-side"><div class="speech ft-say">今天想试试这个吗？</div><div class="ft-ball"></div></div>
      </section>

      ${GROUPS.map(([g, sub]) => {
        const list = ideas.filter((i) => i.group === g);
        if (!list.length) return "";
        return `<section class="section"><div class="sec-title">${esc(g)}<span class="more">${esc(sub)}</span></div>
          <div class="rows">${list.map((i, k) => {
            const [ic, col] = META[i.id] || ["sparkles", "var(--accent)"];
            return `<button class="row" data-idea="${esc(i.id)}" style="--i:${k}">${tile(ic, col, 46)}
              <span class="row-main"><b>${esc(i.title)}</b><span>${esc(i.desc)}</span></span>
              <span class="row-meta">${i.scene && counts[i.scene] ? `<span class="pill good">${icon("check")}${counts[i.scene]}</span>` : ""}<span class="muted">${i.minutes} 分钟</span></span>
              <span class="row-go">${icon("arrow")}</span></button>`;
          }).join("")}</div></section>`;
      }).join("")}

      ${unread.length ? `<section class="section"><div class="sec-title">想先读点东西？<button class="more" data-go="academy">心灵学堂 →</button></div>
        <div class="rows">${unread.map((a, k) => `<button class="row" data-art="${esc(a.id)}" style="--i:${k}">${tile("book", "var(--c-coral)", 46)}
          <span class="row-main"><b>${esc(a.title)}</b><span>${esc(a.summary)}</span></span>
          <span class="row-meta"><span class="muted">${a.minutes} 分钟</span></span><span class="row-go">${icon("arrow")}</span></button>`).join("")}</div></section>` : ""}
    </div>`;

  mountBall(root.querySelector(".ft-ball"), { size: 96 });
  root.querySelectorAll("[data-idea]").forEach((b) => b.addEventListener("click", () => {
    const idea = ideas.find((i) => i.id === b.dataset.idea);
    if (!idea) return;
    if (!idea.scene) {
      state.autoSend = "小光，你现在有多了解我？说说你记得的，也说说你还不确定的。";
      go("chat");
      return;
    }
    startScene(idea.scene);
  }));
  root.querySelectorAll("[data-art]").forEach((b) => b.addEventListener("click", () => go("article", { id: b.dataset.art })));
  root.querySelector("[data-go]")?.addEventListener("click", () => go("academy"));
}
