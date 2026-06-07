# Notes Sync Agent

Apple Notes ↔ Obsidian Vault 双向同步。

## 职责

| 方向 | 内容 |
|------|------|
| Notes → Obsidian | HTML → Markdown，图片导出到 `<folder>/<title>/`（与笔记同目录下的同名子文件夹） |
| Obsidian → Notes | Markdown → HTML，推回 Notes（图片不反向） |
| 冲突策略 | Notes 优先 |

## 配置

- Vault：`/Users/jiayi/Documents/Obsidian Vault`
- 频率：每 4 小时（launchd StartInterval=14400）
- 状态文件：`{vault}/.notes_sync_state.json`（隐藏文件，不提交 git）
- `run.sh` 不接 slot 参数、不写 `.stamps/`、不截断 `sync.log`（与其他定时 agent 不同 — 这是连续 interval 模式，无补跑概念）
- 依赖：Python `markdownify` / `markdown` / `beautifulsoup4`（由 `install.sh` 安装到系统 Python 3.14）

## 文件

| 文件 | 用途 |
|------|------|
| `sync.py` | 主同步逻辑 |
| `run.sh` | 入口脚本 |
| `install.sh` | 安装 launchd agent 和依赖 |
| `com.notes_sync.plist` | launchd 配置 |

## 注意事项

- AppleScript 首次运行会弹出 Notes 访问授权，在系统设置中允许即可
- 附件子目录下的图片不同步回 Notes
- Obsidian 中新建的 `.md` 文件，只要在已同步的文件夹下，就会被推到 Notes
- 不在已知 Notes 文件夹下的 Obsidian 文件不会被推到 Notes
