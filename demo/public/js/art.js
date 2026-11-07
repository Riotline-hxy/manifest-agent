// 好消息的星罐（好消息页、蜕变报告里用）。

const star5 = (cx, cy, r, fill) => {
  let d = "";
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.45 : r;
    d += `${i ? "L" : "M"}${(cx + Math.cos(a) * rr).toFixed(1)},${(cy + Math.sin(a) * rr).toFixed(1)}`;
  }
  return `<path d="${d}Z" fill="${fill}" stroke="${fill}" stroke-width="2" stroke-linejoin="round"/>`;
};

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
