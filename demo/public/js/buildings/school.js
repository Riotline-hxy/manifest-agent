/* @building {"name": "小学堂", "cat": "build", "size": [1, 2], "price": 170, "lv": 19, "height": 66, "desc": "屋顶的小钟每天响两次", "enabled": true} */
// 小学堂：长长一排教室，屋脊上一座小钟亭，旗杆。可以转 90°
export default function draw(k) {
  const { P, poly, shade, faceL, faceR, box, roofX, roofY, win, door, shadow, line } = k;
  const ly = k.d > k.w;
  const a = k.w / 2 - 0.16, b = k.d / 2 - 0.16;
  const h = 26, wall = "#f4ead6", trim = "#c76b4e";
  const wins = [];
  if (ly) {   // 长边是朝右下的那面（x = a）
    for (let i = 0; i < 4; i++) {
      const y0 = -b + 0.1 + i * ((2 * b - 0.2) / 4), y1 = y0 + 0.18;
      wins.push(i === 2 ? door(faceR(a, y0 + 0.02, y1 - 0.02, 3, 17), "#6b4a8a") : win(faceR(a, y0 + 0.02, y1 - 0.02, 10, 21), trim));
    }
    wins.push(win(faceL(b, -0.12, 0.12, 10, 21), trim));
  } else {    // 长边是朝左下的那面（y = b）
    for (let i = 0; i < 4; i++) {
      const x0 = -a + 0.1 + i * ((2 * a - 0.2) / 4), x1 = x0 + 0.18;
      wins.push(i === 1 ? door(faceL(b, x0 + 0.02, x1 - 0.02, 3, 17), "#6b4a8a") : win(faceL(b, x0 + 0.02, x1 - 0.02, 10, 21), trim));
    }
    wins.push(win(faceR(a, -0.12, 0.12, 10, 21), trim));
  }
  const roof = (ly ? roofY : roofX)({ a, b, z: h, rise: 16, c: "#4f7fa8", wall: shade(wall, -0.1) });
  // 屋脊中间的钟亭
  const bell = box({ a: 0.08, b: 0.08, z: h + 12, h: 10, c: "#f4ead6" })
    + poly([P(-0.1, 0.1, h + 22), P(0.1, 0.1, h + 22), P(0, 0, h + 31)], "#c76b4e")
    + poly([P(0.1, -0.1, h + 22), P(0.1, 0.1, h + 22), P(0, 0, h + 31)], shade("#c76b4e", -0.2))
    + `<circle cx="${P(0, 0.08, h + 15)[0]}" cy="${P(0, 0.08, h + 15)[1]}" r="2.2" fill="#f2c34b"/>`;
  const fp = ly ? { x: a + 0.08, y: b - 0.05 } : { x: a - 0.05, y: b + 0.08 };
  const top = P(fp.x, fp.y, 44);
  const flag = line(P(fp.x, fp.y, 0), top, "#8a8f9f", 1.3) + `<path class="tw-flag" d="M${top[0]},${top[1]} l10,2.5 -10,3.5 z" fill="#ff8a65"/>`;
  return shadow(Math.max(k.w, k.d) * 0.95, 4)
    + box({ a: a + 0.03, b: b + 0.03, h: 3, c: "#cbbfa9" })
    + box({ a, b, z: 3, h: h - 3, c: wall, r: shade(wall, -0.15) })
    + poly(ly ? faceR(a, -b, b, 3, 7) : faceL(b, -a, a, 3, 7), shade(trim, 0.15))
    + wins.join("") + roof + bell + flag;
}
