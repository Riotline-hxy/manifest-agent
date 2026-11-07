// 「聊聊现在的你」两个原型共用：四个问题、插图、小光的样子。离线可开（不用 import）。
// 定位：简单告诉小光我现在的状态 → 想看到一点进步 → 小光给出今天就能开始的第一小步，带我一起变好。
(function () {
  const q = new URLSearchParams(location.search);
  document.documentElement.dataset.theme = q.get("theme") || "mist";

  window.icon = (name) => `<svg class="ic-svg" viewBox="0 0 24 24" aria-hidden="true">${(window.ICONS || {})[name] || ""}</svg>`;
  window.tile = (name, color, size = 40) => `<span class="tile" style="--tile:${color};width:${size}px;height:${size}px">${icon(name)}</span>`;
  window.esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // 小光：原型里用简化的云朵画法（正式版用 App 里的果冻形象）。mood: idle | happy
  window.mascot = (mood = "idle") => {
    const eyes = mood === "happy"
      ? `<path d="M45 61q5-6 10 0M67 61q5-6 10 0" fill="none" stroke="#2a2433" stroke-width="3.2" stroke-linecap="round"/>`
      : `<ellipse cx="50" cy="61" rx="4" ry="5.6" fill="#2a2433"/><ellipse cx="72" cy="61" rx="4" ry="5.6" fill="#2a2433"/>
         <circle cx="51.6" cy="58.6" r="1.4" fill="#fff"/><circle cx="73.6" cy="58.6" r="1.4" fill="#fff"/>`;
    return `<svg class="xg-svg ${mood}" viewBox="0 0 122 112" aria-hidden="true">
      <defs><radialGradient id="xgf" cx="38%" cy="28%" r="85%"><stop offset="0" stop-color="#ffffff"/><stop offset=".62" stop-color="#eff0fb"/><stop offset="1" stop-color="#cfd3ef"/></radialGradient></defs>
      <ellipse cx="61" cy="104" rx="34" ry="5" fill="rgba(40,30,80,.13)"/>
      <path d="M30 92C13 92 6 75 17 64C8 49 23 33 39 40C43 23 66 16 77 31C92 22 109 36 102 53C116 60 111 91 92 92Z" fill="url(#xgf)"/>
      <path d="M36 44c4-6 11-8 17-6" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity=".9"/>
      ${eyes}<path d="M58 70q3 2.5 6 0" fill="none" stroke="#2a2433" stroke-width="2.4" stroke-linecap="round"/>
      <ellipse cx="42" cy="70" rx="5" ry="3" fill="#ffb3c7" opacity=".55"/><ellipse cx="80" cy="70" rx="5" ry="3" fill="#ffb3c7" opacity=".55"/>
    </svg>`;
  };

  // 插图：柔和的扁平小画，颜色跟着主题（.f1 .f2 .fp .fm .fl .fs 填色，.s .s2 线条，见 tune.css）
  const BASE = `<rect class="f2" x="16" y="49" width="64" height="7" rx="3.5"/>`;
  const ILL = {
    // 最近的状态：节奏线（吸收同事版本的画法）
    busy: `<path class="s2" d="M6 28c10 14 14 16 22 0s12-14 18 4 10 14 18-2 10-12 26 2"/><path class="s" d="M6 38c8-18 14-18 20 0s12 16 18-2 10-18 18 0 12 14 28-6"/>`,
    steady: `<path class="s2 dash" d="M6 44h84"/><path class="s" d="M6 32c14-9 28-9 42 0s28 9 42 0"/>`,
    change: `<path class="s2 dash" d="M6 46h30"/><path class="s" d="M36 46c14 0 18-24 34-26 8-1 12-2 16-4"/><circle class="fl" cx="88" cy="15" r="5"/>`,
    slow: `<path class="s" d="M6 38h20M33 38h13M53 38h8M68 38h3"/><path class="f1" d="M83 14a10 10 0 1 0 7 16 8 8 0 0 1-7-16z"/>`,
    // 想变好的方向
    wish: `<path class="f2" d="M4 58c14-17 30-24 44-24s30 8 44 24z"/><path class="s" d="M48 34V8"/><path class="fl" d="M48 8h20l-5 6 5 6H48z"/>`,
    body: `<path class="s2 dash" d="M16 50a32 32 0 0 1 64 0"/><path class="s" d="M8 50h80"/><circle class="fl" cx="26" cy="27" r="9"/><path class="f1" d="M71 15a9 9 0 1 0 8 13 7 7 0 0 1-8-13z"/>`,
    study: `<path class="fs" d="M12 16c11-4 23-4 36 2v36c-13-6-25-6-36-2z"/><path class="f2" d="M84 16c-11-4-23-4-36 2v36c13-6 25-6 36-2z"/><path class="s2" d="M20 27c7-2 13-2 20 1M20 36c7-2 13-2 20 1M56 28c7-3 13-3 20-1M56 37c7-3 13-3 20-1"/>`,
    mood: `<ellipse class="f2" cx="48" cy="48" rx="36" ry="9"/><ellipse class="s2" cx="48" cy="48" rx="20" ry="4.5"/><path class="fp" d="M48 38c-9-6-15-10-15-17a7.5 7.5 0 0 1 15-3 7.5 7.5 0 0 1 15 3c0 7-6 11-15 17z"/>`,
    // 现在能拿出多少劲：种子 → 小苗 → 小树
    seed: BASE + `<path class="s" d="M48 49V36"/><path class="fm" d="M48 41c-10 0-14-5-14-11 8 0 14 4 14 11z"/><path class="fm2" d="M48 37c7 0 10-4 10-9-6 0-10 3-10 9z"/>`,
    sprout: BASE + `<path class="s" d="M48 49V20"/><path class="fm" d="M48 35c-10 0-14-6-14-12 8 0 14 4 14 12z"/><path class="fm" d="M48 28c9 0 13-5 13-11-7 0-13 4-13 11z"/>`,
    tree: BASE + `<path class="s" d="M48 49V30"/><circle class="fm" cx="38" cy="25" r="11"/><circle class="fm" cx="58" cy="23" r="12"/><circle class="fm2" cx="48" cy="13" r="10"/>`,
    // 路上怎么陪
    listen: `<rect class="f2" x="8" y="10" width="50" height="30" rx="15"/><path class="f2" d="M18 37l-5 12 14-9z"/><circle class="f1" cx="22" cy="25" r="3.2"/><circle class="f1" cx="33" cy="25" r="3.2"/><circle class="f1" cx="44" cy="25" r="3.2"/><circle class="fm" cx="76" cy="42" r="11"/>`,
    untangle: `<path class="s2" d="M6 32c4-15 12-15 12 0s8 15 12 0 8-13 10 2-6 8-2-2"/><path class="s" d="M50 32h32"/><path class="s" d="M76 25l8 7-8 7"/>`,
    push: `<rect class="f2" x="10" y="44" width="18" height="10" rx="3"/><rect class="f1" x="31" y="33" width="18" height="21" rx="3"/><rect class="fs" x="52" y="21" width="18" height="33" rx="3"/><path class="s" d="M76 22l10-10M78 12h8v8"/>`,
    cheer: `<circle class="fl" cx="46" cy="32" r="21"/><path fill="#fff" opacity=".92" d="M46 19l3.8 8.6 9.3.9-7 6.2 2.1 9.1-8.2-4.8-8.2 4.8 2.1-9.1-7-6.2 9.3-.9z"/><circle class="fp" cx="76" cy="14" r="3.5"/><circle class="f1" cx="16" cy="16" r="2.6"/><circle class="fm" cx="80" cy="48" r="2.6"/>`,
  };
  window.ill = (k, cls = "") => `<svg class="ill ${cls}" viewBox="0 0 96 64" aria-hidden="true">${ILL[k] || ""}</svg>`;

  window.TUNE = {
    kicker: "聊聊现在的你",
    intro: "说说现在的你，我们从这里开始。",
    wish: "敢开口说英语",          // 原型假设 TA 已经有这个愿望
    steps: [
      {
        key: "state", q: "最近的你，更像哪一种？", short: "最近",
        opts: [
          { v: "busy", label: "忙忙碌碌", hint: "事情一件接一件", ill: "busy", react: "最近事情不少呀。" },
          { v: "steady", label: "按自己的节奏", hint: "和平时差不多", ill: "steady", react: "有自己的节奏，挺好。" },
          { v: "change", label: "正在变化", hint: "有些事不一样了", ill: "change", react: "变化的时候，正好重新开始。" },
          { v: "slow", label: "想慢下来", hint: "有点累了", ill: "slow", react: "好，那我们不着急。" },
        ],
      },
      {
        key: "dir", q: "接下来，最想在哪儿看到一点进步？", short: "想变好的",
        opts: [
          { v: "wish", label: "敢开口说英语", hint: "接着你的愿望", ill: "wish", react: "好，接着往前走。" },
          { v: "body", label: "作息和身体", hint: "睡好、动起来", ill: "body", react: "身体顾好了，别的都轻松一点。" },
          { v: "study", label: "学习和工作", hint: "做得进去、做得完", ill: "study", react: "好，我们找个好下手的地方。" },
          { v: "mood", label: "心情和状态", hint: "少点焦虑、多点轻松", ill: "mood", react: "好，先让自己舒服一点。" },
        ],
      },
      {
        key: "energy", q: "现在，你能拿出多少劲？", short: "劲头",
        opts: [
          { v: "seed", label: "一点点就好", hint: "每天两分钟", ill: "seed", react: "那就从很小的一步开始。" },
          { v: "sprout", label: "每天一小会", hint: "十几分钟", ill: "sprout", react: "好，每天一小会，刚刚好。" },
          { v: "tree", label: "想认真来一次", hint: "可以多花点时间", ill: "tree", react: "好！那我们来点实在的。" },
        ],
      },
      {
        key: "accomp", q: "这一路，我怎么陪你比较好？", short: "陪你的方式",
        opts: [
          { v: "listen", label: "先听我说", hint: "不急着给建议", ill: "listen", set: "多听我说，不急着给建议", react: "好，你说的时候我先听着。" },
          { v: "untangle", label: "陪我理一理", hint: "乱的时候一起捋", ill: "untangle", set: "和我一起把事情想清楚", react: "好，乱的时候我们一起捋。" },
          { v: "push", label: "推我一把", hint: "给办法，也提醒我", ill: "push", set: "帮我想想具体可以怎么做 · 轻轻提醒", react: "好，该推的时候我会推你一下。" },
          { v: "cheer", label: "给我打打气", hint: "说说我做到了什么", ill: "cheer", set: "给我一些鼓励和信心", react: "好，你做到的事我都会说给你听。" },
        ],
      },
    ],
    extraPh: "可以不写。比如：最近在备考，晚上 11 点以后别找我",
  };
  window.optOf = (step, v) => step.opts.find((o) => o.v === v);
  // 结束页：小光看到的你 + 两个第一小步（ends.js 里是用真模型按每种选法预先跑出来的）
  window.endOf = (a) => (window.ENDS || {})[`${a.state || "none"}|${a.dir || "wish"}|${a.energy || "seed"}`];
})();
