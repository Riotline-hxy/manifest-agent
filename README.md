# 显伴 · 小光（manifest-agent）

显化陪伴 agent 的网页 demo。线上：https://manifest.noryx.cn

- 方案说明（创意 / 技术 / UI，写于 2.6.0；之后加的首页体验、后台、推送见下文）：[docs/三方向方案-v2.md](docs/三方向方案-v2.md)
- 3.0 起，成长系统从「宠物进化 + 徽章」换成了「我的小镇」，见下面的「成长：我的小镇」。宠物和徽章的全部资料备份在仓库外的 `备份区/成长进化系统_宠物与勋章_2026-11-02/`
- v0.3 讨论稿原文：[docs/xiaoguang_v03.txt](docs/xiaoguang_v03.txt) · 会议纪要（10-22）：[docs/meeting.txt](docs/meeting.txt)（[PDF](docs/meeting.pdf)）
- 创意稿（建档题、引导场景、人设一句话）：[creative/](creative/)
- 更早的 demo 和原型已从仓库删除，需要时在 git 历史里找（2026-11-01 之前的提交）

## 本地运行

只需要 Python 3.10+，无第三方依赖。

```bash
cd demo
echo "MODELFLARE_API_KEY=你的key" > .env     # 已在 .gitignore 里
python server.py 8765
```

打开 http://127.0.0.1:8765 ，点「先体验一下」进入两分钟的引导式体验（不建账号）：选一件想改变的事 → 和小光聊几句 → 得到今天的一小步 → 看它记下了什么。注册后这一步和记住的话会带进新账号。

模型配置在 `config/llm.json`（`baseUrl` / `model` / `reasoning`），也可以用环境变量 `MODELFLARE_MODEL` 覆盖。

## 装到手机 · 推送

网站是 PWA：手机浏览器里「添加到主屏幕」就能像 app 一样打开（iPhone 用 Safari，iOS 16.4+；安卓用 Chrome）。
在「我的空间 → 设置 → 手机通知」开启后，小光的主动消息和到点的例行任务，网页关着也会推到手机。

- 推送是空的（不带内容）：手机被叫醒后，`public/sw.js` 用登录 cookie 去 `/api/push/latest` 取那句话再弹出来。所以服务端只需要 VAPID 签名（`core/webpush.py`，纯标准库实现的 ES256），消息原文不经过谷歌 / 苹果的推送服务器。
- VAPID 密钥第一次用时生成在 `data/vapid.json`（随数据备份，别删：换了密钥所有人都要重新开通知）。订阅存在 `data/push.db`。
- 国内很多安卓手机的浏览器收不到网页推送（依赖谷歌推送服务），这部分用户只能打开网页时看到。
- 图标由 `tools/build_icons.py` 画（需要 Pillow，只在开发时用）。

## 管理后台

https://manifest.noryx.cn/admin （本地：http://127.0.0.1:8765/admin）。口令是服务器 `/opt/manifest-agent/.env` 里的 `MANIFEST_ADMIN_KEY`；没设这个变量时后台整个关闭。登录后 12 小时有效，换掉口令所有后台登录立即失效。

能看：用户数与活跃、每天新用户 / 消息 / 模型 tokens、首页体验漏斗、服务器状态、用户列表和单个用户的数量、操作记录与模型用量。看不到对话和记忆原文。
能改：删除单个用户、一次清理所有体验账号（都要手打确认，不能恢复）。

运行计数存在 `data/metrics.db`（只有数字）。每个用户的模型 token 按天记在 `user_counter` 表（分对话 / 后台、含缓存命中），暂不给用户看，商用计费时直接用。

## 测试

```bash
python -m unittest discover -s demo/tests -v
```

用脚本化的假模型跑真服务器，不消耗额度。模型对比：`python demo/bench_models.py`（需要 key，结果写到 `docs/bench-<日期>.json`，不进 git）。

## 成长：我的小镇

每个人一座小镇，现实里做成的事都在这里盖起来。规则全在后端（`core/growth.py`、`core/town.py`），前端和小光只读。

