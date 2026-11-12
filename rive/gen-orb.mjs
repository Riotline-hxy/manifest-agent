// 生成小光光球的 Rive 场景：node gen-orb.mjs → xiaoguang-orb/scene.rml
// 改造型 / 动作就改这里再重新生成，不要手改 scene.rml（会被覆盖）。
//
// 结构：
//   Float（常驻漂浮）> Pose（心情姿态）> Squish（戳一下的弹跳）> 光晕 / 身体 / 高光 / Face（视线）> Look（跟随鼠标）> 眼睛、嘴
// 状态机分层：Float 漂浮 · Blink 眨眼 · Mood 心情（8 种，互相平滑过渡）· Poke 戳一下 · News 新消息红点
// 宿主通过 view model「Orb」驱动：mood（枚举）、hasNews（布尔）、poke（触发器）

import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "xiaoguang-orb", "scene.rml");

// ── 颜色（ARGB）──────────────────────────────────────────────
const C = {
  ink: "FF2A2140", // 眼睛 / 嘴：深梅子墨色，比纯黑柔和
  white: "FFFFFFFF",
  body0: "FFFFFBEA", body1: "FFFFE68C", body2: "FFFFC94D", body3: "FFF29A35",
  glow: "FFFFC94D", glowFar: "FFFFDB7A",
  cheek: "FFFF8E9E",
  dots: "FFFFE08A",
  comet: "FFFFF3C8",
  zz: "FFFFEFB8",
  news: "FFFF5E5E",
  shadow: "55000000",
};

// ── id ──────────────────────────────────────────────────────
let next = 10;
const nid = () => `0:${next++}`;
const ID = new Proxy({}, { get: (t, k) => (t[k] ??= nid()) });

// ── 画图小工具 ───────────────────────────────────────────────
const fill = (color, extra = "") => `<Fill name="Fill"${extra}><SolidColor colorValue="${color}" name="C"/></Fill>`;
const featherFill = (color, strength) =>
  `<Fill fillRule="clockwise" name="Glow"><SolidColor colorValue="${color}" name="C"/><Feather strength="${strength}" name="F"/></Fill>`;
const stroke = (color, t) => `<Stroke thickness="${t}" cap="round" join="round" name="Stroke"><SolidColor colorValue="${color}" name="C"/></Stroke>`;
const ellipse = (w, h = w) => `<Ellipse width="${w}" height="${h}" originX="0.5" originY="0.5" name="Path"/>`;
const rrect = (w, h, r) => `<Rectangle width="${w}" height="${h}" cornerRadiusTL="${r}" originX="0.5" originY="0.5" name="Path"/>`;
const node = (name, attrs, ...kids) => `<Node ${attrs} name="${name}" id="${ID[name]}">${kids.join("")}</Node>`;
const shape = (name, attrs, ...kids) => `<Shape ${attrs} name="${name}" id="${ID[name]}">${kids.join("")}</Shape>`;
const openPath = (verts) => `<PointsPath isClosed="false" name="Path">${verts.join("")}</PointsPath>`;
const sv = (x, y, r = 0) => `<StraightVertex x="${x}" y="${y}"${r ? ` radius="${r}"` : ""}/>`;
const cv = (x, y, rot, d) => `<CubicMirroredVertex x="${x}" y="${y}" rotation="${rot}" distance="${d}"/>`;

// ── 眼睛 ────────────────────────────────────────────────────
// EyeOpen（心情改大小）> Blink（眨眼）> [Wink（戳一下眨单眼）] > Pill（睁眼）；Arc（开心的 ^）不跟着眨
function eye(side) {
  const s = side === "L" ? -1 : 1;
  const pill = node(`Pill${side}`, "",
    shape(`Catch${side}`, `x="5" y="-10"`, ellipse(9), fill(C.white)),
    shape(`PillShape${side}`, "", rrect(24, 42, 12), fill(C.ink)));
  const blinkKids = side === "R" ? node("WinkR", "", pill) : pill;
  return node(`Eye${side}`, `x="${s * 34}" y="-8"`,
    node(`EyeOpen${side}`, "",
      node(`Arc${side}`, `opacity="0"`, shape(`ArcShape${side}`, "", openPath([sv(-12, 6), sv(0, -6, 12), sv(12, 6)]), stroke(C.ink, 6.5))),
      node(`Blink${side}`, "", blinkKids)));
}

