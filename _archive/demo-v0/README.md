# 显伴 · 小光 — 产品 Demo

单文件网页 MVP。产品名 **显伴**，Agent **小光**。对话经本机代理走 ModelFlare 真流式（密钥只在环境变量）。

## 启动（推荐）

```bash
cd /workspace/agent-product/demo
# 密钥勿写进文件；从环境读
export MODELFLARE_API_KEY='你的密钥'
python3 server.py          # 默认 8765
# 或指定端口：
# python3 server.py 8787
```

浏览器打开：http://127.0.0.1:8765/  
跨用户调试可加 `?user_id=alice`（只允许 `[a-zA-Z0-9_-]`）。

- 静态页：`GET /`
- 对话代理：`POST /api/chat`（SSE 流式；服务端读 `MODELFLARE_API_KEY`，并注入记忆摘要）
- 配置：`../config/llm.json`（baseUrl / model / reasoning；不含密钥）

无密钥时仍可打开页面；发消息会回退到本地假气泡。

## 仅看静态（无真对话 / 无记忆 API）

```bash
python3 -m http.server 8765 --directory /workspace/agent-product/demo
```

## 布局

- **≥1180**：muse_web 三栏——左画像+计划 · 中对话 · 右灵感四卡+蜕变入口（无 430px 手机框）
- **≤760**：单栏 + 底栏五签
- 主形象：顶栏 Emotion Ball 可见球；气泡旁同色 orb

## 五区

| Tab | 演示 |
|-----|------|
| **对话** | ModelFlare 流式；状态条；「模拟主动」/「强制演示」；晚间签到审批；3 题建档写 profile |
| **画像** | 从 `/api/memory` 加载意图/价值观/记忆；「忘记」真删 |
| **计划** | 进度环 + 落盘的 `plan_step` 列表 |
| **灵感** | 2×2 四卡；走完强制写 `memory_entry` + `plan_step` |
| **蜕变** | 惊喜洞察 + **9:16 分享卡**（预览/复制文案/下载 PNG，不上云） |

## 记忆 v0.1（按用户隔离）

路径：`demo/data/users/{user_id}/`

| 文件 | 说明 |
|------|------|
| `user_profile.json` | 称呼、intent_primary、boundaries、values… |
| `memory_entry.jsonl` | 一行一条记忆（kind: insight/good_news/lazy_day…） |
| `plan_step.jsonl` | 今日微步 |

示例骨架在 `data/users/_example/`；运行时 `users/*` 已 gitignore（保留 `_example`）。

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memory?user_id=demo` | 读 profile + memories |
| POST | `/api/memory` | 合并写 profile；可附 `memory` / `plan` |
| DELETE | `/api/memory/{id}?user_id=demo` | 真删 jsonl 对应行 |
| GET/POST | `/api/plan?user_id=demo` | 读/追加 plan_step |

Chat 注入规则：system 硬带 `agent_name`、`intent_primary`、`boundaries`；再附近 Top-k≤5 条 memory（优先 insight/good_news；lazy_day 可进但不作鸡血催促）。无命中不编造。

空列表文案：**小光还没记住什么**。

### 冒烟

```bash
# 读
curl -s 'http://127.0.0.1:8765/api/memory?user_id=demo' | head
# 写一条
curl -s -X POST 'http://127.0.0.1:8765/api/memory' \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo","memory":{"kind":"insight","text":"冒烟测试条目"}}'
# 跨用户应读不到 demo 的条
curl -s 'http://127.0.0.1:8765/api/memory?user_id=other' | head
```

## 主动问候 v0.1

规则（产品钉死）：

| 条件 | 说明 |
|------|------|
| 空闲 | `last_chat_at` 距今 ≥ **24h** 才推（从未聊过视为可推） |
| 静默窗 | **23:00–08:00**（Asia/Shanghai）不推 |
| 开关 | `user_profile.proactive_enabled`（默认 true；可关） |
| 选题 | 优先 `intent_primary`，否则 insight/good_news；**禁 lazy 催促** |
| 文案 | 近 **72h** 有 `lazy_day` →「慢下来也没关系，要不要抽一张灵感卡？」；否则 →「还在靠近「{intent}」吗？今天一小步就够。」 |
| Emotion | 统一 **35**（`awaiting_you`） |
| 展示 | 气泡 +「主动陪伴」tag |

`模拟主动` 与真推送走**同一模板选择器**；不满足条件时 toast 说明原因。`强制演示` 跳过 idle/静默（评审用）。无真 cron（演示按钮即可）。

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/proactive?user_id=demo` | 只读：是否该推 + 文案草稿 |
| GET | `/api/proactive?force=1&simulate_hour=14` | 强制 / 模拟小时（测静默窗） |
| POST | `/api/proactive` | 检查并通过则写 `last_proactive_at`、回文案 |
| POST | `/api/activity` | 前端发消息时刷新 `last_chat_at` |

