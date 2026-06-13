# ClaudeCode — macOS 自动化 agent 集合

**简体中文** | [English](README.en.md) | [日本語](README.ja.md)

一组运行在 macOS 上的个人自动化 agent：定时抓取新闻/学术/投行观点，经 LLM 整理后**通过 [Server酱](https://sct.ftqq.com/) 推送到微信**，或写入本地 [Obsidian](https://obsidian.md/) vault。由 `launchd` 调度，配套一套轻量治理基础设施（作用域密钥注入、路径注册表、index 对账、补跑机制）。

> 这是一个真实在用的个人项目。仓库内不含任何密钥或个人数据——所有私人配置都以 `*.example` 模板入库，真身由 `.gitignore` 排除。

## Agents

| Agent | 目录 | 职责 | 触发 | 依赖 |
|-------|------|------|------|------|
| 财经新闻 | `agents/financial_news/` | 每日三次推送财经资讯到微信 | launchd（早/午/晚 + 开机补跑） | NewsAPI + GNews + Groq + Server酱 |
| 脑科学 | `agents/brain_science/` | 每日早/夜推送有来源的脑科学知识 | launchd（补跑 + 夜间） | PubMed + NewsAPI + Groq + Server酱 |
| 华尔街 AI 观点 | `agents/wallstreet_ai/` | 各大投行官方栏目 AI 投资文章 → 主题聚合播报 | launchd（周一/周五 08:00） | Claude + Server酱 |
| 每日简报 | `agents/daily_brief/` | 读 vault 近期内容 + 当日日历 → 联结/模式/问题简报 | launchd（每日 08:30） | Obsidian + Groq |
| 笔记同步 | `agents/notes_sync/` | Apple Notes ↔ Obsidian 双向同步 | launchd（每 4 小时） | Obsidian + Apple Notes |
| 论文阅读 | `agents/paper_reader/` | PubMed/CiNii/PDF 抓取 → Claude 结构化 → Obsidian | 手动 CLI | Claude + Obsidian |

> 含 Obsidian 的 agent 需要你本地有一个 vault，并在 `vault.paths.env` 里配好路径（见下）。纯推送类（财经/脑科学/华尔街）不依赖 Obsidian。

## 基础设施亮点

- **作用域密钥注入（keys not prompts）**：`.env` 是唯一存储处，但每个 `run.sh` 经 `tools/load_env.sh KEY1 KEY2 ...` **只注入自己需要的 key**，agent 进程拿不到无关凭证。
- **Vault 路径注册表**：`vault.paths.env` 是所有 Obsidian 路径的唯一定义处（router 模式）。python 经 `tools/vault_paths.py` 解析，shell 直接 source，**任何脚本不硬编码 vault 路径**。
- **index/log 对账**：`tools/vault_index_sync.py` 把 vault 的 `index.md` 与实际文件对账，写 vault 的 agent 运行后自动调用。
- **补跑机制**：`.stamps/<slot>` 防止同一时段重复推送；`catchup.sh` 在开机/登录时补跑被关机错过的时段。
- **自定位脚本**：所有 `run.sh` 通过 `$SCRIPT_DIR` 解析仓库根，不含绝对路径，可跨机器/跨用户克隆即用。

## 快速开始

```bash
# 1. 克隆
git clone <your-fork-url> ClaudeCode && cd ClaudeCode

# 2. 配置密钥（按需，只填你要用的 agent 所需的 key）
cp .env.example .env
$EDITOR .env

# 3.（仅 Obsidian 相关 agent）配置 vault 路径
cp vault.paths.example.env vault.paths.env
$EDITOR vault.paths.env

# 4.（仅 paper_reader）配置研究兴趣
cp agents/paper_reader/research_interests.example.yaml agents/paper_reader/research_interests.yaml

# 5. 安装定时任务到 launchd（自动把 plist 占位符替换为本机真实路径）
bash scripts/install_launchagents.sh

# 6. 手动跑一次验证（带 slot 名）
agents/financial_news/run.sh morning2
```

需要的 API key 及获取地址见 [.env.example](.env.example)。Python 默认走系统 framework 解释器，可用环境变量覆盖：`PYTHON=/path/to/python3 agents/financial_news/run.sh morning2`。

## 仓库结构

```
agents/<name>/        # 每个 agent 自带 run.sh / CLAUDE.md / plist
tools/                # load_env.sh / vault_paths.py / vault_index_sync.py
scripts/              # install_launchagents.sh 一键部署
.env.example          # 密钥模板
vault.paths.example.env  # vault 路径模板
CLAUDE.md             # 给 Claude Code 看的项目操作手册（也是最好的架构文档）
```

每个 agent 目录下有自己的 `CLAUDE.md`，详述其数据流、参数与注意事项。

## 平台要求

- macOS（依赖 `launchd`；笔记同步与日历段依赖 Apple Notes / Calendar，需授权）
- Python 3.14（或用 `PYTHON` 环境变量指向你的解释器）

## License

[MIT](LICENSE)
