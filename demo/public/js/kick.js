// 两分钟启动：写一件想做却开始不了的事 → 选模式 → 小光拆成几个一两分钟的小动作 → 一次做一个 → 你已经开始了。
// 页面沿用「一课」的骨架（进度条、小光 + 气泡、底栏）；调整路线 / 遇到困难用底部弹层，不跳到聊天。
// 这一次的上下文在服务端（core/kickstart.py），结束时勾了「让小光记住这次体验」才写进《两分钟启动记忆》。
import { api } from "./api.js";
import { state, setData } from "./store.js";
import { esc, icon, sheet, h, toast } from "./ui.js";
import { mountBall } from "./ball.js";
import { confetti } from "./fx.js";

const MODES = [["low", "低能量", "动作更小、更温和，先动起来就好"], ["precise", "拆更准", "先回答三个小问题，拆得更贴合你"]];
const QUICK = {
  adjust: ["再小一点", "换个做法", "这步我已经做过了", "顺序换一下"],
  stuck: ["不想动", "做不到这一步", "被打断了", "不知道怎么做"],
};
const NEXT = ["好，下一个。", "嗯，接着来。", "就这样，慢慢来。"];
const TALK = {
  adjust: { title: "调整路线", sticker: "steps", ph: "哪里不合适？比如：没有温水" },
  stuck: { title: "遇到困难", sticker: "heart", ph: "卡在哪了？说一句就好" },
};
// 这一步用了多久：几秒就点过去的不写，免得像在计时
const dur = (sec) => (!sec || sec < 10 ? "" : sec < 60 ? `${sec} 秒` : `${Math.round(sec / 60)} 分钟`);
const CHEERS = ["开头最难的那一下，已经过去了。", "你没有等到想做才开始。", "动起来了，后面会轻一点。"];

