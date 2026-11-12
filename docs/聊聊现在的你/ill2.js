// 「许个愿」「让愿望落地」原型用的插图：柔和的扁平小画，颜色用 App 的 .ill 配色（css/tune.css，森林主题有自己的一套）。
// 每张 viewBox 0 0 96 64；.f1 .f2 主色深浅，.fp 粉，.fm .fm2 嫩绿，.fl 暖黄，.fs 天蓝，.s .s2 线条，.star 白色。
(function () {
  const POT = `<path class="pot" d="M35 46h26l-3 14H38z"/><rect class="pot2" x="33" y="42" width="30" height="6" rx="2.5"/>`;
  const L = (y, s, k = "fm") => `<path class="${k}" d="M48 ${y}c${-9 * s} 0 ${-13 * s}-4 ${-14 * s}-10 ${8 * s}-1 ${13 * s} 3 ${14 * s} 10z"/>`;
  const R = (y, s, k = "fm2") => `<path class="${k}" d="M48 ${y}c${9 * s} 0 ${13 * s}-4 ${14 * s}-10 ${-8 * s}-1 ${-13 * s} 3 ${-14 * s} 10z"/>`;
  const SPARK = (x, y, k = "fl") => `<path class="${k}" d="M${x} ${y - 7}l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/>`;
  window.ILL = {
    // ---- 最近的状态：节奏线 ----
    busy: `<path class="s2" d="M6 28c10 14 14 16 22 0s12-14 18 4 10 14 18-2 10-12 26 2"/><path class="s" d="M6 38c8-18 14-18 20 0s12 16 18-2 10-18 18 0 12 14 28-6"/>`,
    steady: `<path class="s2 dash" d="M6 44h84"/><path class="s" d="M6 32c14-9 28-9 42 0s28 9 42 0"/>`,
    change: `<path class="s2 dash" d="M6 46h30"/><path class="s" d="M36 46c14 0 18-24 34-26 8-1 12-2 16-4"/><circle class="fl" cx="88" cy="15" r="5"/>`,
    slow: `<path class="s" d="M6 38h20M33 38h13M53 38h8M68 38h3"/><path class="f1" d="M83 14a10 10 0 1 0 7 16 8 8 0 0 1-7-16z"/>`,
    // ---- 许个愿：已有的愿望 / 新的愿望 ----
    wish: `<path class="f2" d="M4 58c14-17 30-24 44-24s30 8 44 24z"/><path class="s" d="M48 34V8"/><path class="fl" d="M48 8h20l-5 6 5 6H48z"/>`,
    newwish: `<circle class="f2" cx="48" cy="34" r="20"/><path class="s" d="M48 25v18M39 34h18"/>${SPARK(76, 14)}<circle class="fp" cx="18" cy="18" r="3"/><circle class="fm" cx="80" cy="48" r="2.6"/>`,
    // ---- 方向 ----
    body: `<path class="s2 dash" d="M16 50a32 32 0 0 1 64 0"/><path class="s" d="M8 50h80"/><circle class="fl" cx="26" cy="27" r="9"/><path class="f1" d="M71 15a9 9 0 1 0 8 13 7 7 0 0 1-8-13z"/>`,
    study: `<path class="fs" d="M12 16c11-4 23-4 36 2v36c-13-6-25-6-36-2z"/><path class="f2" d="M84 16c-11-4-23-4-36 2v36c13-6 25-6 36-2z"/><path class="s2" d="M20 27c7-2 13-2 20 1M20 36c7-2 13-2 20 1M56 28c7-3 13-3 20-1M56 37c7-3 13-3 20-1"/>`,
    people: `<rect class="f2" x="8" y="12" width="44" height="26" rx="13"/><path class="f2" d="M18 35l-4 10 12-8z"/><rect class="fs" x="42" y="26" width="46" height="24" rx="12"/><path class="fs" d="M78 47l5 9-12-7z"/><circle class="f1" cx="56" cy="38" r="2.6"/><circle class="f1" cx="65" cy="38" r="2.6"/><circle class="f1" cx="74" cy="38" r="2.6"/>`,
    mood: `<ellipse class="f2" cx="48" cy="48" rx="36" ry="9"/><ellipse class="s2" cx="48" cy="48" rx="20" ry="4.5"/><path class="fp" d="M48 38c-9-6-15-10-15-17a7.5 7.5 0 0 1 15-3 7.5 7.5 0 0 1 15 3c0 7-6 11-15 17z"/>`,
    life: `<path class="f2" d="M12 46a8 8 0 0 1 9-8 11 11 0 0 1 20 2 7 7 0 0 1 3 13H14a7 7 0 0 1-2-7z"/><path class="fs" d="M64 6l14 15-14 15-14-15z"/><path class="s2" d="M64 6v30M50 21h28"/><path class="s" d="M64 36c-5 7 5 10-1 18"/><path class="fp" d="M60 44l-6 1 4 4z"/><path class="fp" d="M65 51l-5 3 5 2z"/>`,
    // ---- 它实现了，最想得到的 ----
    free: `<ellipse class="fp" cx="48" cy="22" rx="13" ry="15"/><path class="fp" d="M45 36h6l-3 4z"/><path class="s2" d="M48 40c-4 6 4 9 0 16"/><path class="star" d="M42 14q3-4 7-4" opacity=".7"/><path class="s2 dash" d="M8 52h22M66 48h22"/>`,
    brave: `<path class="f2" d="M40 4h16l16 46H24z"/><ellipse class="f1" cx="48" cy="52" rx="24" ry="6"/><circle class="fl" cx="48" cy="32" r="5"/><path class="fl" d="M41 49c0-7 3-11 7-11s7 4 7 11z"/>`,
    safe: `<path class="f2" d="M24 30L48 12l24 18v24H24z"/><path class="s" d="M19 33L48 10l29 23"/><rect class="fl" x="43" y="36" width="11" height="18" rx="2"/><rect class="fl" x="29" y="34" width="9" height="8" rx="1.5"/>`,
    near: `<circle class="fs" cx="38" cy="34" r="15"/><circle class="fp" cx="58" cy="34" r="15" opacity=".9"/><path class="star" d="M48 42s-7-4-7-8c0-4 4-5 7-2 3-3 7-2 7 2 0 4-7 8-7 8z"/>`,
    self: `<ellipse class="f2" cx="48" cy="28" rx="15" ry="20"/><ellipse class="s" cx="48" cy="28" rx="15" ry="20"/><path class="s" d="M48 48v8M40 57h16"/><path class="star" d="M41 18q3-5 8-6" opacity=".85"/>${SPARK(74, 16)}`,
    // ---- 那一刻的感觉 ----
    light: `<path class="f2" d="M72 8C48 12 32 30 26 54c10-6 24-8 32-18 8-10 13-20 14-28z"/><path class="s" d="M72 8C58 24 44 38 26 54"/><path class="s2" d="M54 24l-9-2M47 32l-9-1M40 40l-9 0"/>`,
    proud: `<path class="fs" d="M37 4h9l6 18h-9zM59 4h-9l-6 18h9z"/><circle class="fl" cx="48" cy="38" r="15"/><path class="star" d="M48 30l2.6 5.6 6 .6-4.6 4 1.4 6-5.4-3.2-5.4 3.2 1.4-6-4.6-4 6-.6z"/>`,
    calm: `<path class="s2" d="M8 22c8-6 14-6 22 0s14 6 22 0 14-6 22 0 10 5 14 3"/><path class="s" d="M8 34c8-6 14-6 22 0s14 6 22 0 14-6 22 0 10 5 14 3"/><path class="s2" d="M8 46c8-6 14-6 22 0s14 6 22 0 14-6 22 0 10 5 14 3"/>`,
    steadyfeel: `<ellipse class="f1" cx="48" cy="53" rx="21" ry="7"/><ellipse class="fm" cx="48" cy="41" rx="15" ry="6"/><ellipse class="fs" cx="48" cy="31" rx="10" ry="5"/><ellipse class="fl" cx="48" cy="22" rx="6" ry="4"/>`,
    happy: `<circle class="fl" cx="48" cy="32" r="13"/><path class="s" d="M48 7v6M48 51v6M23 32h6M67 32h6M31 15l4 4M61 45l4 4M65 15l-4 4M35 45l-4 4"/>`,
    // ---- 担心 ----
    rain: `<path class="f2" d="M30 42a10 10 0 0 1-1-20 14 14 0 0 1 27-5 11 11 0 1 1 10 25z"/><path class="s2" d="M38 50l-3 7M50 50l-3 7M62 50l-3 7"/>`,
    hourglass: `<path class="s" d="M32 7h32M32 57h32"/><path class="f2" d="M37 7h22c0 13-11 17-11 25 0-8-11-12-11-25zM37 57h22c0-13-11-17-11-25 0 8-11 12-11 25z"/><path class="fl" d="M42 53h12c-2-6-6-8-6-12 0 4-4 6-6 12z"/>`,
    eyes: `<path class="f2" d="M8 32s8-12 20-12 20 12 20 12-8 12-20 12S8 32 8 32z"/><circle class="f1" cx="28" cy="32" r="6"/><path class="f2" d="M48 32s8-12 20-12 20 12 20 12-8 12-20 12-20-12-20-12z"/><circle class="f1" cx="68" cy="32" r="6"/>`,
    drift: `<path class="fm" d="M60 18c-15 0-26 11-26 26 15 0 26-11 26-26z"/><path class="s2" d="M34 44l16-16"/><path class="s2 dash" d="M68 12c10 4 15 13 12 24"/>`,
    // ---- 拦住你的 ----
    clock: `<circle class="f2" cx="48" cy="34" r="22"/><path class="s" d="M48 21v13l9 6"/><circle class="fl" cx="48" cy="34" r="2.8"/><path class="s2" d="M30 7l-7 6M66 7l7 6"/>`,
    battery: `<rect class="f2" x="20" y="20" width="50" height="26" rx="6"/><rect class="s" x="20" y="20" width="50" height="26" rx="6"/><rect class="f1" x="72" y="28" width="5" height="10" rx="2"/><rect class="fp" x="26" y="26" width="10" height="14" rx="3"/>`,
    note: `<path class="fl" d="M26 8h42v36L56 56H26z"/><path class="f1" d="M68 44H56v12z"/><path class="s" d="M41 24q0-7 7-7t7 7q0 5-7 7v4"/><circle class="f1" cx="48" cy="43" r="2.4"/>`,
    fork: `<circle class="fl" cx="16" cy="44" r="5"/><path class="s" d="M21 44h14"/><path class="s2" d="M35 44c10 0 12-24 26-24h22M35 44c10 0 12 12 26 12h22"/><path class="s2 dash" d="M35 44h48"/>`,
    stone: `<ellipse class="f1" cx="48" cy="24" rx="23" ry="14"/><path class="star" d="M36 18q5-6 13-6" opacity=".45"/><path class="s2" d="M30 47l4 6M48 45v8M66 47l-4 6"/><path class="s" d="M14 59h68"/>`,
    // ---- 时机 ----
    sunrise: `<path class="s" d="M8 46h80"/><path class="fl" d="M30 46a18 18 0 0 1 36 0z"/><path class="s2" d="M48 16v6M24 26l4 4M72 26l-4 4M14 38h6M76 38h6"/>`,
    bowl: `<path class="fs" d="M22 33h52a26 21 0 0 1-52 0z"/><rect class="f1" x="20" y="30" width="56" height="5" rx="2.5"/><path class="s2" d="M38 23c-4-4 4-8 0-12M48 23c-4-4 4-8 0-12M58 23c-4-4 4-8 0-12"/>`,
    bag: `<rect class="fm" x="31" y="18" width="34" height="38" rx="10"/><path class="s" d="M40 18v-4a8 8 0 0 1 16 0v4"/><rect class="fm2" x="38" y="35" width="20" height="13" rx="4"/>`,
    night: `<path class="f1" d="M54 10a20 20 0 1 0 16 32 16 16 0 0 1-16-32z"/><circle class="fl" cx="22" cy="18" r="2.6"/><circle class="fl" cx="80" cy="14" r="2"/><circle class="fl" cx="28" cy="46" r="1.8"/>`,
    // ---- 现在能拿出多少劲（落地里用来定「更小的版本」，保留） ----
    pot1: POT + `<path class="s" d="M48 42v-8"/>` + L(36, .7) + R(36, .7),
    pot2: POT + `<path class="s" d="M48 42V20"/>` + L(36, .8) + R(36, .8) + L(26, .9) + R(26, .9),
    pot3: POT + `<path class="s" d="M48 42V14"/>` + L(36, .8) + R(36, .8) + L(27, .95) + R(27, .95)
      + `<circle class="fp" cx="44" cy="11" r="3.6"/><circle class="fp" cx="52" cy="11" r="3.6"/><circle class="fp" cx="48" cy="7" r="3.6"/><circle class="fp" cx="48" cy="15" r="3.6"/><circle class="fl" cx="48" cy="11" r="2.8"/>`,
  };
  const VIEW = { pot1: "22 0 52 64", pot2: "22 0 52 64", pot3: "22 0 52 64" };
  window.ill = (k) => `<svg class="ill" viewBox="${VIEW[k] || "0 0 96 64"}" aria-hidden="true">${window.ILL[k] || ""}</svg>`;
})();
