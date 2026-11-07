// 「许个愿」「让愿望落地」：对话样子的全屏层。小光问一句，插图卡片放在小光的话下面，点一张变成你说的话，小光回一句接着问。
// 问题和分支在 flows.js；后端 core/flows.py：开始拿 TA 自己的记录，要建议时调一次模型，答完算结尾，勾了的才存。
// 能反悔：底下的「上一步」回到上一题；前面答过的题，点另一张卡片就从那一题重新走（后面的都撤掉）。结尾也能上一步。
// 存好以后回到对话（小光的那句话已经在里面）；「现在就做」打开两分钟启动；「让它落地」接着打开让愿望落地。
import { api } from "./api.js";
import { setData, go } from "./store.js";
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
  const dots = (end = false) => {
    const n = st.total || 4, done = Math.max(0, frames.length - 1) + (end ? 1 : 0);
    $(".tb-dots").innerHTML = Array.from({ length: n }, (_, i) => `<i class="${i < done || end ? "on" : ""} ${!end && i === done ? "now" : ""}"></i>`).join("");
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
  const onKey = (e) => { if (e.key === "Escape") quit(); };
  document.addEventListener("keydown", onKey);

  // ---------------------------------------------------------------- 一题一题 ----
  // 回到第 k 题：后面的消息都撤掉，答案退回到进这一题之前，这一题重新能点
  function rewind(k) {
    token++;
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
      toast(e.message || "小光没想出来，再试一次", "err");
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
      if (r && !(await xg(r))) return;
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
      r = await xg((out) => esc(out.say || ""), { job: () => api.flow("finish", { run_id: run.id, answers: F.answers(st) }), min: 900 });
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
    if (!out.card) {        // 「保持现在就好」「不用改了」：小光说一句就结束
      bar("", `<button class="btn btn-good tb-go" data-ok>好</button>`);
      dock.querySelector("[data-ok]").addEventListener("click", () => { saved = true; api.sceneDiscard(run.id).catch(() => {}); close(); go("chat"); });
      return;
    }
    const c = out.card;
    const cardHtml = `<div class="wcard"><small>${esc(c.small)}</small><b>${esc(c.title)}</b>
      ${c.list ? `<div class="plan-list">${c.list.map((t) => `<p>${icon("check")}<span>${esc(t)}</span></p>`).join("")}</div>` : ""}
      ${(c.lines || []).map((x) => `<p class="wc-line"><em>${esc(x.em)}</em>${esc(x.text)}</p>`).join("")}
      ${c.vow ? `${c.vow_em ? `<p class="wc-line"><em>${esc(c.vow_em)}</em></p>` : ""}<span class="vow">「${esc(c.vow)}」</span>` : ""}</div>`;
    const keeps = `<div class="keeps">${out.keeps.map((it) => `<label class="keep ${it.off ? "off" : ""}"><input type="checkbox" data-k="${esc(it.key)}" ${it.off ? "disabled" : it.on === false ? "" : "checked"}>
      <span>${esc(it.html)}${it.note ? `<em>${esc(it.note)}</em>` : ""}</span><small>${esc(it.to)}</small></label>`).join("")}</div>`;
    const acts = (out.acts || []).includes("land") ? `<button class="btn btn-ghost" data-land>${esc(out.land || "让它落地")}</button>`
      : (out.acts || []).includes("now") ? `<button class="btn btn-ghost" data-now>现在就做</button>` : "";
    const r2 = await xg(`${cardHtml}${keeps}<div class="tb-acts"><button class="btn btn-good" data-save>存好</button>${acts}</div>`, { wide: true, min: 200 });
    if (!r2) return;
    const row = r2.row;
    bar("勾了的才存");
    const save = async (then) => {
      const keys = [...row.querySelectorAll(".keep input:checked")].map((x) => x.dataset.k);
      if (!keys.length && then === "save") { toast("勾一项再存，或者点右上角关掉"); return; }
      row.querySelectorAll(".tb-acts .btn").forEach((b) => b.classList.add("off"));
      try {
        const res = keys.length ? await api.flow("save", { run_id: run.id, keys }) : null;
        saved = true;
        if (res?.state) setData(res.state);
        if (!res) api.sceneDiscard(run.id).catch(() => {});
        close();
        if (then === "land") openTune("relearn", { wishId: F.landWish?.(st, res) || "" });
        else if (then === "now") openKick({ task: res?.step?.title || out.now, stepId: res?.step?.id || "" });
        else { go("chat"); toast("存好了", "", "check"); }
      } catch (e) {
        row.querySelectorAll(".tb-acts .btn").forEach((b) => b.classList.remove("off"));
        toast(e.message || "没存上，再试一次", "err");
      }
    };
    row.querySelector("[data-save]").addEventListener("click", () => save("save"));
    row.querySelector("[data-land]")?.addEventListener("click", () => save("land"));
    row.querySelector("[data-now]")?.addEventListener("click", () => save("now"));
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
      if (F.empty) {      // 让愿望落地，但还没有愿望：先去许一个
        await xg("还没有愿望呢。先许一个，再来让它落地？");
        bar("", `<button class="btn btn-good tb-go" data-wish>去许个愿</button>`);
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
