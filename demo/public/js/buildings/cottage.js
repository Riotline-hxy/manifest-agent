/* @building {"name": "小木屋", "cat": "build", "size": [1, 1], "price": 40, "lv": 1, "height": 44, "desc": "小镇的第一盏灯，从这里亮起来"} */
// 小木屋
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.27, b = 0.25, h = 20, wall = "#f3dcb6";
  const ch = box({ x: -0.12, y: -0.1, a: 0.045, b: 0.045, z: h + 4, h: 15, c: "#b9705a" });
  return shadow(0.85)
    + box({ a, b, h, c: wall, r: shade(wall, -0.16) })
    + line(P(-a, b, 7), P(a, b, 7), "rgba(140,90,50,.18)") + line(P(-a, b, 13), P(a, b, 13), "rgba(140,90,50,.18)")
    + door(faceL(b, -0.06, 0.09, 0, 12.5))
    + win(faceR(a, -0.13, 0.07, 8, 15.5))
    + roofX({ a, b, z: h, rise: 15, c: "#d4664a", wall: shade(wall, -0.16), mid: ch })
    + smoke(P(-0.12, -0.1, h + 22));
}
