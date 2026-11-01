// 宠物：成长页是 Rive 实时动画（livepet.js），其他地方用同一套原画的静态图（醒着 / 睡着两张）。
// silhouette=true 时整只变成剪影（进化图里没走到的形态）。植物、宝箱、星罐仍是扁平 SVG。

// 后端的形态 → 宠物文件：egg 阶段是初生小芽，baby 阶段是抽芽期小芽，四条路线各有幼体和成年体
const PET_ID = {
  egg: "baby", baby: "sprout", "fox-1": "fox-young", "fox-2": "fox-adult", "deer-1": "deer-young", "deer-2": "deer-adult",
  "whale-1": "water-young", "whale-2": "water-adult", "star-1": "star-young", "star-2": "star-adult",
};
export const petId = (art) => PET_ID[String(art || "").replace(/^pet-/, "")] || "baby";

const star5 = (cx, cy, r, fill) => {
  let d = "";
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.45 : r;
    d += `${i ? "L" : "M"}${(cx + Math.cos(a) * rr).toFixed(1)},${(cy + Math.sin(a) * rr).toFixed(1)}`;
  }
  return `<path d="${d}Z" fill="${fill}" stroke="${fill}" stroke-width="2" stroke-linejoin="round"/>`;
};

export function petSVG(form, { silhouette = false, cls = "", sleep = false } = {}) {
  const src = `/pets/img/${petId(form)}${sleep && !silhouette ? "-sleep" : ""}.webp`;
  const sil = silhouette
    ? `<defs><filter id="pet-sil"><feFlood style="flood-color:var(--sil)"/><feComposite in2="SourceAlpha" operator="in"/></filter></defs>`
    : "";
  const zzz = sleep ? `<g class="zzz" aria-hidden="true"><text x="140" y="70">z</text><text x="156" y="52">z</text><text x="170" y="34">Z</text></g>` : "";
  return `<svg class="pet ${silhouette ? "sil" : ""} ${sleep ? "sleeping" : ""} ${cls}" viewBox="0 0 200 200" aria-hidden="true">${sil}
    <ellipse class="pet-shadow" cx="100" cy="186" rx="52" ry="7"/>
    <g class="pet-body"><image href="${src}" x="4" y="8" width="192" height="180" preserveAspectRatio="xMidYMax meet"${silhouette ? ' filter="url(#pet-sil)"' : ""}/></g>${zzz}</svg>`;
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

