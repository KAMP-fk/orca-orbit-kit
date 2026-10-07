#!/usr/bin/env python3
"""Role and independence declarations through the real launcher, with offline CLIs."""
import json
import importlib.util
import subprocess
import re
from pathlib import Path
import unittest

import test_agent_refactor as fixtures


class ReviewerInvolvementContractTests(unittest.TestCase):
    def test_acceptance_involvement_scope_and_summary_declaration(self):
        root = fixtures.REPO_ROOT / 'agents/team/roles/potato'
        scope = '方針・実装・修正・指摘対応・中継依頼'
        declaration = f'本セッションは対象の{scope}のいずれにも関与していない。'
        skill = (root / 'acceptance/skill/SKILL.md').read_text()
        template, rules = skill.split('### 記入規則', 1)
        summary = template.split('Summary:', 1)[1].split('Acceptance Criteria:', 1)[0]
        self.assertIn('<関与の表明（未関与なら定型文）>', summary)
        self.assertNotIn(declaration, summary)
        self.assertIn(f'**Involvement** は対象の{scope}への関与', rules)
        self.assertIn('すべてに関与していない場合だけ `NOT_INVOLVED`', rules)
        self.assertIn(declaration, rules)
        self.assertIn('何に関与したか', rules)
        self.assertIn('何を確認できないか', rules)
        for relative in ('acceptance/README.md', 'acceptance/references/legacy-pipeline.md',
                         'acceptance/claude/agent.md', 'acceptance/claude/legacy-agent.md',
                         'acceptance/lib/backend.sh', 'skill/SKILL.md'):
            with self.subTest(path=relative):
                content = (root / relative).read_text()
                self.assertIn(scope, content)
                self.assertIn(declaration, content)

    def test_declaration_covers_every_relay_gate_three_involvement_term(self):
        root = fixtures.REPO_ROOT / 'agents/team/roles/potato'
        relay = (root / 'relay/bin/review-relay').read_text()
        match = re.search(r'^3\. レビュー記録に、レビュアーが(.+?)に関与していないことが書かれていること。$', relay, re.MULTILINE)
        self.assertIsNotNone(match, 'relay gate three involvement clause is missing')
        declaration = '本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。'
        declaration_terms = set(declaration.split('対象の', 1)[1].split('のいずれにも', 1)[0].split('・'))
        for term in match.group(1).split('・'):
            with self.subTest(term=term):
                self.assertTrue(term)
                self.assertIn(term, declaration_terms)


