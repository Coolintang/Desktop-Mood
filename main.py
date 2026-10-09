"""Run the wallpaper, preview it, or ask the matching instance to quit safely."""
import argparse
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from garden.app_control import LocalControl, SignalExitBridge, send_command


def main(argv=None):
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="春庭 · Haruniwa 动态桌面壁纸")
    parser.add_argument('--preview', action='store_true', help='在普通可交互窗口预览（适用于 Wayland）')
    parser.add_argument('--state', type=Path, default=root / 'data/state.json', help='指定独立 JSON 存档路径')
    parser.add_argument('--screen', help='显示器名称（也可通过系统托盘切换）')
    parser.add_argument('--quit', action='store_true', help='通知当前显示会话中使用此存档的实例保存并退出')
    args = parser.parse_args(argv)
    state_path = args.state.expanduser().resolve()
    if args.quit:
        app = QCoreApplication([sys.argv[0]])
        ok, message, _ = send_command(state_path, 'quit')
        if ok:
            print('已通知春庭保存并退出。')
            return 0
        print('未找到可响应的春庭实例：' + message, file=sys.stderr)
        return 1

    from PySide6.QtWidgets import QApplication
    from garden.window import PondWindow
    app = QApplication([sys.argv[0]])
    app.setApplicationName('Haruniwa')
    app.setQuitOnLastWindowClosed(False)
    control = LocalControl(state_path, app)
    window = None
    try:
        if not control.start(lambda: window.request_exit(), lambda: window.show_controls()):
            print('春庭已在运行，已显示控制面板。')
            return 0
        if app.platformName().startswith('wayland') and not args.preview:
            print('提示：Wayland 合成器可能限制桌面层和鼠标穿透；可使用 --preview 普通窗口模式。', file=sys.stderr)
        window = PondWindow(state_path, preview=args.preview, screen_name=args.screen)
        bridge = SignalExitBridge(window.request_exit, app)
        app.aboutToQuit.connect(bridge.close)
        app.aboutToQuit.connect(control.close)
        window.show_layers()
        try:
            return app.exec()
        finally:
            window.shutdown()
            bridge.close()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        control.close()


if __name__ == '__main__':
    raise SystemExit(main())
