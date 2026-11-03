/* @building {"name": "钟楼", "cat": "build", "size": [1, 1], "price": 140, "lv": 18, "height": 96, "desc": "替你记着走过的每一天"} */
// 钟楼
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a = 0.2, b = 0.2, h = 54, wall = "#e9dfcd";
  const face = (z0) => {   // 钟面贴在朝左下的墙上：在墙的平面里画一个圆
    const ring = [];
    for (let k = 0; k < 20; k++) {
      const t = (k / 20) * Math.PI * 2;
      ring.push(P(Math.cos(t) * 0.13, b + 0.005, z0 + Math.sin(t) * 6.6));
    }
    const c = P(0, b + 0.005, z0), up = P(0, b + 0.005, z0 + 4.6), side = P(0.08, b + 0.005, z0);
    return `<polygon points="${pts(ring)}" fill="#fffaf0" stroke="#8a6a3c" stroke-width="1.4"/>`
      + line(c, up, "#4a3a2a", 1.3) + line(c, side, "#4a3a2a", 1.3) + `<circle cx="${c[0]}" cy="${c[1]}" r="1" fill="#4a3a2a"/>`;
  };
  return shadow(0.66)
    + box({ a: a + 0.04, b: b + 0.04, h: 5, c: "#cbbfa9" })
    + box({ a, b, z: 5, h: h - 5, c: wall, r: shade(wall, -0.17) })
    + door(faceL(b, -0.06, 0.07, 5, 16), "#7a5236")
    + win(faceR(a, -0.07, 0.07, 22, 32), "#8a6a3c", { cross: false })
    + face(h - 12)
    + box({ a: a + 0.02, b: b + 0.02, z: h, h: 3, c: "#d6c9b1" })
    + poly([P(-a - 0.02, b + 0.02, h + 3), P(a + 0.02, b + 0.02, h + 3), P(0, 0, h + 27)], "#5e7fc9")
    + poly([P(a + 0.02, -b - 0.02, h + 3), P(a + 0.02, b + 0.02, h + 3), P(0, 0, h + 27)], shade("#5e7fc9", -0.2))
    + line(P(0, 0, h + 27), P(0, 0, h + 34), "#8a6a3c", 1.2) + `<path d="M${P(0, 0, h + 34)[0]},${P(0, 0, h + 34)[1]} l7,2 -7,2z" fill="#ff8a65"/>`;
}
