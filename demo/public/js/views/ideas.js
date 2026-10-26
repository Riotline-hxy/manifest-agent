// 点子：点一下就让小光带你体验一个场景。每张卡都对应真实的后端状态机，
// 不是静态图文。「你现在有多了解我」会带着真实记忆回到对话里。
import { api } from "../api.js";
import { state, go, setData } from "../store.js";
import { esc, toast, icon, sheet, h } from "../ui.js";

const GROUP_ORDER = ["默契", "愿望", "日常"];

export function renderIdeas(root) {
  const ideas = state.data.ideas || [];
  const groups = {};
  for (const i of ideas) (groups[i.group] ||= []).push(i);

  root.innerHTML = `
    <div class="page-inner">
      <div class="section-head">
        <h2>点子</h2>
        <p>点一下，小光带你做一遍 · 不需要先想好怎么开口</p>
      </div>
      ${GROUP_ORDER.filter((g) => groups[g]).map((g) => `
        <div style="margin-bottom:26px">
          <div class="pg-head" style="font-size:11px;letter-spacing:.18em;color:var(--ink-4);margin-bottom:10px">${esc(g)}</div>
          <div class="card-grid">
            ${groups[g].map(ideaCard).join("")}
          </div>
        </div>`).join("")}
      <p style="font-size:11.5px;color:var(--ink-4);line-height:1.9;margin-top:8px">
        场景结束后写回的内容会出现在计划、好消息或「我的空间」里；不会凭空生成你没说过的事。
      </p>
    </div>`;

  root.querySelectorAll("[data-idea]").forEach((b) => {
    b.addEventListener("click", async () => {
      const idea = ideas.find((i) => i.id === b.dataset.idea);
      if (!idea) return;
      if (idea.prompt === "__know_me__") {
        knowMe();
        return;
      }
      try {
        const out = await api.sceneStart(idea.scene);
        state.sceneStep = { ...out.step, title: out.scene.title };
        state.sceneRunId = out.run?.id;
        setData({ scene: out.run });
        go("chat");
        toast("在对话里开始");
      } catch (e) {
        toast(e.message, "err");
      }
    });
  });
}

function ideaCard(i) {
  return `<button class="idea-card" data-idea="${esc(i.id)}">
    <span class="grp">${esc(i.group)}</span>
    <span class="ic">${icon(i.id === "know-me" ? "space" : i.id === "meditation" ? "moon" : i.id === "gratitude" ? "star" : "spark")}</span>
    <h3>${esc(i.title)}</h3>
    <p>${esc(i.desc)}</p>
    <span class="go">约 ${i.minutes} 分钟 ${icon("arrow")}</span>
  </button>`;
}

// 「你现在有多了解我」：把真实记忆摊开给用户看，并标出不确定的部分。
function knowMe() {
  const mems = state.data.memories || [];
  const active = mems.filter((m) => m.status === "active").slice(0, 10);
  const guesses = mems.filter((m) => m.status === "guess");
  const prefs = state.data.prefs || {};
  const body = h("div", {});
  body.innerHTML = `
    <p style="font-size:13px;color:var(--ink-2);line-height:1.8;margin:0 0 14px">
      这些是确认过、我会拿来理解你的内容。${guesses.length ? `另有 ${guesses.length} 条我还只是猜，需要你点头。` : ""}
    </p>
    ${prefs.intent ? `<div class="fact" style="margin-bottom:12px"><div class="k">正在靠近</div><div class="v">${esc(prefs.intent)}</div>
      ${prefs.why ? `<div class="edit">因为：${esc(prefs.why)}</div>` : ""}</div>` : ""}
    <div class="fact" style="margin-bottom:14px"><div class="k">你希望我在你中断时</div><div class="v">${esc(prefs.care_label)}</div></div>
    ${active.length ? `<div class="path-title">我记得的</div>` : `<p style="color:var(--ink-3);font-size:13px">还没有确认过的记忆。可以在聊天里说「帮我记住……」。</p>`}
    <div style="display:grid;gap:6px">
      ${active.map((m) => `<div style="font-size:13px;line-height:1.6;padding:8px 0;border-bottom:1px solid var(--line)">
        ${esc(m.text)}<span style="color:var(--ink-4);font-size:11px;margin-left:8px">${esc(m.created_at?.slice(5, 10) || "")}</span></div>`).join("")}
    </div>
    ${guesses.length ? `<div class="path-title" style="margin-top:16px">我不确定的</div>
      <div style="display:grid;gap:6px">
        ${guesses.map((m) => `<div class="guess-card"><div class="q">${esc(m.text)}</div>
          <div class="acts"><button class="yes" data-confirm="${esc(m.id)}">对，记下</button>
          <button data-reject="${esc(m.id)}">不太对</button></div></div>`).join("")}
      </div>` : ""}`;

  const s = sheet({
    title: "小光现在了解的",
    body,
    footer: [
      h("button", { class: "btn btn-ghost", onclick: () => { s.close(); go("space"); } }, "去我的空间修改"),
      h("button", { class: "btn btn-ink", onclick: () => s.close() }, "知道了"),
    ],
  });

  body.querySelectorAll("[data-confirm]").forEach((b) => b.addEventListener("click", () => act(b.dataset.confirm, "confirm", body)));
  body.querySelectorAll("[data-reject]").forEach((b) => b.addEventListener("click", () => act(b.dataset.reject, "reject", body)));
}

async function act(id, action, body) {
  try {
    await api.memory(action, { id });
    const data = await api.bootstrap();
    setData(data);
    toast(action === "confirm" ? "记下了" : "删掉了");
    body.querySelector(`[data-${action === "confirm" ? "confirm" : "reject"}="${id}"]`)?.closest(".guess-card")?.remove();
  } catch (e) {
    toast(e.message, "err");
  }
}
