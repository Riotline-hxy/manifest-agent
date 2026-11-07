// 好消息：一面「幸福墙」。TA 记下的每件开心小事是一张便利贴，最近的在前面，最上面的小罐子数着贴了几张。
// 这里只放开心的事，回头翻的时候心里是暖的；心情不好时，记的弹层里有一行把 TA 带去和小光聊。
// 「记一件好事」的弹层（openGoodNote）对话页输入框左边的星星也用它。休息日放在蜕变计划里。
import { api } from "../api.js";
import { state, setData, xpNote, go } from "../store.js";
import { esc, toast, icon, sheet, h } from "../ui.js";
import { flyGain, burstAt } from "../fx.js";
import { jarSVG } from "../art.js";

// 便利贴的颜色：跟着主题的几种颜色走，每张按 id 固定一种，再歪一点点
const TINTS = ["var(--c-lemon)", "var(--c-mint)", "var(--c-sky)", "var(--c-pink)", "var(--c-violet)", "var(--c-orange)"];
const PH = "今天有什么让你嘴角上扬的小事？再小也算，写成一句小诗也行。";
// 听起来像是在难过、吐槽：贴之前轻轻问一句要不要先和小光聊（「终于没那么焦虑了」这种不算）
const LOW = /难过|伤心|好烦|烦死|心烦|崩溃|焦虑|郁闷|想哭|哭了|讨厌|气死|糟糕|倒霉|好累|累死|失眠|压力好大|不开心|心情不好|emo/i;
const EASED = /不再|没那么|不怎么|终于不|没有再|不用再|好多了/;

function seeded(id) {
  let h = 2166136261;
  for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0) / 4294967296);
}

function dateOf(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const md = `${d.getMonth() + 1}月${d.getDate()}日`;
  return d.getFullYear() === new Date().getFullYear() ? md : `${d.getFullYear()}年${md}`;
}

function note(r, i, fresh) {
  const rnd = seeded(r.id);
  const tint = TINTS[Math.floor(rnd() * TINTS.length)];
  const tilt = (rnd() * 2.4 - 1.2).toFixed(2);
  return `<article class="note${fresh ? " fresh" : ""}" data-id="${esc(r.id)}" style="--tint:${tint};--tilt:${tilt}deg;--i:${Math.min(i, 14)}">
    <p>${esc(r.text)}</p><time>${esc(dateOf(r.created_at || r.day))}</time></article>`;
}

export function renderNews(root, { fresh = "" } = {}) {
  const notes = (state.data.records || []).filter((r) => r.type === "good" || r.type === "find");
  root.innerHTML = `
    <div class="view-inner wide news">
      <div class="page-head"><div><h1>好消息</h1><p>把生活里的小开心，贴在这里。</p></div>
        <button class="btn btn-main news-add">${icon("plus")}记下一件好事</button></div>
      <section class="news-jar">
        <div class="nj-say"><b>生活里的好事，值得留一留。</b><p>等你想回头看看，它们都在这里。</p></div>
        <div class="nj-count"><div class="nj-art">${jarSVG(notes.length)}</div>
          <div><span class="num">${notes.length}</span><small>张幸福便利贴</small></div></div>
      </section>
      <section class="section">
        <div class="wall-head"><h2>我的幸福墙</h2>${notes.length > 1 ? "<span>最近的在前面</span>" : ""}</div>
        <div class="wall">
          ${notes.map((r, i) => note(r, i, r.id === fresh)).join("")}
          <button class="note note-add" aria-label="记下一件好事">${icon("plus")}<span>${notes.length ? "再贴一张" : "贴上第一张"}</span></button>
        </div>
        <p class="hint-line">这面墙只有你自己看得到。</p>
      </section>
    </div>`;

  const open = (e) => openGoodNote({
    from: e.currentTarget,
    onSaved: (r) => {
      renderNews(root, { fresh: r?.id || "" });
      const el = r && root.querySelector(`.note[data-id="${CSS.escape(r.id)}"]`);
      if (el) setTimeout(() => burstAt(el, 30), 380);
    },
  });
  root.querySelectorAll(".news-add, .note-add").forEach((b) => b.addEventListener("click", open));
}

// 记一件好事：写一句就贴上墙。听起来不太开心时先问一句；「心情不太好？」把 TA 带去和小光聊（带上已经写的字）
export function openGoodNote({ from, onSaved, onTalk } = {}) {
  const body = h("div", { class: "gn", html: `
    <textarea class="field" rows="4" maxlength="200" placeholder="${PH}"></textarea>
    <div class="gn-low" hidden><p>听起来今天有点不好受。这面墙只放开心的事，要不要先和小光聊聊？</p>
      <div><button class="btn btn-quiet" data-talk>${icon("chat")}去聊聊</button><button class="btn btn-quiet" data-anyway>还是贴上去</button></div></div>
    <button class="gn-talk" data-talk>${icon("chat")}心情不太好？去和小光聊聊</button>` });
  const ta = body.querySelector("textarea");
  const low = body.querySelector(".gn-low");
  let busy = false;
  const save = async (force = false) => {
    const text = ta.value.trim();
    if (!text) { toast("写一句就好"); ta.focus(); return; }
    if (!force && LOW.test(text) && !EASED.test(text)) { low.hidden = false; return; }
    if (busy) return;
    busy = true;
    try {
      const out = await api.record("good", text);
      s.close();
      setData(out);
      if (from?.isConnected) { flyGain(from, out.xp); burstAt(from, 24); }
      toast(`贴上去了${xpNote(out.xp) ? " · " + xpNote(out.xp) : ""}`, "", "star");
      onSaved?.(out.record);
    } catch (e) { toast(e.message, "err"); busy = false; }
  };
  const talk = () => {
    const t = ta.value.trim();
    s.close();
    if (onTalk) return onTalk(t);
    state.composerDraft = t;
    go("chat");
  };
  const s = sheet({
    title: "记下一件好事", sticker: "star", body,
    footer: [h("button", { class: "btn btn-main", onclick: () => save() }, "贴上去")],
  });
  ta.addEventListener("input", () => { low.hidden = true; });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); });
  body.querySelectorAll("[data-talk]").forEach((b) => b.addEventListener("click", talk));
  body.querySelector("[data-anyway]").addEventListener("click", () => save(true));
  setTimeout(() => ta.focus(), 60);
  return s;
}
