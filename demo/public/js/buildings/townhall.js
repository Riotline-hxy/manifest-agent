/* @building {"name": "镇公所", "cat": "build", "size": [2, 2], "price": 260, "lv": 28, "height": 92, "desc": "小镇的大事都在这儿商量", "enabled": true} */
// 镇公所：2×2。宽宽的主楼、正面一排柱子和台阶，中间升起一座带钟的塔楼，两边挂旗
export default function draw(k) {
  const { P, poly, shade, faceL, faceR, box, roofX, win, door, shadow, line } = k;
  const a = 0.78, b = 0.62, h = 30, wall = "#efe6d4";
  const cols = [];
  for (let i = 0; i < 6; i++) {
    const x = -0.62 + i * 0.248;
    cols.push(box({ x, y: b + 0.06, a: 0.03, b: 0.03, z: 6, h: h - 8, c: "#fffdf7" }));
  }
  const wins = [];
  for (let i = 0; i < 5; i++) {
    const x0 = -0.66 + i * 0.27;
    if (i !== 2) wins.push(win(faceL(b, x0 + 0.05, x0 + 0.17, 12, 24), "#8a6a3c"));
  }
  for (const y0 of [-0.5, -0.12, 0.26]) wins.push(win(faceR(a, y0, y0 + 0.16, 12, 24), "#8a6a3c"));
  const steps = [0, 1, 2].map((i) => box({ y: b + 0.14 - i * 0.03, a: 0.3 - i * 0.03, b: 0.05, z: i * 2, h: 2, c: shade("#d6cbb5", i * 0.05) })).join("");
  // 中间的塔楼 + 钟
  const tz = h, th = 26, ta = 0.2;
  const clock = [];
  for (let i = 0; i < 20; i++) {
    const t = (i / 20) * Math.PI * 2;
    clock.push(P(Math.cos(t) * 0.12, ta + 0.005, tz + 14 + Math.sin(t) * 6.2));
  }
  const c0 = P(0, ta + 0.005, tz + 14);
  const flag = (x, y) => { const t = P(x, y, h + 30); return line(P(x, y, h), t, "#8a8f9f", 1.3) + `<path class="tw-flag" d="M${t[0]},${t[1]} l11,2.6 -11,3.6 z" fill="#5b8fd9"/>`; };
  return shadow(1.95, 6)
    + box({ a: a + 0.06, b: b + 0.12, h: 3, c: "#cbbfa9" })
    + box({ a, b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.15) })
    + wins.join("") + door(faceL(b, -0.1, 0.1, 3, 21), "#6b4a8a")
    + steps + cols.join("")
    + poly(faceL(b + 0.09, -a, a, h - 4, h), "#fffdf7")
    + box({ a: a + 0.02, b: b + 0.02, z: h, h: 3, c: "#d6cbb5" })
    + flag(-a + 0.06, -b + 0.06)
    + box({ a: ta, b: ta, z: tz + 3, h: th, c: wall, r: shade(wall, -0.15) })
    + `<polygon points="${clock.map((p) => p.join(",")).join(" ")}" fill="#fffaf0" stroke="#8a6a3c" stroke-width="1.4"/>`
    + line(c0, P(0, ta + 0.005, tz + 18.5), "#4a3a2a", 1.4) + line(c0, P(0.08, ta + 0.005, tz + 14), "#4a3a2a", 1.4)
    + roofX({ a: ta, b: ta, z: tz + 3 + th, rise: 14, c: "#5b8fd9", wall: shade(wall, -0.15) })
    + flag(a - 0.06, b - 0.06);
}
