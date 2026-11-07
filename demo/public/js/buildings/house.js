/* @building {"name": "蓝顶小屋", "cat": "build", "size": [1, 1], "price": 70, "lv": 3, "height": 48, "desc": "窗台上摆着一盆花"} */
// 蓝顶小屋
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.31, b = 0.27, h = 26, wall = "#f6f1e8";
  return shadow(0.98)
    + box({ x: 0, y: 0, a: a + 0.02, b: b + 0.02, h: 3, c: "#c9c2b6" })
    + box({ a, b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.14) })
    + door(faceL(b, 0.06, 0.2, 3, 16), "#4f78b8")
    + win(faceL(b, -0.23, -0.07, 11, 20), "#ffffff")
    + `<g>${[0, 1, 2, 3].map((i) => { const p = P(-0.21 + i * 0.045, b + 0.03, 10.5); return blob(p[0], p[1], 1.5, i % 2 ? "#ff8fb1" : "#ffd166"); }).join("")}</g>`
    + win(faceR(a, -0.18, -0.03, 11, 20), "#ffffff") + win(faceR(a, 0.05, 0.19, 11, 20), "#ffffff")
    + roofX({ a, b, z: h, rise: 17, c: "#5b8fd9", wall: shade(wall, -0.14) });
}
