#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
    printf '%s\n' '请先创建虚拟环境并安装依赖：' 'python3 -m venv .venv' '.venv/bin/pip install -r requirements.txt' >&2
    exit 1
fi
exec "$project_dir/.venv/bin/python" "$project_dir/main.py" "$@"
