// 未登录：一句话说清楚这是什么，然后让人直接进去。
import { api } from "../api.js";
import { state, setData, go } from "../store.js";
import { esc, toast, icon } from "../ui.js";
import { orb, installOrbStyles } from "../orb.js";

const STEPS = [
  ["说清想要什么", "把「想变好」换成一个能看见的具体画面，不是职位名。"],
  ["照着你选的方式陪你", "中断时是提醒、一起找原因，还是先不提——由你定，随时可改。"],
  ["留下真实的小事", "好消息、走过的小步、一次练习。不写日记也能被记住。"],
  ["两只角色，各做各的", "小光是稳定的对话伙伴；宠物是独立的养成线，按经验进化。"],
];

export function renderGate(root) {
  installOrbStyles();
  root.innerHTML = `
    <main class="gate">
      <section class="gate-hero">
        <div class="orb-wrap lg" id="gateOrb"></div>
        <h1>把想成为的人，<br>收成今天的一小步。</h1>
        <p class="lede">显伴是一个显化陪伴 agent。它记得你确认过的事，在你中断的时候按你选的方式回应，然后陪你慢慢靠近。</p>
        <div class="gate-acts">
          <button class="btn btn-ink btn-lg" data-act="guest">先体验一下</button>
          <button class="btn btn-ghost btn-lg" data-act="auth" data-mode="login">登录 / 注册</button>
        </div>
        <p class="fine">体验账号会预置 15 天的示例记录（一条完整的故事线），只属于这个浏览器。想留下来，随时可以把它升级成正式账号。</p>
      </section>
      <aside class="gate-side">
        <div class="kicker">它怎么工作</div>
        <ul class="gate-list">
          ${STEPS.map(([t, d], i) => `<li><span class="n">0${i + 1}</span><span><div class="t">${esc(t)}</div><div class="d">${esc(d)}</div></span></li>`).join("")}
        </ul>
      </aside>
    </main>`;
  root.querySelector("#gateOrb").append(orb("idle", { size: "lg" }));

  root.querySelector("[data-act=guest]").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "准备中…";
    try {
      await api.guest(true);
      window.dispatchEvent(new CustomEvent("xg:enter"));
    } catch (err) {
      toast(err.message, "err");
      btn.disabled = false;
      btn.textContent = "先体验一下";
    }
  });

  root.querySelector("[data-act=auth]").addEventListener("click", () => authSheet(root));
}

function authSheet(root) {
  let mode = "login";
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="auth" style="margin:0 auto;max-width:100%">
      <label>用户名<input class="field" name="username" autocomplete="username" maxlength="20"></label>
      <label>密码<input class="field" name="password" type="password" autocomplete="current-password" minlength="6"></label>
      <p id="authErr" style="color:var(--rose);font-size:12px;min-height:18px;margin:0"></p>
      <button class="btn btn-ink" id="authGo">登录</button>
      <button class="btn btn-quiet" id="authSwitch" style="font-size:12px">还没有账号？注册</button>
    </div>`;
  const body = wrap;
  const scrim = document.createElement("div");
  scrim.className = "scrim";
  const panel = document.createElement("section");
  panel.className = "sheet";
  panel.style.width = "min(420px,92vw)";
  panel.innerHTML = `<header><h3>登录显伴</h3><button class="x" aria-label="关闭">×</button></header><div class="body"></div>`;
  panel.querySelector(".body").append(body);
  document.body.append(scrim, panel);
  const close = () => { scrim.remove(); panel.remove(); };
  scrim.addEventListener("click", close);
  panel.querySelector(".x").addEventListener("click", close);

  const submit = async () => {
    const u = panel.querySelector("[name=username]").value.trim();
    const p = panel.querySelector("[name=password]").value;
    const err = panel.querySelector("#authErr");
    err.textContent = "";
    try {
      if (mode === "login") await api.login(u, p);
      else await api.register(u, p);
      close();
      window.dispatchEvent(new CustomEvent("xg:enter"));
    } catch (e) {
      err.textContent = e.message;
    }
  };
  panel.querySelector("#authGo").addEventListener("click", submit);
  panel.querySelector("#authSwitch").addEventListener("click", (e) => {
    mode = mode === "login" ? "register" : "login";
    panel.querySelector("h3").textContent = mode === "login" ? "登录显伴" : "注册显伴";
    panel.querySelector("#authGo").textContent = mode === "login" ? "登录" : "注册";
    e.currentTarget.textContent = mode === "login" ? "还没有账号？注册" : "已有账号？登录";
  });
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
  setTimeout(() => panel.querySelector("[name=username]").focus(), 60);
}
