// 宠物、植物、宝箱、星罐：全部是扁平 SVG，与小光（Emotion Ball）同一套造型语言——
// 圆润的身体、竖条小眼睛、淡淡的腮红、纯色，不用写实贴图。
// silhouette=true 时整只变成剪影（进化图里没走到的形态）。

const INK = "#1c1c22";

const PAL = {
  egg: { body: "#f4efe2", dark: "#ddd3bd", spot: "#9fdcc4" },
  baby: { body: "#7fd8b8", dark: "#5fc29f", leaf: "#7fd36f", stem: "#4fae5e" },
  fox: { body: "#ffab5e", dark: "#ef8f3e", belly: "#fff1dc", ear: "#ffd9b8", flame: "#ffd166", core: "#ff7a45", leaf: "#7fd36f" },
  deer: { body: "#f3d2ad", dark: "#e2b98d", spot: "#fff4e4", antler: "#9b6b4b", flower: "#ff8fb1", flower2: "#fff6f8", leaf: "#7fd36f" },
  whale: { body: "#8ccbf0", dark: "#6fb3dd", belly: "#d6edfb", leaf: "#7fd36f", trunk: "#a0714f", canopy: "#7fd8b8" },
  star: { body: "#6f62d9", dark: "#5a4ec2", gold: "#ffd66b", eye: "#fffbe8" },
};

