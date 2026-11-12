/* @building {"name": "观星塔", "cat": "build", "size": [1, 1], "price": 130, "lv": 15, "height": 82, "desc": "离星星近一点"} */
// 观星塔
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const c = "#e1d8c6";
  const [sx, sy] = P(0, 0, 0);
  const rx = r1(0.25 * 0.7071 * TW), yt = sy - 50;
  return shadow(0.8)
    + cyl({ r: 0.29, h: 6, c: "#c9bfae" })
    + cyl({ r: 0.25, z: 6, h: 44, c })
    + `<path d="M${sx - 4},${sy - 18} v-6 a4 4 0 0 1 8 0 v6 z" fill="#7a5a3a"/><path d="M${sx - 2.8},${sy - 18.5} v-5.2 a2.8 2.8 0 0 1 5.6 0 v5.2 z" fill="var(--t-win)" class="tw-win"/>`
    + `<path d="M${sx + 4},${sy - 34} v-5 a3.4 3.4 0 0 1 6.8 0 v5 z" fill="#7a5a3a"/><path d="M${sx + 5.1},${sy - 34.4} v-4.4 a2.3 2.3 0 0 1 4.6 0 v4.4 z" fill="var(--t-win)" class="tw-win"/>`
    + `<ellipse cx="${sx}" cy="${yt}" rx="${rx + 3}" ry="${r1(rx * 0.5 + 1.5)}" fill="#a99a80"/>`
    + `<path d="M${sx - rx},${yt} A${rx} ${rx * 0.9} 0 0 1 ${sx + rx},${yt} A${rx} ${rx * 0.5} 0 0 1 ${sx - rx},${yt}Z" fill="url(#@@dome)"/>`
    + `<path d="M${sx - 3},${yt - rx * 0.88} A${rx * 0.4} ${rx * 0.9} 0 0 0 ${sx - 3},${yt + rx * 0.48}" fill="none" stroke="rgba(255,255,255,.28)" stroke-width="3"/>`
    + `<rect x="${sx + 2}" y="${yt - rx * 0.55}" width="13" height="4" rx="2" fill="#4a4f63" transform="rotate(-28 ${sx + 2} ${yt - rx * 0.4})"/>`
    + `<path class="tw-twinkle" d="M${sx + 18},${yt - 22} l1.4,3.2 3.2,1.4 -3.2,1.4 -1.4,3.2 -1.4,-3.2 -3.2,-1.4 3.2,-1.4z" fill="#ffe08a"/>`;
}