// ── 环绕光点（working）：前半圈画在身体前面，后半圈画在身体后面 ──
const ORBIT = { rx: 132, ry: 28, frames: 180, steps: 36 };
const COMETS = [
  { name: "CometA", phase: 0, size: 13 },
  { name: "CometA2", phase: -0.28, size: 8 },
  { name: "CometA3", phase: -0.52, size: 5 },
  { name: "CometB", phase: Math.PI, size: 9 },
  { name: "CometB2", phase: Math.PI - 0.3, size: 5 },
];
const comets = (half) =>
  COMETS.map((c) => shape(`${c.name}${half}`, `x="${ORBIT.rx * Math.cos(c.phase)}" y="0"`, ellipse(c.size), fill(C.comet))).join("");

// ── 场景树（先声明的画在上面）────────────────────────────────
const zLetter = (name, attrs) => node(name, attrs, shape(`${name}Shape`, "", openPath([sv(-7, -7), sv(7, -7), sv(-7, 7), sv(7, 7)]), stroke(C.zz, 3.5)));

const scene = `
${node("Anchor", `x="200" y="200"`, node("Float", "",
  node("News", `x="70" y="-74" scaleX="0" scaleY="0"`,
    shape("NewsDot", "", ellipse(24), `<Stroke thickness="3.5" name="Ring"><SolidColor colorValue="${C.white}" name="C"/></Stroke>`, fill(C.news))),
  node("Zz", `x="74" y="-96" opacity="0"`, zLetter("Z1", ""), zLetter("Z2", `x="24" y="-26" scaleX="0.7" scaleY="0.7"`)),
  node("Dots", `opacity="0"`,
    node("D1", `x="64" y="-98"`, shape("D1Shape", "", ellipse(9), fill(C.dots))),
    node("D2", `x="84" y="-117"`, shape("D2Shape", "", ellipse(12), fill(C.dots))),
    node("D3", `x="108" y="-138"`, shape("D3Shape", "", ellipse(15), fill(C.dots)))),
  node("OrbitFront", `y="72" rotation="-0.1" opacity="0"`, comets("F")),
  node("Pose", "",
    node("Squish", "",
      node("Face", "",
        node("Look", "",
          eye("L"), eye("R"),
          node("Mouth", `y="30"`,
            node("Smile", "", shape("SmileShape", "", openPath([sv(-9, -2), cv(0, 4, 0, 6), sv(9, -2)]), stroke(C.ink, 4))),
            node("MouthO", `opacity="0"`, shape("MouthOShape", "", rrect(18, 15, 7.5), fill(C.ink))))),
        node("Cheeks", `opacity="0.55"`,
          shape("CheekL", `x="-60" y="20"`, ellipse(28, 15), featherFill(C.cheek, 6)),
          shape("CheekR", `x="60" y="20"`, ellipse(28, 15), featherFill(C.cheek, 6)))),
      node("Shine", `x="-38" y="-50" rotation="-0.55"`,
        shape("ShineShape", `opacity="0.7"`, ellipse(52, 28), featherFill(C.white, 8))),
      shape("Body", "", ellipse(190),
        `<Fill name="Fill"><RadialGradient startX="-28" startY="-38" endX="114" endY="-38" name="G">` +
          `<GradientStop colorValue="${C.body0}" position="0"/><GradientStop colorValue="${C.body1}" position="0.32"/>` +
          `<GradientStop colorValue="${C.body2}" position="0.72"/><GradientStop colorValue="${C.body3}" position="1"/>` +
        `</RadialGradient></Fill>`),
      node("Halo", `opacity="0.8"`,
        shape("HaloNear", "", ellipse(200), featherFill(C.glow, 26)),
        shape("HaloFar", `opacity="0.4"`, ellipse(250), featherFill(C.glowFar, 60))))),
  node("OrbitBack", `y="72" rotation="-0.1" opacity="0"`, comets("B"))))}
${node("ShadowN", `x="200" y="342"`, shape("ShadowShape", "", ellipse(110, 14), featherFill(C.shadow, 10)))}
${node("LookHandle", `x="200" y="200"`)}
${shape("HitArea", `x="200" y="200"`, rrect(400, 400, 0), fill("00000000"))}
<Joystick posX="200" posY="200" width="400" height="400" xId="${ID.animLookX}" yId="${ID.animLookY}" handleSourceId="${ID.LookHandle}" name="Look" id="${ID.Joystick}"/>
<Event name="poked" id="${ID.EvPoked}"/>`;

