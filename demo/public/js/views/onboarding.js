// 建档：用「一课」的形式，一屏一题，小光问，你点。可以跳过可选题，
// 也可以一开始就「先跳过」，直接去聊天。
import { api } from "../api.js";
import { state } from "../store.js";
import { runLesson } from "../lesson.js";
import { toast } from "../ui.js";

const OPT_ART = {
  soft: "st-seed", stardust: "st-jar", ink: "st-book", geo: "st-compass",
  "自信与表达": "st-letter", "健康作息": "st-moon", "学业或作品": "st-book", "关系与边界": "st-mirror",
  "早起型": "st-seed", "夜猫": "st-moon", "不固定": "st-steps",
  nudge: "st-letter", analyze: "st-compass", quiet: "st-moon",
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
      return { v, label, art: OPT_ART[v] || OPT_ART[label] };
    });
    return {
      q: q.q, hint: q.hint || "", index: k, total: qs.length,
      opts, multi: q.type.startsWith("multi"), maxPick: q.max || 3,
      free: q.type === "text" || q.type.endsWith("_or_text"), ph: q.ph || "",
      optional: !!(q.optional || q.skip || q.key === "boundaries"),
    };
  };

  runLesson({
    kicker: "认识一下",
    finishLabel: "开始聊天",
    start: async () => step(0),
    answer: async (v) => {
      const q = qs[i];
      answers[q.key] = q.type.startsWith("multi") ? (v || []) : (v ?? (q.key === "agent_name" ? "小光" : ""));
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
      // 一题都不想答：用最小的默认值建档，进去以后随时可以「重新认识我」
      try {
        await api.onboard({
          agent_name: answers.agent_name || "小光", agent_avatar_id: answers.agent_avatar_id || "soft",
          intent_primary: answers.intent_primary || "还没想好", intent_why: answers.intent_why || "想先看看",
          care_style: answers.care_style || "analyze",
        });
        toast("先进去看看吧，想说的时候再说", "", "st-seed");
        window.dispatchEvent(new CustomEvent("xg:enter"));
      } catch (e) { toast(e.message, "err"); }
    },
  });
}
