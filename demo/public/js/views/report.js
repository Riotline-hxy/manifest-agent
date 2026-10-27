// 蜕变报告：14 / 30 天。页面上是信 + 可核对来源的故事节点；
// 「播放回顾」是全屏故事模式（一页一个瞬间，数字会滚动），最后是分享预览。
// 数据不足时诚实说，不凑故事。
import { api } from "../api.js";
import { state } from "../store.js";
import { esc, toast, sheet, h, icon, tile } from "../ui.js";
import { confetti, countUp } from "../fx.js";
import { petSVG, jarSVG } from "../pet.js";

const NODE = { start: ["flag", "var(--c-orange)"], good: ["star", "var(--c-lemon)"], action: ["checkc", "var(--c-mint)"],
  rest: ["moon", "var(--c-violet)"], theme: ["quote", "var(--c-pink)"] };
const petNow = () => state.data.growth?.stage?.art || "pet-baby";

export async function renderReport(root) {
  const days = state.reportDays || 14;
  root.innerHTML = `<div class="view-inner"><div class="empty">${petSVG(petNow(), { cls: "alive" })}<p>正在把小事串起来…</p></div></div>`;
  let r;
  try {
    r = await api.report(days, true);
  } catch (e) {
    root.innerHTML = `<div class="view-inner"><div class="empty"><p>${esc(e.message)}</p></div></div>`;
    return;
  }
  draw(root, r);
  // 模型润色在后台，回来了就替换信的文字
  api.report(days, false).then((full) => {
    if (state.route !== "report" || state.reportDays !== days || !full.narrative) return;
    r.narrative = full.narrative;
    const t = root.querySelector(".letter-text");
    const hd = root.querySelector(".rep-hero h2");
    if (t) { t.textContent = full.narrative.text; t.classList.add("swap"); }
    if (hd && full.narrative.title) hd.textContent = full.narrative.title;
  }).catch(() => {});
}

function draw(root, r) {
  const n = r.narrative || { title: `这 ${r.period} 天的你`, text: "" };
  root.innerHTML = `
    <div class="view-inner report">
      <div class="page-head"><div><h1>蜕变报告</h1><p>用真实记录写成，每个节点都能核对来源</p></div>
        <span class="spacer"></span>
        <div class="tabs rep-tabs">${r.periods.map((p) => `<button class="${p.days === r.period ? "on" : ""}" data-days="${p.days}">${p.label}${p.ready ? "" : " · 未满"}</button>`).join("")}<span class="ind"></span></div>
      </div>

      <section class="rep-hero">
        <div class="rh-copy">
          <span class="pill acc">${r.period} 天 · ${r.ready ? "已解锁" : `还差 ${r.period - r.days_in} 天`}</span>
          <h2>${esc(n.title)}</h2>
          <div class="rh-nums">
            <div>${tile("star", "var(--c-lemon)", 34)}<span class="num" data-c="${r.facts.good}">0</span><small>好消息</small></div>
            <div>${tile("flag", "var(--c-orange)", 34)}<span class="num" data-c="${r.facts.done}">0</span><small>小步</small></div>
            <div>${tile("bolt", "var(--accent)", 34)}<span class="num" data-c="${r.xp}">0</span><small>经验</small></div>
          </div>
          ${r.empty ? "" : `<button class="btn btn-main btn-lg" data-play>${icon("play")}播放回顾</button>`}
        </div>
        <div class="rh-pet">${petSVG(petNow(), { cls: "alive" })}</div>
      </section>

      ${r.empty ? `<div class="empty"><h3>这 ${r.period} 天的记录还不够</h3><p>报告不会凭空编故事。多聊几句、记几件好事再来。</p></div>` : `
      <section class="letter card">
        <div class="lt-k">小光写给你</div>
        <p class="letter-text">${esc(n.text)}</p>
        <div class="lt-sign">—— ${esc(r.facts.agent || "小光")}</div>
      </section>

      <section class="section">
        <div class="sec-title">这段路上的节点 <span class="more">点开能看到原始记录</span></div>
        <div class="story">
          ${r.nodes.map((node, i) => `<div class="snode card" style="--i:${i}">
            ${tile(...(NODE[node.kind] || ["sparkles", "var(--accent)"]), 44)}
            <div class="sn-main">
              <div class="sn-k">${esc(node.label)}</div>
              <div class="sn-t">${esc(node.title)}</div>
              <div class="sn-d">${esc(node.text)}</div>
              ${node.sources?.length ? `<details><summary>核对来源 · ${node.sources.length}</summary>
                <ul>${node.sources.map((s) => `<li>${esc(s.text)}</li>`).join("")}</ul></details>` : ""}
            </div>
          </div>`).join("")}
        </div>
      </section>

      ${r.surprise ? `<section class="surprise">${tile("gift", "var(--accent)", 52)}<div><div class="sp-k">你可能没注意到的</div><div class="sp-t">${esc(r.surprise)}</div></div></section>` : ""}

      <div class="rep-acts">
        <button class="btn btn-main" data-share>${icon("sparkles")}生成分享预览</button>
        <button class="btn btn-ghost" data-play>再看一遍回顾</button>
      </div>
      <p class="hint-line">报告默认仅你自己可见。分享前会先给你一页预览，人名、地点这类细节由你逐项决定。</p>`}
    </div>`;

  root.querySelectorAll("[data-c]").forEach((el) => countUp(el, Number(el.dataset.c), 1100));
  const tabs = root.querySelector(".rep-tabs");
  requestAnimationFrame(() => {
    const on = tabs.querySelector(".on");
    Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" });
  });
  tabs.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
    state.reportDays = Number(b.dataset.days);
    renderReport(root);
  }));
  root.querySelectorAll("[data-play]").forEach((b) => b.addEventListener("click", () => play(r)));
  root.querySelector("[data-share]")?.addEventListener("click", () => share(r));
}

