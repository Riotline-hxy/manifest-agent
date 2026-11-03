/* @building {"name": "小图书馆", "cat": "build", "size": [1, 1], "price": 120, "lv": 9, "height": 44, "desc": "装着你读过的每一页"} */
// 小图书馆
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.35, b = 0.3, h = 28, wall = "#ece4d4";
  const cols = [-0.25, -0.12, 0.01, 0.14, 0.27].map((x) => poly(faceL(b + 0.03, x - 0.025, x + 0.025, 3, h - 2), "#fffdf7")).join("");
  return shadow(1.08)
    + box({ a: a + 0.04, b: b + 0.06, h: 3, c: "#c8bfae" })
    + box({ a, b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.16) })
    + poly(faceL(b + 0.002, -0.3, 0.32, 5, h - 3), shade(wall, -0.1))
    + win(faceL(b + 0.005, -0.21, -0.05, 9, 21), "#7a5a3a") + door(faceL(b + 0.005, 0.05, 0.19, 3, 18), "#6b4a8a")
    + cols
    + poly(faceL(b + 0.04, -a, a, h - 3, h), "#fffdf7")
    + win(faceR(a, -0.22, -0.04, 10, 21), "#7a5a3a") + win(faceR(a, 0.04, 0.22, 10, 21), "#7a5a3a")
    + roofX({ a, b: b + 0.04, z: h, rise: 11, o: 0.03, c: "#7d6cc9", wall: "#fffdf7" });
}
