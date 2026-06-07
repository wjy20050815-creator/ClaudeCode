#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
PLIST_SRC="$SCRIPT_DIR/com.notes_sync.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.notes_sync.plist"

echo "Installing dependencies…"
$PYTHON -m pip install html2text markdown --quiet

echo "Registering launchd agent…"
cp "$PLIST_SRC" "$PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "Done. Sync runs every 4 hours."
echo "  Manual run : bash $SCRIPT_DIR/run.sh"
echo "  Logs       : $SCRIPT_DIR/sync.log"
echo ""
echo "First run will ask for Notes access permission — grant it in System Settings."
