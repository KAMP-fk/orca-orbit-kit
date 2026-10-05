"""Three-entry review routing with local Git fixtures and zero model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import review_routing
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
        self.sha = self.git('rev-parse', 'HEAD').strip()
        self.prompt = self.root / 'review request.md'
        self.prompt.write_text('Review the fixed change for regressions.\n')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              text=True, capture_output=True).stdout

    def cli(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE')}
        return subprocess.run([sys.executable, str(PACKAGE / 'bin/review'), *args],
                              text=True, capture_output=True, env=env, timeout=15)

    def test_inbox_needs_no_backend_and_cannot_carry_a_request(self):
        result = self.cli('--inbox')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--kind technical', result.stdout)
        self.assertNotEqual(self.cli('--inbox', '--kind', 'technical').returncode, 0)

    def test_acceptance_and_technical_select_exactly_one_route(self):
        acceptance = review_routing.review_plan('acceptance', self.repo, issue='CAF-123')
        technical = review_routing.review_plan('technical', self.repo, prompt_file=self.prompt)
        self.assertEqual(acceptance['route'], 'peach')
        self.assertEqual(technical['route'], 'potato')
        self.assertNotIn('potato', acceptance['argv'])
        self.assertNotIn(str(PACKAGE / 'bin/peach-task'), technical['argv'])
        self.assertIn('read', technical['argv'])
        self.assertTrue(acceptance['requiresUninvolvedTask'])
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
        self.assertEqual(self.cli(*args, '--dry-run').returncode, 0)

    def test_remote_identity_keeps_concafe_on_owner_codex_policy_without_contract_file(self):
        self.git('remote', 'add', 'origin', 'git@github.com:KAMP-fk/concafe-techo.git')
        for kind in ('acceptance', 'technical', 'final'):
            plan = review_routing.review_plan(kind, self.repo, issue='CAF-123',
                                              prompt_file=self.prompt, sha=self.sha)
            self.assertEqual(plan['route'], 'separate-project-task')
            self.assertEqual(plan['requiredModel'], 'gpt-6-astra' if kind == 'final' else 'gpt-6.1-sol')
            self.assertEqual(plan['requiredEffort'], 'high')
            self.assertFalse(plan['executableHere'])
            self.assertIsNone(plan['argv'])

    def test_concafe_worktree_is_recognized_even_if_renamed(self):
        self.git('remote', 'add', 'origin', 'https://github.com/KAMP-fk/concafe-techo.git')
        worktree = self.root / 'unrelated-task-name'
        self.git('worktree', 'add', '--detach', str(worktree), self.sha)
        self.assertTrue(review_routing.is_concafe_path(worktree))

    def test_direct_potato_cannot_bypass_concafe_route_by_omitting_repo_option(self):
        self.git('remote', 'add', 'origin', 'git@github.com:KAMP-fk/concafe-techo.git')
        config = self.root / 'claude config'
        (config / 'agents').mkdir(parents=True)
        (config / 'agents/potato.md').symlink_to(PACKAGE / 'roles/potato/claude/agent.md')
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(config)}):
            with self.assertRaisesRegex(ValueError, '別 Codex タスク'):
                role_launch.launch_spec('potato', self.repo, 'Review', batch=True, dry_run=True)

    def test_dry_run_technical_has_no_orca_model_or_task_state(self):
        with mock.patch.object(review_routing, 'git_process', wraps=review_routing.git_process) as git:
            plan = review_routing.review_plan('technical', self.repo, prompt_file=self.prompt)
        self.assertFalse(plan['startsSession'])
        self.assertTrue(all(call.args[0].endswith('/git') for call in git.call_args_list))
        result = self.cli('--kind', 'technical', '--repo', str(self.repo),
                          '--prompt-file', str(self.prompt), '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['route'], 'potato')


if __name__ == '__main__':
    unittest.main()
