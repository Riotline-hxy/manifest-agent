// 对话：整站的主工作台。一个延续的线程，不做会话切换。
import { api, streamChat } from "../api.js";
import { state, setData, refresh, go, xpNote } from "../store.js";
import { esc, richText, h, fmtDay, fmtTime, toast, icon } from "../ui.js";
import { orb, installOrbStyles } from "../orb.js";

const TOOL_META = {
  add_step: { label: "计划", icon: "plan" },
  complete_step: { label: "计划", icon: "check" },
  log_good_news: { label: "好消息", icon: "star" },
  log_lazy_day: { label: "偷懒日", icon: "moon" },
  remember: { label: "记忆", icon: "space" },
  search_memory: { label: "回忆", icon: "spark" },
  get_growth: { label: "成长", icon: "pet" },
  knowledge_search: { label: "心灵学堂", icon: "book" },
  set_care_style: { label: "偏好", icon: "space" },
  start_scene: { label: "场景", icon: "spark" },
};

const HINTS = [
  "帮我记住我喜欢吃寿司",
  "我三天没健身了",
  "小光，你对我了解多少？",
  "今天有什么值得开心的事吗",
  "水桶效应是什么意思",
  "我什么时候能进化到下一阶段？",
];

function toolCard(name, args, result) {
  const meta = TOOL_META[name] || { label: "动作", icon: "spark" };
  const ok = result?.ok !== false;
  const wrap = document.createElement("div");
  wrap.className = `toolcard ${ok ? "" : "fail"}`;
  let title = "";
  let note = "";
  let xp = "";
  let extra = "";
  if (name === "add_step" && ok) {
    title = result.step?.title || args.title || "";
    note = "已写入你的蜕变计划";
  } else if (name === "complete_step") {
    if (ok) {
      title = result.step?.title || "";
      note = "这一小步完成了";
      xp = xpNote(result.xp);
    } else {
      title = "没找到对应的一小步";
      note = "没有写入任何完成记录";
    }
  } else if (name === "log_good_news") {
    if (ok) {
      title = result.record?.text || "";
      note = `第 ${result.count} 条好消息`;
      xp = xpNote(result.xp);
    } else {
      title = "没有记下来";
      note = result.error || "保存失败";
    }
  } else if (name === "log_lazy_day") {
    title = "今天记成了偷懒日";
    note = "不清零任何进度";
  } else if (name === "remember") {
    if (ok) {
      title = result.memory?.text || "";
      note = "已写入长期记忆，可以在「我的空间」修改";
    } else {
      title = "没有写入";
      note = result.error || "";
    }
  } else if (name === "get_growth") {
    const g = result.growth || {};
    title = g.stage?.name ? `现在是「${g.stage.name}」` : "查了成长状态";
    note = `累计 ${g.total ?? "?"} 经验` + (g.to_next ? `，再 ${g.to_next} 到${g.next.name}` : "");
  } else if (name === "knowledge_search") {
    const list = result.articles || [];
    title = list.length ? "找到了这些篇目" : "学堂里没有相关篇目";
    note = list.length ? list.map((a) => a.title).join(" · ") : "不会凭空写一篇";
    extra = list.map((a) => `
      <div class="mini-step">
        <span>${esc(a.title)}</span>
        <button class="btn btn-quiet btn-sm cta" data-article="${esc(a.id)}">阅读</button>
      </div>`).join("");
  } else if (name === "set_care_style") {
    title = ok ? "互动偏好更新了" : "没有更新";
    note = ok ? result.shown || "" : result.error || "";
  } else if (name === "start_scene") {
    title = result.title || args.scene || "";
    note = "场景会在输入框上方开始";
  } else if (name === "search_memory") {
    const list = result.memories || [];
    title = list.length ? `从记忆里找到 ${list.length} 条` : "没有找到相关记忆";
    note = list.map((m) => m.text).join("；");
  } else {
    title = ok ? "完成" : "没有写成";
    note = result?.error || "";
  }
  wrap.innerHTML = `
    <div class="tc-head">${icon(meta.icon)}<span>${esc(meta.label)}</span>
      ${xp ? `<span class="xp">${esc(xp)}</span>` : ""}</div>
    <div class="tc-body">
      <div class="tc-title">${esc(title)}</div>
      ${note ? `<div class="tc-note">${esc(note)}</div>` : ""}
    </div>
    ${extra}`;
  wrap.querySelectorAll("[data-article]").forEach((b) => {
    b.addEventListener("click", () => {
      state.articleId = b.dataset.article;
      go("article");
    });
  });
  return wrap;
}

