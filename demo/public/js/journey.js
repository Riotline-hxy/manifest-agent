// 蜕变计划的愿望类别、细线图形（选方向时的愿景、空状态的小人）和点亮动效。
// 所有线条同一种笔触（圆头、细线、一点光晕），颜色跟随当前氛围。

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

const S = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';

// 起点的小人：盘腿坐着，安静地看向前方
export function figureSVG() {
  return `<svg class="j-figure" viewBox="0 0 60 60" ${S} aria-hidden="true">
    <g class="fig">
      <circle cx="30" cy="12" r="6.5"/>
      <path d="M26,21 C21.5,22.5 19.5,26.5 19.5,31.5 L19.5,40"/>
      <path d="M34,21 C38.5,22.5 40.5,26.5 40.5,31.5 L40.5,40"/>
      <path d="M19.5,33 C21.5,38 25,41 30,41 C35,41 38.5,38 40.5,33"/>
      <path d="M19.5,40 C13,41.5 9.5,44.5 10.5,47.5 C11.5,50.5 18,50.5 30,48.5 C42,50.5 48.5,50.5 49.5,47.5 C50.5,44.5 47,41.5 40.5,40"/>
      <path d="M22,46 C26,45 34,45 38,46" opacity=".55"/>
    </g></svg>`;
}

// 终点的愿景：每类一个线描图形
export function visionSVG(cat, cls = "") {
  const g = {
    calm: `<path d="M36,56 A24,24 0 0 1 84,56"/><path d="M60,22 v-6 M38,32 l-4,-4 M82,32 l4,-4" opacity=".7"/><path d="M22,58 H98"/><path d="M34,66 H86" opacity=".75"/><path d="M46,74 H74" opacity=".5"/>`,
    wealth: `<path d="M22,88 L46,58 L60,70 L84,38 L98,38"/><path d="M88,30 L98,38 L90,48"/><path d="M22,96 H98" opacity=".5"/><path d="M40,30 l2.5,6 6,2.5 -6,2.5 -2.5,6 -2.5,-6 -6,-2.5 6,-2.5z" opacity=".8"/>`,
    body: `<path d="M60,92 C40,78 22,64 22,46 C22,34 31,26 41,26 C49,26 55,30 60,37 C65,30 71,26 79,26 C89,26 98,34 98,46 C98,64 80,78 60,92Z"/>
      <path d="M30,58 H46 L52,46 L60,70 L67,52 L72,58 H90" opacity=".85"/><path d="M98,18 l2,5 5,2 -5,2 -2,5 -2,-5 -5,-2 5,-2z" opacity=".7"/>`,
    confidence: `<path d="M60,22 l9,18.5 20.5,3 -14.8,14.4 3.5,20.4 -18.2,-9.6 -18.2,9.6 3.5,-20.4 -14.8,-14.4 20.5,-3z"/><path d="M96,20 l2,5 5,2 -5,2 -2,5 -2,-5 -5,-2 5,-2z" opacity=".75"/><path d="M28,88 H92" opacity=".45"/>`,
    relation: `<circle cx="44" cy="50" r="8"/><circle cx="76" cy="50" r="8"/><path d="M28,92 C30,74 58,74 60,92 M60,92 C62,74 90,74 92,92"/><path d="M60,34 c-3,-6 -12,-4 -9,3 l9,8 9,-8 c3,-7 -6,-9 -9,-3z"/>`,
    freedom: `<path d="M32,98 V56 A28,28 0 0 1 88,56 V98 Z"/><path d="M60,28 V98 M32,64 H88" opacity=".6"/>
      <g class="pane pane-l"><path d="M32,98 V56 A28,28 0 0 1 60,28 V98 Z" fill="var(--surface-2)"/></g>
      <g class="pane pane-r"><path d="M88,98 V56 A28,28 0 0 0 60,28 V98 Z" fill="var(--surface-2)"/></g>`,
    other: `<circle cx="60" cy="56" r="16"/><path d="M60,28 v-8 M84,34 l6,-6 M36,34 l-6,-6 M92,56 h8 M20,56 h8" opacity=".75"/><path d="M28,90 H92" opacity=".45"/>`,
  }[cat] || "";
  return `<svg class="vision ${cls}" viewBox="0 0 120 120" ${S}>${g}</svg>`;
}

// ---------------------------------------------------------------- 点亮节点的小动效 ----
// 都很短（≤1.2s），不挡住随后打开的卡片；系统「减少动态效果」打开时只留一圈静态光晕。
export function playFx(kind, board, dot, ctx = {}) {
  const layer = board.querySelector(".j-fx");
  if (!layer || !dot) return;
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
    const f = board.querySelector(".j-start .fig");
    f?.classList.remove("stretch"); void board.offsetWidth; f?.classList.add("stretch");
    const lit = board.querySelector(".curve-lit");
    if (lit && ctx.frac != null) {
      const len = lit.getTotalLength();
      lit.style.strokeDasharray = `${len * ctx.frac} ${len}`;
      lit.classList.remove("on"); void lit.offsetWidth; lit.classList.add("on");
    }
    add("fx-glow");
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
    const v = board.querySelector(".j-goal");
    v?.classList.remove("open"); void v?.offsetWidth; v?.classList.add("open");
    setTimeout(() => v?.classList.remove("open"), 1600);
    add("fx-glow");
  } else {
    add("fx-glow");
  }
}
