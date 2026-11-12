/* @building {"name": "花拱门", "cat": "decor", "size": [1, 1], "price": 30, "lv": 7, "height": 36, "desc": "从下面走过去，像进了另一段路"} */
// 花拱门
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  // 两根柱子 + 一道半圆，立在朝左下的那个面里；花沿着拱一路开过去
  const arc = [];
  for (let k = 0; k <= 12; k++) {
    const t = Math.PI * (1 - k / 12);
    arc.push(P(0.21 * Math.cos(t), 0.02, 21 + 10 * Math.sin(t)));
  }
  const flowers = arc.filter((_, k) => k % 2 === 0).map((q, k) => blob(q[0], q[1], 3.2, ["#ff8fb1", "#fff4f7", "#ffd166"][k % 3])).join("");
  const leaves = arc.filter((_, k) => k % 2).map((q) => blob(q[0], q[1] + 1, 2.6, "#5cb768")).join("");
  return shadow(0.5, 1.5)
    + box({ x: -0.21, y: 0.02, a: 0.025, b: 0.025, h: 22, c: "#f1e6d2" }) + box({ x: 0.21, y: 0.02, a: 0.025, b: 0.025, h: 22, c: "#f1e6d2" })
    + `<polyline points="${pts(arc)}" fill="none" stroke="#e9dcc4" stroke-width="3.4" stroke-linecap="round"/>`
    + `<polyline points="${pts(arc)}" fill="none" stroke="#fff8ec" stroke-width="1.2" stroke-linecap="round" opacity=".8"/>`
    + leaves + flowers
    + blob(P(-0.21, 0.04, 2)[0], P(-0.21, 0.04, 2)[1], 4, "url(#@@leaf)") + blob(P(0.21, 0.04, 2)[0], P(0.21, 0.04, 2)[1], 4, "url(#@@leaf)");
}
