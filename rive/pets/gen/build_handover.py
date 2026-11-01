"""生成交接用的单文件网页：python -I gen/build_handover.py → xiaoya-pets-handover.html

所有东西都嵌在一个 HTML 里（Rive 网页运行时、WASM、10 只宠物的 .riv），双击就能打开，不需要服务器。
"""
import base64
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW = os.path.join(ROOT, "review")
OUT = os.path.join(ROOT, "xiaoya-pets-handover.html")

PETS = [
    {"id": "baby", "name": "初生小芽", "stage": "初生", "route": "", "skill": ""},
    {"id": "sprout", "name": "抽芽期小芽", "stage": "抽芽期", "route": "", "skill": ""},
    {"id": "fox-young", "name": "小焰", "stage": "幼体", "route": "行动路线", "skill": "余温", "note": "尾尖亮起，暖光从脚边铺开，光点升起收淡"},
    {"id": "fox-adult", "name": "焰尾狐", "stage": "成年", "route": "行动路线", "skill": "余温", "note": "尾尖亮起，暖光从脚边铺开，光点升起收淡"},
    {"id": "deer-young", "name": "花苞", "stage": "幼体", "route": "好消息路线", "skill": "留芳", "note": "抬头，花瓣从花角两侧飘落"},
    {"id": "deer-adult", "name": "花角鹿", "stage": "成年", "route": "好消息路线", "skill": "留芳", "note": "抬头，花瓣从花角两侧飘落"},
    {"id": "water-young", "name": "涟芽", "stage": "幼体", "route": "练习路线", "skill": "回澜", "note": "抬起蓄势，轻点地面，两圈水纹扩散"},
    {"id": "water-adult", "name": "澜灵", "stage": "成年", "route": "练习路线", "skill": "回澜", "note": "抬起蓄势，轻点地面，两圈水纹扩散"},
    {"id": "star-young", "name": "星点", "stage": "幼体", "route": "均衡路线", "skill": "连星", "note": "尾尖轻点，五颗星依次亮起连成小径"},
    {"id": "star-adult", "name": "星灵", "stage": "成年", "route": "均衡路线", "skill": "连星", "note": "尾尖轻点，五颗星依次亮起连成小径"},
]


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


riv = {}
for p in PETS:
    path = os.path.join(REVIEW, "riv", f"{p['id']}.riv")
    riv[p["id"]] = b64(path)
    p["kb"] = os.path.getsize(path) // 1024
wasm = b64(os.path.join(REVIEW, "vendor", "rive.wasm"))
runtime = open(os.path.join(REVIEW, "vendor", "rive.js"), encoding="utf8").read()
today = datetime.date.today().isoformat()

rows = "".join(
    f"<tr><td><b>{p['name']}</b></td><td>{p['stage']}</td><td>{p['route'] or '—'}</td>"
    f"<td>{('「' + p['skill'] + '」' + p['note']) if p['skill'] else '—（分化后才有）'}</td>"
    f"<td><code>{p['id']}.riv</code></td><td>{p['kb']} KB</td>"
    f"<td><button class='dl' data-id='{p['id']}'>下载</button></td></tr>"
    for p in PETS)

