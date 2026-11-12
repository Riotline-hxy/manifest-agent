// 「显化你的愿望」「调整现有计划」：对话样子的全屏层。小光问一句，插图卡片放在小光的话下面，点一张变成你说的话，小光回一句接着问。
// 问题在 flows.js；后端 core/flows.py：开始拿 TA 自己的记录，答完一题需要时调一次模型，答完算结尾，勾了的才存。
// 能反悔：底下的「上一步」回到上一题；前面答过的题，点另一张卡片就从那一题重新走（后面的都撤掉）。结尾也能上一步。
// 结尾两种：显化卡（小光的小纸条 + 卡片 + 会存的东西）；调整方案（一条条改动，能取消、能说一句重新调，「一键调整」）。
// 存好以后回到对话（小光的那句话已经在里面）；「现在就去做」打开两分钟启动。
import { api } from "./api.js";
import { setData, go, aname } from "./store.js";
import { esc, icon, toast } from "./ui.js";
import { agentMini } from "./ball.js";
import { openKick } from "./kick.js";
import { ill } from "./ills.js";
import { FLOWS } from "./flows.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const BACK = `<button class="tb-back" data-back><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>上一步</button>`;

export function openTune(sceneId = "relearn", { wishId = "" } = {}) {
  const el = document.createElement("div");
  el.className = "tune";
  el.innerHTML = `
    <div class="tb-top">
      <button class="tb-x" aria-label="关闭">×</button>
      <div class="grow"><b></b><small></small></div>
      <div class="tb-dots"></div>
    </div>
    <div class="tb-thread"><div class="thread-in"><div class="msgs"></div></div></div>
    <div class="tb-dock"><div class="tb-dock-in"></div></div>`;
  document.body.append(el);
  requestAnimationFrame(() => el.classList.add("in"));
  const $ = (s) => el.querySelector(s);
  const list = $(".msgs"), thread = $(".tb-thread"), dock = $(".tb-dock-in");
  let F = null, run = null, finished = false, saved = false, gone = false, token = 0, ending = false;
  const st = { a: {}, l: {}, total: 4 };
  // 走过的每一题：{id, row 这一题的那条消息, snap 进这一题之前的答案, opts 这一题的选项}。上一步、改答案都靠它
  let frames = [];

  const down = () => requestAnimationFrame(() => thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" }));
  // 进度点：每一题可以带 dot（亮到第几个，几题同属一步时用）和 stage（顶栏小字，比如「显化第 2 步 · 消除怀疑」）
  const dots = (end = false) => {
    const n = st.total || 4, f = frames[frames.length - 1], s = f && F?.steps[f.id];
    const done = end ? n : s && s.dot != null ? val(s.dot) : Math.max(0, frames.length - 1);
    $(".tb-dots").innerHTML = Array.from({ length: n }, (_, i) => `<i class="${i < done || end ? "on" : ""} ${!end && i === done ? "now" : ""}"></i>`).join("");
    if (F) $(".tb-top small").textContent = end ? (F.endSub || F.sub) : (s && val(s.stage)) || F.sub;
  };
  const me = (text) => { list.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bub">${esc(text)}</div></div>`); down(); };
  // 小光的一条：先冒三个点，等 job 回来（或者等一小会儿）再换成内容。中途上一步 / 关掉了就返回 null
  async function xg(content, { wide = false, job = null, min = 450 } = {}) {
    const t = token;
    list.insertAdjacentHTML("beforeend", `<div class="msg assistant ${wide ? "wide" : ""}">${agentMini()}<div class="col"><div class="bub"><span class="typing"><i></i><i></i><i></i></span></div></div></div>`);
    const row = list.lastElementChild;
    down();
    let out = null;
    try {
      [out] = await Promise.all([job ? job() : null, wait(min)]);
    } catch (e) {
      if (t === token) row.remove();
      throw e;
    }
    if (gone || t !== token) return null;
    const html = typeof content === "function" ? content(out) : content;
    row.querySelector(".col").innerHTML = html.startsWith("<") ? html : `<div class="bub">${html}</div>`;
    down();
    return { row, out };
  }
  const val = (x) => (typeof x === "function" ? x(st) : x);
  const snap = () => JSON.parse(JSON.stringify(st));
  const restore = (s) => { for (const k of Object.keys(st)) delete st[k]; Object.assign(st, JSON.parse(JSON.stringify(s))); };
  // 底下一条：左边「上一步」（第一题没有），中间一句提示，右边一个按钮
  const canBack = () => !saved && frames.length > (ending ? 0 : 1);
  const bar = (hint = "", right = "") => {
    dock.innerHTML = `${canBack() ? BACK : ""}<span class="tb-hint">${hint}</span>${right}`;
    dock.querySelector("[data-back]")?.addEventListener("click", back);
  };
  // 底下一条输入框：自己写一句（「我自己写」和写一句的题都用它）
  const ask = (ph) => new Promise((res) => {
    const t = token;
    dock.innerHTML = `${canBack() ? BACK : ""}<div class="tb-composer"><input maxlength="30" placeholder="${esc(ph || "写一句")}" aria-label="${esc(ph || "写一句")}"><button class="tb-send" aria-label="发送">${icon("send")}</button></div>`;
    dock.querySelector("[data-back]")?.addEventListener("click", back);
    const inp = dock.querySelector("input");
    setTimeout(() => inp.focus(), 50);
    const send = () => { const v = inp.value.trim(); if (v && t === token) { dock.innerHTML = ""; res(v); } };
    dock.querySelector(".tb-send").addEventListener("click", send);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) send(); });
  });

  const close = () => {
    gone = true;
    document.removeEventListener("keydown", onKey);
    el.classList.remove("in");
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  };
  // 中途关掉、或者结尾没存：这次的回答不留（和别的「聊聊」一样）
  const quit = () => {
    if (run && !saved) (finished ? api.sceneDiscard(run.id) : api.sceneCancel()).catch(() => {});
    close();
  };
  $(".tb-x").addEventListener("click", quit);
  const onKey = (e) => {
    if (e.key !== "Escape") return;
    const card = el.querySelector(".mc-wrap");     // 显化卡开着：先收起卡片
    if (card) card.querySelector(".mc-x").click(); else quit();
  };
  document.addEventListener("keydown", onKey);

  // ---------------------------------------------------------------- 一题一题 ----
  // 回到第 k 题：后面的消息都撤掉，答案退回到进这一题之前，这一题重新能点
  function rewind(k) {
    token++;
    el.querySelector(".mc-wrap")?.remove();
    ending = false;
    const f = frames[k];
    while (f.row.nextElementSibling) f.row.nextElementSibling.remove();
    restore(f.snap);
    frames = frames.slice(0, k + 1);
    dots();
    arm(F.steps[f.id], f);
  }
  function back() {
    const k = ending ? frames.length - 1 : frames.length - 2;   // 停在结尾：回到最后一题；停在某一题：回到它的上一题
    if (k >= 0 && frames[k]?.row) rewind(k);
  }

  function choices(s, opts) {
    const custom = val(s.custom);
    const rows = s.type === "rows";
    const card = (o, k) => rows
      ? `<button class="rowc" data-v="${esc(o.v)}" style="--i:${k}">${icon(o.icon || "check")}<span><b>${esc(o.label)}</b>${o.hint ? `<small>${esc(o.hint)}</small>` : ""}</span>${o.prog != null ? `<em class="prog"><i style="width:${Math.round(o.prog * 100)}%"></i></em>` : ""}</button>`
      : `<button class="il" data-v="${esc(o.v)}" style="--i:${k}">${ill(o.ill)}<span><b>${esc(o.label)}</b>${o.hint ? `<small>${esc(o.hint)}</small>` : ""}</span></button>`;
    const mine = custom ? (rows
      ? `<button class="rowc mine" data-v="__mine" style="--i:${opts.length}">${icon("edit")}<span><b>我自己写</b></span></button>`
      : `<button class="il mine" data-v="__mine" style="--i:${opts.length}">${ill("pen")}<span><b>我自己写</b><small>说说你的</small></span></button>`) : "";
    const n = opts.length + (custom ? 1 : 0);
    return rows ? `<div class="rowcs" data-ch>${opts.map(card).join("")}${mine}</div>`
      : `<div class="ils ${n === 3 ? "three" : ""}" data-ch>${opts.map(card).join("")}${mine}</div>`;
  }

  async function step(id) {
    if (!id) return finish();
    const s = F.steps[id];
    const f = { id, row: null, snap: snap(), opts: [] };
    frames.push(f);
    dock.innerHTML = "";
    dots();
    // 选项可能要等小光的建议（改小一点 / 再加一件）：三个点一直冒到建议回来
    let r;
    try {
      r = await xg((opts) => {
        const sub = val(s.sub);
        let html = `<div class="bub">${val(s.q)}${sub ? `<small class="bub-sub">${esc(sub)}</small>` : ""}</div>${val(s.body) || ""}`;
        if (s.type === "text") html += `<div class="tb-chips" data-ch>${val(s.chips).map((c) => `<button class="chip" data-c="${esc(c)}">${esc(c)}</button>`).join("")}</div>`;
        if (s.type === "cards" || s.type === "rows") html += choices(s, opts);
        return html;
      }, { wide: true, job: async () => (s.type === "cards" || s.type === "rows" ? await val(s.opts) : []) });
    } catch (e) {
      toast(e.message || "" + aname() + "没想出来，再试一次", "err");
      frames.pop();
      return bar("", `<button class="tb-skip" data-retry>再试一次</button>`), dock.querySelector("[data-retry]").addEventListener("click", () => step(id));
    }
    if (!r) return;
    f.row = r.row;
    f.opts = r.out || [];
    arm(s, f);
  }

  // 让一题能答：装上点卡片、跳过、写一句的处理。第一次出现和「回到这一题」都走这里
  function arm(s, f) {
    const k = frames.indexOf(f);
    const key = s.key || f.id;
    const box = f.row.querySelector("[data-ch]");
    box?.classList.remove("dim", "past");
    box?.querySelectorAll(".on").forEach((b) => b.classList.remove("on"));
    const next = () => step(val(s.next));
    const answered = async (o, text) => {
      box?.classList.add("past");
      me(text);
      // 最后一题不再回一句：结尾那句话就是回应，两句挨着会显得啰嗦
      const last = !val(s.next);
      const r = last ? "" : typeof s.react === "function" ? s.react(o ? o.v : "custom", st, text) : (o?.react || (o ? "" : (s.customReact ?? "嗯，我记下了。")));
      // 自己写的话，小光要先听懂再回（调一次模型）：三个点冒到回来为止
      if (r && typeof r.then === "function") { if (!(await xg((t) => (t && t.startsWith("<") ? t : esc(t || "嗯，我听到了。")), { job: () => r }))) return; }
      else if (r && !(await xg(r))) return;
      next();
    };
    // 已经答过的题：点另一张就从这一题重新走（先退回这一题，再替 TA 点一下；同一个元素正在点的时候 click() 不会再触发，所以等这一下过去）
    const repick = (b) => { rewind(k); setTimeout(() => b.click()); };

    if (s.type === "info") {
      bar("", `<button class="btn btn-good tb-go">${esc(s.cta || "继续")}</button>`);
      dock.querySelector(".tb-go").addEventListener("click", () => { dock.innerHTML = ""; next(); });
      return;
    }
    if (s.type === "text") {
      const take = (v) => {
        if (box.classList.contains("dim")) return;
        box.classList.add("dim");
        dock.innerHTML = "";
        st.a[key] = v; st.l[key] = v;
        [...box.querySelectorAll(".chip")].find((c) => c.dataset.c === v)?.classList.add("on");
        answered(null, v);
      };
      box.querySelectorAll(".chip").forEach((c) => { c.onclick = () => (box.classList.contains("past") ? repick(c) : take(c.dataset.c)); });
      ask(s.ph).then(take);
      return;
    }
    const opts = f.opts, custom = val(s.custom);
    const lock = (v) => { box.classList.add("dim"); if (v) box.querySelector(`[data-v="${CSS.escape(v)}"]`)?.classList.add("on"); };
    const pick = async (v) => {
      if (box.classList.contains("dim")) return;
      if (v === "__mine") {
        lock("__mine");
        const text = await ask(custom);
        st.a[key] = "custom"; st.l[key] = text;
        return answered(null, text);
      }
      const o = opts.find((x) => x.v === v);
      lock(v);
      dock.innerHTML = "";
      if (o) { st.a[key] = v; st.l[key] = o.label; } else { delete st.a[key]; delete st.l[key]; }
      if (!o) { box.classList.add("past"); me("先跳过"); if (!(await xg("好，这个先放着。"))) return; return next(); }
      answered(o, o.label);
    };
    box.querySelectorAll("[data-v]").forEach((b) => { b.onclick = () => (box.classList.contains("past") ? repick(b) : pick(b.dataset.v)); });
    bar(s.skip !== false ? "点一张就好" : "", s.skip !== false ? `<button class="tb-skip">先跳过</button>` : "");
    dock.querySelector(".tb-skip")?.addEventListener("click", () => pick(null));
  }

  // ---------------------------------------------------------------- 结尾 ----
  async function finish() {
    ending = true;
    dock.innerHTML = "";
    dots(true);
    let r;
    try {
      r = await xg((out) => (out.letter ? `<div class="bub letter">${esc(out.letter)}</div>` : esc(out.say || "")),
        { job: () => api.flow("finish", { run_id: run.id, answers: F.answers(st) }), min: 900 });
    } catch (e) {
      toast(e.message || "没连上，再试一次", "err");
      return bar("", `<button class="tb-skip" data-retry>再试一次</button>`), dock.querySelector("[data-retry]").addEventListener("click", finish);
    }
    if (!r) return;
    finished = true;
    const out = r.out;
    if (out.state) setData(out.state);        // 练习的经验、金币先到账；聊到的内容等勾了再存
    if (out.xp?.amount) r.row.querySelector(".col").insertAdjacentHTML("beforeend",
      `<div class="tb-xp">${icon("bolt")}经验 +${out.xp.amount}${out.xp.coins ? ` · 金币 +${out.xp.coins}` : ""}</div>`);
    if (out.changes) return planEnding(out);
    return cardEnding(out);
  }

  const keepsHtml = (list) => `<div class="keeps">${list.map((it) => `<label class="keep ${it.off ? "off" : ""}"><input type="checkbox" data-k="${esc(it.key)}" ${it.off ? "disabled" : it.on === false ? "" : "checked"}>
      <span>${esc(it.html)}${it.note ? `<em>${esc(it.note)}</em>` : ""}</span><small>${esc(it.to)}</small></label>`).join("")}</div>`;

  // 存：只存勾了的。then：save 回到对话 / now 打开两分钟启动 / 一个函数（调整计划：留在这里看改了什么）
  async function saveKeys(row, keys, then, nowTask = "") {
    row.querySelectorAll(".tb-acts .btn").forEach((b) => b.classList.add("off"));
    try {
      const res = keys.length ? await api.flow("save", { run_id: run.id, keys }) : null;
      saved = true;
      if (res?.state) setData(res.state);
      if (!res) api.sceneDiscard(run.id).catch(() => {});
      if (typeof then === "function") return then(res);
      close();
      if (then === "now") openKick({ task: res?.step?.title || nowTask, stepId: res?.step?.id || "" });
      else { go("chat"); toast("存好了", "", "check"); }
    } catch (e) {
      row.querySelectorAll(".tb-acts .btn").forEach((b) => b.classList.remove("off"));
      toast(e.message || "没存上，再试一次", "err");
    }
  }

  // 显化卡：一条横栏，点开看整张卡（卡片在 openCard）；下面是会存的东西
  const STAR = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.5 6.1 6.6.5-5 4.3 1.6 6.4L12 16.6l-5.7 3.5 1.6-6.4-5-4.3 6.6-.5z"/></svg>`;
  function openCard(c) {
    el.querySelector(".mc-wrap")?.remove();
    const n = c.steps || 7;
    const lit = new Set((c.lines || []).map((x) => x.n));
    const wrap = document.createElement("div");
    wrap.className = "mc-wrap";
    wrap.innerHTML = `<div class="mc" role="dialog" aria-label="我的显化卡">
      <button class="mc-x" aria-label="收起">×</button>
      <div class="mc-head">
        <span class="mc-star">${STAR}</span><span class="mc-star s2">${STAR}</span><span class="mc-star s3">${STAR}</span>
        <small>${esc(c.small || "我的显化卡")}${c.date ? ` · ${esc(c.date)}` : ""}</small>
        <h3>${esc(c.title)}</h3>
        <div class="mc-seven" aria-label="走过的步数">${Array.from({ length: 7 }, (_, i) => `<i class="${i >= 7 - n && lit.has(i + 1) ? "on" : i < 7 - n ? "skip" : ""}"></i>`).join("")}<em>${n === 7 ? "显化七步" : "显化六步"}</em></div>
      </div>
      <ol class="mc-list">${(c.lines || []).map((x) => `<li><i>${x.n}</i><div><small>${esc(x.stage || "")}</small><p><em>${esc(x.em)}</em>${esc(x.text)}</p></div></li>`).join("")}</ol>
      ${c.vow ? `<div class="mc-vow">${esc(c.vow)}</div>` : ""}
    </div>`;
    el.append(wrap);
    requestAnimationFrame(() => wrap.classList.add("in"));
    const shut = () => { wrap.classList.remove("in"); setTimeout(() => wrap.remove(), 260); };
    wrap.addEventListener("click", (e) => { if (e.target === wrap || e.target.closest(".mc-x")) shut(); });
  }

  async function cardEnding(out) {
    const c = out.card;
    const barHtml = `<button class="mc-bar" data-card><span class="mc-bar-ic">${STAR}</span>
      <span class="mc-bar-t"><b>${esc(c.small || "我的显化卡")}</b><small>${esc(c.title)}</small></span><span class="mc-bar-go">查看</span></button>`;
    const acts = (out.acts || []).includes("now") ? `<button class="btn btn-ghost" data-now>现在就去做</button>` : "";
    const r2 = await xg(`${out.intro ? `<div class="bub">${esc(out.intro)}</div>` : ""}${barHtml}${keepsHtml(out.keeps || [])}
      <div class="tb-acts"><button class="btn btn-good" data-save>存好</button>${acts}</div>`, { wide: true, min: 300 });
    if (!r2) return;
    const row = r2.row;
    row.querySelector("[data-card]").addEventListener("click", () => openCard(c));
    bar("勾了的才存");
    const keys = () => [...row.querySelectorAll(".keep input:checked")].map((x) => x.dataset.k);
    row.querySelector("[data-save]").addEventListener("click", () => {
      if (!keys().length) { toast("勾一项再存，或者点右上角关掉"); return; }
      saveKeys(row, keys(), "save");
    });
    row.querySelector("[data-now]")?.addEventListener("click", () => saveKeys(row, keys(), "now", out.now));
  }

  // 调整方案：一条条改动（能取消），底下说一句重新调，「一键调整」后看改了什么
  async function planEnding(out, think = 0) {
    const rows = out.changes.length
      ? `<div class="chg">${out.changes.map((c, i) => `<label class="chg-row" style="--i:${i}"><input type="checkbox" checked data-k="${esc(c.key)}">
          <span><small class="k">${esc(c.label)}</small><b>${c.kind === "step_add" ? `加进「${esc(c.target)}」：${esc(c.to)}` : `<s>${esc(c.target)}</s> → ${esc(c.to)}`}</b>${c.why ? `<em>${esc(c.why)}</em>` : ""}</span></label>`).join("")}</div>`
      : `<div class="chg-none">${icon("check")}计划不用改，照现在的来就好。</div>`;
    const remember = (out.keeps || []).filter((k) => k.key === "remember");
    const target = think ? await xg(`<div class="bub">${esc(out.say)}</div>`, { wide: true, min: 1 }) : { row: list.lastElementChild };
    if (!target) return;
    const r2 = await xg(`${rows}${remember.length ? keepsHtml(remember) : ""}
      <div class="tb-acts"><button class="btn btn-good" data-go>${out.changes.length ? "一键调整" : "好"}</button></div>`, { wide: true, min: 300 });
    if (!r2) return;
    const row = r2.row;
    // 底下：觉得不对就说一句，把意见、上下文和这一版方案发给小光重新调
    dock.innerHTML = `${canBack() ? BACK : ""}<div class="tb-composer"><input maxlength="60" placeholder="哪里不对？说一句，我重新调" aria-label="哪里不对"><button class="tb-send" aria-label="发送">${icon("send")}</button></div>`;
    dock.querySelector("[data-back]")?.addEventListener("click", back);
    const inp = dock.querySelector("input");
    const t = token;
    const revise = async () => {
      const text = inp.value.trim();
      if (!text || t !== token) return;
      dock.innerHTML = "";
      row.querySelectorAll("input").forEach((x) => (x.disabled = true));
      row.querySelector(".tb-acts")?.remove();
      me(text);
      try {
        const r3 = await xg((o) => esc(o.say), { wide: true, job: () => api.flow("step", { run_id: run.id, kind: "revise", text, answers: F.answers(st) }), min: 600 });
        if (r3) planEnding(r3.out);
      } catch (e) {
        toast(e.message || "没调成，再说一次试试", "err");
        planEnding(out, 1);
      }
    };
    dock.querySelector(".tb-send").addEventListener("click", revise);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) revise(); });
    row.querySelector("[data-go]").addEventListener("click", () => {
      const keys = [...row.querySelectorAll("input:checked")].map((x) => x.dataset.k);
      if (!keys.length) { saved = true; api.sceneDiscard(run.id).catch(() => {}); close(); go("chat"); return; }
      me(out.changes.length ? "一键调整" : "好");
      saveKeys(row, keys, async (res) => {
        row.querySelectorAll("input").forEach((x) => (x.disabled = true));
        row.querySelector(".tb-acts")?.remove();
        bar("", "");
        const done = res?.done || [];
        const r4 = await xg(`${done.length ? `<div class="wcard"><small>改好了</small><b>这周的计划</b>
            <div class="plan-list">${done.map((d) => `<p>${icon("check")}<span>${esc(d)}</span></p>`).join("")}</div></div>` : ""}
          <div class="bub">${esc(done.length ? "蜕变计划里已经改好了。过一阵状态变了，再回来调。" : "记下了。过一阵状态变了，再回来调。")}</div>
          <div class="tb-acts"><button class="btn btn-good" data-ok>好</button></div>`, { wide: true, min: 700 });
        r4?.row.querySelector("[data-ok]").addEventListener("click", () => { close(); go("chat"); });
      });
    });
  }

  // ---------------------------------------------------------------- 开始 ----
  (async () => {
    try {
      const out = await api.flow("start", { scene: sceneId, wish_id: wishId });
      run = out.run;
      F = FLOWS[sceneId](out.ctx, run);
      $(".tb-top b").textContent = F.title;
      $(".tb-top small").textContent = F.sub;
      st.total = F.total || 4;
      dots();
      if (F.empty) {      // 调整现有计划，但还没有愿望：先去显化一个
        await xg("还没有愿望，也就还没有计划。先显化一个愿望？");
        bar("", `<button class="btn btn-good tb-go" data-wish>显化你的愿望</button>`);
        dock.querySelector("[data-wish]").addEventListener("click", () => { api.sceneCancel().catch(() => {}); saved = true; close(); openTune("seven_steps_lite"); });
        return;
      }
      await step(F.first(st));
    } catch (e) {
      toast(e.message || "没打开，再试一次", "err");
      close();
    }
  })();
}
