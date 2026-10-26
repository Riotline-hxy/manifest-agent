// 建构：一屏一题，允许跳过。完成后直接进入对话。
import { api } from "../api.js";
import { state, setData } from "../store.js";
import { esc, toast, icon } from "../ui.js";
import { orb, installOrbStyles } from "../orb.js";

export function renderOnboarding(root) {
  installOrbStyles();
  const qs = (state.onboarding || []).filter((q) => q);
  const answers = {};
  let i = 0;
  let multi = [];

  root.innerHTML = `<main class="onboard"><div class="ob-card">
    <div class="ob-top">
      <div class="ob-steps" id="steps"></div>
      <button class="ob-skip" id="skipAll">先跳过，直接聊</button>
    </div>
    <div id="slot"></div>
  </div></main>`;

  const steps = root.querySelector("#steps");
  const slot = root.querySelector("#slot");

  steps.innerHTML = qs.map((_, k) => `<i class="${k === 0 ? "on" : ""}"></i>`).join("");

  function current() {
    return qs[i];
  }

  function render() {
    const q = current();
    if (!q) return submit();
    steps.querySelectorAll("i").forEach((el, k) => el.classList.toggle("on", k <= i));
    multi = [];
    const isSingle = q.type === "single" || q.type === "single_or_text";
    const isMulti = q.type === "multi" || q.type === "multi_or_text";
    slot.innerHTML = `
      <div class="ob-q">
        <div class="num">0${i + 1} / 0${qs.length}</div>
        <h2>${esc(q.q)}</h2>
        ${q.hint ? `<p class="hint">${esc(q.hint)}</p>` : q.ph && !isSingle ? `<p class="hint">${esc(q.ph)}</p>` : `<p class="hint"></p>`}
        <div class="ob-opts" id="opts">
          ${isSingle ? (q.options || []).map((o) => {
            const v = typeof o === "string" ? o : o.v;
            const l = typeof o === "string" ? o : o.label;
            return `<button class="chip" data-v="${esc(v)}">${esc(l)}</button>`;
          }).join("") : ""}
          ${isMulti ? (q.options || []).map((o) => `<button class="chip" data-v="${esc(o)}">${esc(o)}</button>`).join("") : ""}
        </div>
        ${isSingle || isMulti ? "" : `<input class="field ob-input" id="freeText" placeholder="${esc(q.ph || "")}" maxlength="60">`}
        ${isSingle || isMulti ? `<input class="field ob-input" id="freeText" style="margin-top:12px;font-size:15px;font-family:var(--sans)" placeholder="${esc(q.ph || "也可以自己写一句")}" maxlength="60">` : ""}
      </div>
      <div class="ob-foot">
        <button class="btn btn-quiet btn-sm" id="back">${i > 0 ? "上一题" : ""}</button>
        ${q.skip || q.optional ? `<button class="btn btn-quiet btn-sm" id="skip">这题跳过</button>` : ""}
        <div class="spacer"></div>
        <button class="btn btn-ink" id="next">${i === qs.length - 1 ? "开始" : "下一题"} ${icon("arrow")}</button>
      </div>`;

    const inp = slot.querySelector("#freeText");
    setTimeout(() => inp?.focus(), 60);

    slot.querySelectorAll("[data-v]").forEach((b) => {
      if (isMulti && q.type.includes("multi")) {
        b.addEventListener("click", () => {
          const v = b.dataset.v;
          if (multi.includes(v)) {
            multi = multi.filter((x) => x !== v);
            b.classList.remove("on");
          } else {
            if (multi.length >= (q.max || 3)) return toast(`最多选 ${q.max || 3} 个`);
            multi.push(v);
            b.classList.add("on");
          }
          if (q.type === "multi_or_text") {
            if (multi.includes("无")) multi = ["无"];
          }
        });
      } else {
        b.addEventListener("click", () => {
          slot.querySelectorAll("[data-v]").forEach((x) => x.classList.remove("on"));
          b.classList.add("on");
          inp.value = b.dataset.v;
        });
      }
    });

    const adv = (skip = false) => {
      const q2 = current();
      if (!skip) {
        if (q2.type.includes("multi")) {
          answers[q2.key] = multi.length ? multi : inp.value.trim() ? [inp.value.trim()] : [];
        } else {
          answers[q2.key] = inp?.value.trim() || "";
        }
        const required = !q2.optional && q2.key !== "boundaries";
        if (required && !answers[q2.key] && !(Array.isArray(answers[q2.key]) && answers[q2.key].length)) {
          toast("这题需要选一个，或者点「跳过」");
          return;
        }
      } else {
        answers[q2.key] = q2.type.includes("multi") ? [] : "";
      }
      i += 1;
      render();
    };

    slot.querySelector("#next").addEventListener("click", () => {
      if (inp?.value.trim() && !slot.querySelector("[data-v].on") && !q.type.includes("multi")) {
        answers[current().key] = inp.value.trim();
      }
      adv(false);
    });
    slot.querySelector("#skip")?.addEventListener("click", () => adv(true));
    slot.querySelector("#back").addEventListener("click", () => {
      if (i === 0) return;
      i -= 1;
      render();
    });
    inp?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        slot.querySelector("#next").click();
      }
    });
  }

  let submitting = false;
  async function submit() {
    if (submitting) return;
    submitting = true;
    try {
      await api.onboard(answers);
      toast("建档完成");
      state.route = "chat";
      location.hash = "#chat";
      window.dispatchEvent(new CustomEvent("xg:enter"));
    } catch (e) {
      submitting = false;
      toast(e.message, "err");
    }
  }

  root.querySelector("#skipAll").addEventListener("click", async () => {
    // 只申请最小可用身份：保留已答的部分，用默认值补全
    const minimal = {
      agent_name: answers.agent_name || "小光",
      agent_avatar_id: answers.agent_avatar_id || "soft",
      intent_primary: answers.intent_primary || "还没想好",
      intent_why: answers.intent_why || "想先看看这个产品能做什么",
      care_style: answers.care_style || "analyze",
    };
    try {
      await api.onboard(minimal);
      state.route = "chat";
      location.hash = "#chat";
      window.dispatchEvent(new CustomEvent("xg:enter"));
    } catch (e) {
      toast(e.message, "err");
    }
  });

  render();
}
