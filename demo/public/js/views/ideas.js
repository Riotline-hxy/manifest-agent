// 点子：点一个，小光带你做一遍。上面一张「今日推荐」，下面按分组排成干净的列表（Muse 式）。
// 每一项背后都是真实可玩的场景（或真实的一轮对话），不是展示图。
import { state, go } from "../store.js";
import { esc, icon, tile } from "../ui.js";
import { mountBall } from "../ball.js";
import { startScene } from "../scene.js";
import { openKick } from "../kick.js";
import { openTune } from "../tune.js";

const META = {
  seven_steps_lite: ["star", "var(--c-orange)"], relearn: ["sprout", "var(--c-violet)"],
  kickstart: ["footsteps", "var(--c-mint)"], meditation: ["wind", "var(--c-sky)"], gratitude: ["heart", "var(--c-pink)"],
  topic_blank_day: ["sun", "var(--c-lemon)"], topic_manual: ["book", "var(--c-sky)"], topic_parallel: ["sparkles", "var(--c-violet)"],
};
const GROUPS = [["愿望", "一个让你更相信，一个让它做得成"], ["日常", "几分钟就能做完"], ["话题", "不知道聊什么，点一个"]];

export function renderIdeas(root) {
  const ideas = state.data.ideas || [];
  const counts = state.data.scene_counts || {};
  // 今日推荐由后端每天定一次（和每日任务里的「做今天推荐的练习」是同一个），做完也不会换
  const dl = state.data.growth?.daily || {};
  const pick = ideas.find((i) => i.scene && i.scene === dl.pick) || ideas.find((i) => i.scene);
  const task = (dl.tasks || []).find((t) => t.id === "pick" || t.id === "practice");
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
            <span class="pill">${counts[pick.scene] ? `做过 ${counts[pick.scene]} 次` : "还没试过"}</span><span class="pill acc">完成 +12 经验 · +10 金币</span>${task && !task.done ? `<span class="pill good">今天的每日任务再 +${task.xp} 经验 · +${task.coins} 金币</span>` : ""}</div>
          <button class="btn btn-main btn-lg" data-idea="${esc(pick.id)}">${esc(pick.cta || "开始")} ${icon("arrow")}</button>
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
              <span class="row-meta">${i.scene && counts[i.scene] ? `<span class="pill good">${icon("check")}${counts[i.scene]}</span>` : ""}<span class="muted">${i.kind === "topic" ? "聊几句" : `${i.minutes} 分钟`}</span></span>
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
    if (idea.kind === "kick") openKick();
    else if (idea.kind === "tune") openTune(idea.scene);
    else if (idea.kind === "topic") {          // 话题：去对话，替你发出那句话，小光照话题陪你聊
      state.autoSend = idea.send;
      state.pendingTopic = idea.topic;
      go("chat");
    } else startScene(idea.scene);
  }));
  root.querySelectorAll("[data-art]").forEach((b) => b.addEventListener("click", () => go("article", { id: b.dataset.art })));
  root.querySelector("[data-go]")?.addEventListener("click", () => go("academy"));
}
