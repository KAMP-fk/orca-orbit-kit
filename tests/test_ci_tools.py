"""Exercise relocated CI tooling with fixture Docker/act, never a real container."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/ci/concafe-act-validate.sh'
LEGACY_SCRIPT = ROOT / 'concafe-act-validate.sh'
FIXTURE = '''#!/usr/bin/env python3
import json, os
from pathlib import Path
import sys
name = Path(sys.argv[0]).name
with Path(os.environ['CI_TOOL_LOG']).open('a') as stream:
    stream.write(json.dumps({'command': name, 'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
if name == 'docker':
    if sys.argv[1:] == ['info']:
        sys.exit(int(os.environ.get('CI_TOOL_DOCKER_RC', '0')))
    if sys.argv[1:3] == ['image', 'inspect']:
        sys.exit(1)
    if sys.argv[1] != 'build':
        sys.exit(99)
else:
    sys.exit(int(os.environ.get('CI_TOOL_ACT_RC', '0')))
'''


class CIToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / 'checkout with spaces'
        workflow = self.repo / '.github/workflows/ci.yml'
        workflow.parent.mkdir(parents=True)
        workflow.write_text('name: fixture\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for command in ('docker', 'act'):
            executable = self.bin / command
            executable.write_text(FIXTURE)
            executable.chmod(0o755)
        self.log = self.root / 'calls.jsonl'
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                                CI_TOOL_LOG=str(self.log))

    def run_script(self, script=SCRIPT, mode='--dry-run'):
        return subprocess.run([str(script), str(self.repo), mode], cwd=self.root,
                              env=self.environment, text=True, capture_output=True, timeout=10)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_canonical_and_legacy_paths_use_the_same_scoped_build_context_and_checkout(self):
        receipts = []
        for script in (SCRIPT, LEGACY_SCRIPT):
            result = self.run_script(script)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = self.calls()
            self.assertEqual([row['command'] for row in calls], ['docker', 'docker', 'docker', 'act'])
            build = calls[2]['argv']
            dockerfile = Path(build[build.index('-f') + 1])
            context = Path(build[-1])
            self.assertEqual(dockerfile, SCRIPT.parent / 'CONCAFE-ACT.Dockerfile')
            self.assertEqual(context, SCRIPT.parent)
            self.assertTrue(dockerfile.is_file())
            self.assertEqual(Path(calls[3]['cwd']), self.repo.resolve())
            self.assertIn('-n', calls[3]['argv'])
            for option in ('--secret-file', '--env-file', '--var-file'):
                self.assertEqual(calls[3]['argv'][calls[3]['argv'].index(option) + 1], '/dev/null')
            self.assertEqual(calls[3]['argv'][calls[3]['argv'].index('--container-daemon-socket') + 1], '-')
            receipts.append(calls)
            self.log.unlink()
        self.assertEqual(receipts[0], receipts[1])

    def test_invalid_usage_and_unavailable_docker_never_invoke_act(self):
        result = self.run_script(mode='--unknown')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())
        self.environment['CI_TOOL_DOCKER_RC'] = '1'
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertEqual([row['command'] for row in self.calls()], ['docker'])

    def test_act_exit_code_is_preserved_in_both_entry_paths(self):
        self.environment['CI_TOOL_ACT_RC'] = '7'
        for script in (SCRIPT, LEGACY_SCRIPT):
            self.assertEqual(self.run_script(script, mode='').returncode, 7)
        self.assertNotIn('-n', self.calls()[-1]['argv'])


if __name__ == '__main__':
    unittest.main()
