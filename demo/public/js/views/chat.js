// 对话：主工作台。一个延续的线程。小光的表情跟着对话状态变（右侧面板和顶部小条同步），
// 小光做的事统一画成三种样子（推荐 / 回执 / 待确认，见 acts.js），经验飞进顶栏。
import { api, streamChat } from "../api.js";
import { state, setData, refresh, go } from "../store.js";
import { esc, richText, fmtDay, fmtTime, toast, icon, tile, sheet, h } from "../ui.js";
import { mountBall, setAgentMood, agentMini, MOOD_TEXT, celebrate, clearAgentHold, settleAgent, feelOf } from "../ball.js";
import { flyGain, burstAt } from "../fx.js";
import { actsBlock, liveAct } from "../acts.js";
import { startScene } from "../scene.js";
import { openKick } from "../kick.js";
import { openLazy, isResting } from "../rest.js";
import { openGoodNote } from "./goodnews.js";


const HINTS = [
  ["帮我记住我喜欢吃寿司", "memory"], ["我三天没健身了", "moon"], ["你对我了解多少？", "eye"],
  ["今天被老师夸了", "star"], ["水桶效应是什么意思", "book"], ["我的小镇还能建什么？", "home"],
];

// 正在进行的一轮对话。回复是流式的、可能要十几秒；这期间用户切去别的页面，
// 对话页会被整个重画，所以这一轮的内容不能只放在页面元素上：放在这里，回来时接着画。
let live = null;   // { text, acc, memories, tools: [], acts: [], msgId, done, sceneToStart, am, scroll }
let chatPos = null;   // { stick, fromBottom, at }：对话页重画时用来回到 TA 正在看的位置

function liveEls() {
  const am = live?.am;
  if (!am || !am.isConnected) return null;
  return { am, col: am.querySelector(".col"), txt: am.querySelector(".txt"), when: am.querySelector(".when") };
}

// 在当前的对话页里画出「这一轮」：用户那句 + 小光正在写的回复（已经收到的部分和工具卡片）
function mountLive(list, scroll) {
  list.append(bubble({ role: "user", content: live.text }));
  const am = document.createElement("div");
  am.className = "msg assistant";
  am.innerHTML = `${agentMini()}<div class="col"><div class="bub"><div class="txt"><span class="dots"><i></i><i></i><i></i></span></div></div><div class="when"></div></div>`;
  list.append(am);
  live.am = am;
  live.scroll = scroll;
  const e = liveEls();
  if (live.memories) { const r = recall(live.memories); if (r) e.col.insertBefore(r, e.when); }
  for (const [v, i] of live.acts || []) { const el = liveAct(v, i, live); if (el) e.col.insertBefore(el, e.when); }
  if (live.acc) e.txt.innerHTML = richText(live.acc) + (live.done ? "" : '<span class="caret"></span>');
  scroll();
}

function recall(memories) {
  if (!memories?.length) return null;
  const el = document.createElement("details");
  el.className = "recall";
  el.innerHTML = `<summary>${icon("memory")}参考了 ${memories.length} 条记忆</summary>
    <ul>${memories.map((m) => `<li><span class="pill ${m.status === "guess" ? "acc" : "good"}">${m.status === "guess" ? "猜测" : "记得"}</span>${esc(m.text)}</li>`).join("")}</ul>`;
  return el;
}

function bubble(m) {
  const el = document.createElement("div");
  el.className = `msg ${m.role}`;
  if (m.role === "user") {
    el.innerHTML = `<div class="bub">${esc(m.content)}</div>`;
    return el;
  }
  const meta = m.meta || {};
  const tag = meta.task ? `<span class="pill acc">${icon("clock")}例行任务 · ${esc(meta.task_title || "")}</span>`
    : meta.scene ? `<span class="pill">${icon("wind")}练习</span>` : "";   // 主动发来的消息不加标签：就是朋友发来的一条
  el.innerHTML = `${agentMini()}<div class="col"><div class="bub">${tag}<div class="txt">${richText(m.content)}</div></div>
    <div class="when">${fmtTime(m.created_at)}</div></div>`;
  const block = (meta.acts || []).length ? actsBlock(meta.acts, { msgId: m.id }) : null;
  if (block) el.querySelector(".col").insertBefore(block, el.querySelector(".when"));
  return el;
}

