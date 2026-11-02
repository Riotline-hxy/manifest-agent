// 对话：主工作台。一个延续的线程。小光的表情跟着对话状态变（右侧面板和顶部小条同步），
// 工具结果落成带图标方块的卡片，经验飞进顶栏。
import { api, streamChat } from "../api.js";
import { state, setData, refresh, go, xpNote } from "../store.js";
import { esc, richText, fmtDay, fmtTime, toast, icon, tile, sheet, h } from "../ui.js";
import { mountBall, setAgentMood, pulseAgent, agentMini, MOOD_TEXT } from "../ball.js";
import { flyXP, burstAt } from "../fx.js";
import { startScene } from "../scene.js";
import { openLazy, adjustSheet, isResting } from "../rest.js";
import { askNotify } from "../tasks.js";

const TOOL = {
  add_step: ["flag", "var(--c-orange)", "加进计划"], complete_step: ["checkc", "var(--c-orange)", "完成一小步"],
  log_good_news: ["star", "var(--c-lemon)", "收下小确幸"], log_lazy_day: ["moon", "var(--c-violet)", "今天偷个懒"], adjust_habit: ["leaf", "var(--c-mint)", "调整了习惯"],
  propose_plan: ["flag", "var(--c-orange)", "小光提议的计划"], schedule_task: ["clock", "var(--c-sky)", "安排好了"],
  cancel_task: ["clock", "var(--c-sky)", "关掉了提醒"], list_tasks: ["list", "var(--c-sky)", "看了看例行任务"],
  search_chats: ["chat", "var(--c-violet)", "翻了翻以前的聊天"],
  update_notebook: ["book", "var(--c-violet)", "改了笔记本"],
  edit_plan: ["flag", "var(--c-orange)", "改好了计划"], add_habit: ["clock", "var(--c-mint)", "加了一个习惯"],
  checkin_habit: ["checkc", "var(--c-mint)", "习惯打卡"],
  remember: ["memory", "var(--c-violet)", "记住了"], correct_memory: ["edit", "var(--c-violet)", "改掉旧记忆"],
  search_memory: ["memory", "var(--c-violet)", "翻了翻记忆"], get_growth: ["sprout", "var(--c-mint)", "查了成长"],
  knowledge_search: ["book", "var(--c-coral)", "心灵学堂"], set_care_style: ["compass", "var(--c-sky)", "互动偏好"],
  start_scene: ["wind", "var(--c-mint)", "开始练习"], checkin: ["chat", "var(--c-sky)", "今天来聊了"],
  propose_moment: ["sparkles", "var(--c-violet)", "要留在轨迹上吗"],
};

// 小光提议的计划：逐项勾选，用户点「加进计划」才写入
function planFoot(el, result) {
  const plan = result.plan || {};
  const groups = [["milestones", "里程碑", "flag"], ["habits", "习惯", "clock"], ["steps", "小步", "check"]];
  const box = el.querySelector(".tool-f");
  box.classList.add("plan-pick");
  box.innerHTML = `${result.why ? `<p class="pp-why">${esc(result.why)}</p>` : ""}
    ${groups.filter(([k]) => (plan[k] || []).length).map(([k, label, ic]) => `<div class="pp-g"><div class="pp-k">${icon(ic)}${label}</div>
      ${plan[k].map((it, i) => `<label class="pp-it"><input type="checkbox" checked data-k="${k}" data-i="${i}"><span>${esc(it.title)}</span>
        <small>${k === "habits" ? (it.freq === "weekly" ? `每周 ${it.per_week || 3} 次` : "每天") : k === "milestones" && it.due_in_days ? `约 ${it.due_in_days} 天后` : ""}</small></label>`).join("")}</div>`).join("")}
    <div class="pp-acts"><button class="btn btn-sm btn-main" data-apply>${icon("check")}加进「${esc(result.wish_title || "")}」</button>
      <button class="btn btn-sm btn-quiet" data-skip>先不加</button></div>`;
  box.querySelector("[data-skip]").addEventListener("click", () => {
    box.innerHTML = `<span class="muted">好，这次先不加。想改哪里，直接跟我说。</span>`;
    el.classList.add("dim");
  });
  box.querySelector("[data-apply]").addEventListener("click", async (e) => {
    const pick = { milestones: [], habits: [], steps: [] };
    box.querySelectorAll("input:checked").forEach((c) => pick[c.dataset.k].push(plan[c.dataset.k][+c.dataset.i]));
    if (!pick.milestones.length && !pick.habits.length && !pick.steps.length) return toast("至少勾一项");
    e.currentTarget.disabled = true;
    try {
      const out = await api.planApply({ wish_id: result.wish_id, ...pick });
      setData(out);
      const n = out.made || {};
      box.innerHTML = `<span class="muted">加好了：${[n.milestones && `${n.milestones} 个里程碑`, n.habits && `${n.habits} 个习惯`, n.steps && `${n.steps} 个小步`].filter(Boolean).join("、")}</span>
        <button class="btn btn-sm btn-ghost" data-go-plan>去蜕变计划看看</button>`;
      box.querySelector("[data-go-plan]").addEventListener("click", () => go("plan"));
      el.querySelector(".tool-k").textContent = "加进计划了";
      burstAt(el.querySelector(".tile"), 26);
    } catch (err) { e.currentTarget.disabled = false; toast(err.message, "err"); }
  });
}

