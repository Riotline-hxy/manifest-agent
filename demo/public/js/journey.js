// 成长轨迹看板的「主题」：六类愿望共用同一张看板，只在右上角的愿景图形和点亮瞬间时的
// 小动效上有区别（文档 §四、§五：一个主色系，主题靠少量图形和动效区分）。
// 图形都是线描，和界面的线性图标同一种笔触；颜色跟随当前氛围的强调色。

export const VIEW_W = 1000;
export const VIEW_H = 520;
// 固定的柔和曲线：从左下「现在的我」到右上「向往的我」。它是时间轴，不是进度条。
export const CURVE = "M150,452 C240,446 280,392 340,364 C400,336 450,344 515,316 C580,288 630,270 690,268 C760,266 752,214 792,192 C832,170 850,158 862,140";
export const T0 = 0.05;
export const T1 = 0.93;

export const CATS = {
  calm: { label: "心灵平静", icon: "wind", color: "var(--c-sky)", fx: "ripple",
    prompts: ["今天有哪一刻让你慢下来了？", "什么让你紧张，你是怎么照顾自己的？", "睡前，想放下的一件事是？"] },
  wealth: { label: "财富与事业", icon: "sparkles", color: "var(--c-lemon)", fx: "coins",
    prompts: ["今天学到或推进了什么？", "有没有一个新机会、新的联系？", "做了哪件让你更有选择的小事？"] },
  body: { label: "理想身材与健康", icon: "leaf", color: "var(--c-mint)", fx: "stretch",
    prompts: ["今天身体做了什么让你喜欢的事？", "睡得怎么样？醒来时什么感觉？", "哪一顿饭让身体觉得舒服？"] },
  confidence: { label: "自信与自我接纳", icon: "star", color: "var(--c-violet)", fx: "stars",
    prompts: ["今天哪一刻你说出了自己的想法？", "做了哪件有点怕、但还是做了的事？", "今天对自己说了一句什么好话？"] },
  relation: { label: "亲密关系与人际", icon: "heart", color: "var(--c-pink)", fx: "link",
    prompts: ["今天和谁有一次好的交流？", "你说出了自己的什么需要？", "有没有一个让你觉得被理解的瞬间？"] },
  freedom: { label: "生活方式与自由", icon: "sun", color: "var(--c-coral)", fx: "window",
    prompts: ["今天有哪一刻是按自己的节奏过的？", "做了一件新鲜事吗？", "哪个瞬间让你觉得自在？"] },
  other: { label: "其他愿望", icon: "compass", color: "var(--c-orange)", fx: "glow",
    prompts: ["今天离想要的自己近了一点的瞬间？", "做了什么让你满意的小事？", "此刻最想记住的是什么？"] },
};
export const catOf = (id) => CATS[id] || CATS.other;
export const MOODS = ["平静", "开心", "紧张", "疲惫", "温暖", "骄傲", "有点难过"];

// 右上角「向往的我」：每类一个线描小图
const S = 'fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"';
export function visionSVG(cat, cls = "") {
  const g = {
    calm: `<circle cx="60" cy="40" r="15"/><path d="M22,74 q9,-6 19,0 t19,0 t19,0 t19,0"/><path d="M32,88 q7,-5 14,0 t14,0 t14,0 t14,0" opacity=".6"/>`,
    wealth: `<ellipse cx="54" cy="88" rx="24" ry="7"/><path d="M30,88 v-10 M78,88 v-10"/><ellipse cx="54" cy="78" rx="24" ry="7"/><path d="M30,78 v-10 M78,78 v-10"/><ellipse cx="54" cy="68" rx="24" ry="7"/>
      <path d="M92,24 l3,8 8,3 -8,3 -3,8 -3,-8 -8,-3 8,-3z"/>`,
    body: `<circle cx="60" cy="26" r="9"/><path d="M60,37 L60,72 M60,46 L42,28 M60,46 L78,28 M60,72 L47,98 M60,72 L73,98"/><path d="M28,104 h64" opacity=".5"/>`,
    confidence: `<path d="M60,24 l9.5,19.5 21.5,3 -15.5,15 3.7,21.4 -19.2,-10.1 -19.2,10.1 3.7,-21.4 -15.5,-15 21.5,-3z"/><path d="M98,18 l2,5 5,2 -5,2 -2,5 -2,-5 -5,-2 5,-2z"/>`,
    relation: `<circle cx="44" cy="52" r="9"/><circle cx="76" cy="52" r="9"/><path d="M28,96 q16,-36 32,0 M60,96 q16,-36 32,0"/><path d="M60,32 c-4,-7 -14,-4 -10,4 l10,9 10,-9 c4,-8 -6,-11 -10,-4z"/>`,
    freedom: `<path d="M30,100 L30,58 A30,30 0 0 1 90,58 L90,100 Z"/><circle cx="60" cy="70" r="8"/>
      <g class="pane pane-l"><path d="M30,100 L30,58 A30,30 0 0 1 60,28 L60,100 Z" fill="var(--surface-3)"/></g>
      <g class="pane pane-r"><path d="M90,100 L90,58 A30,30 0 0 0 60,28 L60,100 Z" fill="var(--surface-3)"/></g>`,
    other: `<circle cx="60" cy="58" r="17"/><path d="M60,26 v-8 M84,34 l6,-6 M36,34 l-6,-6 M92,58 h8 M20,58 h8"/>`,
  }[cat] || "";
  return `<svg class="vision ${cls}" viewBox="0 0 120 120" ${S}>${g}</svg>`;
}

