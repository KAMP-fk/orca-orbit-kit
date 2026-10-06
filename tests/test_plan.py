"""Offline checks for Banana's read-only plan: canned orca / gh fixtures on PATH, no network, no writes."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import plan

FIXTURE = '''#!%s
import json, os, sys
from pathlib import Path
root = Path(os.environ['PLAN_FIXTURE_DIR'])
with open(root / 'calls.log', 'a') as log:
    log.write(json.dumps(sys.argv) + '\\n')
name, args = Path(sys.argv[0]).name, sys.argv[1:]
if name == 'orca' and args[:2] == ['linear', 'list-issues']:
    key = 'created' if '--created-at' in args else args[args.index('--state') + 1]
elif name == 'orca' and args[:2] == ['worktree', 'list']:
    key = 'worktrees'
elif name == 'gh' and args[:2] == ['pr', 'list']:
    key = 'gh-' + args[args.index('--state') + 1]
else:
    print('fixture: unexpected ' + ' '.join(sys.argv), file=sys.stderr)
    raise SystemExit(9)
if key in os.environ.get('PLAN_FIXTURE_FAIL', '').split(','):
    print('fixture: ' + key + ' unavailable', file=sys.stderr)
    raise SystemExit(1)
sys.stdout.write((root / (key + '.json')).read_text())
''' % sys.executable

NOW = datetime.now(timezone.utc)


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat().replace('+00:00', 'Z')


def issue(identifier, title, state='Todo', priority=4, labels=(), description='PRIVATE_DESCRIPTION'):
    labels_json = [{'id': 'l-' + name, 'name': name, 'color': '#000'} for name in labels]
    label = {0: 'No priority', 1: 'urgent', 2: 'high', 3: 'medium', 4: 'low'}[priority]
    return dict(id='uuid-' + identifier, identifier=identifier, title=title, url='https://linear.app/x/issue/' + identifier,
                description=description, priority=priority, priorityLabel=label, labels=labels_json,
                state={'id': 's', 'name': state, 'type': 'unstarted'}, createdAt=ago(30), updatedAt=ago(2),
                assignee=None, branchName='x', cycle=None, dueDate=None, estimate=None, project=None, team={'key': 'CAF'})


def linear(issues, truncated=False):
    return {'ok': True, 'id': 'r', 'result': {'issues': issues, 'truncated': truncated, 'meta': {
        'limit': None, 'returned': len(issues), 'hasMore': truncated, 'partial': False, 'workspaceErrors': []}}}


def pr(number, title, branch, draft=False, labels=(), hours=0.2, body='PRIVATE_BODY'):
    return dict(number=number, title=title, headRefName=branch, isDraft=draft, updatedAt=ago(hours), body=body,
                labels=[{'id': 'g-' + name, 'name': name, 'description': 'd', 'color': 'fff'} for name in labels])


TODO = [
    issue('CAF-268', 'M4/M5 店舗ページの訪問履歴'),
    issue('CAF-381', '洗い出し結果を整理する', priority=3, labels=['human-approval']),
    issue('CAF-355', '本番 migration の承認', priority=3, labels=['risk:high', 'type:chore']),
    issue('CAF-393', 'idempotency key binding'),
    issue('CAF-169', '報告の引き継ぎ', description='blockedBy: CAF-168 と CAF-167'),
    issue('CAF-402', 'CI runner の Node を温める', priority=2),
    issue('CAF-410', 'CI supervisor の停止検知', priority=1),
    issue('CAF-420', '推し一覧の並び', priority=0),
    issue('CAF-430', 'linked worktree がある issue', priority=2),
]
IN_PROGRESS = [issue('CAF-300', 'レビュー relay の門', 'In Progress'), issue('CAF-301', '店舗検索', 'In Progress')]
IN_REVIEW = [issue('CAF-302', 'GitHub Actions の workflow 整理', 'In Review')]
DONE = [issue('CAF-29%d' % i, 'done %d' % i, 'Done') for i in range(3)]
CREATED = [issue('CAF-45%d' % i, 'new %d' % i, 'Backlog') for i in range(4)]
WORKTREES = {'ok': True, 'result': {'truncated': False, 'hostScope': {}, 'totalCount': 4, 'worktrees': [
    dict(path='/w/393', branch='refs/heads/codex/caf-393-idempotency-key-binding', displayName='caf-393',
         repoId='r', isArchived=False, linkedLinearIssue=None),
    dict(path='/w/268', branch='refs/heads/codex/caf-268-old', displayName='caf-268', repoId='r',
         isArchived=True, linkedLinearIssue=None),
    dict(path='/w/430', branch='refs/heads/KAMP-fk/misc', displayName='caf-430', repoId='r',
         isArchived=False, linkedLinearIssue='CAF-430'),
    dict(path='/w/1690', branch='refs/heads/codex/caf-1690-not-169', displayName='x', repoId='r',
         isArchived=False, linkedLinearIssue=None),
]}}
OPEN_PRS = [
    pr(310, 'CI node prewarm (CAF-402)', 'codex/caf-402-ci-node-prewarm', labels=['risk:low', 'auto-ready:enabled'], hours=20),
    pr(311, 'HOLD: CAF-355 本番 migration', 'codex/caf-355-migration', draft=True, labels=['risk:high'], hours=0.2),
    pr(312, 'CAF-440 feature branch', 'feature/x', labels=['risk:low']),
    pr(313, 'CAF-441 draft without hold', 'claude/caf-441-foo', draft=True, hours=3),
]
MERGED = [{'number': n, 'mergedAt': ago(10)} for n in (304, 305, 308, 309)]


class PlanFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plan-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.data = self.root / 'data'
        self.data.mkdir()
        for name in ('orca', 'gh'):
            executable = self.bin / name
            executable.write_text(FIXTURE)
            executable.chmod(0o755)
        self.write('Todo', linear(TODO))
        self.write('In Progress', linear(IN_PROGRESS))
        self.write('In Review', linear(IN_REVIEW))
        self.write('Done', linear(DONE))
        self.write('created', linear(CREATED))
        self.write('worktrees', WORKTREES)
        self.write('gh-open', OPEN_PRS)
        self.write('gh-merged', MERGED)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE', 'ORCA_DEV_REPO_ROOT')}
        # Only the fixture directory is on PATH, so `orca` and `gh` resolve to the canned scripts.
        self.env.update(PATH=str(self.bin), ORCA_CLI_COMMAND='orca', PLAN_FIXTURE_DIR=str(self.data))

    def write(self, key, value):
        (self.data / (key + '.json')).write_text(json.dumps(value, ensure_ascii=False))

    def run_plan(self, *args, fail=()):
        env = dict(self.env, PLAN_FIXTURE_FAIL=','.join(fail))
        command = [sys.executable, '-B', str(PACKAGE / 'bin/plan'), '--team', 'CAF', '--repo', 'KAMP-fk/concafe-techo']
        return subprocess.run(command + list(args), capture_output=True, text=True, env=env, timeout=30)

    def calls(self):
        log = self.data / 'calls.log'
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_counts_line_matches_fixture_numbers(self):
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Todo 9 / In Progress 2 / In Review 1 / open PR 4（Draft 2）/ 直近3日: 起票 4・Done 3・merge 4', result.stdout)
        self.assertIn('merged:>=2026-', result.stdout)
        self.assertIn(' UTC）', result.stdout)
        # CI / レビュー / Actions+workflow titles among the 12 open issues → 4 mechanism.
        self.assertIn('機構 vs 製品: 機構 4 / 製品 8（open issue 12 件', result.stdout)
        self.assertIn('依存（blockedBy）は CLI が返さないので未確認', result.stdout)

    def test_truncated_count_is_marked_as_lower_bound(self):
        self.write('Todo', linear(TODO, truncated=True))
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Todo 9+ /', result.stdout)
        self.assertIn('下限', result.stdout)
        value = json.loads(self.run_plan('--json').stdout)
        self.assertTrue(value['counts']['Todo']['lower_bound'])
        self.assertEqual(next(s['status'] for s in value['sources'] if s['name'] == 'list-issues Todo'), 'truncated')

    def test_candidates_are_ordered_and_excluded_with_reasons(self):
        result = self.run_plan()
        value = json.loads(self.run_plan('--json').stdout)
        ready = [entry['identifier'] for entry in value['candidates']['ready']]
        self.assertEqual(ready, ['CAF-410', 'CAF-268', 'CAF-420'])  # urgent → low → none, then number
        reasons = {entry['identifier']: entry['reasons'][0] for entry in value['candidates']['excluded']}
        self.assertEqual(set(reasons), {'CAF-381', 'CAF-355', 'CAF-393', 'CAF-169', 'CAF-402', 'CAF-430'})
        self.assertIn('human-approval → 持ち主の合図待ち', reasons['CAF-381'])
        self.assertIn('risk:high → 持ち主の合図待ち', reasons['CAF-355'])
        self.assertIn('既存 worktree codex/caf-393-idempotency-key-binding → 補充しない', reasons['CAF-393'])
        self.assertIn('既存 worktree KAMP-fk/misc → 補充しない', reasons['CAF-430'])  # linkedLinearIssue match
        self.assertIn('既存 PR #310 → 補充しない', reasons['CAF-402'])
        self.assertIn('本文に blockedBy の記述 → 未確認', reasons['CAF-169'])
        text = result.stdout
        self.assertLess(text.index('CAF-410'), text.index('CAF-268'))
        self.assertIn('  CAF-169  Low     本文に blockedBy の記述 → 未確認（CLI は返さない。Linear で見る）', text)
        self.assertIn('既存 worktree なし・PR なし', text)

    def test_wip_limits_shown_candidates(self):
        result = self.run_plan('--wip', '1')
        self.assertIn('WIP 上限 1', result.stdout)
        self.assertIn('  （他 1 件）', result.stdout)
        self.assertNotIn('  CAF-420', result.stdout)

    def test_pr_hints_cover_hold_auto_ready_branch_and_stale(self):
        result = self.run_plan()
        lines = {int(line[1:6]): line for line in result.stdout.splitlines() if line.startswith('#31')}
        self.assertIn('Ready・auto-ready:enabled → CI/merge の機械待ち', lines[310])
        self.assertIn('90分以上更新なし → 誰の手か確かめる', lines[310])
        self.assertIn('Draft HOLD', lines[311])
        self.assertIn('Draft・HOLD → review 待ち', lines[311])
        self.assertIn('risk:high → 持ち主の合図', lines[311])
        self.assertNotIn('90分以上', lines[311])
        self.assertIn('branch 名が許可外 → 新しい ref で PR を作り直す', lines[312])
        self.assertIn('Draft・HOLD なし', lines[313])
        self.assertIn('90分以上更新なし', lines[313])
        self.assertIn('CAF-402', lines[310])
        self.assertIn('更新 20h前', lines[310])

    def test_descriptions_and_bodies_are_never_printed(self):
        for args in ((), ('--json',)):
            result = self.run_plan(*args)
            self.assertNotIn('PRIVATE_', result.stdout + result.stderr)

    def test_missing_gh_is_unconfirmed_and_still_exit_zero(self):
        (self.bin / 'gh').unlink()
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('open PR 未確認（Draft 未確認）', result.stdout)
        self.assertIn('merge 未確認', result.stdout)
        self.assertIn('未確認（gh pr list open: gh が見つからない）', result.stdout)
        self.assertIn('PR 未確認（gh が見つからない）', result.stdout)
        self.assertIn('Todo 9 /', result.stdout)
        value = json.loads(self.run_plan('--json').stdout)
        self.assertIsNone(value['counts']['open_pr']['count'])
        self.assertIsNone(value['open_prs'])

    def test_failing_single_state_is_unconfirmed_not_zero(self):
        result = self.run_plan(fail=('In Review',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('In Review 未確認', result.stdout)
        self.assertIn('In Review は未確認で含まない', result.stdout)
        self.assertIn('未確認（list-issues In Review: exit 1: fixture: In Review unavailable）', result.stdout)

    def test_orca_failing_for_every_issue_read_exits_one(self):
        result = self.run_plan(fail=('Todo', 'In Progress', 'In Review', 'Done', 'created'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('Todo 未確認 / In Progress 未確認 / In Review 未確認', result.stdout)
        self.assertIn('未確認（list-issues Todo: exit 1', result.stdout)
        self.assertIn('open PR 4（Draft 2）', result.stdout)  # what gh gave is still reported

    def test_bad_arguments_exit_two(self):
        base = [sys.executable, '-B', str(PACKAGE / 'bin/plan')]
        for args in (['--repo', 'o/r'], ['--team', 'CAF'], ['--team', 'CAF', '--repo', 'no-slash'],
                     ['--team', 'CAF', '--repo', 'o/r', '--days', '0'], ['--team', 'CAF', '--repo', 'o/r', '--wip', '0'],
                     ['--team', 'CAF', '--repo', 'o/r', '--bogus']):
            result = subprocess.run(base + args, capture_output=True, text=True, env=self.env, timeout=30)
            self.assertEqual(result.returncode, 2, args)
        self.assertEqual(self.calls(), [])

    def test_json_schema_sanity(self):
        result = self.run_plan('--json', '--days', '5')
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['team'], 'CAF')
        self.assertEqual(value['repo'], 'KAMP-fk/concafe-techo')
        self.assertEqual(value['days'], 5)
        self.assertEqual(len(value['sources']), 8)
        for source in value['sources']:
            self.assertEqual(set(source) - {'reason'}, {'name', 'command', 'status', 'observed_at'})
            self.assertIsInstance(source['command'], list)
            self.assertEqual(source['status'], 'success')
            self.assertRegex(source['observed_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        for key in ('Todo', 'In Progress', 'In Review', 'done', 'created', 'open_pr', 'draft_pr', 'merged'):
            self.assertIn('count', value['counts'][key])
            self.assertIn('lower_bound', value['counts'][key])
        self.assertEqual(value['mechanism']['open_issues'], 12)
        self.assertEqual([p['number'] for p in value['open_prs']], [310, 311, 312, 313])
        self.assertEqual(set(value['open_prs'][0]), {'number', 'title', 'issue', 'issue_source', 'draft', 'hold', 'labels',
                                                    'branch', 'branch_allowed', 'updated_at', 'age_hours', 'hint'})
        self.assertEqual(value['candidates']['shown'], 3)
        self.assertEqual(value['unverified'], [])
        self.assertTrue(value['linear_available'])
        done = next(s['command'] for s in value['sources'] if s['name'] == 'list-issues Done')
        self.assertEqual(done[-5:], ['--state', 'Done', '--updated-at', '-P5D', '--json'])
        created = next(s['command'] for s in value['sources'] if s['name'] == 'list-issues created')
        self.assertEqual(created[-3:], ['--created-at', '-P5D', '--json'])

    def test_only_read_only_subcommands_are_invoked_and_counts_use_no_limit(self):
        self.run_plan('--project', 'M3')
        self.run_plan('--json')
        calls = self.calls()
        self.assertEqual(len(calls), 16)
        for argv in calls:
            name = Path(argv[0]).name
            if name == 'orca':
                self.assertIn(argv[1:3], (['linear', 'list-issues'], ['worktree', 'list']))
                self.assertIn('--json', argv)
                if argv[1:3] == ['linear', 'list-issues']:
                    self.assertNotIn('--limit', argv)
            else:
                self.assertEqual(name, 'gh')
                self.assertEqual(argv[1:3], ['pr', 'list'])
                self.assertIn(argv[argv.index('--state') + 1], ('open', 'merged'))
        projected = [argv for argv in calls if '--project' in argv]
        self.assertEqual(len(projected), 5)
        self.assertTrue(all(argv[argv.index('--project') + 1] == 'M3' for argv in projected))
        # Nothing but the fixture log was written anywhere under the temp root.
        self.assertEqual(sorted(p.name for p in self.data.iterdir() if p.suffix != '.json'), ['calls.log'])


class PlanUnitTests(unittest.TestCase):
    def test_pr_issue_derivation_prefers_title_then_branch_then_body(self):
        self.assertEqual(plan.pr_issue('CAF', {'title': 'HOLD: CAF-355 x'}), ('CAF-355', 'title'))
        self.assertEqual(plan.pr_issue('CAF', {'title': 'CI prewarm (CAF-402)'}), ('CAF-402', 'title'))
        self.assertEqual(plan.pr_issue('CAF', {'title': 'CAF-7 start'}), ('CAF-7', 'title'))
        self.assertEqual(plan.pr_issue('CAF', {'title': 'no id', 'headRefName': 'codex/caf-12-x'}), ('CAF-12', 'branch'))
        self.assertEqual(plan.pr_issue('CAF', {'title': 'no id', 'headRefName': 'feature/x', 'body': 'Closes CAF-9'}), ('CAF-9', 'body'))
        self.assertEqual(plan.pr_issue('CAF', {'title': 'mentions CAF-3 inside'}), (None, None))

    def test_worktree_match_requires_prefix_and_exact_number(self):
        rows = [{'branch': 'refs/heads/codex/caf-169-x'}, {'branch': 'refs/heads/codex/caf-1690-x'},
                {'branch': 'refs/heads/KAMP-fk/caf-169-review'}, {'branch': 'refs/heads/other', 'linkedLinearIssue': 'caf-169'}]
        self.assertEqual(plan.worktree_matches('CAF', 'CAF-169', rows), ['codex/caf-169-x', 'other'])
        self.assertEqual(plan.worktree_matches('CAF', 'CAF-1', rows), [])

    def test_mechanism_words_are_matched_coarsely(self):
        self.assertTrue(plan.is_mechanism('CI runner を直す'))
        self.assertTrue(plan.is_mechanism('GitHub Actions の整理'))
        self.assertTrue(plan.is_mechanism('レビュー relay'))
        self.assertFalse(plan.is_mechanism('specific 店舗ページ'))
        self.assertFalse(plan.is_mechanism('推し一覧'))


if __name__ == '__main__':
    unittest.main()
