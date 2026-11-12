// 手机通知：装到主屏幕（PWA）+ 网页推送订阅。
// iPhone 只有「添加到主屏幕」后从主屏幕打开，才能开推送（iOS 16.4+）；安卓 Chrome 直接能开。
import { get, post } from "./api.js";

export const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
export const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

// ---- 安装 ----
let installEvt = null;
addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvt = e;
  dispatchEvent(new CustomEvent("xg:installable"));
});
addEventListener("appinstalled", () => { installEvt = null; });

/** installed | prompt（安卓 / 电脑 Chrome 能一键装）| ios（要手动添加）| browser（其他浏览器，看菜单） */
export function installState() {
  if (standalone()) return "installed";
  if (installEvt) return "prompt";
  return isIOS() ? "ios" : "browser";
}

export async function install() {
  if (!installEvt) return false;
  installEvt.prompt();
  const { outcome } = await installEvt.userChoice;
  installEvt = null;
  return outcome === "accepted";
}

export function registerSW() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {});
  // 点通知时页面已经开着：sw 让它切到对话
  navigator.serviceWorker.addEventListener("message", (e) => {
    if (e.data?.type === "xg:open-chat") location.hash = "#chat";
  });
}

// ---- 推送 ----
export const PUSH_WHY = {
  "ios-home": "iPhone 要先把显伴「添加到主屏幕」，再从主屏幕打开，才能开通知",
  unsupported: "这个浏览器不支持网页通知，换手机自带的 Chrome / Safari 试试",
  denied: "通知被浏览器拦下了：到浏览器的网站设置里，把这个网站的通知改成「允许」",
  dismissed: "这次没开成，想开的时候再点一下",
  failed: "没开成，可能是网络问题，等会儿再试",
};

/** ok | ios-home | unsupported | denied */
export function pushSupport() {
  if (isIOS() && !standalone()) return "ios-home";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return "ok";
}

const bytes = (b64) => {
  const s = b64.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(s + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
};
const sameKey = (sub, key) => {
  const a = sub.options?.applicationServerKey;
  if (!a) return true;
  const x = new Uint8Array(a), y = bytes(key);
  return x.length === y.length && x.every((v, i) => v === y[i]);
};
// sw 注册失败时 ready 永远不会好：最多等 8 秒
const ready = () => Promise.race([navigator.serviceWorker.ready,
  new Promise((_, rej) => setTimeout(() => rej(new Error("sw")), 8000))]);

async function subscribed(reg, key) {
  let sub = await reg.pushManager.getSubscription();
  if (sub && !sameKey(sub, key)) { await sub.unsubscribe(); sub = null; }   // 服务器换过密钥
  return sub;
}

export async function pushOn() {
  if (pushSupport() !== "ok" || Notification.permission !== "granted") return false;
  try { return !!(await (await ready()).pushManager.getSubscription()); } catch { return false; }
}

/** 必须在点击里调用（Safari 要求）。返回 { ok, reason?, devices? } */
export async function enablePush() {
  const sup = pushSupport();
  if (sup !== "ok") return { ok: false, reason: sup };
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return { ok: false, reason: perm === "denied" ? "denied" : "dismissed" };
  try {
    const reg = await ready();
    const { key } = await get("/api/push/key");
    const sub = (await subscribed(reg, key)) ||
      await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) });
    const out = await post("/api/push/subscribe", { subscription: sub.toJSON() });
    return { ok: true, devices: out.devices };
  } catch {
    return { ok: false, reason: "failed" };
  }
}

export async function disablePush() {
  try {
    const sub = await (await ready()).pushManager.getSubscription();
    if (sub) {
      await post("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
      await sub.unsubscribe();
    }
  } catch {}
}

/** 进门时：已经开过通知的设备，把订阅再报给服务器一次（换了账号登录、或服务器删过）。 */
export async function syncPush() {
  if (pushSupport() !== "ok" || Notification.permission !== "granted") return;
  try {
    const reg = await ready();
    const { key } = await get("/api/push/key");
    const sub = await subscribed(reg, key);   // 用户自己关掉的不会再开
    if (sub) await post("/api/push/subscribe", { subscription: sub.toJSON() });
  } catch {}
}

/** 退出登录前：这台设备的订阅地址，交给服务器解绑。 */
export async function deviceEndpoint() {
  try { return (await (await ready()).pushManager.getSubscription())?.endpoint || ""; } catch { return ""; }
}
