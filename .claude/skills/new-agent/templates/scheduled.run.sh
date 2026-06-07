#!/bin/bash
set -a
source /Users/jiayi/Developer/ClaudeCode/.env
set +a

SLOT="${1:-unknown}"
shift
LOGFILE="/Users/jiayi/Developer/ClaudeCode/agents/<NAME>/<NAME>.log"
STAMPDIR="/Users/jiayi/Developer/ClaudeCode/.stamps"
mkdir -p "$STAMPDIR"

if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 500 ]; then
    tail -500 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

cd "/Users/jiayi/Developer/ClaudeCode/agents/<NAME>"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 <NAME>.py "$@" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[重试] 首次失败（exit $EXIT_CODE），60 秒后重试..." >> "$LOGFILE"
    sleep 60
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 <NAME>.py "$@" >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
fi

if [ $EXIT_CODE -eq 0 ]; then
    TZ="Asia/Tokyo" date "+%Y-%m-%d" > "${STAMPDIR}/${SLOT}"
fi
