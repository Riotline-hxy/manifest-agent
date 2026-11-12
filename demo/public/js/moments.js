// 瞬间：一句话，可以配一张照片，可以挂在某个愿望下，也可以不挂。
// 「留下一个瞬间」这一张卡片在哪儿都一样：瞬间页、蜕变计划（右上角、日历里「这天记一笔」）、对话输入框左边的相机。
// 照片在手机上先压好（大图长边 1600、小图长边 480，WebP，不支持就 JPEG），只有本人能看；小光看不到图。
// 瞬间只由 TA 自己留：做练习、走流程都不会自动加。
import { api, post } from "./api.js";
import { state, setData, xpNote } from "./store.js";
import { esc, toast, icon, tile, sheet, h, confirmSheet } from "./ui.js";
import { catOf, MOODS } from "./journey.js";

export const photoURL = (pid, small = false) => (pid ? `/api/photo?id=${encodeURIComponent(pid)}${small ? "&s=1" : ""}` : "");

const D = (s) => new Date(s.slice(0, 10) + "T00:00:00Z");
const addDays = (s, n) => new Date(D(s).getTime() + n * 864e5).toISOString().slice(0, 10);
export const md = (s) => `${+s.slice(5, 7)}月${+s.slice(8, 10)}日`;

const PH = "想写什么都行，一两句就好。比如：下班路上的晚霞很好看，我停下来看了一会儿。";

// ---------------------------------------------------------------- 照片：压一压再传 ----
async function decode(file) {
  try { return await createImageBitmap(file, { imageOrientation: "from-image" }); } catch {}
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
}
const toBlob = (c, type, q) => new Promise((r) => c.toBlob(r, type, q));
async function shrink(src, max, q) {
  const w = src.width, ht = src.height, k = Math.min(1, max / Math.max(w, ht));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w * k)); c.height = Math.max(1, Math.round(ht * k));
  c.getContext("2d").drawImage(src, 0, 0, c.width, c.height);
  let b = await toBlob(c, "image/webp", q);
  if (!b || b.type !== "image/webp") b = await toBlob(c, "image/jpeg", q);
  return b;
}
const b64 = (blob) => new Promise((res, rej) => {
  const fr = new FileReader();
  fr.onload = () => res(String(fr.result).split(",")[1] || "");
  fr.onerror = rej;
  fr.readAsDataURL(blob);
});

// 选好的照片 → 两份压好的图（还没上传）；读不出来返回 null
export async function preparePhoto(file) {
  let src;
  try { src = await decode(file); } catch { return null; }
  if (!src || !src.width) return null;
  let full = await shrink(src, 1600, 0.82);
  if (full && full.size > 2.8 * 1024 * 1024) full = await shrink(src, 1280, 0.7);
  const thumb = await shrink(src, 480, 0.78);
  src.close?.();
  if (!full || !thumb) return null;
  return { full, thumb, preview: URL.createObjectURL(thumb) };
}

export async function uploadPhoto(p) {
  const out = await post("/api/photo", { data: await b64(p.full), thumb: await b64(p.thumb) });
  return out.photo;
}

