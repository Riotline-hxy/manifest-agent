/* @building {"name": "冰淇淋车", "cat": "decor", "size": [1, 1], "price": 40, "lv": 13, "height": 42, "desc": "夏天的傍晚会停在这儿", "enabled": true} */
// 冰淇淋车：小推车 + 条纹遮阳伞
export default function draw(k) {
  const { P, poly, shade, faceL, box, shadow, blob, line } = k;
  const a = 0.21, b = 0.13;
  const wheel = (x) => { const p = P(x, b + 0.01, 3.5); return `<circle cx="${p[0]}" cy="${p[1]}" r="3.6" fill="#4a4f63"/><circle cx="${p[0]}" cy="${p[1]}" r="1.4" fill="#c9ccd6"/>`; };
  // 伞面：从伞尖往一圈边上切成 8 瓣，后面的先画
  const tip = P(0, 0, 40), wedges = [];
  for (let i = 0; i < 8; i++) {
    const t0 = (i / 8) * Math.PI * 2, t1 = ((i + 1) / 8) * Math.PI * 2;
    const r0 = P(Math.cos(t0) * 0.3, Math.sin(t0) * 0.3, 31), r1_ = P(Math.cos(t1) * 0.3, Math.sin(t1) * 0.3, 31);
    wedges.push({ y: (r0[1] + r1_[1]) / 2, svg: poly([tip, r0, r1_], i % 2 ? "#fff6f8" : "#ff8fb1") });
  }
  wedges.sort((p, q) => p.y - q.y);
  const cone = P(-0.06, b + 0.01, 21);
  return shadow(0.55, 2)
    + box({ a, b, z: 4, h: 13, c: "#fff3e0", r: "#f3dcc0" })
    + poly(faceL(b, -a, a, 9, 12), "#ff8fb1")
    + wheel(-0.13) + wheel(0.13)
    + line(P(0, 0, 17), P(0, 0, 39), "#8a8f9f", 1.4)
    + wedges.map((w) => w.svg).join("")
    + `<path d="M${cone[0] - 3},${cone[1] - 2} L${cone[0]},${cone[1] + 5} L${cone[0] + 3},${cone[1] - 2} Z" fill="#d99a4e"/>`
    + blob(cone[0], cone[1] - 3.5, 3.2, "#ffe0ec") + blob(cone[0] + 0.8, cone[1] - 6.4, 1, "#ff6b6b");
}
