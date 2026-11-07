// 聊聊现在的你：在对话样子的全屏层里聊着来。小光问一句，插图卡片放在小光的话下面，点一张变成你说的话，小光回一句接着问；
// 答完小光说一句看到的你，给两个今天就能开始的第一小步；下面列出会存的东西，勾了的才存（core/relearn.py）。
// 存好以后回到对话（小光的那句话已经在里面）；「现在就做第一步」直接打开两分钟启动。
import { api } from "./api.js";
import { setData, go } from "./store.js";
import { esc, icon, toast } from "./ui.js";
import { agentMini } from "./ball.js";
import { openKick } from "./kick.js";

// 插图：柔和的扁平小画，颜色跟着主题（css/tune.css 里 .ill 的几种填色和线条）
const POT = `<path class="pot" d="M35 46h26l-3 14H38z"/><rect class="pot2" x="33" y="42" width="30" height="6" rx="2.5"/>`;
const LEAF = (x, y, s, k = "fm") => `<path class="${k}" d="M48 ${y}c${-9 * s} 0 ${-13 * s}-4 ${-14 * s}-10 ${8 * s}-1 ${13 * s} 3 ${14 * s} 10z" transform="translate(${x} 0)"/>`;
const LEAF_R = (y, s, k = "fm2") => `<path class="${k}" d="M48 ${y}c${9 * s} 0 ${13 * s}-4 ${14 * s}-10 ${-8 * s}-1 ${-13 * s} 3 ${-14 * s} 10z"/>`;
const ILL = {
  // 最近的状态：节奏线
  busy: `<path class="s2" d="M6 28c10 14 14 16 22 0s12-14 18 4 10 14 18-2 10-12 26 2"/><path class="s" d="M6 38c8-18 14-18 20 0s12 16 18-2 10-18 18 0 12 14 28-6"/>`,
  steady: `<path class="s2 dash" d="M6 44h84"/><path class="s" d="M6 32c14-9 28-9 42 0s28 9 42 0"/>`,
  change: `<path class="s2 dash" d="M6 46h30"/><path class="s" d="M36 46c14 0 18-24 34-26 8-1 12-2 16-4"/><circle class="fl" cx="88" cy="15" r="5"/>`,
  slow: `<path class="s" d="M6 38h20M33 38h13M53 38h8M68 38h3"/><path class="f1" d="M83 14a10 10 0 1 0 7 16 8 8 0 0 1-7-16z"/>`,
  // 想变好的方向
  wish: `<path class="f2" d="M4 58c14-17 30-24 44-24s30 8 44 24z"/><path class="s" d="M48 34V8"/><path class="fl" d="M48 8h20l-5 6 5 6H48z"/>`,
  body: `<path class="s2 dash" d="M16 50a32 32 0 0 1 64 0"/><path class="s" d="M8 50h80"/><circle class="fl" cx="26" cy="27" r="9"/><path class="f1" d="M71 15a9 9 0 1 0 8 13 7 7 0 0 1-8-13z"/>`,
  study: `<path class="fs" d="M12 16c11-4 23-4 36 2v36c-13-6-25-6-36-2z"/><path class="f2" d="M84 16c-11-4-23-4-36 2v36c13-6 25-6 36-2z"/><path class="s2" d="M20 27c7-2 13-2 20 1M20 36c7-2 13-2 20 1M56 28c7-3 13-3 20-1M56 37c7-3 13-3 20-1"/>`,
  mood: `<ellipse class="f2" cx="48" cy="48" rx="36" ry="9"/><ellipse class="s2" cx="48" cy="48" rx="20" ry="4.5"/><path class="fp" d="M48 38c-9-6-15-10-15-17a7.5 7.5 0 0 1 15-3 7.5 7.5 0 0 1 15 3c0 7-6 11-15 17z"/>`,
  people: `<rect class="f2" x="8" y="12" width="44" height="26" rx="13"/><path class="f2" d="M18 35l-4 10 12-8z"/><rect class="fs" x="42" y="26" width="46" height="24" rx="12"/><path class="fs" d="M78 47l5 9-12-7z"/><circle class="f1" cx="56" cy="38" r="2.6"/><circle class="f1" cx="65" cy="38" r="2.6"/><circle class="f1" cx="74" cy="38" r="2.6"/>`,
  // 现在能拿出多少劲：同一个小花盆，苗一点点长高
  pot1: POT + `<path class="s" d="M48 42v-8"/>` + LEAF(0, 36, .7) + LEAF_R(36, .7),
  pot2: POT + `<path class="s" d="M48 42V20"/>` + LEAF(0, 36, .8) + LEAF_R(36, .8) + LEAF(0, 26, .9) + LEAF_R(26, .9),
  pot3: POT + `<path class="s" d="M48 42V14"/>` + LEAF(0, 36, .8) + LEAF_R(36, .8) + LEAF(0, 27, .95) + LEAF_R(27, .95)
    + `<circle class="fp" cx="44" cy="11" r="3.6"/><circle class="fp" cx="52" cy="11" r="3.6"/><circle class="fp" cx="48" cy="7" r="3.6"/><circle class="fp" cx="48" cy="15" r="3.6"/><circle class="fl" cx="48" cy="11" r="2.8"/>`,
  // 路上怎么陪
  listen: `<rect class="f2" x="8" y="10" width="50" height="30" rx="15"/><path class="f2" d="M18 37l-5 12 14-9z"/><circle class="f1" cx="22" cy="25" r="3.2"/><circle class="f1" cx="33" cy="25" r="3.2"/><circle class="f1" cx="44" cy="25" r="3.2"/><circle class="fm" cx="76" cy="42" r="11"/>`,
  untangle: `<path class="s2" d="M6 32c4-15 12-15 12 0s8 15 12 0 8-13 10 2-6 8-2-2"/><path class="s" d="M50 32h32"/><path class="s" d="M76 25l8 7-8 7"/>`,
  push: `<rect class="f2" x="10" y="44" width="18" height="10" rx="3"/><rect class="f1" x="31" y="33" width="18" height="21" rx="3"/><rect class="fs" x="52" y="21" width="18" height="33" rx="3"/><path class="s" d="M76 22l10-10M78 12h8v8"/>`,
  cheer: `<circle class="fl" cx="46" cy="32" r="21"/><path class="star" d="M46 19l3.8 8.6 9.3.9-7 6.2 2.1 9.1-8.2-4.8-8.2 4.8 2.1-9.1-7-6.2 9.3-.9z"/><circle class="fp" cx="76" cy="14" r="3.5"/><circle class="f1" cx="16" cy="16" r="2.6"/><circle class="fm" cx="80" cy="48" r="2.6"/>`,
};
// 花盆画得窄，用窄一点的画框，三列的小卡片里才不会显得太小
const VIEW = { pot1: "22 0 52 64", pot2: "22 0 52 64", pot3: "22 0 52 64" };
const ill = (k) => `<svg class="ill" viewBox="${VIEW[k] || "0 0 96 64"}" aria-hidden="true">${ILL[k] || ""}</svg>`;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const SKIP = "（跳过）";

