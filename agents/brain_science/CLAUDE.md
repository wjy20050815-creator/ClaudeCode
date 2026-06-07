# 脑科学知识推送 Agent

每日两次向微信推送有来源依据的脑科学知识，内容来自真实学术论文和权威健康科学媒体。

## 数据流

PubMed 学术论文 + 权威健康科学媒体（NewsAPI） → Groq LLaMA → Server酱 → 微信

## 内容来源（严格限定）

| 类型 | 来源 | API |
|------|------|-----|
| 学术论文 | PubMed（NIH 数据库） | 免费，无需 Key |
| 健康科学媒体 | Scientific American、ScienceDaily、Medical News Today、Psychology Today、Harvard Health、Nature、New Scientist | NewsAPI（已有 Key） |

AI 的角色是**改写和摘要**，不得凭空生成内容。若来源材料为空则跳过推送。

## 触发时机

| 时段 | 触发方式 | LaunchAgent |
|------|---------|-------------|
| 早晨 | 开机后 06:00 起，由 catchup.sh 触发 | `com.brain_science.catchup.plist` |
| 夜间 | 每天 22:30 JST 定时 | `com.brain_science.night.plist` |

- stamp 文件位于 `.stamps/brain_morning` 和 `.stamps/brain_night`
- 同一天内同一时段已推送则跳过，不重复推送
- `run.sh` 必须传入 `morning` 或 `night` 作为第一个参数，否则报错退出（手动补跑：`agents/brain_science/run.sh morning`）

## 主题分工与抓取策略

**morning（早晨认知与效率）**
- PubMed 关键词：皮质醇觉醒反应、晨间手机使用与注意力、晨间习惯与前额叶
- NewsAPI 关键词：brain morning cognitive focus attention wake alertness

**night（夜间睡眠与大脑恢复）**
- PubMed 关键词：睡眠记忆巩固、蓝光与褪黑素、胶质淋巴系统
- NewsAPI 关键词：sleep brain health memory neuroscience circadian recovery

## 去重机制

- `history.txt`：记录已推送知识点的标题，保留最近 60 条
- 每次摘要前将历史注入 Prompt，AI 被要求严禁重复历史话题
- 仅在推送成功（Server酱返回 code=0）后写入历史

## 与金融新闻 Agent 的隔离

| 组件 | 金融新闻 | 脑科学 |
|------|---------|--------|
| Python 脚本 | `financial_news/financial_news.py` | `agents/brain_science/brain_science.py` |
| 日志 | `financial_news/financial_news.log` | `agents/brain_science/brain_science.log` |
| Stamp 文件 | `morning2`, `afternoon`, `night` | `brain_morning`, `brain_night` |
| LaunchAgent | `com.financial_news.*` | `com.brain_science.*` |
| 去重历史 | 无 | `agents/brain_science/history.txt` |