- **经验**：长期成长，只增不减。行动 +10、记录 +6、练习 +12、每天第一次来聊 +8；每类每天 30、总共 120；同一件事只算一次。
- **等级**：升一级要 40 + 15×(n−1) 经验，最多 500（Lv32 起，满额大约三天一级）。老账号按旧算法（每 40 一级）到过的等级记成保底，不会掉。等级解锁新建筑和更大的土地（5×5 → 12×12，Lv32）。
- **金币**：建造用的建材。完成小步 +10、习惯打卡 +8、到达里程碑 +30、好消息 +4、瞬间 +5、做完练习 +10，每类每天有上限；聊天只给经验、不给金币。第一次做成一件真事送 40，够盖第一栋小木屋。
- **每日任务**（小光面板「每日任务」）：每天四件，固定一件行动，另外三件从任务池里按天轮换、只挑这个人用得上的；每件给经验和金币，四件都做到再给一份，一天最多 +38 经验、+68 金币。做了真实的事就自动完成、自动发，每天 0 点换新；偷懒日里行动类先暂停，不挡全勤。和愿望里的小步是两套东西：小步没有期限，不会被刷新。
- **一段小步走完**：一个愿望的小步全部做完时，弹一张卡片：想想新的小步（去和小光聊）/ 之后再说；小光也会在聊到时问一次。
- 数值怎么定的、各类用户一天大概拿多少，见 [docs/成长数值设计.md](docs/成长数值设计.md)。
- **小镇**：商店里 30 样东西（建筑 / 自然 / 道路 / 装饰），有 1×2、2×2 的大建筑，长条的可以转 90°。价格看细节和大小，不跟着等级涨。点一样、再点一块空地就建好；同一次点击带同一个请求号，重发不会扣两次。建筑不会坏、不会因为中断消失，可以挪位置、收进仓库，都不花钱。每栋建筑记下它是哪天建的、那之前做成了什么；到达里程碑送一块刻着名字的纪念碑。
- **老账号**：第一次打开时，过去的经验按一半换成金币（等级保底），小光关于宠物 / 徽章的记忆收起来（`town.ensure`）。旧的 `badge` 表和 `pet_*` 画像原样留在库里，不再读。
- 小镇是手写的等距 SVG（没有图片、引擎和滤镜），深色氛围是夜里（窗户和路灯会亮），浅色氛围是白天。
- **建筑素材库**：`demo/public/js/buildings/<id>.js`，一个文件一样东西，第一行是元数据，下面是画法（画具在 `public/js/townkit.js`）。服务器把这个目录拼成 `/js/buildings/all.js` 一次给前端。新放进来的默认不上架。
- **后台**（`/admin`）：「小镇」页全局改每样东西的价格、解锁等级、上下架（存在 `data/town_config.json`，所有人立刻生效）；用户详情里能看经验和金币的每一笔，能加减经验和金币（要写原因，记在用户的成长账本和 `data/admin_log.jsonl`）。

## 目录

```
demo/
  server.py          HTTP、会话、SSE
  routes.py          接口
  core/
    auth.py          账号与会话（PBKDF2、HttpOnly cookie）
    store.py         每用户一个 SQLite：画像、记忆(FTS5)+修订记录、小步、记录、对话、经验 / 金币账本、小镇、夜间整理
    agent.py         人设、11 个工具、流式工具循环（remember 需要用户明确要求）
    digest.py        夜里的记忆整理（增量、受保护记忆需原话依据）
    growth.py        经验和金币：账本、每日上限、去重、每日任务、升级标记
    town.py          我的小镇：商店、土地、买 / 挪 / 收、建筑的故事、纪念碑、老账号开镇
    academy.py       心灵学堂（只读）
    scenes.py        引导场景的步骤状态机（含「重新认识我」）
    scheduler.py     后台线程：03:00 后整理昨天、主动消息
    report.py        14/30 天蜕变报告
    onboarding.py    建档、示例账号数据（/api/auth/guest，首页已不再使用）
    admin.py         管理后台的只读统计（读用户库只读打开）
    metrics.py       按天的运行计数：请求、对话并发、模型 tokens、体验漏斗
    webpush.py       网页推送：VAPID 签名、订阅、叫醒设备
    trial.py         首页引导式体验（/api/trial/chat，无状态，模型不可用时有写好的回应）
  bench_models.py    模型对比（开发用）
  tests/             接口测试（假模型）
  public/
    index.html       应用；admin.html 管理后台
    manifest.webmanifest · sw.js · icons/   PWA：装到桌面、收推送
    css/             base · components · shell · chat · pages · journey · town · lesson · gate · admin · fonts(生成)
    js/              app · store · api · ui(线性图标) · theme(五种氛围) · town(等距小镇 SVG) · art(星罐) · fx(动效/庆祝)
                     · ball(Emotion Ball 适配) · lesson(「一课」) · scene · tasks(例行任务) · push(通知/安装)
                     · journey · rest · account · admin · views/（gate 首页 · trial 引导体验 · chat · plan · space …）
    fonts/           源流圆体 CN + Nunito 的按需切片（生成）
    vendor/emotion-ball/
config/              llm.json（模型）· llm.env.example
creative/            创意稿
docs/                方案、讨论稿、会议纪要
tools/
  build_fonts.py     重新切字体（需要源字体与 jieba 词频表，见文件头）
  build_icons.py     画 PWA 图标（需要 Pillow）
  shoot.py           本地桌面截图（开发用，依赖仓库外的 Playwright）
deploy/              部署脚本与 systemd 服务（服务文件改了要手动装：见 deploy.sh 文件头）
```

## 数据

运行时数据在 `demo/data/`（服务器上软链到 `/opt/manifest-agent/data`）：`auth.db` 存账号，`u/<user_id>/mind.db` 每人一份。不进 git。

## 形象与素材

- 小光的形象是 Emotion Ball（[sam70361/emotion-ball](https://github.com/sam70361/emotion-ball)）：引擎非商业免费，**球形角色外观永不商用**。本仓库用于竞赛 demo，页面有署名并保留其 LICENSE / NOTICE；商用前需换成自研形象，只改 `public/js/ball.js`。
- 小镇的建筑、树、路和星罐都是代码画的 SVG（`public/js/town.js`、`public/js/art.js`）；位图只有 PWA 图标（`tools/build_icons.py` 画的）。
- 字体：源流圆体 CN（Resource Han Rounded，SIL OFL 1.1）与 Nunito（SIL OFL 1.1）。
