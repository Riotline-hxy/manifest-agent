/* @building {"name": "中心花园", "cat": "nature", "size": [2, 2], "price": 200, "lv": 22, "height": 52, "desc": "十字小路、四棵树，中间一座小亭子", "enabled": true} */
// 中心花园：2×2。一块微微抬起的草坪，十字小路，四角各一棵树，中间一座六角小亭
export default function draw(k) {
  const { P, poly, shade, box, cyl, shadow, blob, line } = k;
  const a = 0.92;
  const tree = (x, y, pink) => {
    const g = P(x, y, 0);
    return `<ellipse cx="${g[0]}" cy="${g[1] + 2}" rx="15" ry="7" fill="url(#@@sh)"/>`
      + box({ x, y, a: 0.035, b: 0.035, z: 2, h: 9, c: "#9a6b4b" })
      + `<g class="tw-sway">${blob(g[0] - 5, g[1] - 17, 6.5, pink ? "url(#@@pink)" : "url(#@@leaf)")}${blob(g[0] + 5, g[1] - 18, 7, pink ? "url(#@@pink)" : "url(#@@leaf)")}${blob(g[0], g[1] - 24, 8.5, pink ? "url(#@@pink)" : "url(#@@leaf)")}</g>`;
  };
  const path = (x0, x1, y0, y1) => poly([P(x0, y0, 2.2), P(x1, y0, 2.2), P(x1, y1, 2.2), P(x0, y1, 2.2)], "var(--t-path)");
  const bed = [];
  for (let i = 0; i < 10; i++) {
    const t = (i / 10) * Math.PI * 2, p = P(Math.cos(t) * 0.62, Math.sin(t) * 0.62, 3);
    bed.push(blob(p[0], p[1], 2.2, ["#ff8fb1", "#ffd166", "#ffffff", "#b9a7ff"][i % 4]));
  }
  // 小亭：圆台 + 六根柱 + 尖顶
  const pillars = [];
  for (let i = 0; i < 6; i++) {
    const t = (i / 6) * Math.PI * 2 + 0.3;
    pillars.push({ d: Math.sin(t) + Math.cos(t), svg: line(P(Math.cos(t) * 0.26, Math.sin(t) * 0.26, 6), P(Math.cos(t) * 0.26, Math.sin(t) * 0.26, 28), "#f4ead6", 2.6) });
  }
  pillars.sort((p, q) => p.d - q.d);
  const roof = [], tip = P(0, 0, 44);
  for (let i = 0; i < 6; i++) {
    const t0 = (i / 6) * Math.PI * 2 + 0.3, t1 = ((i + 1) / 6) * Math.PI * 2 + 0.3;
    const r0 = P(Math.cos(t0) * 0.36, Math.sin(t0) * 0.36, 28), r1_ = P(Math.cos(t1) * 0.36, Math.sin(t1) * 0.36, 28);
    roof.push({ y: (r0[1] + r1_[1]) / 2, svg: poly([tip, r0, r1_], i % 2 ? "#c35b4e" : shade("#c35b4e", 0.12)) });
  }
  roof.sort((p, q) => p.y - q.y);
  return box({ a, b: a, h: 2, c: "#8fcf7d", t: "var(--t-grass-a)", l: "#79b465", r: "#69a356" })
    + path(-a, a, -0.12, 0.12) + path(-0.12, 0.12, -a, a)
    + bed.join("")
    + tree(-0.72, -0.72) + tree(0.72, -0.72, true) + tree(-0.72, 0.72, true)
    + cyl({ r: 0.32, z: 2, h: 4, c: "#e6dccb" })
    + pillars.filter((p) => p.d < 0).map((p) => p.svg).join("") + pillars.filter((p) => p.d >= 0).map((p) => p.svg).join("")
    + roof.map((r) => r.svg).join("") + blob(tip[0], tip[1] - 1, 1.8, "#ffd166")
    + tree(0.72, 0.72);
}
