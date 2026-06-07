#!/bin/bash
set -a
source /Users/jiayi/Developer/ClaudeCode/.env
set +a

cd /Users/jiayi/Developer/ClaudeCode/agents/<NAME>
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 <NAME>.py "$@"
