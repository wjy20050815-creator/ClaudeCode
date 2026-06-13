#!/bin/bash
# 自定位仓库根，避免硬编码绝对路径（可跨机器/跨用户）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.14/bin/python3}"

# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$("$REPO_ROOT/tools/load_env.sh" GROQ_API_KEY NEWSAPI_KEY SERVERCHAN_KEY)"

SLOT="${1}"
if [[ "$SLOT" != "morning" && "$SLOT" != "night" ]]; then
    echo "[错误] 需要传入 slot 参数：morning 或 night" >&2
    exit 1
fi

LOGFILE="$SCRIPT_DIR/brain_science.log"
STAMPDIR="$REPO_ROOT/.stamps"
mkdir -p "$STAMPDIR"

# 保留最近 500 行，防止日志无限增长
if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 500 ]; then
    tail -500 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

cd "$SCRIPT_DIR"
"$PYTHON" brain_science.py --slot "$SLOT" >> "$LOGFILE" 2>&1

if [ $? -eq 0 ]; then
    TZ="Asia/Tokyo" date "+%Y-%m-%d" > "${STAMPDIR}/brain_${SLOT}"
fi
