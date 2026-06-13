#!/bin/bash
# 自定位仓库根，避免硬编码绝对路径（可跨机器/跨用户）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.14/bin/python3}"

# 作用域注入：只拿本 agent 需要的 key（keys not prompts）。把 <KEYS> 换成所需 key 列表
eval "$("$REPO_ROOT/tools/load_env.sh" <KEYS>)"

cd "$SCRIPT_DIR"
"$PYTHON" <NAME>.py "$@"
