// 显伴的 service worker：只做两件事——收推送、点通知回到对话。
// 不缓存任何页面或接口（页面本来就要联网用，缓存只会带来「看到旧版本」的问题）。
//
// 推送是空的（服务端不加密内容），被叫醒后用登录 cookie 去 /api/push/latest 取那句话。
// iOS / Chrome 都要求每次推送必须弹一条通知，所以取不到时也弹一条兜底的。

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  e.waitUntil((async () => {
    let title = "小光";
    let body = "小光给你留了一句话";
    let tag = "xg";
    try {
      const fromPush = e.data ? e.data.json() : null;   // 以后改成带内容的推送也能用
      const d = fromPush || await (await fetch("/api/push/latest", { credentials: "same-origin", cache: "no-store" })).json();
      if (d && d.text) {
        title = d.title || title;
        body = d.text;
        tag = d.id || tag;
      }
    } catch {}
    await self.registration.showNotification(title, {
      body, tag, renotify: true,
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-96.png",
      data: { url: "/#chat" },
    });
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL(e.notification.data?.url || "/#chat", self.location.origin).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if (new URL(w.url).origin === self.location.origin) {
        await w.focus();
        w.postMessage({ type: "xg:open-chat" });
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});
