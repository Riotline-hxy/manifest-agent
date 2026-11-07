// 引导场景入口：点子、对话里小光提议、我的空间，都走这里。
import { api } from "./api.js";
import { state, setData, refresh, go } from "./store.js";
import { runLesson } from "./lesson.js";
import { music } from "./music.js";
import { toast } from "./ui.js";
import { openTune } from "./tune.js";

// 有明确含义的选项配一个图标方块，其他用数字键（「聊聊」两个练习和冥想只用数字键 + 文字）
const CHIP_ICON = {
  "做完了": ["check", "var(--c-mint)"],
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
  if (sceneId === "relearn") return openTune();     // 聊聊现在的你：对话样子的一页（tune.js）
  let runId = null, title = "";
  // 背景音乐要在点击的这一下就开始放（手机浏览器的规矩），所以不等接口返回
  const src = (state.data?.scenes || []).find((s) => s.id === sceneId)?.music;
  runLesson({
    music: src ? music(src) : null,
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
      return out.done ? out : { done: false, reply: out.reply, glow: out.glow, step: toStep(out.step, title) };
    },
    // 结束页：勾选的才存；「返回对话」就丢掉这次的回答。冥想：talk = 「我想和你聊聊」
    review: {
      save: (items, extra, talk = false) => api.sceneSave(runId, items, extra, talk),
      back: () => api.sceneDiscard(runId).catch(() => {}),
    },
    onDone: (out) => {
      if (out.state) setData(out.state); else refresh();
      onFinish?.(out);
      if (out.review && !out.stay) go("chat");     // 冥想「先不记录」「保存感受」留在原来的页面
    },
    onClose: async () => {
      try { await api.sceneCancel(); await refresh(); } catch {}
      toast("先停在这儿，随时可以再来");
    },
  });
}