// ── 动画小工具 ───────────────────────────────────────────────
// track: [[frame, value], ...]；value 相同的单帧轨道就是「保持这个值」
const EASE = `<CubicEaseInterpolator x1="0.42" y1="0" x2="0.58" y2="1"/>`;
function kfs(track, interp = "cubic") {
  return track
    .map(([f, v]) =>
      interp === "cubic"
        ? `<KeyFrameDouble frame="${f}" value="${+v.toFixed(4)}" interpolationType="cubic">${EASE}</KeyFrameDouble>`
        : `<KeyFrameDouble frame="${f}" value="${+v.toFixed(4)}" interpolationType="${interp}"/>`)
    .join("");
}
// props: { "Obj.prop": number | track | {track, interp} }
function anim(name, duration, loop, props) {
  const byObj = {};
  for (const [k, v] of Object.entries(props)) {
    const [obj, prop] = k.split(".");
    const spec = typeof v === "number" ? { track: [[0, v]] } : Array.isArray(v) ? { track: v } : v;
    (byObj[obj] ??= []).push(`<KeyedProperty property="${prop}">${kfs(spec.track, spec.interp)}</KeyedProperty>`);
  }
  const keyed = Object.entries(byObj).map(([obj, ps]) => `<KeyedObject objectId="${ID[obj]}">${ps.join("")}</KeyedObject>`).join("");
  return `<LinearAnimation loopValue="${loop}" fps="60" duration="${duration}" name="${name}" id="${ID["anim" + name]}">${keyed}</LinearAnimation>`;
}
const both = (prefix, prop, v) => ({ [`${prefix}L.${prop}`]: v, [`${prefix}R.${prop}`]: v });
const shift = (track, k) => track.map(([f, v]) => [f, v * k]);

// ── 心情：每个心情都要把下面这些属性全部写上，过渡时才能完整混合 ──
const MOOD_BASE = {
  "Pose.y": 0, "Pose.rotation": 0, "Pose.scaleX": 1, "Pose.scaleY": 1,
  "Face.x": 0, "Face.y": 0,
  ...both("EyeOpen", "scaleX", 1), ...both("EyeOpen", "scaleY", 1),
  ...both("Pill", "opacity", 1), ...both("Arc", "opacity", 0),
  "Smile.opacity": 1, "MouthO.opacity": 0, "MouthO.scaleX": 1, "MouthO.scaleY": 1,
  "Cheeks.opacity": 0.55, "Dots.opacity": 0, "OrbitFront.opacity": 0, "OrbitBack.opacity": 0, "Zz.opacity": 0,
  "Halo.scaleX": 1, "Halo.scaleY": 1, "Halo.opacity": 0.8,
};

function cometTracks() {
  const out = {};
  const { rx, ry, frames, steps } = ORBIT;
  for (const c of COMETS) {
    const x = [], y = [], front = [], back = [];
    for (let i = 0; i <= steps; i++) {
      const f = Math.round((i / steps) * frames);
      const a = c.phase + (i / steps) * Math.PI * 2;
      const isFront = Math.sin(a) > 0; // 下半圈（y 为正）在身体前面
      x.push([f, rx * Math.cos(a)]); y.push([f, ry * Math.sin(a)]);
      front.push([f, isFront ? 1 : 0]); back.push([f, isFront ? 0 : 1]);
    }
    for (const half of ["F", "B"]) {
      out[`${c.name}${half}.x`] = { track: x, interp: "linear" };
      out[`${c.name}${half}.y`] = { track: y, interp: "linear" };
      out[`${c.name}${half}.opacity`] = { track: half === "F" ? front : back, interp: "linear" };
    }
  }
  return out;
}

const pulse = (from, to, d, offset = 0) => [[0, from], [offset, from], [offset + 20, to], [offset + 45, from], [d, from]];

