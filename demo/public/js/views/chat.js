// 对话：主工作台。一个延续的线程；小光（Emotion Ball）在顶上，
// 表情跟着对话状态变；工具结果落成带贴纸的卡片，经验飞进顶栏。
import { api, streamChat } from "../api.js";
import { state, setData, refresh, go, xpNote } from "../store.js";
import { esc, richText, fmtDay, fmtTime, toast, icon } from "../ui.js";
import { mountBall, MOOD_TEXT } from "../ball.js";
import { art, flyXP, burstAt } from "../fx.js";
import { startScene } from "../scene.js";

const TOOL_ART = {
  add_step: "st-flag", complete_step: "st-flag", log_good_news: "st-jar", log_lazy_day: "st-moon",
  remember: "st-mirror", correct_memory: "st-mirror", search_memory: "st-mirror", get_growth: "@pet",
  knowledge_search: "st-book", set_care_style: "st-compass", start_scene: "st-lotus", checkin: "st-letter",
};
const TOOL_LABEL = {
  add_step: "加进计划", complete_step: "完成一小步", log_good_news: "收下好消息", log_lazy_day: "偷懒日",
  remember: "记住了", correct_memory: "改掉旧记忆", search_memory: "翻了翻记忆", get_growth: "查了成长",
  knowledge_search: "心灵学堂", set_care_style: "互动偏好", start_scene: "开始练习", checkin: "今天来聊了",
};

const HINTS = [
  ["帮我记住我喜欢吃寿司", "st-mirror"],
  ["我三天没健身了", "st-moon"],
  ["你对我了解多少？", "st-compass"],
  ["今天被老师夸了", "st-jar"],
  ["水桶效应是什么意思", "st-book"],
  ["我什么时候能进化？", "@pet"],
];

const artOf = (k) => art(k === "@pet" ? (state.data?.growth?.stage?.art || "pet-egg") : k);

function toolCard(name, args, result) {
  const ok = result?.ok !== false;
  let title = "", note = "", foot = "";
  switch (name) {
    case "add_step": title = result.step?.title || args.title || ""; note = "写进蜕变计划了"; break;
    case "complete_step":
      title = ok ? result.step?.title : "没找到对应的一小步";
      note = ok ? "打勾了，花园里多了一棵植物" : "没有写入任何完成记录"; break;
    case "log_good_news": title = ok ? result.record?.text : "没有记下来"; note = ok ? `星罐里第 ${result.count} 颗星` : result.error; break;
    case "log_lazy_day": title = "今天记成偷懒日"; note = "什么都不会清零"; break;
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
      foot = `<button class="btn btn-sm btn-ghost" data-go="growth">去成长页看看</button>`; break;
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
    default: title = ok ? "完成" : "没有写成"; note = result?.error || "";
  }
  const xp = result?.xp ? xpNote(result.xp) : name === "checkin" ? xpNote(result) : "";
  const el = document.createElement("div");
  el.className = `tool ${ok ? "" : "fail"}`;
  el.innerHTML = `
    <img class="tool-art" src="${artOf(TOOL_ART[name] || "st-seed")}" alt="">
    <div class="tool-main">
      <div class="tool-k">${esc(TOOL_LABEL[name] || "动作")}${ok ? "" : " · 没成功"}</div>
      <div class="tool-t">${esc(title || "")}</div>
      ${note ? `<div class="tool-n">${esc(note)}</div>` : ""}
      ${foot ? `<div class="tool-f">${foot}</div>` : ""}
    </div>
    ${xp ? `<span class="tool-xp ${result?.xp?.amount || result?.amount ? "" : "zero"}">${esc(xp)}</span>` : ""}`;
  el.querySelectorAll("[data-article]").forEach((b) => b.addEventListener("click", () => go("article", { id: b.dataset.article })));
  el.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  const amount = result?.xp?.amount || (name === "checkin" ? result?.amount : 0);
  if (amount) setTimeout(() => flyXP(el.querySelector(".tool-xp"), amount), 250);
  if (ok && ["log_good_news", "complete_step"].includes(name)) setTimeout(() => burstAt(el.querySelector(".tool-art"), 30), 150);
  return el;
}