profile 字段：`last_chat_at`、`last_proactive_at`、`proactive_enabled`。

### 演示怎么点

1. 开 `python3 server.py`，打开 http://127.0.0.1:8765/
2. 顶栏 **主动问候** 开关默认开；关掉后模拟/强制按钮灰掉并写回 profile
3. 点 **模拟主动**：若在静默窗或未满 24h → toast 说明原因，不出气泡
4. 点 **强制演示** → 必出带「主动陪伴」tag 的气泡，emotion→35（开关关闭时不可点）
5. 发一条聊天后，`last_chat_at` 刷新；再点模拟主动应提示未满 24h

### 冒烟（curl）

```bash
# 当前若在静默窗或刚聊过 → should_push=false
curl -s 'http://127.0.0.1:8765/api/proactive?user_id=demo' | python3 -m json.tool

# 模拟白天但仍未满 24h（先 touch 一次）
curl -s -X POST 'http://127.0.0.1:8765/api/activity' -H 'Content-Type: application/json' \
  -d '{"user_id":"demo"}'
curl -s 'http://127.0.0.1:8765/api/proactive?user_id=demo&simulate_hour=14'

# 强制演示 → delivered
curl -s -X POST 'http://127.0.0.1:8765/api/proactive' -H 'Content-Type: application/json' \
  -d '{"user_id":"demo","force":true}'
```


## 蜕变分享卡 v0.1

点法：

1. 开 `python3 server.py` → http://127.0.0.1:8765/
2. 底栏进 **蜕变** → 点 **生成分享卡片（演示）**
3. 弹出 9:16（1080×1920）预览卡：球头像 + N 天蜕变 / 前后意图 / 高光 / 偷懒诚实账 / surprise 紫卡
4. **复制文案** → 剪贴板 + toast；**下载 PNG** → 本机文件（html2canvas，不上云）

文案优先级（`surprise_line`）：① `good_news`≥3 → 点主题；② 有 `lazy_day` 仍有微步 →「慢的日子也走了 X 步」；③ 否则 day1 why × dayN 计划反差。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/share?user_id=demo` | 返回卡字段 + `share_text`（非空可冒烟） |

### 冒烟

```bash
curl -s 'http://127.0.0.1:8765/api/share?user_id=demo' | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('share_text'); print('OK', d['surprise_rule'], len(d['share_text']), 'chars')"
```

## 主动问候开关

顶栏 **主动问候** 小开关（默认开）。关掉后「模拟主动 / 强制演示」灰掉，并 `POST /api/memory` 写回 `profile.proactive_enabled=false`。force 不再跳过开关。

## Emotion 钩子（技术钉死）

| 时机 | emotion_id | 说明 |
|------|------------|------|
| 请求发出 | `30` | 前端 `setAvatarState("thinking")` |
| 首 token | `39` | SSE `event: emotion`（仅状态变时推） |
| 流结束 | `02` | SSE `event: emotion` |
| 审批 chip | `35` | `awaiting_you` |

外形为 **Emotion Ball 可见 blob 球**（`#6b4eff`）；竞赛 demo 用球视觉+动作，商用另议（见 NOTES-emotion-ball.md）。

## 人设（system）

小光是你的显化陪伴——只帮你把「想成为的人」收成今天能走的一小步，不做万能助理。

## 局限

无登录 / 真 cron（主动靠按钮演示）；分享卡本机 html2canvas 导出 PNG，不上云。密钥禁止写进 HTML/JS/仓库明文。
