// 「显化你的愿望」「调整现有计划」的问题。界面和引擎在 tune.js（对话样子的全屏层，能上一步、能改前面的答案）；
// TA 自己的记录（ctx）、每一步小光的话、结尾和保存在后端 core/flows.py（manifest_flow.py、relearn.py）。
// 每一题：type cards 插图卡片 / rows 文字卡片 / text 写一句（带例子）；custom 最后一张「我自己写」；skip:false 不能跳过；
// react 小光回一句（可以是调模型的 Promise；纯文字会被转义，以 < 开头的当作已经转义好的 HTML）；next 下一题（null 就是答完了）；stage 顶栏小字；dot 进度点亮到第几个。
import { api } from "./api.js";
import { esc, icon } from "./ui.js";

const rows = (list, icon_) => (list || []).map((t, i) => ({ v: "o" + i, label: t, icon: icon_ }));
const cards = (obj, ills, extra = {}) => Object.entries(obj || {}).map(([v, s]) => {
  const [label, hint] = String(s).replace("）", "").split("（");
  return { v, label, hint: hint || "", ill: ills[v], react: extra[v] };
});
const bubbles = (...parts) => parts.filter(Boolean).map((p) => (p.startsWith("<") ? p : `<div class="bub">${p}</div>`)).join("");

// ---------------------------------------------------------------- 显化你的愿望 ----
const STAGES = ["清晰愿景", "消除怀疑", "调整行为", "克服考验", "无条件感恩", "嫉妒变动力", "信任"];
const FEEL_ILL = { light: "light", proud: "proud", calm: "calm", steadyfeel: "steadyfeel", happy: "happy" };
const DOUBT_ILL = { worth: "rain", able: "stone", late: "hourglass", others: "eyes", none: "sunrise" };
const TEST_ILL = { settle: "fork", old: "drift", cold: "rain", none: "sunrise" };
const ENVY_ILL = { sour: "rain", admire: "light", learn: "study", none: "calm" };
const TRUST_ILL = { rush: "hourglass", fear: "rain", calm: "calm" };
const THANKS = ["我必须早起", "我必须每天上课或上班", "家人一直在支持我"];

