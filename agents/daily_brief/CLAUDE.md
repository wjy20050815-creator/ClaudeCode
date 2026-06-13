# 每日简报 Agent

每天早上 8:30 自动读取 Obsidian vault 近期内容，通过 Groq LLaMA 生成每日简报，写入 vault 的 `每日思维启发简报/`，并附当日日历日程。

## 数据流

macOS 日历（osascript，当日事件）+ Obsidian vault（Clippings/只为记录/我们需要思考/就活/投资/CS自学/ゼミ发表/调酒/爱好）→ Groq LLaMA → `每日思维启发简报/brief-YYYY-MM-DD.md` → 可选 Server酱 → 微信

> vault 路径经 `vault.paths.env` 注册表解析（`VAULT_BRIEF_DIR`），不硬编码。

## 扫描范围

`daily_brief.py` 的 `SCAN_FOLDERS` 定义（文件夹、回溯天数、字符上限），修改扫描范围编辑该常量。

## 日历段

- `fetch_today_events()` 用 osascript 查 Calendar.app 当日事件（跳过 生日/Siri建议/计划的提醒事项），约 20–30 秒
- **失败不阻塞**：拿不到日历则简报无「📅 今日日程」段，错误写入日志
- 首次在新权限环境（如 launchd 换了 responsible process）运行会触发 macOS 日历授权弹窗，需手动允许一次；若推送里持续缺日程段，去 系统设置 → 隐私与安全性 → 日历 检查

## 触发

| 时段 | 时间 | LaunchAgent |
|------|------|-------------|
| 每日早晨 | 08:30 JST | `com.daily_brief.morning.plist` |

- stamp 文件：`.stamps/daily_brief`（名称硬编码，`run.sh` 不接 slot 参数）
- 同一天已成功则跳过，失败后 60 秒自动重试一次
- 依赖：`GROQ_API_KEY`（必须）；`SERVERCHAN_KEY` 可选（无则仅写 vault，不推微信）。`run.sh` 经 `tools/load_env.sh` 只注入这两个 key

## vault 治理职责

`run.sh` 末尾（无论简报成败）调用 `tools/vault_index_sync.py --fix --reason daily_brief`，每日对账 vault 的 `index.md`/`log.md` 与实际文件——这是整个 vault hot cache 的每日 cadence，兜住所有写入者（含手动编辑）的漂移。

## 输出

- `{VAULT_BRIEF_DIR}/brief-YYYY-MM-DD.md`
- 内容：今日日程（如有）、3个联结、1个模式、1个今日问题

## 每周合成（手动）

```bash
cd <repo>/agents/daily_brief
python3 weekly_synthesis.py
# 回溯更长时间：
python3 weekly_synthesis.py --days 14
```

输出写入 `{vault}/Inbox/synthesis-YYYY-MM-DD.md`
