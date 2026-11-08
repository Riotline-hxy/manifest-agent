// 小工具：DOM 构建、转义、时间、toast、sheet。

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// 允许很小子集的 markdown：段落、**粗体**
export function richText(s) {
  const safe = esc(s);
  return safe
    .split(/\n{2,}/)
    .map((p) => listBlocks(p.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")))
    .join("");
}

// 一段话里连着几行「1. 」「2. 」或「· 」「- 」开头的，画成列表（小光讲步骤、几个要点时会分行写）；其余照旧换行
const OL = /^\s*\d{1,2}[.、．]\s*/;
const UL = /^\s*[·•\-]\s+/;
function listBlocks(p) {
  const out = [];
  let text = [], list = null;
  const flushText = () => { if (text.length) out.push(`<p>${text.join("<br>")}</p>`); text = []; };
  const flushList = () => { if (list) out.push(`<${list.tag} class="txt-list">${list.items.map((x) => `<li>${x}</li>`).join("")}</${list.tag}>`); list = null; };
  for (const line of p.split("\n")) {
    const tag = OL.test(line) ? "ol" : UL.test(line) ? "ul" : "";
    if (tag) {
      flushText();
      if (list && list.tag !== tag) flushList();
      list = list || { tag, items: [] };
      list.items.push(line.replace(tag === "ol" ? OL : UL, ""));
    } else {
      flushList();
      text.push(line);
    }
  }
  flushText();
  flushList();
  return out.join("");
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// 用 HTML 字符串构建节点（视图里读起来更接近原来的排版）
export function frag(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content;
}

const TZ = "Asia/Shanghai";

export function fmtDay(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const same = (a, b) => a.toLocaleDateString("zh-CN", { timeZone: TZ }) === b.toLocaleDateString("zh-CN", { timeZone: TZ });
  if (same(d, now)) return "今天";
  const y = new Date(now.getTime() - 864e5);
  if (same(d, y)) return "昨天";
  return d.toLocaleDateString("zh-CN", { timeZone: TZ, month: "long", day: "numeric" });
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("zh-CN", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
}

export function dayKey(iso) {
  return (iso || "").slice(0, 10);
}

export function toast(msg, kind = "", ic = "") {
  let wrap = $(".toast-wrap");
  if (!wrap) {
    wrap = h("div", { class: "toast-wrap" });
    document.body.append(wrap);
  }
  const lead = ic ? h("span", { class: "toast-ic", html: icon(ic) }) : h("span", { class: "toast-av", html: window.__agentMini?.() || "" });
  const el = h("div", { class: `toast ${kind}` }, lead, h("span", {}, msg));
  wrap.append(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  }, 2600);
}

// 通用弹层：返回一个可以 close() 的句柄
export function sheet({ title, body, footer, onClose, sticker }) {
  const scrim = h("div", { class: "scrim" });
  const panel = h("section", { class: "sheet", role: "dialog", "aria-modal": "true" },
    h("header", {}, sticker ? h("span", { html: tile(sticker, "var(--accent)", 38) }) : null,
      h("h3", {}, title || ""), h("button", { class: "x", "aria-label": "关闭", onclick: close }, "×")),
    h("div", { class: "body" }, body),
    footer ? h("footer", {}, footer) : null,
  );
  function close() {
    scrim.remove();
    panel.remove();
    document.removeEventListener("keydown", onKey);
    onClose?.();
  }
  function onKey(e) {
    if (e.key === "Escape") close();
  }
  scrim.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.append(scrim, panel);
  return { close, panel };
}

export function confirmSheet(title, text, okLabel = "确认", sticker = "moon") {
  return new Promise((resolve) => {
    const s = sheet({
      title, sticker,
      body: h("p", { style: "font-size:15px;line-height:1.8;color:var(--text-2);margin:4px 0 6px" }, text),
      footer: [
        h("button", { class: "btn btn-ghost", onclick: () => { resolve(false); s.close(); } }, "先不要"),
        h("button", { class: "btn btn-main", onclick: () => { resolve(true); s.close(); } }, okLabel),
      ],
      onClose: () => resolve(false),
    });
  });
}

export function debounce(fn, ms = 120) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

export const ICONS = {
  chat: '<path d="M5 6.25Q10.5 3.9 17.75 6Q20.1 7 19.6 12.25Q19.4 16 15.25 16.5H10L5.15 19.5L6 15.5Q3.3 13.75 4.15 9.1Q4.25 7.3 5 6.25Z"/><circle cx="8.25" cy="11" r="0.9" fill="currentColor" stroke="none"/><circle cx="12" cy="11" r="0.9" fill="currentColor" stroke="none"/><circle cx="15.75" cy="11" r="0.9" fill="currentColor" stroke="none"/>',
  flag: '<path d="M6.5 20.5Q6.3 12.6 6.65 4M7 5Q11.5 3.35 17.85 5.75L16.2 9.05L17.95 12.1Q11.9 10.15 6.6 12.5"/>',
  star: '<path d="M11.85 3.65L14.65 8.95L20.45 9.95L16.25 14.15L16.9 20L11.75 17.45L6.5 20.15L7.35 14.15L3.4 9.75L9.15 8.95Z"/>',
  sprout: '<path d="M11.85 20.35Q12.2 15.4 11.85 10.5M11.8 14.4Q4.75 14.35 4 7.2Q11.05 6.05 11.8 14.4ZM12 11.85Q12.05 4.95 19.7 4.5Q20.1 11.85 12 12.5Z"/>',
  bulb: '<path d="M8.85 16Q8.7 14.35 6.85 12.5Q4.4 10 5.55 6.95Q7 3.4 11.7 3.5Q16.85 3.15 18.5 7.1Q19.7 10.55 16.75 13.2Q15.4 14.45 15.05 16ZM9.1 18.4L14.85 18.3M10.25 20.5H13.65M12 15.5V11L9.5 9M12 11L14.5 8.9"/>',
  book: '<path d="M12 6.65Q8.25 4.25 3.5 5.25L3.75 18.4Q8.4 17.35 12 20Q15.75 17.5 20.3 18.4L20.5 5.2Q15.7 4.3 12 6.65V20"/>',
  letter: '<path d="M5 6.25Q12 5.8 18.5 6.15Q19.6 6.2 19.6 7.4L19.75 17Q19.75 18.1 18.6 18.05L5.2 18.1Q4.1 18.1 4.1 17L4.05 7.5Q4.05 6.25 5 6.25ZM4.5 7L11.9 12.7L19.2 6.85"/>',
  user: '<path d="M4.65 19.75Q5.3 14.35 11.95 14.25Q18.5 14.3 19.4 19.65M12 3.8C17.05 3.75 17.3 11.55 12.05 11.7C6.75 11.85 6.7 3.85 12 3.8Z"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h3M11 17h9"/><circle cx="16" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  palette: '<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.8-1.7 0-1.3-1.2-1.6-1.2-2.7 0-.9.8-1.6 1.7-1.6h2.2A4 4 0 0 0 20.5 10C20.5 6.4 16.7 3.5 12 3.5z"/><circle cx="8" cy="11" r="1.1"/><circle cx="11" cy="7.5" r="1.1"/><circle cx="15.5" cy="8" r="1.1"/>',
  plus: '<path d="M11.95 4.6Q12.25 11.95 12 19.5M4.55 12.1Q11.85 11.85 19.45 12"/>',
  check: '<path d="M5 12.3Q7.1 14.4 9.5 16.65Q14.05 10.75 19.35 6.05"/>',
  checkc: '<path d="M12.15 3.7C17.1 3.6 20.6 7.4 20.25 12.25C20.05 17.35 16.25 20.65 11.5 20.3C6.55 20.15 3.4 16.35 3.7 11.7C3.9 6.85 7.45 3.8 12.15 3.7ZM8.1 12.25L10.7 14.8L16.3 9.2"/>',
  moon: '<path d="M16.35 4.15Q12.8 4.75 12.35 8.65Q12.05 13.2 17 14.4Q18.5 14.7 20.1 14.1C18.9 19.9 11.3 22.4 6.45 17.5C1.7 12.75 5.25 4.8 11 4.05Q13.85 3.65 16.35 4.15Z"/>',
  sun: '<path d="M12.1 7.75C17.85 7.55 17.9 16.5 12.05 16.45C6.3 16.45 6.4 7.85 12.1 7.75ZM12 2.5V4.5M12 19.5V21.5M2.5 12H4.5M19.5 12H21.5M5.25 5.25L6.75 6.75M17.25 17.25L18.75 18.75M18.75 5.25L17.25 6.75M6.75 17.25L5.25 18.75"/>',
  send: '<path d="M11.9 19.65Q12.2 12.1 11.95 4.65M6.15 10.45L11.95 4.65L18 10.65"/>',
  close: '<path d="M5.6 5.85Q12 12.25 18.35 18.05M18.25 5.65Q12.2 11.95 5.75 18.4"/>',
  arrow: '<path d="M4.4 12.15Q11.7 11.9 19.5 12M14.35 6.6L19.6 12L14.1 17.5"/>',
  back: '<path d="M19.6 12.15Q12.3 11.9 4.5 12M9.65 6.6L4.4 12L9.9 17.5"/>',
  gift: '<path d="M5.2 11.1L5.35 19.85L18.8 19.75L18.95 11.1M12 7.5V19.75M4.1 7.5H19.95V11H4.05ZM12 7.25Q5.75 7.6 6.85 4.45Q8.95 1.7 12 7.25Q15.35 1.75 17.5 4.5Q18.55 7.55 12 7.25"/>',
  heart: '<path d="M11.9 19.55C9.15 17.7 3.7 13.75 3.95 9.1C4.2 4.1 9.45 3.4 12 7.15C14.65 3.4 19.75 4.4 20 9.2C20.2 13.75 14.55 18 11.9 19.55Z"/>',
  compass: '<path d="M12.1 3.75C17 3.55 20.55 7.15 20.3 12.1C20.15 17.15 16.5 20.5 11.55 20.25C6.5 20.05 3.35 16.45 3.7 11.5C3.95 6.7 7.4 3.9 12.1 3.75Z"/><path d="M14.95 8.35L13.35 13.1L8.75 15.65L10.5 10.8Z" stroke-width="1.75"/><path d="M12 5.9V6.6M12 17.4V18.1" stroke-width="1.4"/>',
  wind: '<path d="M4 9h10a2.5 2.5 0 1 0-2.5-2.5M4 13h14a2.5 2.5 0 1 1-2.5 2.5M4 17h6"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  sparkles: '<path d="M10 3.5l1.6 4.4 4.4 1.6-4.4 1.6L10 15.5l-1.6-4.4L4 9.5l4.4-1.6zM17.5 14l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
  steps: '<path d="M4 19h4v-4h4v-4h4V7h4"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
  camera: '<path d="M8.6 6.55L9.7 4.75Q10.05 4.2 10.7 4.2H13.35Q14 4.2 14.35 4.75L15.45 6.55H18.4Q20.2 6.6 20.2 8.4Q20.4 13.1 20.15 17.4Q20.05 19.2 18.3 19.25Q12 19.6 5.7 19.25Q3.95 19.2 3.85 17.4Q3.6 12.9 3.85 8.4Q3.95 6.6 5.7 6.55ZM12 9.6C14.25 9.55 15.65 11 15.6 13C15.55 15.05 14.1 16.35 12 16.35C9.95 16.3 8.5 15 8.45 13C8.45 10.95 9.9 9.6 12 9.6ZM17.35 9.35H17.45"/>',
  calendar: '<path d="M5.6 5.85Q12 5.5 18.45 5.85Q20.1 6 20.05 7.6Q20.3 13.3 19.95 18.6Q19.85 20.15 18.3 20.2Q12 20.5 5.7 20.2Q4.15 20.1 4.05 18.55Q3.75 13.2 4 7.55Q4.1 6 5.6 5.85ZM4.25 10.3Q12 9.95 19.85 10.25M8.4 3.6V7.6M15.65 3.6V7.6M8.3 14.2H8.4M12 14.15H12.1M15.7 14.2H15.8"/>',
  clock: '<path d="M12.1 3.65C17.05 3.55 20.6 7.2 20.25 12.45C20.15 17.75 16.4 20.6 11.5 20.3C6.45 20.2 3.35 16.45 3.7 11.5C3.9 6.8 7.5 3.6 12.1 3.65ZM12 6.7V11.9L15.65 14.1"/>',
  bell: '<path d="M11 3.65Q12 2.35 13.05 3.65M4.65 16.9Q7.15 14 6.7 9.55Q6.45 5.05 11.9 4.95Q17.45 5 17.2 9.8Q16.85 14.4 19.45 16.9ZM10.1 19.5Q12 21.05 13.95 19.5"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>',
  shield: '<path d="M11.8 3.55Q15.55 5.55 19.5 6L18.9 13.35Q17.75 18 11.9 20.55Q6.05 17.9 5.1 13.25L4.55 6Q8.45 5.55 11.8 3.55ZM8.5 12.25L11.1 14.7L15.8 9.7"/>',
  menu: '<path d="M4.25 6.5Q12 6.25 19.5 6.5M4.25 12H19.5M4.25 17.5Q12 17.7 19.5 17.5"/>',
  panel: '<path d="M5.5 4.6L18.2 4.7Q20 4.7 19.95 6.5L19.8 17.5Q19.8 19.3 18 19.3L5.9 19.4Q4.05 19.4 4.05 17.6L4.15 6.45Q4.15 4.6 5.5 4.6ZM14.75 4.75V19.3M17.2 8.75V11.25"/>',
  bolt: '<path d="M13.15 3.4L5.25 13.6L11.55 13.35L10.5 20.6L18.75 10.25L12.65 10.45Z"/>',
  leaf: '<path d="M4.65 19.5Q3.45 13.1 8 8.45Q12.75 3.85 19.55 4.2Q20 11.45 15.7 15.75Q11.05 20.5 4.65 19.5ZM4.65 19.5L14.35 9.55"/>',
  memory: '<path d="M6.05 4.45H17.6Q18.65 4.45 18.65 5.5V19.75H6.05Q4.6 19.75 4.6 18.35V6Q4.6 4.45 6.05 4.45ZM7.55 4.5V19.7M10.5 9.1H15.4M10.5 12.55H14.55"/>',
  edit: '<path d="M5.05 15.15L15.6 4.6Q16.75 3.55 17.85 4.6L19.6 6.4Q20.55 7.4 19.5 8.45L9.05 19L4.4 19.6ZM13.5 6.7L17.5 10.6M5.05 15.15L9.05 19"/>',
  trash: '<path d="M4.6 6.6Q12 6.35 19.5 6.55M9 4.1H15M6.5 6.75L7.25 18.65Q7.35 20 8.65 20H15.25Q16.65 20 16.75 18.55L17.5 6.75M10.05 10.5L10.4 16.25M14 10.5L13.7 16.25"/>',
  download: '<path d="M12 3.9Q11.75 9.5 12 15.05M7.1 10.55L12 15.35L16.85 10.4M4.75 16.5V19.1Q4.75 20.1 6 20.05H18Q19.25 20.05 19.25 19V16.5"/>',
  play: '<path d="M8.15 5.2Q7.75 11.9 8.1 18.8Q8.1 19.55 8.75 19.1L18.6 12.6Q19.5 12 18.6 11.4L8.85 4.9Q8.2 4.45 8.15 5.2Z"/>',
  music: '<path d="M9.3 17.1L9.5 6.25L19.25 4.15L19.05 14.75M9.5 9.6L19.15 7.5M9.3 16.95C9.3 20.3 3.7 21.3 3.7 18.2C3.65 15.05 9.4 14.35 9.3 16.95ZM19.05 14.7C19.1 18.05 13.45 19.1 13.45 16C13.45 12.85 19.2 12.1 19.05 14.7Z"/>',
  egg: '<path d="M12 3.65C15.45 3.5 19.05 9.8 18.6 14.55C18.35 18.55 15.6 20.5 11.85 20.4C7.85 20.3 5.3 18 5.35 14.15C5.3 9.4 8.7 3.75 12 3.65Z"/>',
  report: '<path d="M5.95 3.7H14.95L18.6 7.4V20H6.05ZM14.95 3.8V7.5H18.5M9.1 17.25V14.4M12.3 17.25V12.25M15.4 17.25V10.25"/>',
  quote: '<path d="M10.2 6.5H5.05V12.5H10.2V15.05Q10.1 18.25 6.85 18.5M19.1 6.5H14V12.5H19.1V15.05Q19 18.25 15.8 18.5"/>',
  lock: '<path d="M6.55 10.5H17.5Q19 10.5 19 12.05L18.9 18.7Q18.9 20.3 17.4 20.3L6.6 20.25Q5.1 20.25 5.15 18.65V12Q5.15 10.5 6.55 10.5ZM8 10.5V7.5Q8.05 3.4 12.1 3.5Q16.2 3.6 16.1 7.65V10.5M12 14.5V16.75"/>',
  home: '<path d="M3.2 11.3L11.75 4.3Q12.1 4 12.5 4.35L20.55 11.25M5.5 10.15L5.55 19Q5.55 20 6.6 20H17.35Q18.5 20 18.5 18.8V10.15M10 19.5V13.8Q12 13.25 14 13.8V19.5"/>',
  minus: '<path d="M5.05 12.15Q11.9 11.9 19.05 12"/>',
  box: '<path d="M4.35 7.6L12 3.65L19.55 7.85L19.35 16.6L11.95 20.5L4.5 16.25ZM4.35 7.6L12.05 11.65L19.55 7.85M12.05 11.65L11.95 20.5M8.1 5.6L15.75 9.75"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  turn: '<path d="M19 12a7 7 0 1 1-2.05-4.95"/><path d="M19 4.5V8h-3.5"/>',
  footsteps: '<path d="M7.65 3.7C10.15 3.6 10.55 6.15 9.6 8.8Q8.7 11.15 8.95 13.65Q9.15 16 7.2 16.3Q5.25 16.5 5.15 14.8Q5.05 13.35 5.55 12Q6 10.95 5.1 9.1C3.9 6.4 5.05 3.8 7.65 3.7Z"/><path d="M15.7 7.7C18.3 7.55 19.25 9.9 18.5 12.65Q17.75 15.2 18.15 17.7Q18.45 20.15 16.5 20.5Q14.6 20.8 14.3 19.1Q14.1 17.55 14.4 16.1Q14.75 14.75 13.8 13.1C12.25 10.25 13.2 7.9 15.7 7.7Z"/>',
};

export function icon(name, size = "") {
  return `<svg class="ic-svg" viewBox="0 0 24 24" ${size ? `style="width:${size};height:${size}"` : ""} aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

// 彩色圆角方块 + 白色线性图标：整站唯一的「贴图」形式
export function tile(name, color = "var(--accent)", size = 40) {
  return `<span class="tile" style="--tile:${color};width:${size}px;height:${size}px">${icon(name)}</span>`;
}