html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>小芽宠物动效 · 交接</title>
<style>
  :root {{ --bg: #f6f3ec; --card: #fffdf8; --ink: #3a3530; --muted: #8b8379; --line: #ebe4d8; --soft: #fbf8f2; }}
  * {{ box-sizing: border-box; }}
  html, body {{ overflow-x: hidden; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.7 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 32px 22px 64px; }}
  h1 {{ font-size: 26px; margin: 0; font-weight: 650; }}
  .sub {{ color: var(--muted); margin: 4px 0 0; }}
  nav {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 18px 0 8px; }}
  nav a {{ color: var(--ink); text-decoration: none; font-size: 13px; padding: 4px 12px; border: 1px solid var(--line); border-radius: 999px; background: #fff; }}
  h2 {{ font-size: 18px; margin: 40px 0 12px; font-weight: 650; }}
  h3 {{ font-size: 15px; margin: 22px 0 8px; }}
  p, li {{ color: #4a443d; }}
  code {{ background: #f1ece2; padding: 1px 6px; border-radius: 5px; font-size: 13px; }}
  pre {{ background: #2f2b27; color: #f3eee6; padding: 14px 16px; border-radius: 12px; overflow: auto; font-size: 13px; line-height: 1.6; }}
  pre code {{ background: none; padding: 0; color: inherit; }}
  .tbl {{ overflow-x: auto; border-radius: 14px; }}
  table {{ width: 100%; min-width: 620px; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; font-size: 14px; }}
  th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  th {{ background: var(--soft); color: var(--muted); font-weight: 600; font-size: 13px; }}
  tr:last-child td {{ border-bottom: 0; }}
  .show {{ display: grid; grid-template-columns: 1fr 300px; gap: 22px; }}
  .stage {{ background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 16px; position: relative; }}
  canvas {{ width: 100%; aspect-ratio: 1; display: block; cursor: pointer; border-radius: 18px; background: radial-gradient(circle at 50% 64%, #fff 0, #fbf6ec 72%); }}
  .now {{ position: absolute; left: 32px; top: 28px; font-size: 13px; color: var(--muted); background: rgba(255,255,255,.88); padding: 2px 10px; border-radius: 999px; }}
  .who {{ display: flex; align-items: baseline; gap: 10px; margin: 12px 6px 0; }}
  .who b {{ font-size: 20px; }}
  .who span {{ color: var(--muted); font-size: 13px; }}
  aside {{ display: flex; flex-direction: column; gap: 18px; }}
  .group h4 {{ margin: 0 0 8px; font-size: 13px; color: var(--muted); font-weight: 600; letter-spacing: 1px; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .acts {{ display: grid; gap: 6px; }}
  button {{ border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 12px; padding: 7px 12px; font: inherit; font-size: 14px; cursor: pointer; text-align: left; }}
  .chips button, button.dl {{ border-radius: 999px; padding: 3px 12px; font-size: 13px; }}
  button:hover {{ border-color: #d9cdb9; background: #fffaf1; }}
  button.on {{ background: #3a3530; color: #fff; border-color: #3a3530; }}
  button small {{ display: block; color: var(--muted); font-size: 12px; }}
  button.on small {{ color: #d8d0c4; }}
  button:disabled {{ opacity: .4; cursor: default; }}
  .tip {{ color: var(--muted); font-size: 12px; margin: 0; }}
  .note {{ background: var(--soft); border: 1px solid var(--line); border-radius: 14px; padding: 12px 16px; }}
  @media (max-width: 780px) {{ .show {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <h1>小芽宠物动效 · 交接</h1>
  <p class="sub">10 个形态 · Rive 原生动画 · {today} · 这一个文件就能看全部动作，也能把每只宠物的 .riv 下载下来</p>
  <nav>
    <a href="#show">动作预览</a><a href="#list">形象清单</a><a href="#actions">动作说明</a>
    <a href="#api">接入方式</a><a href="#rules">设计约定</a><a href="#edit">怎么修改</a><a href="#known">已知问题</a>
  </nav>

  <h2 id="show">动作预览</h2>
  <div class="show">
    <div class="stage">
      <canvas id="cv" width="900" height="900"></canvas>
      <div class="now" id="now">待机</div>
      <div class="who"><b id="name"></b><span id="tag"></span></div>
    </div>
    <aside>
      <div class="group"><h4>选宠物</h4><div class="chips" id="pets"></div></div>
      <div class="group"><h4>动作</h4>
        <div class="acts">
          <button data-a="demo" id="demoBtn">▶ 自动演示全部<small>待机 → 打招呼 → 摸一摸 → 庆祝 → 招式 → 犯困睡着 → 醒来（约 25 秒）</small></button>
          <button data-a="pet">摸一摸<small>放松地闭上眼、腮红、把头蹭向手、尾巴慢摇</small></button>
          <button data-a="celebrate">庆祝<small>下蹲蓄力 → 轻轻跳起、空中停一下 → 软着陆 → 开心地左右晃，眼睛 ^^</small></button>
          <button data-a="skill" id="skillBtn">招式<small></small></button>
          <button data-a="sleep" id="sleepBtn">睡觉<small>犯困：眼皮慢慢往下掉、撑开一下、再合上 → 睡着</small></button>
        </div>
      </div>
      <p class="tip">鼠标移到宠物身上会打招呼并保持关注，点一下是摸一摸。待机时会自己呼吸、环顾、抖耳朵、摇尾巴、随机眨眼。</p>
    </aside>
  </div>

  <h2 id="list">形象清单</h2>
  <div class="tbl"><table>
    <tr><th>形态</th><th>阶段</th><th>路线</th><th>招式</th><th>文件</th><th>大小</th><th></th></tr>
    {rows}
  </table></div>
  <p class="tip" style="margin-top:8px">每个 .riv 都是独立文件，原画贴图嵌在里面，可以按需只加载当前宠物。</p>

  <h2 id="actions">动作说明</h2>
  <div class="tbl"><table>
    <tr><th>动作</th><th>怎么触发</th><th>时长</th><th>内容</th></tr>
    <tr><td>待机</td><td>默认</td><td>8 秒循环</td><td>呼吸、慢慢环顾、左右耳各抖一次、尾巴正弦摆动、随机单眨 / 连眨</td></tr>
    <tr><td>打招呼 → 关注</td><td><code>hovered = true</code></td><td>1 秒 + 循环</td><td>轻轻挺身、竖耳、歪头；然后保持关注，尾巴慢摇。<code>hovered = false</code> 回到待机</td></tr>
    <tr><td>摸一摸</td><td><code>pet</code> 触发</td><td>3 秒</td><td>放松地闭眼（∪）、腮红、把头蹭向手、耳朵放松、尾巴摇、冒一颗心</td></tr>
    <tr><td>庆祝</td><td><code>celebrate</code> 触发</td><td>2.8 秒</td><td>下蹲蓄力 → 轻轻跳起、在最高处停一下 → 软着陆 → 开心地左右晃，眼睛 ^^（∩）、星星</td></tr>
    <tr><td>犯困 → 睡觉</td><td><code>sleeping = true</code></td><td>2.5 秒 + 循环</td><td>眼皮慢慢往下掉、撑开一下、再合上，头一点一点低下去；睡着后呼吸变慢、耳朵耷拉、Zz</td></tr>
    <tr><td>醒来</td><td><code>sleeping = false</code></td><td>2.6 秒</td><td>半睁眼 → 又眯一下 → 睁开 → 伸懒腰 → 慢慢甩头，回到待机</td></tr>
    <tr><td>招式</td><td><code>skill</code> 触发</td><td>2.5 秒</td><td>只有分化后的 8 个形态有，见上表；眼睛保持睁开，特效避开五官。初生和抽芽期触发了不会有反应</td></tr>
  </table></div>
  <p>一次性动作（摸一摸、庆祝、招式）播完回到待机；如果指针还在宠物上就回到关注。动作进行中重复触发会被合并，不会叠加。睡着时触发摸一摸 / 庆祝不会把它吵醒，需要先把 <code>sleeping</code> 设回 false。</p>

  <h2 id="api">接入方式</h2>
  <ul>
    <li>状态机名 <code>Pet</code>，View Model 名 <code>Pet</code>（默认实例已导出，<code>autoBind</code> 即可）。</li>
    <li>属性：<code>hovered</code>（布尔）、<code>sleeping</code>（布尔）、<code>pet</code> / <code>celebrate</code> / <code>skill</code>（触发器）。和之前 Codex 版的接口名一致，去掉了背景色 / 背景透明度——背景交给 app 的场景。</li>
    <li>画板 500×500，透明背景；所有形态脚底都在 y≈452，换形态时位置不跳。</li>
    <li>文件里没有脚本（只有矢量、网格、骨骼和状态机），网页运行时直接能播，不需要签名构建。已验证 <code>@rive-app/webgl2@2.49.0</code>。</li>
  </ul>
<pre><code>import {{ Rive, Layout, Fit, Alignment }} from "@rive-app/webgl2";

const pet = new Rive({{
  src: "/pets/fox-young.riv",          // 当前宠物的文件
  canvas: document.querySelector("#pet"),
  stateMachine: "Pet",
  autoplay: true,
  autoBind: true,
  layout: new Layout({{ fit: Fit.Contain, alignment: Alignment.BottomCenter }}),
  onLoad: () => pet.resizeDrawingSurfaceToCanvas(),
}});

const vm = () => pet.viewModelInstance;   // onLoad 之后才有
vm().boolean("hovered").value = true;      // 指针移入 / 打开宠物页
vm().trigger("pet").trigger();             // 摸一摸
vm().trigger("celebrate").trigger();       // 完成任务、拿到经验
vm().trigger("skill").trigger();           // 路线招式（分化形态）
vm().boolean("sleeping").value = true;     // 休息；改回 false 自动播放醒来</code></pre>

  <h2 id="rules">设计约定（改动作时请保持）</h2>
  <ul>
    <li><b>精而不是多</b>：动作数量少，每个动作都有预备、主动作、跟随和回弹；节奏放慢到像真的小动物，不做弹球式快速蹦跳。参考宝可梦、洛克王国的宠物待机和互动。</li>
    <li><b>不要“眯眼笑”</b>：下眼皮往上推、还露着瞳孔的眯眼会显得像奸笑。开心用完全闭上的 ^^（∩），放松 / 睡觉用 ∪。</li>
    <li><b>眼皮要像真的眼皮</b>：闭眼时按原画睫毛做的睫毛线往下走，它上面盖上皮肤（颜色取自眼睛上下的毛色，只在这只眼里）；合上后换成闭眼线。两只眼的闭眼线共用脸的角度；幼年形态两只眼闭上后一样大。眼睛闭着或半闭时随机眨眼暂停。</li>
    <li><b>特效避开五官</b>，背景不放进宠物文件；休息不责备用户，回来时温柔招呼。</li>
  </ul>

  <h2 id="edit">怎么修改</h2>
  <p>整只宠物不是手绘矢量，而是<b>原画贴图 + 三角网格 + 骨骼蒙皮</b>：造型和定稿原画完全一致，所有动作靠骨骼完成。工程全部由脚本生成，项目在 <code>manifest-agent/rive/pets/</code>：</p>
  <div class="tbl"><table>
    <tr><th>文件</th><th>作用</th></tr>
    <tr><td><code>gen/prep_art.py</code></td><td>整理原画：去白底、裁边、缩到 720px → <code>art/</code>（源图来自 Codex 的 <code>manifest-pet-gallery-deploy-v2.tar.gz</code>）</td></tr>
    <tr><td><code>gen/rigs.json</code></td><td>每只宠物的骨骼关键点（地面 / 胯 / 脖子 / 头顶）和耳朵、鳃、尾巴的区域，手工标注，坐标是 <code>art/</code> 里的像素</td></tr>
    <tr><td><code>gen/gen_pets.py</code> · <code>gen/eyes.py</code></td><td>生成网格、权重、骨骼、眼皮（量眼睛轮廓、补皮肤、闭眼线）</td></tr>
    <tr><td><code>gen/motion.py</code></td><td>动作设计：状态机、每个动作的关键帧、四个路线招式</td></tr>
    <tr><td><code>gen/render_seq.py</code> · <code>gen/closeup.py</code> · <code>gen/eyealign.py</code></td><td>检查工具：逐帧截图、脸部特写、闭眼和原画对齐</td></tr>
    <tr><td><code>gen/build_handover.py</code></td><td>生成这个交接文件</td></tr>
    <tr><td><code>projects/&lt;宠物&gt;/</code></td><td>生成出来的 Rive 工程（<code>scene.rml</code>，不要手改，会被覆盖）</td></tr>
    <tr><td><code>review/</code></td><td>本地预览页（<code>python -m http.server 8790 --directory review</code>）</td></tr>
  </table></div>
<pre><code># 需要 Rive CLI（rive.app/cli）和 Python（numpy、scipy、pillow、opencv）
python -I gen/gen_pets.py                 # 重新生成全部工程（也可以只写宠物名）
rive projects/fox-young --once            # 构建 .riv
rive projects/fox-young                   # 打开预览窗口，改了自动刷新
python -I gen/build_handover.py           # 重新生成交接文件（先把 .riv 复制到 review/riv/）</code></pre>
  <p>改动作：改 <code>gen/motion.py</code>（帧数按 60fps）。改骨骼或部件范围：改 <code>gen/rigs.json</code>，再用 <code>review</code> 预览检查耳朵、尾巴转动时边缘有没有被拉扯。加新形态：放原画 → 跑 <code>prep_art.py</code> → 在 <code>rigs.json</code> 里标关键点 → 生成。</p>

  <h2 id="known">已知问题 · 下一步</h2>
  <div class="note">
    <ul>
      <li>焰尾狐左眼正好在橙色和米色毛的交界上，闭眼后外眼角有一小块颜色略浅，不仔细看看不出。</li>
      <li>下一步：接入 app（按需加载当前宠物的 .riv）、设计经验值系统、完善宠物功能（含“已分化后想解锁其他形态”的图鉴方案）。</li>
    </ul>
  </div>
</div>

<script>{runtime}</script>
<script>
  const RIV = {json.dumps(riv)};
  const WASM = "{wasm}";
  const PETS = {json.dumps([{k: p.get(k, "") for k in ("id", "name", "stage", "route", "skill", "note")} for p in PETS], ensure_ascii=False)};

  const bytes = (s) => {{ const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }};
  rive.RuntimeLoader.setWasmBinary(bytes(WASM).buffer);
  const cache = {{}};
  const rivBytes = (id) => (cache[id] = cache[id] || bytes(RIV[id]));

  document.querySelectorAll("button.dl").forEach((b) => b.addEventListener("click", () => {{
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([rivBytes(b.dataset.id)], {{ type: "application/octet-stream" }}));
    a.download = b.dataset.id + ".riv"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }}));

  const cv = document.getElementById("cv"), nowEl = document.getElementById("now");
  const sleepBtn = document.getElementById("sleepBtn"), skillBtn = document.getElementById("skillBtn");
  let r = null, vmi = null, cur = null, sleeping = false, demoTimer = null, pending = [];
  const say = (t) => (nowEl.textContent = t);
  const whenReady = (f) => (vmi ? f() : pending.push(f));
  const fire = (n) => whenReady(() => vmi.trigger(n).trigger());
  const setBool = (n, v) => whenReady(() => {{ vmi.boolean(n).value = v; }});

  function setSleep(v) {{
    sleeping = v; setBool("sleeping", v);
    sleepBtn.classList.toggle("on", v);
    sleepBtn.firstChild.textContent = v ? "叫醒" : "睡觉";
    sleepBtn.querySelector("small").textContent = v ? "半睁眼 → 又眯一下 → 睁开 → 伸懒腰 → 慢慢甩头" : "犯困：眼皮慢慢往下掉、撑开一下、再合上 → 睡着";
    say(v ? "犯困 → 睡着" : "醒来");
  }}

  function load(pet) {{
    stopDemo(); cur = pet; sleeping = false;
    document.getElementById("name").textContent = pet.name;
    document.getElementById("tag").textContent = pet.route ? pet.route + " · " + pet.stage : pet.stage;
    document.querySelectorAll("#pets button").forEach((b) => b.classList.toggle("on", b.dataset.id === pet.id));
    skillBtn.disabled = !pet.skill;
    skillBtn.firstChild.textContent = pet.skill ? "招式 · " + pet.skill : "招式（分化后才有）";
    skillBtn.querySelector("small").textContent = pet.note || "初生和抽芽期还没有自己的招式";
    sleepBtn.classList.remove("on"); sleepBtn.firstChild.textContent = "睡觉";
    sleepBtn.querySelector("small").textContent = "犯困：眼皮慢慢往下掉、撑开一下、再合上 → 睡着";
    say("待机");
    if (r) r.cleanup();
    vmi = null; pending = [];
    r = new rive.Rive({{
      buffer: rivBytes(pet.id).slice().buffer, canvas: cv, autoplay: true, stateMachine: "Pet", autoBind: true,
      layout: new rive.Layout({{ fit: rive.Fit.Contain, alignment: rive.Alignment.Center }}),
      onLoad: () => {{ r.resizeDrawingSurfaceToCanvas(); vmi = r.viewModelInstance; const q = pending; pending = []; q.forEach((f) => f()); }},
    }});
  }}

  function stopDemo() {{
    if (demoTimer) {{ demoTimer.forEach(clearTimeout); demoTimer = null; }}
    document.getElementById("demoBtn").classList.remove("on");
  }}

  function demo() {{
    stopDemo(); if (sleeping) setSleep(false);
    document.getElementById("demoBtn").classList.add("on");
    const k = cur.skill ? 3000 : 0;
    const steps = [
      [0, () => say("待机")],
      [3500, () => {{ setBool("hovered", true); say("打招呼 · 关注"); }}],
      [6500, () => {{ setBool("hovered", false); say("摸一摸"); fire("pet"); }}],
      [10300, () => {{ say("庆祝"); fire("celebrate"); }}],
      [13800, () => {{ if (cur.skill) {{ say("招式 · " + cur.skill); fire("skill"); }} }}],
      [13800 + k, () => setSleep(true)],
      [20300 + k, () => setSleep(false)],
      [23500 + k, () => {{ say("待机"); stopDemo(); }}],
    ];
    demoTimer = steps.map(([t, f]) => setTimeout(f, t));
  }}

  const chips = document.getElementById("pets");
  PETS.forEach((p) => {{ const b = document.createElement("button"); b.textContent = p.name; b.dataset.id = p.id; b.onclick = () => load(p); chips.appendChild(b); }});
  document.querySelectorAll("[data-a]").forEach((b) => b.addEventListener("click", () => {{
    const a = b.dataset.a;
    if (a === "demo") return demo();
    stopDemo();
    if (a === "sleep") return setSleep(!sleeping);
    if (sleeping) setSleep(false);
    say({{ pet: "摸一摸", celebrate: "庆祝", skill: "招式 · " + cur.skill }}[a]);
    fire(a);
  }}));
  cv.addEventListener("pointerenter", () => {{ setBool("hovered", true); if (!sleeping && !demoTimer) say("打招呼 · 关注"); }});
  cv.addEventListener("pointerleave", () => {{ setBool("hovered", false); if (!sleeping && !demoTimer) say("待机"); }});
  cv.addEventListener("click", () => {{ if (!sleeping) {{ fire("pet"); say("摸一摸"); }} }});
  window.addEventListener("resize", () => r && r.resizeDrawingSurfaceToCanvas());
  load(PETS[2]);
</script>
</body>
</html>
"""
with open(OUT, "w", encoding="utf8") as f:
    f.write(html)
print(OUT, os.path.getsize(OUT) // 1024, "KB")