export async function openKick({ task = "", stepId = "" } = {}) {
  const el = document.createElement("div");
  el.className = "lesson kick";
  el.innerHTML = `
    <div class="lesson-top">
      <button class="lesson-x" aria-label="关闭">×</button>
      <div class="bar lesson-bar"><i></i></div>
      <span class="lesson-count num"></span>
    </div>
    <div class="lesson-stage">
      <div class="lesson-kicker">两分钟启动</div>
      <div class="lesson-ask"><div class="lesson-ball"></div><div class="speech lesson-q"></div></div>
      <div class="kick-body"></div>
    </div>
    <div class="lesson-foot"><div class="kick-foot"></div></div>`;
  document.body.append(el);
  requestAnimationFrame(() => el.classList.add("in"));
  const ball = mountBall(el.querySelector(".lesson-ball"), { size: 116, emotion: "03", agent: false });
  const $ = (s) => el.querySelector(s);
  const body = $(".kick-body"), foot = $(".kick-foot");
  let run = null;
  let busy = false;

  const say = (text) => {
    const q = $(".lesson-q");
    q.textContent = text;
    q.classList.remove("pop"); void q.offsetWidth; q.classList.add("pop");
  };
  const progress = (done, total, label = "") => {
    $(".lesson-bar > i").style.width = `${total ? Math.max(4, (done / total) * 100) : 4}%`;
    $(".lesson-count").textContent = label;
  };
  const buttons = (list) => {
    foot.replaceChildren(...list.map(([label, cls, fn, wide]) => h("button", { class: `btn ${cls}${wide ? " wide" : ""}`, onclick: fn }, label)));
    return [...foot.children];
  };
  const close = () => {
    document.removeEventListener("keydown", onKey);
    el.classList.remove("in");
    el.classList.add("out");
    setTimeout(() => { el.remove(); ball.destroy(); }, 320);
  };
  // 中途关掉：这一次什么都不留（和结束时不勾「记住」一样）
  const quit = async () => {
    if (run && run.status === "active") api.kick("close", { run_id: run.id }).catch(() => {});
    close();
  };
  $(".lesson-x").addEventListener("click", quit);
  const onKey = (e) => { if (e.key === "Escape" && !document.querySelector(".sheet")) quit(); };
  document.addEventListener("keydown", onKey);

  // 等模型：小光在想，按钮先灰着
  async function think(text, job) {
    if (busy) return null;
    busy = true;
    say(text);
    ball.set("thinking");
    el.classList.add("waiting");
    foot.querySelectorAll("button").forEach((b) => b.classList.add("off"));
    try {
      return await job();
    } catch (e) {
      ball.set("error");
      toast(e.message || "没成功，再试一次", "err");
      foot.querySelectorAll("button").forEach((b) => b.classList.remove("off"));
      return null;
    } finally {
      busy = false;
      el.classList.remove("waiting");
    }
  }

  // ---- 1. 写下想做的事、选模式 ----
  async function home() {
    progress(0, 1, "");
    say("想做哪件事？说一件就好。");
    ball.set("listening");
    let data = { active: null };
    try { data = await api.kickHome(); } catch {}
    // 快速启动蜕变计划里待做的小步：当前愿望的排前面，点一下就填好，小光也知道它挂在哪个愿望下
    const cur = state.data.journey?.current;
    const steps = (state.data.steps || []).filter((s) => s.status === "todo")
      .sort((a, b) => (b.wish_id === cur) - (a.wish_id === cur)).slice(0, 4);
    let mode = "default";
    let fromStep = stepId;
    body.innerHTML = `
      <textarea class="field kick-task" rows="2" maxlength="40" placeholder="比如：起床、开始写报告、去洗个澡"></textarea>
      <div class="kick-modes">${MODES.map(([k, l]) => `<button class="kick-mode" data-mode="${k}" aria-pressed="false">${esc(l)}</button>`).join("")}</div>
      <p class="kick-hint"></p>
      ${data.active ? `<button class="kick-resume">${icon("footsteps")}<span>接着做「${esc(data.active.task)}」<small>第 ${Math.min(data.active.cur + 1, data.active.total)}/${data.active.total} 步</small></span>${icon("arrow")}</button>` : ""}
      ${steps.length && !stepId ? `<div class="kick-picks"><span>从小步开始</span>${steps.map((s) =>
        `<button class="kick-pick" data-step="${esc(s.id)}">${icon("flag")}<span>${esc(s.title)}</span></button>`).join("")}</div>` : ""}`;
    const ta = body.querySelector(".kick-task");
    ta.value = task;
    const [go] = buttons([["开始", "btn-good btn-lg", () => begin(), true]]);
    const ready = () => go.classList.toggle("off", !ta.value.trim());
    ready();
    ta.addEventListener("input", () => { fromStep = ""; body.querySelectorAll("[data-step]").forEach((x) => x.classList.remove("on")); ready(); });
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); begin(); } });
    setTimeout(() => ta.focus(), 250);
    body.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
      mode = mode === b.dataset.mode ? "default" : b.dataset.mode;
      body.querySelectorAll("[data-mode]").forEach((x) => { x.classList.toggle("on", x.dataset.mode === mode); x.setAttribute("aria-pressed", x.dataset.mode === mode); });
      body.querySelector(".kick-hint").textContent = MODES.find(([k]) => k === mode)?.[2] || "";
      ball.set("curious");
    }));
    body.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => {
      const s = steps.find((x) => x.id === b.dataset.step);
      ta.value = s.title;
      ready();
      fromStep = s.id;
      body.querySelectorAll("[data-step]").forEach((x) => x.classList.toggle("on", x === b));
    }));
    body.querySelector(".kick-resume")?.addEventListener("click", () => { run = data.active; showStep(); });

    async function begin() {
      const t = ta.value.trim();
      if (!t || busy) return;
      const out = await think(mode === "precise" ? "我先问三个小问题……" : "我想想怎么拆……", () => api.kick("start", { task: t, mode, step_id: fromStep }));
      if (!out) return;
      run = out.run;
      if (run.questions.length) questions(); else showStep();
    }
  }

  // ---- 2. 拆更准：三个问题，每个有贴着这件事的快捷选项，也能自己写 ----
  function questions() {
    progress(0, 1, "");
    say("先回答三个小问题，我拆得更准一点。");
    ball.set("listening");
    const ans = {};
    body.innerHTML = run.questions.map((q) => `
      <div class="kick-q" data-k="${q.key}"><b>${esc(q.q)}</b>
        <div class="kick-opts">${q.options.map((o) => `<button class="chip" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>
        <input class="field" maxlength="40" placeholder="其他"></div>`).join("");
    const [go] = buttons([["继续", "btn-good btn-lg", submit, true]]);
    const ready = () => go.classList.toggle("off", !Object.values(ans).some(Boolean));
    ready();
    body.querySelectorAll(".kick-q").forEach((box) => {
      const k = box.dataset.k, inp = box.querySelector("input");
      box.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
        const on = !c.classList.contains("on");
        box.querySelectorAll(".chip").forEach((x) => x.classList.remove("on"));
        c.classList.toggle("on", on);
        inp.value = "";
        ans[k] = on ? c.dataset.v : "";
        ready();
      }));
      inp.addEventListener("input", () => {
        box.querySelectorAll(".chip").forEach((x) => x.classList.remove("on"));
        ans[k] = inp.value.trim();
        ready();
      });
    });
    async function submit() {
      const out = await think("好，我按你说的来拆……", () => api.kick("answer", { run_id: run.id, answers: ans }));
      if (!out) return;
      run = out.run;
      showStep();
    }
  }

  // ---- 3. 一次一个动作 ----
  function showStep(fresh = "") {
    if (run.finished) return finished();
    const s = run.route[run.cur];
    const nxt = run.route.slice(run.cur + 1).find((x) => x.state === "todo");
    progress(run.done, run.total, `${run.cur + 1}/${run.total}`);
    say(fresh || run.say || (run.cur === 0 ? "先做这一个就好。" : NEXT[run.cur % NEXT.length]));
    ball.set(fresh || run.say ? "happy" : "listening");
    body.innerHTML = `
      <div class="kick-card"><b>${esc(s.title)}</b>${s.tip ? `<p>${esc(s.tip)}</p>` : ""}<span class="pill">${icon("clock")}约 ${s.minutes} 分钟</span></div>
      ${nxt ? `<p class="kick-next">接下来：${esc(nxt.title)}</p>` : ""}
      ${run.ctx?.step ? `<p class="kick-from">${icon("flag")}来自小步「${esc(run.ctx.step)}」</p>` : ""}`;
    buttons([
      ["完成这一步", "btn-good btn-lg", () => done(), true],
      ["调整路线", "btn-ghost", () => talk("adjust")],
      ["遇到困难", "btn-ghost", () => talk("stuck")],
    ]);
  }

  async function done(how = "done") {
    if (busy) return;
    busy = true;
    ball.set("happy");
    ball.pulse("bounce");
    try {
      const out = await api.kick(how, { run_id: run.id });
      run = out.run;
      if (out.state) setData(out.state);
      busy = false;
      if (run.finished) finished(out.xp); else showStep();
    } catch (e) {
      busy = false;
      toast(e.message || "没成功，再试一次", "err");
    }
  }

  // ---- 调整路线 / 遇到困难：弹层里说一句或点一个，小光只改现在这一步和后面的 ----
  function talk(kind) {
    const s = run.route[run.cur];
    const said = run.log.filter((x) => x.text);
    const wrap = h("div", { class: "kick-sheet" });
    wrap.innerHTML = `
      <div class="k-now"><small>现在这一步</small><b>${esc(s.title)}</b>${s.tip ? `<span>${esc(s.tip)}</span>` : ""}</div>
      ${said.length ? `<div class="k-log">${said.map((x) => `<p class="me">${esc(x.text)}</p><p class="xg">${esc(x.say)}</p>`).join("")}</div>` : ""}
      <div class="k-quick">${QUICK[kind].map((q) => `<button data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
      <div class="k-send"><textarea class="field" rows="1" maxlength="120" placeholder="${TALK[kind].ph}"></textarea>
        <button class="btn btn-main k-go" aria-label="发送">${icon("send")}</button></div>
      ${kind === "stuck" ? `<div class="k-alt"><button class="btn btn-quiet" data-skip>${icon("arrow")}先跳过这一步</button>
        <button class="btn btn-quiet" data-stop>${icon("moon")}今天先到这儿</button></div>` : ""}
      <p class="k-wait" hidden>小光在想……</p>`;
    const sh = sheet({ title: TALK[kind].title, sticker: TALK[kind].sticker, body: wrap });
    sh.panel.classList.add("kick-panel");
    sh.panel.previousElementSibling?.classList.add("kick-scrim");    // 弹层要盖在全屏的这一页上面
    const ta = wrap.querySelector("textarea");
    setTimeout(() => ta.focus(), 80);
    const send = async (text) => {
      text = (text || "").trim();
      if (!text || busy) return;
      busy = true;
      wrap.classList.add("waiting");
      wrap.querySelector(".k-wait").hidden = false;
      try {
        const out = await api.kick(kind, { run_id: run.id, text });
        run = out.run;
        sh.close();
        showStep(out.say);
      } catch (e) {
        wrap.querySelector(".k-wait").hidden = true;
        toast(e.message || "没调成，再试一次", "err");
      } finally {
        busy = false;
        wrap.classList.remove("waiting");
      }
    };
    wrap.querySelector(".k-go").addEventListener("click", () => send(ta.value));
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(ta.value); } });
    wrap.querySelectorAll("[data-q]").forEach((b) => b.addEventListener("click", () => send(b.dataset.q)));
    wrap.querySelector("[data-skip]")?.addEventListener("click", () => { sh.close(); done("skip"); });
    wrap.querySelector("[data-stop]")?.addEventListener("click", () => { sh.close(); finished(); });
  }

  // ---- 4. 你已经开始了：路线回顾（做了哪几步、各用了多久、在哪儿改过路线）+ 让小光记住 ----
  function finished(xp) {
    progress(1, 1, "");
    const n = run.route.filter((x) => x.state === "done").length;
    const left = run.route.filter((x) => x.state === "todo").length;
    say(run.cheer || CHEERS[n % CHEERS.length]);
    ball.set("done");
    ball.pulse("burst");
    if (n) confetti(innerWidth / 2, innerHeight * 0.35, 80);
    const total = run.secs >= 60 ? `用时 ${Math.round(run.secs / 60)} 分钟` : run.secs > 0 ? "用时不到 1 分钟" : "";
    const found = [...new Set(run.log.map((x) => x.found).filter(Boolean))].slice(-2);
    body.innerHTML = `
      <div class="kick-done">
        <h2>你已经开始了。</h2>
        <p>做了 <b class="num">${n}</b> 步${left ? ` · 还有 ${left} 步没做` : total ? ` · ${total}` : ""}</p>
      </div>
      <div class="kick-review">
        <div class="kr-head"><b>${esc(run.task)}</b>${run.mode !== "default" ? `<span class="pill">${esc(run.mode_label)}</span>` : ""}</div>
        ${run.ctx?.step ? `<p class="kr-from">${icon("flag")}来自小步「${esc(run.ctx.step)}」</p>` : ""}
        <div class="kr-list">${review()}</div>
      </div>
      <label class="kick-remember"><input type="checkbox"><span>让小光记住这次体验
        ${found.map((f) => `<small>${icon("sparkles")}小光发现：${esc(f)}</small>`).join("")}</span></label>
      ${xp?.amount ? `<div class="rv-xp">${icon("bolt")}经验 +${xp.amount}${xp.coins ? ` · 金币 +${xp.coins}` : ""}</div>` : ""}`;
    buttons([
      ["继续做这件事", "btn-ghost btn-lg", run.finished ? more : () => showStep()],   // 中途停下的：接着做剩下的
      ["结束", "btn-good btn-lg", end],
    ]);
  }

  // 一步一行，点开看当时的提示；因为 TA 说了一句而换上来的那一步，下面挂着 TA 说的那句；继续做的那几步前面有条分隔
  function review() {
    return run.route.map((x, i) => {
      const at = run.log.filter((l) => l.step === i);
      const more = at.some((l) => l.kind === "more") ? `<div class="kr-more"><span>接着又做了</span></div>` : "";
      const notes = at.filter((l) => TALK[l.kind]).map((l) =>
        `<div class="kr-note">${icon(TALK[l.kind].sticker)}<span><b>${TALK[l.kind].title}</b>${esc(l.text)}</span></div>`).join("");
      const tag = x.state === "skipped" ? "跳过了" : x.state === "todo" ? "没做" : dur(x.sec);
      const mark = x.state === "done" ? icon("check") : x.state === "skipped" ? icon("arrow") : "";
      return `${more}<details class="kr-step ${x.state}">
        <summary><i class="kr-mark">${mark}</i><span>${esc(x.title)}</span><em>${tag}</em>${x.tip ? icon("chevron") : ""}</summary>
        ${x.tip ? `<p>${esc(x.tip)}</p>` : ""}</details>${notes}`;
    }).join("");
  }

  async function more() {
    const out = await think("好，接着来……", () => api.kick("more", { run_id: run.id }));
    if (!out) return;
    run = out.run;
    showStep();
  }

  async function end() {
    if (busy) return;
    busy = true;
    const remember = !!body.querySelector(".kick-remember input")?.checked;
    try {
      const out = await api.kick("finish", { run_id: run.id, remember });
      if (out.state) setData(out.state);
      run = null;
      close();
      if (out.saved) toast("记下了，小光会记得这次", "", "memory");
    } catch (e) {
      busy = false;
      toast(e.message || "没结束成，再试一次", "err");
    }
  }

  home();
}
