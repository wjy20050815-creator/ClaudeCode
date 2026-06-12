#!/bin/bash
# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$(/Users/jiayi/Developer/ClaudeCode/tools/load_env.sh GROQ_API_KEY NEWSAPI_KEY GNEWS_KEY SERVERCHAN_KEY)"

SLOT="${1:-unknown}"
shift
LOGFILE="/Users/jiayi/Developer/ClaudeCode/agents/financial_news/financial_news.log"
STAMPDIR="/Users/jiayi/Developer/ClaudeCode/.stamps"
mkdir -p "$STAMPDIR"

# 保留最近 500 行，防止日志无限增长
if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 500 ]; then
    tail -500 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

cd "/Users/jiayi/Developer/ClaudeCode/agents/financial_news"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 financial_news.py "$@" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[重试] 首次失败（exit $EXIT_CODE），60 秒后重试..." >> "$LOGFILE"
    sleep 60
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 financial_news.py "$@" >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
fi

# 仅在脚本成功退出时写入 stamp，失败时保留补跑机会
if [ $EXIT_CODE -eq 0 ]; then
    TZ="Asia/Tokyo" date "+%Y-%m-%d" > "${STAMPDIR}/${SLOT}"
fi
