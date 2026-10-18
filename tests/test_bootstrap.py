"""Check bootstrap's shared interpreter setup without downloading dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def exercise_bootstrap(self, launcher="working"):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            tools = directory / 'tools'
            tools.mkdir()
            runtime = directory / 'runtime'
            python_store = runtime / 'python'
            python_store.mkdir(parents=True)
            marker = python_store / 'retained-interpreter'
            marker.write_text('must survive virtual environment recreation')
            uv = tools / 'uv'
            uv.write_text(f'#!{sys.executable}\n' + '''
import os
from pathlib import Path
import sys
import shutil
assert os.environ['UV_PYTHON_PREFERENCE'] == 'only-managed'
if sys.argv[1] == 'venv':
    assert '--clear' in sys.argv
    assert sys.argv[sys.argv.index('--python') + 1] == '3.15'
    runtime = Path(sys.argv[-1])
    store = Path(os.environ['UV_PYTHON_INSTALL_DIR'])
    assert store == runtime.parent / 'python'
    if runtime.exists():
        shutil.rmtree(runtime)
    store.mkdir(exist_ok=True)
    python = store / 'python3.15'
    python.write_text('#!/bin/sh\\nexit 0\\n')
    python.chmod(0o700)
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'bin/python').symlink_to(python)
    galaxy = runtime / 'bin/ansible-galaxy'
    galaxy.write_text('#!/bin/sh\\nexit 0\\n')
    galaxy.chmod(0o700)
    launcher = runtime / 'bin/ansible-pull'
    mode = os.environ['BOOTSTRAP_TEST_LAUNCHER']
    if mode == 'working':
        launcher.write_bytes(galaxy.read_bytes())
        launcher.chmod(0o700)
    elif mode == 'broken':
        launcher.write_bytes(b'#!/nonexistent-bootstrap-test-python\\n')
        launcher.chmod(0o700)
else:
    assert sys.argv[1] == 'pip'
''')
            uv.chmod(0o755)
            result = subprocess.run(
                ['bash', '-c', 'umask 077; exec bash "$1" "$2"',
                 'bootstrap-test', str(ROOT / 'scripts/bootstrap.sh'), str(runtime)],
                env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                         BOOTSTRAP_TEST_LAUNCHER=launcher),
                text=True, capture_output=True)
            self.assertTrue(marker.is_file(), 'Rebuilding the venv deleted its Python store')
            if launcher != 'working':
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Bootstrap failed:', result.stderr)
                self.assertNotIn('Environment ready:', result.stdout)
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for path in [runtime, runtime / 'venv/bin', runtime / 'venv/bin/ansible-galaxy',
                         runtime / 'python', (runtime / 'venv/bin/python').resolve()]:
                self.assertEqual(path.stat().st_mode & 0o005, 0o005, str(path))

    def test_uv_runtime_uses_shared_python_with_readable_permissions(self):
        self.exercise_bootstrap()

    def test_missing_launcher_fails_bootstrap(self):
        self.exercise_bootstrap('missing')

    def test_missing_shebang_interpreter_fails_bootstrap(self):
        self.exercise_bootstrap('broken')
