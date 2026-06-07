#!/bin/bash
# PostToolUse hook: when a LaunchAgent plist was edited, print the reload commands.
INPUT=$(cat)
P=$(printf '%s' "$INPUT" | /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null)
case "$P" in
    */Library/LaunchAgents/com.*.plist)
        echo "Reload required for plist change. Run:"
        echo "  launchctl unload \"$P\" 2>/dev/null; launchctl load \"$P\""
        ;;
esac
exit 0
