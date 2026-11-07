/* @building {"name": "火车站", "cat": "build", "size": [1, 2], "price": 180, "lv": 25, "height": 54, "desc": "从这里出发，去更远的地方", "enabled": true} */
// 火车站：长边靠后的一半是砖红色的站房（拱窗、钟），前一半是带顶棚的站台。可以转 90°
export default function draw(k) {
  const { P, shade, faceL, faceR, box, roofX, roofY, win, door, shadow, line } = k;
  const ly = k.d > k.w;
  const A = k.w / 2 - 0.1, B = k.d / 2 - 0.1;
  const L = ly ? B : A, S = ly ? A : B;                    // 长、短的一半
  const at = (t, s) => (ly ? { x: s, y: t } : { x: t, y: s });
  const half = (lng, sht) => (ly ? { a: sht, b: lng } : { a: lng, b: sht });
  // 站房
  const hl = (L + 0.1) / 2 - 0.02, hc = at(-L + hl, 0), hd = half(hl, S - 0.08);
  const wall = "#d77a5f", h = 26;
  const face = (t0, t1, z0, z1) => (ly ? faceR(hd.a, t0, t1, z0, z1, hc.x, hc.y) : faceL(hd.b, t0, t1, z0, z1, hc.x, hc.y));
  const openings = [0.2, 0.5, 0.8].map((f, i) => {
    const t0 = -hl + 0.06 + f * (2 * hl - 0.12) - 0.065, t1 = t0 + 0.13;
    return i === 1 ? door(face(t0, t1, 3, 17), "#3f6f5a") : win(face(t0, t1, 8, 19), "#f4e6cf", { cross: false });
  }).join("");
  const clock = P(hc.x + (ly ? hd.a : 0), hc.y + (ly ? 0 : hd.b), 23);
  // 站台：两排柱子 + 平顶棚
  const pl = (L - 0.1) / 2, pc = at(0.1 + pl, 0), pd = half(pl, S - 0.04);
  const posts = [];
  for (const t of [-pl + 0.05, pl - 0.05]) for (const s of [-(S - 0.1), S - 0.1]) {
    const q = at(t, s);
    posts.push({ d: q.x + q.y, svg: box({ x: pc.x + q.x, y: pc.y + q.y, a: 0.022, b: 0.022, z: 3, h: 19, c: "#3f6f5a" }) });
  }
  posts.sort((p, q) => p.d - q.d);
  const bench = at(0.1 + pl, S - 0.22);
  return shadow(Math.max(k.w, k.d) * 0.95, 4)
    + box({ a: A, b: B, h: 3, c: "#cfc6b6" })
    + box({ x: pc.x, y: pc.y, a: pd.a, b: pd.b, z: 3, h: 2, c: "#e6dccb" })
    + posts.filter((p) => p.d < pc.x + pc.y).map((p) => p.svg).join("")
    + box({ x: bench.x, y: bench.y, a: ly ? 0.04 : 0.12, b: ly ? 0.12 : 0.04, z: 5, h: 4, c: "#c98a4e" })
    + box({ x: hc.x, y: hc.y, a: hd.a, b: hd.b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.18) })
    + openings
    + (ly ? roofY : roofX)({ x: hc.x, y: hc.y, a: hd.a, b: hd.b, z: h, rise: 13, c: "#3f6f5a", wall: shade(wall, -0.08) })
    + `<circle cx="${clock[0]}" cy="${clock[1]}" r="4.2" fill="#fffaf0" stroke="#3f6f5a" stroke-width="1.3"/>`
    + line(clock, [clock[0], clock[1] - 2.8], "#3f3a36", 1) + line(clock, [clock[0] + 2, clock[1]], "#3f3a36", 1)
    + posts.filter((p) => p.d >= pc.x + pc.y).map((p) => p.svg).join("")
    + box({ x: pc.x, y: pc.y, a: pd.a + 0.02, b: pd.b + 0.02, z: 22, h: 2.5, c: "#3f6f5a" });
}
