/* @building {"name": "圆冠树", "cat": "nature", "size": [1, 1], "price": 12, "lv": 1, "height": 46, "desc": "夏天能在下面乘凉"} */
// 圆冠树
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  return shadow(0.62, 3) + box({ a: 0.05, b: 0.05, h: 13, c: "#9a6b4b" })
    + `<g class="tw-sway">${blob(-8, -20, 10, "url(#@@leaf)")}${blob(8, -22, 11, "url(#@@leaf)")}${blob(0, -30, 14, "url(#@@leaf)")}
      <ellipse cx="-5" cy="-37" rx="5" ry="3" fill="rgba(255,255,255,.28)"/></g>`;
}
