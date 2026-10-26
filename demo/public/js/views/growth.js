// 成长进化：经验值、每日上限、宠物形态与分支、徽章、账本。
// 数字全部来自后端账本；页面不做任何本地加成。
import { api } from "../api.js";
import { state, setData } from "../store.js";
import { esc, toast, icon, confirmSheet } from "../ui.js";

const STAGE_NODES = [
  { id: "seed", name: "种子", at: 0, art: "stage0" },
  { id: "tadpole", name: "游星", at: 80, art: "stage1" },
  { id: "turtle", name: "雏龟", at: 200, art: "stage2" },
  { id: "branch", name: "化形", at: 360, art: "stage2" },
  { id: "adult", name: "成年", at: 700, art: "" },
];

function petArt(name) {
  return `assets/pets/${name}.webp`;
}

export function renderGrowth(root) {
  const g = state.data.growth;
  if (!g) {
    root.innerHTML = `<div class="page-inner"><div class="empty">成长数据还没准备好。</div></div>`;
    return;
  }
  const nextLabel = g.next ? `${g.next.name} · 再 ${g.to_next}` : g.needs_branch ? "等你选分支" : "已到当前最高形态";
  const art = g.stage.art || "stage2";

  root.innerHTML = `
    <div class="page-inner wide">
      <div class="section-head">
        <h2>成长进化</h2>
        <p>只有真实做过的事会写进这本账</p>
      </div>

      <div class="growth-top">
        <div>
          <div class="growth-pet">
            <div class="halo"></div>
            <img src="${petArt(art)}" alt="${esc(g.stage.name)}">
          </div>
        </div>
        <div>
          <div class="eyebrow">${esc(g.pet_name)} · ${esc(g.stage.name)}</div>
          <div class="growth-num"><span class="n">${g.total}</span><span class="u">累计经验</span></div>
          <div class="growth-stage">${esc(g.stage.name)}</div>
          <div class="growth-line">${esc(g.stage.line)}</div>
          <div class="growth-next">${g.next ? `下一形态：<b>${esc(g.next.name)}</b>，还差 <b>${g.to_next}</b> 经验` : `<b>${esc(nextLabel)}</b>`}</div>

          <div class="cap-rows">
            ${g.sources.map((s) => `
              <div class="cap-row">
                <span class="lbl">${esc(s.label)}</span>
                <span class="bar"><i class="${s.used >= s.cap ? "full" : ""}" style="width:${Math.min(100, (s.used / s.cap) * 100)}%"></i></span>
                <span class="val">${s.used}/${s.cap}</span>
              </div>`).join("")}
          </div>
          <div class="growth-next">今天 ${g.today.total}/${g.today.cap} 经验，各类上限 30，总计 120。</div>
        </div>
      </div>

      <div class="path">
        <div class="path-title">形态路线</div>
        <div class="path-line">
          ${STAGE_NODES.map((s, i) => {
            const reached = g.total >= s.at;
            const current = i === STAGE_NODES.filter((x) => g.total >= x.at).length - 1;
            const artName = s.id === "adult" && g.branch ? `${g.branch}_adult` : s.id === "branch" && g.branch ? `${g.branch}_juvenile` : s.art;
            return `<div class="node ${reached ? "reached" : "locked"} ${current ? "current" : ""}">
              <div class="disc">${artName ? `<img src="${petArt(artName)}" alt="">` : `<span style="font-size:20px;color:var(--ink-4)">?</span>`}</div>
              <div class="nm">${esc(s.name)}</div>
              <div class="at">${s.at} XP</div>
            </div>`;
          }).join("")}
        </div>
      </div>

      <div style="margin-top:30px">
        <div class="path-title">${g.needs_branch ? "现在可以化形了——选一条路" : g.branch ? "你的分支" : `化形需要 ${360} 经验`}</div>
        <div class="branches">
          ${g.branches.map((b) => `
            <button class="branch ${g.branch === b.id ? "chosen" : ""} ${g.needs_branch ? "" : g.branch ? "locked" : "locked"}"
                    data-branch="${esc(b.id)}" ${g.needs_branch ? "" : "disabled"}>
              <img src="${petArt(b.juvenile)}" alt="">
              <div class="b-cap">
                <div class="b-name">${esc(b.name)}</div>
                <div class="b-tag">${esc(b.tag)} · ${esc(b.line)}</div>
              </div>
            </button>`).join("")}
        </div>
        ${g.needs_branch ? `<p style="font-size:12px;color:var(--ink-3);margin-top:10px">选完不能反悔，但宠物的历史会保留在下面的图鉴里。</p>` : ""}
      </div>

      <div style="margin-top:30px">
        <div class="path-title">徽章</div>
        <div class="badges">
          ${g.badges.map((b) => `<span class="badge ${b.earned ? "earned" : ""}"><span class="g">${b.earned ? "✦" : "·"}</span>${esc(b.name)}</span>`).join("")}
        </div>
      </div>

      <div style="margin-top:30px">
        <div class="path-title">最近的账本</div>
        <div class="ledger">
          ${(g.ledger || []).map((r) => `
            <div class="ledger-row">
              <span class="d">${esc(r.created_at?.slice(5, 10) || "")}</span>
              <span class="n">${esc(r.note || r.label)}</span>
              <span class="v ${r.amount ? "" : "zero"}">${r.amount ? "+" + r.amount : "0"}</span>
            </div>`).join("") || `<p style="font-size:12px;color:var(--ink-3)">还没有记录。</p>`}
        </div>
      </div>

      <p style="font-size:11.5px;color:var(--ink-4);line-height:1.9;margin-top:24px">
        ${esc("同一件事不会重复计分：完成步骤 +10、好消息 +6、练习 +12、每天第一次来聊 +8；四类各 30、每日 120 封顶。")}<br>
        宠物是独立于小光的养成对象；聊天里的小光形象不会随等级改变。
      </p>
    </div>`;

  root.querySelectorAll("[data-branch]").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!state.data.growth.needs_branch) return;
      const ok = await confirmSheet("选这条分支？", "化形之后宠物会朝这个方向长大，聊天里的选择也会保留。", "就它");
      if (!ok) return;
      try {
        const out = await api.branch(b.dataset.branch);
        setData(out);
        toast("化形完成");
        renderGrowth(root);
      } catch (e) {
        toast(e.message, "err");
      }
    });
  });
}
