#!/bin/bash
set -a
source /Users/jiayi/Developer/ClaudeCode/.env
set +a

LOGFILE="/Users/jiayi/Developer/ClaudeCode/agents/daily_brief/daily_brief.log"
STAMPDIR="/Users/jiayi/Developer/ClaudeCode/.stamps"
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

cd "/Users/jiayi/Developer/ClaudeCode/agents/daily_brief"
echo "[$(date)] [start] 每日简报开始" >> "$LOGFILE"

/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 daily_brief.py >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date)] [retry] 首次失败（exit $EXIT_CODE），60 秒后重试..." >> "$LOGFILE"
    sleep 60
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 daily_brief.py >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo "$TODAY" > "$STAMP"
    echo "[$(date)] [done] 今日简报完成" >> "$LOGFILE"
else
    echo "[$(date)] [fail] 简报生成失败，exit $EXIT_CODE" >> "$LOGFILE"
fi
