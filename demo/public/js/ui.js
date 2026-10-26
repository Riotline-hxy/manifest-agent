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

export function toast(msg, kind = "") {
  let wrap = $(".toast-wrap");
  if (!wrap) {
    wrap = h("div", { class: "toast-wrap" });
    document.body.append(wrap);
  }
  const el = h("div", { class: `toast ${kind}` }, msg);
  wrap.append(el);
  setTimeout(() => {
    el.style.transition = "opacity .3s, transform .3s";
    el.style.opacity = "0";
    el.style.transform = "translateY(6px)";
    setTimeout(() => el.remove(), 320);
  }, 2600);
}

// 通用弹层：返回一个可以 close() 的句柄
export function sheet({ title, body, footer, onClose }) {
  const scrim = h("div", { class: "scrim" });
  const panel = h("section", { class: "sheet", role: "dialog", "aria-modal": "true" },
    h("header", {}, h("h3", {}, title || ""), h("button", { class: "x", "aria-label": "关闭", onclick: close }, "×")),
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

export function confirmSheet(title, text, okLabel = "确认") {
  return new Promise((resolve) => {
    const s = sheet({
      title,
      body: h("p", { style: "font-size:14px;line-height:1.8;color:var(--ink-2);margin:4px 0 10px" }, text),
      footer: [
        h("button", { class: "btn btn-ghost", onclick: () => { s.close(); resolve(false); } }, "先不要"),
        h("button", { class: "btn btn-ink", onclick: () => { s.close(); resolve(true); } }, okLabel),
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
  chat: '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H9l-4 3.5V16H6.5A2.5 2.5 0 0 1 4 13.5z"/>',
  plan: '<path d="M9 5h9M9 12h9M9 19h9"/><path d="M4.5 5l1 1 1.5-1.6M4.5 12l1 1 1.5-1.6M4.5 19l1 1 1.5-1.6"/>',
  pet: '<path d="M12 21c4 0 6.5-2.4 6.5-5.8 0-2.5-1.4-4.6-3.4-5.7.2-2.2-.9-4-2.4-4.4-.5 1.3-.4 2.6.2 3.7A6.6 6.6 0 0 0 12 9c-.3-1.1-.2-2.4.3-3.7-1.5.4-2.6 2.2-2.4 4.4-2 1.1-3.4 3.2-3.4 5.7C6.5 18.6 8 21 12 21z"/>',
  good: '<path d="M12 4l2.2 5 5.3.6-4 3.7 1.2 5.4L12 15.9 7.3 18.7l1.2-5.4-4-3.7 5.3-.6z"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
  book: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5A1.5 1.5 0 0 0 20 18.5z"/>',
  report: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4M9.5 12h6M9.5 15.5h4"/>',
  space: '<circle cx="12" cy="8" r="3.4"/><path d="M4.5 20c.8-3.6 3.9-5.6 7.5-5.6s6.7 2 7.5 5.6"/>',
  send: '<path d="M4.5 12h13M12 6l6 6-6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  moon: '<path d="M19 15.5A7.5 7.5 0 0 1 8.5 5 7.5 7.5 0 1 0 19 15.5z"/>',
  star: '<path d="M12 4l2.2 5 5.3.6-4 3.7 1.2 5.4L12 15.9 7.3 18.7l1.2-5.4-4-3.7 5.3-.6z"/>',
  arrow: '<path d="M5 12h13M13 6l6 6-6 6"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  bell: '<path d="M6.5 10a5.5 5.5 0 0 1 11 0c0 4 1.5 5 1.5 5H5s1.5-1 1.5-5z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
};

export function icon(name, size = "") {
  return `<svg viewBox="0 0 24 24" ${size ? `style="width:${size};height:${size}"` : ""} aria-hidden="true">${ICONS[name] || ""}</svg>`;
}
