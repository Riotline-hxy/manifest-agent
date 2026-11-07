/* @building {"name": "小花丛", "cat": "nature", "size": [1, 1], "price": 8, "lv": 1, "height": 12, "desc": "几朵不挑地方的小花"} */
// 小花丛
export default function draw(k, it = {}, ctx = {}) {
  const { P, pts, poly, line, shade, lerp, inset, faceL, faceR, box, roofX, roofY, win, door, shadow, smoke, cyl, blob, esc, TW, TH, r1 } = k;
  const spots = [[-10, 0, "#ff8fb1"], [-3, -4, "#ffd166"], [5, -2, "#ffffff"], [11, 1, "#b9a7ff"], [-5, 4, "#ffd166"], [3, 5, "#ff8fb1"], [9, -5, "#ff8fb1"]];
  return `<ellipse cx="0" cy="1" rx="17" ry="8.5" fill="#6fbe63" opacity=".55"/>`
    + spots.map(([x, y, c]) => `${line([x, y + 1], [x, y - 5], "#4f9a52", 1.2)}<circle cx="${x}" cy="${y - 6}" r="2.6" fill="${c}"/><circle cx="${x}" cy="${y - 6}" r="1" fill="#f7b93a"/>`).join("");
}
