# 显伴 · 小光（manifest-agent）

显化陪伴 agent 的网页 demo。线上：https://manifest.noryx.cn

- 方案说明（创意 / 技术 / UI，对应线上 2.2.0）：[docs/三方向方案-v2.md](docs/三方向方案-v2.md)
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

打开 http://127.0.0.1:8765 ，点「先体验一下」会建一个带 12 天示例数据的独立体验账号。

模型配置在 `config/llm.json`（`baseUrl` / `model` / `reasoning`），也可以用环境变量 `MODELFLARE_MODEL` 覆盖。

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
    onboarding.py    建档、体验账号示例数据
  public/
    index.html
    css/             base · components · shell · chat · pages · lesson · gate · fonts(生成)
    js/              app · store · api · ui(线性图标) · theme(五种氛围) · pet(扁平 SVG 宠物/植物) · fx(动效/庆祝)
                     · ball(Emotion Ball 适配) · lesson(「一课」) · scene · views/
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
