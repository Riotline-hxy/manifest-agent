/* @building {"name": "小镇路牌", "cat": "decor", "size": [1, 1], "price": 0, "lv": 1, "height": 32, "desc": "写着小镇的名字", "gift": true} */
// 小镇路牌：两根木桩插进草地里（桩脚各一小圈土），周围冒出几簇草；木板有厚度，名字刷在朝外的那一面上。
// 转过来时（k.mirror）整块牌子朝右下，字跟着那一面斜过去，还是从左往右读。
export default function draw(k, it = {}, ctx = {}) {
  const { P, poly, line, shade, faceL, box, shadow, esc, r1 } = k;
  const name = (ctx?.name || "我的小镇").slice(0, 5);
  const m = !!k.mirror;
  const post = "#7a4f31", wood = "#c48a55";
  // 每根桩脚下一小圈翻起来的土：桩是插进地里的
  const mound = [-0.3, 0.3].map((x) => {
    const [cx, cy] = P(x, 0);
    return `<ellipse cx="${cx}" cy="${r1(cy + 0.6)}" rx="6.4" ry="3" fill="#5e4430" opacity=".45"/>`
      + `<ellipse cx="${cx}" cy="${cy}" rx="5.2" ry="2.5" fill="#94704b"/>`
      + `<ellipse cx="${r1(cx - 1)}" cy="${r1(cy - 0.5)}" rx="3" ry="1.1" fill="#b08a60" opacity=".8"/>`;
  }).join("");
  // 几簇草：两三片叶子，从土边上冒出来
  const tuft = (u, v, s = 1) => {
    const [x, y] = P(u, v);
    return `<path d="M${x},${y} q${-1.2 * s},${-3.6 * s} ${-3 * s},${-5 * s} M${x},${y} q${0.2 * s},${-4.4 * s} ${0.8 * s},${-6.4 * s} M${x},${y} q${1.4 * s},${-3 * s} ${3.4 * s},${-4.2 * s}"`
      + ` fill="none" stroke="#4f9e5a" stroke-width="1.3" stroke-linecap="round"/>`;
  };
  const posts = [-0.3, 0.3].map((x) => box({ x, y: 0, a: 0.032, b: 0.032, z: -1, h: 25, c: post })
    + poly([P(x - 0.032, 0.032, 24), P(x + 0.032, 0.032, 24), P(x, 0, 26.5)], shade(post, 0.1))).join("");
  // 木板：有厚度的一块，正面一圈深色的边，中间浅色刷字
  const by = 0.07, bb = 0.026;
  const board = box({ x: 0, y: by, a: 0.42, b: bb, z: 9.5, h: 13.5, c: wood, t: shade(wood, 0.25) });
  const panel = poly(faceL(by + bb + 0.002, -0.37, 0.37, 11, 21.5), m ? "#d9b985" : "#efd5a2");
  const nails = [[-0.39, 20.8], [0.39, 20.8], [-0.39, 11.6], [0.39, 11.6]]
    .map(([u, z]) => { const [x, y] = P(u, by + bb + 0.004, z); return `<circle cx="${x}" cy="${y}" r=".7" fill="#6b4529" opacity=".75"/>`; }).join("");
  const [tx, ty] = P(0, by + bb + 0.004, 16.2);
  const fs = name.length > 4 ? 5.2 : name.length > 3 ? 6.2 : 7.2;
  const text = `<g transform="translate(${tx},${ty}) skewY(${m ? -26.565 : 26.565})"><text x="0" y="${r1(fs * 0.36)}" text-anchor="middle" font-size="${fs}" font-weight="800" fill="#6b4529">${esc(name)}</text></g>`;
  const grain = line(P(-0.4, by + bb + 0.003, 10.4), P(0.4, by + bb + 0.003, 10.4), "rgba(90,55,30,.25)", 0.8);
  return shadow(0.62, 1.5) + mound
    + tuft(-0.36, -0.12, 0.85) + tuft(0.22, -0.14, 0.8)
    + posts + board + panel + grain + nails + text
    + tuft(-0.42, 0.1) + tuft(0.38, 0.14, 0.9) + tuft(0.05, 0.3, 1.05) + tuft(-0.18, 0.36, 0.7);
}
