// 入口页：Forest 式的首屏——大字、发光的台子、斜射的光；小光在台子上换着表情。
import { api } from "../api.js";
import { esc, toast, sheet, h } from "../ui.js";
import { mountBall } from "../ball.js";
import { art } from "../fx.js";

const FEATURES = [
  ["st-mirror", "它记得你确认过的事", "说「帮我记住」就会记住；它猜的，要你点头才算数。每天夜里，它把当天的事安静地整理一遍。"],
  ["st-compass", "按你选的方式陪你", "三天没动，它不会说你三分钟热度——它会按你在「重新认识我」里选的，提醒、陪你找原因，或者先不提。"],
  ["pet-fox-1", "一只跟着你长大的小芽", "行动、好消息、练习都会喂养它。它会长成什么，取决于你更常做哪一种。"],
];

export function renderGate(root) {
  root.innerHTML = `
    <div class="gate">
      <header class="gate-nav">
        <div class="logo"><img src="${art("st-seed")}" alt=""><b>显<em>伴</em></b></div>
        <span class="spacer"></span>
        <button class="btn btn-quiet" data-act="auth">登录</button>
      </header>
      <section class="gate-hero">
        <div class="gate-copy">
          <div class="pill lamp gate-kicker">显化陪伴 agent · 网页版</div>
          <h1>把想成为的人，<br>收成今天的<span class="hl">一小步</span>。</h1>
          <p>小光会记得你说过的话，在你中断的时候照你喜欢的方式回应，再陪你一点点往前走。</p>
          <div class="gate-acts">
            <button class="btn btn-lamp btn-lg btn-shine" data-act="guest">先体验一下</button>
            <button class="btn btn-ghost btn-lg" data-act="auth">登录 / 注册</button>
          </div>
          <div class="gate-fine">体验账号预置 15 天的真实故事线 · 每个账号一个独立数据库 · 回复来自真实模型</div>
        </div>
        <div class="gate-stage">
          <div class="stage-glow"></div>
          <div class="gate-ball"></div>
          <img class="gate-pet" src="${art("pet-baby")}" alt="">
          <div class="gate-say speech">嗨，我是小光。</div>
        </div>
      </section>
      <section class="gate-feats">
        ${FEATURES.map(([a, t, d], i) => `
          <div class="feat card wiggle" style="--i:${i}">
            <img class="sticker" src="${art(a)}" alt="">
            <h3>${esc(t)}</h3><p>${esc(d)}</p>
          </div>`).join("")}
      </section>
    </div>`;

  const ball = mountBall(root.querySelector(".gate-ball"), { size: 210, emotion: "01", halo: true });
  const say = root.querySelector(".gate-say");
  const LINES = [["10", "嗨，我是小光。"], ["03", "今天想从哪件小事开始？"], ["37", "你说过的，我都记着。"], ["14", "不催你，慢一点也算数。"], ["19", "准备好了就点「先体验一下」。"]];
  let i = 0;
  const tick = () => {
    if (!say.isConnected) return clearInterval(timer);
    const [m, t] = LINES[i++ % LINES.length];
    ball.set(m);
    say.classList.remove("pop"); void say.offsetWidth; say.classList.add("pop");
    say.textContent = t;
  };
  const timer = setInterval(tick, 3200);
  setTimeout(tick, 900);

  root.querySelector("[data-act=guest]").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.classList.add("off"); b.textContent = "正在准备你的 15 天…";
    ball.set("busy"); ball.pulse("spin");
    try {
      await api.guest(true);
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
  const go = h("button", { class: "btn btn-lamp" }, "登录");
  const s = sheet({ title: "登录显伴", sticker: "st-seed", body: h("div", {}, u, p, err), footer: [sw, go] });
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
