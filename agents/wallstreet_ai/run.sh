#!/bin/bash
# 自定位仓库根，避免硬编码绝对路径（可跨机器/跨用户）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.14/bin/python3}"

# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$("$REPO_ROOT/tools/load_env.sh" ANTHROPIC_API_KEY SERVERCHAN_KEY)"

SLOT="${1:-unknown}"
shift 2>/dev/null
LOGFILE="$SCRIPT_DIR/wallstreet_ai.log"
STAMPDIR="$REPO_ROOT/.stamps"
mkdir -p "$STAMPDIR"

# 保留最近 500 行，防止日志无限增长
if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 500 ]; then
    tail -500 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

cd "$SCRIPT_DIR"
"$PYTHON" wallstreet_ai.py --slot "$SLOT" "$@" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[重试] 首次失败（exit $EXIT_CODE），60 秒后重试..." >> "$LOGFILE"
    sleep 60
    "$PYTHON" wallstreet_ai.py --slot "$SLOT" "$@" >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
fi

# 仅在脚本成功退出时写入 stamp，失败时保留补跑机会
if [ $EXIT_CODE -eq 0 ]; then
    TZ="Asia/Tokyo" date "+%Y-%m-%d" > "${STAMPDIR}/wallstreet_${SLOT}"
fi
