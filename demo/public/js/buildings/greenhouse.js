/* @building {"name": "玻璃花房", "cat": "build", "size": [1, 1], "price": 110, "lv": 10, "height": 38, "desc": "冬天也有花开"} */
// 玻璃花房
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.32, b = 0.28, h = 20;
  const plants = [[-0.15, 0.05, "#5cb768"], [0.05, -0.08, "#ff8fb1"], [0.12, 0.1, "#5cb768"], [-0.05, 0.15, "#ffd166"]]
    .map(([x, y, c]) => { const p = P(x, y, 10); return blob(p[0], p[1], 5.5, c === "#5cb768" ? "url(#@@leaf)" : c) + blob(p[0] - 3, p[1] + 3, 4, "url(#@@leaf)"); }).join("");
  const grid = [];
  for (const x of [-0.16, 0, 0.16]) grid.push(line(P(x, b, 3), P(x, b, h), "#ffffff", 1, ' opacity=".8"'));
  for (const y of [-0.14, 0, 0.14]) grid.push(line(P(a, y, 3), P(a, y, h), "#ffffff", 1, ' opacity=".8"'));
  const A = a + 0.03, B = b + 0.03, z = h, rise = 13;
  return shadow(1)
    + box({ a: a + 0.02, b: b + 0.02, h: 3, c: "#c97c5d" })
    + plants
    + poly(faceL(b, -a, a, 3, h), "url(#@@glass)") + poly(faceR(a, -b, b, 3, h), "url(#@@glass)", ' opacity=".85"')
    + grid.join("")
    + poly([P(-A, 0, z + rise), P(A, 0, z + rise), P(A, B, z), P(-A, B, z)], "url(#@@glass)")
    + poly([P(a, -b, z), P(a, b, z), P(a, 0, z + rise)], "url(#@@glass)")
    + `<polyline points="${pts([P(-A, B, z), P(-A, 0, z + rise), P(A, 0, z + rise), P(A, B, z), P(-A, B, z)])}" fill="none" stroke="#ffffff" stroke-width="1.4" stroke-linejoin="round"/>`
    + line(P(a, -b, z), P(a, 0, z + rise), "#ffffff", 1.2) + line(P(0, 0, z + rise), P(0, B, z), "#ffffff", 1);
}
