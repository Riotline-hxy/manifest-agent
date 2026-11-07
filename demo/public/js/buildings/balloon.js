/* @building {"name": "热气球", "cat": "decor", "size": [1, 1], "price": 120, "lv": 14, "height": 82, "desc": "在小镇上空慢慢飘"} */
// 热气球
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  // 飘在自己那格上空：影子留在地上，球和吊篮一起慢慢上下。竖条纹用 clipPath 裁进球皮里
  const cy = -60;
  const shape = `M-16,${cy} A16 18 0 1 1 16,${cy} Q14,${cy + 10} 5,${cy + 19} L-5,${cy + 19} Q-14,${cy + 10} -16,${cy} Z`;
  const bands = ["#ff8a65", "#ffd166", "#ff8a65", "#7fd3c4", "#ff8a65", "#ffd166"]
    .map((c, k) => `<rect x="${-16 + k * 5.4}" y="${cy - 20}" width="5.6" height="40" fill="${c}"/>`).join("");
  return `<ellipse cx="0" cy="2" rx="12" ry="5.5" fill="url(#@@sh)" opacity=".7"/>`
    + `<g class="tw-float"><clipPath id="@@bl"><path d="${shape}"/></clipPath>`
    + `<g clip-path="url(#@@bl)">${bands}<rect x="-16" y="${cy - 20}" width="32" height="40" fill="url(#@@cyl)"/></g>`
    + `<path d="M-5,${cy + 19} L-4,${cy + 27} M5,${cy + 19} L4,${cy + 27}" stroke="#8a5d3b" stroke-width=".9"/>`
    + `<rect x="-5" y="${cy + 26}" width="10" height="7" rx="1.6" fill="#b27a4a"/><rect x="-5" y="${cy + 26}" width="10" height="2" rx="1" fill="#d39a62"/>`
    + `<ellipse cx="-7" cy="${cy - 9}" rx="3.6" ry="6" fill="rgba(255,255,255,.32)"/></g>`;
}
