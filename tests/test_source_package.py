"""Publication boundaries, with isolated Git fixtures and no external services."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'package_scan', Path(__file__).resolve().parents[1] / 'scripts/scan-source.py')
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], env=self.env)

    def test_index_secret_remains_detected_after_working_copy_is_cleaned(self):
        secret = 'ghp_' + 'aB3dE5fG7hJ9kL2mN4pQ6rS8tU0vW1xY3zA5'
        source = self.root / 'source.txt'
        source.write_text(secret)
        self.git('add', 'source.txt')
        source.write_text('safe working copy')
        result = SCAN.scan(self.root)
        self.assertEqual(result['findings'][0]['kind'], 'github-token')
        self.assertNotIn(secret, str(result))

    def test_history_is_scanned_even_when_current_index_is_safe(self):
        source = self.root / 'source.txt'
        source.write_text('tskey-auth-' + 'abC1-' * 8)
        self.git('add', 'source.txt')
        self.git('commit', '-qm', 'fixture')
        source.write_text('safe')
        self.git('add', 'source.txt')
        self.git('commit', '-qm', 'safe current fixture')
        self.assertEqual(SCAN.scan(self.root)['findings'], [])
        self.assertTrue(SCAN.scan(self.root, history=True)['findings'])

    def test_private_runtime_and_external_symlink_fail_even_without_token_pattern(self):
        (self.root / '.env').write_text('ORBIT_ALLOWED_USERS=user@example.invalid')
        (self.root / 'external').symlink_to('/tmp/not-package-source')
        self.git('add', '.env', 'external')
        kinds = {x['kind'] for x in SCAN.scan(self.root)['findings']}
        self.assertEqual(kinds, {'private-runtime-path', 'external-symlink'})

    def test_git_environment_cannot_redirect_index_scoping(self):
        (self.root / 'source.txt').write_text('safe')
        self.git('add', 'source.txt')
        with patch.dict(os.environ, {'GIT_DIR': '/nonexistent/foreign-repo',
                                     'GIT_WORK_TREE': '/nonexistent/foreign-work'}):
            result = SCAN.scan(self.root)
        self.assertEqual(result['checked'], 1)
        self.assertEqual(result['findings'], [])


if __name__ == '__main__':
    unittest.main()
