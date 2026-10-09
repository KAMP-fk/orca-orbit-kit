"""Offline checks for truthful activity and idempotent display setup."""
import json
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import activity
import workspace_display as display


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = {'schemaVersion': 1, 'repo': 'owner/repo'}
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(self.cfg))
        self.state = self.root / 'devin'
        self.native = {'truncated': False, 'worktrees': []}

    def record(self, **fields):
        value = dict(schemaVersion=1, repo='owner/repo', issue='CAF-301', state='implementing',
                     execution='execution', session='session', branch='codex/caf-301-fix', pr=None,
                     feedback='PRIVATE_FEEDBACK', token='PRIVATE_TOKEN')
        value.update(fields)
        path = self.state / 'job/record.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def snapshot(self, **kwargs):
        return activity.snapshot(self.config, self.state, self.root / 'projects', native=self.native, **kwargs)

    def test_disconnected_is_visible_and_never_calls_adapter(self):
        self.record()
        with patch.object(activity, 'adapter', side_effect=AssertionError('No external calls')):
            value = self.snapshot(observe=True)
        self.assertEqual(value['connection'], '未接続・起動不可')
        self.assertEqual(value['devin'][0]['remoteState'], '未取得')

    def test_projection_excludes_prompts_feedback_and_control_sequences(self):
        self.record()
        self.native['worktrees'] = [dict(displayName='Agent\x1b\nHome', agents=[dict(
            agentType='codex', state='working', updatedAt=123,
            toolInput='PRIVATE_TOOL', lastAssistantMessage='PRIVATE_MESSAGE')])]
        output = activity.render(self.snapshot())
        for value in ('PRIVATE_', '\x1b', 'lastAssistantMessage', 'toolInput'):
            self.assertNotIn(value, output)
        self.assertIn('| working |', output)

    def test_current_development_path_and_retained_history_are_distinct(self):
        self.record()
        output = activity.render(self.snapshot())
        self.assertTrue(output.startswith(activity.SCREEN_HEADING + '\n'))
        self.assertIn('Banana（開発 / Codex）', output)
        self.assertIn('開発: Banana / Codex', output)
        self.assertIn('Devin 保存済み台帳（利用停止）', output)
        self.assertIn('Devin 保存済み案件 |', output)
        self.assertNotIn('Banana / Devin CLI', output)

    def test_remote_observation_cannot_mutate_controller_or_call_quality_gate(self):
        record = self.record(state='in_review')
        before = record.read_bytes()
        receipt = dict(session='session', branch='codex/caf-301-fix', workerState='validating')
        with patch.object(activity, 'adapter', return_value=receipt) as adapter:
            rows = activity.devin_rows(self.cfg, self.state, observe=True)
        self.assertEqual(rows[0]['state'], 'in_review')
        self.assertEqual(rows[0]['remoteState'], 'validating')
        self.assertEqual(adapter.call_args.args[1:3], ('implementation', 'observe'))
        self.assertEqual(record.read_bytes(), before)

    def test_uncertain_start_and_completed_record_are_never_remote_retried(self):
        for state in ('start_unknown', 'revision_unknown', 'done'):
            self.record(state=state)
            with patch.object(activity, 'adapter', side_effect=AssertionError('No resend')):
                activity.devin_rows(self.cfg, self.state, observe=True)

    def test_foreign_session_marks_remote_unconfirmed(self):
        self.record()
        with patch.object(activity, 'adapter', return_value=dict(session='other', branch='codex/caf-301-fix')):
            rows = activity.devin_rows(self.cfg, self.state, observe=True)
        self.assertEqual(rows[0]['remoteState'], '取得失敗・未確認')

    def test_truncated_observation_is_not_reported_as_idle_or_success(self):
        self.native['truncated'] = True
        value = self.snapshot()
        self.assertEqual(value['orcaObservation'], '取得失敗・未確認')
        self.assertEqual(value['agents'], [])

    def test_malformed_and_linked_records_are_unconfirmed_without_leaking_content(self):
        path = self.record()
        private = self.root / 'private'
        private.write_text('PRIVATE_SECRET')
        path.unlink()
        path.symlink_to(private)
        value = self.snapshot()
        self.assertEqual(value['devin'], [{'state': '記録不正・未確認'}])
        self.assertNotIn('PRIVATE', json.dumps(value))

    def test_cli_once_with_custom_roots_does_not_write_state(self):
        self.record()
        cli = self.root / 'orca'
        cli.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"ok":True,"result":{"worktrees":[]}}))\n')
        cli.chmod(0o755)
        env = {k:v for k,v in os.environ.items() if k not in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE')}
        env.update(ORCA_CLI_COMMAND=str(cli), NAMED_TEAM_DEVIN_CONFIG=str(self.config),
                   NAMED_TEAM_DEVIN_STATE_DIR=str(self.state), NAMED_TEAM_PROJECT_TASK_DIR=str(self.root / 'projects'))
        result = subprocess.run([sys.executable, '-B', str(PACKAGE / 'bin/activity'), '--json'],
                                capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['devin'][0]['issue'], 'CAF-301')
        self.assertFalse((self.root / 'projects').exists())


class DisplayTests(unittest.TestCase):
    def inventory(self):
        return {'worktrees': [dict(id=str(i), path=str(path), displayName='old', comment='old', hostId='local')
                              for i, (path, _, _, _) in enumerate(display.specs())]}

    def test_metadata_apply_preserves_sessions_status_and_changes_role_hierarchy(self):
        inventory = self.inventory()
        inventory['worktrees'][2]['parentWorktreeId'] = '1'
        targets = display.plan(inventory)
        with patch.object(display, 'call') as call:
            handle = display.apply(targets, {'handle': 'existing'})
        self.assertEqual(handle, 'existing')
        for invocation in call.call_args_list:
            self.assertEqual(invocation.args[:2], ('worktree', 'set'))
            self.assertNotIn('--workspace-status', invocation.args)
        changes = {args.args[args.args.index('--worktree')+1]: args.args for args in call.call_args_list}
        self.assertEqual(changes['id:2'][-1], '--no-parent')
        self.assertNotIn('--parent-worktree', changes['id:2'])
        self.assertNotIn('--parent-worktree', changes['id:0'])
        self.assertNotIn('--parent-worktree', changes['id:3'])

    def test_reapplying_normalized_inventory_never_creates_another_tab(self):
        inventory = self.inventory()
        for row, spec in zip(inventory['worktrees'], display.specs()):
            row.update(displayName=spec[1], comment=spec[2])
        for target in display.plan(inventory):
            next(row for row in inventory['worktrees'] if row['id'] == target['id'])['parentWorktreeId'] = target['parentId']
        with patch.object(display, 'call') as call:
            display.apply(display.plan(inventory), {'handle': 'existing'})
        call.assert_not_called()

    def test_display_receipt_must_match_the_planned_hierarchy(self):
        inventory = self.inventory()
        targets = display.plan(inventory)
        for target in targets:
            row = next(row for row in inventory['worktrees'] if row['id'] == target['id'])
            row.update(displayName=target['title'], comment=target['comment'], parentWorktreeId=target['parentId'])
        display.verify(targets, inventory)
        inventory['worktrees'][2]['parentWorktreeId'] = 'wrong-parent'
        with self.assertRaises(RuntimeError):
            display.verify(targets, inventory)

    def test_missing_duplicate_and_incomplete_homes_block_before_mutation(self):
        missing = self.inventory(); missing['worktrees'].pop(0)
        duplicate = self.inventory(); duplicate['worktrees'].append(dict(duplicate['worktrees'][0]))
        incomplete = dict(self.inventory(), truncated=True)
        for value in (missing, duplicate, incomplete):
            with self.assertRaises(RuntimeError):
                display.plan(value)

    def test_activity_creation_is_model_free_and_uses_exact_existing_home(self):
        targets = display.plan(self.inventory())
        for row in targets:
            row['changed'] = False
        with patch.object(display, 'call', return_value={'terminal':{'handle':'observer'}}) as call:
            self.assertEqual(display.apply(targets, None), 'observer')
        args = call.call_args.args
        self.assertEqual(args[:2], ('terminal', 'create'))
        self.assertEqual(args[args.index('--worktree')+1], 'id:0')
        command = args[args.index('--command')+1]
        self.assertIn('bin/activity', command)
        self.assertNotIn('bin/agent ', command)

    def test_duplicate_live_activity_tabs_block_setup(self):
        with patch.object(display, 'call', side_effect=[self.inventory(), {'terminals':[
            dict(title=activity.TITLE, connected=True, handle='1'),
            dict(title=activity.TITLE, connected=True, handle='2')]}]):
            with self.assertRaises(RuntimeError):
                display.prepare()

    def test_live_shell_or_stale_output_does_not_count_as_running_observer(self):
        for lines in (['shell prompt'], ['Devin / Orca エージェント状況',
                        '[' + (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat() + '] 観測']):
            with patch.object(display, 'call', return_value={'terminal':{'tail':lines}}):
                self.assertFalse(display.healthy('observer'))
        for heading in activity.SCREEN_HEADINGS:
            lines = ['[' + datetime.now(timezone.utc).isoformat() + '] 観測', heading]
            with patch.object(display, 'call', return_value={'terminal':{'tail':lines}}):
                self.assertTrue(display.healthy('observer'))

    def test_isolated_setup_never_accesses_live_orca(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, ORCA_CLI_COMMAND='/missing/orca')
            env.pop('ORCA_ENVIRONMENT', None); env.pop('ORCA_PAIRING_CODE', None)
            command = [sys.executable, '-B', str(PACKAGE / 'bin/setup'), '--home', folder]
            for args in ([], ['--check']):
                result = subprocess.run(command + args, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((Path(folder) / '.local/bin/activity').resolve(), PACKAGE / 'bin/activity')
