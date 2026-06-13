# ClaudeCode — macOS 自動化エージェント集

[简体中文](README.md) | [English](README.en.md) | **日本語**

macOS 上で動く個人用の自動化エージェント群です。ニュース／学術論文／投資銀行の見解を定期的に取得し、LLM で整理したうえで **[Server酱（ServerChan）](https://sct.ftqq.com/) 経由で WeChat に配信**、またはローカルの [Obsidian](https://obsidian.md/) vault に書き込みます。スケジューリングは `launchd` が担い、軽量なガバナンス基盤（スコープ付きシークレット注入・パスレジストリ・index 整合・取りこぼし再実行）を備えています。

> これは実際に運用している個人プロジェクトです。リポジトリにシークレットや個人データは一切含まれません。プライベートな設定はすべて `*.example` テンプレートとして入っており、実ファイルは `.gitignore` で除外しています。

## エージェント一覧

| エージェント | ディレクトリ | 役割 | トリガー | 依存 |
|-------------|-------------|------|---------|------|
| 経済ニュース | `agents/financial_news/` | 経済ニュースを 1 日 3 回 WeChat に配信 | launchd（朝／昼／夜 + 起動時リカバリ） | NewsAPI + GNews + Groq + ServerChan |
| 脳科学 | `agents/brain_science/` | 出典付きの脳科学知識を朝／夜に配信 | launchd（リカバリ + 夜間） | PubMed + NewsAPI + Groq + ServerChan |
| ウォール街 AI 見解 | `agents/wallstreet_ai/` | 各投資銀行の公式コラムの AI 投資記事 → テーマ別ダイジェスト | launchd（月・金 08:00） | Claude + ServerChan |
| デイリーブリーフ | `agents/daily_brief/` | vault の直近内容 + 当日カレンダー → つながり／パターン／問い | launchd（毎日 08:30） | Obsidian + Groq |
| ノート同期 | `agents/notes_sync/` | Apple Notes ↔ Obsidian の双方向同期 | launchd（4 時間ごと） | Obsidian + Apple Notes |
| 論文リーダー | `agents/paper_reader/` | PubMed/CiNii/PDF を取得 → Claude で構造化 → Obsidian | 手動 CLI | Claude + Obsidian |

> Obsidian を使うエージェントは、ローカルに vault があり、そのパスが `vault.paths.env` に設定されている必要があります（下記参照）。配信のみのエージェント（経済ニュース／脳科学／ウォール街）は Obsidian 不要です。

## 基盤のハイライト

- **スコープ付きシークレット注入（keys not prompts）**：`.env` が唯一の保管場所ですが、各 `run.sh` は `tools/load_env.sh KEY1 KEY2 ...` を介して **必要な key だけ** を注入します。エージェントのプロセスは無関係な認証情報を一切受け取りません。
- **Vault パスレジストリ**：`vault.paths.env` が全 Obsidian パスを定義する唯一の場所です（router パターン）。Python は `tools/vault_paths.py` で解決し、シェルは直接 `source` し、**どのスクリプトも vault パスをハードコードしません**。
- **index/log 整合**：`tools/vault_index_sync.py` が vault の `index.md` を実ファイルと突き合わせます。vault に書き込むエージェントは実行後に自動で呼び出します。
- **取りこぼし再実行**：`.stamps/<slot>` が同一スロット内の重複配信を防ぎ、`catchup.sh` がマシン停止中に逃したスロットを起動／ログイン時に再実行します。
- **自己位置解決スクリプト**：すべての `run.sh` は `$SCRIPT_DIR` でリポジトリルートを解決し、絶対パスを含まず、別マシン／別ユーザーでも clone してそのまま動きます。

## クイックスタート

```bash
# 1. クローン
git clone <your-fork-url> ClaudeCode && cd ClaudeCode

# 2. シークレット設定（使うエージェントに必要な key だけ入れる）
cp .env.example .env
$EDITOR .env

# 3.（Obsidian 系エージェントのみ）vault パス設定
cp vault.paths.example.env vault.paths.env
$EDITOR vault.paths.env

# 4.（paper_reader のみ）研究興味設定
cp agents/paper_reader/research_interests.example.yaml agents/paper_reader/research_interests.yaml

# 5. launchd へ定期ジョブをインストール（plist のプレースホルダは実機の実パスに置換される）
bash scripts/install_launchagents.sh

# 6. 動作確認に 1 回実行（slot 名を渡す）
agents/financial_news/run.sh morning2
```

必要な API key と取得先は [.env.example](.env.example) を参照してください。Python は既定でシステムの framework インタプリタを使います。環境変数で上書きできます：`PYTHON=/path/to/python3 agents/financial_news/run.sh morning2`。

## リポジトリ構成

```
agents/<name>/        # 各エージェントが run.sh / CLAUDE.md / plist を持つ
tools/                # load_env.sh / vault_paths.py / vault_index_sync.py
scripts/              # install_launchagents.sh ワンショット配備
.env.example          # シークレットのテンプレート
vault.paths.example.env  # vault パスのテンプレート
CLAUDE.md             # Claude Code 用の操作マニュアル（最良のアーキテクチャ資料でもある）
```

各エージェントのディレクトリには、データフロー・パラメータ・注意点を記した `CLAUDE.md` があります。

## 動作要件

- macOS（`launchd` に依存。ノート同期とカレンダー部分は Apple Notes / Calendar に依存し、認可が必要）
- Python 3.14（または `PYTHON` 環境変数で自分のインタプリタを指定）

## ライセンス

[MIT](LICENSE)
