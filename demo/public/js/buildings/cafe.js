/* @building {"name": "街角咖啡", "cat": "build", "size": [1, 1], "price": 95, "lv": 6, "height": 36, "desc": "适合坐一个下午"} */
// 街角咖啡
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.31, b = 0.29, h = 24, wall = "#9fd8c8";
  const aw = [];
  for (let i = 0; i < 6; i++) {
    const x0 = -0.28 + i * 0.093, x1 = x0 + 0.093;
    aw.push(poly([P(x0, b, 18), P(x1, b, 18), P(x1, b + 0.12, 13), P(x0, b + 0.12, 13)], i % 2 ? "#fffaf0" : "#3fa27f"));
  }
  const cup = P(a, 0, 16);
  return shadow(1)
    + box({ a, b, h, c: wall, r: shade(wall, -0.18) })
    + win(faceL(b, -0.25, 0.05, 2, 13), "#ffffff")
    + door(faceL(b, 0.1, 0.24, 0, 13), "#3f7f6c")
    + aw.join("")
    + win(faceR(a, -0.2, 0.0, 6, 14), "#ffffff", { cross: false })
    + `<g transform="translate(${cup[0] + 7},${cup[1] - 1})"><rect x="-4" y="-3" width="7" height="6" rx="1.5" fill="#fffaf0"/><path d="M3,-1.5 q2.5,1.5 0,3" fill="none" stroke="#fffaf0" stroke-width="1.2"/></g>`
    + box({ a: a + 0.02, b: b + 0.02, z: h, h: 3, c: "#f5efe3" })
    + box({ x: -0.1, y: -0.06, a: 0.12, b: 0.1, z: h + 3, h: 4, c: "#e8e0d0" })
    + box({ x: -0.2, y: b - 0.01, a: 0.1, b: 0.015, z: h + 3, h: 7, c: "#f5efe3" });
}