const MOODS = [
  { key: "idle", label: "待机", d: 360, p: {
    "Face.x": [[0, 0], [60, 0], [90, -6], [170, -6], [200, 5], [280, 5], [320, 0], [360, 0]],
    "Face.y": [[0, 0], [90, -2], [170, -2], [200, 1], [280, 1], [320, 0], [360, 0]],
    "Halo.scaleX": [[0, 1], [180, 1.04], [360, 1]], "Halo.scaleY": [[0, 1], [180, 1.04], [360, 1]],
  }},
  { key: "listening", label: "在听", d: 120, p: {
    "Pose.rotation": 0.1, "Pose.scaleX": 1.03, "Pose.scaleY": 1.03,
    "Pose.y": [[0, 0], [20, 3], [40, 0], [120, 0]],
    "Face.x": 3, "Face.y": -2,
    ...both("EyeOpen", "scaleX", 1.08), ...both("EyeOpen", "scaleY", 1.12),
    "Smile.opacity": 0.85, "Cheeks.opacity": 0.65,
    "Halo.scaleX": [[0, 1.06], [60, 1.15], [120, 1.06]], "Halo.scaleY": [[0, 1.06], [60, 1.15], [120, 1.06]],
    "Halo.opacity": [[0, 0.9], [60, 1], [120, 0.9]],
  }},
  { key: "thinking", label: "思考", d: 150, p: {
    "Pose.rotation": -0.07, "Face.x": [[0, 9], [75, 12], [150, 9]], "Face.y": -9,
    ...both("EyeOpen", "scaleY", 0.9),
    "Smile.opacity": 0, "MouthO.opacity": 1, "MouthO.scaleX": 0.5, "MouthO.scaleY": 0.45, "Cheeks.opacity": 0.4,
    "Dots.opacity": 1,
    "D1.scaleX": pulse(0.6, 1.2, 150, 0), "D1.scaleY": pulse(0.6, 1.2, 150, 0),
    "D2.scaleX": pulse(0.6, 1.2, 150, 25), "D2.scaleY": pulse(0.6, 1.2, 150, 25),
    "D3.scaleX": pulse(0.6, 1.2, 150, 50), "D3.scaleY": pulse(0.6, 1.2, 150, 50),
  }},
  { key: "working", label: "忙活", d: ORBIT.frames, p: {
    "Pose.rotation": [[0, -0.03], [90, 0.03], [180, -0.03]], "Face.y": 6,
    ...both("EyeOpen", "scaleY", 0.8), "Smile.opacity": 0.7, "Cheeks.opacity": 0.45,
    "OrbitFront.opacity": 1, "OrbitBack.opacity": 1, "Halo.opacity": 0.9,
    ...cometTracks(),
  }},
  { key: "speaking", label: "说话", d: 96, p: {
    "Smile.opacity": 0, "MouthO.opacity": 1,
    "MouthO.scaleY": [[0, 0.35], [8, 1], [16, 0.5], [24, 0.9], [32, 0.3], [42, 0.85], [50, 0.45], [60, 1], [70, 0.4], [80, 0.75], [96, 0.35]],
    "MouthO.scaleX": [[0, 0.9], [8, 1.05], [24, 0.95], [42, 1.05], [60, 1], [80, 0.95], [96, 0.9]],
    "Pose.scaleY": [[0, 1], [8, 1.02], [16, 0.99], [24, 1.015], [32, 0.99], [60, 1.02], [96, 1]],
    "Pose.y": [[0, 0], [24, -2], [48, 0], [72, -2], [96, 0]],
    "Face.x": [[0, -2], [48, 2], [96, -2]], ...both("EyeOpen", "scaleY", 1.04), "Cheeks.opacity": 0.65,
    "Halo.scaleX": [[0, 1.02], [8, 1.08], [32, 1.03], [60, 1.08], [96, 1.02]],
    "Halo.scaleY": [[0, 1.02], [8, 1.08], [32, 1.03], [60, 1.08], [96, 1.02]],
  }},
  { key: "happy", label: "开心", d: 72, p: {
    ...both("Pill", "opacity", 0), ...both("Arc", "opacity", 1),
    "Smile.opacity": 0, "MouthO.opacity": 1, "MouthO.scaleX": 1.15, "MouthO.scaleY": 0.85, "Cheeks.opacity": 0.95,
    "Pose.y": [[0, 0], [18, -14], [36, 0], [54, -14], [72, 0]],
    "Pose.scaleY": [[0, 0.93], [8, 1.06], [18, 1], [30, 1.03], [36, 0.93], [44, 1.06], [54, 1], [66, 1.03], [72, 0.93]],
    "Pose.scaleX": [[0, 1.06], [8, 0.96], [18, 1], [30, 0.98], [36, 1.06], [44, 0.96], [54, 1], [66, 0.98], [72, 1.06]],
    "Pose.rotation": [[0, -0.05], [36, 0.05], [72, -0.05]],
    "Halo.scaleX": 1.1, "Halo.scaleY": 1.1, "Halo.opacity": 1,
  }},
  { key: "surprised", label: "惊讶", d: 90, p: {
    ...both("EyeOpen", "scaleX", 1.18), ...both("EyeOpen", "scaleY", 1.28),
    "Smile.opacity": 0, "MouthO.opacity": 1, "MouthO.scaleX": 0.85, "MouthO.scaleY": 1.15,
    "Pose.y": -6, "Pose.scaleX": 0.97, "Pose.scaleY": 1.05, "Face.y": -3, "Cheeks.opacity": 0.5,
    "Halo.scaleX": [[0, 1.12], [45, 1.2], [90, 1.12]], "Halo.scaleY": [[0, 1.12], [45, 1.2], [90, 1.12]], "Halo.opacity": 1,
  }},
  { key: "sleepy", label: "犯困", d: 240, p: {
    ...both("EyeOpen", "scaleY", -0.7), ...both("Pill", "opacity", 0), ...both("Arc", "opacity", 1),
    "Smile.opacity": 0, "MouthO.opacity": 0.9, "MouthO.scaleX": 0.55, "MouthO.scaleY": [[0, 0.35], [120, 0.55], [240, 0.35]],
    "Pose.rotation": 0.12, "Pose.y": 6, "Pose.scaleY": [[0, 0.97], [120, 1.02], [240, 0.97]], "Face.y": 4, "Cheeks.opacity": 0.5,
    "Halo.opacity": 0.45, "Halo.scaleX": [[0, 0.95], [120, 1], [240, 0.95]], "Halo.scaleY": [[0, 0.95], [120, 1], [240, 0.95]],
    "Zz.opacity": 1,
    "Z1.y": { track: [[0, 8], [240, -22]], interp: "linear" }, "Z1.opacity": [[0, 0], [50, 1], [190, 1], [240, 0]],
    "Z2.y": { track: [[0, -26], [120, -41], [121, -11], [240, -26]], interp: "linear" },
    "Z2.opacity": [[0, 1], [70, 1], [120, 0], [121, 0], [170, 1], [240, 1]],
  }},
];