function recallBlock(memories) {
  if (!memories?.length) return null;
  const el = document.createElement("details");
  el.className = "recall";
  el.innerHTML = `<summary>小光参考了 ${memories.length} 条${memories.some((m) => m.status === "guess") ? "（含待确认）" : ""}记忆</summary>
    <ul>${memories.map((m) => `<li><span class="tag ${m.status === "guess" ? "gold" : "jade"}">${m.status === "guess" ? "猜测" : "记得"}</span><span>${esc(m.text)}</span></li>`).join("")}</ul>`;
  return el;
}

function messageNode(msg, { streaming = false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${msg.role}`;
  if (msg.role === "user") {
    wrap.innerHTML = `<div class="bubble">${esc(msg.content)}</div>`;
    return wrap;
  }
  const meta = msg.meta || {};
  wrap.innerHTML = `
    <div class="who"><span class="glyph">光</span></div>
    <div class="body">
      <div class="text">${streaming ? "" : richText(msg.content)}</div>
      <div class="meta">
        <span>${msg.created_at ? fmtTime(msg.created_at) : ""}${meta.scene ? " · 场景" : ""}${meta.proactive ? " · 主动找你" : ""}${meta.scene_done ? " · 已写入" : ""}</span>
        ${streaming ? "" : `<button data-copy>复制</button>`}
      </div>
    </div>`;
  const copy = wrap.querySelector("[data-copy]");
  if (copy) {
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(msg.content);
        toast("已复制");
      } catch {
        toast("复制失败", "err");
      }
    });
  }
  return wrap;
}

function dayRule(iso) {
  const d = document.createElement("div");
  d.className = "day-rule";
  d.textContent = fmtDay(iso);
  return d;
}

export function renderChat(root) {
  installOrbStyles();
  const data = state.data;
  const messages = data.messages || [];
  const steps = (data.steps || []).filter((s) => s.status === "todo");
  const scene = data.scene;

  root.innerHTML = `<div class="chat"></div>`;
  const chat = root.firstElementChild;

  const thread = document.createElement("div");
  thread.className = "thread";
  const inner = document.createElement("div");
  inner.className = "thread-inner";
  thread.append(inner);

  // 开场 / 空态
  const hasHistory = messages.length > 0;
  if (!hasHistory) {
    const op = document.createElement("div");
    op.className = "opener";
    const ow = document.createElement("div");
    ow.className = "orb-wrap";
    ow.append(orb("idle", { size: "lg" }));
    op.append(ow);
    op.insertAdjacentHTML("beforeend", `
      <h2>${esc(data.profile?.nickname || "你好")}，今天想从哪一件小事开始？</h2>
      <p>你可以直接说话，也可以让我替你记下来。${data.prefs?.intent ? `你正在靠近「${esc(data.prefs.intent)}」。` : ""}</p>
      <div class="chips">${["帮我定一个今天能做的小步", "我想记一件好事", "陪我呼吸一下", "你还记得我吗"].map((t) => `<button class="chip" data-fill="${esc(t)}">${esc(t)}</button>`).join("")}</div>`);
    inner.append(op);
  }

  let lastDay = "";
  for (const m of messages) {
    const dk = fmtDay(m.created_at);
    if (dk && dk !== lastDay) {
      inner.append(dayRule(m.created_at));
      lastDay = dk;
    }
    inner.append(messageNode(m));
  }

  chat.append(thread);

  // 输入区
  const composer = document.createElement("div");
  composer.className = "composer";
  composer.innerHTML = `<div class="composer-inner"></div>`;
  const ci = composer.firstElementChild;
  chat.append(composer);

  const hints = document.createElement("div");
  hints.className = "hints";
  hints.innerHTML = HINTS.map((t) => `<button class="chip" data-fill="${esc(t)}">${esc(t)}</button>`).join("");
  ci.append(hints);

  const inputbox = document.createElement("div");
  inputbox.className = "inputbox";
  inputbox.innerHTML = `
    <button class="ib" data-act="good" title="记一条好消息" aria-label="记一条好消息">${icon("star")}</button>
    <textarea rows="1" placeholder="跟小光说点什么…" aria-label="消息"></textarea>
    <button class="ib" data-act="rest" title="今天是偷懒日" aria-label="今天是偷懒日">${icon("moon")}</button>
    <button class="send" aria-label="发送">${icon("send")}</button>`;
  ci.append(inputbox);

  const foot = document.createElement("div");
  foot.className = "composer-foot";
  foot.innerHTML = `<span>小光记得你确认过的内容；猜测要你点头才算数。</span>
    <span class="spacer"></span>
    <span><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd>+<kbd>Enter</kbd> 换行</span>`;
  ci.append(foot);

  const ta = inputbox.querySelector("textarea");
  const sendBtn = inputbox.querySelector(".send");

  function autoGrow() {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 168) + "px";
  }
  ta.addEventListener("input", () => {
    state.composerDraft = ta.value;
    autoGrow();
  });
  ta.value = state.composerDraft || "";
  autoGrow();

  function fill(text) {
    ta.value = text;
    state.composerDraft = text;
    autoGrow();
    ta.focus();
  }
  root.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => fill(b.dataset.fill)));
  hints.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => fill(b.dataset.fill)));

  // 场景状态条
  function renderScene() {
    ci.querySelector(".scene-bar")?.remove();
    const sc = state.data?.scene;
    if (!sc) return;
    const step = state.sceneStep;
    if (!step) {
      loadSceneStep(sc.id);
      return;
    }
    const bar = document.createElement("div");
    bar.className = "scene-bar";
    const total = step.total || 1;
    const chips = (step.chips || []).map((c) => `<button class="chip" data-chip="${esc(c)}">${esc(c)}</button>`).join("");
    bar.innerHTML = `
      <div class="sb-top">引导 · ${esc(step.title || "")}
        <button class="x" data-act="cancel">结束</button></div>
      <div class="q">${esc(step.q)}</div>
      ${step.timer ? breathBox(step.timer) : ""}
      <div class="chips">${chips}</div>
      <div class="prog">${Array.from({ length: total }, (_, i) => `<i class="${i <= step.index ? "on" : ""}"></i>`).join("")}</div>`;
    ci.insertBefore(bar, hints);
    bar.querySelectorAll("[data-chip]").forEach((b) => b.addEventListener("click", () => answerScene(b.dataset.chip)));
    bar.querySelector("[data-act=cancel]").addEventListener("click", async () => {
      await api.sceneCancel();
      state.sceneStep = null;
      await refresh();
      renderScene();
    });
    if (step.timer) startBreath(bar, step.timer);
    if (step.ph) ta.placeholder = step.ph;
  }

  async function loadSceneStep(sceneId) {
    try {
      const out = await api.sceneStart(sceneId);
      state.sceneStep = { ...out.step, title: out.scene.title };
      if (out.run) state.sceneRunId = out.run.id;
      setData({ scene: out.run });
      renderScene();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  async function answerScene(text) {
    const runId = state.sceneRunId || state.data?.scene?.id;
    if (!runId) return;
    try {
      const out = await api.sceneAnswer(runId, text);
      const t = document.createElement("div");
      t.className = "msg user";
      t.innerHTML = `<div class="bubble">${esc(text)}</div>`;
      inner.append(t);
      if (out.done) {
        state.sceneStep = null;
        state.sceneRunId = null;
        setData(out.state || {});
        const done = document.createElement("div");
        done.className = "msg assistant";
        done.innerHTML = `<div class="who"><span class="glyph">光</span></div>
          <div class="body"><div class="text">${richText(out.summary)}</div>
          <div class="meta"><span>${out.xp?.amount ? `+${out.xp.amount} 经验` : "练习已完成"}</span></div></div>`;
        inner.append(done);
        renderScene();
        scroll();
        await refresh();
        return;
      }
      state.sceneStep = out.step;
      renderScene();
      scroll();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  function scroll() {
    thread.scrollTop = thread.scrollHeight;
  }
  scroll();

  // 发送
  let busy = false;
  async function send(textOverride) {
    const text = (textOverride ?? ta.value).trim();
    if (!text || busy) return;
    busy = true;
    sendBtn.disabled = true;
    ta.value = "";
    state.composerDraft = "";
    autoGrow();
    hints.style.opacity = "0";

    const um = document.createElement("div");
    um.className = "msg user";
    um.innerHTML = `<div class="bubble">${esc(text)}</div>`;
    inner.append(um);

    const am = document.createElement("div");
    am.className = "msg assistant";
    am.innerHTML = `<div class="who"><span class="glyph">光</span></div>
      <div class="body"><div class="text"><span class="thinking"><i></i><i></i><i></i></span></div><div class="meta"></div></div>`;
    inner.append(am);
    scroll();

    const body = am.querySelector(".body");
    const textEl = am.querySelector(".text");
    const glyph = am.querySelector(".glyph");
    let acc = "";
    let started = false;
    let tools = [];
    let moodTimer;
    let finalized = false;
    // done 与 close 都可能到达；只收尾一次。服务端把这条回复完整落库，
    // 所以即使最后几个 delta 丢了，也以落库内容为准。
    async function finalize() {
      if (finalized) return;
      finalized = true;
      textEl.classList.remove("streaming");
      if (acc) {
        textEl.innerHTML = richText(acc);
        body.querySelector(".meta").innerHTML = `<span>${fmtTime(new Date().toISOString())}</span><button data-copy>复制</button>`;
        body.querySelector("[data-copy]")?.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(acc);
            toast("已复制");
          } catch {}
        });
      }
      glyph.style.background = "";
      glyph.style.color = "";
      glyph.style.transform = "";
      try {
        const data = await refresh();
        const last = (data.messages || []).filter((m) => m.role === "assistant").pop();
        if (last && acc && last.content && last.content.length > acc.length) {
          acc = last.content;
          textEl.innerHTML = richText(acc);
        }
        renderScene();
      } catch {}
      if (tools.some((t) => t.name === "start_scene" && t.result?.ok)) {
        state.sceneStep = null;
        loadSceneStep(tools.find((t) => t.name === "start_scene").result.scene);
      }
      scroll();
    }

    try {
      await streamChat(text, {
        mood: ({ id }) => {
          clearTimeout(moodTimer);
          const speaking = id === "39";
          glyph.style.transform = speaking ? "scale(1.08)" : "";
        },
        context: ({ memories }) => {
          const r = recallBlock(memories);
          if (r) body.insertBefore(r, body.querySelector(".meta"));
        },
        delta: ({ text: t }) => {
          if (!started) {
            started = true;
            textEl.innerHTML = "";
            textEl.classList.add("streaming");
            glyph.textContent = "光";
            glyph.style.background = "var(--jade)";
            glyph.style.color = "#fff";
          }
          acc += t;
          textEl.innerHTML = richText(acc) + `<span class="caret"></span>`;
          scroll();
        },
        tool: ({ name, args, result }) => {
          tools.push({ name, result });
          body.insertBefore(toolCard(name, args, result), body.querySelector(".meta"));
          scroll();
        },
        error: ({ message }) => {
          if (!acc) {
            textEl.innerHTML = richText(message || "我这边出了点问题。");
          }
          toast("模型服务暂时不可用", "err");
        },
        done: finalize,
        close: finalize,
      });
    } catch (e) {
      textEl.innerHTML = richText("我这边连不上了，稍后再试试。你刚才说的我先留着。");
      toast(e.message || "发送失败", "err");
    } finally {
      clearTimeout(moodTimer);
      finalize();
      busy = false;
      sendBtn.disabled = false;
      ta.focus();
      scroll();
    }
  }

  sendBtn.addEventListener("click", () => send());
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send();
    }
  });

  inputbox.querySelector("[data-act=good]").addEventListener("click", async () => {
    const text = prompt("记一件好事（再小也算）")?.trim();
    if (!text) return;
    try {
      const out = await api.record("good", text);
      sortRefresh(out, "收下一条好消息");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  inputbox.querySelector("[data-act=rest]").addEventListener("click", async () => {
    try {
      const out = await api.record("rest", "今天想休息");
      sortRefresh(out, "今天是偷懒日，什么都不会清零");
    } catch (e) {
      toast(e.message, "err");
    }
  });

  async function sortRefresh(out, msg) {
    setData(out);
    toast(msg);
    await refresh();
    rerenderKeepDraft();
  }

  function rerenderKeepDraft() {
    const draft = ta.value;
    const pos = thread.scrollTop;
    renderChat(root);
    const nt = root.querySelector("textarea");
    if (nt) {
      nt.value = draft;
      state.composerDraft = draft;
    }
    const t2 = root.querySelector(".thread");
    if (t2) t2.scrollTop = pos;
  }

  renderScene();
  return { renderScene, rerenderKeepDraft };
}

// 呼吸练习
function breathBox(timer) {
  return `<div class="breath" data-breath>
      <div class="ring"></div><div class="pulse"></div>
      <span class="cnt">准备好就开始</span>
    </div>`;
}

let breathTimer = null;
function startBreath(bar, timer) {
  clearInterval(breathTimer);
  const box = bar.querySelector("[data-breath]");
  if (!box) return;
  const pulse = box.querySelector(".pulse");
  const cnt = box.querySelector(".cnt");
  let round = 0;
  let phase = "in";
  let left = timer.inhale;
  const total = timer.rounds || 6;
  const tick = () => {
    cnt.textContent = `${phase === "in" ? "吸气" : "呼气"} ${left} · 第 ${Math.min(round + 1, total)}/${total} 轮`;
    left -= 1;
    if (left < 0) {
      if (phase === "in") {
        phase = "out";
        left = timer.exhale - 1;
        pulse.classList.remove("in");
        pulse.classList.add("out");
      } else {
        round += 1;
        if (round >= total) {
          cnt.textContent = "做完了";
          pulse.className = "pulse";
          clearInterval(breathTimer);
          return;
        }
        phase = "in";
        left = timer.inhale - 1;
        pulse.classList.remove("out");
        pulse.classList.add("in");
      }
    }
  };
  pulse.classList.add("in");
  tick();
  breathTimer = setInterval(tick, 1000);
}
