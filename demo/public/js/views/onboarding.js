// 建档：「一课」形式。选氛围时整页背景当场切换，选颜色时提问的小光当场变色。
import { api } from "../api.js";
import { state } from "../store.js";
import { runLesson } from "../lesson.js";
import { toast } from "../ui.js";
import { applyTheme, themeOf } from "../theme.js";
import { setAgentColor } from "../ball.js";

const OPT_ICON = {
  "自信与表达": ["chat", "var(--c-sky)"], "健康作息": ["moon", "var(--c-violet)"], "学业或作品": ["book", "var(--c-coral)"],
  "关系与边界": ["heart", "var(--c-pink)"], "早起型": ["sun", "var(--c-lemon)"], "夜猫": ["moon", "var(--c-violet)"],
  "不固定": ["steps", "var(--c-sky)"], nudge: ["letter", "var(--c-sky)"], analyze: ["compass", "var(--c-mint)"],
  quiet: ["moon", "var(--c-violet)"], "别说教": ["close", "var(--c-coral)"], "别鸡血催促": ["bolt", "var(--c-orange)"], "无": ["check", "var(--c-mint)"],
};

export function renderOnboarding(root) {
  root.innerHTML = "";
  const qs = state.onboarding || [];
  const answers = {};
  let i = 0;

  const step = (k) => {
    const q = qs[k];
    const opts = (q.options || []).map((o) => {
      const v = typeof o === "string" ? o : o.v;
      const label = typeof o === "string" ? o : o.label;
      const base = { v, label, sub: o.sub };
      if (q.key === "theme") return { ...base, theme: themeOf(v) };
      if (q.key === "agent_hue") return { ...base, color: v };
      const ic = OPT_ICON[v] || OPT_ICON[label];
      return ic ? { ...base, icon: ic[0], tint: ic[1] } : base;
    });
    return {
      q: q.q, hint: q.hint || "", index: k, total: qs.length, opts,
      multi: q.type.startsWith("multi"), maxPick: q.max || 3,
      free: q.type === "text" || q.type.endsWith("_or_text"), ph: q.ph || "",
      optional: !!(q.optional || q.skip || q.key === "boundaries"),
      onPick: q.key === "theme" ? (v) => { applyTheme(v); setAgentColor(answers.agent_hue || themeOf(v).agent); }
        : q.key === "agent_hue" ? (v) => setAgentColor(v) : null,
    };
  };

  runLesson({
    kicker: "认识一下",
    finishLabel: "开始聊天",
    start: async () => step(0),
    answer: async (v) => {
      const q = qs[i];
      answers[q.key] = q.type.startsWith("multi") ? (v || []) : (v ?? (q.key === "agent_name" ? "小光" : q.key === "theme" ? "forest" : ""));
      i += 1;
      if (i < qs.length) return { done: false, step: step(i) };
      await api.onboard(answers);
      return {
        done: true,
        summary: `好，我是${answers.agent_name || "小光"}。你想靠近「${answers.intent_primary}」——我们从今天能做的最小一步开始。`,
        wrote: [
          { type: "profile", label: "记住了你想靠近的", item: { text: answers.intent_primary } },
          { type: "profile", label: "中断时我会这样陪你", item: { text: { nudge: "轻轻提醒你", analyze: "陪你一起找原因", quiet: "先不提，等你开口" }[answers.care_style] || "按你说的来" } },
        ],
      };
    },
    onDone: () => window.dispatchEvent(new CustomEvent("xg:enter")),
    onClose: async () => {
      try {
        await api.onboard({
          agent_name: answers.agent_name || "小光", theme: answers.theme || localStorage.getItem("xg-theme") || "forest",
          agent_hue: answers.agent_hue || "", intent_primary: answers.intent_primary || "还没想好",
          intent_why: answers.intent_why || "想先看看", care_style: answers.care_style || "analyze",
        });
        toast("先进去看看吧，想说的时候再说");
        window.dispatchEvent(new CustomEvent("xg:enter"));
      } catch (e) { toast(e.message, "err"); }
    },
  });
}
