// 引导场景入口：点子、对话里小光提议、我的空间，都走这里。
import { api } from "./api.js";
import { setData, refresh } from "./store.js";
import { runLesson } from "./lesson.js";
import { toast } from "./ui.js";

// 有明确含义的选项配一个图标方块，其他用数字键
const CHIP_ICON = {
  "轻轻提醒我一下": ["letter", "var(--c-sky)"], "陪我一起找原因": ["compass", "var(--c-mint)"], "先别提，等我自己说": ["moon", "var(--c-violet)"],
  "早上": ["sun", "var(--c-lemon)"], "下午": ["sun", "var(--c-orange)"], "晚上": ["moon", "var(--c-violet)"], "不固定": ["steps", "var(--c-sky)"],
  "被看见、被说出来": ["star", "var(--c-lemon)"], "自己知道就好": ["lock", "var(--c-sky)"], "想听具体的观察，不想听夸奖": ["eye", "var(--c-mint)"],
  "做完了": ["check", "var(--c-mint)"], "还是它": ["flag", "var(--c-orange)"], "允许自己慢一点": ["moon", "var(--c-violet)"],
  "平静": ["wind", "var(--c-sky)"], "轻松": ["leaf", "var(--c-mint)"], "温暖": ["heart", "var(--c-pink)"], "踏实": ["steps", "var(--c-orange)"],
  "开阔": ["sun", "var(--c-lemon)"], "兴奋": ["sparkles", "var(--c-pink)"], "坚定": ["flag", "var(--c-orange)"], "温柔": ["heart", "var(--c-coral)"],
};

export function toStep(s, title) {
  return {
    ...s,
    opts: (s.chips || []).map((c) => ({ v: c, label: c, icon: CHIP_ICON[c]?.[0], tint: CHIP_ICON[c]?.[1] })),
    free: !!s.ph, optional: !!s.optional, title,
  };
}

export function startScene(sceneId, { onFinish } = {}) {
  let runId = null, title = "";
  runLesson({
    start: async () => {
      const out = await api.sceneStart(sceneId);
      runId = out.run?.id;
      title = out.scene.title;
      document.querySelector(".lesson-kicker").textContent = title;
      return toStep(out.step, title);
    },
    answer: async (v) => {
      const out = await api.sceneAnswer(runId, v ?? "（跳过）");
      return out.done ? out : { done: false, step: toStep(out.step, title) };
    },
    onDone: (out) => {
      if (out.state) setData(out.state); else refresh();
      onFinish?.(out);
    },
    onClose: async () => {
      try { await api.sceneCancel(); await refresh(); } catch {}
      toast("先停在这儿，随时可以再来");
    },
  });
}