// ------------------------------------------------------------ 故事模式 ----
function slides(r) {
  const n = r.narrative || {};
  const pet = petNow();
  const firstGood = r.nodes.find((x) => x.kind === "good");
  const theme = r.nodes.find((x) => x.kind === "theme");
  const out = [
    { tone: "a", html: `<div class="s-art">${petSVG(pet, { cls: "alive" })}</div><div class="s-k">${r.period} 天</div><h2>这是你的<br>蜕变回顾</h2><p>${esc(r.facts.name || "你")}，准备好了吗？</p>` },
    { tone: "b", html: `<div class="s-k">这段时间你</div>
        <div class="s-nums"><div><b class="num" data-c="${r.facts.good}">0</b><span>条好消息</span></div>
        <div><b class="num" data-c="${r.facts.done}">0</b><span>个小步</span></div>
        ${r.facts.rest ? `<div><b class="num" data-c="${r.facts.rest}">0</b><span>天休息</span></div>` : ""}</div>
        <p>休息的那几天，什么都没有被清零。</p>` },
  ];
  if (firstGood) out.push({ tone: "c", html: `<div class="s-art jar">${jarSVG(r.facts.good)}</div><div class="s-k">第一颗星</div><h2 class="quote">「${esc(firstGood.title)}」</h2><p>${esc(firstGood.text)}</p>` });
  if (theme) out.push({ tone: "d", html: `<div class="s-k">你写下的好事里，反复出现的是</div><h2 class="huge">${esc(theme.title)}</h2><p>它也许比你以为的更重要。</p>` });
  if (r.surprise) out.push({ tone: "e", html: `<div class="s-k">你可能没注意到</div><h2 class="mid">${esc(r.surprise)}</h2>` });
  if (n.text) out.push({ tone: "f", html: `<div class="s-k">小光写给你</div><p class="s-letter">${esc(n.text)}</p>` });
  out.push({ tone: "a", end: true, html: `<div class="s-art">${petSVG(pet, { cls: "alive" })}</div><h2>下一段，<br>不用更快。</h2><p>想留个纪念，可以做一张只公开你选的内容的分享卡。</p>
    <div class="s-acts"><button class="btn btn-main btn-lg" data-s-share>做分享卡</button><button class="btn btn-ghost btn-lg" data-s-close>回到报告</button></div>` });
  return out;
}

