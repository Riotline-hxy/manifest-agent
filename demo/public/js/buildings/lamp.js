/* @building {"name": "路灯", "cat": "decor", "size": [1, 1], "price": 15, "lv": 2, "height": 40, "desc": "天黑了会亮"} */
// 路灯
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const top = P(0, 0, 30);
  return shadow(0.28, 1.5)
    + `<circle class="tw-glow" cx="${top[0]}" cy="${top[1] + 3}" r="16" fill="url(#@@glow)"/>`
    + box({ a: 0.035, b: 0.035, h: 4, c: "#4a4f63" }) + box({ a: 0.016, b: 0.016, z: 4, h: 22, c: "#585e75" })
    + box({ a: 0.055, b: 0.055, z: 26, h: 7, c: "#fff1bf", l: "var(--t-win)", r: "var(--t-win)", t: "#fff7da" })
    + `<path d="M${top[0] - 6},${top[1] - 3} L${top[0]},${top[1] - 9} L${top[0] + 6},${top[1] - 3} Z" fill="#4a4f63"/>`;
}