export function renderChat(root) {
  const d = state.data;
  const p = d.profile || {};
  const msgs = d.messages || [];
  const mems = (d.memories || []).filter((m) => m.status === "active").length;

  root.innerHTML = `
    <div class="chat">
      <div class="buddy-bar"><div class="buddy">
        <div class="buddy-ball"></div>
        <div><div class="buddy-nm">${esc(p.agent_name || "小光")}</div>
          <div class="buddy-st"><i></i><span data-agent-status>${MOOD_TEXT["02"]}</span></div></div>
        <span style="flex:1"></span>
        <span class="pill good">${icon("memory")}记得你 ${mems} 件事</span>
      </div></div>
      <div class="thread"><div class="thread-in"><div class="msgs"></div></div></div>
      <div class="composer"><div class="composer-in">
        <div class="hints">${HINTS.map(([t, ic]) => `<button class="chip" data-fill="${esc(t)}">${icon(ic)}${esc(t)}</button>`).join("")}</div>
        <div class="inbox">
          <button class="ib" data-act="good" title="记一件好事">${icon("star")}</button>
          <textarea rows="1" placeholder="给${esc(p.agent_name || "小光")}发消息" aria-label="消息"></textarea>
          <button class="ib ${isResting() ? "on" : ""}" data-act="lazy" title="${isResting() ? "今天在偷懒" : "今天偷个懒"}">${icon("moon")}</button>
          <button class="send" aria-label="发送">${icon("send")}</button>
        </div>
      </div></div>
    </div>`;

  mountBall(root.querySelector(".buddy-ball"), { size: 48, halo: false });
  const list = root.querySelector(".msgs");
  const thread = root.querySelector(".thread");
  let lastDay = "";
  if (!msgs.length) {
    list.innerHTML = `<div class="opener"><h2>${esc(p.nickname || "你好")}，今天想从哪件小事开始？</h2>
      <p>${p.intent_primary ? `你正在靠近「${esc(p.intent_primary)}」。` : ""}直接说话就行，也可以让我替你记下来。</p></div>`;
  }
  for (const m of msgs) {
    const dk = fmtDay(m.created_at);
    if (dk !== lastDay) { list.insertAdjacentHTML("beforeend", `<div class="day"><span>${esc(dk)}</span></div>`); lastDay = dk; }
    list.append(bubble(m));
  }
  // 回复在一点点长出来时，只有 TA 本来就在最底下才跟着往下走；TA 往上翻了，就别把 TA 拽回来。
  // 一轮回完会刷新数据、整页重画：TA 正在往上翻着看的话，重画后回到原来的位置（chatPos 记着离底部多远）。
  // force：打开对话页、刚发出一句话时，直接到底。
  let stick = !(chatPos && !chatPos.stick && Date.now() - chatPos.at < 60000);
  thread.addEventListener("scroll", () => {
    if (!thread.isConnected || !thread.clientHeight) return;   // 旧页面被换下来时也会触发一次，那时量出来全是 0
    const fromBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
    stick = fromBottom < 80;
    chatPos = { stick, fromBottom, at: Date.now() };
  }, { passive: true });
  const scroll = (force) => {
    if (force !== true && !stick) return;
    thread.scrollTop = thread.scrollHeight;
    stick = true;
  };
  if (live) {
    if (lastDay !== "今天") { list.insertAdjacentHTML("beforeend", `<div class="day"><span>今天</span></div>`); lastDay = "今天"; }
    list.querySelector(".opener")?.remove();
    mountLive(list, scroll);
  }
  requestAnimationFrame(() => {
    if (stick) return scroll(true);
    thread.scrollTop = thread.scrollHeight - thread.clientHeight - chatPos.fromBottom;
  });
  // 主动消息已经画在对话里了：打开对话就算看过，不然它会一直挡住小光的下一条
  if ((d.inbox || []).length) api.inboxSeen().then(() => setData({ inbox: [] })).catch(() => {});

  const ta = root.querySelector("textarea");
  const send = root.querySelector(".send");
  const hints = root.querySelector(".hints");
  const grow = () => {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
    hints.classList.toggle("hide", !!ta.value.trim());
    send.classList.toggle("ready", !!ta.value.trim());
  };
  ta.value = state.composerDraft || "";
  grow();
  ta.addEventListener("input", () => { state.composerDraft = ta.value; grow(); });
  root.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => {
    ta.value = b.dataset.fill; state.composerDraft = ta.value; grow(); ta.focus();
  }));

  async function sendMsg() {
    const text = ta.value.trim();
    if (!text || live) return;          // 上一轮还没回完（哪怕是在别的页面发的）
    const sentAt = Date.now() - 5000;
    const topic = state.pendingTopic || "";       // 点子里点了一个话题：这一句带着它发
    state.pendingTopic = "";
    ta.value = ""; state.composerDraft = ""; grow();
    if (lastDay !== "今天") { list.insertAdjacentHTML("beforeend", `<div class="day"><span>今天</span></div>`); lastDay = "今天"; }
    list.querySelector(".opener")?.remove();
    live = { text, acc: "", memories: null, tools: [], acts: [], msgId: null, done: false, sceneToStart: null };
    clearAgentHold();   // 用户开口了：之前停留的表情让位
    mountLive(list, scroll);
    scroll(true);   // 刚发出一句话：回到最底下
    const turn = live;
    const sc = () => turn.scroll?.();
    let started = false;

    try {
      await streamChat(text, {
        mood: ({ id }) => setAgentMood(id),
        context: ({ memories }) => {
          turn.memories = memories;
          const e = liveEls(); const r = e && recall(memories);
          if (r) e.col.insertBefore(r, e.when);
        },
        delta: ({ text: t }) => {
          turn.acc += t;
          const e = liveEls();
          if (e) { if (!started) { started = true; e.txt.innerHTML = ""; } e.txt.innerHTML = richText(turn.acc) + '<span class="caret"></span>'; sc(); }
        },
        tool: ({ name, args, result, acts = [], act_start = 0 }) => {
          turn.tools.push({ name, args, result });
          const e = liveEls();
          acts.forEach((v, k) => {
            turn.acts.push([v, act_start + k]);
            const el = liveAct(v, act_start + k, turn, result?.xp || (name === "checkin" ? result : null));
            if (e && el) e.col.insertBefore(el, e.when);
          });
          if (name === "start_scene" && result?.ok) { turn.sceneToStart = result.scene; turn.kickTask = result.task || ""; }
          if ((name === "complete_step" || name === "log_good_news") && result?.ok !== false) celebrate();
          sc();
        },
        done: ({ message_id }) => { turn.msgId = message_id; },
        error: () => { setAgentMood("error"); toast("模型服务暂时连不上", "err"); },
      }, topic ? { topic } : {});
    } catch (e) {
      turn.acc = turn.acc || "我这边连不上了，稍后再试试。你刚才说的我先留着。";
      setAgentMood("error");
      toast(e.message || "发送失败", "err");
    } finally {
      turn.done = true;
      let e = liveEls();
      if (e) { e.txt.innerHTML = richText(turn.acc || "嗯。"); e.when.textContent = fmtTime(new Date().toISOString()); }
      try {
        const data = await refresh();
        // 只用这一轮刚写下的回复（防止拿到别的时间点的消息）
        const last = (data.messages || []).slice(-1)[0];
        e = liveEls();
        if (e && last?.role === "assistant" && Date.parse(last.created_at) >= sentAt && last.content && last.content.length > turn.acc.length) e.txt.innerHTML = richText(last.content);
        // 这一轮做过的事换成存下来的样子（带消息 id，撤销、留下才能记到这条消息上；3 处以上收成一行）
        const saved = last?.id === turn.msgId ? last.meta?.acts : null;
        if (e && saved?.length) {
          e.col.querySelectorAll(":scope > .cact, :scope > .acts").forEach((x) => x.remove());
          const block = actsBlock(saved, { msgId: turn.msgId });
          if (block) e.col.insertBefore(block, e.when);
        }
      } catch {}
      if (live === turn) live = null;    // 之后重画对话页就直接用服务器上的记录了
      if (turn.sceneToStart && state.route === "chat") setTimeout(() => turn.sceneToStart === "kickstart"
        ? openKick({ task: turn.kickTask }) : startScene(turn.sceneToStart), 900);
      setTimeout(() => settleAgent(feelOf(text, turn.tools)), 1600);   // 按这句话的意思停留一个表情，约 1 分钟后回到待机
      sc();
      if (liveEls() || document.contains(ta)) ta.focus();
    }
  }
  send.addEventListener("click", sendMsg);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMsg(); }
  });
  if (state.autoSend) {
    ta.value = state.autoSend;
    state.autoSend = "";
    grow();
    setTimeout(sendMsg, 400);
  }

  root.querySelector("[data-act=good]").addEventListener("click", (e) => quickGood(e.currentTarget));
  root.querySelector("[data-act=lazy]").addEventListener("click", () => openLazy({ onDone: () => { setAgentMood("tired", { hold: 60000 }); renderChat(root); } }));
  // 记一件好事：和好消息页同一个弹层。「心情不太好？」就把写了的字放进输入框，直接和小光聊
  function quickGood(btn) {
    openGoodNote({
      from: btn,
      onSaved: () => celebrate(),
      onTalk: (t) => { ta.value = t || ta.value; state.composerDraft = ta.value; grow(); ta.focus(); },
    });
  }
}
