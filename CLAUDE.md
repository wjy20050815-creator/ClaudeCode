# ClaudeCode

macOS 自动化 agent 集合，统一通过 Server酱推送内容到微信。

## Agents

| Agent | 目录 | 职责 | 触发 |
|-------|------|------|------|
| 财经新闻 | `agents/financial_news/` | 每日三次推送财经资讯 | launchd（morning2/afternoon/night + catchup） |
| 脑科学 | `agents/brain_science/` | 每日早晨/夜间推送脑科学知识 | launchd（catchup + night） |
| 论文阅读 | `agents/paper_reader/` | PubMed/CiNii 抓取学术论文整理到 Obsidian Vault | 手动 CLI |
| 笔记同步 | `agents/notes_sync/` | Apple Notes ↔ Obsidian 双向同步 | launchd（4 小时） |
| 每日简报 | `agents/daily_brief/` | 读取 vault 近期内容，生成联结/模式/问题简报到 Inbox/ | launchd 08:30 |
| 就活 YouTube | `agents/shukatsu_youtube/` | YouTube 字幕抓取 → Obsidian 素材 → NotebookLM 投入 | 手动 CLI |
| 华尔街 AI 观点 | `agents/wallstreet_ai/` | 各大投行官方栏目的 AI 投资文章 → 主题聚合中文播报 | launchd（周一/周五 08:00） |

> 每个 agent 目录下有自己的 `CLAUDE.md`，本文件不覆盖它们。

## 子项目

- `obsidian-mind/` — 独立的 Obsidian vault 模板系统，自带 `CLAUDE.md` / skill 体系 / SessionStart hook。修改前先读其根 CLAUDE.md，不要混淆其约定（vault 路径、frontmatter schema）与本仓库其他 agent。

## Skill ↔ Agent 对应

同名的 skill 和 agent 是包装关系：skill 是对话入口，agent 是脚本本体。修改 skill 前先读 agent 的源码，不要重复实现。

| Skill（`~/.claude/skills/`） | Agent（本仓库） | 关系 |
|------|-------|------|
| `paper-reader` | `agents/paper_reader/` | skill 提供对话流程，与 agent 共享 `papers.json` |
| `shukatsu` | `agents/shukatsu_youtube/` | `/shukatsu ingest` 调用 agent 的 `ingest.py` |

## 基础设施

- **Python**：`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- **环境变量**：统一从 `.env` 加载，各 `run.sh` 以 `set -a; source .env; set +a` 注入
- **Stamp 文件**：`.stamps/<slot>`（项目根目录下，**不是** `~/.stamps/`），防止同一时段重复推送；删除对应文件即可强制补跑
- **`run.sh` 参数约定**：
  - `financial_news` / `brain_science` 第一个参数是 slot 名（`morning2`/`afternoon`/`night` 或 `morning`/`night`），成功后写 `.stamps/<slot>`（brain_science 写 `brain_<slot>`）
  - `daily_brief` 不接 slot，stamp 文件硬编码为 `.stamps/daily_brief`
  - `wallstreet_ai` 第一个参数是 slot 名（`monday`/`friday`），成功后写 `.stamps/wallstreet_<slot>`
  - `notes_sync` 不接 slot、不写 stamp（按 launchd 间隔触发，无补跑机制）
  - `paper_reader` / `shukatsu_youtube` 是手动 CLI，参数透传给 python
- **LaunchAgents**：`~/Library/LaunchAgents/com.<agent_name>.<slot>.plist`
- **日志**：`agents/<name>/<name>.log`，定时 agent 由 `run.sh` 自动 tail 截断（financial_news/brain_science 500 行，daily_brief 300 行，notes_sync 2000 行），勿手动清空。注：notes_sync 日志由 plist 重定向写入，截断用 `cat` 原地覆盖而非 `mv`
- **agent 目录结构差异（均为有意，非遗漏）**：`requirements.txt` 仅「用 Python 且有独立依赖」的 agent 有（financial_news/brain_science/paper_reader/wallstreet_ai）——notes_sync 依赖写在 `install.sh`、shukatsu 是 Node、daily_brief 复用根环境；`catchup.sh` 仅「关机会错过固定时段、需开机补跑」的 agent 有（financial_news/brain_science）

| 变量 | 用途 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API（paper_reader、wallstreet_ai） |
| `GROQ_API_KEY` | Groq LLaMA（financial_news、brain_science） |
| `NEWSAPI_KEY` | NewsAPI 英文新闻源 |
| `GNEWS_KEY` | GNews 新闻源（financial_news） |
| `SERVERCHAN_KEY` | Server酱微信推送 |

## Skills（`~/.claude/skills/`）

| Skill | 用途 |
|-------|------|
| `defuddle` | 从网页提取干净 Markdown |
| `es-coach` | 就活 ES 对话式批改コーチ |
| `find-skills` | 搜索安装新 skill |
| `json-canvas` | 读写 Obsidian `.canvas` 文件 |
| `karpathy-guidelines` | 减少 LLM 编码错误的行为准则 |
| `meal-planner` | AI 饮食规划：冰箱食材管理、每周菜单生成、微信联动 |
| `obsidian-bases` | 创建/编辑 `.base` 数据库文件 |
| `obsidian-cli` | 命令行操控 Obsidian 实例 |
| `obsidian-markdown` | Obsidian Markdown 语法参考 |
| `obsidian-second-brain` | Obsidian vault 全体操作（蒸馏 / 研究 / kanban 等） |
| `paper-reader` | 单篇论文读み込みフロー（paper_reader agent と連携） |
| `stock-report` | 个股深度投资分析报告（日/美/港/欧，4 种风格，12 章结构化） |
| `shukatsu` | 日本就活蒸馏コーチ（ingest / distill / coach 3 模式） |

## 编码准则（Karpathy）

1. **编码前先思考**：暴露假设，有歧义先提问
2. **简单优先**：最少代码，不加未请求的功能或抽象
3. **外科手术式修改**：只改必须改的，不顺手重构
4. **目标驱动**：定义可验证标准，多步骤先陈述计划

## 常用运维

```bash
# 强制补跑某个时段（删除 stamp 后 launchd 下次会重新执行；或手动调用 run.sh）
rm .stamps/morning2   # 例：财经新闻早间

# 手动跑一次（带 slot 名以便正确写 stamp）
agents/financial_news/run.sh morning2

# 看最近日志
tail -100 agents/financial_news/financial_news.log

# 重新加载某个 LaunchAgent
launchctl unload ~/Library/LaunchAgents/com.financial_news.morning2.plist
launchctl load   ~/Library/LaunchAgents/com.financial_news.morning2.plist
```

## 修改守则

- 修改任何 agent 前，先读对应目录的 `CLAUDE.md`
- 新增 agent 时，在上方 Agents 表格追加一行
- `.env` 只加不删，废弃的 key 注释掉而非删除
- `*.log` 不提交 git，不手动截断，由各 agent 自行 append
