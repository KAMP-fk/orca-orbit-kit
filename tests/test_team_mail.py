"""Exercise real durable role exchanges and concurrent publication in a fixture."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TEAM = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(TEAM / 'lib'))
import team_mail as mail


class TeamMailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_receipt_and_reply_have_distinct_meaning(self):
        item = mail.send(self.root, 'tomato', ['banana'], 'FX-1', 'AC と調査依頼')
        self.assertEqual([row['id'] for row in mail.records(self.root, 'banana', True)], [item['id']])
        receipt = mail.acknowledge(self.root, 'banana', item['id'], '次は Banana が調査')
        self.assertEqual(len(mail.records(self.root, 'banana', True)), 1)  # Received, still awaiting reply.
        self.assertEqual(mail.records(self.root)[0]['replies'], [])
        self.assertEqual(mail.acknowledge(self.root, 'banana', item['id'], '重複'), receipt)
        reply = mail.send(self.root, 'banana', ['tomato'], 'Re: FX-1', '調査済み、次は Tomato が範囲確認', item['id'])
        self.assertEqual(mail.records(self.root, 'banana', True), [])
        self.assertEqual([row['id'] for row in mail.records(self.root, 'tomato', True)], [reply['id']])
        original = next(row for row in mail.records(self.root) if row['id'] == item['id'])
        self.assertEqual(original['replies'], [reply['id']])
        with self.assertRaises(ValueError):
            mail.acknowledge(self.root, 'tomato', item['id'], '別の宛先')
        with self.assertRaises(ValueError):
            mail.send(self.root, 'owner', ['tomato'], 'Re: FX-1', '宛先ではない', item['id'])

    def test_parallel_messages_are_not_lost_or_partially_read(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda n: mail.send(self.root, 'banana', ['tomato'], str(n), str(n)), range(48)))
        received = mail.records(self.root, 'tomato', True)
        self.assertEqual({row['id'] for row in received}, {row['id'] for row in rows})
        self.assertEqual({row['body'] for row in received}, {str(n) for n in range(48)})
        self.assertEqual(list(self.root.rglob('.pending-*')), [])

    def test_potato_reply_is_verbatim_and_attributes_relay(self):
        item = mail.send(self.root, 'tomato', ['potato'], '規準への質問', '見逃しの型を確認')
        path = self.root / 'result.md'
        body = '元の ID: ' + item['id'] + '\n宛先: Tomato\n回答: 規準外。次は Tomato が判断\n\n'
        path.write_text('# 技術確認\nPASS\n## 連絡\n' + body + '## 記録\n原文記録\n')
        returned = mail.relay_potato(self.root, path, ['tomato'], '規準の返答', item['id'])
        self.assertEqual(returned['body'], body)
        self.assertEqual((returned['from'], returned['relay'], returned['source']), ('potato', 'banana', str(path.resolve())))
        self.assertEqual(mail.records(self.root, 'potato', True), [])
        with self.assertRaises(ValueError):
            mail.send(self.root, 'potato', ['tomato'], '自由な返答', '書き換えた本文')
        with self.assertRaises(ValueError):
            mail.acknowledge(self.root, 'potato', item['id'], '自身では書かない')

    def test_reading_absent_mailbox_has_no_side_effect(self):
        root = self.root / 'missing'
        self.assertEqual(mail.records(root, 'banana', True), [])
        self.assertFalse(root.exists())
        process = subprocess.run([sys.executable, str(TEAM / 'bin/team-mail'), '--root', str(root),
                                  'inbox', '--role', 'banana'], text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), [])
        self.assertFalse(root.exists())

    def test_notification_requires_receipt_but_not_a_reply(self):
        item = mail.send(self.root, 'banana', ['tomato'], '進行通知', 'FX-1 完了', needs_reply=False)
        self.assertEqual(len(mail.records(self.root, 'tomato', True)), 1)
        mail.acknowledge(self.root, 'tomato', item['id'], '日誌に集約する')
        self.assertEqual(mail.records(self.root, 'tomato', True), [])

    def test_acceptance_report_is_relayed_whole_without_changing_gate_format(self):
        path = self.root / 'acceptance.md'
        text = 'Issue: FX-1 fixture\n\nVerdict: BLOCKED\n\nSummary:\n固定版の資料が不足。次は Banana\n'
        path.write_text(text)
        returned = mail.relay_potato(self.root, path, ['banana', 'tomato'], '受入結果')
        self.assertEqual(returned['body'], text)
        self.assertEqual(path.read_text(), text)

    def test_corrupt_mail_is_an_error_and_receipt_on_previous_day_is_included(self):
        item = mail.send(self.root, 'banana', ['tomato'], '停止', '次は Tomato が確認')
        path = self.root / 'messages' / (item['id'] + '.json')
        item['at'] = '2026-10-06T23:59:00+09:00'
        path.write_text(json.dumps(item))
        receipt = mail.acknowledge(self.root, 'tomato', item['id'], '受領')
        self.assertEqual(len(mail.records(self.root, day=receipt['at'][:10])), 1)
        path.write_text('{partial')
        with self.assertRaises(ValueError):
            mail.records(self.root)


if __name__ == '__main__':
    unittest.main()
