// 「一课」：建档和所有引导场景共用的全屏问答（多邻国式）。
// 上：进度条；中：小光 + 气泡 + 选项卡 / 输入框 / 呼吸圈；下：继续按钮。
// 每答一题，小光有一个小反应；最后是完成页，经验数字滚动上来。

import { esc } from "./ui.js";
import { mountBall } from "./ball.js";
import { art, confetti, countUp } from "./fx.js";

const NICE = ["记下了", "嗯，我懂了", "这个很重要", "谢谢你告诉我", "收到", "好，就按你说的"];
const KEYS = "123456789";

export function runLesson({ kicker = "", start, answer, onClose, onDone, finishLabel = "继续" }) {
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

  const ball = mountBall(el.querySelector(".lesson-ball"), { size: 116, emotion: "03" });
  const $ = (s) => el.querySelector(s);
  const go = $(".lesson-go");
  const skip = $(".lesson-skip");
  let step = null;
  let value = null;
  let busy = false;
  let breathTimer = 0;

  const close = (result) => {
    clearInterval(breathTimer);
    document.removeEventListener("keydown", onKey);
    el.classList.remove("in");
    el.classList.add("out");
    setTimeout(() => { el.remove(); ball.destroy(); }, 320);
    if (result) onDone?.(result); else onClose?.();
  };
  $(".lesson-x").addEventListener("click", () => close(null));

  function setReady(on) {
    go.classList.toggle("off", !on);
  }

  function show(s) {
    step = s;
    value = s.multi ? [] : null;
    const total = s.total || 1;
    $(".lesson-bar > i").style.width = `${Math.max(4, (s.index / total) * 100)}%`;
    $(".lesson-count").textContent = `${s.index + 1}/${total}`;
    const q = $(".lesson-q");
    q.textContent = s.q;
    q.classList.remove("pop"); void q.offsetWidth; q.classList.add("pop");
    if (s.hint) q.insertAdjacentHTML("beforeend", `<small>${esc(s.hint)}</small>`);
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
    let html = "";
    if (opts.length) {
      html += `<div class="opts ${opts.length > 4 ? "many" : ""}">${opts.map((o, i) => `
        <button class="opt" data-v="${esc(o.v)}" style="--i:${i}">
          <span class="key">${KEYS[i] || ""}</span>
          ${o.art ? `<img src="${art(o.art)}" alt="">` : ""}
          <span class="lbl">${esc(o.label)}</span>
        </button>`).join("")}</div>`;
    }
    if (s.ph || s.free) {
      html += `<textarea class="field lesson-text" rows="${opts.length ? 1 : 3}" maxlength="${s.max_len || 120}"
        placeholder="${esc(s.ph || "也可以自己写一句")}"></textarea>`;
    }
    box.innerHTML = html;
    const ta = box.querySelector(".lesson-text");
    box.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => pick(b)));
    ta?.addEventListener("input", () => {
      if (ta.value.trim()) {
        box.querySelectorAll(".opt.on").forEach((x) => { if (!s.multi) x.classList.remove("on"); });
        value = s.multi ? [...(value || []).filter((x) => opts.some((o) => o.v === x)), ta.value.trim()] : ta.value.trim();
      } else if (!s.multi) value = null;
      setReady(!!(s.multi ? value?.length : value));
    });
    ta?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
    });
    setReady(false);
    if (!opts.length) setTimeout(() => ta?.focus(), 250);
  }

  function pick(b) {
    const v = b.dataset.v;
    if (step.multi) {
      const max = step.maxPick || 3;
      if (b.classList.contains("on")) { b.classList.remove("on"); value = value.filter((x) => x !== v); }
      else if (value.length < max) { b.classList.add("on"); value.push(v); }
      else { b.classList.add("shake"); setTimeout(() => b.classList.remove("shake"), 400); }
      setReady(value.length > 0);
    } else {
      el.querySelectorAll(".opt.on").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      const ta = el.querySelector(".lesson-text");
      if (ta) ta.value = "";
      value = v;
      setReady(true);
    }
    ball.set("curious");
  }

  async function submit(skipIt = false) {
    if (busy || (!skipIt && go.classList.contains("off"))) return;
    busy = true;
    const v = skipIt ? null : value;
    // 小反应：底栏变绿 + 一句话 + 小光开心一下
    el.querySelector(".lesson-foot").classList.add("good");
    $(".lesson-react").innerHTML = `<img src="${art("st-seed")}" alt=""><b>${skipIt ? "没关系，跳过" : NICE[(Math.random() * NICE.length) | 0]}</b>`;
    ball.set(skipIt ? "shy" : "happy");
    ball.pulse("bounce");
    go.classList.add("off");
    try {
      const [out] = await Promise.all([answer(v, step), new Promise((r) => setTimeout(r, 650))]);
      busy = false;
      if (out.done) return finish(out);
      show(out.step);
    } catch (e) {
      busy = false;
      ball.set("error");
      $(".lesson-react").innerHTML = `<b style="color:var(--danger)">${esc(e.message || "没成功，再试一次")}</b>`;
      el.querySelector(".lesson-foot").classList.remove("good");
      setReady(true);
    }
  }

  function finish(out) {
    clearInterval(breathTimer);
    $(".lesson-bar > i").style.width = "100%";
    $(".lesson-count").textContent = "";
    ball.set("done");
    ball.pulse("burst");
    const wrote = out.wrote || [];
    const WROTE_ART = { memory: "st-mirror", step: "st-flag", record: "st-jar", profile: "st-compass" };
    $(".lesson-q").textContent = out.summary || "完成啦。";
    $(".lesson-answer").innerHTML = `
      <div class="lesson-done">
        ${out.xp?.amount ? `<div class="xp-card"><img src="${art("st-jar")}" alt=""><div><div class="lbl">获得经验</div><div class="num big">+<span data-c>0</span></div></div></div>` : ""}
        ${wrote.length ? `<div class="wrote">${wrote.map((w, i) => `<div class="w" style="--i:${i}"><img src="${art(WROTE_ART[w.type] || "st-seed")}" alt="">
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

  function onKey(e) {
    if (!step || e.target.tagName === "TEXTAREA") {
      if (e.key === "Escape") close(null);
      return;
    }
    const i = KEYS.indexOf(e.key);
    if (i >= 0) {
      const b = el.querySelectorAll(".opt")[i];
      if (b) pick(b);
    } else if (e.key === "Enter") submit();
    else if (e.key === "Escape") close(null);
  }
  document.addEventListener("keydown", onKey);
  go.addEventListener("click", () => { if (go.onclick) return; submit(); });
  skip.addEventListener("click", () => submit(true));

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
