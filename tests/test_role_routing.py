"""Orca role routing and Peach task checks; no hosted/model calls."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_named_task_sessions

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import role_contract
import task_session


class RoutingTests(unittest.TestCase):
    def test_selected_orca_build_is_never_replaced_when_missing(self):
        cases = [({'ORCA_CLI_COMMAND': '/missing/custom-orca'}, 'linux', '/missing/custom-orca'),
                 ({'ORCA_DEV_REPO_ROOT': '/fixture/dev'}, 'darwin', 'orca-dev'),
                 ({}, 'linux', 'orca-ide'), ({}, 'darwin', 'orca')]
        for env, platform, expected in cases:
            with self.subTest(env=env, platform=platform), mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(role_contract.sys, 'platform', platform), \
                 mock.patch.object(role_contract.shutil, 'which', return_value=None):
                self.assertEqual(role_contract.orca_command(), expected)

    def test_workspace_check_uses_selected_cli_and_does_not_create_or_launch(self):
        import importlib.machinery
        loader = importlib.machinery.SourceFileLoader('workspace_checker', str(PACKAGE / 'bin/start-workspaces'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec);loader.exec_module(module)
        rows = [{'displayName': name, 'path': str(role_contract.workspace_root(role)), 'id': role + '::/fixture/' + role} for role, name in role_contract.NAMES.items() if role in role_contract.HOME_ROLES]
        calls = []
        def invoke(argv, **kwargs):
            calls.append(argv)
            if argv[1:3] == ['repo', 'list']:
                result = {'repos': [{'id': 'skills-repo', 'path': str(module.FOLDER)}]}
            elif argv[1:3] == ['worktree', 'list']:
                result = {'worktrees': rows}
            elif argv[1:3] == ['terminal', 'list']:
                result = {'terminals': []}
            else:
                raise AssertionError('Mutation/launch during check: ' + repr(argv))
            return subprocess.CompletedProcess(argv, 0, json.dumps({'ok': True, 'result': result}), '')
        with mock.patch.dict(os.environ, {'ORCA_CLI_COMMAND': '/fixture/orca'}, clear=True), \
             mock.patch.object(sys, 'argv', ['start-workspaces', '--check']), \
             mock.patch.object(module.subprocess, 'run', side_effect=invoke), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            module.main()
        self.assertEqual(len(output.getvalue().splitlines()), 3)
        self.assertTrue(all(call[0] == '/fixture/orca' for call in calls))


class PeachTaskTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_named_task_sessions.TaskSessionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.env = self.fixture.env
        self.reviewer = PACKAGE.parent / 'linear-inreview-reviewer/bin/linear-inreview-reviewer'

    def preview(self, *args):
        return subprocess.run([str(self.reviewer), '--dry-run', *args], env=self.env,
                              text=True, capture_output=True, timeout=15)

    def test_wrapper_preserves_review_options_and_dry_run_has_no_service_or_model_calls(self):
        result = self.preview('CAF-123', '--pr', 'owner/repo#123', '--test-check', 'CI / unit tests')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['argv'], [str(self.reviewer), 'CAF-123', '--pr', 'owner/repo#123',
                                        '--test-check', 'CI / unit tests'])
        self.assertEqual(data['taskWorkspace'], None)
        self.assertFalse(data['startsSession'])
        self.assertFalse(self.fixture.fixture.log.exists())
        self.assertFalse(self.fixture.state.exists())

    def test_invalid_selector_or_remote_context_does_not_start_a_task(self):
        result = self.preview('--worktree', 'path:relative', 'CAF-123')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.env['ORCA_PAIRING_CODE'] = 'remote'
        result = self.preview('CAF-123')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.fixture.state.exists())

    def test_stdout_collector_keeps_issue_report_and_nonzero_verdict_before_close(self):
        for rc in (0, 1, 3):
            with self.subTest(rc=rc), mock.patch.dict(os.environ, self.env, clear=True), \
                 contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                command = [sys.executable, '-c', "print('Issue: CAF-123\\nVerdict: ' + " +
                           repr({0: 'PASS', 1: 'CHANGES_REQUIRED', 3: 'BLOCKED'}[rc]) +
                           "); raise SystemExit(" + str(rc) + ")"]
                actual = task_session.launch_task('peach', command, self.fixture.fixture.workspace,
                                                  {}, self.env['ORCA_CLI_COMMAND'], collector='stdout')
                self.assertEqual(actual, rc)
                run = self.fixture.run_dir()
                self.assertIn('Issue: CAF-123', (run / 'result.txt').read_text())
                self.assertIn('Issue: CAF-123', output.getvalue())
                self.assertTrue((run / 'closed.json').is_file())
                self.assertEqual(json.loads((run / 'request.json').read_text())['worktreeId'], 'fixture-workspace')

    def test_missing_final_report_is_blocked_and_not_returned_as_success(self):
        with mock.patch.dict(os.environ, self.env, clear=True), \
             contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            actual = task_session.launch_task('peach', [sys.executable, '-c', "print('partial progress')"],
                                              self.fixture.fixture.workspace, {},
                                              self.env['ORCA_CLI_COMMAND'], collector='stdout')
        self.assertEqual(actual, 3)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('BLOCKED', (self.fixture.run_dir() / 'error.txt').read_text())

    def test_rejected_draft_pass_is_only_progress_and_last_blocked_report_is_returned(self):
        command = [sys.executable, '-c', "print('Issue: CAF-123\\nVerdict: PASS\\n\\nIssue: CAF-123\\nVerdict: BLOCKED'); raise SystemExit(3)"]
        with mock.patch.dict(os.environ, self.env, clear=True), \
             contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            actual = task_session.launch_task('peach', command, self.fixture.fixture.workspace,
                                              {}, self.env['ORCA_CLI_COMMAND'], collector='stdout')
        self.assertEqual(actual, 3)
        self.assertNotIn('Verdict: PASS', output.getvalue())
        self.assertIn('Verdict: BLOCKED', (self.fixture.run_dir() / 'result.txt').read_text())
        self.assertIn('Verdict: PASS', (self.fixture.run_dir() / 'progress.log').read_text())


if __name__ == '__main__':
    unittest.main()
