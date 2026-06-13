#!/bin/bash
# 开机/登录时检查各播报是否被错过，若错过则以当前时间为基准补跑
TODAY_JST=$(TZ="Asia/Tokyo" date "+%Y-%m-%d")
NOW_TOTAL=$(( 10#$(TZ="Asia/Tokyo" date "+%H") * 60 + 10#$(TZ="Asia/Tokyo" date "+%M") ))
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STAMPDIR="$REPO_ROOT/.stamps"
SCRIPT="$SCRIPT_DIR/run.sh"

# 09:10 早报
if [ $NOW_TOTAL -ge $((9 * 60 + 10)) ]; then
    if [ "$(cat "${STAMPDIR}/morning2" 2>/dev/null)" != "$TODAY_JST" ]; then
        /bin/bash "$SCRIPT" morning2
    fi
fi

# 16:30 午报
if [ $NOW_TOTAL -ge $((16 * 60 + 30)) ]; then
    if [ "$(cat "${STAMPDIR}/afternoon" 2>/dev/null)" != "$TODAY_JST" ]; then
        /bin/bash "$SCRIPT" afternoon
    fi
fi

# 23:30 夜报
if [ $NOW_TOTAL -ge $((23 * 60 + 30)) ]; then
    if [ "$(cat "${STAMPDIR}/night" 2>/dev/null)" != "$TODAY_JST" ]; then
        /bin/bash "$SCRIPT" night
    fi
fi
