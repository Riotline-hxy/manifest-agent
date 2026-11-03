/* @building {"name": "喷泉", "cat": "decor", "size": [1, 1], "price": 80, "lv": 8, "height": 30, "desc": "小镇广场的中心"} */
// 喷泉
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const [sx, sy] = P(0, 0, 0);
  const spray = (d) => `<path class="tw-spray" d="M${sx},${sy - 22} q${d * 8},-6 ${d * 14},12" fill="none" stroke="#bfe6ff" stroke-width="1.6" stroke-linecap="round"/>`;
  return shadow(1, 2)
    + cyl({ r: 0.4, h: 7, c: "#cfd6e0" })
    + `<ellipse cx="${sx}" cy="${sy - 7}" rx="${r1(0.34 * 0.7071 * TW)}" ry="${r1(0.34 * 0.7071 * TH)}" fill="url(#@@water)"/>`
    + `<path class="tw-water" d="M${sx - 10},${sy - 6} q4,-2 8,0 M${sx + 3},${sy - 9} q4,-2 8,0" fill="none" stroke="rgba(255,255,255,.7)" stroke-width="1.1" stroke-linecap="round"/>`
    + cyl({ r: 0.05, z: 7, h: 12, c: "#dde3ec" })
    + `<ellipse cx="${sx}" cy="${sy - 19}" rx="8" ry="3.4" fill="#cfd6e0"/><ellipse cx="${sx}" cy="${sy - 19.6}" rx="6.4" ry="2.4" fill="url(#@@water)"/>`
    + spray(-1) + spray(1) + `<circle class="tw-spray" cx="${sx}" cy="${sy - 25}" r="1.6" fill="#dff3ff"/>`;
}
