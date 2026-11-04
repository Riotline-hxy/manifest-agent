// 引导场景入口：点子、对话里小光提议、我的空间，都走这里。
import { api } from "./api.js";
import { setData, refresh, go } from "./store.js";
import { runLesson } from "./lesson.js";
import { toast } from "./ui.js";

// 有明确含义的选项配一个图标方块，其他用数字键（「聊聊你的愿望」「聊聊现在的你」只用数字键 + 文字）
const CHIP_ICON = {
  "做完了": ["check", "var(--c-mint)"],
  "平静": ["wind", "var(--c-sky)"], "轻松": ["leaf", "var(--c-mint)"], "温暖": ["heart", "var(--c-pink)"], "踏实": ["steps", "var(--c-orange)"],
  "开阔": ["sun", "var(--c-lemon)"],
};

export function toStep(s, title) {
  const plain = !!s.plain;
  return {
    ...s,
    opts: (s.chips || []).map((c) => ({ v: c, label: c, ask: s.ask?.[c] || "", icon: plain ? "" : CHIP_ICON[c]?.[0], tint: plain ? "" : CHIP_ICON[c]?.[1] })),
    free: !!s.ph, optional: !!s.optional, maxPick: s.max || 3, title,
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
      if (out.done && out.review && out.state) setData(out.state);   // 经验、金币先到账；聊到的内容等用户勾了再存
      return out.done ? out : { done: false, reply: out.reply, step: toStep(out.step, title) };
    },
    // 结束页：勾选的才存；「返回对话」就丢掉这次的回答
    review: {
      save: (items, extra) => api.sceneSave(runId, items, extra),
      back: () => api.sceneDiscard(runId).catch(() => {}),
    },
    onDone: (out) => {
      if (out.state) setData(out.state); else refresh();
      onFinish?.(out);
      if (out.review) go("chat");
    },
    onClose: async () => {
      try { await api.sceneCancel(); await refresh(); } catch {}
      toast("先停在这儿，随时可以再来");
    },
  });
}
