// 与后端的所有通信。所有请求都带 cookie；用户身份只由服务端会话决定。

export class ApiError extends Error {
  constructor(status, message) {
    super(message || "请求失败");
    this.status = status;
  }
}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!res.ok) throw new ApiError(res.status, data?.error || `HTTP ${res.status}`);
  return data;
}

export const get = (p) => request("GET", p);
export const post = (p, b = {}) => request("POST", p, b);

export const api = {
  me: () => get("/api/auth/me"),
  login: (username, password) => post("/api/auth/login", { username, password }),
  register: (username, password) => post("/api/auth/register", { username, password }),
  guest: (seed = true) => post("/api/auth/guest", { seed }),
  logout: (endpoint = "") => post("/api/auth/logout", endpoint ? { endpoint } : {}),
  rename: (username) => post("/api/auth/rename", { username }),
  bootstrap: () => get("/api/bootstrap"),
  onboard: (answers, carry = null) => post("/api/onboard", { answers, carry }),
  trial: (payload) => post("/api/trial/chat", payload),
  onboardPlan: (payload) => post("/api/onboard/plan", payload),
  profile: (patch) => post("/api/profile", patch),
  memory: (action, payload = {}) => post("/api/memory", { action, ...payload }),
  step: (action, payload = {}) => post("/api/step", { action, ...payload }),
  record: (type, text) => post("/api/record", { type, text }),
  sceneStart: (scene) => post("/api/scene/start", { scene }),
  sceneAnswer: (run_id, text) => post("/api/scene/answer", { run_id, text }),
  sceneSave: (run_id, items, extra) => post("/api/scene/save", { run_id, items, extra }),
  sceneDiscard: (run_id) => post("/api/scene/discard", { run_id }),
  sceneCancel: () => post("/api/scene/cancel"),
  growth: () => get("/api/growth"),
  town: (action, payload = {}) => post("/api/town", { action, ...payload }),
  digest: () => post("/api/memory/digest"),
  academy: () => get("/api/academy"),
  article: (id) => get(`/api/academy/article?id=${encodeURIComponent(id)}`),
  report: (days, fast = false) => get(`/api/report?days=${days}${fast ? "&fast=1" : ""}`),
  proactiveNow: () => post("/api/proactive/now"),
  inboxSeen: () => post("/api/inbox/seen"),
  exportAll: () => get("/api/export"),
  wish: (action, payload = {}) => post("/api/wish", { action, ...payload }),
  moment: (action, payload = {}) => post("/api/moment", { action, ...payload }),
  habit: (action, payload = {}) => post("/api/habit", { action, ...payload }),
  milestone: (action, payload = {}) => post("/api/milestone", { action, ...payload }),
  planApply: (payload) => post("/api/plan/apply", payload),
  rest: (undo = false) => post("/api/record", { type: "rest", undo }),
  task: (action, payload = {}) => post("/api/task", { action, ...payload }),
  notebook: (text) => post("/api/notebook", { text }),
  wishReview: (id, days) => get(`/api/wish/review?id=${encodeURIComponent(id)}&days=${days}`),
  wishReflect: (id, days, text) => post("/api/wish/reflect", { id, days, text }),
  insight: (payload) => post("/api/wish/insight", payload),
  pushTest: () => post("/api/push/test"),
};

// 真流式对话：服务端通过 SSE 逐段推送。
export async function streamChat(text, handlers = {}) {
  const res = await fetch("/api/chat", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok || !res.body) {
    const raw = await res.text().catch(() => "");
    let msg = `HTTP ${res.status}`;
    try {
      msg = JSON.parse(raw).error || msg;
    } catch {}
    throw new ApiError(res.status, msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload;
      try {
        payload = JSON.parse(data);
      } catch {
        continue;
      }
      handlers[event]?.(payload);
    }
  }
  handlers.close?.();
}
