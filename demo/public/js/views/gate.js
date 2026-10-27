// 入口页：一句话 + 小光 + 选个氛围。点氛围整页当场换，登录后会记到画像里。
import { api } from "../api.js";
import { esc, toast, sheet, h, tile } from "../ui.js";
import { mountBall, setAgentColor } from "../ball.js";
import { petSVG } from "../pet.js";
import { THEMES, applyTheme, themeOf } from "../theme.js";

const FEATURES = [
  ["memory", "var(--c-violet)", "它记得你确认过的事", "说「帮我记住」就会记住；它猜的，要你点头才算数。每天夜里，它会把当天的事安静地整理一遍。"],
  ["compass", "var(--c-mint)", "按你选的方式陪你", "三天没动，它不会说你三分钟热度——会按你选的，轻轻提醒、陪你找原因，或者先不提。"],
  ["sprout", "var(--c-orange)", "一只跟着你长大的小芽", "行动、好消息、练习都会喂养它。它最后长成什么，取决于你更常做哪一种。"],
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
          <div class="gate-pet">${petSVG("baby", { cls: "alive" })}</div>
          <div class="gate-say speech">嗨，我是小光。</div>
        </div>
      </section>
      <section class="gate-feats">
        ${FEATURES.map(([ic, c, t, d], i) => `<div class="feat card" style="--i:${i}">${tile(ic, c, 48)}<h3>${esc(t)}</h3><p>${esc(d)}</p></div>`).join("")}
      </section>
      <footer class="gate-foot">小光形象：Emotion Ball（非商业演示授权） · 每个账号一个独立数据库 · 回复来自真实模型</footer>
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
    setAgentColor(t.agent);
    root.querySelectorAll("[data-t]").forEach((x) => x.classList.toggle("on", x === b));
    root.querySelector(".gt-name").textContent = `${t.name} · ${t.for}`;
    ball.set("10"); ball.pulse("bounce");
  }));
  root.querySelector("[data-act=guest]").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.classList.add("off"); b.textContent = "正在准备你的 15 天…";
    ball.set("busy"); ball.pulse("spin");
    try {
      await api.guest(true);
      await api.profile({ theme: themeOf(localStorage.getItem("xg-theme")).id }).catch(() => {});
      window.dispatchEvent(new CustomEvent("xg:enter"));
    } catch (err) {
      toast(err.message, "err");
      b.classList.remove("off"); b.textContent = "先体验一下";
    }
  });
  root.querySelectorAll("[data-act=auth]").forEach((b) => b.addEventListener("click", authSheet));
}

function authSheet() {
  let mode = "login";
  const u = h("input", { class: "field", placeholder: "用户名", autocomplete: "username", maxlength: "20" });
  const p = h("input", { class: "field", type: "password", placeholder: "密码", autocomplete: "current-password", style: "margin-top:10px" });
  const err = h("p", { style: "color:var(--danger);font-size:13px;min-height:18px;margin:8px 0 0" });
  const sw = h("button", { class: "btn btn-quiet", style: "margin-right:auto" }, "还没有账号？注册");
  const go = h("button", { class: "btn btn-main" }, "登录");
  const s = sheet({ title: "登录显伴", sticker: "user", body: h("div", {}, u, p, err), footer: [sw, go] });
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
    s.panel.querySelector("h3").textContent = mode === "login" ? "登录显伴" : "注册显伴";
    go.textContent = mode === "login" ? "登录" : "注册";
    sw.textContent = mode === "login" ? "还没有账号？注册" : "已有账号？登录";
  });
  setTimeout(() => u.focus(), 60);
}
