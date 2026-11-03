/* @building {"name": "纪念碑", "cat": "decor", "size": [1, 1], "price": 0, "lv": 1, "height": 42, "desc": "到达里程碑那天，小镇送给你的", "gift": true} */
// 纪念碑
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const top = P(0, 0, 33);
  return shadow(0.55, 2)
    + box({ a: 0.17, b: 0.17, h: 5, c: "#c9c3d6" }) + box({ a: 0.11, b: 0.11, z: 5, h: 4, c: "#dcd6e6" })
    + poly([P(-0.07, 0.07, 9), P(0.07, 0.07, 9), P(0.035, 0.035, 30), P(-0.035, 0.035, 30)], "#ece7f3")
    + poly([P(0.07, -0.07, 9), P(0.07, 0.07, 9), P(0.035, 0.035, 30), P(0.035, -0.035, 30)], "#c9c1d9")
    + `<path class="tw-twinkle" d="M${top[0]},${top[1] - 6} l1.8,4 4,1.8 -4,1.8 -1.8,4 -1.8,-4 -4,-1.8 4,-1.8z" fill="#ffd166"/>`;
}
