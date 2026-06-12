#!/bin/bash
# 作用域注入：只拿本 agent 需要的 key（keys not prompts）
eval "$(/Users/jiayi/Developer/ClaudeCode/tools/load_env.sh ANTHROPIC_API_KEY)"

cd /Users/jiayi/Developer/ClaudeCode/agents/paper_reader
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 paper_reader.py "$@"
RC=$?

# vault 治理：论文/概念笔记写入后对账 index/log（best-effort）
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
    /Users/jiayi/Developer/ClaudeCode/tools/vault_index_sync.py --fix --reason paper_reader || true

exit $RC
