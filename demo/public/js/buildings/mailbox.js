/* @building {"name": "邮筒", "cat": "decor", "size": [1, 1], "price": 18, "lv": 4, "height": 28, "desc": "寄给未来的自己"} */
// 邮筒
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const p = P(0, 0, 22);
  return shadow(0.3, 1.5) + box({ a: 0.025, b: 0.025, h: 14, c: "#585e75" })
    + box({ a: 0.08, b: 0.06, z: 14, h: 9, c: "#e0574f" })
    + `<ellipse cx="${p[0] + 0.7}" cy="${p[1] + 0.5}" rx="5.6" ry="3" fill="${shade("#e0574f", 0.15)}"/>`
    + poly(faceL(0.061, -0.05, 0.03, 18, 19.6), "#7a2b26")
    + `<rect x="${p[0] + 5}" y="${p[1] - 2}" width="1.2" height="7" fill="#ffd166"/><rect x="${p[0] + 5}" y="${p[1] - 2}" width="4" height="2.6" fill="#ffd166"/>`;
}
