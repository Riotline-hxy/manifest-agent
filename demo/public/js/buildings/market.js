/* @building {"name": "集市", "cat": "build", "size": [1, 2], "price": 160, "lv": 16, "height": 44, "desc": "一排小摊，周末最热闹", "enabled": true} */
// 集市：长条的木棚，条纹顶，长边上一溜摊位摆着水果和花。可以转 90°（k.w、k.d 对调）
export default function draw(k) {
  const { P, poly, shade, box, shadow, blob } = k;
  const ly = k.d > k.w;                        // 长边沿 y
  const a = k.w / 2 - 0.12, b = k.d / 2 - 0.12;
  const L = ly ? b : a, S = ly ? a : b;        // 长、短的一半
  const at = (t, s) => (ly ? { x: s, y: t } : { x: t, y: s });   // t 沿长边，s 沿短边
  const z = 26, rise = 12, o = 0.06;
  const cols = ["#ff8a65", "#fff4e6"];
  const n = 6, segs = [];
  for (let i = 0; i < n; i++) {
    const t0 = -L - o + ((2 * (L + o)) / n) * i, t1 = t0 + (2 * (L + o)) / n;
    const c = cols[i % 2];
    const Q = (t, s, zz) => { const q = at(t, s); return P(q.x, q.y, zz); };
    segs.push({ back: poly([Q(t0, -S - o, z), Q(t1, -S - o, z), Q(t1, 0, z + rise), Q(t0, 0, z + rise)], shade(c, 0.1)),
      front: poly([Q(t0, 0, z + rise), Q(t1, 0, z + rise), Q(t1, S + o, z), Q(t0, S + o, z)], ly ? shade(c, -0.12) : c) });
  }
  // 柱子：四个角 + 长边中间
  const posts = [];
  for (const t of [-L + 0.04, 0, L - 0.04]) for (const s of [-S + 0.04, S - 0.04]) {
    const q = at(t, s);
    posts.push({ d: q.x + q.y, svg: box({ x: q.x, y: q.y, a: 0.025, b: 0.025, z: 3, h: z - 3, c: "#a0704e" }) });
  }
  posts.sort((p, q) => p.d - q.d);
  // 长边朝外的那一侧摆摊：一个个矮柜台，上面放水果
  const fruit = ["#ff6b6b", "#ffd166", "#7fd36f", "#ff8a65", "#b9a7ff"];
  const stalls = [];
  for (let i = 0; i < 4; i++) {
    const t = -L + 0.22 + (i * (2 * L - 0.44)) / 3;
    const q = at(t, S - 0.16);
    stalls.push(box({ x: q.x, y: q.y, a: ly ? 0.07 : 0.16, b: ly ? 0.16 : 0.07, z: 3, h: 8, c: "#c98a4e" }));
    const top = P(q.x, q.y, 12);
    for (let j = 0; j < 3; j++) stalls.push(blob(top[0] - 5 + j * 5, top[1] + (j % 2) * 1.5, 2.4, fruit[(i + j) % fruit.length]));
  }
  const gableEnd = ly ? [at(L + o, -S - o), at(L + o, S + o), at(L + o, 0)] : [at(L + o, -S - o), at(L + o, S + o), at(L + o, 0)];
  return shadow(Math.max(k.w, k.d) * 0.92, 4)
    + box({ a: a + 0.04, b: b + 0.04, h: 3, c: "#d9c7a8" })
    + posts.filter((p) => p.d < 0).map((p) => p.svg).join("")
    + stalls.join("")
    + posts.filter((p) => p.d >= 0).map((p) => p.svg).join("")
    + segs.map((g) => g.back).join("") + segs.map((g) => g.front).join("")
    + poly([P(gableEnd[0].x, gableEnd[0].y, z), P(gableEnd[1].x, gableEnd[1].y, z), P(gableEnd[2].x, gableEnd[2].y, z + rise)], "#e8735a");
}
