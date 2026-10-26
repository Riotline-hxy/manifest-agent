# 创意 · Onboarding 题库 + 灵感场景脚本 v0.1
对齐技术字段锁定（snake_case）。日期：2026-10-25

## A. Onboarding 题库（8 题 → user_profile）

规则：全答完才写 profile；每题 ≤15 秒可答；可跳过标 optional 的题。

| # | 题干 | 选项/输入 | 写入字段 |
|---|---|---|---|
| 1 | 先给你的伙伴起个名字？ | 自由输入，默认「小光」 | agent_name |
| 2 | 选一个头像气质 | 柔光 / 星尘 / 水墨 / 几何（映射 avatar_id） | agent_avatar_id |
| 3 | 你这阵子最想靠近的是？ | 自信与表达 / 健康作息 / 学业或作品 / 关系与边界 / 自定义一句 | intent_primary（自定义→原文） |
| 4 | 为什么这件事对你重要？（一句话） | 短文本 | 同步写入 intent.why；intent.title 由 intent_primary 生成 |
| 5 | 你更像哪种节奏？ | 早起型 / 夜猫 / 不固定 | schedule_hint |
| 6 | 别人常觉得你是？（最多选 3） | 敏感 / 理性 / 行动派 / 拖延但爆发 / 需要被提醒 / 喜欢独处 | traits[] |
| 7 | （可选）有没有想对号入座的类型标签？ | 跳过 / 填 MBTI 或「不确定」 | mbti_hint? |
| 8 | 有什么绝对别碰？（边界） | 多选：别说教 / 别鸡血催促 / 别提某话题（自定义）/ 无 | boundaries[] |

验收：≤3 分钟；完成后画像页可见 agent_name、intent_primary、traits、boundaries。

## B. 灵感场景脚本（4 张）

结束后服务端须落 ≥1 条 memory_entry 或 plan_step。

### 1. clarify · 说清想要的
- title: 说清想要的
- script_steps:
  1. 「用一句话说你想要的生活片段（不是职位名）。」
  2. 「去掉『应该』之后，哪半句是真的？」
  3. 「如果已经实现了，明天早上你会先做什么？」
- writes_to: plan
- 结束动作：生成 1 条 plan_step（title=明天那一小步，status=todo）；另写 memory_entry kind=insight

### 2. gratitude · 三分钟感恩
- title: 三分钟感恩
- script_steps:
  1. 「今天已经发生的、哪怕很小的一件好事？」
  2. 「再来一件：跟人有关的。」
  3. 「再来一件：跟自己有关的。」
- writes_to: memory
- 结束动作：3 条合并或 1 条 memory_entry kind=good_news（text 含三点）

### 3. meditation · 短冥想引导
- title: 短冥想引导
- script_steps:
  1. 「找个舒服姿势。跟着呼吸数 4 拍吸、4 拍呼，共 6 轮。」（MVP 纯文字倒计时）
  2. 「想象意图已实现时，身体哪里最先放松？」
  3. 「用一个词记下这种感觉。」
- writes_to: memory
- 结束动作：memory_entry kind=insight（感觉词）；语音后补

### 4. seven_steps_lite · 七步轻走一遍
- title: 七步轻走一遍
- script_steps:
  1. 澄清：重述当前 intent_primary
  2. 信念：补一句「我配得上，因为…」
  3. 感受：选情绪标签（平静/兴奋/坚定/温柔）
  4. 行动：定今日 1 步
  5. 感恩：一句已有
  6. 释放：写下可放下的执念（不评判）
  7. 见证：选「允许自己慢一点」打勾
- writes_to: plan
- 结束动作：1× plan_step + 1× memory_entry kind=insight（信念句）

## C. 主动问候文案位（proactive_cue）
- idle_hours=24；静默 23:00–08:00
- topic_from=intent 优先：「还在靠近「{intent.title}」吗？今天只要动一小步就够。」
- topic_from=memory 若有 lazy_day：「昨天慢了也没关系。要不要从灵感区抽一张卡？」

## D. 蜕变报告惊喜位（占位规则）
surprise_line 生成规则（MVP 可模板）：
- 若 good_news ≥3：点出最高频主题词
- 若 lazy_day ≥1 且 done 步数仍涨：写「慢下来的日子里你其实完成了 X」
- 否则：引用用户第一天 why 与第 N 天 plan 标题的反差一句
