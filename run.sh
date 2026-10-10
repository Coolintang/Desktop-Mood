#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
    printf '%s\n' '尚未安装运行环境，请先运行 ./install.sh。' >&2
    exit 1
fi
exec "$project_dir/.venv/bin/python" "$project_dir/garden/launcher.py" "$@"