// ── 其它层的动画 ─────────────────────────────────────────────
const animations = [
  anim("Float", 240, "loop", {
    "Float.y": [[0, 0], [120, -7], [240, 0]],
    "ShadowN.scaleX": [[0, 1], [120, 0.84], [240, 1]], "ShadowN.opacity": [[0, 1], [120, 0.65], [240, 1]],
  }),
  anim("Blink", 300, "loop", both("Blink", "scaleY", {
    interp: "linear",
    track: [[0, 1], [170, 1], [174, 0.08], [180, 1], [252, 1], [255, 0.08], [260, 1], [263, 0.08], [268, 1], [300, 1]],
  })),
  ...MOODS.map((m) => anim(`Mood_${m.key}`, m.d, "loop", { ...MOOD_BASE, ...m.p })),
  anim("PokeRest", 1, "oneShot", { "Squish.scaleX": 1, "Squish.scaleY": 1, "Squish.rotation": 0, "WinkR.scaleY": 1 }),
  anim("PokeBoing", 54, "oneShot", {
    "Squish.scaleY": [[0, 1], [6, 0.82], [16, 1.12], [28, 0.95], [40, 1.02], [54, 1]],
    "Squish.scaleX": [[0, 1], [6, 1.14], [16, 0.92], [28, 1.04], [40, 0.99], [54, 1]],
    "Squish.rotation": [[0, 0], [10, 0.09], [24, -0.05], [38, 0.02], [54, 0]],
    "WinkR.scaleY": [[0, 1], [8, 0.1], [34, 0.1], [42, 1], [54, 1]],
  }),
  anim("NewsOff", 1, "oneShot", { "News.scaleX": 0, "News.scaleY": 0 }),
  anim("NewsOn", 90, "loop", { "News.scaleX": [[0, 1], [45, 1.14], [90, 1]], "News.scaleY": [[0, 1], [45, 1.14], [90, 1]] }),
  anim("LookX", 60, "oneShot", {
    "Look.x": { track: [[0, -10], [60, 10]], interp: "linear" },
    "Shine.x": { track: [[0, -35], [60, -41]], interp: "linear" },
  }),
  anim("LookY", 60, "oneShot", {
    "Look.y": { track: [[0, -7], [60, 7]], interp: "linear" },
    "Shine.y": { track: [[0, -48], [60, -52]], interp: "linear" },
  }),
];

