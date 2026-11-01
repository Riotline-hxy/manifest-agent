// 成长页的宠物：Rive 实时动画。页面上能做的只有点它，所以动作这样安排：
//   - 点一下：摸一摸；鼠标移上去：打招呼、看着你
//   - 回到这页时经验比上次多了（做了事、进化了）：庆祝一次
//   - 分化之后，今天做过自己这条路线的事（行动 / 好消息 / 练习，星灵是三样里做了两样）：每天第一次来放一次招式
//   - 偷懒日：进来后犯困睡着；点一下醒来，一会儿没人理又睡着
// 运行时用到时才加载；加载失败、或者系统设置了减少动态效果，就留着原来的静态图。
import { state } from "./store.js";
import { isResting } from "./rest.js";
import { petId } from "./pet.js";

const REDOZE_MS = 20000;
let runtime = null;
let current = null;

function loadRuntime() {
  if (window.rive) return Promise.resolve(window.rive);
  runtime ||= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "/vendor/rive/rive.js";
    s.onload = () => {
      window.rive.RuntimeLoader.setWasmUrl("/vendor/rive/rive.wasm");
      window.rive.RuntimeLoader.setWasmFallbackUrl("/vendor/rive/rive_fallback.wasm");
      resolve(window.rive);
    };
    s.onerror = () => { runtime = null; reject(new Error("rive runtime")); };
    document.head.appendChild(s);
  });
  return runtime;
}

// 存在本机、按账号区分：上次看到的经验、今天是否已经放过招式
const mem = (k) => `xb-pet-${state.user?.id || "me"}-${k}`;

function entryAction(g) {
  const seen = Number(localStorage.getItem(mem("xp")));
  localStorage.setItem(mem("xp"), String(g.total));
  if (Number.isFinite(seen) && seen > 0 && g.total > seen) return "celebrate";
  if (!g.branch) return "";
  const by = g.today?.by_source || {};
  const did = g.branch === "star"
    ? ["action", "good", "practice"].filter((k) => by[k] > 0).length >= 2
    : by[g.branch_info?.source] > 0;
  const today = state.data?.journey?.today || new Date().toDateString();
  if (!did || localStorage.getItem(mem("skill")) === today) return "";
  localStorage.setItem(mem("skill"), today);
  return "skill";
}

export async function mountLivePet(host, g) {
  current?.destroy();
  current = null;
  if (!host || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let rive;
  try { rive = await loadRuntime(); } catch { return; }
  if (!host.isConnected) return;

  const canvas = document.createElement("canvas");
  canvas.className = "live-pet";
  host.appendChild(canvas);
  const timers = new Set();
  const later = (fn, ms) => { const t = setTimeout(() => { timers.delete(t); fn(); }, ms); timers.add(t); return t; };
  const resting = isResting();
  let vmi = null, sleeping = false, redoze = 0;

  const fire = (name) => vmi?.trigger(name)?.trigger();
  const setSleep = (v) => { sleeping = v; if (vmi) vmi.boolean("sleeping").value = v; };
  const scheduleDoze = () => { clearTimeout(redoze); timers.delete(redoze); redoze = later(() => setSleep(true), REDOZE_MS); };

  const r = new rive.Rive({
    src: `/pets/${petId(g.stage.art)}.riv`, canvas, stateMachine: "Pet", autoplay: true, autoBind: true,
    layout: new rive.Layout({ fit: rive.Fit.Contain, alignment: rive.Alignment.Center }),
    onLoad: () => {
      r.resizeDrawingSurfaceToCanvas();
      vmi = r.viewModelInstance;
      host.classList.add("live");
      if (resting) return void later(() => setSleep(true), 900);
      const act = entryAction(g);
      if (act) later(() => fire(act), act === "skill" ? 1000 : 700);
    },
    onLoadError: () => destroy(),
  });

  canvas.addEventListener("pointerenter", () => { if (vmi) vmi.boolean("hovered").value = true; });
  canvas.addEventListener("pointerleave", () => { if (vmi) vmi.boolean("hovered").value = false; });
  canvas.addEventListener("click", () => {
    if (!vmi) return;
    if (sleeping) setSleep(false);
    else fire("pet");
    if (resting) scheduleDoze();
  });

  const onResize = () => r.resizeDrawingSurfaceToCanvas();
  window.addEventListener("resize", onResize);
  // 切到别的页面时这一块会被整页替换掉，发现画布不在了就释放
  const watch = setInterval(() => { if (!canvas.isConnected) destroy(); }, 1500);

  function destroy() {
    clearInterval(watch);
    timers.forEach(clearTimeout);
    window.removeEventListener("resize", onResize);
    try { r.cleanup(); } catch {}
    canvas.remove();
    host.classList.remove("live");
    if (current === api) current = null;
  }
  const api = { destroy };
  current = api;
}
