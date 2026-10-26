# 显伴 · 小光（manifest-agent）

显化陪伴 agent 的网页 demo。线上：https://manifest.noryx.cn

- 方案说明 v2（创意 / 技术 / UI，对应线上 2.0.0）：[docs/三方向方案-v2.md](docs/三方向方案-v2.md)
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
    store.py         每用户一个 SQLite：画像、记忆(FTS5)、小步、记录、对话、活动
    agent.py         人设、工具、流式工具循环
    memory.py        记忆写入管线（ADD/UPDATE/DELETE，推测待确认）
    scenes.py        灵感四场景的步骤状态机
    scheduler.py     主动消息定时任务
    report.py        蜕变报告与惊喜句
    onboarding.py    8 题建档、体验账号示例数据
  public/
    index.html
    css/             tokens / shell / components / chat / pages
    js/              api, store, ui, orb, app + views/（12 个 ES 模块）
    assets/pets/     宠物九形态 + 报告封面（gpt-image-2 生成，WebP）
tools/gen_pets.py    重新生成宠物素材
  tests/
deploy/              systemd 与部署脚本
```

## 数据

运行时数据在 `demo/data/`（服务器上软链到 `/opt/manifest-agent/data`）：`auth.db` 存账号，`u/<user_id>/mind.db` 每人一份。不进 git。

## 形象与素材

- 聊天中的小光是一枚自绘 SVG 光球（`public/js/orb.js`），原创、无第三方授权限制。
- 宠物素材由 `tools/gen_pets.py` 调用 `gpt-image-2` 生成（需要 `OPENLUX_API_KEY`），统一风格提示词后压缩为 WebP。
- `public/vendor/emotion-ball` 是上一版遗留素材，当前页面已不再引用；如确认不再使用，可以整目录删除。
