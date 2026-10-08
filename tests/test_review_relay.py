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
        sys.exit(config.get('statuses_rc', 0))
    elif args[0] == 'api' and args[1].endswith('/issues/comments/123'):
        comment = config.get('comment', {
            'html_url': 'https://github.com/fixture/repo/pull/999#issuecomment-123',
            'issue_url': 'https://api.github.com/repos/fixture/repo/issues/999',
            'id': 123, 'body': config.get('record_body', ''),
        })
        if '-q' in args:
            print(comment.get('body', '') if isinstance(comment, dict) else '')
        else:
            print(json.dumps(comment))
        sys.exit(config.get('comment_rc', 0))
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

    def run_relay(self, *args, record=None, repo='fixture/repo'):
        config = dict(self.config)
        config.setdefault('record_body', self.record.read_text() if self.record.exists() else '')
        (self.root / 'config.json').write_text(json.dumps(config))
        return subprocess.run([str(RELAY), '999', str(record or COMMENT_URL),
                               '--repo', repo, '--verdict', str(self.verdict), *args], env=self.env,
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
            '-f', 'target_url=' + COMMENT_URL,
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

    def test_listed_mechanical_gates_still_stop_before_model_in_both_draft_states(self):
        cases = [
            ('unreadable', {}, None, 'レビュー記録の本文を取れない'),
            ('risk', {'labels': []}, SHA, 'risk の分類ラベルが無い'),
            ('duplicate', {'statuses': [{'context': 'review:passed', 'state': 'success'}]},
             SHA, '既に review:passed'),
            ('failed', {'checks': 'validate\tfail\tfixture-url'}, SHA, '失敗している check'),
            ('pending', {'checks': 'validate\tpending\tfixture-url'}, SHA, 'pending の check'),
            ('sha', {}, SHA[:12], 'full SHA が逐語で無い'),
        ]
        for draft in (False, True):
            for name, config, record_sha, reason in cases:
                with self.subTest(gate=name, draft=draft):
                    (self.root / 'calls.jsonl').unlink(missing_ok=True)
                    self.config = dict(config, draft=draft)
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

    def test_draft_with_either_risk_label_passes_the_mechanical_gates(self):
        # T4 2026-10-08: a Draft is relayed for risk:low as well as risk:high.
        for label in ('risk:low', 'risk:high'):
            with self.subTest(label=label):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.config = {'draft': True, 'labels': ['review:required', label, 'other']}
                result = self.run_relay()
                self.assertNotIn('PR が Draft', result.stderr)
                self.assertTrue(any(c[0] == 'codex' for c in self.calls()), result.stdout + result.stderr)

    def draft_skipping_section(self, prompt):
        heading = '## Draft 中の skipping（merge の関門 FULL-CI-GATE へ委ねる扱い）'
        if heading not in prompt:
            return None
        body = prompt.split(heading, 1)[1].split('```', 2)[1]
        return [line for line in body.splitlines() if line]

    def test_draft_skipping_checks_are_delegated_and_can_post(self):
        self.config = {
            'draft': True,
            'checks': ('validate\tpass\tfixture-url\n'
                       'Supabase Preview\tskipping\tfixture-url\n'
                       'bundle-budget\tskipping\tfixture-url\n'
                       'drill\tskipping\tfixture-url'),
        }
        low = 'Low 2: drill が skipped なので未実行。行き先: CAF-999\n'
        self.verdict.write_text(self.verdict.read_text() + low)
        self.record.write_text(self.verdict.read_text() + self.identities)
        result = self.run_relay()
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = next(c[-1] for c in self.calls() if c[0] == 'codex')
        self.assertEqual(self.draft_skipping_section(prompt),
                         ['Supabase Preview', 'bundle-budget', 'drill'])
        self.assertIn(low.strip(), prompt)
        self.assertEqual(len(self.posts()), 1)

    def test_draft_cancelled_check_stops_before_model(self):
        self.config = {'draft': True, 'checks': (
            'drill\tskipping\tfixture-url\nvalidate\tcancelled\tfixture-url')}
        result = self.run_relay()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('失敗している check', result.stderr)
        self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.audit(), '')

    def test_ready_skipping_checks_have_no_delegation_line(self):
        self.config = {'draft': False, 'checks': 'drill\tskipping\tfixture-url',
                       'verdict': 'RELAY: REFUSE — 5. fixture Ready skipping'}
        result = self.run_relay()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        prompt = next(c[-1] for c in self.calls() if c[0] == 'codex')
        self.assertIsNone(self.draft_skipping_section(prompt))
        self.assertIn('drill\tskipping\tfixture-url', prompt)
        self.assertEqual(self.posts(), [])

    def test_draft_delegation_uses_only_exact_skipping_state(self):
        self.config = {'draft': True, 'checks': (
            'drill\tskipping\tfixture-url\n'
            'skipping in name\tpass\tfixture-url\n'
            'other\tskipped\tfixture-url\n'
            'partial\tskipping-extra\tfixture-url')}
        result = self.run_relay('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = next(c[-1] for c in self.calls() if c[0] == 'codex')
        self.assertEqual(self.draft_skipping_section(prompt), ['drill'])

    def test_gate_five_prompt_defers_draft_skipping_and_uses_check_state(self):
        result = self.run_relay('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = next(c[-1] for c in self.calls() if c[0] == 'codex')
        gate_five = prompt.split('5. 事実シートの check に失敗や未完了が無いこと。', 1)[1]
        self.assertIn('事実シートの「Draft 中の skipping（merge の関門 FULL-CI-GATE へ委ねる扱い）」節に'
                      '挙がった check は未完了に数えない。fail / pending / cancelled は従来どおり拒む。',
                      gate_five)
        self.assertIn('判定本文の Low が未実行と書いていても、check の状態で判定する。', gate_five)

    def test_partial_risk_labels_stop_before_model(self):
        for draft in (False, True):
            for labels in (['xrisk:high'], ['risk:lowish'], ['risk:highish'],
                           ['xrisk:low'], ['other', 'risk:lowish', 'review:required']):
                with self.subTest(draft=draft, labels=labels):
                    (self.root / 'calls.jsonl').unlink(missing_ok=True)
                    self.config = {'draft': draft, 'labels': labels}
                    result = self.run_relay()
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('risk の分類ラベルが無い', result.stderr)
                    self.assertEqual(self.posts(), [])
                    self.assertFalse(any(c[0] == 'codex' for c in self.calls()))
                    self.assertEqual(self.audit(), '')

    def test_invalid_draft_value_stops_before_model(self):
        for draft in (None, 'true', 'false', 'invalid', 0, 1, [], {}):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.config = {'draft': draft}
                result = self.run_relay()
                self.assert_correction_rejected(result, 'isDraft が boolean でない')

    def test_comma_containing_risk_labels_stop_before_model(self):
        for draft in (False, True):
            for labels in (['a,risk:low'], ['risk:high,b'], ['a,risk:high,b'],
                           ['other', 'a,risk:low', 'review:required']):
                with self.subTest(draft=draft, labels=labels):
                    (self.root / 'calls.jsonl').unlink(missing_ok=True)
                    self.config = {'draft': draft, 'labels': labels}
                    result = self.run_relay()
                    self.assert_correction_rejected(result, 'risk の分類ラベルが無い')

    def test_draft_without_risk_label_is_still_refused(self):
        self.config = {'draft': True, 'labels': []}
        result = self.run_relay()
        self.assertEqual(result.returncode, 1)
        self.assertIn('risk の分類ラベルが無い', result.stderr)
        self.assertEqual(self.posts(), [])
        self.assertFalse(any(c[0] == 'codex' for c in self.calls()))

    def test_verdict_is_required_before_model_or_service_calls(self):
        (self.root / 'config.json').write_text('{}')
        result = subprocess.run([str(RELAY), '999', str(self.record), '--repo', 'fixture/repo'],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('--verdict が無い', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_summarized_record_cannot_drop_qualifications_from_verdict(self):
        self.verdict.write_text(self.verdict.read_text() + 'Unresolved Medium: fixture qualification\n')
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.config['draft'] = draft
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
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.config['draft'] = draft
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

    def test_comment_response_must_match_this_pr_before_model_in_both_modes(self):
        valid = {'html_url': COMMENT_URL,
                 'issue_url': 'https://api.github.com/repos/fixture/repo/issues/999',
                 'id': 123, 'body': self.record.read_text()}
        cases = [
            ('other-pr', {**valid, 'issue_url': valid['issue_url'].replace('/999', '/998')}),
            ('other-html-url', {**valid, 'html_url': COMMENT_URL.replace('/999', '/998')}),
            ('canonical-repo-case', {**valid, 'html_url': COMMENT_URL.replace('fixture', 'Fixture')}),
            ('other-id', {**valid, 'id': 124}),
            ('missing-id', {k: v for k, v in valid.items() if k != 'id'}),
            ('non-string-body', {**valid, 'body': [valid['body']]}),
            ('missing-body', {k: v for k, v in valid.items() if k != 'body'}),
            ('not-object', [valid]),
        ]
        for flags in ((), ('--correct-target-url',)):
            for name, comment in cases:
                with self.subTest(mode=flags, response=name):
                    (self.root / 'calls.jsonl').unlink(missing_ok=True)
                    self.correction_fixture(None if flags else [])
                    self.config['comment'] = comment
                    self.assert_correction_rejected(
                        self.run_relay(*flags), 'この PR の URL / id / 本文型と一致しない')

    def test_comment_fetch_failure_rejects_in_both_modes(self):
        for flags in ((), ('--correct-target-url',)):
            with self.subTest(mode=flags):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture(None if flags else [])
                # Even a valid partial response must not hide gh's failure.
                self.config['comment_rc'] = 1
                self.assert_correction_rejected(
                    self.run_relay(*flags), 'レビュー記録のコメントを読めない')

    def test_normal_mode_requires_this_pr_comment_url(self):
        for url in (PR_URL, str(self.record),
                    COMMENT_URL.replace('/999', '/998'),
                    COMMENT_URL.replace('fixture/repo', 'other/repo'),
                    PR_URL + '#issuecomment-0', COMMENT_URL + '/extra'):
            with self.subTest(url=url):
                self.assert_correction_rejected(
                    self.run_relay(record=url), 'この PR の issue コメント URL')
                self.assertEqual(self.calls(), [])

    def test_repo_case_must_match_api_comment_urls_in_both_modes(self):
        for flags in ((), ('--correct-target-url',)):
            with self.subTest(mode=flags):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture(None if flags else [])
                self.assert_correction_rejected(
                    self.run_relay(*flags, repo='Fixture/repo',
                                   record=COMMENT_URL.replace('fixture', 'Fixture')),
                    'この PR の URL / id / 本文型と一致しない')

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
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture([self.status(COMMENT_URL)])
                self.config['draft'] = draft
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url', record=COMMENT_URL), '二重に出さない')

    def test_correction_requires_this_pr_comment_url(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture()
                self.config['draft'] = draft
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

    def test_correction_same_timestamp_uses_larger_id_with_newest_first_response(self):
        latest_url = PR_URL + '/latest'
        self.correction_fixture([
            self.status(latest_url, status_id=2),
            self.status(PR_URL, status_id=1),
        ])
        result = self.run_relay('--correct-target-url')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(latest_url + ' → ' + COMMENT_URL, self.audit())

    def test_correction_same_timestamp_newest_failure_first_blocks_stale_success(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture([
                    self.status(state='failure', status_id=2), self.status(status_id=1),
                ])
                self.config['draft'] = draft
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url'), '最新の review:passed が success でない')

    def test_correction_rejects_invalid_status_timestamp_or_id(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                valid = self.status()
                cases = [
                    ('missing-created-at', {k: v for k, v in valid.items() if k != 'created_at'}),
                    ('timezone-offset', {**valid, 'created_at': '2026-10-07T20:00:00+09:00'}),
                    ('missing-id', {k: v for k, v in valid.items() if k != 'id'}),
                    ('fractional-id', {**valid, 'id': 1.5}),
                    ('zero-id', {**valid, 'id': 0}),
                ]
                for name, status in cases:
                    with self.subTest(status=name):
                        (self.root / 'calls.jsonl').unlink(missing_ok=True)
                        self.correction_fixture([status])
                        self.config['draft'] = draft
                        self.assert_correction_rejected(
                            self.run_relay('--correct-target-url'), '日時 / id が不正')

    def test_correction_rejects_unreadable_status_pages(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                cases = [
                    ('first-page-not-array', {'statuses': {'message': 'fixture error'}}),
                    ('later-page-not-array', {'status_pages': [{'message': 'fixture error'}]}),
                    ('gh-failed', {'statuses_rc': 1}),
                ]
                for name, config in cases:
                    with self.subTest(history=name):
                        (self.root / 'calls.jsonl').unlink(missing_ok=True)
                        self.correction_fixture()
                        self.config['draft'] = draft
                        self.config.update(config)
                        self.assert_correction_rejected(
                            self.run_relay('--correct-target-url'), 'status 履歴を読めない')
                        self.assertTrue(any('--paginate' in c for c in self.calls()))

    def test_any_previous_correct_success_blocks_correction_including_later_pages(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture()
                self.config['draft'] = draft
                self.config['status_pages'] = [[self.status(COMMENT_URL, created_at='2026-10-07T10:00:00Z')]]
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url', record=COMMENT_URL), '二重に出さない')

    def test_correction_does_not_overwrite_newer_failure_error_or_pending(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                for state in ('failure', 'error', 'pending'):
                    with self.subTest(state=state):
                        self.correction_fixture([self.status(), self.status(state=state, status_id=2)])
                        self.config['draft'] = draft
                        self.assert_correction_rejected(
                            self.run_relay('--correct-target-url', record=COMMENT_URL), '最新の review:passed が success でない')

    def test_correction_requires_existing_success(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
                self.correction_fixture([])
                self.config['draft'] = draft
                self.assert_correction_rejected(
                    self.run_relay('--correct-target-url', record=COMMENT_URL), '訂正する success が無い')

    def test_correction_still_checks_sha_identity_verbatim_and_ci(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                (self.root / 'calls.jsonl').unlink(missing_ok=True)
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
                        self.config['draft'] = draft
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
