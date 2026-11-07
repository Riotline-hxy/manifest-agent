/* @building {"name": "圆灌木", "cat": "nature", "size": [1, 1], "price": 6, "lv": 1, "height": 20, "desc": "圆滚滚的一团绿"} */
// 圆灌木
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  return shadow(0.5, 2) + blob(-6, -5, 7, "url(#@@leaf)") + blob(6, -5, 7.5, "url(#@@leaf)") + blob(0, -10, 8.5, "url(#@@leaf)")
    + blob(-3, -12, 1.6, "#ff6b6b") + blob(5, -7, 1.6, "#ff6b6b") + blob(-7, -4, 1.4, "#ff6b6b")
    + `<ellipse cx="-3" cy="-14" rx="3.5" ry="2" fill="rgba(255,255,255,.25)"/>`;
}
