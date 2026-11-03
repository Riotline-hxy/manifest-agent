/* @building {"name": "风车", "cat": "build", "size": [1, 1], "price": 130, "lv": 12, "height": 70, "desc": "风一吹，就慢慢转起来"} */
// 风车
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const a0 = 0.24, a1 = 0.15, h = 40, wall = "#f4ead8";
  const L = [P(-a0, a0, 0), P(a0, a0, 0), P(a1, a1, h), P(-a1, a1, h)];
  const R = [P(a0, -a0, 0), P(a0, a0, 0), P(a1, a1, h), P(a1, -a1, h)];
  const hub = P(0.02, a1 + 0.06, h - 6);
  const blade = (deg) => `<g transform="rotate(${deg})"><rect x="-1.2" y="-27" width="2.4" height="27" fill="#8a5d3b"/><rect x="1.2" y="-26" width="6.5" height="19" fill="#fffaf0" stroke="#c9b79b" stroke-width=".8"/></g>`;
  return shadow(0.85)
    + poly(L, wall) + poly(R, shade(wall, -0.18))
    + door(faceL(a0 - 0.02, -0.06, 0.08, 0, 11), "#8a5d3b")
    + win([P(-0.05, a1 + 0.035, 22), P(0.06, a1 + 0.035, 22), P(0.06, a1 + 0.04, 29), P(-0.05, a1 + 0.04, 29)], "#8a5d3b", { cross: false })
    + roofY({ a: a1, b: a1, z: h, rise: 16, o: 0.04, c: "#c35b4e", wall: shade(wall, -0.04) })
    + `<g transform="matrix(.894 .447 0 1 ${hub[0]} ${hub[1]})"><g class="tw-blades">${[0, 90, 180, 270].map(blade).join("")}<circle r="2.6" fill="#6b4a33"/></g></g>`;
}