function recall(memories) {
  if (!memories?.length) return null;
  const el = document.createElement("details");
  el.className = "recall";
  el.innerHTML = `<summary><img src="${art("st-mirror")}" alt="">参考了 ${memories.length} 条记忆</summary>
    <ul>${memories.map((m) => `<li><span class="pill ${m.status === "guess" ? "lamp" : "leaf"}">${m.status === "guess" ? "猜测" : "记得"}</span>${esc(m.text)}</li>`).join("")}</ul>`;
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
  const tag = meta.proactive ? `<span class="pill lamp">小光主动找你</span>` : meta.scene ? `<span class="pill sky">练习</span>` : "";
  el.innerHTML = `<span class="mini-orb"></span>
    <div class="col"><div class="bub">${tag}<div class="txt">${richText(m.content)}</div></div>
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
        <div class="buddy-txt">
          <div class="buddy-nm">${esc(p.agent_name || "小光")}<span class="buddy-st"><i></i><span>${MOOD_TEXT["02"]}</span></span></div>
          <div class="buddy-pills"><span class="pill leaf">记得你 ${mems} 件事</span><span class="pill">陪伴第 ${d.counts?.days || 1} 天</span>
          ${p.care_style ? `<span class="pill sky">中断时：${esc(d.prefs?.care_label || "")}</span>` : ""}</div>
        </div>
      </div></div>
      <div class="thread"><div class="thread-in">
        <div class="msgs"></div>
      </div></div>
      <div class="composer"><div class="composer-in">
        <div class="hints">${HINTS.map(([t, a]) => `<button class="chip" data-fill="${esc(t)}"><img src="${artOf(a)}" alt="">${esc(t)}</button>`).join("")}</div>
        <div class="inbox">
          <button class="ib" data-act="good" title="记一条好消息"><img src="${art("st-jar")}" alt=""></button>
          <textarea rows="1" placeholder="和${esc(p.agent_name || "小光")}说点什么…" aria-label="消息"></textarea>
          <button class="ib" data-act="rest" title="今天是偷懒日"><img src="${art("st-moon")}" alt=""></button>
          <button class="send" aria-label="发送">${icon("send")}</button>
        </div>
        <div class="c-foot">只用你确认过的事理解你 · 猜测要你点头才算数 · 夜里会帮你整理当天的记忆</div>
      </div></div>
    </div>`;

  const ball = mountBall(root.querySelector(".buddy-ball"), { size: 72, emotion: "02", idle: true });
  const status = root.querySelector(".buddy-st span");
  ball.onChange((id) => { status.textContent = MOOD_TEXT[id] || "在这儿陪着你"; });

  const list = root.querySelector(".msgs");
  const thread = root.querySelector(".thread");
  let lastDay = "";
  if (!msgs.length) {
    list.innerHTML = `<div class="opener card">
      <h2>${esc(p.nickname || "你好")}，今天想从哪件小事开始？</h2>
      <p>${p.intent_primary ? `你正在靠近「${esc(p.intent_primary)}」。` : ""}直接说话就行，也可以让我替你记下来。</p></div>`;
  }
  for (const m of msgs) {
    const dk = fmtDay(m.created_at);
    if (dk !== lastDay) {
      list.insertAdjacentHTML("beforeend", `<div class="day"><span>${esc(dk)}</span></div>`);
      lastDay = dk;
    }
    list.append(bubble(m));
  }
  const scroll = () => { thread.scrollTop = thread.scrollHeight; };
  requestAnimationFrame(scroll);

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

  let busy = false;
  async function sendMsg() {
    const text = ta.value.trim();
    if (!text || busy) return;
    busy = true;
    ta.value = ""; state.composerDraft = ""; grow();
    if (lastDay !== "今天") { list.insertAdjacentHTML("beforeend", `<div class="day"><span>今天</span></div>`); lastDay = "今天"; }
    list.querySelector(".opener")?.remove();
    list.append(bubble({ role: "user", content: text }));
    const am = document.createElement("div");
    am.className = "msg assistant";
    am.innerHTML = `<span class="mini-orb"></span><div class="col"><div class="bub"><div class="txt"><span class="dots"><i></i><i></i><i></i></span></div></div><div class="when"></div></div>`;
    list.append(am);
    scroll();
    const col = am.querySelector(".col");
    const txt = am.querySelector(".txt");
    let acc = "", started = false;
    const tools = [];
    let sceneToStart = null;

    const finalize = async () => {
      if (!started && !acc) txt.innerHTML = richText("嗯。");
      txt.innerHTML = richText(acc || txt.textContent);
      am.querySelector(".when").textContent = fmtTime(new Date().toISOString());
      busy = false;
      try {
        const data = await refresh();
        const last = (data.messages || []).filter((m) => m.role === "assistant").pop();
        if (last?.content && last.content.length > acc.length) txt.innerHTML = richText(last.content);
      } catch {}
      if (sceneToStart) setTimeout(() => startScene(sceneToStart), 900);
      setTimeout(() => { if (ball.emotion !== "02") ball.set("idle"); }, 2600);
      scroll();
    };

    try {
      await streamChat(text, {
        mood: ({ id }) => ball.set(id),
        context: ({ memories }) => { const r = recall(memories); if (r) col.insertBefore(r, am.querySelector(".when")); },
        delta: ({ text: t }) => {
          if (!started) { started = true; txt.innerHTML = ""; }
          acc += t;
          txt.innerHTML = richText(acc) + '<span class="caret"></span>';
          scroll();
        },
        tool: ({ name, args, result }) => {
          tools.push(name);
          col.insertBefore(toolCard(name, args, result), am.querySelector(".when"));
          if (name === "start_scene" && result?.ok) sceneToStart = result.scene;
          if (name === "complete_step" || name === "log_good_news") ball.pulse("bounce");
          scroll();
        },
        error: () => { ball.set("error"); toast("模型服务暂时连不上", "err"); },
        done: () => {},
      });
    } catch (e) {
      txt.innerHTML = richText("我这边连不上了，稍后再试试。你刚才说的我先留着。");
      ball.set("error");
      toast(e.message || "发送失败", "err");
    } finally {
      await finalize();
      ta.focus();
    }
  }
  send.addEventListener("click", sendMsg);
  if (state.autoSend) {
    ta.value = state.autoSend;
    state.autoSend = "";
    grow();
    setTimeout(sendMsg, 400);
  }
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMsg(); }
  });

  root.querySelector("[data-act=good]").addEventListener("click", (e) => quickGood(e.currentTarget));
  root.querySelector("[data-act=rest]").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    try {
      setData(await api.record("rest", "今天想休息"));
      ball.set("tired");
      toast("今天是偷懒日，什么都不会清零", "", "st-moon");
      btn.classList.add("pop");
    } catch (err) { toast(err.message, "err"); }
  });

  async function quickGood(btn) {
    const { sheet, h } = await import("../ui.js");
    const input = h("textarea", { class: "field", rows: "3", maxlength: "200", placeholder: "今天发生了什么好事？再小也算。" });
    const s = sheet({
      title: "收下一颗星", sticker: "st-jar", body: input,
      footer: [h("button", {
        class: "btn btn-lamp", onclick: async () => {
          const t = input.value.trim();
          if (!t) return;
          try {
            const out = await api.record("good", t);
            s.close();
            setData(out);
            ball.set("happy"); ball.pulse("bounce");
            if (out.xp?.amount) flyXP(btn, out.xp.amount);
            burstAt(btn, 34);
            toast("收下了，星罐里又多一颗", "", "st-jar");
          } catch (e) { toast(e.message, "err"); }
        },
      }, "收下")],
    });
    setTimeout(() => input.focus(), 60);
  }
}