// ── 状态机 ──────────────────────────────────────────────────
const VM = { vm: ID.VmOrb, mood: ID.VmMood, news: ID.VmNews, poke: ID.VmPoke };
const enumCond = (valueId) => `<TransitionViewModelCondition><TransitionPropertyViewModelComparator><BindablePropertyEnum>` +
  `<DataBindContext sourcePathIds="${VM.vm}-${VM.mood}" propertyKey="637"/></BindablePropertyEnum></TransitionPropertyViewModelComparator>` +
  `<TransitionValueEnumComparator value="${valueId}"/></TransitionViewModelCondition>`;
const boolCond = (v) => `<TransitionViewModelCondition><TransitionPropertyViewModelComparator><BindablePropertyBoolean>` +
  `<DataBindContext sourcePathIds="${VM.vm}-${VM.news}" propertyKey="634"/></BindablePropertyBoolean></TransitionPropertyViewModelComparator>` +
  `<TransitionValueBooleanComparator value="${v}"/></TransitionViewModelCondition>`;
const triggerCond = `<TransitionViewModelCondition><TransitionPropertyViewModelComparator><BindablePropertyTrigger>` +
  `<DataBindContext sourcePathIds="${VM.vm}-${VM.poke}" propertyKey="686"/></BindablePropertyTrigger></TransitionPropertyViewModelComparator>` +
  `<TransitionValueTriggerComparator/></TransitionViewModelCondition>`;
const smooth = `<CubicEaseInterpolator x1="0.4" y1="0" x2="0.2" y2="1"/>`;

const simpleLayer = (name, anim, y) =>
  `<StateMachineLayer name="${name}" id="${nid()}"><AnyState x="400" y="${y - 120}"/><ExitState x="600" y="${y - 120}"/>` +
  `<EntryState x="0" y="${y}"><StateTransition stateToId="${ID["st" + name]}"/></EntryState>` +
  `<AnimationState x="200" y="${y}" animationId="${ID["anim" + anim]}" id="${ID["st" + name]}"/></StateMachineLayer>`;

const moodStates = MOODS.map((m, i) => {
  const out = MOODS.filter((o) => o !== m)
    .map((o) => `<StateTransition stateToId="${ID["stMood_" + o.key]}" duration="380" interpolationType="cubic">${smooth}${enumCond(ID["enum_" + o.key])}</StateTransition>`)
    .join("");
  return `<AnimationState x="${200 + (i % 4) * 220}" y="${Math.floor(i / 4) * 180}" animationId="${ID["animMood_" + m.key]}" id="${ID["stMood_" + m.key]}">${out}</AnimationState>`;
}).join("");

