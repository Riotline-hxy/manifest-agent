/* @building {"name": "摩天轮", "cat": "decor", "size": [2, 2], "price": 280, "lv": 32, "height": 108, "desc": "转一圈，能看见整座小镇", "enabled": true} */
// 摩天轮：2×2。轮子立在 y = 0 那个竖直面里，慢慢转；吊舱跟着转、反着转，始终是正的。
// 最外面那个看不见的圈让轮子的包围盒以轮心为中心，CSS 才能绕轮心转
export default function draw(k) {
  const { P, box, shadow, line, shade } = k;
  const R = 36, hubZ = 50;
  const plane = (y) => { const h = P(0, y, hubZ); return `matrix(.894 .447 0 1 ${h[0]} ${h[1]})`; };
  const legs = (y) => `<g transform="${plane(y)}"><path d="M-30,${hubZ} L0,0 L30,${hubZ}" fill="none" stroke="#e9e2f2" stroke-width="3.4" stroke-linejoin="round"/>
    <path d="M-18,${hubZ * 0.6} L18,${hubZ * 0.6}" stroke="#d8cfe6" stroke-width="2"/></g>`;
  const colors = ["#ff8fb1", "#ffd166", "#7fd3c4", "#a99bff", "#ff8a65", "#6cb8ff", "#ffd166", "#7fd36f"];
  const spokes = colors.map((_, i) => { const t = (i / 8) * Math.PI * 2; return `<line x1="0" y1="0" x2="${(Math.cos(t) * R).toFixed(1)}" y2="${(Math.sin(t) * R).toFixed(1)}" stroke="#f3eefa" stroke-width="1.3"/>`; }).join("");
  const cars = colors.map((c, i) => {
    const t = (i / 8) * Math.PI * 2, x = (Math.cos(t) * R).toFixed(1), y = (Math.sin(t) * R).toFixed(1);
    return `<g transform="translate(${x},${y})"><g class="tw-car"><line x1="0" y1="0" x2="0" y2="3" stroke="#8a8f9f" stroke-width="1"/>
      <rect x="-5" y="3" width="10" height="8" rx="3" fill="${c}"/><rect x="-3.4" y="4.6" width="6.8" height="3" rx="1" fill="var(--t-win)" opacity=".9"/></g></g>`;
  }).join("");
  return shadow(1.7, 6)
    + box({ a: 0.82, b: 0.82, h: 4, c: "#d9cfe6", t: "#ece6f4" })
    + box({ x: 0.45, y: 0.5, a: 0.16, b: 0.12, z: 4, h: 10, c: "#fff3e0" })
    + legs(-0.14)
    + `<g transform="${plane(0)}"><g class="tw-wheel"><circle r="${R + 12}" fill="none"/><circle r="${R}" fill="none" stroke="#ffffff" stroke-width="3"/><circle r="${R - 6}" fill="none" stroke="#f3eefa" stroke-width="1.2"/>
      ${spokes}${cars}<circle r="4" fill="${shade("#a99bff", -0.1)}"/></g></g>`
    + legs(0.14)
    + line(P(0, -0.14, hubZ), P(0, 0.14, hubZ), "#cfc4e0", 3);
}
