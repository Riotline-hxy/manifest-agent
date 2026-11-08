// 「许个愿」「让愿望落地」的问题和分支。界面和引擎在 tune.js（对话样子的全屏层，能上一步、能改前面的答案）；
// TA 自己的记录（ctx）、小光的建议、结尾和保存在后端 core/flows.py（wish_flow.py、relearn.py）。
// 每一题：type cards 插图卡片 / rows 文字卡片 / info 小光报一段记录 + 继续 / text 写一句（带例子）；
// custom 最后一张「我自己写」；skip:false 不能跳过；react 小光回一句；next 下一题（null 就是答完了）。
import { api } from "./api.js";
import { esc, icon } from "./ui.js";

// ---------------------------------------------------------------- 许个愿 ----
const AREAS = [
  { v: "body", label: "身体与作息", hint: "睡好、动起来", ill: "body", react: "身体顾好了，别的都会轻一点。" },
  { v: "study", label: "学习与成长", hint: "学得进去、做得完", ill: "study", react: "好，想在哪儿长出一点本事呢。" },
  { v: "people", label: "关系与表达", hint: "敢开口、多联系", ill: "people", react: "和人有关的愿望，最暖了。" },
  { v: "mood", label: "心情与内在", hint: "少点焦虑、多点轻松", ill: "mood", react: "好，先让心里舒服一点。" },
  { v: "life", label: "生活与自由", hint: "想过的日子", ill: "life", react: "想过的日子，我们好好想想。" },
];
const WANTS = {
  body: ["每天 12 点前睡", "每周运动三次", "好好吃早饭"], study: ["期末不挂科", "每天专心学一小时", "把论文写完"],
  people: ["敢在课上发言", "多和家人联系", "交到一个聊得来的朋友"], mood: ["少一点焦虑", "对自己温柔一点", "睡前不再想东想西"],
  life: ["存下一笔旅行基金", "学会做五道菜", "周末不再躺一整天"],
};
const DAYS = {
  body: ["早上不用闹钟也自然醒", "白天不再犯困", "镜子里的气色变好了"], study: ["打开书就能静下心", "轻轻松松走出考场", "做完一件事心里很踏实"],
  people: ["举手说话不再心跳加速", "和家里的电话变多了", "周末有人约我出去"], mood: ["晚上躺下很快就睡着", "事情多也不慌", "对自己说话温柔了"],
  life: ["订好了想去的旅行", "周末过得满满当当", "做的菜被朋友夸了"],
};
const FUTURE = ["谢谢你那时候开始了", "别急，你会走到的", "你比你以为的更有办法"];
const HEART = [
  { v: "still", label: "还是很想要", ill: "steadyfeel", react: "那就接着往前走。" },
  { v: "more", label: "更想要了", ill: "happy", react: "更想要了，真好。" },
  { v: "far", label: "有点远了", ill: "drift" },
  { v: "unsure", label: "说不清", ill: "calm", react: "说不清也没关系，愿望不用每天都清清楚楚。" },
];
const ONWARD = ["我已经在路上了", "慢一点也是在走", "想起来就再出发"];
const asRows = (list, icon) => list.map((t, i) => ({ v: "o" + i, label: t, icon }));

