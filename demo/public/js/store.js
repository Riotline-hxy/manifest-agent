// 前端共享状态。服务端的 bootstrap 是唯一事实来源：每个动作都用服务端
// 返回的状态整体替换，前端不自己算经验、不自己判断进化。

import { api } from "./api.js";
import { celebrate } from "./fx.js";

const listeners = new Set();

export const state = {
  ready: false,
  user: null,
  route: "chat",
  data: null,
  onboarding: null,
  composerDraft: "",
  articleId: "",
  reportDays: 14,
  ideaFilter: "全部",
  badgeFilter: "全部",
  spaceTab: "memory",
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit() {
  for (const fn of listeners) fn(state);
}

let prevQuests = null;

export function setData(data, { silent = false } = {}) {
  if (!data) return;
  const { user, onboarding, ...rest } = data;
  if (user) state.user = user;
  if (onboarding) state.onboarding = onboarding;
  state.data = { ...(state.data || {}), ...rest };
  const g = rest.growth;
  if (g) {
    // 一次性标记：服务端只会在真实发生时给一次
    if (g.evolved) celebrate("evolve", g.evolved, "evo:" + g.evolved.to);
    // 一次最多弹两枚；老账号升级后可能一下解锁很多，其余用一条提示带过
    const nb = g.badges_new || [];
    nb.slice(0, 2).forEach((b) => celebrate("badge", b, "badge:" + b.id));
    if (nb.length > 2) import("./ui.js").then((m) => m.toast(`另外还解锁了 ${nb.length - 2} 枚徽章，去成长页看看`, "", "st-chest-open"));
    if (prevQuests !== null && prevQuests < 4 && g.quests_done === 4) {
      celebrate("chest", {}, "chest:" + new Date().toDateString());
    }
    prevQuests = g.quests_done;
  }
  if (!silent) emit();
}

export async function refresh() {
  const data = await api.bootstrap();
  setData(data);
  return data;
}

export function go(route, opts = {}) {
  if (opts.id) state.articleId = opts.id;
  state.route = route;
  if (location.hash.slice(1) !== route) history.replaceState(null, "", `#${route}`);
  emit();
}

export function xpNote(xp) {
  if (!xp) return "";
  if (xp.amount) return `+${xp.amount} 经验`;
  if (xp.duplicate) return "这件事已经计过分了";
  if (xp.capped) return xp.note || "今天这一类已经满了";
  return "";
}