function play(r) {
  const list = slides(r);
  const o = document.createElement("div");
  o.className = "story-mode";
  o.innerHTML = `<div class="sm-bars">${list.map(() => "<i><b></b></i>").join("")}</div>
    <button class="sm-x" aria-label="关闭">×</button><div class="sm-slide"></div>
    <button class="sm-prev" aria-label="上一页"></button><button class="sm-next" aria-label="下一页"></button>`;
  document.body.append(o);
  let i = 0, timer = 0;
  const bars = o.querySelectorAll(".sm-bars i");
  const show = (k) => {
    clearTimeout(timer);
    i = Math.max(0, Math.min(list.length - 1, k));
    const s = list[i];
    const slot = o.querySelector(".sm-slide");
    slot.className = `sm-slide tone-${s.tone}`;
    slot.innerHTML = `<div class="sm-in">${s.html}</div>`;
    bars.forEach((b, j) => { b.className = j < i ? "done" : j === i ? "now" : ""; });
    slot.querySelectorAll("[data-c]").forEach((el) => countUp(el, Number(el.dataset.c), 1200));
    slot.querySelector("[data-s-close]")?.addEventListener("click", close);
    slot.querySelector("[data-s-share]")?.addEventListener("click", () => { close(); share(r); });
    if (s.tone === "b" || s.end) confetti(innerWidth / 2, innerHeight * 0.3, 60);
    if (!s.end) timer = setTimeout(() => show(i + 1), 5200);
  };
  const close = () => { clearTimeout(timer); o.classList.add("out"); setTimeout(() => o.remove(), 300); document.removeEventListener("keydown", key); };
  const key = (e) => { if (e.key === "ArrowRight") show(i + 1); else if (e.key === "ArrowLeft") show(i - 1); else if (e.key === "Escape") close(); };
  o.querySelector(".sm-x").addEventListener("click", close);
  o.querySelector(".sm-next").addEventListener("click", () => (list[i].end ? null : show(i + 1)));
  o.querySelector(".sm-prev").addEventListener("click", () => show(i - 1));
  document.addEventListener("keydown", key);
  show(0);
}

// ------------------------------------------------------------ 分享预览 ----
function share(r) {
  const n = r.narrative || {};
  const rows = [
    { id: "letter", label: "小光写的那段话", sub: n.title || "", on: true },
    ...r.nodes.map((x) => ({ id: "n-" + x.label, label: `${x.label}：${x.title}`, sub: x.kind === "good" ? "含具体内容，默认不公开" : "", on: x.kind !== "good" })),
    ...(r.surprise ? [{ id: "surprise", label: "「你可能没注意到的」", sub: r.surprise, on: true }] : []),
    { id: "numbers", label: `数字：${r.facts.good} 条好消息 · ${r.facts.done} 个小步 · ${r.xp} 经验`, sub: "不含任何具体内容", on: true },
  ];
  const body = h("div", {});
  body.innerHTML = `<p style="color:var(--text-2);font-size:14px;margin:0 0 10px">勾选要公开的部分。私密记录不会因为生成报告而公开。</p>
    ${rows.map((x) => `<label class="share-row"><input type="checkbox" ${x.on ? "checked" : ""} data-k="${esc(x.id)}">
      <span><b>${esc(x.label)}</b>${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</span></label>`).join("")}`;
  const s = sheet({
    title: "分享预览", sticker: "letter", body,
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"),
      h("button", {
        class: "btn btn-main", onclick: async () => {
          const on = [...body.querySelectorAll("[data-k]:checked")].map((x) => x.dataset.k);
          const lines = [`「${n.title || `这 ${r.period} 天的你`}」`, ""];
          if (on.includes("letter") && n.text) lines.push(n.text, "");
          r.nodes.forEach((x) => on.includes("n-" + x.label) && lines.push(`· ${x.label}：${x.title}`));
          if (on.includes("surprise") && r.surprise) lines.push("", r.surprise);
          if (on.includes("numbers")) lines.push("", `${r.period} 天：${r.facts.good} 条好消息 · ${r.facts.done} 个小步 · ${r.xp} 经验`);
          lines.push("", "—— 来自显伴 · 小光");
          try { await navigator.clipboard.writeText(lines.join("\n")); toast("文字版已复制", "", "letter"); }
          catch { toast("复制失败", "err"); }
          s.close();
        },
      }, "复制文字版")],
  });
}
