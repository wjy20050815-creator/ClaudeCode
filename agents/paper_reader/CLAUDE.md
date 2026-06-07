# 论文阅读 Agent

学术论文を取得・Claude で構造化要約 → Obsidian Vault の `ゼミ发表/Papers/` に保存する手動 CLI。

## 数据流

URL / DOI / PDF パス → 全文抽出（PyMuPDF / BeautifulSoup）→ Claude API → `papers.json` 追記 + `papers.md` 更新 + Obsidian Vault に Markdown ノート出力

## 关键路径

| 项目 | 路径 |
|------|------|
| Vault | `/Users/jiayi/Documents/Obsidian Vault` |
| ノート出力 | `ゼミ发表/Papers/` |
| 概念ノート | `ゼミ发表/Concepts/` |
| 履歴 JSON | `agents/paper_reader/papers.json` |
| 一覧 MD | `agents/paper_reader/papers.md` |
| 興味設定 | `research_interests.yaml`（`interests` / `excluded_keywords`） |

## 触发

手動 CLI のみ。launchd 登録なし。

```bash
agents/paper_reader/run.sh <url-or-pdf-path>
```

`run.sh` は `.env` を読み込んで `ANTHROPIC_API_KEY` を注入してから `paper_reader.py` を起動する。

## 注意事项

- 抽出上限：`MAX_CHARS = 80_000`（HEAD/TAIL 各 35k）— 長尺論文は中間部分が切られる
- 並列：`MAX_WORKERS = 3`（PubMed 等のレート制限回避）
- `research_interests.yaml` の `excluded_keywords`（書評・教科書紹介等）に該当する論文はスキップされる
- `paper-reader` skill（`~/.claude/skills/paper-reader`）はこの agent と連携する対話モード。skill 経由でも同じ `papers.json` を更新する
