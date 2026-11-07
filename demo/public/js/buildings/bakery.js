/* @building {"name": "面包房", "cat": "build", "size": [1, 1], "price": 90, "lv": 4, "height": 44, "desc": "每天早上都有刚出炉的香味"} */
// 面包房
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.31, b = 0.28, h = 24, wall = "#f7d9a8";
  const stripes = [];
  for (let i = 0; i < 6; i++) {
    const x0 = -0.27 + i * 0.09, x1 = x0 + 0.09;
    stripes.push(poly([P(x0, b, 17), P(x1, b, 17), P(x1, b + 0.13, 11), P(x0, b + 0.13, 11)], i % 2 ? "#fff6ea" : "#e0574f"));
  }
  const sp = P(a, 0.02, 15);
  const ch = box({ x: 0.1, y: -0.12, a: 0.045, b: 0.045, z: h + 3, h: 16, c: "#a66a52" });
  return shadow(0.98)
    + box({ a, b, h, c: wall, r: shade(wall, -0.17) })
    + win(faceL(b, -0.24, 0.04, 3, 14), "#9a6340", { cross: false })
    + `<g>${[[-0.2, 5.5], [-0.12, 5.5], [-0.04, 5.5]].map(([x, z]) => { const p = P(x, b + 0.01, z); return `<ellipse cx="${p[0]}" cy="${p[1]}" rx="3" ry="1.8" fill="#d99a4e"/>`; }).join("")}</g>`
    + door(faceL(b, 0.1, 0.24, 0, 13), "#9a6340")
    + stripes.join("")
    + `<circle cx="${sp[0]}" cy="${sp[1]}" r="5" fill="#fff6ea" stroke="#9a6340" stroke-width="1.2"/>`
    + `<path d="M${sp[0] - 3},${sp[1] + 0.6} q3,-4.5 6,0" fill="none" stroke="#d99a4e" stroke-width="2" stroke-linecap="round"/>`
    + roofY({ a, b, z: h, rise: 15, c: "#a8643f", wall: shade(wall, 0.02), mid: ch })
    + smoke(P(0.1, -0.12, h + 23));
}