// 左下「现在的我」：一个抱膝坐着的小人（线描），永远留在起点
export function figureSVG() {
  return `<g class="figure">
    <path class="ground" d="M8,100 Q100,86 196,100" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" opacity=".35"/>
    <g class="fig-body">
      <circle class="f-head" cx="66" cy="26" r="13"/>
      <path class="f-body" d="M56,44 C47,54 44,72 47,88 C48,94 52,97 58,97 L104,97 C110,97 112,90 107,87 L92,79 C97,72 98,62 93,56 C88,50 80,49 74,52 C70,48 63,43 56,44 Z"/>
      <path class="f-arm" d="M64,58 C70,68 80,73 92,72" fill="none" stroke-width="5" stroke-linecap="round"/>
    </g></g>`;
}

// ---------------------------------------------------------------- 点亮瞬间的小动效 ----
// 都很短（≤1.2s），不挡住记录卡片；系统「减少动态效果」打开时，CSS 会把它们压成瞬间完成。
export function playFx(kind, board, dot, ctx = {}) {
  const layer = board.querySelector(".j-fx");
  if (!layer || !dot) return;
  // 减少动态效果：只留一圈静态光晕，信息照样完整
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) kind = "glow";
  const br = layer.getBoundingClientRect();
  const r = dot.getBoundingClientRect();
  const x = r.left - br.left + r.width / 2, y = r.top - br.top + r.height / 2;
  const add = (cls, style = "") => {
    const el = document.createElement("i");
    el.className = cls;
    el.style.cssText = `left:${x}px;top:${y}px;${style}`;
    layer.append(el);
    setTimeout(() => el.remove(), 1600);
    return el;
  };
  if (kind === "ripple") {
    for (let i = 0; i < 3; i++) add("fx-ring", `animation-delay:${i * 180}ms`);
  } else if (kind === "coins") {
    for (let i = 0; i < 9; i++) {
      const el = add("fx-coin");
      el.animate([{ transform: "translate(-50%,-50%) scale(.4)", opacity: 0 },
        { transform: `translate(calc(-50% + ${(Math.random() - 0.5) * 50}px), calc(-50% - ${18 + Math.random() * 22}px)) scale(1)`, opacity: 1, offset: 0.3 },
        { transform: `translate(calc(-50% + ${(Math.random() - 0.5) * 90}px), calc(-50% + ${40 + Math.random() * 40}px)) scale(.8)`, opacity: 0 }],
        { duration: 1000 + Math.random() * 300, easing: "cubic-bezier(.3,.6,.5,1)", delay: i * 40, fill: "both" });
    }
  } else if (kind === "stars") {
    for (let i = 0; i < 7; i++) {
      const a = (i / 7) * Math.PI * 2;
      const el = add("fx-star");
      el.animate([{ transform: "translate(-50%,-50%) scale(0)", opacity: 0 },
        { transform: `translate(calc(-50% + ${Math.cos(a) * 34}px), calc(-50% + ${Math.sin(a) * 34}px)) scale(1)`, opacity: 1, offset: 0.5 },
        { transform: `translate(calc(-50% + ${Math.cos(a) * 46}px), calc(-50% + ${Math.sin(a) * 46}px)) scale(.4)`, opacity: 0 }],
        { duration: 1100, easing: "ease-out", fill: "both" });
    }
  } else if (kind === "stretch") {
    board.querySelector(".figure")?.classList.remove("stretch");
    void board.offsetWidth;
    board.querySelector(".figure")?.classList.add("stretch");
    const lit = board.querySelector(".curve-lit");
    if (lit && ctx.frac != null) {
      const len = lit.getTotalLength();
      lit.style.strokeDasharray = `${len * ctx.frac} ${len}`;
      lit.classList.remove("on"); void lit.offsetWidth; lit.classList.add("on");
    }
  } else if (kind === "link") {
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "fx-links");
    svg.setAttribute("viewBox", `0 0 ${br.width} ${br.height}`);
    for (const n of ctx.neighbors || []) {
      const nr = n.getBoundingClientRect();
      const line = document.createElementNS(svgNS, "path");
      const nx = nr.left - br.left + nr.width / 2, ny = nr.top - br.top + nr.height / 2;
      line.setAttribute("d", `M${x},${y} Q${(x + nx) / 2},${Math.min(y, ny) - 30} ${nx},${ny}`);
      svg.append(line);
    }
    layer.append(svg);
    setTimeout(() => svg.remove(), 1500);
    add("fx-heart");
  } else if (kind === "window") {
    const v = board.querySelector(".j-vision");
    v?.classList.remove("open"); void v?.offsetWidth; v?.classList.add("open");
    setTimeout(() => v?.classList.remove("open"), 1600);
    add("fx-glow");
  } else {
    add("fx-glow");
  }
}
