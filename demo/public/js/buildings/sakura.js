/* @building {"name": "樱花树", "cat": "nature", "size": [1, 1], "price": 25, "lv": 7, "height": 48, "desc": "花瓣会慢慢落下来"} */
// 樱花树
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const petal = (x, d) => `<ellipse class="tw-petal" cx="${x}" cy="-24" rx="1.6" ry="1.1" fill="#ffc0d3" style="animation-delay:${d}s"/>`;
  return shadow(0.62, 3)
    + `<path d="M-2,2 Q-1,-8 -4,-14 M0,-9 Q4,-14 6,-18" stroke="#8a5d4b" stroke-width="3.2" fill="none" stroke-linecap="round"/>`
    + `<g class="tw-sway">${blob(-9, -20, 10, "url(#@@pink)")}${blob(8, -23, 10.5, "url(#@@pink)")}${blob(-1, -31, 13, "url(#@@pink)")}
      <ellipse cx="-5" cy="-37" rx="5" ry="3" fill="rgba(255,255,255,.35)"/></g>` + petal(-6, 0) + petal(7, 1.8) + petal(1, 3.4);
}
