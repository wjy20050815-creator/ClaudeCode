#!/bin/bash
# 开机时检查脑科学推送是否被错过，若错过则补跑
TODAY_JST=$(TZ="Asia/Tokyo" date "+%Y-%m-%d")
NOW_TOTAL=$(( 10#$(TZ="Asia/Tokyo" date "+%H") * 60 + 10#$(TZ="Asia/Tokyo" date "+%M") ))
STAMPDIR="/Users/jiayi/Developer/ClaudeCode/.stamps"
SCRIPT="/Users/jiayi/Developer/ClaudeCode/agents/brain_science/run.sh"

# 早晨推送：开机后 06:00 起触发（今日首次开机推送晨间知识）
if [ $NOW_TOTAL -ge $((6 * 60 + 0)) ]; then
    if [ "$(cat "${STAMPDIR}/brain_morning" 2>/dev/null)" != "$TODAY_JST" ]; then
        /bin/bash "$SCRIPT" morning
    fi
fi

# 夜间推送：22:30 后开机才补跑（正常由 LaunchAgent 定时触发）
if [ $NOW_TOTAL -ge $((22 * 60 + 30)) ]; then
    if [ "$(cat "${STAMPDIR}/brain_night" 2>/dev/null)" != "$TODAY_JST" ]; then
        /bin/bash "$SCRIPT" night
    fi
fi