function eyes(x1, x2, y, { color = INK, h = 22, w = 11 } = {}) {
  return `<g class="pe" style="transform-origin:${(x1 + x2) / 2}px ${y + h / 2}px">
    <rect x="${x1 - w / 2}" y="${y}" width="${w}" height="${h}" rx="${w / 2}" fill="${color}" transform="rotate(-6 ${x1} ${y + h / 2})"/>
    <rect x="${x2 - w / 2}" y="${y}" width="${w}" height="${h}" rx="${w / 2}" fill="${color}" transform="rotate(6 ${x2} ${y + h / 2})"/>
    <circle cx="${x1 + 2}" cy="${y + 6}" r="2.6" fill="#fff" opacity=".85"/><circle cx="${x2 + 2}" cy="${y + 6}" r="2.6" fill="#fff" opacity=".85"/></g>`;
}
const blush = (x1, x2, y) => `<ellipse cx="${x1}" cy="${y}" rx="9" ry="5" fill="#ff8fa3" opacity=".42"/><ellipse cx="${x2}" cy="${y}" rx="9" ry="5" fill="#ff8fa3" opacity=".42"/>`;
const shine = (x, y, rx = 18, ry = 10) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="#fff" opacity=".32" transform="rotate(-28 ${x} ${y})"/>`;
const sprout = (x, y, p, s = 1) => `<g transform="translate(${x} ${y}) scale(${s})">
    <path d="M0,0 C0,-8 1,-14 0,-20" stroke="${p.stem || "#4fae5e"}" stroke-width="4" stroke-linecap="round" fill="none"/>
    <ellipse cx="-10" cy="-22" rx="11" ry="6.5" fill="${p.leaf}" transform="rotate(-28 -10 -22)"/>
    <ellipse cx="11" cy="-25" rx="12" ry="7" fill="${p.leaf}" transform="rotate(24 11 -25)"/></g>`;
const star5 = (cx, cy, r, fill) => {
  let d = "";
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.45 : r;
    d += `${i ? "L" : "M"}${(cx + Math.cos(a) * rr).toFixed(1)},${(cy + Math.sin(a) * rr).toFixed(1)}`;
  }
  return `<path d="${d}Z" fill="${fill}" stroke="${fill}" stroke-width="2" stroke-linejoin="round"/>`;
};

const FORMS = {
  egg: (p) => `
    <ellipse cx="100" cy="114" rx="50" ry="62" fill="${p.body}"/>
    <circle cx="76" cy="94" r="6" fill="${p.spot}"/><circle cx="124" cy="132" r="7" fill="${p.spot}"/>
    <circle cx="88" cy="150" r="4.5" fill="${p.spot}"/><circle cx="126" cy="96" r="4" fill="${p.spot}"/>
    <polyline points="84,58 92,66 100,56 108,66 116,58" fill="none" stroke="${p.dark}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
    ${sprout(100, 56, { leaf: "#7fd36f" }, 0.85)}
    ${shine(76, 84)}
    @face<path d="M80,116 q6,5 12,0 M108,116 q6,5 12,0" stroke="${INK}" stroke-width="3.6" stroke-linecap="round" fill="none"/>${blush(74, 126, 130)}@`,
  baby: (p) => `
    <ellipse cx="80" cy="174" rx="13" ry="7" fill="${p.dark}"/><ellipse cx="120" cy="174" rx="13" ry="7" fill="${p.dark}"/>
    <circle cx="100" cy="118" r="58" fill="${p.body}"/>
    ${sprout(100, 62, p)}
    ${shine(72, 88)}
    @face${eyes(84, 116, 104)}${blush(70, 130, 132)}@`,
  "fox-1": (p) => `
    <path d="M138,150 C176,150 188,112 172,82 C164,104 150,118 130,126 Z" fill="${p.body}"/>
    <ellipse cx="172" cy="86" rx="13" ry="16" fill="${p.flame}" transform="rotate(20 172 86)"/>
    <path d="M172,74 C178,82 178,92 171,97 C166,90 166,82 172,74Z" fill="${p.core}"/>
    <path d="M60,96 L66,46 L98,74 Z" fill="${p.body}" stroke="${p.body}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M140,96 L134,46 L102,74 Z" fill="${p.body}" stroke="${p.body}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M68,84 L71,58 L88,74 Z" fill="${p.ear}"/><path d="M132,84 L129,58 L112,74 Z" fill="${p.ear}"/>
    <circle cx="100" cy="124" r="56" fill="${p.body}"/>
    <ellipse cx="100" cy="146" rx="32" ry="22" fill="${p.belly}"/>
    ${shine(74, 96, 16, 9)}
    @face${eyes(84, 116, 108)}<path d="M96,134 L104,134 L100,139Z" fill="#3a2a22" stroke="#3a2a22" stroke-width="2" stroke-linejoin="round"/>${blush(70, 130, 134)}@`,
  "fox-2": (p) => `
    <path d="M136,152 C186,156 198,104 176,66 C168,96 152,116 128,126 Z" fill="${p.body}"/>
    <ellipse cx="177" cy="70" rx="17" ry="22" fill="${p.flame}" transform="rotate(16 177 70)"/>
    <path d="M178,52 C187,64 186,78 177,84 C170,74 170,62 178,52Z" fill="${p.core}"/>
    <circle cx="186" cy="40" r="3" fill="${p.flame}"/><circle cx="164" cy="42" r="2.2" fill="${p.flame}"/>
    <path d="M56,94 L60,34 L98,68 Z" fill="${p.body}" stroke="${p.body}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M144,94 L140,34 L102,68 Z" fill="${p.body}" stroke="${p.body}" stroke-width="10" stroke-linejoin="round"/>
    <path d="M65,82 L67,50 L88,68 Z" fill="${p.ear}"/><path d="M135,82 L133,50 L112,68 Z" fill="${p.ear}"/>
    ${sprout(100, 66, { leaf: p.leaf }, 0.8)}
    <circle cx="100" cy="122" r="60" fill="${p.body}"/>
    <ellipse cx="100" cy="148" rx="36" ry="24" fill="${p.belly}"/>
    ${shine(72, 92, 18, 10)}
    @face${eyes(83, 117, 104, { h: 24 })}<path d="M96,134 L104,134 L100,139Z" fill="#3a2a22" stroke="#3a2a22" stroke-width="2" stroke-linejoin="round"/>${blush(68, 132, 134)}@`,
  "deer-1": (p) => `
    <path d="M86,76 L80,52 M82,60 L70,54 M114,76 L120,52 M118,60 L130,54" stroke="${p.antler}" stroke-width="5" stroke-linecap="round" fill="none"/>
    <circle cx="80" cy="50" r="5.5" fill="${p.flower}"/><circle cx="120" cy="50" r="5.5" fill="${p.flower}"/>
    <ellipse cx="54" cy="100" rx="17" ry="8" fill="${p.dark}" transform="rotate(-24 54 100)"/>
    <ellipse cx="146" cy="100" rx="17" ry="8" fill="${p.dark}" transform="rotate(24 146 100)"/>
    <circle cx="100" cy="124" r="54" fill="${p.body}"/>
    <circle cx="74" cy="148" r="5" fill="${p.spot}"/><circle cx="128" cy="150" r="4" fill="${p.spot}"/><circle cx="118" cy="160" r="3" fill="${p.spot}"/>
    ${shine(76, 98, 15, 9)}
    @face${eyes(85, 115, 108)}<ellipse cx="100" cy="136" rx="5" ry="3.5" fill="#6b4a3a"/>${blush(72, 128, 136)}@`,
  "deer-2": (p) => `
    <path d="M84,74 L72,34 M76,48 L58,40 M74,40 L80,22 M116,74 L128,34 M124,48 L142,40 M126,40 L120,22" stroke="${p.antler}" stroke-width="5.5" stroke-linecap="round" fill="none"/>
    <circle cx="58" cy="39" r="6" fill="${p.flower}"/><circle cx="80" cy="21" r="5" fill="${p.flower2}"/><circle cx="72" cy="33" r="5.5" fill="${p.flower}"/>
    <circle cx="142" cy="39" r="6" fill="${p.flower}"/><circle cx="120" cy="21" r="5" fill="${p.flower2}"/><circle cx="128" cy="33" r="5.5" fill="${p.flower}"/>
    <ellipse cx="94" cy="58" rx="7" ry="4" fill="${p.leaf}" transform="rotate(-30 94 58)"/>
    <ellipse cx="50" cy="98" rx="19" ry="9" fill="${p.dark}" transform="rotate(-24 50 98)"/>
    <ellipse cx="150" cy="98" rx="19" ry="9" fill="${p.dark}" transform="rotate(24 150 98)"/>
    <circle cx="100" cy="122" r="60" fill="${p.body}"/>
    <circle cx="70" cy="150" r="6" fill="${p.spot}"/><circle cx="132" cy="152" r="5" fill="${p.spot}"/><circle cx="120" cy="164" r="3.5" fill="${p.spot}"/><circle cx="84" cy="166" r="3" fill="${p.spot}"/>
    ${shine(72, 92, 18, 10)}
    @face${eyes(84, 116, 104, { h: 24 })}<ellipse cx="100" cy="134" rx="5.5" ry="3.8" fill="#6b4a3a"/>${blush(68, 132, 134)}@`,
  "whale-1": (p) => `
    <path d="M150,124 Q170,114 182,90 Q168,100 158,98 Q166,110 150,124Z" fill="${p.body}"/>
    <path d="M150,124 Q172,128 188,112 Q174,112 162,108Z" fill="${p.dark}"/>
    <ellipse cx="96" cy="124" rx="62" ry="50" fill="${p.body}"/>
    <ellipse cx="92" cy="144" rx="44" ry="24" fill="${p.belly}"/>
    ${sprout(94, 76, { leaf: p.leaf }, 0.75)}
    ${shine(66, 98, 16, 9)}
    @face${eyes(78, 108, 108, { h: 20, w: 10 })}${blush(64, 120, 132)}@`,
  "whale-2": (p) => `
    <path d="M154,124 Q178,110 190,80 Q174,94 162,92 Q172,108 154,124Z" fill="${p.body}"/>
    <path d="M154,124 Q180,130 196,108 Q180,108 166,104Z" fill="${p.dark}"/>
    <ellipse cx="96" cy="126" rx="68" ry="54" fill="${p.body}"/>
    <ellipse cx="92" cy="150" rx="50" ry="24" fill="${p.belly}"/>
    <rect x="93" y="48" width="9" height="30" rx="4" fill="${p.trunk}"/>
    <circle cx="97" cy="42" r="19" fill="${p.canopy}"/><circle cx="82" cy="50" r="12" fill="${p.canopy}"/><circle cx="113" cy="50" r="12" fill="${p.canopy}"/>
    <circle cx="40" cy="70" r="2.5" fill="#fff" opacity=".8"/><circle cx="160" cy="52" r="2" fill="#fff" opacity=".8"/>
    ${shine(62, 100, 18, 10)}
    @face${eyes(76, 108, 110, { h: 22 })}${blush(62, 122, 136)}@`,
  "star-1": (p) => `
    <path d="M146,150 A24,24 0 1 0 170,116 A17,17 0 1 1 146,150Z" fill="${p.gold}"/>
    <circle cx="100" cy="122" r="56" fill="${p.body}"/>
    ${star5(100, 62, 14, p.gold)}
    <circle cx="70" cy="146" r="2.6" fill="${p.gold}"/><circle cx="132" cy="96" r="2.2" fill="${p.gold}"/><circle cx="128" cy="154" r="2.8" fill="${p.gold}"/><circle cx="74" cy="100" r="1.8" fill="${p.gold}"/>
    ${shine(76, 96, 15, 8)}
    @face${eyes(85, 115, 108, { color: p.eye })}${blush(72, 128, 136)}@`,
  "star-2": (p) => `
    <path d="M60,40 A44,22 0 0 0 140,40" stroke="${p.gold}" stroke-width="6" stroke-linecap="round" fill="none"/>
    <path d="M142,154 A30,30 0 1 0 178,112 A22,22 0 1 1 142,154Z" fill="${p.gold}"/>
    <circle cx="100" cy="122" r="60" fill="${p.body}"/>
    ${star5(100, 60, 15, p.gold)}${star5(42, 92, 6, p.gold)}${star5(160, 70, 5, p.gold)}
    <circle cx="68" cy="148" r="3" fill="${p.gold}"/><circle cx="134" cy="94" r="2.4" fill="${p.gold}"/><circle cx="130" cy="158" r="3" fill="${p.gold}"/><circle cx="72" cy="98" r="2" fill="${p.gold}"/><circle cx="104" cy="168" r="2" fill="${p.gold}"/>
    ${shine(72, 92, 18, 9)}
    @face${eyes(84, 116, 104, { color: p.eye, h: 24 })}${blush(68, 132, 134)}@`,
};

export const FORM_OF = { "pet-egg": "egg", "pet-baby": "baby" };

export function petSVG(form, { silhouette = false, cls = "" } = {}) {
  form = FORM_OF[form] || form.replace(/^pet-/, "");
  const key = form.split("-")[0];
  const p = PAL[key] || PAL.baby;
  const build = FORMS[form] || FORMS.baby;
  let body = build(p);
  if (silhouette) {
    body = body.replace(/@face[\s\S]*?@/g, "").replace(/fill="(?!none)[^"]*"/g, 'fill="var(--sil)"')
      .replace(/stroke="(?!none)[^"]*"/g, 'stroke="var(--sil)"').replace(/opacity="[^"]*"/g, "");
  } else {
    body = body.replace(/@face([\s\S]*?)@/g, "$1");
  }
  return `<svg class="pet ${silhouette ? "sil" : ""} ${cls}" viewBox="0 0 200 200" aria-hidden="true">
    <ellipse class="pet-shadow" cx="100" cy="186" rx="52" ry="7"/>
    <g class="pet-body">${body}</g></svg>`;
}

// ---------------------------------------------------------------- 植物 ----
const PLANTS = {
  sprout: `<path d="M30,78 C30,66 31,58 30,48" stroke="#4fae5e" stroke-width="4" stroke-linecap="round" fill="none"/>
    <ellipse cx="20" cy="46" rx="11" ry="6" fill="#7fd36f" transform="rotate(-28 20 46)"/><ellipse cx="41" cy="42" rx="12" ry="7" fill="#8fdc7a" transform="rotate(24 41 42)"/>`,
  tulip: `<path d="M30,78 L30,44" stroke="#4fae5e" stroke-width="4" stroke-linecap="round"/>
    <ellipse cx="21" cy="62" rx="10" ry="5" fill="#7fd36f" transform="rotate(-40 21 62)"/>
    <path d="M18,30 Q18,48 30,48 Q42,48 42,30 L36,36 L30,26 L24,36 Z" fill="#ff8fb1" stroke="#ff8fb1" stroke-width="2" stroke-linejoin="round"/>`,
  bush: `<circle cx="20" cy="62" r="15" fill="#5fbf6e"/><circle cx="40" cy="60" r="16" fill="#6fcd7c"/><circle cx="30" cy="48" r="16" fill="#7fd88a"/>
    <circle cx="22" cy="54" r="3" fill="#ff6b6b"/><circle cx="38" cy="50" r="3" fill="#ff6b6b"/><circle cx="34" cy="64" r="3" fill="#ff6b6b"/>`,
  tree: `<rect x="26" y="52" width="8" height="26" rx="3" fill="#a0714f"/><circle cx="30" cy="38" r="20" fill="#7fd8b8"/><circle cx="18" cy="48" r="11" fill="#6ccaa7"/><circle cx="43" cy="47" r="12" fill="#6ccaa7"/>`,
  glow: `<rect x="26" y="52" width="8" height="26" rx="3" fill="#a0714f"/><circle cx="30" cy="36" r="21" fill="#5fc29f"/>
    <circle cx="22" cy="30" r="3.5" fill="#ffd66b"/><circle cx="38" cy="40" r="3.5" fill="#ffd66b"/><circle cx="30" cy="22" r="3" fill="#ffd66b"/><circle cx="18" cy="44" r="3" fill="#ffd66b"/>`,
};
export const PLANT_KINDS = Object.keys(PLANTS);
export function plantSVG(kind) {
  return `<svg class="plant-svg" viewBox="0 0 60 80" aria-hidden="true">${PLANTS[kind] || PLANTS.sprout}</svg>`;
}

// ---------------------------------------------------------------- 宝箱 / 星罐 ----
export function chestSVG(open = false) {
  return `<svg class="chest ${open ? "open" : ""}" viewBox="0 0 120 110" aria-hidden="true">
    <g class="chest-glow"><circle cx="60" cy="46" r="34" fill="var(--accent)" opacity=".25"/>
      ${star5(40, 26, 6, "#ffd66b")}${star5(78, 18, 5, "#ffd66b")}${star5(62, 8, 4, "#ffd66b")}</g>
    <rect x="16" y="52" width="88" height="48" rx="10" fill="#c98a3a"/>
    <rect x="16" y="52" width="88" height="10" fill="#b0752d"/>
    <rect x="52" y="52" width="16" height="48" fill="#e0a64d"/>
    <g class="chest-lid"><path d="M16,54 Q16,26 60,26 Q104,26 104,54 Z" fill="#d99a45"/><rect x="52" y="26" width="16" height="28" fill="#eab25a"/></g>
    <rect x="54" y="62" width="12" height="14" rx="3" fill="#7a4a1d"/></svg>`;
}

export function jarSVG(n = 0) {
  const stars = [];
  for (let i = 0; i < Math.min(n, 14); i++) {
    const x = 40 + ((i * 37) % 44), y = 104 - Math.floor(i / 4) * 14 - ((i * 13) % 8);
    stars.push(star5(x, y, 6, "#ffd66b"));
  }
  return `<svg class="jar" viewBox="0 0 120 130" aria-hidden="true">
    <rect x="34" y="8" width="52" height="14" rx="5" fill="#c98a3a"/>
    <path d="M38,22 L82,22 Q100,30 100,52 L100,108 Q100,122 86,122 L34,122 Q20,122 20,108 L20,52 Q20,30 38,22Z" fill="var(--jar-glass)" stroke="var(--jar-edge)" stroke-width="3"/>
    ${stars.join("")}
    <path d="M30,52 Q30,40 40,36" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity=".5" fill="none"/></svg>`;
}

