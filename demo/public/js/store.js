// 前端共享状态。服务端的 bootstrap 是唯一事实来源：每个动作都用服务端
// 返回的状态整体替换，前端不自己算经验和金币、不自己判断升级。

import { api } from "./api.js";
import { celebrate } from "./fx.js";
import { toast } from "./ui.js";
import { setKinds } from "./town.js";

const listeners = new Set();

// TA 给陪伴者起的名字，没起就是「小光」。界面上所有提到它的地方都用这个。
// 名字是 TA 自己写的，最多 8 个字；去掉 HTML 里有特殊意义的几个字符，放进模板里就不用再转义。
export const aname = () => String(state.data?.profile?.agent_name || "").replace(/[<>&"'`]/g, "").trim() || "小光";

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
  spaceTab: "settings",
  planRange: 30,
  planListOpen: false,
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit() {
  for (const fn of listeners) fn(state);
}

export function setData(data, { silent = false } = {}) {
  if (!data) return;
  const { user, onboarding, ...rest } = data;
  if (user) state.user = user;
  if (onboarding) state.onboarding = onboarding;
  state.data = { ...(state.data || {}), ...rest };
  if (rest.town?.kinds) setKinds(rest.town.kinds);   // 画地上的东西要用（占地、高度）
  // 一次性标记：服务端只会在真的升级时给一次
  const lv = rest.growth?.level_up;
  if (lv) celebrate("level", lv, "lv:" + lv.to);
  // 这一笔顺带完成了每日任务 / 拿到第一份建材 / 收到纪念碑：轻轻说一声
  const x = rest.xp;
  if (x?.first_gift) toast(`第一份建材到了：+${x.first_gift} 金币，去小镇盖第一栋小木屋吧`, "", "home");
  else if (x?.daily?.length) toast(x.daily.map((t) => (t.id === "all" ? "每日任务四件都做到了" : `每日任务：${t.label}`) + ` +${t.xp} 经验 +${t.coins} 金币`).join("；"), "", "gift");
  // 一个愿望的小步都做完了：等勾选的动画走完，弹一张「这一段走完了」
  const c = rest.cleared;
  if (c) setTimeout(() => celebrate("cleared", { ...c, onNext: () => { state.autoSend = `「${c.title}」的小步都做完了。帮我想想接下来可以做的两三个小步吧，先问问我现在的情况。`; go("chat"); } },
    `clr:${c.wish_id}:${c.done}`), 350);
  if (x?.gift) setTimeout(() => toast(`小镇送来一块纪念碑，刻着「${x.gift.note}」，在仓库里`, "", "home"), 700);
  if (!silent) emit();
}

export async function refresh() {
  const data = await api.bootstrap();
  setData(data);
  return data;
}

export function go(route, opts = {}) {
  route = { goodnews: "moments", growth: "town" }[route] || route;   // 旧名字：好消息换成了瞬间
  if (opts.id) state.articleId = opts.id;
  state.route = route;
  if (location.hash.slice(1) !== route) history.replaceState(null, "", `#${route}`);
  emit();
}

export function xpNote(xp) {
  if (!xp) return "";
  const n = xp.amount_total ?? xp.amount;
  const got = [n ? `+${n} 经验` : "", xp.coins > 0 ? `+${xp.coins} 金币` : ""].filter(Boolean);
  if (got.length) return got.join(" · ");
  if (xp.duplicate) return "这件事已经计过分了";
  if (xp.capped) return xp.note || "今天这一类已经满了";
  return "";
}
