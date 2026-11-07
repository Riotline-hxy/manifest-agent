/* @building {"name": "松树", "cat": "nature", "size": [1, 1], "price": 12, "lv": 2, "height": 48, "desc": "一年四季都绿着"} */
// 松树
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const tier = (yb, w, ht) => `<path d="M0,${yb - ht} L${-w},${yb} L0,${yb + w * 0.32} Z" fill="#62ad72"/><path d="M0,${yb - ht} L${w},${yb} L0,${yb + w * 0.32} Z" fill="#3e8458"/>`;
  return shadow(0.55, 3) + box({ a: 0.04, b: 0.04, h: 9, c: "#8a5d3b" })
    + `<g class="tw-sway">${tier(-8, 15, 18)}${tier(-19, 12, 17)}${tier(-29, 8.5, 15)}</g>`;
}
