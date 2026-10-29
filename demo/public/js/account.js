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