function wishFlow(ctx) {
  const W = ctx.wishes || [];
  const wish = (st) => W.find((w) => w.id === st.a.pick);
  const fresh = (w) => !w.steps && !w.checks && !w.moments;
  return {
    title: "许个愿",
    sub: "说出它，看见它，相信它",
    first: (st) => { if (W.length) return "pick"; st.a.pick = "new"; st.total = 4; return "area"; },
    total: 5,
    steps: {
      pick: { type: "cards", skip: false, q: "今天想许一个新愿，还是给已有的愿望再添点信心？",
        opts: () => [...W.map((w) => ({ v: w.id, label: w.title, hint: "给它添点信心", ill: "wish", react: "好，我们先看看它走到哪了。" })),
          { v: "new", label: "一个新的愿望", hint: ctx.full ? `愿望已经有 ${ctx.max} 个了` : "许一个新的", ill: "newwish", react: "好，许一个新的。" }],
        next: (st) => (st.a.pick === "new" ? "area" : "look") },
      // ---------- 新的愿望：哪一块 → 具体想要 → 那一天 → 未来的你说 ----------
      area: { type: "cards", q: "想让生活的哪一块变好？", opts: AREAS, custom: "比如：想更会照顾自己", next: "want" },
      want: { type: "text", q: "具体一点，你想要的是……", sub: "像已经在路上那样说就好。点一个也行。",
        chips: (st) => WANTS[st.a.area] || ["每天早点睡", "敢开口说话", "少一点焦虑"], ph: "写下你想要的", react: "好，我记下了。", next: "day" },
      day: { type: "rows", q: "如果它真的实现了，那一天会有什么不一样？",
        opts: (st) => asRows(DAYS[st.a.area] || ["早上醒来心情很好", "做完了一直想做的事", "身边的人说我变了"], "sparkles"),
        custom: "写下那一天的样子", react: () => "嗯，我好像也看见了。", next: "words" },
      words: { type: "rows", q: "到那时，你最想对现在的自己说什么？", opts: asRows(FUTURE, "quote"), custom: "写给现在的自己", next: null },
      // ---------- 已有的愿望：看看走过的路 → 最有感觉的一刻 → 现在心里 → 留一句话 ----------
      // 还没留下什么记录的愿望：不报一串 0，也不问「最有感觉的一刻」
      look: { type: "info", q: (st) => { const w = wish(st);
          return fresh(w) ? `「${esc(w.title)}」才开始 ${w.days} 天，还没留下什么记录。没关系，我们先看看现在的心情。` : `「${esc(w.title)}」已经走了 ${w.days} 天。`; },
        body: (st) => { const w = wish(st);
          if (fresh(w)) return "";
          return `<div class="stats"><span>做完 <b>${w.steps}</b> 个小步</span><span>打卡 <b>${w.checks}</b> 次</span><span>留下 <b>${w.moments}</b> 个瞬间</span></div>
            ${w.quote ? `<p class="quote">你写过：「${esc(w.quote)}」</p>` : ""}`; },
        next: (st) => { if (!wish(st).picks.length) { st.total = 4; return "heart"; } return "moment"; } },
      moment: { type: "rows", q: "这一路，最让你有感觉的是哪一刻？", opts: (st) => wish(st).picks.map((p, i) => ({ v: "m" + i, ...p })),
        custom: "写下那一刻", react: () => "这一刻，我也记得。", next: "heart" },
      heart: { type: "cards", q: "现在想起这个愿望，你心里……", opts: HEART,
        react: (v, st) => (v === "far" ? (wish(st).vision ? `远一点也没关系。你当初写下的样子是「${wish(st).vision}」，它还在那儿。` : "远一点也没关系，它还在那儿。")
          : HEART.find((h) => h.v === v)?.react || "嗯，我听到了。"), next: "onward" },
      onward: { type: "rows", q: "给接着往前走的自己，留一句话吧。", opts: asRows(ONWARD, "quote"), custom: "写给自己", next: null },
    },
    answers: (st) => ({ pick: st.a.pick, area: st.a.area || "", area_label: st.l.area || "", want: st.l.want || "", day: st.l.day || "",
      words: st.l.words || "", moment: st.l.moment || "", heart: st.a.heart || "", onward: st.l.onward || "" }),
    landWish: (st, saved) => saved?.wish_id || (st.a.pick !== "new" ? st.a.pick : ""),
  };
}

// ---------------------------------------------------------------- 让愿望落地 ----
const FEEL = [
  { v: "smooth", label: "挺顺的", hint: "照着做就行", ill: "sunrise", react: "顺的时候，最适合再往前一点点。" },
  { v: "stuck", label: "有点卡", hint: "有一件动不起来", ill: "stone", react: "卡住很正常，我们看看是哪一件。" },
  { v: "full", label: "太满了", hint: "顾了这头顾不上那头", ill: "busy", react: "那就先放下一点，留出喘气的地方。" },
  { v: "none", label: "顾不上", hint: "这周几乎没碰", ill: "battery", react: "没关系，这周我们只保一件。" },
];
const HOW = [
  { v: "small", label: "改小一点", hint: "小到一定做得到", ill: "pot1" },
  { v: "time", label: "换个时间", hint: "定个固定的时候", ill: "clock" },
  { v: "pause", label: "这周先停一停", hint: "不算放弃", ill: "night" },
];

