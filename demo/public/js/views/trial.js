// 首页「先体验一下」：两分钟的引导式体验，不建账号。
// 选一件想改变的事 → 和小光聊几句 → 今天的一小步 → 看它记下了什么。
// 注册 / 登录时把结果放进 sessionStorage，建档或进门时带进新账号（takeCarry）。
import { api } from "../api.js";
import { esc, icon, tile, toast } from "../ui.js";
import { mountBall, agentMini } from "../ball.js";
import { confetti } from "../fx.js";
import { renderGate, authSheet } from "./gate.js";

export const GOALS = [
  { id: "sleep", ic: "moon", c: "var(--c-violet)", t: "想早点睡", sub: "总是熬到很晚",
    open: "想早点睡，嗯，这个我陪你。现在一般几点睡？晚上那会儿通常在干嘛？",
    hints: ["总是刷手机到一两点", "躺下脑子停不下来", "白天困，晚上又不困"] },
  { id: "speak", ic: "chat", c: "var(--c-sky)", t: "想更敢开口", sub: "话到嘴边又咽回去",
    open: "想更敢开口。最近有没有哪个时刻，你其实想说点什么，最后没说出来？",
    hints: ["开会时不敢发言", "怕说错被人笑", "跟不熟的人不知道聊什么"] },
  { id: "todo", ic: "flag", c: "var(--c-orange)", t: "想把拖着的事做完", sub: "越拖越不想碰",
    open: "是哪件事在拖着你？说说它现在卡在哪儿。",
    hints: ["论文一直没动笔", "不知道从哪开始", "一打开就想逃"] },
  { id: "self", ic: "heart", c: "var(--c-pink)", t: "想对自己好一点", sub: "最近有点累、有点乱",
    open: "嗯，听起来最近不太轻松。是哪方面让你觉得累？随便说说就行。",
    hints: ["事情太多，喘不过气", "总觉得自己做得不够好", "睡不好，心情也差"] },
  { id: "ideal", ic: "sparkles", c: "var(--c-lemon)", t: "想离理想的自己近一点", sub: "知道想要什么，不知道怎么走",
    open: "你心里那个「理想的自己」是什么样子？描述一下就好，不用很完整。",
    hints: ["想成为更自律的人", "想有自己的作品", "想活得松弛一点"] },
  { id: "move", ic: "wind", c: "var(--c-mint)", t: "想动起来", sub: "运动总是三分钟热度",
    open: "想动起来，好呀。之前试过吗？一般是卡在哪一步？",
    hints: ["坚持不了几天", "下班太累了", "不知道练什么"] },
];
const STAGES = ["想改变的事", "聊几句", "今天的一小步", "记下来"];
const CARRY_KEY = "xg-trial";

let ball = null;

export function takeCarry() {
  try {
    const c = JSON.parse(sessionStorage.getItem(CARRY_KEY) || "null");
    return c?.step ? c : null;
  } catch { return null; }
}
export const dropCarry = () => sessionStorage.removeItem(CARRY_KEY);

export function renderTrial(root) {
  root.innerHTML = `
    <div class="gate trial">
      <header class="gate-nav">
        <span class="gate-logo"><span class="gl-ball"></span><b>显伴</b></span>
        <span class="spacer"></span>
        <button class="btn btn-quiet" data-act="home">${icon("back")}回首页</button>
      </header>
      <div class="trial-wrap">
        <ol class="trial-stages">${STAGES.map((s, i) => `<li data-i="${i}"><i>${i + 1}</i><span>${s}</span></li>`).join("")}</ol>
        <div class="trial-hello"><div class="trial-ball"></div><div class="speech trial-say"></div></div>
        <div class="trial-body"></div>
      </div>
    </div>`;
  mountBall(root.querySelector(".gl-ball"), { size: 30, halo: false, interactive: false, agent: false });
  ball = mountBall(root.querySelector(".trial-ball"), { size: 88, emotion: "03" });
  root.querySelector("[data-act=home]").addEventListener("click", () => { root.innerHTML = ""; renderGate(root); });
  pickGoal(root);
}

function stage(root, i, line, mood) {
  root.querySelectorAll(".trial-stages li").forEach((li) => {
    li.classList.toggle("on", +li.dataset.i === i);
    li.classList.toggle("done", +li.dataset.i < i);
  });
  const say = root.querySelector(".trial-say");
  say.textContent = line;
  say.classList.remove("pop"); void say.offsetWidth; say.classList.add("pop");
  if (mood) { ball.set(mood); ball.pulse("bounce"); }
  root.querySelector(".gate").scrollTo({ top: 0, behavior: "smooth" });
}