class ReviewerRoleTests(unittest.TestCase):
    setUp = fixtures.OfflineCase.setUp
    run_cli = fixtures.OfflineCase.run_cli
    review = fixtures.OfflineCase.review
    calls = fixtures.OfflineCase.calls

    def packet(self):
        return max((self.root / 'reviewer-state/packets/CAF-999').iterdir(),
                   key=lambda p: p.stat().st_mtime_ns)

    def valid_report(self):
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def reject(self, report):
        self.config['report'] = report
        result = self.review()
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertNotIn('Verdict: PASS', result.stdout)
        self.assertIn('Verdict: BLOCKED', result.stdout)
        self.assertEqual((self.packet() / 'verdict.raw').read_text(), report + '\n')

    def test_explicit_pr_is_fixed_review_with_approved_backend(self):
        for backend in ('claude',):
            with self.subTest(backend=backend):
                result = self.review('--backend', backend)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                packet = self.packet()
                self.assertEqual(json.loads((packet / 'meta.json').read_text())['reviewMode'], 'fixed-pr')
                self.assertIn('* Review Mode: fixed-pr', result.stdout)
                context = json.loads(self.model_context_log.read_text().splitlines()[-1])
                prompt = context['argv'][-1]
                self.assertIn('- Review Mode: fixed-pr', prompt)
                self.assertIn('Involvement は対象の方針・実装・修正・指摘対応・中継依頼への関与', prompt)
                self.assertIn('本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。', prompt)
                if backend == 'claude':
                    self.assertIn('現行正本が定める R 段', prompt)
                else:
                    self.assertIn('concafe の正式 R 段には該当しない', prompt)
                    self.assertNotIn('現行正本が定める R 段', prompt)
                self.assertNotIn('Astra high 等の最終ゲートは維持する', prompt)

    def test_implicit_pr_is_generic_and_does_not_upgrade_to_r(self):
        self.config['issue_description'] = 'Acceptance Criteria: fixture https://github.com/test/repo/pull/1'
        result = self.run_cli(fixtures.REVIEWER, 'CAF-999', '--backend', 'claude')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        packet = self.packet()
        self.assertEqual(json.loads((packet / 'meta.json').read_text())['reviewMode'], 'issue')
        self.assertIn('* Review Mode: issue', result.stdout)
        context = json.loads(self.model_context_log.read_text().splitlines()[-1])
        self.assertIn('自動探索で PR の証拠を取得しても固定 PR の独立 R 段へ昇格しない', context['argv'][-1])

    def test_missing_declarations_are_rejected_without_launcher_filling_them(self):
        report = self.valid_report()
        for line in ('* Reviewer: fixture-reviewer\n', '* Involvement: NOT_INVOLVED\n',
                     '* Review Mode: fixed-pr\n'):
            with self.subTest(line=line):
                self.reject(report.replace(line, ''))
                self.assertNotIn(line, (self.packet() / 'verdict.md').read_text())

    def test_involved_unknown_and_invalid_declarations_cannot_pass(self):
        report = self.valid_report()
        for value in ('INVOLVED', 'UNKNOWN', 'not_involved', '<involvement>'):
            with self.subTest(value=value):
                self.reject(report.replace('Involvement: NOT_INVOLVED', 'Involvement: ' + value))

    def test_missing_identity_and_duplicate_declaration_are_rejected(self):
        report = self.valid_report()
        for malformed in (*(report.replace('Reviewer: fixture-reviewer', 'Reviewer: ' + identity)
                            for identity in ('UNKNOWN', 'unknown', '-', 'N/A', '  ', '不明', 'なし', '<reviewer自身の識別名>')),
                          report + '* Involvement: NOT_INVOLVED\n'):
            self.reject(malformed)

    def test_non_involvement_sentence_requires_not_involved_for_every_verdict(self):
        declaration = '本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。'
        report = self.valid_report()
        for verdict in ('CHANGES_REQUIRED', 'BLOCKED', 'PASS'):
            for involvement in ('INVOLVED', 'UNKNOWN', 'NOT_INVOLVED'):
                with self.subTest(verdict=verdict, involvement=involvement):
                    candidate = report.replace('Verdict: PASS', 'Verdict: ' + verdict).replace(
                        'Involvement: NOT_INVOLVED', 'Involvement: ' + involvement)
                    if involvement == 'NOT_INVOLVED':
                        self.config['report'] = candidate
                        result = self.review()
                        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                        self.assertIn('Verdict: ' + verdict, result.stdout)
                    else:
                        self.reject(candidate)
                        self.assertIn('non-involvement declaration contradicts Involvement',
                                      (self.packet() / 'verdict-validation.err').read_text())

    def test_not_involved_requires_declaration_in_summary_for_every_verdict(self):
        declaration = '本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。'
        report = self.valid_report()
        for verdict in ('PASS', 'CHANGES_REQUIRED', 'BLOCKED'):
            for location in ('summary', 'missing', 'findings'):
                with self.subTest(verdict=verdict, location=location):
                    candidate = report.replace('Verdict: PASS', 'Verdict: ' + verdict)
                    if location != 'summary':
                        candidate = candidate.replace(declaration + '\n', '')
                    if location == 'findings':
                        candidate = candidate.replace('Findings:\n', 'Findings:\n' + declaration + '\n')
                    if location == 'summary':
                        self.config['report'] = candidate
                        result = self.review()
                        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                        self.assertIn('Verdict: ' + verdict, result.stdout)
                    else:
                        self.reject(candidate)
                        self.assertIn('NOT_INVOLVED requires non-involvement declaration in Summary',
                                      (self.packet() / 'verdict-validation.err').read_text())

    def test_summary_involvement_placeholder_is_rejected(self):
        report = self.valid_report()
        for verdict in ('PASS', 'CHANGES_REQUIRED', 'BLOCKED'):
            with self.subTest(verdict=verdict):
                self.reject(report.replace('Verdict: PASS', 'Verdict: ' + verdict).replace(
                    'Summary:\n', 'Summary:\n<関与の表明（未関与なら定型文）>\n'))

    def test_report_cannot_change_launcher_role(self):
        self.reject(self.valid_report().replace('Review Mode: fixed-pr', 'Review Mode: issue'))

    def test_known_generic_disclaimer_cannot_be_kept_with_fixed_pr_pass(self):
        report = self.valid_report()
        for summary in ('この PASS は固定 SHA の最終独立レビューの代わりになりません。',
                        'この PASS は concafe の固定 SHA 最終独立レビューや\n'
                        '`review:passed` status の代わりにならない。',
                        'この PASS は最終独立レビューの代わりにはなりません。',
                        'この PASS は concafe の review:passed の根拠にはならない。',
                        'この汎用 Issue reviewer の PASS は、concafe の固定 SHA 最終独立レビュー・署名 verdict と別の条件。',
                        'この PASS は最終ゲート充足へ転用しない。'):
            with self.subTest(summary=summary):
                self.reject(report.replace('\nfixture\n', '\n' + summary + '\n', 1))

    def test_honest_evidence_limit_does_not_invalidate_fixed_review(self):
        report = self.valid_report()
        self.config['report'] = report.replace('\nfixture\n',
            '\nrepo 外の現物はこの判定の対象外。署名の充足を主張しない。\n', 1)
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual((self.packet() / 'verdict.raw').read_text(),
                         (self.packet() / 'verdict.md').read_text())

    def test_current_denial_in_findings_is_rejected_but_history_is_allowed(self):
        report = self.valid_report()
        self.reject(report.replace('Findings:\n\n* なし', 'Findings:\n\n* この PASS は最終独立レビューの代わりにはなりません。'))
        self.config['report'] = report.replace('Findings:\n\n* なし', 'Findings:\n\n* [Low] 旧判定には「最終独立レビューの代わりにはなりません」と留保があった。新しい本判定は固定PRのRである。')
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_historical_denial_followed_by_current_recheck_is_allowed(self):
        report = self.valid_report()
        self.config['report'] = report.replace('Findings:\n\n* なし', 'Findings:\n\n* [Low] 旧 verdict は「固定 SHA 最終独立レビューの代わりにならない」と範囲を限定しており、本判定はその後の再確認である。')
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_generic_report_cannot_claim_fixed_pr_mode(self):
        self.config['issue_description'] = 'Acceptance Criteria: fixture https://github.com/test/repo/pull/1'
        result = self.run_cli(fixtures.REVIEWER, 'CAF-999', '--backend', 'claude')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.config['report'] = result.stdout.replace('Review Mode: issue', 'Review Mode: fixed-pr')
        result = self.run_cli(fixtures.REVIEWER, 'CAF-999', '--backend', 'claude')
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('Verdict: BLOCKED', result.stdout)

    def test_unknown_involvement_blocked_keeps_reviewer_name_and_summary(self):
        report = self.valid_report().replace('Verdict: PASS', 'Verdict: BLOCKED')
        self.config['report'] = report.replace('Involvement: NOT_INVOLVED', 'Involvement: UNKNOWN').replace('本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。', '関与の有無を確認できない。')
        result = self.review('--backend', 'claude')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('Reviewer: fixture-reviewer', result.stdout)
        self.assertIn('Involvement: UNKNOWN', result.stdout)
        self.assertIn('Involvement を確認できなければ UNKNOWN', json.loads(self.model_context_log.read_text().splitlines()[-1])['argv'][-1])

    def test_concafe_codex_backend_is_blocked_before_any_model_even_without_probe(self):
        candidates = self.root / 'candidates.json'
        candidates.write_text(json.dumps([{'owner': 'KAMP-fk', 'repo': 'concafe-techo', 'number': 303}]))
        backend = fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib/backend.sh'
        report_lib = fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib/report.sh'
        for probe in ('0', '1'):
            result = self.run_cli(Path('/bin/bash'), '-c', 'source "$1"; source "$2"; CAND="$3"; REVIEW_MODE=fixed-pr; BACKEND=codex; PREFLIGHT="$4"; REVIEWER_NAME=fixture; IDENT=CAF-999; PACKET=""; preflight_backend', '_', str(report_lib), str(backend), str(candidates), probe)
            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            self.assertIn('approved Claude Opus backend', result.stdout)
        self.assertFalse(any(c[0] in ('codex','claude') for c in self.calls()))

    def test_saved_concafe_pass_cannot_use_codex_metadata(self):
        report = self.valid_report()
        packet = self.packet()
        meta_path = packet / 'meta.json'; meta = json.loads(meta_path.read_text())
        meta.update(backend='codex', model='gpt-5.6-sol')
        meta['prCandidates'][0].update(owner='KAMP-fk', repo='concafe-techo')
        meta_path.write_text(json.dumps(meta))
        pr_root = packet / 'github/pr-KAMP-fk-concafe-techo-1'
        (packet / 'github/pr-test-repo-1').rename(pr_root)
        pr_file = pr_root / 'pr.json'; pr = json.loads(pr_file.read_text())
        pr['url'] = 'https://github.com/KAMP-fk/concafe-techo/pull/1'; pr_file.write_text(json.dumps(pr))
        (packet / 'verdict.md').write_text(report.replace('https://github.com/test/repo/pull/1', pr['url']))
        spec = importlib.util.spec_from_file_location('evidence', fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib/evidence.py')
        evidence = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)
        with self.assertRaisesRegex(Exception, 'approved Claude Opus backend/model'):
            evidence.validate_verdict(packet)
        meta.update(backend='claude', model='claude-opus-5-5')
        meta_path.write_text(json.dumps(meta))
        self.assertEqual(evidence.validate_verdict(packet)['verdict'], 'PASS')

    def test_positive_role_statements_and_evidence_limits_are_not_denials(self):
        spec = importlib.util.spec_from_file_location('evidence', fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib/evidence.py')
        evidence = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)
        examples = [
            ('固定 SHA の review:passed 用 R として確認\n#279 のとおり job 成功は job 内の全テスト実行までは満たさない', ''),
            ('固定 SHA の最終独立レビューとして全 AC を確認し、満たさない項目は無かった。', ''),
            ('本判定は固定 full head SHA の R', 'Findings:\n\n旧判定には「最終独立レビューの代わりにはなりません」と留保があった。'),
            ('本判定は最終独立レビューとして、署名 verdict など別の条件を要求しない', ''),
            ('本判定は固定 SHA の R', 'Acceptance Criteria:\n\n* [x] review:passed を満たさない場合はhold\n* [x] 全ACを確認'),
        ]
        for summary, other in examples:
            with self.subTest(summary=summary):
                self.assertFalse(evidence.disclaims_fixed_review_role('Summary:\n' + summary + '\n\n' + other, summary))

    def test_candidate_classification_error_cannot_launch_model(self):
        candidates = self.root / 'candidates.json'; candidates.write_text('{')
        backend = fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib/backend.sh'
        report_lib = fixtures.REPO_ROOT / 'agents/team/roles/potato/acceptance/lib/report.sh'
        result = self.run_cli(Path('/bin/bash'), '-c', 'source "$1"; source "$2"; CAND="$3"; REVIEW_MODE=fixed-pr; BACKEND=codex; PREFLIGHT=0; REVIEWER_NAME=fixture; IDENT=CAF-999; PACKET=""; preflight_backend', '_', str(report_lib), str(backend), str(candidates))
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn('cannot classify fixed-pr model policy', result.stdout)
        self.assertFalse(any(c[0] in ('codex', 'claude') for c in self.calls()))

    def test_concafe_codex_real_launcher_path_stops_before_model(self):
        self.config['pr_url'] = 'https://github.com/KAMP-fk/concafe-techo/pull/1'
        result = self.run_cli(fixtures.REVIEWER, 'CAF-999', '--pr', 'KAMP-fk/concafe-techo#1', '--backend', 'codex', '--no-preflight')
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn('Opus 5.5 / high に固定', result.stderr)
        self.assertFalse(self.calls())

    def test_involved_reviewer_can_return_blocked_without_forged_independence(self):
        report = self.valid_report().replace('Verdict: PASS', 'Verdict: BLOCKED')
        self.config['report'] = report.replace('Involvement: NOT_INVOLVED', 'Involvement: INVOLVED').replace('本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。', '対象の実装に関与した。')
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('* Involvement: INVOLVED', result.stdout)
        self.assertIn('Verdict: BLOCKED', result.stdout)


if __name__ == '__main__':
    unittest.main()
