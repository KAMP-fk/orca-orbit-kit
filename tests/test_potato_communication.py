"""Communication-only Potato requests use isolated mail and never call a model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TEAM = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(TEAM / 'lib'))
from potato_communication import communication_plan
import team_mail as mail


class PotatoCommunicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='potato-mail-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'mail with spaces'
        self.item = mail.send(self.root, 'owner', ['potato'], '相互連絡の運用',
                              '受領して返答してください。\n本文は原文のまま。')
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE')}
        self.env['NAMED_TEAM_TASK_DIR'] = str(Path(self.temporary.name) / 'tasks')

    def cli(self, *args):
        return subprocess.run([sys.executable, str(TEAM / 'bin/potato'),
                               '--mail-root', str(self.root), *args],
                              env=self.env, text=True, capture_output=True, timeout=15)

    def snapshot(self):
        return {str(path.relative_to(self.temporary.name)): path.read_bytes()
                for path in Path(self.temporary.name).rglob('*') if path.is_file()}

    def test_owner_message_uses_pinned_read_only_backend_without_a_verdict(self):
        before = self.snapshot()
        result = self.cli('--kind', 'communication', '--id', self.item['id'], '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['request'], self.item)
        self.assertEqual(plan['relay']['to'], 'owner')
        self.assertEqual(plan['relay']['replyTo'], self.item['id'])
        self.assertEqual((plan['requiredModel'], plan['requiredEffort']), ('claude-opus-5-5', 'high'))
        self.assertFalse(plan['isReview'])
        self.assertFalse(plan['isFinalVerdict'])
        self.assertFalse(plan['startsSession'])
        backend = plan['backendArgv']
        self.assertEqual(backend[backend.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(backend[backend.index('--mcp-config') + 1], '{"mcpServers":{}}')
        self.assertIn('--restricted', backend)
        self.assertIn('--read-only', plan['argv'])
        self.assertEqual(self.snapshot(), before)

        # Exercise the actual downstream parser/configuration, with no launch.
        downstream = subprocess.run(plan['argv'][:-2] + ['--dry-run'] + plan['argv'][-2:],
                                    env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(downstream.returncode, 0, downstream.stderr)
        self.assertFalse(json.loads(downstream.stdout)['startsSession'])
        self.assertEqual(self.snapshot(), before)

    def test_inbox_exposes_pending_messages_and_clears_only_after_verbatim_relay(self):
        before = self.snapshot()
        inbox = self.cli('--inbox')
        self.assertEqual(inbox.returncode, 0, inbox.stderr)
        self.assertIn(self.item['id'], inbox.stdout)
        self.assertEqual(self.snapshot(), before)
        body = ('元の ID: ' + self.item['id'] + '\n宛先: owner\n'
                '受領: 相互連絡の手順を確認。\n返答: 原文を Banana が中継する。\n'
                '次の担当: Banana が中継し、Tomato が日誌へ集約。\n')
        source = Path(self.temporary.name) / 'result.txt'
        source.write_text('## 連絡\n' + body, encoding='utf-8')
        result = subprocess.run([sys.executable, str(TEAM / 'bin/team-mail'), '--root', str(self.root),
                                 'relay-potato', '--source-file', str(source), '--to', 'owner',
                                 '--subject', '運用の返答', '--id', self.item['id']],
                                env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertEqual(reply['body'], body)
        self.assertEqual((reply['from'], reply['relay'], reply['reply_to']),
                         ('potato', 'banana', self.item['id']))
        self.assertEqual(reply['source'], str(source.resolve()))
        self.assertEqual(mail.records(self.root, 'potato', unread=True), [])
        original = next(row for row in mail.records(self.root) if row['id'] == self.item['id'])
        self.assertEqual(original['receipts'], [])
        self.assertEqual(original['replies'], [reply['id']])
        self.assertNotIn(self.item['id'], self.cli('--inbox').stdout)
        with self.assertRaisesRegex(ValueError, '重複起動'):
            communication_plan(self.root, self.item['id'])

    def test_foreign_missing_invalid_and_internally_mismatched_ids_fail_without_writes(self):
        foreign = mail.send(self.root, 'owner', ['banana'], '別の連絡', 'Banana 宛')
        for identifier in (foreign['id'], 'f' * 32, '../messages', ''):
            with self.subTest(identifier=identifier):
                before = self.snapshot()
                result = self.cli('--kind', 'communication', '--id', identifier, '--dry-run')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.snapshot(), before)
        path = self.root / 'messages' / (self.item['id'] + '.json')
        corrupt = dict(self.item, id='e' * 32)
        path.write_text(json.dumps(corrupt))
        with self.assertRaisesRegex(ValueError, '元の message ID'):
            communication_plan(self.root, self.item['id'])

    def test_communication_cannot_carry_review_arguments_or_be_hidden_in_inbox(self):
        for option in ('--repo', '--issue', '--pr', '--sha', '--prompt-file'):
            with self.subTest(option=option):
                result = self.cli('--kind', 'communication', '--id', self.item['id'], option, 'fixture', '--dry-run')
                self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.cli('--kind', 'communication', '--dry-run').returncode, 0)
        self.assertNotEqual(self.cli('--inbox', '--id', self.item['id']).returncode, 0)
        self.assertNotEqual(self.cli('--kind', 'technical', '--id', self.item['id']).returncode, 0)

    def test_absent_inbox_remains_absent(self):
        absent = Path(self.temporary.name) / 'absent'
        result = subprocess.run([sys.executable, str(TEAM / 'bin/potato'), '--inbox', '--mail-root', str(absent)],
                                env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(absent.exists())


if __name__ == '__main__':
    unittest.main()
