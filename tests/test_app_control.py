"""Exercise only child processes and temporary state files; never signal other apps."""
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QDir
from PySide6.QtWidgets import QApplication
from garden.app_control import LocalControl, endpoint_name, send_command

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class AppControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name) / 'state.json'
        self.children = []
        self.env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
        self.real_state = ROOT / 'data/state.json'
        self.original = self.real_state.read_bytes() if self.real_state.exists() else None

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()  # Only this test's own failed child, never a discovered PID.
                    child.communicate(timeout=5)
            else:
                child.communicate()
        self.assertEqual(self.real_state.read_bytes() if self.real_state.exists() else None, self.original)
        self.directory.cleanup()

    def launch(self, paused=False):
        if paused:
            code = '''
import sys
from PySide6.QtCore import QTimer
from garden.window import PondWindow
original = PondWindow.__init__
def init(self, *args, **kwargs):
    original(self, *args, **kwargs)
    self.set_running(False)
    self.state.water_quality = 67
    QTimer.singleShot(0, lambda: print('PAUSED_READY', flush=True))
PondWindow.__init__ = init
from main import main
raise SystemExit(main(sys.argv[1:]))
'''
            command = [PYTHON, '-c', code, '--state', str(self.state)]
        else:
            command = [PYTHON, str(ROOT / 'main.py'), '--state', str(self.state)]
        child = subprocess.Popen(command, cwd=ROOT, env=self.env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        if paused:
            ready, _, _ = select.select([child.stdout], [], [], 8)
            self.assertTrue(ready, 'paused child did not start')
            self.assertEqual(child.stdout.readline().strip(), 'PAUSED_READY')
        else:
            for _ in range(50):
                if child.poll() is not None:
                    self.fail('child failed: ' + child.stderr.read())
                if send_command(self.state, 'show', timeout=100)[0]:
                    break
                time.sleep(.05)
            else:
                self.fail('child did not start local server')
        return child

    def cli(self, *args):
        # A quit request must not initialize a GUI platform connection.
        env = {**self.env, 'QT_QPA_PLATFORM': 'nonexistent-test-platform'}
        return subprocess.run([PYTHON, str(ROOT / 'main.py'), '--state', str(self.state), *args],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=5)

    def test_missing_quit_is_nonzero_and_creates_no_state(self):
        result = self.cli('--quit')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('未找到', result.stderr)
        self.assertFalse(self.state.exists())

    def test_real_main_quit_and_duplicate_start(self):
        child = self.launch()
        # A long-running wallpaper must retain its instance lock, even when old.
        lock_path = Path(QDir.tempPath()) / (endpoint_name(self.state) + '.lock')
        original_lock = lock_path.read_bytes()
        os.utime(lock_path, (time.time()-120, time.time()-120))
        duplicate = subprocess.run([PYTHON, str(ROOT / 'main.py'), '--state', str(self.state)],
                                   cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertIn('已在运行', duplicate.stdout)
        self.assertEqual(lock_path.read_bytes(), original_lock)
        self.assertIsNone(child.poll())
        result = self.cli('--quit')
        self.assertEqual(result.returncode, 0, result.stderr)
        _, errors = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, errors)
        self.assertTrue(self.state.exists())
        self.assertFalse((Path(QDir.tempPath()) / endpoint_name(self.state)).exists())

    def test_other_state_does_not_exit_target(self):
        child = self.launch()
        other = Path(self.directory.name) / 'other.json'
        self.assertFalse(send_command(other, 'quit', timeout=100)[0])
        self.assertIsNone(child.poll())
        self.assertFalse(other.exists())
        self.assertEqual(self.cli('--quit').returncode, 0)
        child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0)

    def test_paused_sigint_and_sigterm_save_and_exit_zero(self):
        import json
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signum):
                self.state.unlink(missing_ok=True)
                child = self.launch(paused=True)
                started = time.monotonic()
                child.send_signal(signum)
                _, errors = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, errors)
                self.assertLess(time.monotonic() - started, 3)
                self.assertEqual(json.loads(self.state.read_text())['water_quality'], 67)

    def test_proven_stale_socket_can_be_recovered(self):
        path = Path(QDir.tempPath()) / endpoint_name(self.state)
        stale = socket.socket(socket.AF_UNIX)
        try:
            stale.bind(str(path))
        finally:
            stale.close()
        control = LocalControl(self.state)
        try:
            self.assertTrue(control.start(lambda: None, lambda: None))
            self.assertTrue(control.server.isListening())
        finally:
            control.close()
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
