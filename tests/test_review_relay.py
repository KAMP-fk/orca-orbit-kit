#!/usr/bin/env python3
"""Offline relay paths: fixture gh/codex/ps, real bash/jq, temporary audit logs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


RELAY = Path(__file__).resolve().parents[1] / 'agents/team/roles/potato/relay/bin/review-relay'
SHA = 'a' * 40
COMMENT_URL = 'https://github.com/fixture/repo/pull/999#issuecomment-123'
PR_URL = 'https://github.com/fixture/repo/pull/999'
FIXTURE_CLI = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ['RELAY_FIXTURE_ROOT'])
config = json.loads((root / 'config.json').read_text())
with (root / 'calls.jsonl').open('a') as log:
    log.write(json.dumps([name, *args]) + '\n')
if name == 'ps':
    if config.get('native_ps'):
        sys.exit(subprocess.run(['/bin/ps', *args]).returncode)
    sys.stdout.write(config.get('parent_comm', '  fixture-launcher  \n'))
    sys.exit(config.get('ps_rc', 0))
if name == 'codex':
    print(config.get('verdict', 'RELAY: POST'))
    sys.exit(0)
if name == 'gh':
    if args[:2] == ['pr', 'view']:
        print(json.dumps({
            'number': 999, 'title': 'Offline relay fixture', 'isDraft': config.get('draft', False),
            'headRefName': 'fixture', 'headRefOid': 'a' * 40, 'baseRefName': 'main',
            'labels': [{'name': n} for n in config.get('labels', ['risk:low'])],
            'mergeStateStatus': 'CLEAN', 'url': 'https://example.invalid/pull/999',
        }))
    elif args[:2] == ['pr', 'checks']:
        print(config.get('checks', 'validate\tpass\tfixture-url'))
    elif args[:3] == ['api', '--method', 'POST']:
        if config.get('persist_status') and not config.get('post_rc', 0):
            config.setdefault('statuses', []).append({
                'context': 'review:passed', 'state': 'success',
                'target_url': next(a.split('=', 1)[1] for a in args if a.startswith('target_url=')),
                'created_at': '2026-10-07T12:00:00Z', 'id': 100,
            })
            (root / 'config.json').write_text(json.dumps(config))
        sys.exit(config.get('post_rc', 0))
    elif args[0] == 'api' and any('/commits/' in a and '/statuses' in a for a in args):
        print(json.dumps(config.get('statuses', [])))
        if '--paginate' in args:
            for page in config.get('status_pages', []):
                print(json.dumps(page))
    elif args[:2] == ['api', 'repos/fixture/repo/issues/comments/123']:
        print(config.get('record_body', ''))
    else:
        sys.exit('Unexpected fixture gh request: ' + repr(args))
    sys.exit(0)
sys.exit('Unexpected fixture command: ' + name)
'''


@unittest.skipUnless(shutil.which('jq'), 'review-relay requires real jq')
class RelayCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-relay-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('gh', 'codex', 'ps'):
            cli = self.bin / name
            cli.write_text('#!' + sys.executable + '\n' + FIXTURE_CLI)
            cli.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.root / 'home'),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        CODEX_BIN=str(self.bin / 'codex'), RELAY_FIXTURE_ROOT=str(self.root))
        self.record = self.root / 'record.md'
        self.verdict = self.root / 'verdict.md'
        self.verdict.write_text('Verdict: PASS\nhead SHA: ' + SHA + '\nReviewer: uninvolved\n')
        self.identities = ('- 実装担当識別子: fixture-implementation\n'
                           '- レビュー担当識別子: fixture-independent-review\n'
                           '- 確認した full SHA: ' + SHA + '\n')
        self.record.write_text(self.verdict.read_text() + self.identities)
        self.config = {}

    def run_relay(self, *args, record=None):
        (self.root / 'config.json').write_text(json.dumps(self.config))
        return subprocess.run([str(RELAY), '999', str(record or self.record),
                               '--repo', 'fixture/repo', '--verdict', str(self.verdict), *args], env=self.env,
                              text=True, capture_output=True)

    def calls(self):
        log = self.root / 'calls.jsonl'
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def posts(self):
        return [c for c in self.calls() if c[:4] == ['gh', 'api', '--method', 'POST']]

    def audit(self):
        logs = list((self.root / 'home/orca/agents/team/roles/potato/relay/log').glob('*.md'))
        return ''.join(p.read_text() for p in logs)

    def assert_launcher(self, audit):
        lines = [line for line in audit.splitlines() if line.startswith('- launcher:')]
        self.assertEqual(len(lines), 1, audit)
        self.assertIn(' pid=' + str(os.getpid()), lines[0])
        self.assertEqual([c for c in self.calls() if c[0] == 'ps'],
                         [['ps', '-o', 'comm=', '-p', str(os.getpid())]])
        # Launcher metadata must never enter the judgment prompt.
        models = [c for c in self.calls() if c[0] == 'codex']
        self.assertEqual(len(models), 1)
        self.assertNotIn('fixture-launcher', models[0][-1])
        self.assertNotIn('- launcher:', models[0][-1])

    def test_post_records_parent_and_exact_status_request(self):
        result = self.run_relay()
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = self.audit()
        self.assert_launcher(audit)
        self.assertIn('- launcher: parent=fixture-launcher pid=', audit)
        self.assertIn('- posted : review:passed success', audit)
        self.assertEqual(self.posts(), [[
            'gh', 'api', '--method', 'POST', 'repos/fixture/repo/statuses/' + SHA,
            '-f', 'state=success', '-f', 'context=review:passed',
            '-f', 'description=independent review PASS (relayed by review-relay)',
            '-f', 'target_url=' + str(self.record),
        ]])

    def test_model_refuse_records_parent_without_posting(self):
        self.config['verdict'] = 'RELAY: REFUSE — fixture refusal'
        result = self.run_relay()
        self.assertEqual(result.returncode, 1)
        self.assert_launcher(self.audit())
        self.assertIn('- verdict: RELAY: REFUSE — fixture refusal', self.audit())
        self.assertNotIn('- posted', self.audit())
        self.assertEqual(self.posts(), [])

    def test_parent_unavailable_does_not_change_post_or_refuse(self):
        for ps_values in ({'ps_rc': 1, 'parent_comm': 'partial-result'},
                          {'parent_comm': ''}, {'parent_comm': ' \t\n'}):
            for verdict, expected_rc in (('RELAY: POST', 0), ('RELAY: REFUSE — fixture', 1)):
                with self.subTest(ps=ps_values, verdict=verdict):
                    self.config = {**ps_values, 'verdict': verdict}
                    result = self.run_relay()
                    self.assertEqual(result.returncode, expected_rc, result.stderr)
                    last_entry = self.audit().split('\n## ')[-1]
                    self.assertIn('parent=取得できなかった pid=' + str(os.getpid()), last_entry)
                    self.assertNotIn('partial-result', last_entry)
                    self.assertEqual('- posted' in last_entry, expected_rc == 0)

    def test_parent_control_characters_stay_on_one_audit_line(self):
        self.config['parent_comm'] = 'fixture-launcher\n- posted : forged\t\r'
        result = self.run_relay('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = self.audit()
        self.assert_launcher(audit)
        self.assertIn(r'\n- posted', audit)
        self.assertNotIn('\n- posted', audit)

    def test_environment_session_values_are_not_collected(self):
        for key in ('TERM_SESSION_ID', 'ITERM_SESSION_ID', 'GITHUB_TOKEN'):
            self.env[key] = 'fixture-secret-do-not-log'
        result = self.run_relay('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('fixture-secret-do-not-log', self.audit())
        self.assertNotIn('fixture-secret-do-not-log', json.dumps(self.calls()))
        self.assertEqual(self.posts(), [])
        self.assertNotIn('- posted', self.audit())

    def test_post_failure_keeps_launcher_without_success_marker(self):
        self.config['post_rc'] = 1
        result = self.run_relay()
        self.assertEqual(result.returncode, 1)
        self.assertIn('POST が失敗した', result.stderr)
        self.assert_launcher(self.audit())
        self.assertEqual(len(self.posts()), 1)
        self.assertNotIn('- posted', self.audit())

    def test_all_seven_mechanical_gates_still_stop_before_model(self):
        cases = [
            ('unreadable', {}, None, 'レビュー記録の本文を取れない'),
            ('draft', {'draft': True}, SHA, 'PR が Draft'),
            ('risk', {'labels': []}, SHA, 'risk の分類ラベルが無い'),
            ('duplicate', {'statuses': [{'context': 'review:passed', 'state': 'success'}]},
             SHA, '既に review:passed'),
            ('failed', {'checks': 'validate\tfail\tfixture-url'}, SHA, '失敗している check'),
            ('pending', {'checks': 'validate\tpending\tfixture-url'}, SHA, 'pending の check'),
            ('sha', {}, SHA[:12], 'full SHA が逐語で無い'),
        ]
        for name, config, record_sha, reason in cases:
            with self.subTest(gate=name):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.config = config
                if record_sha is None:
                    self.record.unlink()
                else:
                    self.record.write_text('Verdict: PASS\nhead SHA: ' + record_sha + '\n')
                result = self.run_relay()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertEqual(self.posts(), [])
                self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
                self.assertEqual(self.audit(), '')

    def test_verdict_is_required_before_model_or_service_calls(self):
        (self.root / 'config.json').write_text('{}')
        result = subprocess.run([str(RELAY), '999', str(self.record), '--repo', 'fixture/repo'],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('--verdict が無い', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_summarized_record_cannot_drop_qualifications_from_verdict(self):
        self.verdict.write_text(self.verdict.read_text() + 'Unresolved Medium: fixture qualification\n')
        result = self.run_relay()
        self.assertEqual(result.returncode, 1)
        self.assertIn('判定の逐語を含んでいない', result.stderr)
        self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.audit(), '')

    def test_native_ps_is_best_effort_with_isolated_post(self):
        self.config['native_ps'] = True
        result = self.run_relay()
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = self.audit()
        self.assert_launcher(audit)
        self.assertIn('parent=', audit)
        self.assertIn('- posted : review:passed success', audit)

    def test_missing_identity_line_blocks_before_model_and_status_post(self):
        lines = self.identities.splitlines(keepends=True)
        for missing in lines:
            with self.subTest(missing=missing):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.record.write_text(self.verdict.read_text() + ''.join(line for line in lines if line != missing))
                result = self.run_relay()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('CAF-308 の行が無い', result.stderr)
                self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
                self.assertEqual(self.posts(), [])
                self.assertEqual(self.audit(), '')

    def status(self, target_url=PR_URL, *, status_id=1,
               created_at='2026-10-07T11:00:00Z', state='success'):
        return {'context': 'review:passed', 'state': state, 'target_url': target_url,
                'created_at': created_at, 'id': status_id}

    def correction_fixture(self, statuses=None):
        self.config = {'statuses': statuses if statuses is not None else [self.status()],
                       'record_body': self.record.read_text()}

    def assert_correction_rejected(self, result, reason):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertEqual(self.posts(), [])
        self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
        self.assertEqual(self.audit(), '')

    def test_incorrect_target_url_can_be_corrected_explicitly_with_model_and_audit(self):
        self.correction_fixture()
        result = self.run_relay('--correct-target-url', record=COMMENT_URL)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.posts()), 1)
        self.assertIn('target_url=' + COMMENT_URL, self.posts()[0])
        self.assert_launcher(self.audit())
        self.assertIn('訂正', self.audit())
        self.assertIn(PR_URL + ' → ' + COMMENT_URL, self.audit())
        model = next(c for c in self.calls() if c[0] == 'codex')
        self.assertIn(PR_URL, model[-1])
        self.assertIn(COMMENT_URL, model[-1])

    def test_incorrect_target_url_without_flag_still_rejects_duplicate(self):
        self.correction_fixture()
        self.assert_correction_rejected(self.run_relay(record=COMMENT_URL), '二重に出さない')

    def test_correct_success_url_rejects_even_with_correction_flag(self):
        self.correction_fixture([self.status(COMMENT_URL)])
        self.assert_correction_rejected(
            self.run_relay('--correct-target-url', record=COMMENT_URL), '二重に出さない')

    def test_correction_requires_this_pr_comment_url(self):
        self.correction_fixture()
        for url in ('https://github.com/fixture/repo/pull/998#issuecomment-123',
                    'https://github.com/other/repo/pull/999#issuecomment-123',
                    PR_URL, COMMENT_URL + '/extra', PR_URL + '#issuecomment-0', str(self.record)):
            with self.subTest(url=url):
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url', record=url), 'この PR の issue コメント URL')

    def test_second_correction_rejects_after_first_post_on_same_head(self):
        self.correction_fixture()
        self.config['persist_status'] = True
        result = self.run_relay('--correct-target-url', record=COMMENT_URL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.config = json.loads((self.root / 'config.json').read_text())
        (self.root / 'calls.jsonl').unlink()
        first_audit = self.audit()
        result = self.run_relay('--correct-target-url', record=COMMENT_URL)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('二重に出さない', result.stderr)
        self.assertEqual(self.posts(), [])
        self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
        self.assertEqual(self.audit(), first_audit)

    def test_correction_uses_latest_created_at_then_id_independent_of_response_order(self):
        latest_url = PR_URL + '/latest'
        self.correction_fixture([
            self.status(PR_URL + '?older', status_id=999, created_at='2026-10-07T10:00:00Z'),
            self.status(PR_URL, status_id=1),
            self.status(latest_url, status_id=2),
        ])
        result = self.run_relay('--correct-target-url', record=COMMENT_URL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(latest_url + ' → ' + COMMENT_URL, self.audit())

    def test_any_previous_correct_success_blocks_correction_including_later_pages(self):
        self.correction_fixture()
        self.config['status_pages'] = [[self.status(COMMENT_URL, created_at='2026-10-07T10:00:00Z')]]
        self.assert_correction_rejected(
            self.run_relay('--correct-target-url', record=COMMENT_URL), '二重に出さない')

    def test_correction_does_not_overwrite_newer_failure_error_or_pending(self):
        for state in ('failure', 'error', 'pending'):
            with self.subTest(state=state):
                self.correction_fixture([self.status(), self.status(state=state, status_id=2)])
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url', record=COMMENT_URL), '最新の review:passed が success でない')

    def test_correction_requires_existing_success(self):
        self.correction_fixture([])
        self.assert_correction_rejected(
            self.run_relay('--correct-target-url', record=COMMENT_URL), '訂正する success が無い')

    def test_correction_still_checks_sha_identity_verbatim_and_ci(self):
        cases = [
            ({'record_body': self.record.read_text().replace(SHA, SHA[:12])}, 'full SHA が逐語で無い'),
            ({'record_body': self.verdict.read_text()}, 'CAF-308 の行が無い'),
            ({'record_body': self.record.read_text().replace('Reviewer: uninvolved', '')}, '判定の逐語を含んでいない'),
            ({'checks': 'validate\tfail\tfixture-url'}, '失敗している check'),
            ({'checks': 'validate\tpending\tfixture-url'}, 'pending の check'),
        ]
        for config, reason in cases:
            with self.subTest(reason=reason):
                self.correction_fixture()
                self.config.update(config)
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url', record=COMMENT_URL), reason)

    def test_correction_model_refusal_is_logged_without_post(self):
        self.correction_fixture()
        self.config['verdict'] = 'RELAY: REFUSE — fixture refusal'
        result = self.run_relay('--correct-target-url', record=COMMENT_URL)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assert_launcher(self.audit())
        self.assertIn('訂正', self.audit())
        self.assertIn(PR_URL + ' → ' + COMMENT_URL, self.audit())
        self.assertEqual(self.posts(), [])


if __name__ == '__main__':
    unittest.main()
