/* @building {"name": "小池塘", "cat": "nature", "size": [1, 1], "price": 40, "lv": 5, "height": 0, "desc": "水面上漂着一片荷叶", "layer": "ground"} */
// 小池塘
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const stones = [];
  for (let k = 0; k < 11; k++) {
    const t = (k / 11) * Math.PI * 2;
    stones.push(`<ellipse cx="${r1(Math.cos(t) * 24)}" cy="${r1(Math.sin(t) * 11.6)}" rx="4.2" ry="2.6" fill="${k % 2 ? "#cfc7b7" : "#bdb4a3"}"/>`);
  }
  return `<ellipse cx="0" cy="0" rx="26" ry="12.8" fill="#a99f8c"/>` + stones.join("")
    + `<ellipse cx="0" cy="0" rx="21.5" ry="10" fill="url(#@@water)"/>`
    + `<path class="tw-water" d="M-11,-2 q4,-2 8,0 M3,3 q4,-2 8,0" fill="none" stroke="rgba(255,255,255,.7)" stroke-width="1.2" stroke-linecap="round"/>`
    + `<path d="M6,-3 a5 2.6 0 1 0 0.1,0 l-2.5,1.6z" fill="#5cb768"/><circle cx="8" cy="-4.5" r="1.6" fill="#ff8fb1"/>`;
}
