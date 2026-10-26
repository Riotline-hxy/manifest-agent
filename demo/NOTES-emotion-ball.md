# Emotion Ball 接入说明（显伴 · 小光 demo）

## 仓库与出处

- 仓库：https://github.com/sam70361/emotion-ball
- 本地路径：`demo/vendor/emotion-ball/`（浅克隆，已去掉 `.git`）
- 在线预览（上游）：https://emotion-balls.vercel.app/

## 竞赛 Demo 策略（2026-10-26 起）

**竞赛 / 非商用 demo：直接展示上游可见球（blob）+ 动作。**  
商用产品是否继续用球视觉另议（上游球身体视觉永不提供商业授权）。

| 层 | 用法 |
| --- | --- |
| (A) 表情引擎 + 配置 | `setEmotion` / `spin` / `bounce`；非商业免费，商用需另授权 |
| (B) 球形角色视觉 | **本竞赛 demo 展示** blob + `#6b4eff`；**商用禁止**，上线前须换成自研形象 |

Attribution：页面脚注与本 NOTES；分发须保留上游 `LICENSE`、`NOTICE.md`。

## 实际用到的文件

```
vendor/emotion-ball/emotion-ball/js/rings.js
vendor/emotion-ball/emotion-ball/js/emotions.js
vendor/emotion-ball/emotion-ball/js/ball.js
vendor/emotion-ball/emotion-ball/js/engine.js
```

页面引用（相对 `demo/index.html`）：

```html
<script src="vendor/emotion-ball/emotion-ball/js/rings.js"></script>
<script src="vendor/emotion-ball/emotion-ball/js/emotions.js"></script>
<script src="vendor/emotion-ball/emotion-ball/js/ball.js"></script>
<script src="vendor/emotion-ball/emotion-ball/js/engine.js"></script>
```

可见宿主：`#xgAvatar`（顶栏 44px）。`EmotionBall.create(#xgAvatar, { shape:'blob', color:'#6b4eff', lite:false })`。  
气泡旁用同色 CSS orb（`.orb-mini`），避免每条消息建引擎实例。失败时 `console.warn` 并回退 CSS orb。

## emotionId 映射表

| 产品状态 `data-state` | emotionId | 上游名称 | 触发时机（demo） |
| --- | --- | --- | --- |
| `idle` | `02` | 待机放空 | 回复结束 / 批准后 |
| `thinking` | `30` | 思考中 | 发送后；并 `spin(1)` |
| `streaming` | `39` | 输出回复 | 首 token；并 `bounce()` |
| `awaiting_you` | `35` | 等待输入 | 待确认 / 主动问候 |

## 验证方式

```bash
cd /workspace/agent-product/demo
python3 server.py   # 8765
# http://127.0.0.1:8765/
```

1. 顶栏是**紫色 Emotion Ball blob**（非胶囊 SVG）。  
2. `#xgAvatar` 有 `data-emotion-engine="emotion-ball"`。  
3. 发消息：thinking→30+spin，streaming→39，结束→02。  
4. 主动问候 → emotion 35。

## 布局（同轮）

≥1180：左画像+计划 / 中对话 / 右灵感+蜕变。  
≤760：底栏五签切列。已去掉 `max-width:430px` 手机框。


## 壳 v0.2（2026-10-26）
- 左轨 72px 五入口；主舞台整页切换；顶栏球 72px。
- 页脚：「Emotion Ball · 仅学习演示」。
- 晋升：`profile.incentive` + `POST /api/demo/promote`；完成微步 `POST /api/plan action=complete`。
