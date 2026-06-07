# 财经新闻播报 Agent

定时抓取财经新闻，经 AI 整理后推送到微信。

## 数据流

NewsAPI（英文）→ Groq LLaMA → Server酱 → 微信

## 定时任务

- 每天 09:10（morning2）/ 16:30（afternoon）/ 23:30（night）JST 各推送一次
- 由 launchd 调用 `run.sh <slot>`，日志写入 `agents/financial_news/financial_news.log`
- 成功后写入 `<repo>/.stamps/<slot>` 文件（日期）；catchup.sh 在开机/登录时补跑漏掉的时段
- `--as-of` 参数用于手动补跑，补跑时 stamp 由 `run.sh` 正常写入
- 强制重跑：`rm .stamps/<slot>` 然后 `agents/financial_news/run.sh <slot>`

## 关键参数

- 抓取窗口：36 小时（NewsAPI 免费版约有 24 小时延迟）
- 最多输出：10 条，按重要性排序

## 行为规范

- 新闻筛选标准在 `SYSTEM_PROMPT` 中定义，修改筛选逻辑应编辑该变量
- **不推送重复新闻**：同一事件/文章不应在多次推送中重复出现；如修改去重逻辑，应在此记录方案
- 股价行情部分独立于新闻，每次必推
- **catalyst-calendar 段**：股价之后追加未来 7 天 WATCHLIST 个股的财报日期（数据源 yfinance `.calendar`，仅对 jp/us 个股，跳过指数/汇率/期货/sina）；无事件时该段不输出，不影响其他段落
- 补跑（`--as-of`）时标题加"（补）"后缀
