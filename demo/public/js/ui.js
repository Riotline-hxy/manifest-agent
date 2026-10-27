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
    .map((p) => `<p>${p.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>")}</p>`)
    .join("");
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
        h("button", { class: "btn btn-ghost", onclick: () => { s.close(); resolve(false); } }, "先不要"),
        h("button", { class: "btn btn-main", onclick: () => { s.close(); resolve(true); } }, okLabel),
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
  chat: '<path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4 3.5V16h0A1 1 0 0 1 5 15z"/>',
  flag: '<path d="M6 21V4"/><path d="M6 4.5h10.5l-2 3.5 2 3.5H6"/>',
  star: '<path d="M12 4.2l2.3 4.8 5.2.7-3.8 3.6.9 5.2L12 16l-4.6 2.5.9-5.2-3.8-3.6 5.2-.7z"/>',
  sprout: '<path d="M12 21v-8"/><path d="M12 13c0-4 2.8-6.5 7-6.5 0 4.2-2.8 6.5-7 6.5z"/><path d="M12 15c0-3.2-2.2-5.2-5.6-5.2 0 3.4 2.2 5.2 5.6 5.2z"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2V16h5v-.2c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3z"/>',
  book: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/>',
  letter: '<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M4.5 7l7.5 6 7.5-6"/>',
  user: '<circle cx="12" cy="8.5" r="3.6"/><path d="M5 20c.8-3.6 3.6-5.6 7-5.6s6.2 2 7 5.6"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h3M11 17h9"/><circle cx="16" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  palette: '<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.8-1.7 0-1.3-1.2-1.6-1.2-2.7 0-.9.8-1.6 1.7-1.6h2.2A4 4 0 0 0 20.5 10C20.5 6.4 16.7 3.5 12 3.5z"/><circle cx="8" cy="11" r="1.1"/><circle cx="11" cy="7.5" r="1.1"/><circle cx="15.5" cy="8" r="1.1"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  checkc: '<circle cx="12" cy="12" r="8.5"/><path d="M8.2 12.3l2.6 2.6 5-5.2"/>',
  moon: '<path d="M19 14.5A7.5 7.5 0 0 1 9.5 5 7.5 7.5 0 1 0 19 14.5z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
  send: '<path d="M12 19V6M6.5 11.5L12 6l5.5 5.5"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  arrow: '<path d="M5 12h13M13 6l6 6-6 6"/>',
  back: '<path d="M19 12H6M11 6l-6 6 6 6"/>',
  gift: '<rect x="4" y="9" width="16" height="11" rx="2"/><path d="M3.5 9h17M12 9v11"/><path d="M12 9c-1.5-3.5-5-4-5-1.5S10 9 12 9zM12 9c1.5-3.5 5-4 5-1.5S14 9 12 9z"/>',
  heart: '<path d="M12 19.5s-7.5-4.4-7.5-10A4.2 4.2 0 0 1 12 7a4.2 4.2 0 0 1 7.5 2.5c0 5.6-7.5 10-7.5 10z"/>',
  compass: '<circle cx="12" cy="12" r="8.5"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
  wind: '<path d="M4 9h10a2.5 2.5 0 1 0-2.5-2.5M4 13h14a2.5 2.5 0 1 1-2.5 2.5M4 17h6"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  sparkles: '<path d="M10 3.5l1.6 4.4 4.4 1.6-4.4 1.6L10 15.5l-1.6-4.4L4 9.5l4.4-1.6zM17.5 14l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
  steps: '<path d="M4 19h4v-4h4v-4h4V7h4"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  shield: '<path d="M12 3.5l7 2.5v5.5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M15 4.5v15"/>',
  bolt: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
  leaf: '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14z"/><path d="M5 19l7-7"/>',
  memory: '<path d="M12 4a5 5 0 0 0-5 5c0 1.2.4 2.2 1 3-1.8.6-3 2.2-3 4a4 4 0 0 0 4 4h6a4 4 0 0 0 4-4c0-1.8-1.2-3.4-3-4 .6-.8 1-1.8 1-3a5 5 0 0 0-5-5z"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  trash: '<path d="M5 7h14M10 4h4M7 7l1 13h8l1-13"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
  egg: '<path d="M12 3.5c3.6 0 6.5 5.3 6.5 9.5a6.5 6.5 0 0 1-13 0C5.5 8.8 8.4 3.5 12 3.5z"/>',
  report: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4M9.5 12h6M9.5 15.5h4"/>',
  quote: '<path d="M9.5 7.5H6v4.5h3.5V15c0 1.5-1 2.5-2.5 2.5M18.5 7.5H15v4.5h3.5V15c0 1.5-1 2.5-2.5 2.5"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
};

export function icon(name, size = "") {
  return `<svg class="ic-svg" viewBox="0 0 24 24" ${size ? `style="width:${size};height:${size}"` : ""} aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

// 彩色圆角方块 + 白色线性图标：整站唯一的「贴图」形式
export function tile(name, color = "var(--accent)", size = 40) {
  return `<span class="tile" style="--tile:${color};width:${size}px;height:${size}px">${icon(name)}</span>`;
}