export function openTune() {
  const el = document.createElement("div");
  el.className = "tune";
  el.innerHTML = `
    <div class="tb-top">
      <button class="tb-x" aria-label="关闭">×</button>
      <div class="grow"><b>聊聊现在的你</b><small>说说现在的你，我们从这里开始</small></div>
      <div class="tb-dots"></div>
    </div>
    <div class="tb-thread"><div class="thread-in"><div class="msgs"></div></div></div>
    <div class="tb-dock"><div class="tb-dock-in"></div></div>`;
  document.body.append(el);
  requestAnimationFrame(() => el.classList.add("in"));
  const $ = (s) => el.querySelector(s);
  const list = $(".msgs"), thread = $(".tb-thread"), dock = $(".tb-dock-in");
  let run = null, total = 4, done = 0, saved = false, gone = false, first = 0;

  const down = () => requestAnimationFrame(() => thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" }));
  const dots = (now) => { $(".tb-dots").innerHTML = Array.from({ length: total }, (_, i) => `<i class="${i < done ? "on" : ""} ${i === now ? "now" : ""}"></i>`).join(""); };
  const me = (text) => { list.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bub">${esc(text)}</div></div>`); down(); };
  // 小光的一条：先冒三个点，等 job 回来（或者等一小会儿）再换成内容
  async function xg(content, { wide = false, job = null, min = 450 } = {}) {
    list.insertAdjacentHTML("beforeend", `<div class="msg assistant ${wide ? "wide" : ""}">${agentMini()}<div class="col"><div class="bub"><span class="typing"><i></i><i></i><i></i></span></div></div></div>`);
    const row = list.lastElementChild;
    down();
    let out = null;
    try {
      [out] = await Promise.all([job ? job() : null, wait(min)]);
    } catch (e) {
      row.remove();
      throw e;
    }
    if (gone) return null;
    const html = typeof content === "function" ? content(out) : content;
    row.querySelector(".col").innerHTML = html.startsWith("<") ? html : `<div class="bub">${html}</div>`;
    down();
    return { row, out };
  }

  const close = () => {
    gone = true;
    document.removeEventListener("keydown", onKey);
    el.classList.remove("in");
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  };
  // 中途关掉：这次的回答不留（和别的「聊聊」一样）
  const quit = () => {
    if (run && !saved) api.sceneCancel().catch(() => {});
    close();
  };
  $(".tb-x").addEventListener("click", quit);
  const onKey = (e) => { if (e.key === "Escape") quit(); };
  document.addEventListener("keydown", onKey);

  function ask(step) {
    total = step.total || total;
    dots(step.index);
    dock.innerHTML = "";
    const head = step.intro ? `${esc(step.intro)}<br>${esc(step.q)}` : esc(step.q);
    return xg(`<div class="bub">${head}</div><div class="ils ${step.opts.length === 3 ? "three" : ""}">${step.opts.map((o, k) =>
      `<button class="il" data-v="${esc(o.v)}" style="--i:${k}">${ill(o.ill)}<span><b>${esc(o.label)}</b><small>${esc(o.hint)}</small></span></button>`).join("")}</div>`,
    { wide: true }).then((r) => {
      if (!r) return;
      const cards = r.row.querySelector(".ils");
      cards.querySelectorAll(".il").forEach((b) => b.addEventListener("click", () => pick(step, b.dataset.v, cards)));
      dock.innerHTML = `<span class="tb-hint">点一张就好</span><button class="tb-skip">先跳过</button>`;
      dock.querySelector(".tb-skip").addEventListener("click", () => pick(step, null, cards));
    });
  }

  async function pick(step, v, cards) {
    if (cards.classList.contains("dim")) return;
    const o = v ? step.opts.find((x) => x.v === v) : null;
    cards.classList.add("dim");
    if (o) cards.querySelector(`[data-v="${CSS.escape(v)}"]`).classList.add("on");
    dock.innerHTML = "";
    me(o ? o.label : "先跳过");
    done = step.index + 1;
    dots(-1);
    const last = step.index + 1 >= total;
    try {
      const r = await xg((out) => esc(out.done ? (out.review?.say || "") : (out.reply || "好，这个先放着。")), {
        job: () => api.sceneAnswer(run.id, o ? o.v : SKIP), min: last ? 900 : 450,
      });
      if (!r) return;
      if (r.out.done) ending(r.out, r.row);
      else ask(r.out.step);
    } catch (e) {
      toast(e.message || "没连上，再点一次试试", "err");
      cards.classList.remove("dim");
      cards.querySelector(".il.on")?.classList.remove("on");
      list.lastElementChild?.remove();     // 撤掉刚才那句「我」
      dock.innerHTML = `<span class="tb-hint">点一张就好</span>`;
    }
  }

  // 结束页：小光看到的你 → 两个第一小步挑一个 → 会存下的东西（都能取消）
  async function ending(out, seeRow) {
    if (out.state) setData(out.state);         // 练习的经验、金币先到账；聊到的内容等勾了再存
    const rv = out.review;
    if (out.xp?.amount) seeRow.querySelector(".col").insertAdjacentHTML("beforeend",
      `<div class="tb-xp">${icon("bolt")}经验 +${out.xp.amount}${out.xp.coins ? ` · 金币 +${out.xp.coins}` : ""}</div>`);
    const stepIt = rv.items.find((it) => it.key === "step");
    const keeps = rv.items.map((it) => `<label class="keep ${it.off ? "off" : ""}"><input type="checkbox" data-k="${it.key}" ${it.off ? "disabled" : "checked"}>
      <span>${it.key === "step" ? `第一小步：<b class="k-step">${esc(stepIt.choices[0].title)}</b>`
        : it.key === "wish" ? `新的愿望「${esc(it.text)}」` : `${esc(it.title)}：${esc(it.text)}`}${it.note ? `<em>${esc(it.note)}</em>` : ""}</span>
      <small>${esc(it.to)}</small></label>`).join("");
    const r = await xg(`<div class="bub">我们从这一步开始？挑一个：</div>
      <div class="firsts">${stepIt.choices.map((c, k) => `<button class="first ${k === 0 ? "on" : ""}" data-i="${k}" style="--i:${k}">
        <span><b>${esc(c.title)}</b><small>${esc(c.why)}</small></span><i>${k === 0 ? icon("check") : ""}</i></button>`).join("")}</div>
      ${rv.wish ? `<p class="tb-under">${icon("flag")}放在愿望「${esc(rv.wish)}」下面</p>` : ""}
      <div class="keeps">${keeps}</div>
      <div class="tb-acts"><button class="btn btn-good" data-go>存好，开始吧</button><button class="btn btn-ghost" data-now>现在就做第一步</button></div>`,
    { wide: true });
    if (!r) return;
    const row = r.row;
    row.querySelectorAll(".first").forEach((b) => b.addEventListener("click", () => {
      first = +b.dataset.i;
      row.querySelectorAll(".first").forEach((x, k) => { x.classList.toggle("on", k === first); x.querySelector("i").innerHTML = k === first ? icon("check") : ""; });
      row.querySelector(".k-step").textContent = stepIt.choices[first].title;
    }));
    dock.innerHTML = `<div class="tb-composer"><input maxlength="200" placeholder="${esc(rv.extra?.q || "")}（可以不写）" aria-label="还有什么想让我先知道的"></div>`;
    const extra = dock.querySelector("input");
    const go_ = async (now) => {
      const items = [...row.querySelectorAll(".keep input:checked")].map((x) => ({ key: x.dataset.k, text: x.dataset.k === "step" ? stepIt.choices[first].title : "" }));
      if (!items.length && !extra.value.trim()) { toast("勾一项，或者写一句再存"); return; }
      row.querySelectorAll(".tb-acts .btn").forEach((b) => b.classList.add("off"));
      try {
        const res = await api.sceneSave(run.id, items, extra.value.trim());
        saved = true;
        if (res.state) setData(res.state);
        close();
        if (now && res.step) openKick({ task: res.step.title, stepId: res.step.id });
        else { go("chat"); toast("存好了，第一小步在「今天」里", "", "check"); }
      } catch (e) {
        row.querySelectorAll(".tb-acts .btn").forEach((b) => b.classList.remove("off"));
        toast(e.message || "没存上，再试一次", "err");
      }
    };
    row.querySelector("[data-go]").addEventListener("click", () => go_(false));
    row.querySelector("[data-now]").addEventListener("click", () => go_(true));
  }

  (async () => {
    dots(0);
    try {
      const out = await api.sceneStart("relearn");
      run = out.run;
      await ask(out.step);
    } catch (e) {
      toast(e.message || "没打开，再试一次", "err");
      close();
    }
  })();
}
