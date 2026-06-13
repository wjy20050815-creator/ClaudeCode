#!/bin/bash
# 自定位仓库根，避免硬编码绝对路径（可跨机器/跨用户）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.14/bin/python3}"

# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$("$REPO_ROOT/tools/load_env.sh" GROQ_API_KEY SERVERCHAN_KEY)"

LOGFILE="$SCRIPT_DIR/daily_brief.log"
STAMPDIR="$REPO_ROOT/.stamps"
STAMP="${STAMPDIR}/daily_brief"
mkdir -p "$STAMPDIR"

# 保留最近 300 行
if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 300 ]; then
    tail -300 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

TODAY=$(TZ="Asia/Tokyo" date "+%Y-%m-%d")

# 同一天已运行成功则跳过
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$TODAY" ]; then
    echo "[$(date)] [skip] 今日简报已完成，跳过" >> "$LOGFILE"
    exit 0
fi

cd "$SCRIPT_DIR"
echo "[$(date)] [start] 每日简报开始" >> "$LOGFILE"

"$PYTHON" daily_brief.py >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date)] [retry] 首次失败（exit $EXIT_CODE），60 秒后重试..." >> "$LOGFILE"
    sleep 60
    "$PYTHON" daily_brief.py >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo "$TODAY" > "$STAMP"
    echo "[$(date)] [done] 今日简报完成" >> "$LOGFILE"
else
    echo "[$(date)] [fail] 简报生成失败，exit $EXIT_CODE" >> "$LOGFILE"
fi

# vault 治理：每日对账 index.md（hot cache）与 vault 实际文件，兜住所有写入者的漂移。
# best-effort：对账失败不影响简报结果。
"$PYTHON" "$REPO_ROOT/tools/vault_index_sync.py" --fix --reason daily_brief >> "$LOGFILE" 2>&1 || true
