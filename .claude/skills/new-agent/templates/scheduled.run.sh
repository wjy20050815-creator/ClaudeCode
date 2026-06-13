#!/bin/bash
# 自定位仓库根，避免硬编码绝对路径（可跨机器/跨用户）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.14/bin/python3}"

# 作用域注入：只拿本 agent 需要的 key（keys not prompts）。把 <KEYS> 换成所需 key 列表
eval "$("$REPO_ROOT/tools/load_env.sh" <KEYS>)"

SLOT="${1:-unknown}"
shift
LOGFILE="$SCRIPT_DIR/<NAME>.log"
STAMPDIR="$REPO_ROOT/.stamps"
mkdir -p "$STAMPDIR"

if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 500 ]; then
    tail -500 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

cd "$SCRIPT_DIR"
"$PYTHON" <NAME>.py "$@" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[重试] 首次失败（exit $EXIT_CODE），60 秒后重试..." >> "$LOGFILE"
    sleep 60
    "$PYTHON" <NAME>.py "$@" >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
fi

if [ $EXIT_CODE -eq 0 ]; then
    TZ="Asia/Tokyo" date "+%Y-%m-%d" > "${STAMPDIR}/${SLOT}"
fi
