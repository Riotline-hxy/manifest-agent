// 心灵学堂：团队审核的只读内容。列表与文章详情在同一个模块，
// 卡片样式和行动文案刻意与「点子」区分开——这里是「读」，那里是「做」。
import { api } from "../api.js";
import { state, go, setData } from "../store.js";
import { esc, toast, icon, richText } from "../ui.js";

export function renderAcademy(root) {
  const items = state.data.academy || [];
  const byChapter = {};
  for (const a of items) (byChapter[a.chapter] ||= []).push(a);

  root.innerHTML = `
    <div class="page-inner">
      <div class="section-head">
        <h2>心灵学堂</h2>
        <p>团队整理与审核的内容 · 小光只读，不能改写</p>
      </div>
      ${Object.entries(byChapter).map(([ch, list]) => `
        <div style="margin-bottom:24px">
          <div class="pg-head" style="font-size:11px;letter-spacing:.18em;color:var(--ink-4);margin-bottom:10px">${esc(ch)}</div>
          <div class="card-grid">
            ${list.map((a) => `
              <button class="idea-card academy" data-art="${esc(a.id)}">
                <span class="grp">${a.minutes} 分钟</span>
                <span class="ic">${icon("book")}</span>
                <h3>${esc(a.title)}</h3>
                <p>${esc(a.summary)}</p>
                <span class="go">${a.read ? "已读 · 再读一遍" : "阅读"} ${icon("arrow")}</span>
              </button>`).join("")}
          </div>
        </div>`).join("")}
      <p style="font-size:11.5px;color:var(--ink-4);line-height:1.9">
        学堂文章由团队维护。你可以让小光解释其中任何一篇，但它不会在对话里新建、上传或修改正式内容。
      </p>
    </div>`;

  root.querySelectorAll("[data-art]").forEach((b) => {
    b.addEventListener("click", () => {
      state.articleId = b.dataset.art;
      go("article");
    });
  });
}

export async function renderArticle(root) {
  root.innerHTML = `<div class="page-inner"><p style="color:var(--ink-3)">正在打开…</p></div>`;
  let article;
  try {
    const out = await api.article(state.articleId);
    article = out.article;
  } catch (e) {
    root.innerHTML = `<div class="page-inner"><div class="empty"><div class="glyph">?</div>
      <p>${esc(e.message || "没有这篇文章")}</p>
      <button class="btn btn-ghost" id="backAcademy">回到学堂</button></div></div>`;
    root.querySelector("#backAcademy")?.addEventListener("click", () => go("academy"));
    return;
  }
  root.innerHTML = `
    <div class="page-inner article-page">
      <button class="btn btn-quiet btn-sm" id="backAcademy" style="margin-bottom:18px">← 心灵学堂</button>
      <div class="art-meta">
        <span class="tag gold">${esc(article.chapter)}</span>
        <span>${article.minutes} 分钟</span>
        <span>${article.tags.map(esc).join(" · ")}</span>
      </div>
      <h2>${esc(article.title)}</h2>
      <div class="summary">${esc(article.summary)}</div>
      <div class="prose">
        ${article.body.map((p) => `<p>${esc(p)}</p>`).join("")}
      </div>
      ${article.practice ? `<div class="practice"><b>可以现在练习</b>${esc(article.practice)}</div>` : ""}
      <div class="src">来源：${esc(article.source)}</div>
      <div style="display:flex;gap:10px;margin-top:22px;flex-wrap:wrap">
        <button class="btn btn-ink" id="askXiaoguang">${icon("chat")}让小光解释这篇</button>
        <button class="btn btn-ghost" id="backAcademy2">继续读别的</button>
      </div>
    </div>`;

  const back = () => go("academy");
  root.querySelector("#backAcademy").addEventListener("click", back);
  root.querySelector("#backAcademy2").addEventListener("click", back);
  root.querySelector("#askXiaoguang").addEventListener("click", async () => {
    state.composerDraft = `学堂里的「${article.title}」是什么意思？用通俗的话讲给我听。`;
    go("chat");
    await api.academy();
  });
  // 阅读记录以服务端为准，但不必为它整页刷新
}
