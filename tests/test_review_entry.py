"""Unified review routing with local Git fixtures and zero model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import review_routing
import project_identity
import role_launch


class ReviewEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-entry-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'fixture with spaces'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.repo / 'source.txt').write_text('fixture\n')
        self.git('add', 'source.txt')
        self.git('commit', '-qm', 'Fixture')
        self.git('remote', 'add', 'origin', 'git@github.com:fixture/repo.git')
        self.sha = self.git('rev-parse', 'HEAD').strip()
        self.prompt = self.root / 'review request.md'
        self.prompt.write_text('Review the fixed change for regressions.\n')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              text=True, capture_output=True).stdout

    def cli(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE')}
        return subprocess.run([sys.executable, str(PACKAGE / 'bin/potato'), *args],
                              text=True, capture_output=True, env=env, timeout=15)

    def test_inbox_needs_no_backend_and_cannot_carry_a_request(self):
        result = self.cli('--inbox')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--kind technical', result.stdout)
        self.assertIn('Potato｜', result.stdout)
        self.assertNotEqual(self.cli('--inbox', '--kind', 'technical').returncode, 0)

    def test_old_review_command_is_the_same_potato_route_without_a_session(self):
        args = ['--kind', 'technical', '--repo', str(self.repo), '--prompt-file', str(self.prompt), '--dry-run']
        current = self.cli(*args)
        old = subprocess.run([sys.executable, str(PACKAGE / 'bin/review'), *args],
                             text=True, capture_output=True, timeout=15)
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertEqual(old.returncode, 0, old.stderr)
        plan = json.loads(current.stdout)
        self.assertEqual(plan, json.loads(old.stdout))
        self.assertEqual(plan['entrypoint'], 'potato')
        self.assertEqual(plan['displayName'], 'Potato')
        self.assertEqual(plan['executorRole'], 'review')
        self.assertFalse(plan['startsSession'])
        self.assertIn('read', plan['argv'])

    def test_acceptance_and_technical_select_exactly_one_route(self):
        acceptance = review_routing.review_plan('acceptance', self.repo, issue='CAF-123')
        technical = review_routing.review_plan('technical', self.repo, prompt_file=self.prompt)
        self.assertEqual(acceptance['route'], 'acceptance')
        self.assertEqual(technical['route'], 'technical')
        self.assertNotIn('potato', acceptance['argv'])
        self.assertNotIn(str(PACKAGE / 'bin/acceptance-task'), technical['argv'])
        self.assertIn('read', technical['argv'])
        self.assertTrue(acceptance['requiresUninvolvedTask'])
        self.assertEqual(acceptance['argv'][-2:], ['--expected-repo', 'fixture/repo'])
        self.assertEqual(technical['executorRole'], 'review')
        self.assertFalse(technical['isFinalVerdict'])

    def test_acceptance_cannot_implicitly_become_fixed_pr_final_review(self):
        with self.assertRaisesRegex(ValueError, '--kind final'):
            review_routing.review_plan('acceptance', self.repo, issue='CAF-123', pr='owner/repo#123')

    def test_missing_scope_request_or_mismatching_sha_blocks_before_launch(self):
        for argv in [[], ['--kind', 'technical'],
                     ['--kind', 'technical', '--repo', str(self.repo)],
                     ['--kind', 'acceptance', '--repo', str(self.repo)],
                     ['--kind', 'final', '--repo', str(self.repo)],
                     ['--kind', 'final', '--repo', str(self.repo), '--sha', 'a' * 40]]:
            self.assertNotEqual(self.cli(*argv).returncode, 0)

    def test_final_is_only_a_handoff_plan_and_never_successful_execution(self):
        args = ['--kind', 'final', '--repo', str(self.repo), '--sha', self.sha]
        actual = self.cli(*args)
        self.assertEqual(actual.returncode, 3, actual.stderr)
        plan = json.loads(actual.stdout)
        self.assertEqual(plan['route'], 'separate-project-task')
        self.assertIsNone(plan['argv'])
        self.assertFalse(plan['startsSession'])
        self.assertFalse(plan['executableHere'])
        self.assertFalse(plan['isFinalVerdict'])
        self.assertTrue(plan['requiresFinalVerdict'])
        self.assertEqual(self.cli(*args, '--dry-run').returncode, 0)

    def test_remote_identity_keeps_concafe_separate_with_latest_opus_pin(self):
        self.git('remote', 'set-url', 'origin', 'git@github.com:KAMP-fk/concafe-techo.git')
        for kind in ('acceptance', 'technical', 'final'):
            options = {'issue': 'CAF-123'} if kind == 'acceptance' else {'prompt_file': self.prompt} if kind == 'technical' else {'sha': self.sha}
            plan = review_routing.review_plan(kind, self.repo, **options)
            self.assertEqual(plan['route'], 'separate-project-task')
            self.assertEqual(plan['requiredModel'], 'claude-opus-5-5')
            self.assertEqual(plan['requiredEffort'], 'high')
            self.assertEqual(plan['requiredBackend'], 'claude')
            self.assertFalse(plan['executableHere'])
            self.assertIsNone(plan['argv'])

    def test_concafe_worktree_is_recognized_even_if_renamed(self):
        self.git('remote', 'set-url', 'origin', 'https://github.com/KAMP-fk/concafe-techo.git')
        worktree = self.root / 'unrelated-task-name'
        self.git('worktree', 'add', '--detach', str(worktree), self.sha)
        self.assertTrue(review_routing.is_concafe_path(worktree))

    def test_direct_review_cannot_bypass_concafe_route_by_omitting_repo_option(self):
        self.git('remote', 'set-url', 'origin', 'git@github.com:KAMP-fk/concafe-techo.git')
        with self.assertRaisesRegex(ValueError, '別タスク'):
            role_launch.launch_spec('review', self.repo, 'Review', batch=True, dry_run=True)


    def test_dry_run_technical_has_no_orca_model_or_task_state(self):
        with mock.patch.object(project_identity, 'git_process', wraps=project_identity.git_process) as git:
            plan = review_routing.review_plan('technical', self.repo, prompt_file=self.prompt)
        self.assertFalse(plan['startsSession'])
        self.assertTrue(all(call.args[0].endswith('/git') for call in git.call_args_list))
        result = self.cli('--kind', 'technical', '--repo', str(self.repo),
                          '--prompt-file', str(self.prompt), '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['route'], 'technical')

    def test_unused_options_are_rejected_instead_of_losing_the_request(self):
        for kind, options in [('technical', {'issue': 'CAF-123', 'prompt_file': self.prompt}),
                              ('technical', {'pr': 'fixture/repo#1', 'prompt_file': self.prompt}),
                              ('acceptance', {'issue': 'CAF-123', 'prompt_file': self.prompt}),
                              ('final', {'sha': self.sha, 'pr': 'other/repo#1'})]:
            with self.subTest(kind=kind, options=options), self.assertRaises(ValueError):
                review_routing.review_plan(kind, self.repo, **options)

    def test_handoff_keeps_the_actual_request_and_detects_dirty_scope(self):
        self.git('remote', 'set-url', 'origin', 'git@github.com:KAMP-fk/concafe-techo.git')
        (self.repo / 'source.txt').write_text('dirty change\n')
        plan = review_routing.review_plan('technical', self.repo, prompt_file=self.prompt)
        self.assertEqual(plan['request']['text'], self.prompt.read_text())
        self.assertEqual(len(plan['request']['sha256']), 64)
        self.assertEqual(plan['request']['path'], str(self.prompt))
        self.assertTrue(plan['checkoutDirty'])

    def test_acceptance_without_verified_repository_identity_blocks(self):
        self.git('remote', 'remove', 'origin')
        with self.assertRaisesRegex(ValueError, 'origin'):
            review_routing.review_plan('acceptance', self.repo, issue='CAF-123')

    def test_unreadable_git_identity_does_not_allow_generic_claude(self):
        failed = subprocess.CompletedProcess([], 128, '', 'fatal: permission denied')
        with mock.patch.object(project_identity, 'git_process', return_value=failed):
            with self.assertRaisesRegex(ValueError, '識別'):
                project_identity.is_concafe_path(self.repo)


if __name__ == '__main__':
    unittest.main()
