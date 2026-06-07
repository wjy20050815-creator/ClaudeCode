# 华尔街 AI 投资观点播报 Agent

定时抓取各大投行/独立研究机构【官方公开栏目】中与 AI 投资相关的文章，
抓取原文全文后经 Claude 主题深读（中英混合）推送到微信。

## 数据流

```
Google News site定向 RSS（官方域名，发现）
  → batchexecute 解码出原文真实 URL
  → Jina Reader（r.jina.ai）抓正文全文 → extract_body 剥离免责声明/导航
  → Claude（claude-sonnet-4-6）主题深读：论据→机制→分歧→启示
  → Server酱 → 微信
```

## 全文抓取链（关键，易碎需关注）

- **解码** `decode_google_news_url`：Google News 的 `<link>` 是 JS 跳转，HTTP 解析不出原文。用 `news.google.com/_/DotsSplashUi/data/batchexecute` 接口解码出真实 URL。Google 偶尔改接口，若大面积解码失败先查这里。
- **抓正文** `fetch_fulltext`：用 `https://r.jina.ai/<真实URL>` 取干净 markdown。注意 Jina 封禁 news.google.com，**必须先解码再抓**，不能直接喂 Google 链接。匿名档有速率限制，故逐篇 `sleep(1.5)`。
- **剥正文** `extract_body`：很多官方页（尤其 JPM Asset Management）正文前有大段「机构投资者免责声明墙」。靠「归一化标题锚点取最后一次出现」定位正文起点；标题比对必须两边都归一化（去标点），否则冒号会导致锚点失配、误把免责声明当正文。
- 任一环节失败则回退到 RSS 摘要（仍纳入该篇，但深度受限）。

## 数据源设计

- 抓取走 Google News RSS 的 `site:<官方域名>` 限定符，**只返回官方域名内的文章**，不含媒体二手报道与付费墙研报。
- 机构清单在 `wallstreet_ai.py` 的 `INSTITUTIONS`（顶级投行全覆盖 + 独立研究机构）。
- **独立研究机构（Wedbush / Bernstein）很少有公开栏目**，site定向下覆盖可能稀疏甚至为空——这是「只要官方栏目」决策的预期结果，不是 bug。若需纳入 Dan Ives 等的媒体引用观点，去掉对应机构的 `site:` 限定即可（会引入二手报道）。
- AI 相关性二次过滤：`AI_TOKENS` 关键词 + `NAV_STOPWORDS` 停用词（剔除 Careers/Home 等导航页）。

## 定时任务

- 每周一、周五 08:00 JST 各推送一次
- launchd 用 `StartCalendarInterval` 的 `Weekday`（1=周一，5=周五）
- 由 launchd 调用 `run.sh <slot>`（slot = `monday` / `friday`），日志写入 `wallstreet_ai.log`
- 成功后写入 `<repo>/.stamps/wallstreet_<slot>` 文件（日期）
- 强制重跑：`rm .stamps/wallstreet_monday` 然后 `agents/wallstreet_ai/run.sh monday`

## 关键参数

- 抓取窗口：`LOOKBACK_DAYS = 21` 天（拉宽提量；靠 `history.txt` 去重保证不重复推送）
- 机构：`INSTITUTIONS` 12 家（GS/MS/JPM/BofA/Citi/Wells Fargo/UBS/Barclays/Deutsche Bank/Jefferies/Wedbush/Bernstein），每家可配多个域名，多域名用 `(site:a OR site:b)` 合并为一次查询
- 跨次去重：`history.txt` 记录已推送文章链接（保留最近 400 条），仅在推送成功后追加
- 送入 LLM 上限：`MAX_ARTICLES = 14` 条；每篇正文截到 `MAX_BODY_CHARS = 5500` 字；输出 `CLAUDE_MAX_TOKENS = 8000`
- 引擎：`CLAUDE_MODEL = claude-sonnet-4-6`（需 `ANTHROPIC_API_KEY` 有余额；如需更强改 `claude-opus-4-8`）
- 提量旋钮：嫌少就调大 `LOOKBACK_DAYS` / `MAX_ARTICLES` 或往 `INSTITUTIONS` 加机构；嫌长就调小 `MAX_ARTICLES`

## 行为规范

- 版式为「主题深读」：按 AI capex/变现、二阶受益、半导体算力、AI 与 ECM 等主题跨机构聚合（主题由 Claude 动态归纳），每篇给「核心判断 / 论据&数据 / 投资启示」三层
- **数字保留英文原写法**（USD 700bn、11→16 trillion、+7% CAGR）：prompt 硬规则，避免 billion→亿 的数量级翻译错误
- 来源链接由系统在 LLM 输出后程序化追加（`build_source_list`），**不让 LLM 生成 URL**，保证链接不被篡改；正文用【编号】回指；链接优先用解码后的真实 URL
- 手动测试：`agents/wallstreet_ai/run.sh monday --dry-run`（只抓取整理打印，不推送、不写 history）
