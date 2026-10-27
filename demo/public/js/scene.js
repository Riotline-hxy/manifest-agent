// 引导场景的入口：任何地方（点子、对话里小光提议、我的空间）都走这里。
import { api } from "./api.js";
import { setData, refresh } from "./store.js";
import { runLesson } from "./lesson.js";
import { toast } from "./ui.js";

// 选项配贴纸：只给有明确含义的选项配，其他用数字键
const CHIP_ART = {
  "轻轻提醒我一下": "st-letter", "陪我一起找原因": "st-compass", "先别提，等我自己说": "st-moon",
  "早上": "st-seed", "下午": "plant-tree", "晚上": "st-moon", "不固定": "st-steps",
  "被看见、被说出来": "st-jar", "自己知道就好": "st-mirror", "想听具体的观察，不想听夸奖": "st-book",
  "做完了": "st-lotus", "平静": "st-lotus", "轻松": "st-seed", "温暖": "st-letter", "踏实": "plant-bush",
  "开阔": "plant-glow", "兴奋": "st-chest-open", "坚定": "st-flag", "温柔": "plant-tulip",
  "还是它": "st-flag", "允许自己慢一点": "st-moon",
};

export function toStep(s, title) {
  return {
    ...s,
    opts: (s.chips || []).map((c) => ({ v: c, label: c, art: CHIP_ART[c] })),
    free: !!s.ph,
    optional: !!s.optional,
    title,
  };
}

export function startScene(sceneId, { onFinish } = {}) {
  let runId = null;
  let title = "";
  runLesson({
    kicker: "",
    start: async () => {
      const out = await api.sceneStart(sceneId);
      runId = out.run?.id;
      title = out.scene.title;
      document.querySelector(".lesson-kicker").textContent = title;
      return toStep(out.step, title);
    },
    answer: async (v) => {
      const out = await api.sceneAnswer(runId, v ?? "（跳过）");
      if (out.done) return out;
      return { done: false, step: toStep(out.step, title) };
    },
    onDone: (out) => {
      if (out.state) setData(out.state);
      else refresh();
      onFinish?.(out);
    },
    onClose: async () => {
      try { await api.sceneCancel(); await refresh(); } catch {}
      toast("先停在这儿，随时可以再来", "", "st-moon");
    },
  });
}
