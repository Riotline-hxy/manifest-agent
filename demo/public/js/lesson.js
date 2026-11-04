// 「一课」：所有引导场景共用的全屏问答（多邻国式）。
// 上：进度条；中：小光 + 气泡 + 选项卡 / 输入框 / 呼吸圈；下：继续按钮。
// 每答一题，小光有一个小反应；有的题答完小光会回一句话（点继续再往下）。
// 结束有两种：答完就写的场景是完成页（经验数字滚动上来）；先确认再存的场景是「这次聊到的」，勾选、改一改，再保存。

import { esc, icon, tile } from "./ui.js";
import { mountBall, lookPicture } from "./ball.js";
import { confetti, countUp } from "./fx.js";

const NICE = ["记下了", "嗯，我懂了", "这个很重要", "谢谢你告诉我", "收到", "好，就按你说的"];
const KEYS = "123456789";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

export function runLesson({ kicker = "", start, answer, review: rvApi, onClose, onDone, finishLabel = "继续" }) {
  const el = document.createElement("div");
  el.className = "lesson";
  el.innerHTML = `
    <div class="lesson-top">
      <button class="lesson-x" aria-label="关闭">×</button>
      <div class="bar lesson-bar"><i></i></div>
      <span class="lesson-count num"></span>
    </div>
    <div class="lesson-stage">
      <div class="lesson-kicker">${esc(kicker)}</div>
      <div class="lesson-ask"><div class="lesson-ball"></div><div class="speech lesson-q"></div></div>
      <div class="lesson-answer"></div>
      <div class="lesson-note"></div>
    </div>
    <div class="lesson-foot">
      <div class="lesson-foot-in">
        <button class="btn btn-ghost lesson-skip">跳过</button>
        <div class="lesson-react"></div>
        <button class="btn btn-leaf btn-lg lesson-go off">继续</button>
      </div>
    </div>`;
  document.body.append(el);
  requestAnimationFrame(() => el.classList.add("in"));

  const ball = mountBall(el.querySelector(".lesson-ball"), { size: 116, emotion: "03", agent: false });
  const $ = (s) => el.querySelector(s);
  const go = $(".lesson-go");
  const skip = $(".lesson-skip");
  let step = null;
  let value = null;
  let sel = [];          // 选中的选项（按点的先后）
  let busy = false;
  let breathTimer = 0;
  let next = null;       // 小光回应之后要接着出的那一题
  let ending = null;     // 结束页：{ out, back } —— 这时候关掉 = 返回对话（这次的回答不留）

  const close = (result) => {
    clearInterval(breathTimer);
    document.removeEventListener("keydown", onKey);
    el.classList.remove("in");
    el.classList.add("out");
    setTimeout(() => { el.remove(); ball.destroy(); }, 320);
    if (result) onDone?.(result); else onClose?.();
  };
  const leave = () => (ending ? ending.back() : close(null));
  $(".lesson-x").addEventListener("click", leave);

  function setReady(on) {
    go.classList.toggle("off", !on);
  }

  function say(text) {
    const q = $(".lesson-q");
    q.textContent = text;
    q.classList.remove("pop", "reply"); void q.offsetWidth; q.classList.add("pop");
    return q;
  }

  // 「显化七步」那行小字：这一题对应的那一步亮起来
  function note(s) {
    const n = s?.foot;
    $(".lesson-note").innerHTML = n ? `<span>${esc(n.label)}</span>${n.words.map((w, i) => `<b class="${i === n.at ? "on" : ""}">${esc(w)}</b>`).join("<i>、</i>")}` : "";
  }

  function show(s) {
    step = s;
    next = null;
    value = null;
    sel = [];
    const total = s.total || 1;
    $(".lesson-bar > i").style.width = `${Math.max(4, (s.index / total) * 100)}%`;
    $(".lesson-count").textContent = `${s.index + 1}/${total}`;
    const q = say(s.q);
    if (s.hint) q.insertAdjacentHTML("beforeend", `<small>${esc(s.hint)}</small>`);
    note(s);
    ball.set(s.timer ? "focused" : "listening");
    skip.style.visibility = s.optional ? "visible" : "hidden";
    $(".lesson-react").textContent = "";
    el.querySelector(".lesson-foot").classList.remove("good");
    go.textContent = "继续";
    const box = $(".lesson-answer");
    clearInterval(breathTimer);
    const opts = s.opts || (s.chips || []).map((c) => ({ v: c, label: c }));

    if (s.timer) {
      box.innerHTML = `<div class="breath"><span class="b-ring"></span><span class="b-fill"></span><span class="b-txt">准备好就开始</span></div>
        <div style="text-align:center"><button class="btn btn-sky" data-breathe>开始呼吸</button></div>`;
      box.querySelector("[data-breathe]").addEventListener("click", (e) => {
        e.currentTarget.remove();
        breathe(box.querySelector(".breath"), s.timer, () => { value = opts[0]?.v || "做完了"; setReady(true); ball.set("satisfied"); });
      });
      setReady(false);
      return;
    }
    const free = !!(s.ph || s.free);
    const askable = opts.some((o) => o.ask);
    // 只有文字的选项（plain）排成一列，短的两列；带图标的照旧
    const cls = s.plain ? (opts.some((o) => o.label.length > 8) ? "one" : "") : opts.length > 4 ? "many" : "";
    const optsHTML = opts.length ? `<div class="opts ${cls} ${s.after ? "after" : ""}">${opts.map((o, i) => `
        <button class="opt ${o.theme ? "opt-theme" : ""}" data-v="${esc(o.v)}" style="--i:${i}">
          <span class="key">${KEYS[i] || ""}</span>
          ${o.theme ? `<span class="opt-prev" style="background:linear-gradient(160deg, ${o.theme.swatch[0]}, ${o.theme.swatch[1]})"><i style="background:${o.theme.agent}"></i></span>`
            : o.look ? `<span class="opt-look">${lookPicture(o.look)}</span>`
            : o.color ? `<span class="opt-swatch" style="background:${o.color}"></span>`
            : o.icon ? tile(o.icon, o.tint || "var(--accent)", 38) : ""}
          <span class="lbl">${esc(o.label)}${typeof o.sub === "string" && o.sub ? `<small>${esc(o.sub)}</small>` : ""}</span>
        </button>`).join("")}</div>` : "";
    const taHTML = free || askable ? `<textarea class="field lesson-text ${free ? "" : "hide"}" rows="${s.after ? 3 : !opts.length ? 3 : free ? 1 : 2}" maxlength="${s.max_len || 120}"
        placeholder="${esc(s.ph || "也可以自己写一句")}"></textarea>` : "";
    box.innerHTML = s.after ? taHTML + optsHTML : optsHTML + taHTML;
    const ta = box.querySelector(".lesson-text");
    box.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => pick(b)));
    ta?.addEventListener("input", () => {
      // 自己写的时候，取消掉普通选项（「其他，我想自己说」这种要输入的选项留着）
      if (!s.multi && ta.value.trim() && !sel.some(isAsk)) {
        sel = [];
        box.querySelectorAll(".opt.on").forEach((x) => x.classList.remove("on"));
      }
      collect();
    });
    ta?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
    });
    setReady(false);
    if (!opts.length || s.after) setTimeout(() => ta?.focus(), 250);
  }

  const isAsk = (v) => !!(step?.opts || []).find((o) => o.v === v)?.ask;

  // 现在的答案：多选是一组；选了要输入的选项，答案就是输入的文字
  function collect() {
    const ta = $(".lesson-text");
    const txt = ta && !ta.classList.contains("hide") ? ta.value.trim() : "";
    if (step.multi) {
      const arr = sel.filter((v) => !isAsk(v));
      if (txt && (sel.some(isAsk) || !(step.opts || []).some((o) => o.ask))) arr.push(txt);
      value = arr.length ? arr : null;
    } else {
      value = sel[0] && !isAsk(sel[0]) ? sel[0] : txt || null;
    }
    setReady(!!value);
  }

  function pick(b) {
    const v = b.dataset.v;
    const ta = el.querySelector(".lesson-text");
    if (step.multi) {
      const max = step.maxPick || 3;
      if (b.classList.contains("on")) { b.classList.remove("on"); sel = sel.filter((x) => x !== v); }
      else if (sel.length < max) { b.classList.add("on"); sel.push(v); }
      else { b.classList.add("shake"); setTimeout(() => b.classList.remove("shake"), 400); }
    } else {
      el.querySelectorAll(".opt.on").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      sel = [v];
      if (ta && !isAsk(v)) ta.value = "";
    }
    // 要输入的选项：选上才出输入框
    if (ta && (step.opts || []).some((o) => o.ask) && !(step.ph || step.free)) {
      const askOn = sel.find(isAsk);
      ta.classList.toggle("hide", !askOn);
      if (askOn) {
        ta.placeholder = step.opts.find((o) => o.v === askOn).ask;
        setTimeout(() => ta.focus(), 60);
      }
    }
    collect();
    step.onPick?.(v, ball);
    ball.set("curious");
  }

  async function submit(skipIt = false) {
    if (ending) return;
    if (next) return show(next);              // 小光说完一句，点继续进下一题
    if (busy || (!skipIt && go.classList.contains("off"))) return;
    busy = true;
    const v = skipIt ? null : value;
    // 小反应：底栏变绿 + 一句话 + 小光开心一下（只有文字选项的场景不说「记下了」：点保存之前什么都没存）
    el.querySelector(".lesson-foot").classList.add("good");
    $(".lesson-react").innerHTML = `${tile(skipIt ? "arrow" : "check", "var(--good)", 40)}${step.plain ? "" : `<b>${skipIt ? "没关系，跳过" : NICE[(Math.random() * NICE.length) | 0]}</b>`}`;
    ball.set(skipIt ? "shy" : "happy");
    ball.pulse("bounce");
    go.classList.add("off");
    try {
      const [out] = await Promise.all([answer(v, step), wait(650)]);
      busy = false;
      if (out.done) return out.review ? reviewPage(out) : finish(out);
      if (out.reply) return replyThen(out.reply, out.step);
      show(out.step);
    } catch (e) {
      busy = false;
      ball.set("error");
      $(".lesson-react").innerHTML = `<b style="color:var(--danger)">${esc(e.message || "没成功，再试一次")}</b>`;
      el.querySelector(".lesson-foot").classList.remove("good");
      setReady(true);
    }
  }

  // 小光的回应：气泡里说一句，答题区空出来，点继续再出下一题
  function replyThen(text, nextStep) {
    say(text).classList.add("reply");
    ball.set("happy");
    $(".lesson-answer").innerHTML = "";
    $(".lesson-react").textContent = "";
    el.querySelector(".lesson-foot").classList.remove("good");
    skip.style.visibility = "hidden";
    go.textContent = "继续";
    setReady(true);
    next = nextStep;
  }

  function finish(out) {
    clearInterval(breathTimer);
    $(".lesson-bar > i").style.width = "100%";
    $(".lesson-count").textContent = "";
    note(null);
    ball.set("done");
    ball.pulse("burst");
    const wrote = out.wrote || [];
    const WROTE = { memory: ["memory", "var(--c-violet)"], step: ["flag", "var(--c-orange)"], record: ["star", "var(--c-lemon)"], profile: ["compass", "var(--c-sky)"] };
    say(out.summary || "完成啦。");
    $(".lesson-answer").innerHTML = `
      <div class="lesson-done">
        ${out.xp?.amount ? `<div class="xp-card">${tile("bolt", "var(--accent)", 56)}<div><div class="lbl">获得经验</div><div class="num big">+<span data-c>0</span></div></div></div>` : ""}
        ${wrote.length ? `<div class="wrote">${wrote.map((w, i) => `<div class="w" style="--i:${i}">${tile((WROTE[w.type] || ["sparkles"])[0], (WROTE[w.type] || [0, "var(--accent)"])[1], 40)}
          <div><b>${esc(w.label)}</b><span>${esc(w.item?.title || w.item?.text || (w.type === "profile" ? "以后会按你的选择来" : ""))}</span></div></div>`).join("")}</div>` : ""}
      </div>`;
    if (out.xp?.amount) setTimeout(() => countUp($("[data-c]"), out.xp.amount, 700), 300);
    skip.style.visibility = "hidden";
    $(".lesson-react").innerHTML = "";
    el.querySelector(".lesson-foot").classList.add("good");
    go.textContent = finishLabel;
    go.classList.remove("off");
    confetti(innerWidth / 2, innerHeight * 0.35, 110);
    go.onclick = () => close(out);
  }

  // ---- 结束页：这次聊到的（勾选、改一改，保存选中的；返回对话就不留） ----
  function reviewPage(out) {
    clearInterval(breathTimer);
    $(".lesson-bar > i").style.width = "100%";
    $(".lesson-count").textContent = "";
    note(null);
    ball.set("done");
    ball.pulse("burst");
    const rv = out.review;
    const items = rv.items.map((it) => ({ ...it, on: !it.off }));
    let saving = false;
    ending = {
      back: async () => {
        if (saving) return;
        await rvApi?.back?.();
        close({ ...out, review: true });
      },
    };
    say(rv.say);
    $(".lesson-stage").scrollTop = 0;
    const box = $(".lesson-answer");
    const xp = out.xp?.amount ? `<div class="rv-xp">${icon("bolt")}经验 +${out.xp.amount}${out.xp.coins ? ` · 金币 +${out.xp.coins}` : ""}</div>` : "";
    box.innerHTML = `<div class="rv">
      ${items.length ? `<div class="rv-h">${esc(rv.heading || "这次聊到的")}</div><div class="rv-list"></div>` : ""}
      ${rv.extra ? `<div class="rv-extra"><b>${esc(rv.extra.q)}</b><small>${esc(rv.extra.hint || "")}</small>
        <textarea class="field" rows="2" maxlength="300" placeholder="${esc(rv.extra.ph || "选填")}"></textarea></div>` : ""}
      ${xp}</div>`;
    const list = box.querySelector(".rv-list");
    const extra = box.querySelector(".rv-extra textarea");

    const ready = () => setReady(items.some((it) => it.on) || !!extra?.value.trim());
    const draw = () => {
      if (!list) return;
      list.innerHTML = items.map((it, i) => `
        <div class="rv-item ${it.on ? "on" : ""} ${it.off ? "off" : ""}" data-i="${i}" style="--i:${i}">
          <button class="rv-check" role="checkbox" aria-checked="${it.on}" aria-label="${esc(it.title)}" ${it.off ? "disabled" : ""}>${icon("check")}</button>
          <div class="rv-main">
            <div class="rv-t"><b>${esc(it.title)}</b>${it.to ? `<span class="rv-to">${esc(it.to)}</span>` : ""}</div>
            <div class="rv-text">${esc(it.text)}</div>
            ${it.note ? `<small class="rv-note">${esc(it.note)}</small>` : ""}
          </div>
          ${it.off ? "" : `<button class="icon-btn rv-edit" aria-label="改一改" title="改一改">${icon("edit")}</button>`}
        </div>`).join("");
      list.querySelectorAll(".rv-item").forEach((row) => {
        const it = items[+row.dataset.i];
        if (it.off) return;
        row.addEventListener("click", (e) => {
          if (e.target.closest(".rv-edit, textarea")) return;
          it.on = !it.on;
          row.classList.toggle("on", it.on);
          row.querySelector(".rv-check").setAttribute("aria-checked", it.on);
          ready();
        });
        row.querySelector(".rv-edit").addEventListener("click", () => edit(row, it));
      });
      ready();
    };
    // 改一改：原地变成输入框，回车或点别处就好；改过的默认就是要留下的
    const edit = (row, it) => {
      const t = row.querySelector(".rv-text");
      if (t.querySelector("textarea")) return;
      t.innerHTML = `<textarea class="field" rows="2" maxlength="60"></textarea>`;
      const ta = t.querySelector("textarea");
      ta.value = it.text;
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
      const done = () => { it.text = ta.value.trim() || it.text; it.on = true; draw(); };
      ta.addEventListener("blur", done, { once: true });
      ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); ta.blur(); } });
    };
    draw();
    extra?.addEventListener("input", ready);

    skip.textContent = "返回对话";
    skip.style.visibility = "visible";
    skip.onclick = ending.back;
    $(".lesson-react").innerHTML = "";
    el.querySelector(".lesson-foot").classList.remove("good");
    go.textContent = "保存选中的内容";
    ready();
    if (items.length) confetti(innerWidth / 2, innerHeight * 0.35, 70);

    go.onclick = async () => {
      if (saving || go.classList.contains("off")) return;
      saving = true;
      go.classList.add("off");
      skip.classList.add("off");
      go.textContent = "保存中…";
      const slow = setTimeout(() => { say("好，我整理一下……"); ball.set("thinking"); }, 400);
      try {
        const res = await rvApi.save(items.filter((it) => it.on).map(({ key, text }) => ({ key, text })), extra?.value.trim() || "");
        clearTimeout(slow);
        saved(res);
      } catch (e) {
        clearTimeout(slow);
        saving = false;
        say(rv.say);
        ball.set("error");
        $(".lesson-react").innerHTML = `<b style="color:var(--danger)">${esc(e.message || "没存上，再试一次")}</b>`;
        go.textContent = "保存选中的内容";
        skip.classList.remove("off");
        ready();
      }
    };
  }

  // 存好了：小光回一段话，下面列出每一项放到了哪儿
  function saved(res) {
    ending = { back: () => close({ ...res, review: true }) };
    say(res.reply || "收好了。");
    ball.set("happy");
    ball.pulse("bounce");
    const w = res.wrote || [];
    $(".lesson-answer").innerHTML = w.length ? `<div class="rv"><div class="rv-h">放好了</div><div class="rv-done">${w.map((x, i) => `
      <div class="rv-d" style="--i:${i}">${icon("check")}<div><b>${esc(x.text)}</b><span>${esc(x.label)} · ${esc(x.where)}</span></div></div>`).join("")}</div></div>` : "";
    skip.style.visibility = "hidden";
    $(".lesson-react").innerHTML = "";
    el.querySelector(".lesson-foot").classList.add("good");
    go.textContent = "回到对话";
    go.classList.remove("off");
    go.onclick = ending.back;
    $(".lesson-stage").scrollTo({ top: 0, behavior: "smooth" });     // 列表长的时候，先让人看到小光的回话
  }

  function onKey(e) {
    if (!step || e.target.tagName === "TEXTAREA") {
      if (e.key === "Escape") leave();
      return;
    }
    if (ending) {
      if (e.key === "Escape") ending.back();
      return;
    }
    const i = KEYS.indexOf(e.key);
    if (i >= 0 && !next) {
      const b = el.querySelectorAll(".opt")[i];
      if (b) pick(b);
    } else if (e.key === "Enter") submit();
    else if (e.key === "Escape") leave();
  }
  document.addEventListener("keydown", onKey);
  go.addEventListener("click", () => { if (go.onclick) return; submit(); });
  skip.addEventListener("click", () => { if (!ending) submit(true); });

  function breathe(box, t, done) {
    const fill = box.querySelector(".b-fill");
    const txt = box.querySelector(".b-txt");
    const total = t.rounds || 6;
    let round = 0, phase = "in", left = t.inhale;
    fill.style.transition = `transform ${t.inhale}s ease-in-out`;
    fill.style.transform = "scale(1)";
    const tick = () => {
      txt.innerHTML = `<b>${phase === "in" ? "吸气" : "呼气"}</b><span>${left}</span><small>第 ${round + 1}/${total} 轮</small>`;
      left -= 1;
      if (left < 0) {
        if (phase === "in") {
          phase = "out"; left = t.exhale;
          fill.style.transition = `transform ${t.exhale}s ease-in-out`; fill.style.transform = "scale(.45)";
        } else {
          round += 1;
          if (round >= total) { clearInterval(breathTimer); txt.innerHTML = "<b>做完了</b>"; done(); return; }
          phase = "in"; left = t.inhale;
          fill.style.transition = `transform ${t.inhale}s ease-in-out`; fill.style.transform = "scale(1)";
        }
        tick();
      }
    };
    tick();
    breathTimer = setInterval(tick, 1000);
  }

  (async () => {
    try {
      show(await start());
    } catch (e) {
      $(".lesson-q").textContent = e.message || "打不开这个练习";
      ball.set("error");
    }
  })();

  return { close };
}
