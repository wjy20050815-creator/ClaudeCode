#!/bin/bash
# 一键部署：把仓库内所有 agents/*/com.*.plist 安装到 ~/Library/LaunchAgents 并重新加载。
# 仓库是 plist 的唯一真相来源；改完 plist 后跑一次本脚本即可让 launchd 生效。
# 注意：plist 内的路径硬编码为 /Users/jiayi/Developer/ClaudeCode，换机器需先改路径。
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$DEST_DIR"

count=0
for src in "$REPO_ROOT"/agents/*/com.*.plist; do
    [ -e "$src" ] || continue
    name="$(basename "$src")"
    dest="$DEST_DIR/$name"
    cp "$src" "$dest"
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load "$dest"
    echo "  loaded  $name"
    count=$((count + 1))
done

echo ""
echo "Done — $count launchd agent(s) (re)installed from repo."
echo "Verify: launchctl list | grep -E 'com\\.(financial_news|brain_science|notes_sync|daily_brief|wallstreet_ai)\\.'"
