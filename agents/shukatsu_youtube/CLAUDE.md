# 就活 YouTube Agent

就活関連 YouTube 動画の字幕を抽出 → Obsidian Vault の `素材/YouTube/` に原文保存 → NotebookLM へ自動投入する手動 CLI。

**AI 要約は行わない**：NotebookLM 側で要約するため、字幕原文のみ保存する。

## 数据流

YouTube URL → メタデータ + 字幕抽出 → 業界分類 → Obsidian Vault に Markdown 保存 → patchright で NotebookLM ノートに追加

## 关键路径

| 项目 | 路径 |
|------|------|
| Vault 出力 | `/Users/jiayi/Documents/Obsidian Vault/就活/知识库/_蒸馏システム/素材/YouTube/` |
| Python venv | `~/.claude/skills/obsidian-second-brain/.venv/bin/python`（借用其他 skill 的 venv，删除该 skill 会破坏本 agent） |
| NotebookLM 認証 | `~/Library/Application Support/notebooklm-mcp/browser_state/state.json` |
| スクリーンショット | `agents/shukatsu_youtube/screenshots/` |
| バッチ URL リスト | `batch_urls.txt` |

## 业界分类

`ingest.py` の `INDUSTRY_PATTERNS` で正規表現マッチ：

- `金融失敗`：外銀落ち / 金融失敗 / 落選 / 不合格
- `商社`：商社 / 伊藤忠 / 三菱商事 / 三井物産 / 住友商事 / 丸紅 / 双日 / 兼松
- `金融`：外銀 / 投資銀行 / ゴールドマン / モルスタ / JP モルガン / メガバンク 等
- マッチなし → `全行業`

手動指定：`python ingest.py <url> 商社`

## 触发

手動 CLI のみ。

```bash
# 単発
python ingest.py https://www.youtube.com/watch?v=XXXXXXXXXXX

# バッチ（batch_urls.txt の各行を処理）
python ingest.py --batch batch_urls.txt

# NotebookLM へまとめて追加
node add_to_notebooklm.mjs
```

## NotebookLM 連携

`add_to_notebooklm.mjs` 内 `NOTEBOOKS` 定数に各業界のノートブック URL とビデオ URL を記述：

| 業界 | NotebookLM URL の管理 |
|------|----------------------|
| 商社就活 | 定数内に直接埋め込み |
| 金融就活 | 同上 |
| 全行業共通就活 | 同上 |

`--screenshot-only` フラグでスクリーンショットのみ取得（投入前の動作確認用）。

## 注意事项

- 字幕が取れない動画はスキップ（YouTube 内部 API による取得・API key 不要）
- patchright が初回起動時に `state.json` を要求 — `notebooklm-mcp` の setup_auth で生成しておく
- 同じ動画 ID を再 ingest しても上書きされる（差分マージなし）
- `shukatsu` skill（`/shukatsu ingest`）はこの agent をラップした対話インターフェース