function manifestFlow(ctx, run) {
  const W = ctx.wishes || [];
  const old = (st) => st.a.pick && st.a.pick !== "new";
  const wish = (st) => W.find((w) => w.id === st.a.pick);
  const stage = (n) => () => `显化第 ${n} 步 · ${STAGES[n - 1]}`;
  const dot = (n) => (st) => Math.max(0, n - (old(st) ? 2 : 1));
  const R = (st) => (st.r ||= {});
  // 每一步答完调一次模型：同样的答案只问一次（上一步、改答案再回来，不重新等）
  const cache = new Map();
  const call = (kind, st) => {
    const answers = flow.answers(st);
    const k = kind + "|" + JSON.stringify(answers);
    if (!cache.has(k)) cache.set(k, api.flow("step", { run_id: run.id, kind, answers }).catch((e) => { cache.delete(k); throw e; }));
    return cache.get(k);
  };
  // 模型没连上：这一步也能接着走
  const soft = (p, fallback) => p.catch(() => fallback);

  const flow = {
    title: "显化你的愿望",
    sub: "说清它，相信它，走向它",
    endSub: "都走完了",
    total: 7,
    first: (st) => { if (W.length) return "pick"; st.a.pick = "new"; return "want"; },
    steps: {
      pick: { type: "cards", skip: false, q: "今天想显化哪个愿望？", sub: "新的愿望完整走七步；已有的愿望从第 2 步开始，让信念更坚定。",
        opts: () => [...W.map((w) => ({ v: w.id, label: w.title, hint: "让信念更坚定 · 6 步", ill: "wish", react: "好，我们一起把它再看清楚一点。" })),
          { v: "new", label: "一个新的愿望", hint: ctx.full ? `愿望已经有 ${ctx.max} 个了` : "完整走一遍 · 7 步", ill: "newwish", react: "好，从说清它开始。" }],
        next: (st) => { st.total = old(st) ? 6 : 7; return old(st) ? "doubt" : "want"; } },

      // ---------- 1 清晰愿景（新的愿望才有）----------
      want: { type: "text", stage: stage(1), dot: dot(1), q: "你想要什么？先随口说一句就好。", sub: "下一步我们一起把它说具体。",
        chips: ["换一份喜欢的工作", "每天睡个好觉", "敢在人前表达自己"], ph: "写下你想要的",
        react: (v, st) => soft(call("spec", st).then((r) => { R(st).spec = r; return r.say; }), "好，我们把它说具体一点。"), next: "spec" },
      spec: { type: "rows", stage: stage(1), dot: dot(1), q: "越具体，越有力量。说具体一点，可能是这样：", sub: "挑一个，或者自己写。",
        opts: (st) => rows(R(st).spec?.opts, "sparkles"), custom: "写下更具体的样子", react: () => "好，就是它。", next: "feel" },
      feel: { type: "cards", stage: stage(1), dot: dot(1), q: "现在闭上眼，想象它已经实现了。那一刻，你感觉……",
        opts: cards(ctx.feels, FEEL_ILL), custom: "说说那种感觉",
        react: (v, st) => soft(call("vision", st).then((r) => {
          R(st).vision = r;
          return r.vision ? bubbles("那一刻，大概是这样：", `<p class="quote">${esc(r.vision)}</p>`, esc(r.say)) : r.say;
        }), "这个画面，记在心里。"), next: "doubt" },

      // ---------- 2 消除怀疑 ----------
      doubt: { type: "cards", stage: stage(2), dot: dot(2),
        q: (st) => (old(st) ? `「${esc(wish(st).title)}」，想到它，心里有没有一个声音说「我做不到」？` : "想到它，心里有没有一个声音说「我做不到」？"),
        body: (st) => (old(st) && wish(st).vision ? `<p class="quote">你当初写下的样子：${esc(wish(st).vision)}</p>` : ""),
        opts: cards(ctx.doubts, DOUBT_ILL), custom: "说说那个声音",
        react: (v, st) => soft(call("doubt", st).then((r) => { R(st).doubt = r; return r.say; }), "这个声音很多人都有，先让它待在那儿。"), next: "aff" },
      aff: { type: "rows", stage: stage(2), dot: dot(2), q: "挑一句，以后对自己说：", sub: "小声念一遍试试。",
        opts: (st) => rows(R(st).doubt?.opts, "quote"), custom: "写一句自己的", react: () => "嗯，记住这句。", next: "act" },

      // ---------- 3 调整行为 ----------
      act: { type: "rows", stage: stage(3), dot: dot(3), q: "如果你已经是实现了它的人，今天会做一件什么事？", sub: "显化不是许愿，是行动。",
        opts: async (st) => rows((await soft(call("act", st), { opts: [] })).opts, "flag"), custom: "写下今天要做的事",
        react: (v, st) => soft(call("act_say", st).then((r) => r.say), "好，今天就去做。"), next: "test" },

      // ---------- 4 克服考验 ----------
      test: { type: "cards", stage: stage(4), dot: dot(4), q: "往前走的时候，总有想将就、想退回去的时候。最近有吗？",
        opts: cards(ctx.tests, TEST_ILL), custom: "说说是什么",
        react: (v, st) => soft(call("test", st).then((r) => { R(st).test = r; return r.say; }), "想退回去的时候，人人都有。"), next: "plan" },
      plan: { type: "rows", stage: stage(4), dot: dot(4), q: "下次它再出现，你打算……",
        opts: (st) => rows(R(st).test?.opts, "check"), custom: "写下你的打算", react: () => "好，到时候你会想起来的。", next: "thanks" },

      // ---------- 5 无条件感恩 ----------
      thanks: { type: "text", stage: stage(5), dot: dot(5), q: "对现在的生活，有什么让你觉得有幸？",
        sub: "也可以写一句「我必须……」，我们把它换成「我有幸能……」。", chips: THANKS, ph: "写一句",
        react: (v, st) => soft(call("thanks", st).then((r) => {
          R(st).thanks = r;
          return r.line ? bubbles(`<p class="quote">${esc(r.line)}</p>`, esc(r.say)) : r.say;
        }), "这样换个说法，心里会轻一点。"), next: "envy" },

      // ---------- 6 嫉妒变动力 ----------
      envy: { type: "cards", stage: stage(6), dot: dot(6), q: "有没有谁，已经活成了你想要的样子？看到 TA，你心里……",
        opts: cards(ctx.envy, ENVY_ILL), custom: "说说你的感觉",
        react: (v, st) => soft(call("envy", st).then((r) => {
          R(st).envy = r;
          return bubbles(esc(r.say), r.learn ? `<p class="tb-note">${icon("sparkles")}可以学的：${esc(r.learn)}</p>` : "");
        }), "这份感觉在告诉你，你真正想要什么。"), next: "trust" },

      // ---------- 7 信任 ----------
      trust: { type: "cards", stage: stage(7), dot: dot(7), q: "最后一步。想到它什么时候会来，你心里……",
        opts: cards(ctx.trust, TRUST_ILL), custom: "说说你的感觉",
        react: (v, st) => soft(call("trust", st).then((r) => { R(st).trust = r; return r.say; }), "今天能做的你会去做，剩下的交给时间。"), next: "letgo" },
      letgo: { type: "rows", stage: stage(7), dot: dot(7), q: "该做的你会去做，剩下的交给时间。挑一句，心急的时候对自己说：",
        opts: (st) => rows(R(st).trust?.opts, "quote"), custom: "写一句自己的", next: null },
    },
    answers: (st) => {
      const r = st.r || {};
      return { pick: st.a.pick || "new", want: st.l.want || "", spec: st.l.spec || "", vision: r.vision?.vision || "", feel: st.l.feel || "",
        doubt: st.l.doubt || "", aff: st.l.aff || "", act: st.l.act || "", test: st.l.test || "", plan: st.l.plan || "",
        thanks: st.l.thanks || "", thanks_line: r.thanks?.line || "", envy: st.l.envy || "", learn: r.envy?.learn || "",
        trust: st.l.trust || "", letgo: st.l.letgo || "" };
    },
  };
  return flow;
}

