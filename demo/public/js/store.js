// 前端共享状态。服务端返回的 bootstrap 就是唯一事实来源；
// 每个动作都用服务端返回的新状态整体替换，避免前后端各算一套。

import { api } from "./api.js";

const listeners = new Set();

export const state = {
  ready: false,
  user: null,
  me: null,
  route: "chat",
  data: null,
  busy: false,
  theme: localStorage.getItem("xg-theme") || "paper",
  railCollapsed: localStorage.getItem("xg-rail") === "1",
  composerDraft: "",
  articleId: "",
  reportDays: 14,
  sceneStep: null,
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit() {
  for (const fn of listeners) fn(state);
}

export function setData(data) {
  if (!data) return;
  // bootstrap 与增量接口结构一致；用户信息另存
  const { user, onboarding, ...rest } = data;
  if (user) state.user = user;
  if (onboarding) state.onboarding = onboarding;
  state.data = { ...(state.data || {}), ...rest };
  emit();
}

export async function refresh() {
  const data = await api.bootstrap();
  setData(data);
  return data;
}

export function setTheme(t) {
  state.theme = t;
  localStorage.setItem("xg-theme", t);
  document.documentElement.dataset.theme = t === "dusk" ? "dusk" : "paper";
  emit();
}

export function go(route, opts = {}) {
  if (route === "article") {
    state.articleId = opts.id || state.articleId;
  }
  state.route = route;
  if (location.hash.slice(1) !== route) history.replaceState(null, "", `#${route}`);
  emit();
}

// 完成动作后的统一收尾：用返回状态替换 + 轻提示
export function applyResult(data, msg) {
  setData(data);
  if (msg) import("./ui.js").then((m) => m.toast(msg));
}

export function xpNote(xp) {
  if (!xp) return "";
  if (xp.amount) return `+${xp.amount} 经验`;
  if (xp.duplicate) return "这件事已经计过分了";
  if (xp.capped) return xp.note || "今天这一类已经满了";
  return "";
}
