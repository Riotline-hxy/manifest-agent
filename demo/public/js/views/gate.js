// 入口页：一句话 + 小光 + 选个氛围。点氛围整页当场换，登录后会记到画像里。
import { api } from "../api.js";
import { esc, toast, sheet, h, tile } from "../ui.js";
import { mountBall } from "../ball.js";
import { renderTrial } from "./trial.js";
import { THEMES, applyTheme, themeOf } from "../theme.js";

// 三张卡片分别回答：它能帮我做什么 / 和普通聊天机器人有什么不一样 / 我为什么会一直用它
const FEATURES = [
  ["flag", "var(--c-orange)", "把想要的样子，变成今天能做的事", "想早点睡、想敢开口、想把拖着的事做完——先说给小光听。它陪你把心里那个样子说清楚，再拆成今天就能动手的一件小事。显化不靠干等，靠每天往那儿挪一点。"],
  ["chat", "var(--c-violet)", "不是问答机器，是一个记得你的朋友", "它记得你上次聊到哪、在意什么、不喜欢被怎么催。不用每次从头讲，隔天它还会自己来问一句：「昨天那件事，后来怎么样了？」"],
  ["sprout", "var(--c-mint)", "每一小步都算数，不用逼自己", "做到的小事、碰到的好消息，都会变成看得见的成长记录，你的小镇也跟着一点点盖起来。哪天没做到也没关系，它不会数落你，明天接着来就好。"],
];

export function renderGate(root) {
  const cur = themeOf(localStorage.getItem("xg-theme")).id;
  root.innerHTML = `
    <div class="gate">
      <header class="gate-nav">
        <span class="gate-logo"><span class="gl-ball"></span><b>显伴</b></span>
        <span class="spacer"></span>
        <button class="btn btn-quiet" data-act="auth">登录</button>
      </header>
      <section class="gate-hero">
        <div class="gate-copy">
          <span class="pill acc">显化陪伴 agent · 网页版</span>
          <h1>把想成为的人，<br>收成今天的<span class="hl">一小步</span>。</h1>
          <p>小光会记得你说过的话，在你中断的时候照你喜欢的方式回应，再陪你一点点往前走。</p>
          <div class="gate-acts">
            <button class="btn btn-main btn-lg" data-act="guest">先体验一下</button>
            <button class="btn btn-ghost btn-lg" data-act="auth">登录 / 注册</button>
          </div>
          <p class="gate-try">不用注册，花两分钟和小光聊几句，带走今天的一小步。</p>
          <div class="gate-themes">
            <span class="gt-k">选一个氛围</span>
            ${THEMES.map((t) => `<button class="gt ${t.id === cur ? "on" : ""}" data-t="${t.id}" title="${esc(t.name)} · ${esc(t.for)}"
              style="background:linear-gradient(160deg, ${t.swatch[0]}, ${t.swatch[1]})"><i style="background:${t.agent}"></i></button>`).join("")}
            <span class="gt-name">${esc(themeOf(cur).name)} · ${esc(themeOf(cur).for)}</span>
          </div>
        </div>
        <div class="gate-stage">
          <div class="gs-glow"></div>
          <div class="gate-ball"></div>
          <div class="gate-say speech">嗨，我是小光。</div>
        </div>
      </section>
      <section class="gate-feats">
        ${FEATURES.map(([ic, c, t, d], i) => `<div class="feat card" style="--i:${i}">${tile(ic, c, 48)}<h3>${esc(t)}</h3><p>${esc(d)}</p></div>`).join("")}
      </section>
      <footer class="gate-foot">每个账号一个独立数据库 · 回复来自真实模型</footer>
    </div>`;

  mountBall(root.querySelector(".gl-ball"), { size: 30, halo: false, interactive: false, agent: false });
  const ball = mountBall(root.querySelector(".gate-ball"), { size: 200, emotion: "01" });
  const say = root.querySelector(".gate-say");
  const LINES = [["10", "嗨，我是小光。"], ["03", "今天想从哪件小事开始？"], ["37", "你说过的，我都记着。"], ["14", "不催你，慢一点也算数。"], ["19", "先挑一个你喜欢的氛围？"]];
  let i = 0;
  const timer = setInterval(() => {
    if (!say.isConnected) return clearInterval(timer);
    const [m, t] = LINES[i++ % LINES.length];
    ball.set(m);
    say.classList.remove("pop"); void say.offsetWidth; say.classList.add("pop");
    say.textContent = t;
  }, 3200);

  root.querySelectorAll("[data-t]").forEach((b) => b.addEventListener("click", () => {
    const t = applyTheme(b.dataset.t);
    root.querySelectorAll("[data-t]").forEach((x) => x.classList.toggle("on", x === b));
    root.querySelector(".gt-name").textContent = `${t.name} · ${t.for}`;
    ball.set("10"); ball.pulse("bounce");
  }));
  root.querySelector("[data-act=guest]").addEventListener("click", () => {
    clearInterval(timer);
    renderTrial(root);
  });
  root.querySelectorAll("[data-act=auth]").forEach((b) => b.addEventListener("click", () => authSheet()));
}

export function authSheet(mode = "login") {
  const u = h("input", { class: "field", placeholder: "用户名", autocomplete: "username", maxlength: "20" });
  const p = h("input", { class: "field", type: "password", placeholder: "密码", autocomplete: "current-password", style: "margin-top:10px" });
  const err = h("p", { style: "color:var(--danger);font-size:13px;min-height:18px;margin:8px 0 0" });
  const sw = h("button", { class: "btn btn-quiet", style: "margin-right:auto" }, "还没有账号？注册");
  const go = h("button", { class: "btn btn-main" }, "登录");
  const s = sheet({ title: "登录显伴", sticker: "user", body: h("div", {}, u, p, err), footer: [sw, go] });
  const label = () => {
    s.panel.querySelector("h3").textContent = mode === "login" ? "登录显伴" : "注册显伴";
    go.textContent = mode === "login" ? "登录" : "注册";
    sw.textContent = mode === "login" ? "还没有账号？注册" : "已有账号？登录";
    p.autocomplete = mode === "login" ? "current-password" : "new-password";
  };
  label();
  const submit = async () => {
    err.textContent = "";
    try {
      if (mode === "login") await api.login(u.value.trim(), p.value);
      else await api.register(u.value.trim(), p.value);
      s.close();
      window.dispatchEvent(new CustomEvent("xg:enter"));
    } catch (e) { err.textContent = e.message; }
  };
  go.addEventListener("click", submit);
  s.panel.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  sw.addEventListener("click", () => {
    mode = mode === "login" ? "register" : "login";
    label();
  });
  setTimeout(() => u.focus(), 60);
}
