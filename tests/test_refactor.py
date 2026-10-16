"""Behavior checks; no target host changes or Docker daemon required."""
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = yaml.safe_load((ROOT / 'roles/docker/defaults/main.yml').read_text())
CATALOG = DEFAULTS['docker_service_catalog']


def run(*args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


class ComposeTests(unittest.TestCase):
    def test_every_compose_template_is_valid(self):
        self.assertIsNotNone(shutil.which('docker'), 'Docker CLI with Compose is required')
        env = Environment(undefined=StrictUndefined)
        variables = dict(DEFAULTS, username='fixture', managed_user_home='/srv/fixture',
                         media_path='/srv/media', pki_path='/srv/pki',
                         managed_user_uid=1234, managed_user_gid=5678,
                         docker_path='/srv/fixture/docker', domain='fixture.lan',
                         public_domain='fixture.example')
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            shutil.copy(ROOT / 'tests/fixtures/compose.env', directory / '.env')
            for name, service in CATALOG.items():
                with self.subTest(service=name):
                    source = ROOT / 'roles/docker/templates' / service['template']
                    rendered = env.from_string(source.read_text()).render(**variables)
                    path = directory / 'docker-compose.yml'
                    path.write_text(rendered)
                    result = run('docker', 'compose', '--project-directory', str(directory),
                                 '-f', str(path), 'config', '--quiet')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    if name in ['plex', 'syncthing', 'qbittorrent']:
                        self.assertIn('PUID=1234', rendered)
                        self.assertIn('PGID=5678', rendered)

    def test_desktop_startup_omits_unselected_apps(self):
        env = Environment(undefined=StrictUndefined)
        for desktop in ['i3', 'labwc']:
            filename = 'config' if desktop == 'i3' else 'autostart'
            source = ROOT / f'roles/gui/templates/.config/{desktop}/{filename}.j2'
            rendered = env.from_string(source.read_text()).render(gui_components=[], base_components=[])
            active_lines = '\n'.join(line for line in rendered.splitlines()
                                     if not line.lstrip().startswith('#'))
            self.assertNotIn('firefox', active_lines)
            self.assertNotIn('alacritty', active_lines)
            self.assertNotIn('udiskie', active_lines)
            self.assertNotIn('pactl', active_lines)


class CatalogTests(unittest.TestCase):
    def test_catalog_order_and_template_coverage(self):
        order = DEFAULTS['docker_service_order']
        self.assertEqual(set(order), set(CATALOG))
        self.assertEqual(len(order), len(set(order)))
        self.assertEqual(len(CATALOG), len({v['directory'] for v in CATALOG.values()}))
        self.assertEqual(len(CATALOG), len({v['tag'] for v in CATALOG.values()}))
        for name, entry in CATALOG.items():
            self.assertTrue((ROOT / 'roles/docker/templates' / entry['template']).is_file())
            self.assertTrue(set(entry['requires']) <= set(order[:order.index(name)]))

    def test_ansible_dependency_validation(self):
        executable = shutil.which('ansible-playbook')
        self.assertIsNotNone(executable, 'ansible-playbook is required')
        play = [{'hosts': 'localhost', 'gather_facts': False,
                 'vars_files': [str(ROOT / 'roles/docker/defaults/main.yml')],
                 'tasks': [{'ansible.builtin.import_tasks': str(ROOT / 'roles/docker/tasks/validate.yml')}]}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'validate.yml'
            path.write_text(yaml.safe_dump(play))
            cases = [([], True), (['step-ca'], True),
                     (DEFAULTS['docker_service_order'], True),
                     (['traefik'], False), (['step-ca', 'vaultwarden'], False),
                     (['unsupported'], False)]
            for selected, valid in cases:
                with self.subTest(selected=selected):
                    result = run(executable, '-i', 'localhost,', '-c', 'local', str(path),
                                 '-e', json.dumps({'docker_services': selected, 'docker_selected': selected}),
                                 cwd=ROOT)
                    self.assertEqual(result.returncode == 0, valid, result.stdout + result.stderr)


# Fake package dependency graph exercises the actual cleanup helper without
# invoking the machine's package manager. Mutations are retained across calls.
FAKE_PACMAN = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
state = Path(os.environ['PACKAGE_STATE'])
packages = json.loads(state.read_text())
args = sys.argv[1:]
if args == ['-Qq']:
    print('\\n'.join(packages))
elif args == ['-Qqt']:
    if os.environ.get('QUERY_FAIL'):
        sys.exit(7)
    leaves = [p for p in packages if not any(p in deps for deps in packages.values())]
    if leaves:
        print('\\n'.join(leaves))
    else:
        sys.exit(1)
elif args[:2] == ['-R', '--noconfirm']:
    name = args[2]
    if os.environ.get('REMOVE_FAIL'):
        sys.exit(9)
    assert not any(name in deps for deps in packages.values())
    del packages[name]
    state.write_text(json.dumps(packages))
else:
    sys.exit(2)
'''


class CleanupTests(unittest.TestCase):
    def exercise(self, packages, candidates, protected=(), mode='apply', **extra_env):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            pacman = directory / 'pacman'
            pacman.write_text(FAKE_PACMAN)
            pacman.chmod(0o755)
            state = directory / 'packages.json'
            state.write_text(json.dumps(packages))
            environment = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'],
                               PACKAGE_STATE=str(state), **extra_env)
            arguments = list(itertools.chain.from_iterable(('--protect', p) for p in protected))
            arguments += list(itertools.chain.from_iterable(('--candidate', p) for p in candidates))
            result = run('bash', str(ROOT / 'roles/package_cleanup/files/prune-packages.sh'),
                         mode, *arguments, env=environment)
            return result, json.loads(state.read_text())

    def test_removes_dependency_chain_regardless_of_candidate_order(self):
        result, remaining = self.exercise({'app': ['library'], 'library': []}, ['library', 'app'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(remaining, {})
        self.assertIn('removed library', result.stdout)

    def test_shared_and_explicitly_protected_packages_survive(self):
        result, remaining = self.exercise(
            {'i3': ['ttf-hack'], 'alacritty': ['ttf-hack'], 'ttf-hack': [], 'protected': []},
            ['alacritty', 'ttf-hack', 'protected'], ['ttf-hack', 'protected'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(remaining), {'i3', 'ttf-hack', 'protected'})

    def test_reverse_dependencies_are_preserved_without_explicit_protection(self):
        result, remaining = self.exercise({'i3': ['ttf-hack'], 'ttf-hack': []}, ['ttf-hack'])
        self.assertEqual(result.returncode, 0)
        self.assertIn('ttf-hack', remaining)

    def test_check_mode_reports_changes_without_removing_packages(self):
        result, remaining = self.exercise({'app': []}, ['app'], mode='check')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(remaining, {'app': []})
        self.assertIn('would remove app', result.stdout)

    def test_already_removed_packages_are_unchanged(self):
        result, remaining = self.exercise({'other': []}, ['absent'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertEqual(remaining, {'other': []})

    def test_query_and_removal_errors_fail(self):
        for environment in [{'QUERY_FAIL': '1'}, {'REMOVE_FAIL': '1'}]:
            result, remaining = self.exercise({'app': []}, ['app'], **environment)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('app', remaining)


class PlaybookTests(unittest.TestCase):
    def test_purge_playbook_only_loads_purge_tasks(self):
        result = run('ansible-playbook', str(ROOT / 'purge.yml'), '--list-tasks', cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Purge explicitly selected GUI user data', result.stdout)
        self.assertIn('Purge explicitly selected Docker service data', result.stdout)
        self.assertNotIn('Install selected desktop', result.stdout)
        self.assertNotIn('Install Docker', result.stdout)
        self.assertNotIn('Launch', result.stdout)

    def test_docker_tags_reach_only_requested_deployments(self):
        # Stub only leaf operations; execute the real catalog, dependency checks,
        # dispatch loop and nested includes. No Docker or host changes occur.
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            tasks = directory / 'roles/docker/tasks'
            tasks.mkdir(parents=True)
            for name in ['main.yml', 'validate.yml', 'deploy.yml']:
                shutil.copy(ROOT / 'roles/docker/tasks' / name, tasks / name)
            for name in ['service.yml', 'step-ca.yml', 'traefik.yml']:
                (tasks / name).write_text(yaml.safe_dump([
                    {'name': 'Record deployment', 'ansible.builtin.debug':
                     {'msg': 'DEPLOY_SERVICE={{ docker_service }}'}}]))
            for name in ['install.yml', 'remove.yml']:
                (tasks / name).write_text('---\n[]\n')
            identity = directory / 'roles/user_identity/tasks'
            identity.mkdir(parents=True)
            (identity / 'main.yml').write_text('---\n[]\n')
            playbook = directory / 'tags.yml'
            playbook.write_text(yaml.safe_dump([
                {'hosts': 'localhost', 'gather_facts': False,
                 'vars_files': [str(ROOT / 'roles/docker/defaults/main.yml')],
                 'roles': [{'role': 'docker', 'tags': 'docker'}]}]))
            for tag, expected in [('qb', ['qbittorrent']), ('vw', ['vaultwarden']),
                                  ('traefik', ['traefik']), ('step-ca', ['step-ca']),
                                  ('docker', list(CATALOG))]:
                with self.subTest(tag=tag):
                    result = run('ansible-playbook', '-i', 'localhost,', '-c', 'local',
                                 str(playbook), '--tags', tag, cwd=ROOT)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    for service in CATALOG:
                        self.assertEqual(f'DEPLOY_SERVICE={service}' in result.stdout,
                                         service in expected, result.stdout)

    def test_purge_requires_disabled_targets_and_check_mode_retains_data(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            home = directory / 'home'
            profile = home / '.mozilla'
            profile.mkdir(parents=True)
            sentinel = profile / 'sentinel'
            sentinel.write_text('retain during check mode')
            inventory = directory / 'inventory'
            inventory.write_text('[local]\nfixture ansible_connection=local\n')
            variables = {'ansible_become': False, 'ansible_python_interpreter': sys.executable,
                         'managed_user_home': str(home), 'desktop': 'none',
                         'docker_services': [], 'docker_enabled': False,
                         'gui_components': [], 'purge_gui_targets': ['firefox']}
            result = run('ansible-playbook', '-i', str(inventory), str(ROOT / 'purge.yml'),
                         '--check', '-e', json.dumps(variables), cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(sentinel.is_file())
            variables['gui_components'] = ['firefox']
            result = run('ansible-playbook', '-i', str(inventory), str(ROOT / 'purge.yml'),
                         '--check', '-e', json.dumps(variables), cwd=ROOT)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Disable targets with local.yml', result.stdout)
            self.assertTrue(sentinel.is_file())


if __name__ == '__main__':
    unittest.main()
