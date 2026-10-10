"""Exercise installer control flow with fake package tools; never run real apt/sudo."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='installer test ')
        self.root = Path(self.directory.name)
        self.bin = self.root/'bin'
        self.bin.mkdir()
        self.project = self.root/'project with spaces'
        (self.project/'.venv/bin').mkdir(parents=True)
        shutil.copy(ROOT/'install.sh', self.project/'install.sh')
        shutil.copy(ROOT/'requirements.txt', self.project/'requirements.txt')
        self.log = self.root/'commands.log'
        self.env = {**os.environ, 'PATH': str(self.bin)+':/usr/bin:/bin', 'INSTALL_TEST_LOG': str(self.log),
                    'XDG_CURRENT_DESKTOP': 'GNOME', 'INSTALL_TEST_MISSING': 'libxcb-cursor0'}
        self.script(self.bin/'dpkg-query', '''
if [[ "${@: -1}" == "$INSTALL_TEST_MISSING" ]]; then exit 1; fi
printf 'install ok installed'
''')
        self.script(self.bin/'apt-get', '''
printf 'apt-get %s\\n' "$*" >> "$INSTALL_TEST_LOG"
exit "${INSTALL_TEST_APT_EXIT:-0}"
''')
        self.script(self.bin/'sudo', 'exec "$@"\n')
        self.script(self.bin/'python3', 'exit 0\n')
        self.script(self.project/'.venv/bin/python', '''
printf 'venv-python %s\\n' "$*" >> "$INSTALL_TEST_LOG"
if [[ "$1" == '-' ]]; then cat >/dev/null; fi
exit 0
''')

    def tearDown(self):
        self.directory.cleanup()

    def script(self, path, source):
        path.write_text('#!/bin/bash\nset -eu\n'+source)
        path.chmod(0o755)

    def install(self, *args):
        return subprocess.run(['bash', str(self.project/'install.sh'), '--no-start', *args],
                              env=self.env, cwd=self.root, capture_output=True, text=True, timeout=10)

    def test_missing_xcb_cursor_is_installed_and_repeated_install_skips_apt(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.log.read_text()
        self.assertIn('apt-get install -y libxcb-cursor0\n', commands)
        self.assertIn('venv-python -m pip install -r '+str(self.project/'requirements.txt'), commands)
        self.env['INSTALL_TEST_MISSING'] = ''
        self.log.unlink()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('apt-get', self.log.read_text())

    def test_package_failure_stops_before_pip_and_start(self):
        self.env['INSTALL_TEST_APT_EXIT'] = '42'
        result = self.install()
        self.assertEqual(result.returncode, 42)
        self.assertNotIn('venv-python', self.log.read_text())

    def test_skip_system_never_invokes_apt(self):
        result = self.install('--skip-system')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('apt-get', self.log.read_text())
