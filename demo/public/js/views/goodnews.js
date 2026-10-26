// 好消息：低门槛记录，不做打卡。好消息 / 偷懒日 / 新发现三种。
import { api } from "../api.js";
import { state, setData, xpNote } from "../store.js";
import { esc, h, fmtDay, toast, icon, confirmSheet } from "../ui.js";

const KIND = {
  good: { glyph: "✦", label: "好消息", cls: "good" },
  rest: { glyph: "☾", label: "偷懒日", cls: "rest" },
  find: { glyph: "◌", label: "新发现", cls: "find" },
};

export function renderNews(root) {
  const data = state.data;
  const records = data.records || [];
  const groups = {};
  for (const r of records) {
    const k = fmtDay(r.created_at || r.day);
    (groups[k] ||= []).push(r);
  }
  const goodCount = records.filter((r) => r.type === "good").length;

  root.innerHTML = `
    <div class="page-inner">
      <div class="section-head">
        <h2>好消息</h2>
        <p>${goodCount} 条被记下来的小事 · 记录“发生了什么”，不只打一个标签</p>
      </div>

      <div class="news-form">
        <textarea class="field" id="newsText" rows="2" maxlength="200"
          placeholder="今天发生了什么值得留下来？再小也算。"></textarea>
        <div class="side">
          <button class="btn btn-jade btn-sm" data-kind="good">${icon("star")}收下</button>
          <button class="btn btn-ghost btn-sm" data-kind="rest">${icon("moon")}偷懒日</button>
          <button class="btn btn-ghost btn-sm" data-kind="find">记发现</button>
        </div>
      </div>

      ${records.length ? Object.entries(groups).map(([day, items]) => `
        <div class="day-group">
          <div class="pg-head" style="display:flex;gap:10px;align-items:center;font-size:11px;letter-spacing:.18em;color:var(--ink-4);margin:22px 0 4px">${esc(day)}</div>
          ${items.map(newsRow).join("")}
        </div>`).join("") : `
        <div class="empty">
          <div class="glyph">✦</div>
          <p>还没有记录。第一条不用重要，真实就好。</p>
        </div>`}

      <p style="font-size:11.5px;color:var(--ink-4);line-height:1.9;margin-top:26px">
        好消息默认只有你能看到。它不会自动出现在任何公开页面；分享卡需要你逐项确认要公开的细节。
      </p>
    </div>`;

  root.querySelectorAll("[data-kind]").forEach((b) => {
    b.addEventListener("click", async () => {
      const ta = root.querySelector("#newsText");
      const text = ta.value.trim();
      if (!text && b.dataset.kind !== "rest") {
        toast("写一句也行");
        ta.focus();
        return;
      }
      try {
        const out = await api.record(b.dataset.kind, text || "今天想休息");
        setData(out);
        const note = xpNote(out.xp);
        toast(note || "记住了");
        renderNews(root);
      } catch (e) {
        toast(e.message, "err");
      }
    });
  });
}

function newsRow(r) {
  const k = KIND[r.type] || KIND.good;
  return `<div class="news-item ${k.cls}">
    <span class="mark">${k.glyph}</span>
    <div>
      <div class="t">${esc(r.text)}</div>
      <div class="d">${esc(k.label)}${r.created_at ? " · " + esc(r.created_at.slice(11, 16)) : ""}</div>
    </div>
  </div>`;
}
