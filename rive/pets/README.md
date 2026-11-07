# 小芽宠物 · Rive 动效

10 个形态（初生小芽、抽芽期小芽，以及四条分化路线的幼体和成年体）共用一套动作，分化后的形态各多一个路线招式。

## 做法

直接用原画做贴图：每只宠物的原画铺一层三角网格，蒙皮到骨骼（地面 / 身体 / 头 / 耳朵或鳃 / 尾巴），动作全部靠骨骼完成，所以造型和定稿的原画完全一致。眨眼和闭眼用「眼皮贴片」（把眼睛位置补成周围毛色的小图）盖住眼睛，闭眼线、腮红、爱心、星星、Zz 和招式特效都是矢量。

```
gen/prep_art.py    原画整理：去白底、裁边、缩到 720px → art/
gen/rigs.json      每只宠物的骨骼关键点和部件区域（手工标注，坐标是 art/ 里的像素）
gen/gen_pets.py    生成 Rive 工程：网格、权重、骨骼、眼皮 → projects/<pet>/
gen/motion.py      动作设计：状态机、每个动作的关键帧、路线招式
gen/eyes.py        量眼睛轮廓、算眼皮和闭眼线
gen/render_seq.py  逐帧截图检查（closeup.py 脸部特写，eyealign.py 闭眼和原画对齐）
gen/build_handover.py  生成交接用的单文件网页 xiaoya-pets-handover.html
gen/export_site.py     发布到网站：.riv、Rive 运行时、静态图 → demo/public/pets、demo/public/vendor/rive
review/index.html  本地预览页（用官方 Rive 网页运行时播放 review/riv/*.riv）
```

改动作改 `gen/motion.py`，改骨骼改 `gen/rigs.json`，然后：

```bash
python -I gen/gen_pets.py            # 重新生成全部（或在后面写宠物名）
rive projects/fox-young --once       # 构建 .riv → projects/fox-young/build/fox-young.riv
```

`projects-preview/` 是同一场景加了浅色背景的版本，只用来截图和做 GIF，不进 app。

## 动作

| 动作 | 怎么触发 | 时长 | 内容 |
|---|---|---|---|
| 待机 | 默认 | 8 秒循环 | 呼吸、慢慢环顾、左右耳各抖一次、尾巴正弦摆动、随机单眨 / 连眨 |
| 打招呼 → 关注 | `hovered = true` | 1 秒 + 循环 | 轻轻挺身、竖耳、歪头，然后保持关注、尾巴慢摇 |
| 摸一摸 | `pet` 触发 | 3 秒 | 放松地闭眼（∪）、腮红、把头蹭向手、耳朵放松、尾巴摇、冒一颗心 |
| 庆祝 | `celebrate` 触发 | 2.8 秒 | 下蹲蓄力 → 轻轻跳起、空中停一下 → 软着陆 → 开心地左右晃，眼睛 ^^（∩） |
| 犯困 → 睡觉 | `sleeping = true` | 2.5 秒 + 循环 | 眼皮慢慢往下掉、撑开一下、再合上，头一点一点低下去；睡着后呼吸变慢、Zz |
| 醒来 | `sleeping = false` | 2.6 秒 | 半睁眼 → 又眯一下 → 睁开 → 伸懒腰 → 慢慢甩头 |
| 招式 | `skill` 触发（只有分化形态） | 2.5 秒 | 余温（狐）/ 留芳（鹿）/ 回澜（水灵）/ 连星（星灵），眼睛保持睁开，特效避开五官 |

一次性动作播完会回到待机（如果指针还在宠物上，就回到关注）。动作进行中重复触发会被合并，不会叠加。

### 眼皮怎么做的

每只眼的轮廓都从原画里量出来（`gen/eyes.py`）。闭眼时，按原画上睫毛做的“睫毛线”往下走、慢慢压扁，
它上面的部分盖上皮肤（补成周围毛色、裁剪成只在这只眼里）；合上后换成一条顺着眼睛倾斜的闭眼线：
∪ 是放松（摸一摸、睡觉），∩ 是开心（庆祝）。眼睛闭着或半闭时，随机眨眼会暂停。

## 接入 app（下一轮）

- 每只宠物一个 `.riv`（360–540 KB，原画贴图嵌在里面），状态机 `Pet`，view model `Pet`。
- 接口：`hovered`（布尔）、`sleeping`（布尔）、`pet` / `celebrate` / `skill`（触发器），和旧版接口一致，去掉了旧版的背景色、背景透明度（背景交给 app 的场景）。
- 画板 500×500、透明背景，角色脚底在 y≈452，换形态时位置不跳。
- 网页用 `@rive-app/webgl2`（已验证 2.49.0 能播放、数据绑定正常），`autoBind: true` 后通过 `rive.viewModelInstance` 设置。

## 验收

```bash
python -m http.server 8790 --directory review
```

打开 http://localhost:8790 ：选宠物，鼠标移到宠物上打招呼，点一下摸一摸，按钮触发庆祝、招式、睡觉 / 叫醒。

交接给别人直接发 `xiaoya-pets-handover.html`：一个文件里包含全部动画、运行时和每只宠物的 .riv（可下载），双击就能打开，不需要服务器。