const ADJ = { small: "改小一点", time: "换个时间", pause: "这周先停一停" };
const ADJ_ICON = { small: "sparkles", time: "clock", pause: "moon" };

function landFlow(ctx, run) {
  const W = ctx.wishes || [];
  const wish = (st) => W.find((w) => w.id === st.a.wish) || W[0];
  const items = (st) => wish(st).items || [];
  const item = (st) => items(st).find((x) => x.v === st.a.which) || (st.a.which === "custom" ? { v: "custom", kind: "other", label: st.l.which } : null);
  // 小光的建议：同一件事只问一次（上一步、改答案再回来，不重新等）
  const cache = new Map();
  const ask = (kind, st, ref = "", label = "", text = "") => {
    const k = [kind, wish(st).id, ref, label, text].join("|");
    if (!cache.has(k)) cache.set(k, api.flow("suggest", { run_id: run.id, kind, wish_id: wish(st).id, ref, label, text }).catch((e) => { cache.delete(k); throw e; }));
    return cache.get(k);
  };
  const plan = (st) => (items(st).length ? "feel" : "first");
  // 这周的感觉：TA 自己说的，按小光听出来的那种算
  const feel = (st) => (st.a.feel === "custom" ? st.a.feel_kind || "stuck" : st.a.feel);
  // 「我想这样调……」之后小光那句话（和建议一起回来）
  let adjustSay = "";
  const week = (st) => {
    const w = wish(st);
    const rows = items(st).map((p) => `<div class="rowc">${icon(p.kind === "habit" ? "check" : "flag")}<span><b>${esc(p.label)}</b><small>${esc(p.hint)}</small></span>${p.prog != null ? `<em class="prog"><i style="width:${Math.round(p.prog * 100)}%"></i></em>` : ""}</div>`).join("");
    const ms = w.ms ? `<p class="tb-note">下一个里程碑「${esc(w.ms.title)}」${w.ms.days == null ? "" : w.ms.days === 0 ? "就在今天" : `还有 ${w.ms.days} 天`}。</p>` : "";
    return `<div class="rowcs wk">${rows}</div>${ms}`;
  };
  return {
    title: "让愿望落地",
    sub: "这周怎么样，我们一起调一调",
    empty: !W.length,
    total: 3,
    // 进度点：前面有没有「想调哪个愿望」（base），后面按 TA 走的那条路算还剩几题
    first: (st) => {
      if (W.length === 1 || ctx.pick) { st.a.wish = ctx.pick || W[0].id; st.base = 0; st.total = items(st).length ? 3 : 1; return plan(st); }
      st.base = 1; st.total = 4;
      return "wish";
    },
    steps: {
      wish: { type: "rows", skip: false, q: "想调哪个愿望？",
        opts: W.map((w) => ({ v: w.id, label: w.title, icon: "flag",
          hint: w.items.length ? `${w.items.filter((x) => x.kind === "habit").length} 个习惯 · ${w.items.filter((x) => x.kind === "step").length} 个没做的小步` : "计划还是空的" })),
        react: () => "好，我们看看它。", next: (st) => { st.total = st.base + (items(st).length ? 3 : 1); return plan(st); } },
      // 计划还是空的：先定第一件事
      first: { type: "rows", skip: false, q: (st) => `「${esc(wish(st).title)}」的计划还是空的。先定第一件事？`, sub: "小到不用下决心就好。",
        opts: async (st) => [...(await ask("first", st)).opts.map((t, i) => ({ v: "o" + i, label: t, icon: "sparkles" })), { v: "none", label: "先不定了", icon: "close" }],
        custom: "我想先做……", next: null },
      feel: { type: "cards", q: (st) => `这周的「${esc(wish(st).title)}」，你觉得怎么样？`, body: week, opts: FEEL, custom: "说说你的感觉",
        // 自己说的感觉：小光先听懂是哪种、接一句，再按那种往下走
        react: (v, st, text) => (v === "custom"
          ? ask("feel", st, "", "", text).then((r) => { st.a.feel_kind = r.feel; return r.say; })
            .catch(() => { st.a.feel_kind = "stuck"; return "嗯，我听到了。我们看看是哪一件。"; })
          : FEEL.find((f) => f.v === v)?.react || ""),
        next: (st) => { const n = feel(st) === "smooth" ? "more" : "which"; st.total = st.base + 3; return n; } },
      which: { type: "rows", q: (st) => ({ full: "先放下哪一件？", none: "只留一件最想保住的，是哪件？" })[feel(st)] || "是哪一件？",
        opts: (st) => items(st).map((p) => ({ ...p, icon: p.kind === "habit" ? "check" : "flag" })), custom: "是别的事",
        react: (v, st) => (feel(st) === "none" ? "好，这周就保它。" : "好，我们看看它。"),
        next: (st) => { if (!st.a.which) return null; return feel(st) === "none" ? "small" : "how"; } },
      how: { type: "cards", q: "想怎么调它？", opts: HOW, custom: "我想这样调……",
        // 自己写的（「我不知道怎么启动」）：不照搬进计划，下一题小光先听懂卡在哪，再给两个对症的调整
        react: (v) => ({ small: "好，小到一定做得到。", time: "好，给它找个固定的时候。", pause: "好，停一停也是在照顾自己。" })[v] || "",
        next: (st) => { const n = ({ small: "small", time: "when", custom: "adjust" })[st.a.how] || null; st.total = st.base + (n ? 4 : 3); return n; } },
      adjust: { type: "rows", skip: false, q: () => esc(adjustSay), sub: "挑一个，或者说说你想怎么做。",
        opts: async (st) => {
          const it = item(st);
          const r = await ask("adjust", st, it.v === "custom" ? "" : it.v, it.v === "custom" ? it.label : "", st.l.how || "");
          adjustSay = r.say;
          return [...r.opts.map((o, i) => ({ v: `${o.kind}:${i}`, label: o.text, hint: ADJ[o.kind], icon: ADJ_ICON[o.kind] })),
            { v: "keep", label: "先不改了", icon: "close" }];
        },
        custom: "写下这周打算怎么做", next: null },
      small: { type: "rows", skip: false, q: "这样小一点，行吗？",
        opts: async (st) => {
          const it = item(st);
          const out = await ask("smaller", st, it.v === "custom" ? "" : it.v, it.v === "custom" ? it.label : "");
          return [...out.opts.map((t, i) => ({ v: "o" + i, label: t, icon: "sparkles" })),
            ...(out.ease ? [{ v: "ease", label: `频率降一档：${out.ease}`, icon: "clock" }] : []),
            { v: "keep", label: "不用改了", icon: "close" }];
        },
        custom: "我自己定", next: null },
      when: { type: "cards", q: (st) => (item(st)?.kind === "habit" ? "什么时候做它最顺？" : "哪天做它？"),
        sub: (st) => (item(st)?.kind === "habit" ? "挑一个每天都会经过的时刻。" : ""),
        opts: (st) => (item(st)?.kind === "habit" ? ctx.when.habit : ctx.when.step), custom: (st) => (item(st)?.kind === "habit" ? "比如：周六上午" : "比如：周三晚上"),
        next: null },
      more: { type: "cards", q: "那这周想……", opts: [{ v: "add", label: "再加一点", hint: "往前多走一步", ill: "pot2" },
        { v: "same", label: "保持现在就好", hint: "照着来", ill: "steady" }],
      react: (v) => (v === "same" ? "好，稳稳的也很好。" : ""), next: (st) => { st.total = st.base + (st.a.more === "add" ? 3 : 2); return st.a.more === "add" ? "add" : null; } },
      add: { type: "rows", skip: false, q: "加一件这周能做的？",
        opts: async (st) => [...(await ask("add", st)).opts.map((t, i) => ({ v: "o" + i, label: t, icon: "sparkles" })), { v: "none", label: "先不加了", icon: "close" }],
        custom: "我想加……", next: null },
    },
    answers: (st) => {
      const out = { wish: wish(st).id };
      for (const k of ["feel", "which", "how", "small", "when", "more", "add", "first", "adjust"]) { out[k] = st.a[k] || ""; out[k + "_label"] = st.l[k] || ""; }
      out.feel_kind = st.a.feel_kind || "";
      out.adjust_kind = (st.a.adjust || "").includes(":") ? st.a.adjust.split(":")[0] : "";
      return out;
    },
  };
}

export const FLOWS = { seven_steps_lite: wishFlow, relearn: landFlow };
