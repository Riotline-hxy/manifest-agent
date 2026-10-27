// 背景预设：五种氛围，适配不同的人。主题只改颜色变量和背景场景，
// 版式、交互完全一致。登录前存在 localStorage，登录后写进画像（跨设备）。

export const THEMES = [
  { id: "forest", name: "森林夜", for: "想安静下来、专注的人", dark: true, agent: "#f7cb4d",
    swatch: ["#0d3528", "#2e8463", "#f7cb4d"] },
  { id: "midnight", name: "深空", for: "喜欢极简、常在夜里聊天的人", dark: true, agent: "#f2f2f4",
    swatch: ["#0e0e11", "#2a2a33", "#f2f2f4"] },
  { id: "paper", name: "晨光", for: "白天用、喜欢清爽干净的人", dark: false, agent: "#8b7cff",
    swatch: ["#f7f6f2", "#ffffff", "#8b7cff"] },
  { id: "peach", name: "暖阳", for: "需要被温柔鼓励的人", dark: false, agent: "#ff8a65",
    swatch: ["#fff2e8", "#ffd9c4", "#ff8a65"] },
  { id: "mist", name: "海雾", for: "容易紧张、想慢下来的人", dark: false, agent: "#5b9dff",
    swatch: ["#eef3f9", "#dbe6f5", "#5b9dff"] },
];

export const AGENT_COLORS = ["#f7cb4d", "#f2f2f4", "#8b7cff", "#ff8a65", "#4fd1a5", "#5b9dff", "#ff8fb1"];

const byId = Object.fromEntries(THEMES.map((t) => [t.id, t]));
export const themeOf = (id) => byId[id] || byId.forest;

let current = null;

export function applyTheme(id) {
  const t = themeOf(id || localStorage.getItem("xg-theme"));
  localStorage.setItem("xg-theme", t.id);
  document.documentElement.dataset.theme = t.id;
  document.documentElement.style.colorScheme = t.dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t.swatch[0]);
  if (current !== t.id) buildScene(t);
  current = t.id;
  return t;
}

export function agentColor(profile) {
  return (profile?.agent_hue && AGENT_COLORS.includes(profile.agent_hue)) ? profile.agent_hue
    : themeOf(profile?.theme || localStorage.getItem("xg-theme")).agent;
}

// 背景场景：每个主题一组装饰层。纯 CSS/DOM，不用图片。
function buildScene(t) {
  let s = document.querySelector(".scene");
  if (!s) {
    s = document.createElement("div");
    s.className = "scene";
    s.setAttribute("aria-hidden", "true");
    document.body.prepend(s);
  }
  let html = "";
  if (t.id === "forest") {
    html += '<i class="ray r1"></i><i class="ray r2"></i><i class="ray r3"></i><i class="ray r4"></i><i class="hill h1"></i><i class="hill h2"></i>';
    html += dust(24) + sparkles([[63, 13], [70, 34], [86, 30], [92, 62], [12, 20]]);
  } else if (t.id === "midnight") {
    html += '<i class="glow g1"></i>' + dust(10);
  } else if (t.id === "paper") {
    html += '<i class="glow g1"></i><i class="glow g2"></i>';
  } else if (t.id === "peach") {
    html += '<i class="sun"></i><i class="glow g1"></i><i class="glow g2"></i>' + dust(14);
  } else {
    html += '<i class="wave w1"></i><i class="wave w2"></i><i class="glow g1"></i>' + dust(10);
  }
  s.innerHTML = html;
}

function dust(n) {
  let h = "";
  for (let i = 0; i < n; i++) {
    const dur = 14 + Math.random() * 18;
    h += `<i class="dust" style="left:${Math.random() * 100}%;bottom:${Math.random() * 40 - 10}%;--dx:${(Math.random() - 0.5) * 120}px;` +
      `animation-duration:${dur}s;animation-delay:${-Math.random() * dur}s;opacity:${0.3 + Math.random() * 0.6}"></i>`;
  }
  return h;
}

function sparkles(list) {
  return list.map(([l, t]) => `<i class="sparkle" style="left:${l}%;top:${t}%;animation-delay:${-Math.random() * 3}s"></i>`).join("");
}