// 小光只能「提议」记录：卡片上由用户决定留不留、留在哪个愿望下
function proposalFoot(el, result) {
  const p = result.proposal || {};
  const ws = result.wishes || [];
  const foot = el.querySelector(".tool-f");
  foot.innerHTML = `${ws.length > 1 ? `<select class="field field-sm" aria-label="留在哪个愿望下">${ws.map((w) =>
      `<option value="${esc(w.id)}" ${w.id === p.wish_id ? "selected" : ""}>${esc(w.title)}</option>`).join("")}</select>` : ""}
    <button class="btn btn-sm btn-main" data-keep>${icon("check")}留下</button>
    <button class="btn btn-sm btn-quiet" data-skip>不用了</button>`;
  foot.querySelector("[data-skip]").addEventListener("click", () => {
    foot.innerHTML = `<span class="muted">好，这次不留。</span>`;
    el.classList.add("dim");
  });
  foot.querySelector("[data-keep]").addEventListener("click", async (e) => {
    const wid = foot.querySelector("select")?.value || p.wish_id;
    e.currentTarget.disabled = true;
    try {
      const out = await api.moment("add", { wish_id: wid, text: p.text, feeling: p.feeling, source: "chat" });
      setData(out);
      const title = (ws.find((w) => w.id === wid) || {}).title || p.wish_title || "";
      foot.innerHTML = `<span class="muted">留在「${esc(title)}」的轨迹上了</span>
        <button class="btn btn-sm btn-ghost" data-go-plan>去看看</button>`;
      foot.querySelector("[data-go-plan]").addEventListener("click", () => go("plan"));
      el.querySelector(".tool-k").textContent = "留在轨迹上了";
      burstAt(el.querySelector(".tile"), 22);
      if (out.xp?.amount) flyXP(el.querySelector(".tile"), out.xp.amount);
    } catch (err) { e.currentTarget.disabled = false; toast(err.message, "err"); }
  });
}

const GOOD_PH = { good: "今天有什么让你嘴角上扬的小事？", meme: "此刻脑子里在上演什么？吐槽、碎碎念都可以" };

const HINTS = [
  ["帮我记住我喜欢吃寿司", "memory"], ["我三天没健身了", "moon"], ["你对我了解多少？", "eye"],
  ["今天被老师夸了", "star"], ["水桶效应是什么意思", "book"], ["我什么时候能进化？", "sprout"],
];

// 正在进行的一轮对话。回复是流式的、可能要十几秒；这期间用户切去别的页面，
// 对话页会被整个重画，所以这一轮的内容不能只放在页面元素上：放在这里，回来时接着画。
let live = null;   // { text, acc, memories, tools: [], done, sceneToStart, am, scroll }

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
  for (const t of live.tools) e.col.insertBefore(toolCard(t.name, t.args, t.result, true), e.when);
  if (live.acc) e.txt.innerHTML = richText(live.acc) + (live.done ? "" : '<span class="caret"></span>');
  scroll();
}

