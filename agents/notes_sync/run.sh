#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
exec "$PYTHON" "$SCRIPT_DIR/sync.py"
