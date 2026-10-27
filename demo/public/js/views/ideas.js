// 点子：点一下，小光带你做一遍。便当盒式排版：今日推荐一张大卡，其余按分组、大小错落。
// 每张卡背后都是真实可玩的场景（或真实的一轮对话），不是展示图。
import { state, go } from "../store.js";
import { esc, icon } from "../ui.js";
import { art } from "../fx.js";
import { startScene } from "../scene.js";

const META = {
  relearn: { art: "st-compass", tone: "violet", line: "六个生活里的小岔路" },
  "know-me": { art: "st-mirror", tone: "violet", line: "它记得的，和它不确定的" },
  clarify: { art: "st-flag", tone: "lamp", line: "把「想变好」说成一个画面" },
  seven_steps_lite: { art: "st-steps", tone: "lamp", line: "七步，每步一句话" },
  meditation: { art: "st-lotus", tone: "sky", line: "4 拍吸，4 拍呼，六轮" },
  gratitude: { art: "st-letter", tone: "pink", line: "三件已经发生的好事" },
};
const GROUPS = ["全部", "默契", "愿望", "日常"];
const SIZES = ["tall", "", "wide", "", "", "wide"];

export function renderIdeas(root) {
  const ideas = state.data.ideas || [];
  const counts = state.data.scene_counts || {};
  const f = state.ideaFilter || "全部";
  // 今日推荐：还没做过的优先，按日期轮换
  const fresh = ideas.filter((i) => i.scene && !counts[i.scene]);
  const pool = fresh.length ? fresh : ideas.filter((i) => i.scene);
  const pick = pool[new Date().getDate() % pool.length];
  const rest = ideas.filter((i) => i.id !== pick.id && (f === "全部" || i.group === f));
  const academy = (state.data.academy || []).filter((a) => !a.read).slice(0, 2);

  root.innerHTML = `
    <div class="view-inner wide ideas">
      <div class="page-title"><img src="${art("st-compass")}" alt=""><div><h1>点子</h1><p>不知道聊什么的时候，点一张，小光带你做一遍</p></div></div>

      <section class="feature tone-${META[pick.id]?.tone || "lamp"}">
        <div class="ft-copy">
          <span class="pill lamp">今日推荐 · ${esc(pick.group)}</span>
          <h2>${esc(pick.title)}</h2>
          <p>${esc(pick.desc)}</p>
          <div class="ft-meta"><span class="pill">约 ${pick.minutes} 分钟</span>
            ${counts[pick.scene] ? `<span class="pill leaf">做过 ${counts[pick.scene]} 次</span>` : `<span class="pill violet">还没试过</span>`}
            <span class="pill lamp">完成 +12 经验</span></div>
          <button class="btn btn-lamp btn-lg btn-shine" data-idea="${esc(pick.id)}">开始 ${icon("arrow")}</button>
        </div>
        <img class="ft-art sticker" src="${art(META[pick.id]?.art || "st-seed")}" alt="">
        <i class="sparkle" style="right:30%;top:16%"></i><i class="sparkle" style="right:8%;top:62%;animation-delay:-1.4s"></i>
      </section>

      <div class="tabs idea-tabs">${GROUPS.map((g) => `<button class="${g === f ? "on" : ""}" data-g="${g}">${g}</button>`).join("")}<span class="ind"></span></div>

      <section class="bento">
        ${rest.map((i, k) => {
          const m = META[i.id] || { art: "st-seed", tone: "lamp", line: "" };
          return `<button class="bento-card tone-${m.tone} ${SIZES[k % SIZES.length]} wiggle" data-idea="${esc(i.id)}" style="--i:${k}">
            <img class="sticker" src="${art(m.art)}" alt="">
            <div class="bc-copy">
              <span class="bc-grp">${esc(i.group)}</span>
              <h3>${esc(i.title)}</h3>
              <p>${esc(i.desc)}</p>
            </div>
            <div class="bc-foot"><span class="pill">${i.minutes} 分钟</span>
              ${i.scene && counts[i.scene] ? `<span class="pill leaf">✓ ${counts[i.scene]}</span>` : ""}
              <span class="go">${icon("arrow")}</span></div>
          </button>`;
        }).join("")}
      </section>

      ${academy.length ? `<section class="section">
        <div class="sec-title">想先读点东西？ <span class="more" data-go="academy">去心灵学堂 →</span></div>
        <div class="mini-books">${academy.map((a) => `<button class="mini-book" data-art="${esc(a.id)}">
          <img src="${art("st-book")}" alt=""><div><b>${esc(a.title)}</b><span>${esc(a.chapter)} · ${a.minutes} 分钟</span></div></button>`).join("")}</div>
      </section>` : ""}
    </div>`;

  const tabs = root.querySelector(".idea-tabs");
  const place = () => {
    const on = tabs.querySelector("button.on");
    const ind = tabs.querySelector(".ind");
    ind.style.left = on.offsetLeft + "px";
    ind.style.width = on.offsetWidth + "px";
  };
  requestAnimationFrame(place);
  tabs.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => {
    state.ideaFilter = b.dataset.g;
    renderIdeas(root);
  }));

  root.querySelectorAll("[data-idea]").forEach((b) => b.addEventListener("click", () => {
    const idea = ideas.find((i) => i.id === b.dataset.idea);
    if (!idea) return;
    if (!idea.scene) {
      // 「你现在有多了解我」：交给真正的对话，让小光自己说它记得什么、不确定什么
      state.autoSend = "小光，你现在有多了解我？说说你记得的，也说说你还不确定的。";
      go("chat");
      return;
    }
    startScene(idea.scene);
  }));
  root.querySelectorAll("[data-art]").forEach((b) => b.addEventListener("click", () => go("article", { id: b.dataset.art })));
  root.querySelector("[data-go]")?.addEventListener("click", () => go("academy"));
}
