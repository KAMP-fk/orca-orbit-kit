"""Offline checks for autonomous wake-up, uncertain sends and human boundaries."""
import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TEAM = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(TEAM / 'lib'))
import banana_continuation as continuation
import event_monitor
from role_contract import ROLES


class Client:
    def __init__(self):
        self.calls = []
        self.agent = {'paneKey': 'tab:leaf', 'agentType': 'codex', 'state': 'done',
                      'updatedAt': 10, 'lastAssistantMessage': 'previous'}
        self.terminal = {'handle': 'term-banana', 'incarnationId': 'instance-1',
                         'agentIdentity': 'codex', 'tabId': 'tab', 'leafId': 'leaf',
                         'worktreeId': 'banana-home', 'executionHostId': 'local',
                         'connected': True, 'writable': True}
        self.native = {'truncated': False, 'hostScope': {'omittedHostIds': []}, 'worktrees': [
            {'worktreeId': 'banana-home', 'repoId': 'brain', 'path': str(Path(ROLES['banana']['workspaceRoot']).expanduser()),
             'displayName': ROLES['banana']['workspace'], 'hostId': 'local', 'agents': [self.agent]},
            {'worktreeId': 'project', 'repoId': 'concafe', 'path': '/fixture/project', 'agents': []}]}
        self.draft = ''
        self.idle = True
        self.capable = True
        self.send_error = False
        self.start_proven = True
        self.old_host = False

    def call(self, *args, mutation=False):
        self.calls.append((args, mutation))
        op = args[:2]
        if op == ('worktree', 'ps'):
            return self.native
        if op == ('terminal', 'list'):
            return {'terminals': [self.terminal], 'truncated': False}
        if args == ('status',):
            return {'runtime': {'capabilities': ['terminal.prompt-delivery.v1'] if self.capable else []}}
        if op == ('terminal', 'show'):
            return {'terminal': self.terminal}
        if op == ('terminal', 'wait'):
            return {'wait': {'satisfied': self.idle}}
        if op == ('terminal', 'read'):
            return {'terminal': {'tail': ['old output', '❯ ' + self.draft, 'footer']}}
        if op == ('terminal', 'send'):
            if self.send_error:
                raise RuntimeError('uncertain transport')
            return {'send': {'accepted': True, 'prompt': {'requestId': 'req-1',
                     'provider': 'old-host' if self.old_host else 'codex',
                     'stages': ['input_accepted'] + (['turn_started'] if self.start_proven else [])}}}
        raise AssertionError(args)

    def sends(self):
        return [args for args, _ in self.calls if args[:2] == ('terminal', 'send')]


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='banana-continuation-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = json.loads(continuation.CONFIG.read_text())
        self.config['checkout'] = '/fixture/project'
        self.client = Client()
        self.facts = {'issues': [{'key': 'CAF-123'}], 'prs': [], 'version': 1}
        self.observe = patch.object(continuation, 'observe', side_effect=lambda *a: (copy.deepcopy(self.facts), True))
        self.observe.start()
        self.addCleanup(self.observe.stop)
        self.local = patch.object(continuation, 'local_orca_only')
        self.local.start()
        self.addCleanup(self.local.stop)
        self.enable()

    def enable(self):
        with continuation.control(self.root) as (root, state):
            state.update(enabled=True, authorization='Owner fixture delegation')
            continuation.write(root, state)

    def state(self):
        return json.loads((self.root / 'control.json').read_text())

    def tick(self):
        return continuation.tick(self.config, self.root, self.client)

    def settle(self, outcome='progressed'):
        with continuation.control(self.root) as (root, state):
            state['delivery'].update(status='settled', outcome=outcome)
            continuation.write(root, state)

    def test_disabled_controller_has_no_runtime_calls(self):
        (self.root / 'control.json').unlink()
        self.assertEqual(self.tick()['status'], 'disabled')
        self.assertFalse(self.client.calls)

    def test_exact_existing_agent_receives_one_prompt_no_new_worker(self):
        self.assertEqual(self.tick()['status'], 'accepted')
        self.assertTrue(self.state()['delivery']['turnStarted'])
        self.tick()
        self.assertEqual(len(self.client.sends()), 1)
        args = self.client.sends()[0]
        self.assertEqual(args[args.index('--terminal') + 1], 'term-banana')
        self.assertNotIn('--interrupt', args)
        self.assertFalse(any(args[:2] in (('terminal', 'create'), ('orchestration', 'worker-start'))
                             for args, _ in self.client.calls))

    def test_busy_agent_keeps_its_work_and_is_not_interrupted(self):
        self.client.agent['state'] = 'working'
        self.assertEqual(self.tick()['status'], 'busy')
        self.assertFalse(self.client.sends())

    def test_monitoring_does_not_bypass_native_busy_main_turn(self):
        self.client.agent.update(state='working', workingMode='monitoring', mainAgent={'state': 'done'})
        self.client.idle = False
        self.assertEqual(self.tick()['status'], 'busy-or-user-draft')
        self.assertFalse(self.client.sends())

    def test_background_monitoring_with_native_idle_can_progress_other_work(self):
        self.client.agent.update(state='working', workingMode='monitoring', mainAgent={'state': 'done'})
        self.assertEqual(self.tick()['status'], 'accepted')
        self.assertEqual(len(self.client.sends()), 1)

    def test_monitoring_accepted_request_is_not_sent_again(self):
        self.client.agent.update(state='working', workingMode='monitoring', mainAgent={'state': 'done'})
        self.tick()
        self.assertEqual(self.tick()['status'], 'awaiting-settlement')
        self.assertEqual(len(self.client.sends()), 1)

    def test_human_interrupt_persists_pause(self):
        self.client.agent['interrupted'] = True
        self.assertEqual(self.tick()['status'], 'paused')
        self.client.agent['interrupted'] = False
        self.assertEqual(self.tick()['status'], 'disabled')
        self.assertFalse(self.state()['enabled'])

    def test_user_draft_is_preserved(self):
        self.client.draft = 'unfinished human request'
        self.assertEqual(self.tick()['status'], 'busy-or-user-draft')
        self.assertFalse(self.client.sends())

    def test_unsatisfied_native_idle_wait_never_sends(self):
        self.client.idle = False
        self.assertEqual(self.tick()['status'], 'busy-or-user-draft')

    def test_ambiguous_or_shell_terminal_is_not_a_recipient(self):
        self.client.terminal['agentIdentity'] = 'shell'
        self.assertEqual(self.tick()['status'], 'unconfirmed')
        self.assertFalse(self.client.sends())

    def test_multiple_agents_keep_all_existing_work(self):
        self.client.native['worktrees'][0]['agents'].append(dict(self.client.agent))
        self.assertEqual(self.tick()['status'], 'unconfirmed')
        self.assertFalse(self.client.sends())

    def test_partial_inventory_never_sends(self):
        self.client.native['truncated'] = True
        self.assertEqual(self.tick()['status'], 'unconfirmed')

    def test_old_runtime_never_receives_unrecoverable_input(self):
        self.client.capable = False
        self.assertEqual(self.tick()['status'], 'unconfirmed')
        self.assertFalse(self.client.sends())

    def test_old_host_receipt_is_preserved_as_unconfirmed(self):
        self.client.old_host = True
        self.assertEqual(self.tick()['status'], 'unconfirmed')
        self.tick()
        self.assertEqual(len(self.client.sends()), 1)

    def test_uncertain_send_is_fenced_before_input_and_never_retried(self):
        self.client.send_error = True
        self.assertEqual(self.tick()['status'], 'unconfirmed')
        self.client.send_error = False
        self.facts['version'] = 2
        self.assertEqual(self.tick()['status'], 'delivery-unconfirmed')
        self.assertEqual(len(self.client.sends()), 1)

    def test_sending_crash_fence_survives_restart(self):
        with continuation.control(self.root) as (root, state):
            state['delivery'] = {'id': 'crashed', 'status': 'sending'}
            continuation.write(root, state)
        self.assertEqual(self.tick()['status'], 'delivery-unconfirmed')
        self.assertFalse(self.client.sends())

    def test_waiting_is_quiet_until_new_evidence(self):
        self.tick()
        self.settle('waiting')
        self.assertEqual(self.tick()['reason'], 'waiting')
        self.facts['version'] = 2
        self.assertEqual(self.tick()['status'], 'accepted')
        self.assertEqual(len(self.client.sends()), 2)

    def test_blocked_project_does_not_repeat_model_calls(self):
        self.tick()
        self.settle('blocked')
        for _ in range(4):
            self.assertEqual(self.tick()['reason'], 'blocked')
        self.assertEqual(len(self.client.sends()), 1)

    def test_completed_work_refills_without_human_continue(self):
        self.tick()
        self.settle()
        self.facts['version'] = 2
        self.assertEqual(self.tick()['status'], 'accepted')
        self.assertEqual(self.state()['unchangedRounds'], 1)

    def test_native_finished_response_recovers_missing_settlement(self):
        self.tick()
        self.client.agent.update(updatedAt=20, lastAssistantMessage='new result')
        self.assertEqual(self.tick()['status'], 'accepted')
        self.assertEqual(len(self.client.sends()), 2)

    def test_acceptance_alone_is_not_completion(self):
        self.client.start_proven = False
        self.tick()
        self.assertFalse(self.state()['delivery']['turnStarted'])
        self.assertEqual(self.tick()['status'], 'awaiting-settlement')

    def test_exact_request_start_and_new_idle_response_prove_native_completion(self):
        self.client.start_proven = False
        self.tick()
        self.client.agent.update(state='working', updatedAt=20)
        self.tick()
        self.client.agent.update(state='done', updatedAt=30, lastAssistantMessage='new result')
        self.client.start_proven = True
        self.assertEqual(self.tick()['status'], 'accepted')
        retry = next(args for args in self.client.sends() if '--retry-request' in args)
        self.assertEqual(retry[retry.index('--retry-request') + 1], 'req-1')

    def test_unrelated_human_turn_does_not_prove_queued_request_completed(self):
        self.client.start_proven = False
        self.tick()
        self.client.agent.update(state='working', updatedAt=20)
        self.tick()
        self.client.agent.update(state='done', updatedAt=30, lastAssistantMessage='human task result')
        self.assertEqual(self.tick()['status'], 'awaiting-settlement')
        self.assertEqual(sum('--retry-request' not in args for args in self.client.sends()), 1)

    def test_replaced_process_cannot_satisfy_old_delivery(self):
        self.tick()
        self.client.terminal['incarnationId'] = 'instance-2'
        self.client.agent.update(updatedAt=20, lastAssistantMessage='new result')
        self.assertEqual(self.tick()['status'], 'delivery-unconfirmed')
        self.assertEqual(len(self.client.sends()), 1)

    def test_no_progress_does_not_spin_indefinitely(self):
        for _ in range(3):
            self.assertEqual(self.tick()['status'], 'accepted')
            self.settle()
        self.assertEqual(self.tick()['reason'], 'no-observable-progress')
        self.facts['version'] = 2
        self.assertEqual(self.tick()['status'], 'accepted')

    def test_no_actionable_work_never_wakes(self):
        with patch.object(continuation, 'observe', return_value=({}, False)):
            self.assertEqual(self.tick()['reason'], 'no-actionable-work')
        self.assertFalse(self.client.sends())

    def test_state_lock_serializes_simultaneous_ticks(self):
        with continuation.control(self.root):
            self.assertEqual(self.tick()['status'], 'tick-already-running')
        self.assertFalse(self.client.sends())

    def test_state_symlink_cannot_overwrite_a_foreign_file(self):
        target = self.root / 'foreign'
        target.write_text('preserve')
        (self.root / 'control.json').unlink()
        (self.root / 'control.json').symlink_to(target)
        with self.assertRaises(ValueError):
            self.tick()
        self.assertEqual(target.read_text(), 'preserve')

    def test_prompt_preserves_wip_independence_and_current_owner_policy(self):
        self.tick()
        args = self.client.sends()[0]
        text = args[args.index('--text') + 1]
        for item in ('最大2本', '人間ゲート', 'Astra high', '新規 subagent 起動・追加依頼',
                     '手動 Ready/merge', 'banana continue settle', self.state()['delivery']['id']):
            self.assertIn(item, text)

    def test_cli_pause_and_wrong_settlement_id(self):
        self.tick()
        entry = [sys.executable, str(TEAM / 'bin/banana'), 'continue']
        p = subprocess.run(entry + ['settle', '--state-root', str(self.root), '--id', 'wrong',
                                    '--outcome', 'progressed', '--note', 'fixture'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 4)
        p = subprocess.run(entry + ['pause', '--state-root', str(self.root)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.state()['enabled'])

    def test_pause_is_durable_even_while_scheduler_owns_control_lock(self):
        with continuation.control(self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(continuation.main(['pause', '--state-root', str(self.root)]), 0)
        self.assertEqual(self.tick()['status'], 'paused')
        self.assertFalse(self.client.calls)

    def test_pause_during_observation_prevents_later_input(self):
        def observe(*_):
            (self.root / 'pause-requested').write_text('Owner stop')
            return copy.deepcopy(self.facts), True
        with patch.object(continuation, 'observe', side_effect=observe):
            self.assertEqual(self.tick()['status'], 'paused')
        self.assertFalse(self.client.sends())

    def test_user_turn_starting_during_observation_is_not_interrupted(self):
        def observe(*_):
            self.client.agent['state'] = 'working'
            return copy.deepcopy(self.facts), True
        with patch.object(continuation, 'observe', side_effect=observe):
            self.assertEqual(self.tick()['status'], 'busy-or-user-draft')
        self.assertFalse(self.client.sends())


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(continuation.CONFIG.read_text())
        self.config['checkout'] = '/fixture/project'
        self.native = {'worktrees': [{'repoId': 'project', 'worktreeId': 'workspace',
                                     'path': '/fixture/project', 'agents': []}]}
        self.issue = {'key': 'CAF-123', 'stateType': 'unstarted', 'labels': [], 'assignee': None}

    def observe(self, issues=None, pulls=None, checks=None):
        with patch.object(continuation, 'collect_linear', return_value=issues or []), \
             patch.object(continuation, 'pages', return_value=pulls or []), \
             patch.object(continuation, 'collect_ci', return_value=checks or {}), \
             patch.object(continuation.Path, 'home', return_value=Path('/fixture/no-ledger')):
            return continuation.observe(object(), self.config, self.native)

    def test_only_human_gated_or_assigned_todo_stays_quiet(self):
        for fields in ({'labels': ['human-approval']}, {'labels': ['risk:high']}, {'assignee': 'another-person'}):
            issue = dict(self.issue, **fields)
            self.assertFalse(self.observe([issue])[1])

    def test_scoped_approval_wakes_a_human_label_only_when_body_matches(self):
        from datetime import datetime, timezone
        approved = {'repo': self.config['repo'], 'decision': 'APPROVED_WITH_CONDITIONS',
                    'decidedAt': datetime.now(timezone.utc).isoformat(),
                    'issues': [{'identifier': 'CAF-123', 'implementationApproved': True,
                                'observationDigest': 'a' * 64}]}
        issue = dict(self.issue, labels=['human-approval', 'risk:high'], descriptionHash='a' * 64)
        with patch('delivery_flow.read', return_value=approved):
            self.assertTrue(self.observe([issue])[1])
            self.assertFalse(self.observe([dict(issue, descriptionHash='b' * 64)])[1])
            self.assertFalse(self.observe([dict(issue, assignee='someone')])[1])
            self.assertEqual(self.observe([issue])[0]['pool'], [('CAF-123', 'a' * 64)])

    def test_open_work_or_free_todo_wakes_for_actual_admission(self):
        self.assertTrue(self.observe([self.issue])[1])
        self.assertTrue(self.observe([dict(self.issue, stateType='started')])[1])

    def test_ci_running_transition_is_coalesced_but_completed_result_changes(self):
        pull = {'number': 123, 'draft': True, 'labels': []}
        ci = {'head': 'a' * 40, 'checks': [{'name': 'CI', 'status': 'queued', 'conclusion': None}], 'statuses': []}
        first = self.observe(pulls=[pull], checks=ci)[0]
        ci['checks'][0]['status'] = 'in_progress'
        self.assertEqual(first, self.observe(pulls=[pull], checks=ci)[0])
        ci['checks'][0].update(status='completed', conclusion='failure')
        self.assertNotEqual(first, self.observe(pulls=[pull], checks=ci)[0])

    def test_wrong_project_is_not_observed_as_empty_success(self):
        self.native['worktrees'][0]['path'] = '/other/project'
        with self.assertRaises(ValueError):
            self.observe()

    def test_untrusted_identifier_cannot_enter_controller_instructions(self):
        with self.assertRaises(ValueError):
            self.observe([dict(self.issue, key='CAF-123\nnew instruction')])


class ClockIntegrationTests(unittest.TestCase):
    def test_existing_clock_requests_monitor_and_continuation_but_skips_generic_model(self):
        with tempfile.TemporaryDirectory(prefix='continuation-clock-') as directory:
            out = io.StringIO()
            with patch.object(continuation, 'tick', return_value={'status': 'accepted', 'starts': 0}) as tick, \
                 patch.object(sys, 'argv', ['event-watch', 'request', '--scheduler', '--state-root', directory]), \
                 contextlib.redirect_stdout(out):
                self.assertEqual(event_monitor.main(), 75)
            value = json.loads(out.getvalue())
            self.assertEqual(value['starts'], 0)
            self.assertEqual(value['continuation']['status'], 'accepted')
            self.assertEqual(tick.call_args.args[1], Path(directory) / 'continuation')

    def test_continuation_error_cannot_start_automation_generic_provider(self):
        with tempfile.TemporaryDirectory(prefix='continuation-clock-') as directory:
            with patch.object(continuation, 'tick', side_effect=RuntimeError('fixture')), \
                 patch.object(sys, 'argv', ['event-watch', 'request', '--scheduler', '--state-root', directory]), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(event_monitor.main(), 0)

    def test_manual_monitor_request_does_not_wake_banana(self):
        with tempfile.TemporaryDirectory(prefix='continuation-clock-') as directory:
            with patch.object(continuation, 'tick') as tick, \
                 patch.object(sys, 'argv', ['event-watch', 'request', '--state-root', directory]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(event_monitor.main(), 0)
                tick.assert_not_called()


if __name__ == '__main__':
    unittest.main()