// ---- 1. 想改变的事 ----
function pickGoal(root) {
  stage(root, 0, "嗨，我是小光。最近有没有一件事，你想让自己慢慢变好一点？", "10");
  const body = root.querySelector(".trial-body");
  body.innerHTML = `
    <div class="trial-goals">${GOALS.map((g, i) => `
      <button class="trial-goal" data-g="${g.id}" style="--i:${i}">${tile(g.ic, g.c, 42)}
        <span><b>${esc(g.t)}</b><small>${esc(g.sub)}</small></span></button>`).join("")}</div>
    <div class="trial-own">
      <input class="field" maxlength="30" placeholder="或者自己写一句">
      <button class="btn btn-main" disabled>就这个</button>
    </div>
    <p class="trial-note">不用注册。聊完觉得合适，再决定要不要留下。</p>`;
  const own = body.querySelector(".trial-own input");
  const ok = body.querySelector(".trial-own button");
  own.addEventListener("input", () => { ok.disabled = !own.value.trim(); });
  own.addEventListener("keydown", (e) => { if (e.key === "Enter" && own.value.trim()) ok.click(); });
  ok.addEventListener("click", () => talk(root, {
    id: "own", t: own.value.trim(), hints: [],
    open: `「${own.value.trim()}」，好，我听着。现在大概是什么情况？随便说说就行。`,
  }));
  body.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => talk(root, GOALS.find((g) => g.id === b.dataset.g))));
}

// ---- 2. 聊几句 / 3. 今天的一小步 ----
function talk(root, goal) {
  stage(root, 1, "不用想得很完整，像跟朋友吐槽那样说就行。", "35");
  const body = root.querySelector(".trial-body");
  body.innerHTML = `
    <div class="trial-chat">
      <div class="trial-thread"></div>
      <div class="trial-composer">
        <div class="hints">${goal.hints.map((t) => `<button class="chip" data-fill="${esc(t)}">${esc(t)}</button>`).join("")}</div>
        <div class="inbox"><textarea rows="1" maxlength="300" placeholder="说说看……"></textarea>
          <button class="send" aria-label="发送">${icon("send")}</button></div>
        <div class="trial-meta"><span class="trial-left"></span>
          <button class="btn btn-quiet btn-sm" data-act="finish" hidden>直接帮我拆成一小步</button></div>
      </div>
    </div>`;
  const thread = body.querySelector(".trial-thread");
  const comp = body.querySelector(".trial-composer");
  const ta = comp.querySelector("textarea");
  const send = comp.querySelector(".send");
  const left = comp.querySelector(".trial-left");
  const finishBtn = comp.querySelector("[data-act=finish]");
  const history = [{ role: "assistant", content: goal.open }];
  let busy = false;
  let smaller = 0;

  const scroll = () => requestAnimationFrame(() => {
    const g = root.querySelector(".gate");
    g.scrollTo({ top: g.scrollHeight, behavior: "smooth" });
  });
  const bubble = (role, text) => {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.innerHTML = role === "user" ? `<div class="bub">${esc(text)}</div>`
      : `${agentMini()}<div class="col"><div class="bub"><div class="txt">${text === null ? `<span class="dots"><i></i><i></i><i></i></span>` : esc(text)}</div></div></div>`;
    thread.append(el);
    scroll();
    return el;
  };
  const rounds = () => history.filter((m) => m.role === "user").length;
  const refresh = () => {
    const n = rounds();
    const can = !busy && ta.value.trim();
    send.classList.toggle("ready", !!can);
    left.textContent = n >= 3 ? "" : `还能聊 ${3 - n} 句`;
    finishBtn.hidden = n < 1 || busy;
    ta.disabled = busy;
  };

  async function ask(text, opts = {}) {
    if (busy) return;
    busy = true;
    if (text) { history.push({ role: "user", content: text }); bubble("user", text); }
    comp.querySelector(".hints").classList.add("hide");
    ta.value = ""; refresh();
    ball.set("30");
    const wait = bubble("assistant", null);
    try {
      const r = await api.trial({ goal: goal.t, history, ...opts });
      history.push({ role: "assistant", content: r.reply });
      wait.querySelector(".txt").textContent = r.reply;
      if (r.step) {
        comp.hidden = true;
        stepCard(r);
      } else {
        comp.hidden = false;
        ball.set("35");
      }
    } catch (e) {
      wait.remove();
      if (text) { history.pop(); ta.value = text; }
      toast(e.message, "err");
      ball.set("12");
    }
    busy = false;
    refresh();
    if (!comp.hidden) ta.focus();
  }

  function stepCard(r) {
    stage(root, 2, "这是我觉得今天最好开始的一步。太难的话，跟我说，换个更小的。", "19");
    const card = document.createElement("div");
    card.className = "trial-step";
    card.innerHTML = `
      ${tile("flag", "var(--c-orange)", 48)}
      <div class="ts-main">
        <div class="ts-k">今天的一小步</div>
        <div class="ts-t">${esc(r.step.title)}</div>
        <div class="ts-n">${icon("clock")}${esc(r.step.when)}${r.step.why ? ` · ${esc(r.step.why)}` : ""}</div>
        <div class="ts-acts">
          <button class="btn btn-main" data-act="ok">${icon("check")}就这个</button>
          ${smaller < 2 ? `<button class="btn btn-ghost" data-act="smaller">还是有点难，再小一点</button>` : ""}
        </div>
      </div>`;
    thread.append(card);
    scroll();
    card.querySelector("[data-act=ok]").addEventListener("click", (e) => {
      const b = e.currentTarget.getBoundingClientRect();
      confetti(b.left + b.width / 2, b.top, 60, 0.7);
      done(root, goal, r);
    });
    card.querySelector("[data-act=smaller]")?.addEventListener("click", () => {
      smaller += 1;
      card.classList.add("dim");
      card.querySelectorAll("button").forEach((x) => { x.disabled = true; });
      ask("还是有点难，能再小一点吗？", { smaller: true });
    });
  }

  ta.addEventListener("input", () => {
    ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 140) + "px"; refresh();
  });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send.click(); }
  });
  send.addEventListener("click", () => { const t = ta.value.trim(); if (t) ask(t); });
  comp.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.fill)));
  finishBtn.addEventListener("click", () => {
    history.push({ role: "user", content: "我大概就是这样，帮我拆成今天能做的一小步吧。" });
    bubble("user", "帮我拆成今天能做的一小步吧");
    ask("", { finish: true });
  });

  bubble("assistant", goal.open);
  refresh();
  setTimeout(() => ta.focus(), 300);
}

