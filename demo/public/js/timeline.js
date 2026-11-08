// 时间线（小光面板的「动态」、我的空间的「时间线」共用）：一条竖线把一天从早串到晚。
// 小事是线上的一个点；大一点的事（盖了房子、到达里程碑、开始一段旅程、做完练习、每日任务全做到）是挂在线上的卡片；
// 今天的最后有一个亮着的「现在」，之后还没到的例行任务画在虚线上。
import { esc, icon, tile, fmtDay } from "./ui.js";

const KIND = {
  plan: ["flag", "var(--c-orange)"], step: ["flag", "var(--c-orange)"], record: ["moon", "var(--c-violet)"],
  memory: ["memory", "var(--c-violet)"], scene: ["wind", "var(--c-mint)"], onboarding: ["compass", "var(--c-sky)"],
  profile: ["settings", "var(--c-sky)"], proactive: ["letter", "var(--c-sky)"], rest: ["moon", "var(--c-violet)"],
  task: ["clock", "var(--c-sky)"], journey: ["camera", "var(--c-pink)"], town: ["home", "var(--c-mint)"], daily: ["gift", "var(--c-lemon)"],
};
const WEEK = "日一二三四五六";
const big = (a) => ["town", "scene", "daily"].includes(a.kind) || /^(到达|开启了一段旅程|和小光一起规划)/.test(a.text || "");
const hm = (iso) => (iso || "").slice(11, 16);
const weekday = (day) => "周" + WEEK[new Date(day + "T12:00:00").getDay()];

function row(a, i) {
  const [ic, col] = KIND[a.kind] || ["checkc", "var(--accent)"];
  if (!big(a)) {
    return `<li class="tl-it" style="--c:${col};--i:${i}"><i class="tl-dot"></i><time>${hm(a.at)}</time><span class="tl-t">${esc(a.text)}</span></li>`;
  }
  const [head, ...rest] = (a.text || "").split("：");
  const title = rest.join("：") || head, sub = rest.length ? head : "";
  return `<li class="tl-it big" style="--c:${col};--i:${i}"><i class="tl-dot"></i><time>${hm(a.at)}</time>
    <div class="tl-card">${tile(ic, col, 32)}<div><b>${esc(title)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div></div></li>`;
}

/**
 * acts：bootstrap 的 activity（新的在前）；sums：growth.day_totals；tasks：例行任务（画今天还没到的那几个）；
 * today：服务端的「今天」；now：现在的 ISO 时间（和 activity 同一时区）
 */
// 连着的同一类事（同一天、同一种、同样的开头）合成一条：「在小镇建了一座小木屋」×3 → 「在小镇建了 3 座：小木屋、面包房、松树」
const PREFIX = [[/^在小镇建了一座(.+)$/, "在小镇建了", "座"], [/^(.+?)：(.+)$/, null, "个"]];
function split(a) {
  for (const [re, fixed, unit] of PREFIX) {
    const m = (a.text || "").match(re);
    if (m) return fixed ? { head: fixed, obj: m[1], unit } : { head: m[1], obj: m[2], unit };
  }
  return { head: a.text || "", obj: "", unit: "次" };
}
function merge(items) {   // items：同一天，从早到晚
  const out = [];
  for (const a of items) {
    const prev = out[out.length - 1], s = split(a);
    if (prev && prev.kind === a.kind && prev._head === s.head) {
      prev._objs.push(s.obj);
      prev._n++;
      continue;
    }
    out.push({ ...a, _head: s.head, _objs: [s.obj], _unit: s.unit, _n: 1 });
  }
  return out.map((a) => {
    if (a._n < 2) return a;
    const objs = [...new Set(a._objs.filter(Boolean))];
    return { ...a, text: objs.length ? `${a._head} ${a._n} ${a._unit}：${objs.join("、")}` : `${a._head}（${a._n} 次）` };
  });
}

export function timelineHTML(acts, { sums = {}, tasks = [], today = "", now = "", limit = 40 } = {}) {
  const days = [];
  for (const a of (acts || []).filter((x) => x.kind !== "growth").slice(0, limit)) {   // growth 是旧的宠物分化记录
    const day = (a.at || "").slice(0, 10);
    (days.find((x) => x.day === day) || days[days.push({ day, items: [] }) - 1]).items.push(a);
  }
  const later = (tasks || []).filter((t) => t.enabled && (t.run_at || "").slice(0, 10) === today && t.run_at > now)
    .sort((a, b) => a.run_at.localeCompare(b.run_at)).slice(0, 4);
  if (today && (!days.length || days[0].day !== today) && later.length) days.unshift({ day: today, items: [] });
  if (!days.length) return `<div class="empty sm"><p>还没有动静。</p></div>`;
  return days.map((d) => {
    const s = sums[d.day];
    const isToday = d.day === today;
    const items = merge([...d.items].reverse());   // 一天之内从早到晚
    return `<section class="tl-day ${isToday ? "today" : ""}">
      <header class="tl-dh"><b>${esc(isToday ? "今天" : fmtDay(d.items[0]?.at || d.day))}</b><span>${+d.day.slice(5, 7)}月${+d.day.slice(8, 10)}日 ${weekday(d.day)}</span>
        ${s && (s.xp || s.coins) ? `<em>${s.xp ? `+${s.xp} 经验` : ""}${s.xp && s.coins ? " · " : ""}${s.coins ? `+${s.coins} 金币` : ""}</em>` : ""}</header>
      <ol class="tl-list">
        ${items.map(row).join("")}
        ${isToday ? `<li class="tl-it now"><i class="tl-dot"></i><time>${hm(now) || "现在"}</time><span class="tl-t">现在</span></li>
          ${later.map((t) => `<li class="tl-it later"><i class="tl-dot"></i><time>${hm(t.run_at)}</time><span class="tl-t">${esc(t.title)}<small>${icon("clock")}例行任务</small></span></li>`).join("")}` : ""}
      </ol></section>`;
  }).join("");
}

// 服务端时区的「现在」（activity 的 at 也是这个时区，直接比字符串）
export function nowIso() {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
