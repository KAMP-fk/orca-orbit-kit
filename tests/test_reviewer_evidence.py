#!/usr/bin/env python3
"""Additional evidence/TOCTOU regressions; uses only fixture CLIs and temporary Git."""
import json
from pathlib import Path
import subprocess
import unittest
import test_agent_refactor as fixtures
SHA, BASE_SHA = fixtures.SHA, fixtures.BASE_SHA


class EvidenceCase(unittest.TestCase):
    # Reuse fixture setup/helpers without inheriting the older test methods.
    setUp = fixtures.OfflineCase.setUp
    run_cli = fixtures.OfflineCase.run_cli
    review = fixtures.OfflineCase.review
    calls = fixtures.OfflineCase.calls
    packet = fixtures.OfflineCase.packet
    local_repository = fixtures.OfflineCase.local_repository

    def latest_packet(self):
        return sorted((self.root / 'reviewer-state/packets/CAF-999').iterdir())[-1]

    def assert_blocked(self, result, model_expected=False):
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('Verdict: BLOCKED', result.stdout)
        self.assertNotIn('Verdict: PASS', result.stdout)
        ledger = (self.root / 'reviewer-state/ledger.tsv').read_text().splitlines()
        self.assertIn('\tBLOCKED\t', ledger[-1])
        if not model_expected:
            self.assertFalse(any(c[0] in ('codex', 'claude') for c in self.calls()))

    def test_manifest_tracks_scope_timestamps_and_commands(self):
        p = self.packet(self.review('--packet-only'))
        facts = json.loads((p / 'evidence.json').read_text())
        self.assertTrue(facts['complete'])
        self.assertFalse(facts['missing'])
        for record in facts['observations']:
            self.assertRegex(record['observedAt'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
            self.assertLessEqual(record['startedAt'], record['observedAt'])
            self.assertTrue((p / record['path']).is_file())
        source = json.loads((p / 'github/pr-test-repo-1/source.json').read_text())
        self.assertEqual((source['headSha'], source['baseSha']), (SHA, BASE_SHA))
        self.assertFalse(any(c[:3] == ['gh', 'pr', 'diff'] for c in self.calls()))
        self.assertTrue(any(SHA + '/check-runs' in ' '.join(c) for c in self.calls()))
        self.assertTrue(any(SHA + '/status?' in ' '.join(c) for c in self.calls()))

    def test_actual_git_diff_uses_pinned_base_and_head(self):
        git, base = self.local_repository()
        repo = Path(self.config['local_repo'])
        (repo / 'fixture.txt').write_text('new immutable head\n')
        subprocess.run([git, '-C', str(repo), 'add', 'fixture.txt'], env=self.env, check=True, capture_output=True)
        subprocess.run([git, '-C', str(repo), '-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'new head', '--no-gpg-sign'], env=self.env, check=True, capture_output=True)
        head = subprocess.check_output([git, '-C', str(repo), 'rev-parse', 'HEAD'], env=self.env, text=True).strip()
        self.config.update(base_sha=base, head_sha=head, changed_files=1)
        p = self.packet(self.review('--packet-only'))
        pr_root = p / 'github/pr-test-repo-1'
        expected = subprocess.check_output([git, '-C', str(repo), 'diff', '--binary', base + '...' + head], env=self.env, text=True)
        self.assertEqual((pr_root / 'diff.patch').read_text(), expected)
        self.assertEqual(json.loads((pr_root / 'commits.json').read_text()), [head])
        self.assertEqual(subprocess.check_output([git, '-C', str(p / 'src'), 'rev-parse', 'refs/inreview/base'], env=self.env, text=True).strip(), base)
        self.assertFalse((p / 'src/.git/objects/info/alternates').exists())

    def test_head_and_base_move_stop_before_model(self):
        for update in ({'headRefOid': 'b' * 40}, {'baseRefOid': 'd' * 40}, {'updatedAt': '2026-01-02T00:00:00Z'}):
            with self.subTest(update=update):
                self.log.unlink(missing_ok=True)
                self.config = {'pr_update': update}
                self.assert_blocked(self.review('--packet-only'))

    def test_head_moves_during_model_does_not_record_pass(self):
        self.config.update(pr_update={'headRefOid': 'b' * 40}, pr_update_call=3)
        self.assert_blocked(self.review(), model_expected=True)
        self.assertTrue((self.latest_packet() / 'verdict.raw').exists())

    def test_issue_status_or_requirements_move_during_acquisition(self):
        for update in ({'state': {'name': 'Done'}}, {'description': 'new acceptance criteria'}):
            with self.subTest(update=update):
                self.log.unlink(missing_ok=True)
                self.config = {'issue_update': update}
                self.assert_blocked(self.review('--packet-only'))

    def test_issue_changes_during_model_does_not_record_pass(self):
        self.config.update(issue_update={'description': 'new requirements'}, issue_update_call=3)
        self.assert_blocked(self.review(), model_expected=True)

    def initial_related_response(self, response, rc):
        # Override only the first related fetch; later calls use the normal fixture.
        wrapper = self.bin / 'orca-initial-related'
        wrapper.write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
log = Path(os.environ['CALL_LOG'])
call = ['orca'] + args
previous = [json.loads(row) for row in log.read_text().splitlines()] if log.exists() else []
if args[:3] == ['linear', 'issue', 'CAF-998'] and not any(row[:4] == call[:4] for row in previous):
    with log.open('a') as stream:
        stream.write(json.dumps(call) + '\\n')
    print(%r)
    print('initial related fixture diagnostic', file=sys.stderr)
    sys.exit(%r)
orca = str(Path(__file__).with_name('orca'))
os.execv(orca, [orca] + args)
''' % (json.dumps(response), rc))
        wrapper.chmod(0o755)
        self.env['ORCA_CLI_COMMAND'] = str(wrapper)
        self.config = {'relations': [{'relatedIssue': {'identifier': 'CAF-998'}}]}

    def capture_related_with_failures(self, response, rc=1, failures=1, raw_stdout=None):
        self.initial_related_response(response, rc)
        wrapper = Path(self.env['ORCA_CLI_COMMAND'])
        source = wrapper.read_text().replace(
            "not any(row[:4] == call[:4] for row in previous)",
            "sum(row[:4] == call[:4] for row in previous) < " + str(failures))
        if raw_stdout is not None:
            source = source.replace('print(%r)' % json.dumps(response), 'print(%r)' % raw_stdout)
        # Both attempts must leave the related-Issue loop's stdin untouched.
        wrapper.write_text(source.replace("args = sys.argv[1:]", "sys.stdin.read()\nargs = sys.argv[1:]"))
        packet = self.root / 'capture-packet'
        (packet / 'linear/related').mkdir(parents=True)
        self.env['EVIDENCE_RUNTIME_RETRY_DELAY_SECONDS'] = '0'
        lib = fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib'
        result = self.run_cli('/bin/bash', '-c', r"""
set -euo pipefail
PACKET="$1"
source "$2/evidence.sh"
source "$2/linear.sh"
EXPLICIT_TEST_CHECKS=()
ISSUE=CAF-999
REQUIRED_STATE='In Review'
ORCA_BIN="$ORCA_CLI_COMMAND"
blocked() { printf 'Verdict: BLOCKED\n%s\n' "$1"; exit 3; }
init_evidence
fetch_linear
finalize_evidence
""", 'capture-related', str(packet), str(lib))
        records = [json.loads(row) for row in (packet / 'evidence.jsonl').read_text().splitlines()]
        related = [r for r in records if r['key'] == 'linear.related.CAF-998']
        count = sum(c[:4] == ['orca', 'linear', 'issue', 'CAF-998'] for c in self.calls())
        return result, packet, related, count

    def test_runtime_unavailable_retries_once_then_acquires(self):
        response = {'ok': False, 'error': {'code': 'runtime_unavailable'}}
        result, packet, records, count = self.capture_related_with_failures(response)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(count, 2)
        self.assertEqual([(r['status'], r['exitCode']) for r in records], [('acquired', 0)])
        self.assertIn('runtime_unavailable のため1回再試行', records[0]['detail'])
        self.assertTrue(json.loads((packet / 'evidence.json').read_text())['complete'])
        self.assertTrue(json.loads((packet / 'linear/related/CAF-998.json').read_text())['ok'])
        self.assertEqual((packet / 'linear/related/CAF-998.json.err').read_text(), '')

    def test_runtime_unavailable_retry_failure_still_blocks(self):
        response = {'ok': False, 'error': {'code': 'runtime_unavailable'}}
        result, packet, records, count = self.capture_related_with_failures(response, failures=2)
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('Verdict: BLOCKED', result.stdout)
        self.assertIn('関連 Issue CAF-998 の状態を取得できないため、判定を有効化しない。', result.stdout)
        self.assertEqual(count, 2)
        self.assertEqual([(r['status'], r['exitCode']) for r in records], [('failed', 1)])
        self.assertIn('runtime_unavailable のため1回再試行', records[0]['detail'])
        self.assertEqual(json.loads((packet / 'linear/related/CAF-998.json').read_text()), response)

    def test_other_runtime_error_does_not_retry(self):
        response = {'ok': False, 'error': {'code': 'not_found'}}
        result, _, records, count = self.capture_related_with_failures(response)
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('関連 Issue CAF-998 の状態を取得できないため、判定を有効化しない。', result.stdout)
        self.assertEqual(count, 1)
        self.assertEqual(records[0]['status'], 'failed')
        self.assertNotIn('再試行', records[0]['detail'])

    def test_non_json_failure_does_not_retry(self):
        result, _, records, count = self.capture_related_with_failures({}, raw_stdout='runtime unavailable')
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('関連 Issue CAF-998 の状態を取得できないため、判定を有効化しない。', result.stdout)
        self.assertEqual(count, 1)
        self.assertEqual(records[0]['status'], 'failed')
        self.assertNotIn('再試行', records[0]['detail'])

    def test_exit_zero_runtime_unavailable_does_not_retry(self):
        response = {'ok': False, 'error': {'code': 'runtime_unavailable'}}
        result, _, records, count = self.capture_related_with_failures(response, rc=0)
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('関連 Issue CAF-998 の応答が不正', result.stdout)
        self.assertEqual(count, 1)
        self.assertFalse(any('再試行' in r['detail'] for r in records))

    def test_initial_related_fetch_failure_stops_as_acquisition_failure(self):
        self.initial_related_response({'ok': False, 'code': 'runtime_unavailable'}, 1)
        result = self.review('--packet-only')
        self.assert_blocked(result)
        self.assertIn('関連 Issue CAF-998 の状態を取得できないため、判定を有効化しない。', result.stdout)
        packet = self.latest_packet()
        self.assertIn(str(packet / 'linear/related/CAF-998.json.err'), result.stdout)
        self.assertNotIn('更新された', result.stdout)
        records = [json.loads(row) for row in (packet / 'evidence.jsonl').read_text().splitlines()]
        self.assertEqual([(r['status'], r['exitCode']) for r in records if r['key'] == 'linear.related.CAF-998'], [('failed', 1)])
        self.assertFalse(any('changed' in r['detail'] for r in records))
        self.assertEqual(sum(c[:4] == ['orca', 'linear', 'issue', 'CAF-998'] for c in self.calls()), 1)
        self.assertFalse((packet / 'linear/issue-acquired.json').exists())

    def test_second_related_initial_failure_with_stdin_consuming_orca(self):
        # A CLI that drains stdin must not consume the loop's remaining Issue IDs.
        wrapper = self.bin / 'orca-drain-stdin'
        wrapper.write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
sys.stdin.read()
args = sys.argv[1:]
if args[:3] == ['linear', 'issue', 'CAF-998']:
    with Path(os.environ['CALL_LOG']).open('a') as stream:
        stream.write(json.dumps(['orca'] + args) + '\\n')
    print(json.dumps({'ok': False, 'code': 'runtime_unavailable'}))
    print('second related fixture diagnostic', file=sys.stderr)
    sys.exit(1)
orca = str(Path(__file__).with_name('orca'))
os.execv(orca, [orca] + args)
''')
        wrapper.chmod(0o755)
        self.env['ORCA_CLI_COMMAND'] = str(wrapper)
        self.config = {'relations': [{'relatedIssue': {'identifier': rid}}
                                     for rid in ('CAF-997', 'CAF-998')]}
        result = self.review('--packet-only')
        counts = {rid: sum(c[:4] == ['orca', 'linear', 'issue', rid] for c in self.calls())
                  for rid in ('CAF-997', 'CAF-998')}
        self.assertEqual(counts, {'CAF-997': 1, 'CAF-998': 1}, result.stderr + result.stdout)
        self.assert_blocked(result)
        self.assertIn('関連 Issue CAF-998 の状態を取得できないため、判定を有効化しない。', result.stdout)
        self.assertNotIn('更新された', result.stdout)
        packet = self.latest_packet()
        records = [json.loads(row) for row in (packet / 'evidence.jsonl').read_text().splitlines()]
        for rid, status, rc in (('CAF-997', 'acquired', 0), ('CAF-998', 'failed', 1)):
            self.assertEqual([(r['status'], r['exitCode']) for r in records
                              if r['key'] == 'linear.related.' + rid], [(status, rc)])
        self.assertEqual(json.loads((packet / 'linear/related/CAF-997.json').read_text())
                         ['result']['issue']['identifier'], 'CAF-997')
        self.assertIn('second related fixture diagnostic',
                      (packet / 'linear/related/CAF-998.json.err').read_text())
        self.assertFalse((packet / 'linear/issue-acquired.json').exists())

    def test_initial_related_malformed_response_stops_before_recheck(self):
        for response in ({'ok': False, 'code': 'runtime_unavailable'},
                         {'ok': True, 'result': {'issue': {'identifier': 'CAF-998'}}}):
            with self.subTest(response=response):
                self.log.unlink(missing_ok=True)
                self.initial_related_response(response, 0)
                result = self.review('--packet-only')
                self.assert_blocked(result)
                self.assertIn("関連 Issue CAF-998 の応答が不正", result.stdout)
                packet = self.latest_packet()
                records = [json.loads(row) for row in (packet / 'evidence.jsonl').read_text().splitlines()]
                self.assertTrue(any(r['status'] == 'invalid' and r['detail'] == 'malformed related Issue response' for r in records))
                self.assertFalse(any('changed' in r['detail'] for r in records))
                self.assertEqual(sum(c[:4] == ['orca', 'linear', 'issue', 'CAF-998'] for c in self.calls()), 1)

    def test_related_change_on_acquisition_recheck_still_blocks(self):
        self.config = {'relations': [{'relatedIssue': {'identifier': 'CAF-998'}}],
                       'related_update': {'description': 'changed related requirements'}}
        result = self.review('--packet-only')
        self.assert_blocked(result)
        self.assertIn('関連 Issue CAF-998 の状態・要件・前提が取得後に更新された', result.stdout)
        records = [json.loads(row) for row in (self.latest_packet() / 'evidence.jsonl').read_text().splitlines()]
        self.assertTrue(any(r['detail'] == 'Related Issue requirements, status or context changed' for r in records))

    def test_unchanged_related_acquisition_recheck_proceeds(self):
        self.config = {'relations': [{'relatedIssue': {'identifier': 'CAF-998'}}]}
        packet = self.packet(self.review('--packet-only'))
        self.assertTrue((packet / 'linear/rechecks/acquired/CAF-998.json').is_file())
        self.assertTrue(json.loads((packet / 'evidence.json').read_text())['complete'])
        self.assertFalse(any(c[0] in ('codex', 'claude') for c in self.calls()))

    def test_related_issue_changes_during_model_with_main_unchanged(self):
        updates = ({'related_update': {'description': 'new parent requirements'}},
                   {'related_update': {'state': {'name': 'Done'}}},
                   {'related_result_update': {'comments': [{'body': 'new acceptance premise'}]}},
                   {'related_recheck_rc': 4})
        for update in updates:
            with self.subTest(update=update):
                self.log.unlink(missing_ok=True)
                self.config = {'relations': [{'relatedIssue': {'identifier': 'CAF-998'}}], 'related_update_call': 3, **update}
                self.assert_blocked(self.review(), model_expected=True)
                p = self.latest_packet()
                before = json.loads((p / 'linear/issue.json').read_text())
                after = json.loads((p / 'linear/issue-final.json').read_text())
                self.assertEqual(before, after)
                self.assertTrue(any(c[:4] == ['orca', 'linear', 'issue', 'CAF-998'] and '--full' in c for c in self.calls()))

    def test_parent_and_child_are_rechecked_before_verdict(self):
        for relation in ({'parent': {'identifier': 'CAF-998'}}, {'children': [{'identifier': 'CAF-998', 'state': {'name': 'In Review'}, 'title': 'child'}]}):
            with self.subTest(relation=relation):
                self.log.unlink(missing_ok=True)
                self.config = {**relation, 'related_update_call': 3, 'related_update': {'description': 'changed dependency'}}
                self.assert_blocked(self.review(), model_expected=True)

    def test_unchanged_related_issue_allows_verdict(self):
        self.config = {'relations': [{'relatedIssue': {'identifier': 'CAF-998'}}]}
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        p = self.latest_packet()
        self.assertTrue((p / 'linear/rechecks/acquired/CAF-998.json').is_file())
        self.assertTrue((p / 'linear/rechecks/final/CAF-998.json').is_file())

    def test_claude_probe_actual_model_metadata_is_required(self):
        for usage in ({'claude-sonnet-4-5': {}}, {'unknown-opus': {}}, {}, None,
                      {'claude-opus-4-6': {}}, {'claude-opus-4-5': {}},
                      {'claude-opus-5-5-20261001': {}}, {'opus': {}},
                      {'claude-opus-4-6[1m]': {}},
                      {'claude-opus-5-5': {}, 'claude-haiku-4-5': {}},
                      {'claude-opus-4-6': {}, 'claude-opus-4-5': {}}):
            with self.subTest(usage=usage):
                self.log.unlink(missing_ok=True)
                self.config = {'probe_model_usage': usage}
                self.assert_blocked(self.review('--backend', 'claude'), model_expected=True)
                self.assertEqual(sum(c[0] == 'claude' for c in self.calls()), 1)

    def test_claude_review_actual_model_metadata_is_required(self):
        for usage in ({'claude-sonnet-4-5': {}}, {'unknown-opus': {}}, {}, None,
                      {'claude-opus-4-6': {}}, {'claude-opus-4-5': {}},
                      {'claude-opus-5-5-20261001': {}}, {'opus': {}},
                      {'claude-opus-4-6[1m]': {}},
                      {'claude-opus-5-5': {}, 'claude-haiku-4-5': {}},
                      {'claude-opus-4-6': {}, 'claude-opus-4-5': {}}):
            with self.subTest(usage=usage):
                self.log.unlink(missing_ok=True)
                self.config = {'model_usage': usage}
                self.assert_blocked(self.review('--backend', 'claude'), model_expected=True)
                self.assertEqual(sum(c[0] == 'claude' for c in self.calls()), 2)

    def test_claude_probe_text_containing_opus_is_not_model_proof(self):
        self.config = {'probe_model_usage': {'claude-sonnet-4-5': {}}, 'probe_result': 'opus PREFLIGHT_OK'}
        self.assert_blocked(self.review('--backend', 'claude'), model_expected=True)

    def test_claude_approved_model_ids_are_saved(self):
        for actual_model in ('claude-opus-5-5', 'claude-opus-5-5[1m]'):
            with self.subTest(actual_model=actual_model):
                packet_root = self.root / 'reviewer-state/packets/CAF-999'
                previous_packets = set(packet_root.iterdir()) if packet_root.exists() else set()
                self.config = {'probe_model_usage': {actual_model: {}}, 'model_usage': {actual_model: {}}}
                result = self.review('--backend', 'claude')
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                created_packets = set(packet_root.iterdir()) - previous_packets
                self.assertEqual(len(created_packets), 1)
                p = created_packets.pop()
                for artifact in ('preflight-model.json', 'claude-models.json'):
                    facts = json.loads((p / artifact).read_text())
                    self.assertEqual(facts['actualModelIds'], [actual_model])
                    self.assertEqual(facts['requestedModel'], 'claude-opus-5-5')

    def test_ci_transport_failure_is_not_empty_success(self):
        self.config['checks_fetch_rc'] = 4
        p = self.packet(self.review('--packet-only'))
        facts = json.loads((p / 'evidence.json').read_text())
        self.assertFalse(facts['complete'])
        self.assertTrue(any(row['status'] == 'failed' and 'check-runs' in row['key'] for row in facts['missing']))
        self.assertNotEqual((p / 'github/pr-test-repo-1/check-runs.json').read_text().strip(), '[]')
        self.assert_blocked(self.review())

    def test_ci_changes_during_model_does_not_record_pass(self):
        self.config['ci_after_review'] = {'checks': [{'name': 'Unit tests', 'bucket': 'fail'}], 'checks_rc': 1}
        self.assert_blocked(self.review(), model_expected=True)
        facts = json.loads((self.latest_packet() / 'evidence.json').read_text())
        self.assertFalse(facts['complete'])
        self.assertTrue(any(row['key'].endswith('.verification.final') for row in facts['missing']))

    def test_other_head_ci_cannot_support_pass(self):
        self.config['check_head_sha'] = 'b' * 40
        self.assert_blocked(self.review())

    def test_partial_ci_pages_cannot_support_pass(self):
        self.config['check_run_pages'] = [{'total_count': 2, 'check_runs': [{'id': 1, 'name': 'Unit tests', 'head_sha': SHA, 'status': 'completed', 'conclusion': 'success'}]}]
        self.assert_blocked(self.review())

    def test_partial_status_pages_cannot_support_pass(self):
        self.config['status_pages'] = [{'sha': SHA, 'total_count': 2, 'statuses': [{'id': 1, 'context': 'build', 'state': 'success'}]}]
        self.assert_blocked(self.review())

    def test_graphql_errors_and_truncation_cannot_support_pass(self):
        for thread_response in ({'data': None, 'errors': [{'message': 'partial GraphQL error'}]}, {'data': {'repository': {'pullRequest': {'reviewThreads': {'pageInfo': {'hasNextPage': True}, 'nodes': []}}}}}):
            with self.subTest(response=thread_response):
                self.config['threads'] = thread_response
                self.assert_blocked(self.review())

    def test_thread_transport_failure_is_visible(self):
        self.config['threads_fetch_rc'] = 4
        self.assert_blocked(self.review())

    def test_related_issue_failure_is_visible(self):
        self.config.update(relations=[{'relatedIssue': {'identifier': 'CAF-998'}}], related_rc=4)
        self.assert_blocked(self.review())

    def test_diff_failure_is_visible(self):
        self.config['diff_rc'] = 1
        self.assert_blocked(self.review())

    def test_missing_base_object_is_blocked(self):
        self.local_repository()
        self.config['base_sha'] = 'd' * 40
        self.assert_blocked(self.review('--packet-only'))

    def test_inherited_git_redirection_cannot_change_clone_target(self):
        git, sha = self.local_repository()
        outside_index = self.root / 'wrong-index'
        self.env.update(GIT_DIR=str(self.root / 'not-the-repo'), GIT_WORK_TREE=str(self.root),
                        GIT_INDEX_FILE=str(outside_index), GIT_OBJECT_DIRECTORY=str(self.root / 'wrong-objects'),
                        GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0=str(self.root))
        p = self.packet(self.review('--packet-only'))
        clean_env = {key:value for key,value in self.env.items() if not key.startswith('GIT_')}
        actual = subprocess.check_output([git, '-C', str(p / 'src'), 'rev-parse', 'HEAD'], env=clean_env, text=True).strip()
        self.assertEqual(actual, sha)
        self.assertFalse(outside_index.exists())

    def test_required_ci_matches_head_and_ignores_optional_skip(self):
        self.config.update(checks=[{'name': 'Unit tests', 'bucket': 'pass'}, {'name': 'Optional docs', 'bucket': 'skipping'}], required_checks=[{'name': 'Unit tests', 'bucket': 'pass'}])
        r = self.review()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn('Verdict: PASS', r.stdout)
        facts = json.loads((self.latest_packet() / 'github/pr-test-repo-1/verification.json').read_text())
        self.assertEqual(facts['CI'], 'PASS')

    def test_required_failure_semantic_exit_is_valid_evidence(self):
        self.config.update(checks=[{'name': 'Unit tests', 'bucket': 'fail'}], checks_rc=1, verdict='CHANGES_REQUIRED', report_ci='FAIL', report_tests='FAIL')
        r = self.review()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        facts = json.loads((self.latest_packet() / 'evidence.json').read_text())
        self.assertTrue(facts['complete'])
        row = next(row for row in facts['observations'] if row['key'].endswith('.required-checks'))
        self.assertEqual(row['exitCode'], 1)

    def test_pending_required_ci_cannot_support_pass(self):
        self.config.update(checks=[{'name': 'Unit tests', 'bucket': 'pending'}], checks_rc=8)
        self.assert_blocked(self.review(), model_expected=True)

    def test_required_check_missing_at_pinned_head_is_blocked(self):
        self.config['required_checks'] = [{'name': 'Another head check', 'bucket': 'pass'}]
        self.assert_blocked(self.review())

    def test_explicit_generic_test_mapping(self):
        self.config.update(checks=[{'name': 'CI / full', 'bucket': 'pass'}])
        self.assert_blocked(self.review(), model_expected=True)
        r = self.review('--test-check', 'CI / full')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        policy = json.loads((self.latest_packet() / 'verification-policy.json').read_text())
        self.assertEqual(policy['testChecks'], ['CI / full'])

    def test_unknown_test_mapping_is_blocked(self):
        self.assert_blocked(self.review('--test-check', 'does not exist'))

    def test_tests_claim_is_validated_even_for_changes_required(self):
        self.config.update(verdict='CHANGES_REQUIRED', checks=[{'name': 'Unit tests', 'bucket': 'pass', 'link': None}])
        self.assert_blocked(self.review(), model_expected=True)
        self.config['report_tests'] = 'UNKNOWN'
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        facts = json.loads((self.latest_packet() / 'github/pr-test-repo-1/verification.json').read_text())
        self.assertEqual(facts['Tests'], 'UNKNOWN')
        self.assertEqual(facts['workflowJobs'], [])

    def test_successful_check_cannot_override_skipped_test_job(self):
        self.config.update(test_jobs=[{'databaseId': 1, 'name': 'Unit tests', 'status': 'completed', 'conclusion': 'skipped'}])
        self.assert_blocked(self.review(), model_expected=True)
        self.config.update(verdict='CHANGES_REQUIRED', report_tests='UNKNOWN')
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_workflow_jobs_are_fetched_and_bound_to_head_run_attempt(self):
        packet = self.packet(self.review('--packet-only'))
        facts = json.loads((packet / 'github/pr-test-repo-1/verification.json').read_text())
        self.assertEqual((facts['testChecks'][0]['runId'], facts['testChecks'][0]['attempt'], facts['testChecks'][0]['headSha']), (10, 1, SHA))
        self.assertTrue(any(call[:3] == ['gh', 'run', 'view'] and '--json' in call and 'databaseId,headSha,attempt,url,jobs' in call for call in self.calls()))
        self.assertIn('not that every test', facts['testEvidenceLimit'])

    def test_missing_wrong_or_duplicate_job_evidence_blocks(self):
        for update in ({'test_jobs_rc': 4}, {'test_job_head_sha': 'b' * 40}, {'test_jobs': []},
                       {'test_run': {'databaseId': 10, 'headSha': None, 'attempt': 1, 'jobs': []}},
                       {'test_jobs': [{'databaseId': 2, 'name': 'Unit tests', 'status': 'completed', 'conclusion': 'success'}]},
                       {'test_jobs': [{'databaseId': 1, 'name': 'other', 'status': 'completed', 'conclusion': 'success'}]}):
            with self.subTest(update=update):
                self.config = update
                self.assert_blocked(self.review())

    def test_rerun_attempt_change_invalidates_previous_success(self):
        self.config['ci_after_review'] = {'test_run_attempt': 2}
        self.assert_blocked(self.review(), model_expected=True)

    def test_named_commit_status_is_not_workflow_job_execution(self):
        self.config.update(checks=[{'name': 'build', 'bucket': 'pass'}],
                           status_pages=[{'sha': SHA, 'total_count': 1, 'statuses': [{'id': 20, 'context': 'Unit tests', 'state': 'success'}]}])
        self.assert_blocked(self.review(), model_expected=True)

    def test_non_test_substrings_cannot_support_pass(self):
        for name in ('attestation', 'inspection'):
            with self.subTest(name=name):
                self.config = {'checks': [{'name': name, 'bucket': 'pass'}]}
                self.assert_blocked(self.review(), model_expected=True)
                facts = json.loads((self.latest_packet() / 'github/pr-test-repo-1/verification.json').read_text())
                self.assertEqual(facts['CI'], 'PASS')
                self.assertEqual(facts['Tests'], 'UNKNOWN')
                self.assertEqual(facts['testChecks'], [])

    def test_test_job_tokens_are_classified(self):
        for name in ('Unit tests', 'test_web', 'test:unit', 'vitest', 'pytest-3.11', 'Jest', 'playwright / chromium', 'spec'):
            with self.subTest(name=name):
                self.config = {'checks': [{'name': name, 'bucket': 'pass'}]}
                result = self.review()
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                facts = json.loads((self.latest_packet() / 'github/pr-test-repo-1/verification.json').read_text())
                self.assertEqual(facts['Tests'], 'PASS')
                self.assertEqual([check['name'] for check in facts['testChecks']], [name])

    def test_review_gate_is_never_excluded(self):
        self.config.update(checks=[{'name': 'Unit tests', 'bucket': 'pass'}], status_pages=[{'sha': SHA, 'total_count': 1, 'statuses': [{'id': 99, 'context': 'review:passed', 'state': 'pending'}]}], required_checks=[{'name': 'Unit tests', 'bucket': 'pass'}, {'name': 'review:passed', 'bucket': 'pending'}])
        self.assert_blocked(self.review(), model_expected=True)
        facts = json.loads((self.latest_packet() / 'github/pr-test-repo-1/verification.json').read_text())
        self.assertEqual(facts['CI'], 'UNKNOWN')
        self.assertEqual(facts['possiblePostReviewConditions'][0]['name'], 'review:passed')

    def test_report_commit_mismatch_is_never_recorded_pass(self):
        self.config['report_sha'] = 'b' * 40
        self.assert_blocked(self.review(), model_expected=True)

    def test_report_invalid_fields_and_unmet_criteria_are_rejected(self):
        report = 'Issue: CAF-999 Offline fixture\n\nVerdict: PASS\n\nSummary:\nfixture\n\nAcceptance Criteria:\n\n* [x] fixture\n\nFindings:\n\n* なし\n\nRequired Changes:\n\n* なし\n\nVerification:\n\n* PR: https://github.com/test/repo/pull/1\n* Commit: ' + SHA + '\n* CI: PASS\n* Tests: PASS\n* Reviewer: fixture-reviewer\n* Involvement: NOT_INVOLVED\n* Review Mode: fixed-pr\n'
        for malformed in (report.replace('CAF-999', 'CAF-998'), report.replace('test/repo/pull/1', 'test/repo/pull/2'), report.replace('* CI: PASS', '* CI: UNKNOWN'), report.replace('* Tests: PASS', '* Tests: PASS\n* Tests: UNKNOWN'), report.replace('* [x]', '* [?]'), report.replace('* [x]', '* [ ]'), report.replace('Verdict: PASS', 'Verdict: PASS | BLOCKED')):
            with self.subTest(report=malformed):
                self.config['report'] = malformed
                self.assert_blocked(self.review(), model_expected=True)

    def test_heading_words_inside_title_and_body_do_not_change_sections(self):
        title = 'Verification: smoke test / Findings: note / Required Changes: label'
        self.config = {'issue_title': title}
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.config['report'] = result.stdout.replace('\nfixture\n', '\nSummary mentions Verification: and Findings: as literal text.\n', 1).replace('* [x] fixture', '* [x] Handle Required Changes: and Verification: literal labels')
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('Verdict: PASS', result.stdout)

    def test_all_pass_criteria_must_use_exact_satisfied_item_format(self):
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        valid = result.stdout
        for criteria in ('* [x] AC1\n- [?] AC2', '* [x] AC1\n1. [?] AC2', '* [x] AC1\n  * [?] AC2',
                         '* [x] AC1\n- [x] AC2', '* [x] AC1\nadditional unsupported criteria text', ''):
            with self.subTest(criteria=criteria):
                self.config = {'report': valid.replace('* [x] fixture', criteria)}
                self.assert_blocked(self.review(), model_expected=True)

    def test_explicit_run_jobs_and_log_are_required(self):
        for cfg in ({'run_jobs_rc': 4}, {'run_log_rc': 4}, {'run_jobs': [{'total_count': 2, 'jobs': []}]}):
            with self.subTest(cfg=cfg):
                self.config = cfg
                self.assert_blocked(self.review('--run', 'test/repo:1'))

    def test_explicit_run_secret_log_removed_without_echo(self):
        token = 'ghp_' + 's' * 30
        for cfg in ({'run_log': token}, {'run_log': token, 'run_log_partial': True, 'run_log_rc': 1}):
            with self.subTest(cfg=cfg):
                self.config = cfg
                self.assert_blocked(self.review('--run', 'test/repo:1'))
                self.assertFalse((self.latest_packet() / 'github/runs/test-repo-1/log.txt').exists())
                self.assertNotIn(token, (self.latest_packet() / 'evidence.json').read_text())

    def test_run_snapshot_keeps_its_own_head(self):
        self.config['run_head_sha'] = 'e' * 40
        p = self.packet(self.review('--packet-only', '--run', 'test/repo:1'))
        self.assertTrue(json.loads((p / 'evidence.json').read_text())['complete'])
        jobs = [json.loads(row) for row in (p / 'github/runs/test-repo-1/jobs.jsonl').read_text().splitlines()]
        self.assertEqual(jobs[0]['head_sha'], 'e' * 40)


if __name__ == '__main__':
    unittest.main(verbosity=2)
