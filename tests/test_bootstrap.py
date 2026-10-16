"""Check bootstrap's shared interpreter setup without downloading dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_uv_runtime_uses_shared_python_with_readable_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            tools = directory / 'tools'
            tools.mkdir()
            runtime = directory / 'runtime'
            uv = tools / 'uv'
            uv.write_text(f'#!{sys.executable}\n' + '''
import os
from pathlib import Path
import sys
assert os.environ['UV_PYTHON_PREFERENCE'] == 'only-managed'
if sys.argv[1] == 'venv':
    assert '--clear' in sys.argv
    runtime = Path(sys.argv[-1])
    store = Path(os.environ['UV_PYTHON_INSTALL_DIR'])
    assert store == Path(str(runtime) + '-python')
    store.mkdir()
    python = store / 'python3.13'
    python.write_text('#!/bin/sh\\nexit 0\\n')
    python.chmod(0o700)
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'bin/python').symlink_to(python)
    galaxy = runtime / 'bin/ansible-galaxy'
    galaxy.write_text('#!/bin/sh\\nexit 0\\n')
    galaxy.chmod(0o700)
else:
    assert sys.argv[1] == 'pip'
''')
            uv.chmod(0o755)
            result = subprocess.run(
                ['bash', '-c', 'umask 077; exec bash "$1" "$2"',
                 'bootstrap-test', str(ROOT / 'scripts/bootstrap.sh'), str(runtime)],
                env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH']),
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for path in [runtime, runtime / 'bin', runtime / 'bin/ansible-galaxy',
                         Path(str(runtime) + '-python'), (runtime / 'bin/python').resolve()]:
                self.assertEqual(path.stat().st_mode & 0o005, 0o005, str(path))
