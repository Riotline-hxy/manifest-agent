# 显伴 · 小光（manifest-agent）

显化陪伴 agent 的网页 demo。线上：https://manifest.noryx.cn

- 方案说明（创意 / 技术 / UI，对应线上 2.6.0）：[docs/三方向方案-v2.md](docs/三方向方案-v2.md)
- v0.3 讨论稿原文：[docs/xiaoguang_v03.txt](docs/xiaoguang_v03.txt) · 旧方案：[docs/三方向方案.md](docs/三方向方案.md)
- 会议纪要：[meeting.txt](meeting.txt) · 创意稿：[creative/](creative/)
- 旧版 demo 归档：[_archive/demo-v0/](_archive/demo-v0/)

## 本地运行

只需要 Python 3.10+，无第三方依赖。

```bash
cd demo
echo "MODELFLARE_API_KEY=你的key" > .env     # 已在 .gitignore 里
python server.py 8765
```

打开 http://127.0.0.1:8765 ，点「先体验一下」进入两分钟的引导式体验（不建账号）：选一件想改变的事 → 和小光聊几句 → 得到今天的一小步 → 看它记下了什么。注册后这一步和记住的话会带进新账号。

模型配置在 `config/llm.json`（`baseUrl` / `model` / `reasoning`），也可以用环境变量 `MODELFLARE_MODEL` 覆盖。

## 管理后台

https://manifest.noryx.cn/admin （本地：http://127.0.0.1:8765/admin）。口令是服务器 `/opt/manifest-agent/.env` 里的 `MANIFEST_ADMIN_KEY`；没设这个变量时后台整个关闭。登录后 12 小时有效，换掉口令所有后台登录立即失效。

能看：用户数与活跃、每天新用户 / 消息 / 模型 tokens、首页体验漏斗、服务器状态、用户列表和单个用户的数量、操作记录与模型用量。看不到对话和记忆原文。
能改：删除单个用户、一次清理所有体验账号（都要手打确认，不能恢复）。

运行计数存在 `data/metrics.db`（只有数字）。每个用户的模型 token 按天记在 `user_counter` 表（分对话 / 后台、含缓存命中），暂不给用户看，商用计费时直接用。

## 测试

```bash
python -m unittest discover -s demo/tests -v
```

用脚本化的假模型跑真服务器，不消耗额度。模型对比：`python demo/bench_models.py`（需要 key）。

## 目录

```
demo/
  server.py          HTTP、会话、SSE
  routes.py          接口
  core/
    auth.py          账号与会话（PBKDF2、HttpOnly cookie）
    store.py         每用户一个 SQLite：画像、记忆(FTS5)+修订记录、小步、记录、对话、经验账本、徽章、夜间整理
    agent.py         人设、11 个工具、流式工具循环（remember 需要用户明确要求）
    digest.py        夜里的记忆整理（增量、受保护记忆需原话依据）
    growth.py        经验账本、每日上限、宠物分化、27 枚徽章、今日任务
    academy.py       心灵学堂（只读）
    scenes.py        引导场景的步骤状态机（含「重新认识我」）
    scheduler.py     后台线程：03:00 后整理昨天、主动消息
    report.py        14/30 天蜕变报告
    onboarding.py    建档、示例账号数据（/api/auth/guest，首页已不再使用）
    admin.py         管理后台的只读统计（读用户库只读打开）
    metrics.py       按天的运行计数：请求、对话并发、模型 tokens、体验漏斗
    trial.py         首页引导式体验（/api/trial/chat，无状态，模型不可用时有写好的回应）
  public/
    index.html
    css/             base · components · shell · chat · pages · lesson · gate · fonts(生成)
    js/              app · store · api · ui(线性图标) · theme(五种氛围) · pet(扁平 SVG 宠物/植物) · fx(动效/庆祝)
                     · ball(Emotion Ball 适配) · lesson(「一课」) · scene · views/（gate 首页 · trial 引导体验 · …）
    fonts/           源流圆体 CN + Nunito 的按需切片（生成）
    vendor/emotion-ball/
tools/
  build_fonts.py     重新切字体（需要源字体与 jieba 词频表，见文件头）
  shoot.py           本地桌面截图（开发用，依赖仓库外的 Playwright）
deploy/              systemd 与部署脚本
```

## 数据

运行时数据在 `demo/data/`（服务器上软链到 `/opt/manifest-agent/data`）：`auth.db` 存账号，`u/<user_id>/mind.db` 每人一份。不进 git。

## 形象与素材

- 小光的形象是 Emotion Ball（[sam70361/emotion-ball](https://github.com/sam70361/emotion-ball)）：引擎非商业免费，**球形角色外观永不商用**。本仓库用于竞赛 demo，页面有署名并保留其 LICENSE / NOTICE；商用前需换成自研形象，只改 `public/js/ball.js`。
- 宠物、植物、宝箱、星罐是代码画的扁平 SVG（`public/js/pet.js`），和小光同一种造型语言；全站没有位图素材。
- 字体：源流圆体 CN（Resource Han Rounded，SIL OFL 1.1）与 Nunito（SIL OFL 1.1）。
