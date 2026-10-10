#!/usr/bin/env bash
# Run as your desktop user; only apt requires sudo.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_system=true
start_app=true
python_bin=python3
launch_args=()
while (($#)); do
    case "$1" in
        --skip-system) install_system=false; shift ;;
        --no-start) start_app=false; shift ;;
        --python)
            [[ $# -ge 2 ]] || { echo '--python 后需要解释器路径' >&2; exit 2; }
            python_bin="$2"; shift 2 ;;
        --) shift; launch_args=("$@"); break ;;
        -h|--help)
            cat <<'HELP'
用法：./install.sh [--no-start] [--skip-system] [--python python3] [-- 启动参数]
默认安装 Ubuntu/Debian 系统依赖、项目虚拟环境，并后台启动、登记登录自启动。
  --no-start     只安装，不启动、不登记自启动（服务器/打包环境可用）
  --skip-system 已自行安装系统依赖时跳过 apt
  --python PATH 用指定的 Python 3.10+ 创建虚拟环境
  -- --preview  安装后以普通窗口模式启动
请以日常桌面用户运行，脚本仅在安装系统包时调用 sudo。
HELP
            exit 0 ;;
        *) printf '未知参数：%s（参见 --help）\n' "$1" >&2; exit 2 ;;
    esac
done

if [[ $EUID -eq 0 && "$start_app" == true ]]; then
    echo '请用日常桌面用户运行 ./install.sh，不要 sudo 整个脚本；系统包会单独申请 sudo。' >&2
    exit 1
fi
if "$install_system"; then
    if ! command -v apt-get >/dev/null || ! command -v dpkg-query >/dev/null; then
        echo '自动安装系统依赖目前支持 Ubuntu/Debian；其他发行版请安装 Qt X11/Wayland 依赖后使用 --skip-system。' >&2
        exit 1
    fi
    packages=(python3 python3-venv libxcb-cursor0 libxcb-icccm4 libxcb-image0
              libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1
              libxcb-randr0 libxcb-shm0 libxcb-sync1 libxcb-xfixes0 libxcb-shape0
              libx11-xcb1 libxkbcommon-x11-0 libegl1 libgl1 libdbus-1-3
              libfontconfig1 fonts-noto-cjk)
    # Ubuntu 24.04 / Debian 13 renamed GLib for the 64-bit time_t transition.
    if [[ "$(dpkg-query -W -f='${Status}' libglib2.0-0t64 2>/dev/null || true)" == 'install ok installed' ]]; then
        packages+=(libglib2.0-0t64)
    else
        packages+=(libglib2.0-0)
    fi
    desktop_name="${XDG_CURRENT_DESKTOP:-}"
    if [[ "${desktop_name,,}" == *gnome* || "${desktop_name,,}" == *ubuntu* ]]; then
        packages+=(gnome-shell-extension-appindicator)
    fi
    missing=()
    for package in "${packages[@]}"; do
        if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != 'install ok installed' ]]; then
            missing+=("$package")
        fi
    done
    if ((${#missing[@]})); then
        privilege=()
        if [[ $EUID -ne 0 ]]; then
            command -v sudo >/dev/null || { echo '安装系统包需要 sudo，请先由管理员安装依赖。' >&2; exit 1; }
            privilege=(sudo)
        fi
        "${privilege[@]}" apt-get update
        "${privilege[@]}" apt-get install -y "${missing[@]}"
    fi
fi

command -v "$python_bin" >/dev/null || { printf '找不到 Python：%s\n' "$python_bin" >&2; exit 1; }
"$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "需要 Python 3.10 或更高版本")'
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
    "$python_bin" -m venv "$project_dir/.venv"
fi
"$project_dir/.venv/bin/python" -m pip install -r "$project_dir/requirements.txt"
# Import alone does not detect missing xcb dependencies: load the actual plugin.
"$project_dir/.venv/bin/python" - <<'PY'
import ctypes
from pathlib import Path
from PySide6.QtCore import QLibraryInfo
try:
    ctypes.CDLL('libxcb-cursor.so.0')
    plugins = Path(QLibraryInfo.path(QLibraryInfo.PluginsPath))
    ctypes.CDLL(str(plugins / 'platforms/libqxcb.so'))
except OSError as exc:
    raise SystemExit(f'Qt 桌面依赖不完整：{exc}\nUbuntu/Debian 请确认已安装 libxcb-cursor0 及 Qt XCB 依赖。')
print('Python、PySide6 和 Qt XCB 依赖检查通过（含 libxcb-cursor0）。')
PY

if "$start_app"; then
    if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
        echo '安装完成。当前没有图形桌面会话，请登录桌面后运行 ./run.sh 以启动并启用自启动。'
        exit 0
    fi
    if command -v gnome-extensions >/dev/null; then
        for extension in ubuntu-appindicators@ubuntu.com appindicatorsupport@rgcjonas.gmail.com; do
            if gnome-extensions info "$extension" >/dev/null 2>&1; then
                gnome-extensions enable "$extension" || echo '托盘扩展暂未启用，请重新登录 GNOME 后启用 AppIndicator。' >&2
                break
            fi
        done
    fi
    exec "$project_dir/run.sh" "${launch_args[@]}"
fi
echo '安装完成。运行 ./run.sh 即可后台启动并启用登录自启动。'
