// 「怎么算的」：经验、金币、每日任务、等级和解锁。数字全部来自后端的 growth.rules，和真正算的永远一致。
import { state } from "./store.js";
import { esc, sheet, h, icon } from "./ui.js";
import { COIN_SVG } from "./town.js";

const coin = (n) => `<span class="ru-c">+${n}${COIN_SVG}</span>`;

export function openRules() {
  const g = state.data?.growth;
  const R = g?.rules;
  if (!R) return;
  const dl = g.daily;
  const lv = g.level.lv;
  const body = h("div", { class: "rules", html: `
    <section><h4>${icon("gift")}每日任务 <small>今天最多 +${dl.max.xp} 经验 · +${dl.max.coins} 金币</small></h4>
      <p>每天 0 点换一批：一件固定，三件轮换。做到就自动发。</p>
      <div class="ru-list">${dl.tasks.map((t) => `<div class="ru-row ${t.done ? "on" : ""}"><span>${t.done ? icon("check") : ""}${esc(t.label)}</span><b>+${t.xp} 经验</b>${coin(t.coins)}</div>`).join("")}
        <div class="ru-row sum"><span>四件都做到</span><b>+${dl.bonus.xp} 经验</b>${coin(dl.bonus.coins)}</div></div>
      <p class="muted">偷懒日里行动类暂停，不影响全勤。愿望里的小步没有期限，不跟着刷新。</p></section>

    <section><h4>${icon("bolt")}经验</h4>
      <div class="ru-list">${R.xp.map((x) => `<div class="ru-row"><span>${esc(x.label)}<small>${esc(x.hint)}</small></span><b>+${x.each}</b><em>每天最多 ${x.cap}</em></div>`).join("")}</div>
      <p class="muted">每天最多 +${R.xp_cap}，每日任务另算。同一件事只算一次。</p></section>

    <section><h4>${COIN_SVG}金币</h4>
      <div class="ru-list">${R.coins.map((x) => `<div class="ru-row"><span>${esc(x.label)}</span>${coin(x.each)}<em>这类每天最多 ${x.cap}</em></div>`).join("")}</div>
      <p class="muted">第一次做成一件事送 ${R.first_gift}，够盖小木屋。聊天不给金币。挪位置、收进仓库不花钱。</p></section>

    <section><h4>${icon("sparkles")}等级 <small>你现在 Lv ${lv}</small></h4>
      <p>升一级要 ${R.level_base} + ${R.level_step}×(n−1) 经验。等级不会掉。</p>
      <div class="ru-levels">${R.levels.map((x) => `<span class="${g.total >= x.xp || lv >= x.lv ? "on" : ""}"><b>Lv ${x.lv}</b>${x.xp} 经验</span>`).join("")}</div></section>

    <section><h4>${icon("home")}解锁</h4>
      <div class="ru-list">${R.unlocks.map((u) => `<div class="ru-row ${lv >= u.lv ? "on" : ""}"><span><b class="ru-lv">Lv ${u.lv}</b>${esc([...u.items, ...(u.land ? [`${u.land}×${u.land} 的地`] : [])].join("、"))}</span></div>`).join("")}</div></section>` });
  const s = sheet({ title: "怎么算的", sticker: "list", body, footer: [h("button", { class: "btn btn-main", onclick: () => s.close() }, "知道了")] });
  s.panel.classList.add("rules-sheet");
}
