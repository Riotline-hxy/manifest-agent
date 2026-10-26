// 我的空间：个人档案、记忆（可改可删）、时间线、隐私与通知、数据导出。
// 「重新认识我」不封在这里——它是点子里的独立入口，这里只显示与更正结果。
import { api } from "../api.js";
import { state, setData, go, refresh } from "../store.js";
import { esc, toast, icon, sheet, h, confirmSheet, fmtDay, fmtTime } from "../ui.js";

const KIND_LABEL = {
  identity: "身份", intent: "愿景", preference: "偏好", boundary: "边界",
  insight: "新发现", event: "事件", good_news: "好消息",
};

export function renderSpace(root) {
  const d = state.data;
  const p = d.profile || {};
  const prefs = d.prefs || {};
  const mems = d.memories || [];
  const active = mems.filter((m) => m.status === "active");
  const guesses = mems.filter((m) => m.status === "guess");
  const act = d.activity || [];

  root.innerHTML = `
    <div class="page-inner">
      <div class="section-head">
        <h2>我的空间</h2>
        <p>这里的内容都能改、能删</p>
      </div>

      <div class="space-grid">
        <div class="fact">
          <div class="k">称呼</div>
          <div class="v">${esc(p.nickname || p.username || "还没有")}</div>
          <button class="edit" data-edit="nickname">修改</button>
        </div>
        <div class="fact">
          <div class="k">正在靠近</div>
          <div class="v">${esc(p.intent_primary || "还没有")}</div>
          <div class="edit">${esc(p.intent_why || "在聊天或「说清想要的」里慢慢说")}</div>
        </div>
        <div class="fact">
          <div class="k">中断时希望我</div>
          <div class="v">${esc(prefs.care_label)}</div>
          <button class="edit" data-relearn>重新选一次</button>
        </div>
        <div class="fact">
          <div class="k">宠物</div>
          <div class="v">${esc(d.growth?.pet_name || "小芽")} · ${esc(d.growth?.stage?.name || "")}</div>
          <button class="edit" data-go="growth">去看成长</button>
        </div>
      </div>

      <div class="section-head" style="margin-top:34px">
        <h2 style="font-size:19px">记忆</h2>
        <p>${active.length} 条确认 · ${guesses.length} 条待确认</p>
      </div>

      ${guesses.length ? `<div class="path-title" style="color:var(--gold)">我猜的，需要你点头</div>
        <div style="display:grid;gap:8px;margin-bottom:18px">
          ${guesses.map((m) => `<div class="mem-row guess">
            <div><div class="txt">${esc(m.text)}</div>
              <div class="meta"><span class="tag gold">${esc(KIND_LABEL[m.kind] || "猜测")}</span><span style="color:var(--ink-4);font-size:11px">${esc(m.created_at?.slice(0, 10))}</span></div></div>
            <div class="acts" style="opacity:1"><button data-confirm="${esc(m.id)}">对</button><button data-reject="${esc(m.id)}">不太对</button></div>
          </div>`).join("")}
        </div>` : ""}

      <div style="display:grid;gap:0">
        ${active.map((m) => `<div class="mem-row">
          <div>
            <div class="txt">${esc(m.text)}</div>
            <div class="meta">
              <span class="tag jade">${esc(KIND_LABEL[m.kind] || "记忆")}</span>
              <span class="tag">${m.source === "confirmed" ? "你确认过" : m.source === "onboarding" ? "建档时" : m.source?.startsWith("scene") ? "场景里" : m.source?.includes("explicit") ? "你让我记的" : "小光记的"}</span>
              <span style="color:var(--ink-4);font-size:11px">${esc(m.created_at?.slice(0, 10))}</span>
            </div>
          </div>
          <div class="acts">
            <button data-editmem="${esc(m.id)}">改</button>
            <button data-forget="${esc(m.id)}">忘掉</button>
          </div>
        </div>`).join("") || `<div class="empty"><div class="glyph">·</div><p>还没有确认过的记忆。在聊天里说「帮我记住……」就会出现在这里。</p></div>`}
      </div>

      <div class="add-step" style="margin-top:14px">
        <input class="field" id="newMem" placeholder="亲手写一条：比如「我喜欢吃寿司」" maxlength="120">
        <button class="btn btn-ghost" id="addMem">加进记忆</button>
      </div>

      <div class="section-head" style="margin-top:40px"><h2 style="font-size:19px">时间线</h2><p>只有你自己看得到</p></div>
      <div class="timeline">
        ${act.slice(0, 24).map((a) => `<div class="tl-row ${["plan", "record"].includes(a.kind) ? "hot" : ""}">
          <span class="at">${esc((a.at || "").slice(5, 10))}</span>${esc(a.text)}</div>`).join("")
          || `<div class="tl-row">还没有记录。</div>`}
      </div>

      <div class="section-head" style="margin-top:40px"><h2 style="font-size:19px">隐私与通知</h2></div>
      <div class="pref-row">
        <div class="lbl">主动消息频率<small>只在站内出现，第一版不做手机系统推送</small></div>
        <div class="seg" data-pref="proactive">
          ${[["more", "多一点"], ["normal", "刚好"], ["less", "少一点"], ["off", "先别打扰"]].map(([v, l]) =>
            `<button data-v="${v}" class="${(p.proactive || "normal") === v ? "on" : ""}">${l}</button>`).join("")}
        </div>
      </div>
      <div class="pref-row">
        <div class="lbl">主题<small>纸色或暮色</small></div>
        <div class="seg" data-pref="theme">
          <button data-v="paper" class="${state.theme !== "dusk" ? "on" : ""}">纸色</button>
          <button data-v="dusk" class="${state.theme === "dusk" ? "on" : ""}">暮色</button>
        </div>
      </div>
      <div class="pref-row">
        <div class="lbl">你的数据<small>导出全部：画像、记忆、计划、对话</small></div>
        <button class="btn btn-ghost btn-sm" id="exportData">导出 JSON</button>
      </div>
      <div class="pref-row">
        <div class="lbl">试用主动消息<small>演示用：立刻生成一条站内消息</small></div>
        <button class="btn btn-ghost btn-sm" id="proactive">让 ${esc(p.agent_name || "小光")} 说一句</button>
      </div>

      <p style="font-size:11px;color:var(--ink-4);line-height:1.9;margin-top:22px">
        每个账号在服务器上对应一个独立的数据库文件；接口只从登录会话取身份，不能通过参数读取别人的数据。
        删除记忆是真正的删除。
      </p>
    </div>`;

  root.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  root.querySelector("[data-relearn]")?.addEventListener("click", async () => {
    const out = await api.sceneStart("relearn");
    state.sceneStep = { ...out.step, title: out.scene.title };
    state.sceneRunId = out.run?.id;
    setData({ scene: out.run });
    go("chat");
  });

  root.querySelectorAll("[data-confirm]").forEach((b) =>
    b.addEventListener("click", () => memAct("confirm", b.dataset.confirm, root)));
  root.querySelectorAll("[data-reject]").forEach((b) =>
    b.addEventListener("click", () => memAct("reject", b.dataset.reject, root)));
  root.querySelectorAll("[data-forget]").forEach((b) =>
    b.addEventListener("click", async () => {
      const ok = await confirmSheet("忘掉这条？", "它会从记忆里真正删除，以后不会再用它理解你。", "忘掉");
      if (ok) memAct("forget", b.dataset.forget, root);
    }));
  root.querySelectorAll("[data-editmem]").forEach((b) =>
    b.addEventListener("click", () => {
      const m = mems.find((x) => x.id === b.dataset.editmem);
      if (!m) return;
      editSheet("改一条记忆", m.text, async (text) => {
        await api.memory("edit", { id: m.id, text });
        await refresh();
        renderSpace(root);
        toast("改好了");
      });
    }));
  root.querySelector("[data-edit=nickname]")?.addEventListener("click", () => {
    editSheet("怎么称呼你", p.nickname || "", async (text) => {
      const out = await api.profile({ nickname: text });
      setData(out);
      renderSpace(root);
    });
  });

  root.querySelector("#addMem")?.addEventListener("click", async () => {
    const inp = root.querySelector("#newMem");
    const text = inp.value.trim();
    if (!text) return;
    await api.memory("add", { text });
    await refresh();
    renderSpace(root);
    toast("写进记忆了");
  });

  root.querySelectorAll("[data-pref=proactive] button").forEach((b) =>
    b.addEventListener("click", async () => {
      const out = await api.profile({ proactive: b.dataset.v });
      setData(out);
      renderSpace(root);
    }));
  root.querySelectorAll("[data-pref=theme] button").forEach((b) =>
    b.addEventListener("click", async () => {
      const { setTheme } = await import("../store.js");
      setTheme(b.dataset.v);
      renderSpace(root);
    }));

  root.querySelector("#exportData")?.addEventListener("click", async () => {
    const data = await api.exportAll();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `manifest-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast("已导出");
  });

  root.querySelector("#proactive")?.addEventListener("click", async () => {
    try {
      const out = await api.proactiveNow();
      setData(out);
      toast(out.sent ? "小光发了一条站内消息" : out.reason || "现在不需要打扰");
      if (out.sent) go("chat");
    } catch (e) {
      toast(e.message, "err");
    }
  });
}

async function memAct(action, id, root) {
  try {
    await api.memory(action, { id });
    await refresh();
    renderSpace(root);
  } catch (e) {
    toast(e.message, "err");
  }
}

function editSheet(title, value, onSave) {
  const input = h("input", { class: "field", value, maxlength: "120", style: "font-size:16px" });
  const s = sheet({
    title,
    body: input,
    footer: [
      h("button", { class: "btn btn-ghost", onclick: () => s.close() }, "取消"),
      h("button", {
        class: "btn btn-ink",
        onclick: async () => {
          const v = input.value.trim();
          if (!v) return;
          await onSave(v);
          s.close();
        },
      }, "保存"),
    ],
  });
  setTimeout(() => input.focus(), 50);
}
