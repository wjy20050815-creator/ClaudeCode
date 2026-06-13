#!/bin/bash
# 按 agent 作用域注入环境变量（权限层 = keys not prompts）。
# 用法（run.sh 内）：
#   eval "$("$REPO_ROOT/tools/load_env.sh" GROQ_API_KEY SERVERCHAN_KEY)"
# 只导出参数列出的 key；agent 进程拿不到 .env 里的其他凭证。
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
set -a
source "$ENV_FILE"
set +a
for k in "$@"; do
    printf 'export %s=%q\n' "$k" "${!k}"
done