const stateMachine = `
<StateMachine name="Orb" id="${ID.SM}">
  <StateMachineListenerSingle targetId="${ID.HitArea}" listenerTypeValue="move" name="Look at pointer">
    <ListenerAlignTarget targetId="${ID.LookHandle}"/>
  </StateMachineListenerSingle>
  <StateMachineListenerSingle targetId="${ID.Body}" listenerTypeValue="click" name="Poke">
    <ListenerViewModelChange><BindablePropertyTrigger propertyValue="1">
      <DataBindContext sourcePathIds="${VM.vm}-${VM.poke}" propertyKey="686" direction="true"/>
    </BindablePropertyTrigger></ListenerViewModelChange>
  </StateMachineListenerSingle>
  ${simpleLayer("Float", "Float", 0)}
  ${simpleLayer("Blink", "Blink", 0)}
  <StateMachineLayer name="Mood" id="${nid()}">
    <AnyState x="200" y="-160"/><ExitState x="420" y="-160"/>
    <EntryState x="0" y="0"><StateTransition stateToId="${ID.stMood_idle}"/></EntryState>
    ${moodStates}
  </StateMachineLayer>
  <StateMachineLayer name="Poke" id="${nid()}">
    <AnyState x="200" y="-120"/><ExitState x="420" y="-120"/>
    <EntryState x="0" y="0"><StateTransition stateToId="${ID.stPokeRest}"/></EntryState>
    <AnimationState x="200" y="0" animationId="${ID.animPokeRest}" id="${ID.stPokeRest}">
      <StateTransition stateToId="${ID.stPokeBoing}">${triggerCond}</StateTransition>
    </AnimationState>
    <AnimationState x="420" y="0" animationId="${ID.animPokeBoing}" reset="true" id="${ID.stPokeBoing}">
      <StateMachineFireEvent eventId="${ID.EvPoked}" occursValue="0"/>
      <StateTransition stateToId="${ID.stPokeRest}" duration="120" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>
    </AnimationState>
  </StateMachineLayer>
  <StateMachineLayer name="News" id="${nid()}">
    <AnyState x="200" y="-120"/><ExitState x="420" y="-120"/>
    <EntryState x="0" y="0"><StateTransition stateToId="${ID.stNewsOff}"/></EntryState>
    <AnimationState x="200" y="0" animationId="${ID.animNewsOff}" id="${ID.stNewsOff}">
      <StateTransition stateToId="${ID.stNewsOn}" duration="260" interpolationType="cubic">${smooth}${boolCond(true)}</StateTransition>
    </AnimationState>
    <AnimationState x="420" y="0" animationId="${ID.animNewsOn}" id="${ID.stNewsOn}">
      <StateTransition stateToId="${ID.stNewsOff}" duration="200">${boolCond(false)}</StateTransition>
    </AnimationState>
  </StateMachineLayer>
</StateMachine>`;

// ── 数据：宿主只需要设置 mood / hasNews，或者触发 poke ─────────
const data = `
<DataEnumCustom name="Mood" id="${ID.EnumMood}">
  ${MOODS.map((m) => `<DataEnumValue key="${m.key}" value="${m.label}" id="${ID["enum_" + m.key]}"/>`).join("\n  ")}
</DataEnumCustom>
<ViewModel defaultInstanceId="${ID.VmInst}" name="Orb" id="${VM.vm}">
  <ViewModelPropertyEnumCustom enumId="${ID.EnumMood}" name="mood" id="${VM.mood}"/>
  <ViewModelPropertyBoolean name="hasNews" id="${VM.news}"/>
  <ViewModelPropertyTrigger name="poke" id="${VM.poke}"/>
  <ViewModelInstance exports="true" name="Default" id="${ID.VmInst}">
    <ViewModelInstanceEnum propertyValue="${ID.enum_idle}" viewModelPropertyId="${VM.mood}"/>
    <ViewModelInstanceBoolean propertyValue="false" viewModelPropertyId="${VM.news}"/>
    <ViewModelInstanceTrigger viewModelPropertyId="${VM.poke}"/>
  </ViewModelInstance>
</ViewModel>`;

const rml = `<Rive version="1" kind="fragment">
<Artboard defaultStateMachineId="${ID.SM}" viewModelId="${VM.vm}" viewModelInstanceId="${ID.VmInst}" styleId="${ID.Style}" width="400" height="400" name="XiaoguangOrb" id="${ID.Artboard}">
<LayoutComponentStyle name="Artboard Style" id="${ID.Style}"/>
${stateMachine}
${scene}
${animations.join("\n")}
</Artboard>
${data}
</Rive>
`;

writeFileSync(OUT, rml);
console.log(`wrote ${OUT} (${MOODS.length} moods, ${animations.length} animations, last id ${next - 1})`);
