"""Review intake scope guards; all service/model commands are isolated fixtures."""
import unittest

import test_agent_refactor as fixtures


class ReviewScopeTests(unittest.TestCase):
    setUp = fixtures.OfflineCase.setUp
    run_cli = fixtures.OfflineCase.run_cli
    review = fixtures.OfflineCase.review
    calls = fixtures.OfflineCase.calls
    packet = fixtures.OfflineCase.packet

    def test_matching_expected_repository_keeps_existing_packet_pipeline(self):
        result = self.review('--expected-repo', 'TEST/REPO', '--packet-only')
        self.packet(result)
        self.assertTrue(any(c[:3] == ['gh', 'pr', 'view'] for c in self.calls()))
        self.assertFalse(any(c[0] in ('claude', 'codex') for c in self.calls()))

    def test_explicit_pr_or_run_in_another_repository_blocks_before_services(self):
        for options in [('--expected-repo', 'other/repo'),
                        ('--expected-repo', 'test/repo', '--run', 'other/repo:1')]:
            with self.subTest(options=options):
                result = self.review(*options)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('一致しない', result.stderr)
                self.assertEqual(self.calls(), [])

    def test_discovered_pr_in_another_repository_blocks_before_pr_fetch_or_models(self):
        self.config['issue_description'] = 'AC: https://github.com/test/repo/pull/1'
        result = self.run_cli(fixtures.REVIEWER, 'CAF-999', '--expected-repo', 'other/repo', '--packet-only')
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('一致しない', result.stdout)
        self.assertFalse(any(c[:3] == ['gh', 'pr', 'view'] or c[0] in ('codex', 'claude') for c in self.calls()))

    def test_invalid_or_empty_scope_blocks_without_creating_packets(self):
        for value in ('', 'test/repo#1', '../test', 'https://github.com/test/repo'):
            with self.subTest(value=value):
                result = self.run_cli(fixtures.REVIEWER, 'CAF-999', '--expected-repo', value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse((self.root / 'reviewer-state').exists())


if __name__ == '__main__':
    unittest.main()
