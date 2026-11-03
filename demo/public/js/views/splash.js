// 开屏：每次打开 App 先见到小光。点它会凹一下，按住能捏一捏，快速点两下换个表情或动作；
// 下面一句暖心话，三个入口直接去聊天、计划、小镇。一个浏览器标签页只出现一次（刷新不再打扰）。
import { state, go } from "../store.js";
import { esc, tile } from "../ui.js";
import { mountBall } from "../ball.js";

const LINES = ["慢一点也算数。", "做到一小步，就值得被夸。", "你说过的，我都记着。", "不用完美，只要还在走。", "累了就先歇一会儿，我在。"];

export const shouldSplash = () => !sessionStorage.getItem("xg-splash") && (!location.hash || location.hash === "#");

export function showSplash() {
  sessionStorage.setItem("xg-splash", "1");
  const d = state.data || {}, p = d.profile || {};
  const name = p.nickname || "";
  const hr = new Date().getHours();
  const hello = hr < 5 ? "夜深了" : hr < 11 ? "早上好" : hr < 14 ? "中午好" : hr < 18 ? "下午好" : "晚上好";
  const pool = [...new Set([d.cheer?.you?.text, ...(d.cheer?.affirm || []), ...LINES].filter(Boolean))];
  let li = Math.floor(Math.random() * Math.min(pool.length, 4));
  const todo = (d.steps || []).filter((s) => s.status === "todo").length;
  const el = document.createElement("div");
  el.className = "splash";
  el.innerHTML = `
    <div class="sp-inner">
      <div class="sp-hello" style="--i:0">${hello}${name ? `，${esc(name)}` : ""}</div>
      <div class="sp-ball"></div>
      <div class="sp-tip">点点它，按住还能捏一捏</div>
      <button class="sp-card" style="--i:1" data-next aria-label="换一句"><span class="sp-k">给你的一句话</span><span class="sp-t"></span></button>
      <div class="sp-go">
        <button data-go="chat" style="--i:2">${tile("chat", "var(--c-sky)", 42)}<b>跟我聊聊</b><small>想说就说</small></button>
        <button data-go="plan" style="--i:3">${tile("flag", "var(--c-orange)", 42)}<b>蜕变计划</b><small>${todo ? `还有 ${todo} 个小步` : "今天的一小步"}</small></button>
        <button data-go="town" style="--i:4">${tile("home", "var(--c-mint)", 42)}<b>我的小镇</b><small>${esc(d.town?.name || "去看看")}</small></button>
      </div>
    </div>`;
  document.body.classList.add("splash-on");
  document.body.append(el);
  const tip = el.querySelector(".sp-tip");
  const quiet = () => tip.classList.add("gone");
  const size = Math.round(Math.min(280, innerWidth * 0.66, innerHeight * 0.36));
  const ball = mountBall(el.querySelector(".sp-ball"), { size, emotion: "01", touch: { onTap: quiet, onDouble: quiet } });
  setTimeout(() => ball.set("02"), 1500);

  const say = el.querySelector(".sp-t");
  const show = () => { say.textContent = pool[li % pool.length]; };
  show();
  el.querySelector("[data-next]").addEventListener("click", (e) => {
    li += 1;
    const card = e.currentTarget;
    card.classList.remove("swap"); void card.offsetWidth; card.classList.add("swap");
    setTimeout(show, 140);
  });
  el.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => {
    const to = b.dataset.go;
    el.classList.add("leaving");
    document.body.classList.remove("splash-on");
    if (to !== state.route) go(to);
    setTimeout(() => { ball.destroy(); el.remove(); }, 420);
  }));
}
