/* @building {"name": "小镇路牌", "cat": "decor", "size": [1, 1], "price": 0, "lv": 1, "height": 32, "desc": "写着小镇的名字", "gift": true} */
// 小镇路牌
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const name = (ctx?.name || "我的小镇").slice(0, 5);
  return shadow(0.45, 1.5) + box({ x: -0.14, a: 0.018, b: 0.018, h: 20, c: "#8a5d3b" }) + box({ x: 0.14, a: 0.018, b: 0.018, h: 20, c: "#8a5d3b" })
    + `<g transform="translate(0,-21)"><rect x="-21" y="-9" width="42" height="15" rx="3.5" fill="#a8744c"/><rect x="-19" y="-7.5" width="38" height="12" rx="2.5" fill="#e7c48f"/>
      <text x="0" y="1.6" text-anchor="middle" font-size="${name.length > 4 ? 6.4 : 7.6}" font-weight="800" fill="#6b4529">${esc(name)}</text></g>`;
}
