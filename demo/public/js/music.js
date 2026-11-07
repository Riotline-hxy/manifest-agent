// 练习的背景音乐（现在只有冥想用）：点「开始」的那一下就开始放，慢慢淡入；练习关掉时淡出。
// 手机浏览器要求在点击里开声音；iPhone 上 audio.volume 改不了，所以用 Web Audio 的音量节点做淡入淡出。
// 用户关掉过，就记住，下次默认不放；放不出来（比如不是点出来的）就显示成关着，点一下再放。
const KEY = "xg-music";
const VOL = 0.7;

export function music(src) {
  const a = new Audio(src);
  a.loop = true;
  a.preload = "auto";
  let gain = null, ctx = null;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC();
    gain = ctx.createGain();
    gain.gain.value = 0;
    ctx.createMediaElementSource(a).connect(gain).connect(ctx.destination);
  } catch { gain = null; a.volume = 0; }

  let on = localStorage.getItem(KEY) !== "off";
  let timer = 0, dead = false;
  const subs = new Set();
  const emit = () => subs.forEach((f) => f(on));
  const fade = (to, ms, done) => {
    clearTimeout(timer);
    if (gain) {
      const t = ctx.currentTime;
      gain.gain.cancelScheduledValues(t);
      gain.gain.setValueAtTime(gain.gain.value, t);
      gain.gain.linearRampToValueAtTime(to, t + ms / 1000);
    } else {
      const from = a.volume, t0 = performance.now();
      const step = () => {
        const k = Math.min(1, (performance.now() - t0) / ms);
        a.volume = from + (to - from) * k;
        if (k < 1) timer = setTimeout(step, 40);
      };
      step();
    }
    if (done) timer = setTimeout(done, ms + 30);
  };
  const play = () => {
    ctx?.resume?.();
    a.play().then(() => fade(VOL, 2600)).catch(() => { on = false; emit(); });
  };
  if (on) play();

  return {
    onChange(f) { subs.add(f); f(on); },
    toggle() {
      on = !on;
      localStorage.setItem(KEY, on ? "on" : "off");
      if (on) play(); else fade(0, 500, () => a.pause());
      emit();
    },
    stop() {
      if (dead) return;
      dead = true;
      fade(0, 1400, () => { a.pause(); a.removeAttribute("src"); a.load(); ctx?.close?.(); });
    },
  };
}
