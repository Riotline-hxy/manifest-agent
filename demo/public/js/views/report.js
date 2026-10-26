// 蜕变报告：14 天 / 30 天，封面 + 故事节点 + 可核对来源 + 分享预览。
// 数据不足时诚实说明天数，不凑故事。
import { api } from "../api.js";
import { state, setData } from "../store.js";
import { esc, toast, icon, sheet, h, fmtDay } from "../ui.js";

export async function renderReport(root) {
  const days = state.reportDays || 14;
  root.innerHTML = `<div class="page-inner"><p style="color:var(--ink-3)">正在把小事情串起来…</p></div>`;
  let r;
  try {
    // 先用确定性事实 + 模板文案立刻渲染；模型润色在后台替换
    r = await api.report(days, true);
  } catch (e) {
    root.innerHTML = `<div class="page-inner"><div class="empty"><div class="glyph">…</div><p>${esc(e.message)}</p></div></div>`;
    return;
  }
  state.reportData = r;
  const polish = api.report(days, false).then((full) => {
    if (state.reportDays !== days || state.route !== "report") return;
    state.reportData = full;
    const letter = root.querySelector(".report-letter");
    if (letter && full.narrative) letter.textContent = full.narrative.text;
    const title = root.querySelector(".report-hero h2");
    if (title && full.narrative?.title) title.textContent = full.narrative.title;
  }).catch(() => {});

  const tabs = (r.periods || []).map((p) => `
    <button class="chip ${p.days === r.period ? "on" : ""}" data-days="${p.days}">
      ${p.label}${p.ready ? "" : " · 未满"}</button>`).join("");

  if (!r.ready) {
    root.innerHTML = `
      <div class="page-inner">
        <div class="section-head"><h2>蜕变报告</h2><p>用真实记录写，不补故事</p></div>
        <div class="report-gate">
          <div class="rn">${r.days_in}</div>
          <div class="eyebrow" style="margin-top:6px">陪伴天数</div>
          <p>第一份 ${r.period} 天报告会在第 ${r.period} 天解锁。现在也有一份「当下回顾」，用的是已有的 ${r.facts.good} 条好消息和 ${r.facts.done} 个小步。</p>
          <div style="display:flex;gap:8px;justify-content:center">${tabs}</div>
        </div>
        ${r.narrative ? reportCard(r, true) : ""}
      </div>`;
  } else {
    root.innerHTML = `
      <div class="page-inner">
        <div class="section-head">
          <h2>蜕变报告</h2>
          <p>${r.period} 天 · 每个节点都能核对来源</p>
          <div class="spacer"></div>
          ${tabs}
        </div>
        ${r.empty ? `<div class="empty"><div class="glyph">·</div><p>这 ${r.period} 天里还没有足够的记录。报告不会凭空生成。</p></div>` : reportCard(r, false)}
      </div>`;
  }

  root.querySelectorAll("[data-days]").forEach((b) => {
    b.addEventListener("click", () => {
      state.reportDays = Number(b.dataset.days);
      renderReport(root);
    });
  });

  const share = root.querySelector("#shareReport");
  share?.addEventListener("click", () => openShare(r));
  const print = root.querySelector("#printReport");
  print?.addEventListener("click", () => window.print());
}

function reportCard(r, compact) {
  const n = r.narrative || { title: "当下", text: "" };
  return `<article class="report-card">
    <div class="report-hero">
      <img src="assets/pets/${esc(r.cover || "report-cover")}.webp" alt="">
      <div class="rt">
        <div class="kicker">${r.period} 天 · 蜕变报告</div>
        <h2>${esc(n.title || "这 " + r.period + " 天的你")}</h2>
      </div>
    </div>
    <div class="report-body">
      <div class="report-letter">${esc(n.text || "")}</div>
      ${r.nodes.map((node) => `
        <div class="story-node">
          <div class="sk">${esc(node.label)}</div>
          <div>
            <div class="st">${esc(node.title)}</div>
            <div class="sd">${esc(node.text)}</div>
            ${node.sources?.length ? `<details><summary>核对来源 · ${node.sources.length}</summary>
              <ul class="srcs">${node.sources.map((s) => `<li>${esc(s.text)}</li>`).join("")}</ul></details>` : ""}
          </div>
        </div>`).join("")}
      ${r.surprise ? `<div class="surprise"><div class="lbl">你可能没注意到的</div><div class="txt">${esc(r.surprise)}</div></div>` : ""}
      <div class="report-actions">
        ${compact ? "" : `<button class="btn btn-ink" id="shareReport">${icon("spark")}生成分享预览</button>`}
        <button class="btn btn-ghost" id="printReport">打印 / 存为 PDF</button>
      </div>
      <p style="font-size:11px;color:var(--ink-4);margin-top:14px;line-height:1.8">
        报告默认仅本人可见。分享前会先给你一页预览，敏感细节由你逐项决定是否公开。
      </p>
    </div>
  </article>`;
}

// 分享预览：逐项勾选，默认隐藏人名与地点这类敏感细节
function openShare(r) {
  const n = r.narrative || {};
  const rows = [
    { id: "letter", label: "小光写的这一段话", sub: n.title || "", on: true },
    ...r.nodes.slice(0, 4).map((node) => ({
      id: "n-" + node.label,
      label: node.title,
      sub: node.label,
      on: node.kind !== "good",
    })),
    { id: "surprise", label: "一条「你可能没注意到的」", sub: r.surprise || "", on: !!r.surprise },
    { id: "numbers", label: `数字：${r.facts.good} 条好消息 · ${r.facts.done} 个小步 · ${r.xp} 经验`, sub: "不含任何具体内容", on: true },
  ].filter((x) => x.sub !== undefined && (x.label || x.sub));

  const body = h("div", {});
  body.innerHTML = `
    <p style="font-size:12.5px;color:var(--ink-2);line-height:1.8;margin:0 0 10px">
      选好要公开的部分。私密记录不会因为生成报告而自动公开。
    </p>
    ${rows.map((x) => `<label class="share-row">
      <input type="checkbox" ${x.on ? "checked" : ""} data-share="${esc(x.id)}">
      <span>${esc(x.label)}${x.sub ? `<span class="sub" style="display:block">${esc(x.sub)}</span>` : ""}</span>
    </label>`).join("")}`;

  const footer = [
    h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"),
    h("button", {
      class: "btn btn-ink",
      onclick: async () => {
        const on = Array.from(body.querySelectorAll("[data-share]:checked")).map((x) => x.dataset.share);
        const text = buildShareText(r, on);
        try {
          await navigator.clipboard.writeText(text);
          toast("文字版已复制，可以贴到任何地方");
        } catch {
          toast("复制失败，请手动选择文本", "err");
        }
        s.close();
      },
    }, "复制文字版"),
  ];
  const s = sheet({ title: "分享预览", body, footer });
}

function buildShareText(r, on) {
  const n = r.narrative || {};
  const lines = [`「${n.title || "这 " + r.period + " 天的你"}」`, ""];
  if (on.includes("letter") && n.text) lines.push(n.text, "");
  for (const node of r.nodes.slice(0, 4)) {
    if (on.includes("n-" + node.label)) lines.push(`· ${node.label}：${node.title}`);
  }
  if (on.includes("surprise") && r.surprise) lines.push("", r.surprise);
  if (on.includes("numbers")) {
    lines.push("", `${r.period} 天：${r.facts.good} 条好消息 · ${r.facts.done} 个小步 · ${r.xp} 经验`);
  }
  lines.push("", "—— 来自显伴 · 小光");
  return lines.join("\n");
}
