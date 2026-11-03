/* @building {"name": "长椅", "cat": "decor", "size": [1, 1], "price": 15, "lv": 3, "height": 18, "desc": "走累了坐一会儿"} */
// 长椅
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const wood = "#c98a4e";
  return shadow(0.5, 1.5)
    + box({ x: -0.18, y: 0, a: 0.02, b: 0.06, h: 6, c: "#585e75" }) + box({ x: 0.18, y: 0, a: 0.02, b: 0.06, h: 6, c: "#585e75" })
    + box({ x: 0, y: -0.06, a: 0.24, b: 0.012, z: 6, h: 9, c: shade(wood, -0.05) })
    + box({ a: 0.24, b: 0.08, z: 6, h: 2, c: wood });
}
