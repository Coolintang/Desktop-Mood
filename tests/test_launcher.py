"""Exercise deployment against temporary XDG dirs and child processes only."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from garden import launcher

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='庭院 launcher ')
        self.root = Path(self.directory.name)
        self.state = self.root/'独立 state.json'
        self.config = self.root/'config'
        self.logs = self.root/'logs'
        self.env = {**os.environ, 'XDG_CONFIG_HOME': str(self.config), 'XDG_STATE_HOME': str(self.logs),
                    'QT_QPA_PLATFORM': 'offscreen'}
        self.pids = []

    def tearDown(self):
        if self.pids:
            self.run_cli('--quit')
            for pid in self.pids:
                status = Path(f'/proc/{pid}/stat')
                for _ in range(50):
                    if not status.exists() or status.read_text().split(') ', 1)[1].startswith('Z'):
                        break
                    time.sleep(.1)
                else:
                    os.kill(pid, signal.SIGTERM)  # Only the child PID returned by this test's launcher.
        self.directory.cleanup()

    def run_cli(self, *args, env=None):
        return subprocess.run([str(ROOT/'run.sh'), '--state', str(self.state), *args], cwd=self.root,
                              env=env or self.env, capture_output=True, text=True, timeout=25)

    def start(self, *args):
        result = self.run_cli('--preview', *args)
        match = re.search(r'PID (\d+)', result.stdout)
        if match:
            self.pids.append(int(match[1]))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def test_detach_duplicate_quit_and_autostart_lifecycle(self):
        self.start()
        pid = self.pids[0]
        self.assertEqual(os.getsid(pid), pid)
        self.assertEqual(os.readlink(f'/proc/{pid}/fd/0'), '/dev/null')
        self.assertEqual(os.readlink(f'/proc/{pid}/fd/1'), str(self.logs/'haruniwa/haruniwa.log'))
        path = self.config/'autostart/haruniwa.desktop'
        content = path.read_text()
        self.assertIn('Terminal=false', content)
        self.assertIn(str(self.state), content)
        self.assertIn('--preview', content)
        duplicate = self.start()
        self.assertIn('已在运行', duplicate.stdout)
        self.assertEqual(len(self.pids), 1)
        self.assertEqual(path.read_text(), content)
        self.assertEqual(self.run_cli('--quit').returncode, 0)
        self.assertTrue(path.exists())  # Exiting does not disable the next login.
        for _ in range(50):
            if self.state.exists():
                break
            time.sleep(.1)
        self.assertTrue(self.state.exists())
        disabled = self.run_cli('--disable-autostart')
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertFalse(path.exists())

    def test_no_autostart_and_help_do_not_register(self):
        self.assertEqual(self.run_cli('--help').returncode, 0)
        self.assertFalse(self.config.exists())
        self.start('--no-autostart')
        self.assertFalse(self.config.exists())

    def test_missing_quit_and_bad_arguments_do_not_register(self):
        result = self.run_cli('--quit')
        self.assertNotEqual(result.returncode, 0)
        result = self.run_cli('--not-a-real-option')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.state.exists())

    def test_failed_child_start_does_not_register(self):
        # An isolated checkout with a deterministic failed app, no Qt abort/core dump.
        project = self.root/'failed project'
        (project/'garden').mkdir(parents=True)
        shutil.copy(ROOT/'garden/launcher.py', project/'garden/launcher.py')
        (project/'garden/__init__.py').touch()
        shutil.copy(ROOT/'garden/app_control.py', project/'garden/app_control.py')
        (project/'main.py').write_text('raise SystemExit(7)\n')
        result = subprocess.run([sys.executable, str(project/'garden/launcher.py')], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('退出码 7', result.stderr)
        self.assertFalse(self.config.exists())

    def test_autostart_quotes_and_preserves_manual_entry(self):
        with patch.dict(os.environ, self.env):
            weird = '/tmp/庭院 space "quotes" $cash `literal` \\ %f.json'
            path = launcher.register_autostart(['--state', weird])
            self.assertIn('%%f.json', path.read_text())
            # Use GLib's real desktop parser/launcher to verify argument escaping.
            check = subprocess.run(['/usr/bin/python3', '-c', 'from gi.repository import Gio'],
                                   capture_output=True)
            if check.returncode == 0:
                capture = self.root/'capture.py'
                output = self.root/'captured.json'
                capture.write_text('import json, sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n')
                command = ' '.join(launcher.desktop_arg(arg) for arg in [sys.executable, capture, output, weird])
                path.write_text('[Desktop Entry]\nType=Application\nName=Test\nExec='+command+'\n')
                code = 'from gi.repository import Gio\nimport sys\nGio.DesktopAppInfo.new_from_filename(sys.argv[1]).launch([], None)\n'
                result = subprocess.run(['/usr/bin/python3', '-c', code, str(path)], env=self.env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                for _ in range(50):
                    if output.exists():
                        break
                    time.sleep(.02)
                self.assertEqual(json.loads(output.read_text()), [weird])
            path.write_text('[Desktop Entry]\nName=User entry\n')
            with self.assertRaises(OSError):
                launcher.register_autostart([])
            with self.assertRaises(OSError):
                launcher.disable_autostart()
            self.assertIn('User entry', path.read_text())