// ---------------------------------------------------------------- 留下一个瞬间 ----
// wish：默认挂在哪个愿望下（null = 不挂）；moment：传了就是编辑；day：默认哪一天
export function openMoment({ wish = null, moment = null, day = "", onSaved } = {}) {
  const J = state.data.journey || {};
  const today = J.today;
  const wishes = J.wishes || [];
  const edit = !!moment;
  let wid = edit ? moment.wish_id || "" : wish?.id || "";
  let pickDay = edit ? moment.day : day || today;
  let mood = edit ? moment.mood || "" : "";
  let moods = [...(state.data.profile?.custom_moods || [])];
  let photo = edit ? moment.photo || "" : "";     // 已经在服务器上的照片 id
  let fresh = null;                                // 这次新选的（还没传）
  const curWish = () => wishes.find((w) => w.id === wid) || null;
  const opts = [[today, "今天"], [addDays(today, -1), "昨天"], [addDays(today, -2), "前天"]];

  const body = h("div", { class: "mo-sheet j-compose", html: `
    <div class="mo-photo"></div>
    <div class="lbl">发生了什么</div>
    <textarea class="field" id="moText" rows="3" maxlength="300" placeholder="${PH}">${esc(moment?.text || "")}</textarea>
    <label class="lbl">当时的感受 <span class="muted">（可选）</span></label>
    <input class="field" id="moFeel" maxlength="80" placeholder="比如：慢慢放松了一些" value="${esc(moment?.feeling || "")}">
    <div class="j-moods"></div>
    ${wishes.length ? `<div class="lbl">放进哪个愿望 <span class="muted">（可选）</span></div><div class="j-wishpick mo-wishes"></div>` : ""}
    <label class="lbl">哪一天</label>
    <div class="j-days">${opts.map(([d, l]) => `<button class="chip ${d === pickDay ? "on" : ""}" type="button" data-day="${d}">${l}</button>`).join("")}
      <input class="field field-date" type="date" max="${today}" min="${addDays(today, -365)}" value="${opts.some(([d]) => d === pickDay) ? "" : pickDay}" aria-label="选一个更早的日期"></div>
    <input type="file" accept="image/*" hidden>` });
  const ta = body.querySelector("#moText");
  const file = body.querySelector("input[type=file]");

  // 照片：一张；点空框选图，选了能换、能去掉
  const slot = body.querySelector(".mo-photo");
  const drawPhoto = () => {
    const src = fresh?.preview || photoURL(photo, true);
    slot.innerHTML = src
      ? `<img src="${esc(src)}" alt="这个瞬间的照片"><div class="mo-photo-acts"><button type="button" class="btn btn-sm" data-pick>${icon("camera")}换一张</button><button type="button" class="btn btn-sm" data-unpick>${icon("trash")}去掉</button></div>`
      : `<button type="button" class="mo-photo-add" data-pick>${icon("camera")}<span>加一张照片</span><small>可选，只有你自己看得到</small></button>`;
    slot.classList.toggle("has", !!src);
    slot.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => file.click()));
    slot.querySelector("[data-unpick]")?.addEventListener("click", () => { fresh = null; photo = ""; drawPhoto(); });
  };
  file.addEventListener("change", async () => {
    const f = file.files?.[0];
    file.value = "";
    if (!f) return;
    slot.classList.add("busy");
    const p = await preparePhoto(f);
    slot.classList.remove("busy");
    if (!p) return toast("这张照片读不出来，换一张试试", "err");
    fresh = p;
    drawPhoto();
  });
  drawPhoto();

  // 心情：预设 + 自己的（带 ×）+「别的心情」
  const moodBox = body.querySelector(".j-moods");
  const saveMoods = async () => { try { setData(await api.profile({ custom_moods: moods }), { silent: true }); } catch (e) { toast(e.message, "err"); } };
  const drawMoods = () => {
    moodBox.innerHTML = MOODS.map((t) => `<button class="chip ${mood === t ? "on" : ""}" type="button" data-m="${esc(t)}">${esc(t)}</button>`).join("")
      + moods.map((t) => `<span class="chip mine ${mood === t ? "on" : ""}"><button type="button" data-m="${esc(t)}">${esc(t)}</button><button type="button" class="x" data-rm="${esc(t)}" aria-label="删掉「${esc(t)}」">×</button></span>`).join("")
      + (moods.length < 8 ? `<button class="chip add" type="button" data-add>${icon("plus")}别的心情</button>` : "");
    moodBox.querySelectorAll("[data-m]").forEach((b) => b.addEventListener("click", () => { mood = mood === b.dataset.m ? "" : b.dataset.m; drawMoods(); }));
    moodBox.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", async () => {
      moods = moods.filter((x) => x !== b.dataset.rm); if (mood === b.dataset.rm) mood = ""; drawMoods(); await saveMoods();
    }));
    moodBox.querySelector("[data-add]")?.addEventListener("click", (e) => {
      const inp = h("input", { class: "field chip-input", maxlength: "8", placeholder: "比如：松了口气" });
      e.currentTarget.replaceWith(inp);
      inp.focus();
      let fired = false;
      const done = async () => {
        if (fired) return; fired = true;
        const v = inp.value.trim();
        if (v && !moods.includes(v) && !MOODS.includes(v)) { moods.push(v); mood = v; await saveMoods(); }
        drawMoods();
      };
      inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); done(); } if (ev.key === "Escape") drawMoods(); });
      inp.addEventListener("blur", done);
    });
  };
  drawMoods();

  // 放进哪个愿望：每个愿望一个，加一个「不放进愿望」
  const wishBox = body.querySelector(".mo-wishes");
  const drawWishes = () => {
    if (!wishBox) return;
    wishBox.innerHTML = `<button type="button" class="chip ${wid ? "" : "on"}" data-w="">不放进愿望</button>`
      + wishes.map((w) => `<button type="button" class="chip ${w.id === wid ? "on" : ""}" data-w="${esc(w.id)}">${tile(catOf(w.category).icon, catOf(w.category).color, 20)}<span>${esc(w.title)}</span></button>`).join("");
    wishBox.querySelectorAll("[data-w]").forEach((b) => b.addEventListener("click", () => { wid = b.dataset.w; drawWishes(); }));
  };
  drawWishes();

  const dateIn = body.querySelector(".field-date");
  body.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => {
    pickDay = b.dataset.day; dateIn.value = "";
    body.querySelectorAll("[data-day]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  dateIn.addEventListener("change", () => {
    if (!dateIn.value) return;
    pickDay = dateIn.value;
    body.querySelectorAll("[data-day]").forEach((x) => x.classList.remove("on"));
  });

  const save = async () => {
    if (!ta.value.trim()) { ta.focus(); return toast("写一句发生了什么就好"); }
    btn.disabled = true;
    btn.textContent = fresh ? "照片传上去…" : "留下来…";
    try {
      const pid = fresh ? await uploadPhoto(fresh) : photo;
      const payload = { text: ta.value, feeling: body.querySelector("#moFeel").value, mood, day: pickDay, wish_id: wid, photo: pid };
      const out = edit ? await api.moment("edit", { id: moment.id, ...payload }) : await api.moment("add", payload);
      s.close();
      if (fresh) URL.revokeObjectURL(fresh.preview);
      if (onSaved) onSaved(out, { day: pickDay, wish_id: wid, edit });
      else {
        setData(out);
        toast(edit ? "改好了" : xpNote(out.xp) ? `留下了 · ${xpNote(out.xp)}` : "留下了", "", "camera");
      }
    } catch (e) {
      btn.disabled = false;
      btn.textContent = edit ? "保存" : "留下来";
      toast(e.message, "err");
    }
  };
  const btn = h("button", { class: "btn btn-main", onclick: save }, edit ? "保存" : "留下来");
  const s = sheet({ title: edit ? "编辑这个瞬间" : "留下一个瞬间", body, sticker: "camera",
    footer: [h("button", { class: "btn btn-ghost", onclick: () => s.close() }, edit ? "取消" : "先不写"), btn] });
  s.panel.classList.add("j-sheet", "mo-sheet-panel");
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); });
  if (!edit) setTimeout(() => ta.focus(), 60);
  return s;
}

// 删掉一个瞬间（照片一起删）
export async function deleteMoment(m) {
  if (!(await confirmSheet("删掉这个瞬间？", m.photo ? "照片会一起删掉，删了就找不回来了。" : "删了就找不回来了。", "删掉", "trash"))) return null;
  return api.moment("delete", { id: m.id });
}
