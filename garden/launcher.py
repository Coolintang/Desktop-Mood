"""Detached desktop launch and XDG autostart registration (no shell evaluation)."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MANAGED = 'X-Haruniwa-Managed=true'


def xdg_path(variable, fallback):
    value = os.environ.get(variable, '')
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def autostart_path():
    return xdg_path('XDG_CONFIG_HOME', '.config') / 'autostart/haruniwa.desktop'


def desktop_arg(value):
    # Exec has its own quoting layer, then the desktop file's string escaping.
    value = str(value).replace('%', '%%')
    if any(c in value for c in '\n\r\x00'):
        raise ValueError('自启动路径和参数不能包含换行或空字符')
    value = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + value.replace('\\', '\\\\') + '"'


def register_autostart(app_args):
    path = autostart_path()
    if path.exists() and MANAGED not in path.read_text(encoding='utf-8').splitlines():
        raise OSError(f'已有手工创建的启动项，未覆盖：{path}')
    command = ' '.join(desktop_arg(arg) for arg in [sys.executable, ROOT / 'garden/launcher.py',
                                                  '--autostart', *app_args])
    content = ('[Desktop Entry]\nType=Application\nName=春庭 · Haruniwa\n'
               'Comment=动态庭院与庭友群聊\nExec=' + command + '\n'
               'Icon=preferences-desktop-wallpaper\nTerminal=false\n'
               'StartupNotify=false\nX-GNOME-Autostart-enabled=true\n'
               'X-GNOME-Autostart-Delay=5\n' + MANAGED + '\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def disable_autostart():
    path = autostart_path()
    if path.exists():
        if MANAGED not in path.read_text(encoding='utf-8').splitlines():
            raise OSError(f'此启动项不是脚本创建的，请手动管理：{path}')
        path.unlink()
    print('已关闭春庭登录自启动；当前运行的庭院不受影响。')


def main(argv=None):
    parser = argparse.ArgumentParser(description='春庭：后台运行，并在成功启动后启用当前用户的桌面登录自启动')
    parser.add_argument('--preview', action='store_true', help='普通窗口预览（Wayland 推荐）')
    parser.add_argument('--state', type=Path, default=ROOT / 'data/state.json', help='独立存档路径')
    parser.add_argument('--screen', help='显示器名称')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--quit', action='store_true', help='请求保存并退出，不改变自启动设置')
    mode.add_argument('--foreground', action='store_true', help='前台调试，不登记自启动')
    mode.add_argument('--disable-autostart', action='store_true', help='取消登录自启动')
    mode.add_argument('--autostart', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--no-autostart', action='store_true', help='本次启动不登记或修改自启动项')
    args = parser.parse_args(argv)
    try:
        if args.disable_autostart:
            disable_autostart()
            return 0
        state = args.state.expanduser().resolve()
        app_args = ['--state', str(state)]
        if args.preview:
            app_args.append('--preview')
        if args.screen:
            app_args.extend(['--screen', args.screen])
        command = [sys.executable, str(ROOT / 'main.py'), *app_args]
        if args.quit or args.foreground:
            os.execv(sys.executable, [*command, *(['--quit'] if args.quit else [])])
        if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
                or os.environ.get('QT_QPA_PLATFORM') in ('offscreen', 'minimal')):
            raise RuntimeError('当前没有图形桌面会话，请登录桌面后运行 ./run.sh。')

        sys.path.insert(0, str(ROOT))
        from PySide6.QtCore import QCoreApplication
        from garden.app_control import send_command
        app = QCoreApplication([sys.argv[0]])
        existing = send_command(state, 'ping', timeout=200)[0]
        log_path = xdg_path('XDG_STATE_HOME', '.local/state') / 'haruniwa/haruniwa.log'
        if not existing:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
                log_path.replace(log_path.with_suffix('.log.1'))
            with log_path.open('ab') as log:
                child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    if child.returncode == 0 and send_command(state, 'ping', timeout=200)[0]:
                        break  # Another simultaneous launch won the instance lock.
                    raise RuntimeError(f'启动失败（退出码 {child.returncode}），请查看日志：{log_path}')
                if send_command(state, 'ping', timeout=200)[0]:
                    break
                time.sleep(.1)
            else:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                raise RuntimeError(f'启动超时，请查看日志：{log_path}')
            print(f'春庭已在后台启动（PID {child.pid}）。日志：{log_path}')
        else:
            if not args.autostart:
                send_command(state, 'show')
            print('春庭已在运行。')
        if not (args.no_autostart or args.autostart):
            path = register_autostart(app_args)
            print(f'已启用桌面登录自启动：{path}')
        print('可关闭终端；暂停、继续和保存退出请使用顶部状态栏的春庭图标。')
        return 0
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
