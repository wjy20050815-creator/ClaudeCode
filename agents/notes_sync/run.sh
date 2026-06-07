#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"

# 日志由 launchd plist 重定向写入（StandardOutPath → sync.log）。启动前原地截断防止无限增长。
# 必须用 cat 原地覆盖而非 mv：launchd 已打开的 fd 指向同一 inode，换 inode 会丢失 python 的输出。
LOGFILE="$SCRIPT_DIR/sync.log"
if [ -f "$LOGFILE" ] && [ "$(wc -l < "$LOGFILE")" -gt 2000 ]; then
    tail -n 2000 "$LOGFILE" > "${LOGFILE}.tmp" && cat "${LOGFILE}.tmp" > "$LOGFILE" && rm -f "${LOGFILE}.tmp"
fi

exec "$PYTHON" "$SCRIPT_DIR/sync.py"
