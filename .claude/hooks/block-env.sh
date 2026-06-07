#!/bin/bash
# PreToolUse hook: block Edit/Write to .env (5 API keys live there).
# Allows .env.example, .env.local, .env.dev, etc.
INPUT=$(cat)
P=$(printf '%s' "$INPUT" | /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null)
if [ "$(basename "$P" 2>/dev/null)" = ".env" ]; then
    echo "Blocked: edits to .env are protected (contains 5 API keys). If intentional, edit via terminal: \$EDITOR \"$P\"" >&2
    exit 2
fi
exit 0
