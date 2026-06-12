#!/bin/bash
# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$(/Users/jiayi/Developer/ClaudeCode/tools/load_env.sh GROQ_API_KEY NEWSAPI_KEY SERVERCHAN_KEY)"

SLOT="${1}"
if [[ "$SLOT" != "morning" && "$SLOT" != "night" ]]; then
    echo "[错误] 需要传入 slot 参数：morning 或 night" >&2
    exit 1
fi

LOGFILE="/Users/jiayi/Developer/ClaudeCode/agents/brain_science/brain_science.log"
STAMPDIR="/Users/jiayi/Developer/ClaudeCode/.stamps"
mkdir -p "$STAMPDIR"

# 保留最近 500 行，防止日志无限增长
if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 500 ]; then
    tail -500 "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
fi

cd "/Users/jiayi/Developer/ClaudeCode/agents/brain_science"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 brain_science.py --slot "$SLOT" >> "$LOGFILE" 2>&1

if [ $? -eq 0 ]; then
    TZ="Asia/Tokyo" date "+%Y-%m-%d" > "${STAMPDIR}/brain_${SLOT}"
fi