// ---------------------------------------------------------------- 调整现有计划 ----
const STATE_ILL = { busy: "busy", steady: "steady", change: "change", slow: "slow" };
const ENERGY_ILL = { seed: "pot1", sprout: "pot2", more: "pot3" };
const FEEL_PLAN_ILL = { smooth: "sunrise", stuck: "stone", full: "busy", none: "battery" };

function adjustFlow(ctx) {
  const W = ctx.wishes || [];
  // 第三题上面先放现在的计划：每个愿望下的习惯（本周进度）、没做的小步、里程碑
  const week = () => W.map((w) => {
    const items = w.items.length ? w.items : [{ kind: "", title: "计划还是空的", hint: "" }];
    return `<div class="rowcs wk"><p class="wk-h">${esc(w.title)}</p>${items.map((p) => `<div class="rowc">${icon(p.kind === "habit" ? "check" : p.kind === "ms" ? "star" : "flag")}
      <span><b>${esc(p.title)}</b>${p.hint ? `<small>${esc(p.hint)}</small>` : ""}</span>${p.prog != null ? `<em class="prog"><i style="width:${Math.round(p.prog * 100)}%"></i></em>` : ""}</div>`).join("")}</div>`;
  }).join("");
  return {
    title: "调整现有计划",
    sub: "说说现在的你，我帮你把计划调顺",
    endSub: "这是给你的调整方案",
    empty: !W.length,
    total: 3,
    first: () => "state",
    steps: {
      state: { type: "cards", q: "最近的你，更像哪一种？", custom: "说说最近的你",
        opts: cards(ctx.state, STATE_ILL, { busy: "最近事情不少呀。", steady: "有自己的节奏，挺好。", change: "变化的时候，计划也该跟着变一变。", slow: "好，那我们不着急。" }),
        customReact: "嗯，我听到了。", next: "energy" },
      energy: { type: "cards", q: "现在，你能拿出多少劲？", custom: "说说你的劲头",
        opts: cards(ctx.energy, ENERGY_ILL, { seed: "好，那每件事都要小到两分钟做得完。", sprout: "好，每天一小会，刚刚好。", more: "好，那可以多安排一点。" }),
        customReact: "好，我记下了。", next: "feel" },
      feel: { type: "cards", q: "这阵子的计划，做起来怎么样？", body: week, opts: cards(ctx.feel, FEEL_PLAN_ILL), custom: "说说哪里不顺", next: null },
    },
    answers: (st) => {
      const out = {};
      for (const k of ["state", "energy", "feel"]) { out[k] = st.a[k] || ""; out[k + "_label"] = st.l[k] || ""; }
      return out;
    },
  };
}

export const FLOWS = { seven_steps_lite: manifestFlow, relearn: adjustFlow };
