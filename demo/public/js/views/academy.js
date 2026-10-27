// 心灵学堂：团队审核的只读内容。卡片是「书」（读），和点子的列表（做）区分开；
// 文章页是安静的阅读版式。小光只能解释，不能改写。
import { api } from "../api.js";
import { state, go, refresh } from "../store.js";
import { esc, icon, tile } from "../ui.js";

const CH = { "认识自己": "var(--c-violet)", "显化方法": "var(--c-orange)", "中断与复原": "var(--c-sky)", "身心练习": "var(--c-mint)", "使用说明": "var(--c-coral)" };

export function renderAcademy(root) {
  const items = state.data.academy || [];
  const chapters = [];
  for (const a of items) {
    let c = chapters.find((x) => x.k === a.chapter);
    if (!c) chapters.push((c = { k: a.chapter, list: [] }));
    c.list.push(a);
  }
  root.innerHTML = `
    <div class="view-inner wide academy">
      <div class="page-head"><div><h1>心灵学堂</h1><p>团队整理、审核的内容 · 小光只读、只解释，不改写</p></div><span class="spacer"></span>
        <span class="pill good">${icon("checkc")}已读 ${items.filter((a) => a.read).length}/${items.length}</span></div>
      ${chapters.map((c, ci) => `<section class="section"><div class="sec-title">${esc(c.k)}</div>
        <div class="shelf">${c.list.map((a, i) => `<button class="book" data-art="${esc(a.id)}" style="--bk:${CH[a.chapter] || "var(--accent)"};--i:${ci * 3 + i}">
          <span class="spine"></span>
          <span class="bk-copy">
            <span class="bk-top"><span class="pill">${a.minutes} 分钟</span>${a.read ? `<span class="pill good">${icon("check")}读过</span>` : ""}</span>
            <b>${esc(a.title)}</b><span class="bk-sum">${esc(a.summary)}</span>
            <span class="bk-tags">${a.tags.map((t) => `#${esc(t)}`).join("  ")}</span>
          </span></button>`).join("")}</div></section>`).join("")}
    </div>`;
  root.querySelectorAll("[data-art]").forEach((b) => b.addEventListener("click", () => go("article", { id: b.dataset.art })));
}

export async function renderArticle(root) {
  root.innerHTML = `<div class="view-inner"><div class="empty"><p>翻开中…</p></div></div>`;
  let a;
  try {
    a = (await api.article(state.articleId)).article;
  } catch (e) {
    root.innerHTML = `<div class="view-inner"><div class="empty"><h3>没找到这篇</h3><p>${esc(e.message)}</p><button class="btn btn-main" data-back>回学堂</button></div></div>`;
    root.querySelector("[data-back]").addEventListener("click", () => go("academy"));
    return;
  }
  root.innerHTML = `
    <div class="view-inner article">
      <button class="btn btn-quiet" data-back>${icon("back")}心灵学堂</button>
      <article class="paper card" style="--bk:${CH[a.chapter] || "var(--accent)"}">
        <div class="paper-meta"><span class="ptag">${esc(a.chapter)}</span><span>${a.minutes} 分钟</span><span>${a.tags.map((t) => "#" + esc(t)).join(" ")}</span></div>
        <h1>${esc(a.title)}</h1>
        <blockquote>${esc(a.summary)}</blockquote>
        ${a.body.map((p) => `<p>${esc(p)}</p>`).join("")}
        ${a.practice ? `<div class="practice">${tile("wind", "var(--c-mint)", 44)}<div><b>现在可以试试</b>${esc(a.practice)}</div></div>` : ""}
        <div class="src">${icon("shield")}来源：${esc(a.source)}</div>
      </article>
      <div class="article-acts">
        <button class="btn btn-main btn-lg" data-ask>${icon("chat")}让小光讲给我听</button>
        <button class="btn btn-ghost btn-lg" data-back>继续逛</button>
      </div>
    </div>`;
  root.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => go("academy")));
  root.querySelector("[data-ask]").addEventListener("click", () => {
    state.autoSend = `学堂里的「${a.title}」是什么意思？用通俗的话讲给我听，再联系一下我自己的情况。`;
    go("chat");
  });
  refresh().catch(() => {});
}
