# 每日简报 Agent

每天早上 8:30 自动读取 Obsidian vault 近期内容，通过 Claude API 生成每日简报，写入 vault/Inbox/。

## 数据流

Obsidian vault（Inbox/Clippings/只为记录/我们需要思考/就活）→ Claude Haiku → Inbox/brief-YYYY-MM-DD.md → 可选 Server酱 → 微信

## 扫描范围

| 文件夹 | 回溯天数 |
|--------|---------|
| Inbox | 1天（昨天的快速捕获）|
| Clippings | 7天 |
| 只为记录 | 3天 |
| 我们需要思考 | 7天 |
| 就活 | 7天 |

## 触发

| 时段 | 时间 | LaunchAgent |
|------|------|-------------|
| 每日早晨 | 08:30 JST | `com.daily_brief.morning.plist` |

- stamp 文件：`.stamps/daily_brief`（名称硬编码，`run.sh` 不接 slot 参数）
- 同一天已成功则跳过，失败后 60 秒自动重试一次
- 依赖：`ANTHROPIC_API_KEY`（Claude Haiku 生成简报）；`SERVERCHAN_KEY` 可选（无则仅写 vault，不推微信）

## 输出

- `{vault}/Inbox/brief-YYYY-MM-DD.md`
- 内容：3个联结、1个模式、1个今日问题

## 每周合成（手动）

```bash
cd /Users/jiayi/Developer/ClaudeCode/agents/daily_brief
python3 weekly_synthesis.py
# 回溯更长时间：
python3 weekly_synthesis.py --days 14
```

输出写入 `{vault}/Inbox/synthesis-YYYY-MM-DD.md`