// ---- 4. 记下来 ----
function done(root, goal, r) {
  stage(root, 3, "好，就这么定了。你看，今天这些我都记下了。", "10");
  const remember = r.remember?.length ? r.remember : [`你想${goal.t.replace(/^想/, "")}`];
  const today = new Date();
  const day = `${today.getMonth() + 1}月${today.getDate()}日`;
  sessionStorage.setItem(CARRY_KEY, JSON.stringify({
    goal: goal.t, why_goal: r.why_goal || "", step: r.step.title, why: r.step.why || "", remember,
  }));
  const body = root.querySelector(".trial-body");
  body.innerHTML = `
    <div class="trial-cards">
      <div class="tcard card" style="--i:0">${tile("flag", "var(--c-orange)", 42)}
        <div><div class="tc-k">今天的一小步</div><div class="tc-t">${esc(r.step.title)}</div>
        <div class="tc-n">${esc(r.step.when)}</div></div></div>
      <div class="tcard card" style="--i:1">${tile("memory", "var(--c-violet)", 42)}
        <div><div class="tc-k">小光记住了</div>
        <div class="tc-chips">${remember.map((m) => `<span class="pill">${esc(m)}</span>`).join("")}</div>
        <div class="tc-n">下次来，不用再从头讲一遍。</div></div></div>
      <div class="tcard card" style="--i:2">${tile("sprout", "var(--c-mint)", 42)}
        <div><div class="tc-k">成长记录</div><div class="tc-t">${day} · 定下了第一小步</div>
        <div class="tc-n">做完回来说一声，这里会再多一条，你的小镇也会多一块砖。</div></div></div>
      <div class="tcard card" style="--i:3">${tile("letter", "var(--c-sky)", 42)}
        <div><div class="tc-k">明天，小光会来问你</div><div class="tc-t">「${esc(r.tomorrow || "")}」</div>
        <div class="tc-n">没做成也没关系，它会照你喜欢的方式陪你看看卡在哪。</div></div></div>
    </div>
    <div class="trial-cta card">
      <h3>想让小光明天真的来问你？</h3>
      <p>注册一个账号就行。刚才这一步、它记住的话，都会一起带过去。</p>
      <div class="gate-acts">
        <button class="btn btn-main btn-lg" data-act="reg">注册，留下这一步</button>
        <button class="btn btn-ghost btn-lg" data-act="login">已有账号，登录</button>
      </div>
      <button class="btn btn-quiet" data-act="again">换件事再试试</button>
    </div>`;
  body.querySelector("[data-act=reg]").addEventListener("click", () => authSheet("register"));
  body.querySelector("[data-act=login]").addEventListener("click", () => authSheet("login"));
  body.querySelector("[data-act=again]").addEventListener("click", () => { dropCarry(); pickGoal(root); });
}
