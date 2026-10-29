// 账号：看自己是谁、把体验账号转成正式账号、退出登录。
import { api } from "./api.js";
import { state, go } from "./store.js";
import { esc, icon, toast, sheet, h, confirmSheet } from "./ui.js";

export function openAccount() {
  const u = state.user || {};
  const p = state.data?.profile || {};
  const guest = u.kind === "guest";
  const name = p.nickname || u.username || "我";
  const body = h("div", { class: "acct", html: `
    <div class="acct-head"><span class="acct-av">${esc(name.slice(0, 1))}</span>
      <div><b>${esc(name)}</b><small>${guest ? "体验账号" : `账号：${esc(u.username || "")}`}</small></div></div>
    ${guest ? `<div class="acct-guest">
      <p>体验账号只跟着这次登录。注册一个账号，现在的计划、记忆和小芽都会原样留下，换设备也能登录。</p>
      <input class="field" id="acUser" maxlength="20" placeholder="用户名（2–20 位）" autocomplete="username">
      <input class="field" id="acPass" type="password" maxlength="64" placeholder="密码（至少 6 位）" autocomplete="new-password">
      <button class="btn btn-main" id="acReg">${icon("shield")}注册并保留这些记录</button></div>` : ""}
    <div class="acct-rows">
      <button class="acct-row" data-go="space">${icon("user")}<span>我的空间</span>${icon("arrow")}</button>
      <button class="acct-row danger" id="acOut">${icon("back")}<span>退出登录</span></button>
    </div>` });
  const s = sheet({ title: "我的账号", body, sticker: "user" });
  body.querySelector("[data-go]").addEventListener("click", () => { s.close(); go("space"); });
  body.querySelector("#acReg")?.addEventListener("click", async () => {
    try {
      const out = await api.register(body.querySelector("#acUser").value.trim(), body.querySelector("#acPass").value);
      state.user = out.user;
      s.close();
      toast("注册好了，所有记录都留下了", "", "shield");
    } catch (e) { toast(e.message, "err"); }
  });
  body.querySelector("#acOut").addEventListener("click", async () => {
    s.close();
    const ok = await confirmSheet(guest ? "退出体验账号？" : "退出登录？",
      guest ? "退出后，这个体验账号就找不回来了。想留下这些记录，点「先不要」回去注册一个账号。" : "下次用用户名和密码就能回来，记录都在。",
      guest ? "仍然退出" : "退出", "back");
    if (!ok) return openAccount();
    await logout();
  });
}

export async function logout() {
  try { await api.logout(); } catch {}
  history.replaceState(null, "", location.pathname);
  location.reload();
}

// 左下角头像：我的空间（记忆 / 夜里整理 / 时间线 / 设置）+ 氛围 + 账号，收在一个小菜单里
let menuEl = null;
export function openMeMenu(anchor, { openTheme } = {}) {
  if (menuEl) return closeMenu();
  const u = state.user || {};
  const p = state.data?.profile || {};
  const name = p.nickname || u.username || "我";
  const guest = u.kind === "guest";
  menuEl = h("div", { class: "me-menu", role: "menu", html: `
    <div class="mm-head"><span class="acct-av sm">${esc(name.slice(0, 1))}</span><div><b>${esc(name)}</b><small>${guest ? "体验账号" : esc(u.username || "")}</small></div></div>
    <div class="mm-sec">我的空间</div>
    <button class="mm-item" data-space="memory">${icon("memory")}<span>记忆</span></button>
    <button class="mm-item" data-space="digest">${icon("moon")}<span>夜里整理 · 笔记本</span></button>
    <button class="mm-item" data-space="timeline">${icon("clock")}<span>时间线</span></button>
    <button class="mm-item" data-space="settings">${icon("settings")}<span>设置</span></button>
    <div class="mm-line"></div>
    <button class="mm-item" data-theme>${icon("palette")}<span>氛围与小光的颜色</span></button>
    ${guest ? `<button class="mm-item" data-account>${icon("shield")}<span>注册，保留这些记录</span></button>` : ""}
    <button class="mm-item danger" data-out>${icon("back")}<span>退出登录</span></button>` });
  document.body.append(menuEl);
  const r = anchor.getBoundingClientRect();
  Object.assign(menuEl.style, { left: r.right + 12 + "px", bottom: Math.max(12, innerHeight - r.bottom) + "px" });
  const go2 = (tab) => { closeMenu(); state.spaceTab = tab; state.route === "space" ? window.dispatchEvent(new CustomEvent("xg:redraw")) : go("space"); };
  menuEl.querySelectorAll("[data-space]").forEach((b) => b.addEventListener("click", () => go2(b.dataset.space)));
  menuEl.querySelector("[data-theme]").addEventListener("click", () => { closeMenu(); openTheme?.(); });
  menuEl.querySelector("[data-account]")?.addEventListener("click", () => { closeMenu(); openAccount(); });
  menuEl.querySelector("[data-out]").addEventListener("click", async () => {
    closeMenu();
    const ok = await confirmSheet(guest ? "退出体验账号？" : "退出登录？",
      guest ? "退出后，这个体验账号就找不回来了。想留下这些记录，点「先不要」，再从头像菜单里注册。" : "下次用用户名和密码就能回来，记录都在。",
      guest ? "仍然退出" : "退出", "back");
    if (ok) logout();
  });
  setTimeout(() => document.addEventListener("click", outside), 0);
  document.addEventListener("keydown", esc_);
}
function outside(e) { if (menuEl && !menuEl.contains(e.target)) closeMenu(); }
function esc_(e) { if (e.key === "Escape") closeMenu(); }
function closeMenu() {
  menuEl?.remove(); menuEl = null;
  document.removeEventListener("click", outside);
  document.removeEventListener("keydown", esc_);
}
