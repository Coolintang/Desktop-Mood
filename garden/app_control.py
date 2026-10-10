"""Per-user, per-display controls for one resolved state file; no process killing."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal

from PySide6.QtCore import QDir, QLockFile, QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def endpoint_name(state_path):
    identity = [os.getuid(), str(Path(state_path).expanduser().resolve()),
                os.environ.get('DISPLAY', ''), os.environ.get('WAYLAND_DISPLAY', '')]
    digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:32]
    return f'haruniwa-{digest}'


def send_command(state_path, command, timeout=1200):
    """Return (acknowledged, diagnostic, socket error); never remove an endpoint."""
    socket = QLocalSocket()
    socket.connectToServer(endpoint_name(state_path))
    if not socket.waitForConnected(timeout):
        error = socket.error()
        message = socket.errorString()
        socket.abort()
        return False, message, error
    socket.write((command + '\n').encode('ascii'))
    if socket.bytesToWrite() and not socket.waitForBytesWritten(timeout):
        return False, socket.errorString(), socket.error()
    if not socket.bytesAvailable():
        socket.waitForReadyRead(timeout)
    response = bytes(socket.readAll()).strip()
    socket.disconnectFromServer()
    if response == b'ok':
        return True, '', None
    return False, '实例未确认请求，请稍后重试', socket.error()


class LocalControl(QObject):
    """Own the endpoint under a lock; only a proven stale socket is removed."""
    def __init__(self, state_path, parent=None):
        super().__init__(parent)
        self.state_path = Path(state_path).expanduser().resolve()
        self.name = endpoint_name(self.state_path)
        self.lock = QLockFile(str(Path(QDir.tempPath()) / (self.name + '.lock')))
        # This lock lives for the whole desktop session; age alone is not stale.
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self._clients = set()
        self._on_quit = lambda: None
        self._on_show = lambda: None
        self._owns_lock = False

    def start(self, on_quit, on_show):
        """True for this owner; False after notifying an already running owner."""
        self._on_quit, self._on_show = on_quit, on_show
        if not self.lock.tryLock(0):
            if self.lock.error() == QLockFile.PermissionError:
                raise RuntimeError('无法访问实例锁；请检查临时目录权限')
            ok, message, _ = send_command(self.state_path, 'show')
            if ok:
                return False
            raise RuntimeError('此存档的实例可能正在启动或暂未响应：' + message)
        self._owns_lock = True
        # A legacy or independently started server may not have our lock.
        probe = QLocalSocket()
        probe.connectToServer(self.name)
        if probe.waitForConnected(150):
            probe.abort()
            self.close()
            ok, message, _ = send_command(self.state_path, 'show')
            if ok:
                return False
            raise RuntimeError('已有实例未响应：' + message)
        error = probe.error()
        probe.abort()
        if error == QLocalSocket.ConnectionRefusedError:
            # Lock ownership excludes a cooperating startup; refused connection
            # is evidence of a stale socket. Permissions never reach this path.
            if not QLocalServer.removeServer(self.name):
                self.close()
                raise RuntimeError('无法清理已失效的本地控制端点')
        elif error != QLocalSocket.ServerNotFoundError:
            self.close()
            raise RuntimeError('无法访问本地控制端点：' + probe.errorString())
        if not self.server.listen(self.name):
            message = self.server.errorString()
            self.close()
            raise RuntimeError('无法创建本地控制端点：' + message)
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self._clients.add(socket)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(2000)
            socket.readyRead.connect(lambda client=socket: self._read(client))
            socket.disconnected.connect(lambda client=socket: self._discard(client))
            if socket.bytesAvailable():
                self._read(socket)

    def _read(self, socket):
        if socket.bytesAvailable() > 64:
            socket.abort()
            return
        if not socket.canReadLine():
            return
        command = bytes(socket.readLine()).strip()
        callback = {b'quit': self._on_quit, b'show': self._on_show, b'ping': lambda: None}.get(command)
        socket.write(b'ok\n' if callback else b'error\n')
        socket.flush()
        socket.disconnectFromServer()
        if callback:
            QTimer.singleShot(0, callback)

    def _discard(self, socket):
        self._clients.discard(socket)
        socket.deleteLater()

    def close(self):
        self.server.close()
        for socket in list(self._clients):
            socket.abort()
        if self._owns_lock:
            self.lock.unlock()
            self._owns_lock = False


class SignalExitBridge(QObject):
    """Python signal handlers only mark intent; Qt's timer performs shutdown."""
    def __init__(self, request_exit, parent=None):
        super().__init__(parent)
        self._request_exit = request_exit
        self._pending = False
        self._previous = {}
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.signal(signum, self._mark_exit)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(250)

    def _mark_exit(self, signum, frame):
        self._pending = True

    def _poll(self):
        if self._pending:
            self._pending = False
            self._request_exit()

    def close(self):
        self.timer.stop()
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)
        self._previous.clear()