function toolCard(name, args, result, quiet = false) {
  const ok = result?.ok !== false;
  let title = "", note = "", foot = "";
  switch (name) {
    case "add_step": title = result.step?.title || args.title || ""; note = "写进蜕变计划了"; break;
    case "complete_step": title = ok ? result.step?.title : "没找到对应的一小步"; note = ok ? "打勾了，花园里多了一株" : "没有写入任何完成记录"; break;
    case "log_good_news": title = ok ? result.record?.text : "没有记下来"; note = ok ? `第 ${result.count} 颗星` : result.error; break;
    case "log_lazy_day": title = result?.already ? "今天已经在偷懒了" : (result?.record?.text || "").split("：")[1] || "给自己放个假"; note = "习惯和小步都先暂停，小芽陪你一起睡";
      foot = ok ? `<button class="btn btn-sm btn-ghost" data-lazy-pick="rest">明天继续</button><button class="btn btn-sm btn-ghost" data-lazy-pick="adjust">调整一下计划</button><button class="btn btn-sm btn-quiet" data-lazy-pick="chat">就想聊聊天</button>` : ""; break;
    case "propose_plan": title = ok ? `给「${result.wish_title}」的一套安排` : "没能提议"; note = ok ? "勾掉不想要的，再加进计划" : result.error;
      foot = ok ? " " : ""; break;
    case "adjust_habit": title = ok ? result.habit : "没找到这个习惯"; note = ok ? result.done : result.error; break;
    case "schedule_task": title = ok ? result.task.title : "没安排上"; note = ok ? `${result.task.when}${result.task.kind === "ai" ? " · 到点小光会给你发消息" : " · 到点叫你"}` : result.error;
      foot = ok && "Notification" in window && Notification.permission === "default" ? `<button class="btn btn-sm btn-ghost" data-notify>${icon("letter")}开启浏览器通知</button>` : ""; break;
    case "cancel_task": title = ok ? result.task : "没找到这个提醒"; note = ok ? "以后不会再响了" : result.error; break;
    case "list_tasks": title = `${(result.tasks || []).filter((x) => x.on).length} 个开着的例行任务`; note = (result.tasks || []).filter((x) => x.on).map((x) => `${x.title}（${x.when}）`).join("；"); break;
    case "search_chats": title = (result.hits || []).length ? `找到 ${(result.hits || []).length} 段` : "没翻到"; note = (result.hits || []).slice(0, 2).map((x) => `${x.date.slice(5, 10)} ${x.text}`).join(" / "); break;
    case "edit_plan": title = ok ? `「${result.title}」` : "这次没改成"; note = ok ? (result.changed || []).join("，") : result.error;
      foot = ok ? `<button class="btn btn-sm btn-ghost" data-go="plan">去蜕变计划看看</button>` : ""; break;
    case "update_notebook": title = ok ? ({ add: "加进笔记本了", replace: "改好了", remove: "删掉了" }[args.action || "add"]) : "这次没改成";
      note = ok ? (args.text || args.old || "") : result.error; foot = ok ? `<button class="btn btn-sm btn-ghost" data-go-notebook>看看笔记本</button>` : ""; break;
    case "add_habit": title = ok ? result.habit.title : "没有加上"; note = ok ? `${result.habit.freq_text} · 放进「${result.wish_title}」了` : result.error; break;
    case "checkin_habit": title = ok ? result.habit.title : "没找到这个习惯"; note = ok ? (result.already ? "今天已经打过卡了" : `本周 ${result.habit.week}/${result.habit.need}`) : "没有写入打卡"; break;
    case "remember": title = ok ? result.memory?.text : "没有写入"; note = ok ? "长期记住了，在「我的空间」可以改" : result.error; break;
    case "correct_memory":
      title = ok ? (result.deleted ? `删掉：${result.old}` : result.new) : "没找到要改的那条";
      note = ok ? (result.deleted ? "按你说的忘掉了" : `原来是：${result.old}`) : "什么都没改"; break;
    case "search_memory": {
      const l = result.memories || [];
      title = l.length ? `找到 ${l.length} 条` : "没找到相关记忆"; note = l.map((m) => m.text).join("；"); break;
    }
    case "get_growth": {
      const g = result.growth || {};
      title = `${g.pet_name || "小芽"} · ${g.stage || ""} · Lv${g.level || 1}`;
      note = g.next ? `累计 ${g.total} 经验，再 ${g.to_next} 到「${g.next.name}」` : `累计 ${g.total} 经验`;
      foot = `<button class="btn btn-sm btn-ghost" data-go="growth">去看进化图</button>`; break;
    }
    case "knowledge_search": {
      const l = result.articles || [];
      title = l.length ? l.map((a) => a.title).join(" · ") : "学堂里没有相关篇目";
      note = l.length ? "团队审核的内容，小光只读" : "不会凭空写一篇";
      foot = l.map((a) => `<button class="btn btn-sm btn-ghost" data-article="${esc(a.id)}">读「${esc(a.title)}」</button>`).join(""); break;
    }
    case "set_care_style": title = ok ? result.shown : "没有更新"; note = "以后按这个方式陪你"; break;
    case "start_scene": title = result.title || ""; note = "马上开始"; break;
    case "checkin": title = "今天的第一句话"; note = "陪伴任务完成"; break;
    case "propose_moment": title = ok ? result.proposal?.text : "没能提议"; note = ok ? (result.proposal?.feeling ? `当时的感受：${result.proposal.feeling}` : "还没保存，你决定") : result.error;
      foot = ok ? " " : ""; break;
    default: title = ok ? "完成" : "没有写成"; note = result?.error || "";
  }
  const amount = result?.xp?.amount || (name === "checkin" ? result?.amount : 0);
  const xp = result?.xp ? xpNote(result.xp) : name === "checkin" ? xpNote(result) : "";
  const [ic, col, label] = TOOL[name] || ["sparkles", "var(--accent)", "动作"];
  const el = document.createElement("div");
  el.className = `tool ${ok ? "" : "fail"}`;
  el.innerHTML = `${tile(ok ? ic : "close", ok ? col : "var(--danger)", 40)}
    <div class="tool-main"><div class="tool-k">${esc(label)}${ok ? "" : " · 没成功"}</div>
      <div class="tool-t">${esc(title || "")}</div>${note ? `<div class="tool-n">${esc(note)}</div>` : ""}
      ${foot ? `<div class="tool-f">${foot}</div>` : ""}</div>
    ${xp ? `<span class="tool-xp ${amount ? "" : "zero"}">${esc(xp)}</span>` : ""}`;
  el.querySelectorAll("[data-article]").forEach((b) => b.addEventListener("click", () => go("article", { id: b.dataset.article })));
  el.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  if (ok && name === "propose_moment") proposalFoot(el, result);
  if (ok && name === "propose_plan") planFoot(el, result);
  el.querySelector("[data-go-notebook]")?.addEventListener("click", () => { state.spaceTab = "digest"; go("space"); });
  el.querySelector("[data-notify]")?.addEventListener("click", (e) => { askNotify(); e.currentTarget.remove(); });
  el.querySelectorAll("[data-lazy-pick]").forEach((b) => b.addEventListener("click", () => {
    const pick = b.dataset.lazyPick;
    const f = el.querySelector(".tool-f");
    if (pick === "adjust") { adjustSheet(); return; }
    f.innerHTML = `<span class="muted">${pick === "rest" ? "好，明天我们再继续。" : "好，想说什么都行，我听着。"}</span>`;
    if (pick === "chat") document.querySelector(".composer textarea")?.focus();
  }));
  if (amount && !quiet) setTimeout(() => flyXP(el.querySelector(".tool-xp"), amount), 250);
  if (ok && !quiet && ["log_good_news", "complete_step", "checkin_habit"].includes(name)) setTimeout(() => burstAt(el.querySelector(".tile"), 26), 150);
  return el;
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
    : meta.proactive ? `<span class="pill acc">${icon("letter")}小光主动找你</span>` : meta.scene ? `<span class="pill">${icon("wind")}练习</span>` : "";
  el.innerHTML = `${agentMini()}<div class="col"><div class="bub">${tag}<div class="txt">${richText(m.content)}</div></div>
    <div class="when">${fmtTime(m.created_at)}</div></div>`;
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
          <button class="ib" data-act="good" title="记一条好消息">${icon("star")}</button>
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
  const scroll = () => { thread.scrollTop = thread.scrollHeight; };
  if (live) {
    if (lastDay !== "今天") { list.insertAdjacentHTML("beforeend", `<div class="day"><span>今天</span></div>`); lastDay = "今天"; }
    list.querySelector(".opener")?.remove();
    mountLive(list, scroll);
  }
  requestAnimationFrame(scroll);
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
    ta.value = ""; state.composerDraft = ""; grow();
    if (lastDay !== "今天") { list.insertAdjacentHTML("beforeend", `<div class="day"><span>今天</span></div>`); lastDay = "今天"; }
    list.querySelector(".opener")?.remove();
    live = { text, acc: "", memories: null, tools: [], done: false, sceneToStart: null };
    mountLive(list, scroll);
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
        tool: ({ name, args, result }) => {
          turn.tools.push({ name, args, result });
          const e = liveEls();
          if (e) e.col.insertBefore(toolCard(name, args, result), e.when);
          if (name === "start_scene" && result?.ok) turn.sceneToStart = result.scene;
          if (name === "complete_step" || name === "log_good_news") pulseAgent("bounce");
          sc();
        },
        error: () => { setAgentMood("error"); toast("模型服务暂时连不上", "err"); },
      });
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
      } catch {}
      if (live === turn) live = null;    // 之后重画对话页就直接用服务器上的记录了
      if (turn.sceneToStart && state.route === "chat") setTimeout(() => startScene(turn.sceneToStart), 900);
      setTimeout(() => setAgentMood("idle"), 2600);
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
  root.querySelector("[data-act=lazy]").addEventListener("click", () => openLazy({ onDone: () => { setAgentMood("tired"); renderChat(root); } }));
  function quickGood(btn) {
    let kind = "good";
    const body = h("div", { class: "qg", html: `<div class="tabs qg-tabs"><button class="on" data-k="good">${icon("star")}小确幸</button><button data-k="meme">${icon("chat")}内心戏</button><span class="ind"></span></div>
      <textarea class="field" rows="3" maxlength="200" placeholder="${GOOD_PH.good}"></textarea>` });
    const input = body.querySelector("textarea");
    const tabs = body.querySelector(".tabs");
    const place = () => { const on = tabs.querySelector("button.on"); Object.assign(tabs.querySelector(".ind").style, { left: on.offsetLeft + "px", width: on.offsetWidth + "px" }); };
    tabs.querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => {
      kind = b.dataset.k; input.placeholder = GOOD_PH[kind];
      tabs.querySelectorAll("[data-k]").forEach((x) => x.classList.toggle("on", x === b)); place(); input.focus();
    }));
    const s = sheet({
      title: "记一笔好消息", sticker: "star", body,
      footer: [h("button", { class: "btn btn-main", onclick: async () => {
        const t = input.value.trim();
        if (!t) return input.focus();
        try {
          const out = await api.record(kind, t);
          s.close();
          setData(out);
          setAgentMood("happy"); pulseAgent("bounce");
          if (out.xp?.amount) flyXP(btn, out.xp.amount);
          burstAt(btn, 30);
          toast(kind === "meme" ? "收下这段内心戏了" : "收下了，星空里又亮了一颗");
        } catch (e) { toast(e.message, "err"); }
      } }, "记下来")],
    });
    requestAnimationFrame(place);
    setTimeout(() => input.focus(), 60);
  }
}
