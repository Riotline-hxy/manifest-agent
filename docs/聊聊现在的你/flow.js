// 原型用的通用流程：对话样子的全屏层（和 App 里「聊聊现在的你」的 B 样子一样：标题 + 一句副标题 + 进度点）。
// 步骤类型：cards 插图卡片 / rows 文字卡片（可带进度条）/ info 小光报一段 TA 自己的记录 + 继续 / text 写一句（带例子）。
// cards、rows 都可以带：body（问题下面先放一段记录）、custom（最后一张「我自己写」）、skip（默认可以跳过）。
// 能反悔：底下的「上一步」回到上一题；前面答过的题，点另一张卡片就从那一题重新走（后面的都撤掉）。
// App 里的同一套在 demo/public/js/tune.js。
(function () {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const PEN = `<path class="f2" d="M20 50l6-16 30-30 10 10-30 30z"/><path class="s" d="M56 4l10 10M20 50l16-6"/><path class="s2 dash" d="M40 56h40"/>`;
  const BACK = `<button class="tb-back" data-back><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>上一步</button>`;

  window.runFlow = function (F) {
    const st = { a: {}, l: {}, ...(F.state || {}) };
    const el = document.createElement("div");
    el.className = "tune in";
    el.innerHTML = `
      <div class="tb-top">
        <button class="tb-x" aria-label="重新开始">×</button>
        <div class="grow"><b>${esc(F.title)}</b><small>${esc(F.sub || "")}</small></div>
        <div class="tb-dots"></div>
      </div>
      <div class="tb-thread"><div class="thread-in"><div class="msgs"></div></div></div>
      <div class="tb-dock"><div class="tb-dock-in"></div></div>`;
    document.body.append(el);
    const $ = (s) => el.querySelector(s);
    const list = $(".msgs"), thread = $(".tb-thread"), dock = $(".tb-dock-in");
    let token = 0;
    // 走过的每一题：{id, row 这一题的那条消息, snap 进这一题之前的答案}。上一步、改答案都靠它
    let frames = [];

    const down = () => requestAnimationFrame(() => thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" }));
    const dots = (end = false) => { const n = st.total || 4, done = Math.max(0, frames.length - 1) + (end ? 1 : 0); $(".tb-dots").innerHTML = Array.from({ length: n }, (_, i) => `<i class="${i < done || end ? "on" : ""} ${!end && i === done ? "now" : ""}"></i>`).join(""); };
    const me = (text) => { list.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bub">${esc(text)}</div></div>`); down(); };
    async function xg(html, { wide = false, min = 520, think = 0, now = false } = {}) {
      const t = token;
      list.insertAdjacentHTML("beforeend", `<div class="msg assistant ${wide ? "wide" : ""}"><span class="mini">${mascot("idle")}</span><div class="col"><div class="bub"><span class="typing"><i></i><i></i><i></i></span></div></div></div>`);
      const row = list.lastElementChild;
      down();
      if (!now) await wait(think || min + Math.min(html.replace(/<[^>]+>/g, "").length, 50) * 7);
      if (t !== token) return null;
      row.querySelector(".col").innerHTML = html.startsWith("<") ? html : `<div class="bub">${html}</div>`;
      down();
      return row;
    }
    const val = (x) => (typeof x === "function" ? x(st) : x);
    const snap = () => JSON.parse(JSON.stringify(st));
    const restore = (s) => { for (const k of Object.keys(st)) delete st[k]; Object.assign(st, JSON.parse(JSON.stringify(s))); };
    // 底下一条：左边「上一步」（第一题没有），中间一句提示，右边一个按钮
    const bar = (hint = "", right = "", { canBack = true } = {}) => {
      dock.innerHTML = `${canBack && frames.length > (ending ? 0 : 1) ? BACK : ""}<span class="tb-hint">${hint}</span>${right}`;
      dock.querySelector("[data-back]")?.addEventListener("click", back);
    };
    // 底下一条输入框：自己写一句（「我自己写」和 text 步骤都用它）
    const ask = (ph) => new Promise((res) => {
      const t = token;
      dock.innerHTML = `${frames.length > 1 ? BACK : ""}<div class="tb-composer"><input maxlength="30" placeholder="${esc(ph || "写一句")}"><button class="tb-send" aria-label="发送">${icon("send")}</button></div>`;
      dock.querySelector("[data-back]")?.addEventListener("click", back);
      const inp = dock.querySelector("input");
      setTimeout(() => inp.focus(), 50);
      const send = () => { const v = inp.value.trim(); if (v && t === token) { dock.innerHTML = ""; res(v); } };
      dock.querySelector(".tb-send").onclick = send;
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) send(); });
    });

    // 回到第 k 题：后面的消息都撤掉，答案退回到进这一题之前，这一题重新能点
    function rewind(k) {
      token++;
      const f = frames[k];
      while (f.row.nextElementSibling) f.row.nextElementSibling.remove();
      restore(f.snap);
      frames = frames.slice(0, k + 1);
      dots();
      arm(F.steps[f.id], f.row);
    }
    function back() {
      // 停在结尾：回到最后一题；停在某一题：回到它的上一题
      const k = ending ? frames.length - 1 : frames.length - 2;
      ending = false;
      if (k >= 0) rewind(k);
    }
    let ending = false;

    async function go(id) {
      if (!id) {
        ending = true;
        dock.innerHTML = "";
        dots(true);
        return F.ending(st, { xg, me, dock, st, ask, bar });
      }
      const s = F.steps[id];
      frames.push({ id, row: null, snap: snap() });
      const f = frames[frames.length - 1];
      dock.innerHTML = "";
      dots();
      const sub = val(s.sub);
      const head = `<div class="bub">${val(s.q)}${sub ? `<small class="bub-sub">${sub}</small>` : ""}</div>${val(s.body) || ""}`;
      let html = head;
      if (s.type === "text") html += `<div class="tb-chips" data-ch>${val(s.chips).map((c) => `<button class="chip" data-c="${esc(c)}">${esc(c)}</button>`).join("")}</div>`;
      if (s.type === "cards" || s.type === "rows") html += choices(s);
      const row = await xg(html, { wide: true });
      if (!row) return;
      f.row = row;
      arm(s, row);
    }

    function choices(s) {
      const opts = val(s.opts);
      const custom = val(s.custom);
      const rows = s.type === "rows";
      const card = (o, k) => rows
        ? `<button class="rowc" data-v="${esc(o.v)}" style="--i:${k}">${icon(o.icon || "check")}<span><b>${esc(o.label)}</b>${o.hint ? `<small>${esc(o.hint)}</small>` : ""}</span>${o.prog != null ? `<em class="prog"><i style="width:${Math.round(o.prog * 100)}%"></i></em>` : ""}</button>`
        : `<button class="il" data-v="${esc(o.v)}" style="--i:${k}">${ill(o.ill)}<span><b>${esc(o.label)}</b>${o.hint ? `<small>${esc(o.hint)}</small>` : ""}</span></button>`;
      const mine = custom ? (rows
        ? `<button class="rowc mine" data-v="__mine" style="--i:${opts.length}">${icon("edit")}<span><b>我自己写</b></span></button>`
        : `<button class="il mine" data-v="__mine" style="--i:${opts.length}"><svg class="ill" viewBox="0 0 96 64">${PEN}</svg><span><b>我自己写</b><small>说说你的</small></span></button>`) : "";
      const n = opts.length + (custom ? 1 : 0);
      return rows ? `<div class="rowcs" data-ch>${opts.map(card).join("")}${mine}</div>`
        : `<div class="ils ${n === 3 ? "three" : ""}" data-ch>${opts.map(card).join("")}${mine}</div>`;
    }

    // 让一题能答：装上点卡片、跳过、写一句的处理。第一次出现和「回到这一题」都走这里
    function arm(s, row) {
      const id = frames[frames.length - 1].id;
      const key = s.key || id;
      const k = frames.length - 1;
      const box = row.querySelector("[data-ch]");
      box?.classList.remove("dim", "past");
      box?.querySelectorAll(".on").forEach((b) => b.classList.remove("on"));
      const next = () => go(val(s.next));
      const answered = async (o, text) => {
        box?.classList.add("past");
        me(text);
        // 最后一题不再回一句：结尾那句话就是回应，两句挨着会显得啰嗦
        const last = !val(s.next);
        const r = last ? "" : typeof s.react === "function" ? s.react(o ? o.v : "custom", st, text) : (o?.react || (o ? "" : (s.customReact ?? "嗯，我记下了。")));
        if (r && !(await xg(r))) return;
        next();
      };
      // 已经答过的题：点另一张就从这一题重新走（先退回这一题，再替 TA 点一下）
      // （同一个元素正在点的时候 click() 不会再触发，所以等这一下过去）
      const repick = (b) => { ending = false; rewind(k); setTimeout(() => b.click()); };

      if (s.type === "info") {
        bar("", `<button class="btn btn-good tb-go">${s.cta || "继续"}</button>`);
        dock.querySelector(".tb-go").onclick = () => { dock.innerHTML = ""; next(); };
        return;
      }
      if (s.type === "text") {
        const take = (v) => { if (box.classList.contains("dim")) return; box.classList.add("dim"); dock.innerHTML = ""; st.a[key] = v; st.l[key] = v; box.querySelector(`[data-c="${CSS.escape(v)}"]`)?.classList.add("on"); answered(null, v); };
        box.querySelectorAll(".chip").forEach((c) => { c.onclick = () => (box.classList.contains("past") ? repick(c) : take(c.dataset.c)); });
        ask(s.ph).then(take);
        return;
      }
      const opts = val(s.opts);
      const custom = val(s.custom);
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
        if (!o) { box.classList.add("past"); me("先跳过"); if (!(await xg(s.skipReact || "好，这个先放着。"))) return; return next(); }
        answered(o, o.say || o.label);
      };
      box.querySelectorAll("[data-v]").forEach((b) => { b.onclick = () => (box.classList.contains("past") ? repick(b) : pick(b.dataset.v)); });
      bar(s.skip !== false ? "点一张就好" : "", s.skip !== false ? `<button class="tb-skip">先跳过</button>` : "");
      dock.querySelector(".tb-skip")?.addEventListener("click", () => pick(null));
    }

    function restart() {
      token++;
      list.innerHTML = "";
      st.a = {}; st.l = {};
      Object.assign(st, F.state || {});
      frames = [];
      ending = false;
      go(val(F.first));
    }
    $(".tb-x").onclick = restart;
    restart();
  };

  // 结尾页的小零件：会存下的东西（勾选）
  window.keeps = (items) => `<div class="keeps">${items.map((it) => `<label class="keep"><input type="checkbox" ${it.on === false ? "" : "checked"}><span>${it.html}</span><small>${esc(it.to)}</small></label>`).join("")}</div>`;
})();
