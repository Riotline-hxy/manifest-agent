/* @building {"name": "花店", "cat": "build", "size": [1, 1], "price": 75, "lv": 11, "height": 46, "desc": "门口摆满了今天开的花", "enabled": true} */
// 花店：粉色条纹雨棚，门口一排花桶
export default function draw(k) {
  const { P, poly, shade, faceL, faceR, box, roofY, win, door, shadow, blob } = k;
  const a = 0.29, b = 0.27, h = 22, wall = "#fbe6ea";
  const aw = [];
  for (let i = 0; i < 6; i++) {
    const x0 = -0.27 + i * 0.09, x1 = x0 + 0.09;
    aw.push(poly([P(x0, b, 17), P(x1, b, 17), P(x1, b + 0.12, 12), P(x0, b + 0.12, 12)], i % 2 ? "#fff6f8" : "#f28aa6"));
  }
  const pots = [-0.2, -0.06, 0.08].map((x, i) => {
    const p = P(x, b + 0.1, 0);
    const c = [["#ff8fb1", "#ffffff", "#ffd166"], ["#ffd166", "#ff8a65", "#ff8fb1"], ["#b9a7ff", "#ff8fb1", "#ffffff"]][i];
    return `<rect x="${p[0] - 3.2}" y="${p[1] - 5}" width="6.4" height="5" rx="1.2" fill="#a0704e"/>`
      + blob(p[0] - 1.6, p[1] - 7, 2.4, c[0]) + blob(p[0] + 1.7, p[1] - 7.4, 2.2, c[1]) + blob(p[0], p[1] - 9.6, 2, c[2]);
  }).join("");
  return shadow(0.98)
    + box({ a, b, h, c: wall, r: shade(wall, -0.15) })
    + win(faceL(b, -0.24, 0.02, 3, 13), "#c76b86", { cross: false })
    + door(faceL(b, 0.08, 0.22, 0, 13), "#c76b86")
    + aw.join("")
    + win(faceR(a, -0.16, 0.06, 9, 17), "#c76b86")
    + roofY({ a, b, z: h, rise: 14, c: "#7fbf8f", wall: shade(wall, 0.03) })
    + pots;
}
