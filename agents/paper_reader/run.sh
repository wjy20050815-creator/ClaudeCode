#!/bin/bash
set -a
source /Users/jiayi/Developer/ClaudeCode/.env
set +a

cd /Users/jiayi/Developer/ClaudeCode/agents/paper_reader
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 paper_reader.py "$@"
