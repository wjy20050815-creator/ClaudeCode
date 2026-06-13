#!/bin/bash
# 自定位仓库根，避免硬编码绝对路径（可跨机器/跨用户）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.14/bin/python3}"

# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$("$REPO_ROOT/tools/load_env.sh" ANTHROPIC_API_KEY)"

cd "$SCRIPT_DIR"
"$PYTHON" paper_reader.py "$@"
RC=$?

# vault 治理：论文/概念笔记写入后对账 index/log（best-effort）
"$PYTHON" "$REPO_ROOT/tools/vault_index_sync.py" --fix --reason paper_reader || true

exit $RC
