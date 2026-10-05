"""Visible task lifecycle regressions; only fixture backends and Orca are called."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import test_named_agents


ORCA_FIXTURE = r'''#!/usr/bin/python3
import json, os, shlex, subprocess, sys
from pathlib import Path
a=sys.argv[1:]
root=Path(os.environ['NAMED_TEAM_TASK_DIR'])
root.mkdir(exist_ok=True)
with (root/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\n')
if a[:2]==['worktree','list']:
 roles=json.loads(Path(os.environ['NAMED_TEAM_ROLE_CONTRACT']).read_text())
 rows=[{'id':'fixture-workspace','hostId':'local',
   'path':str(Path(v['workspaceRoot']).expanduser().absolute()),
   'displayName':v.get('workspaceAliases',[v['workspace']])[0]} for v in roles.values()
   if not os.environ.get('FIXTURE_ONLY_ENTRIES') or v['activation']=='home']
 if os.environ.get('FIXTURE_DUPLICATE_ROLE'):
  role=roles[os.environ['FIXTURE_DUPLICATE_ROLE']]
  rows.append({'id':'duplicate','path':str(Path(role['workspaceRoot']).expanduser().absolute()),'displayName':role['workspace']})
 result={'worktrees':rows,'truncated':False}
elif a[:2]==['worktree','show']:
 result={'worktree':{'id':'fixture-workspace'}}
elif a[:2]==['terminal','create']:
 command=a[a.index('--command')+1]
 run=Path(shlex.split(command)[-1])
 (root/'latest').write_text(str(run))
 if not os.environ.get('FIXTURE_NO_RESULT'):
  env=os.environ.copy(); env['ORCA_TERMINAL_HANDLE']='term_fixture'
  with (run/'visible.txt').open('w') as visible:
   child=subprocess.Popen(['/bin/sh','-c',command], env=env, stdout=visible, stderr=subprocess.STDOUT)
  (run/'fixture-worker.pid').write_text(str(child.pid))
 result={'terminal':{'handle':'term_fixture','tabId':'fixture-tab'}}
 if os.environ.get('FIXTURE_CREATE_TIMEOUT'):
  if os.environ.get('FIXTURE_CREATE_TIMEOUT_ONCE'):
   mark=root/'timed-out-once'
   if not mark.exists():
    mark.write_text('1'); sys.exit('Timed out waiting for terminal handle after creation')
  else: sys.exit('Timed out waiting for terminal handle after creation')
elif a[:2]==['terminal','list']:
 run=Path((root/'latest').read_text())
 if os.environ.get('FIXTURE_LIST_EMPTY'): result={'terminals':[]}
 else: result={'terminals':[{'handle':'term_fixture','tabId':'fixture-tab',
   'title':'Potato · '+run.name}]}
elif a[:2]==['terminal','read']:
 run=Path((root/'latest').read_text())
 result={'terminal':{'status':'exited' if (run/'finished.json').exists() or os.environ.get('FIXTURE_NO_RESULT') else 'running'}}
elif a[:2]==['terminal','wait']:
 result={'wait':{'satisfied':not bool(os.environ.get('FIXTURE_EXIT_UNKNOWN'))}}
elif a[:2]==['terminal','close']:
 run=Path((root/'latest').read_text())
 # A close is only accepted after both result and status have been saved.
 assert (run/'result.txt').is_file() and (run/'finished.json').is_file()
 assert (run/'error.txt').is_file()
 assert '--tab' in a
 if os.environ.get('FIXTURE_CLOSE_FAIL'): sys.exit('fixture close unavailable')
 result={}
else: sys.exit('Unexpected Orca call: '+repr(a))
print(json.dumps({'ok':True,'result':result}))
'''


MODEL_FIXTURE = r'''#!/usr/bin/python3
import json, os, sys, time
from pathlib import Path
Path(os.environ['NAMED_AGENT_FIXTURE_LOG']).write_text(json.dumps({
 'argv':sys.argv,'cwd':os.getcwd(),'configHome':os.environ.get('CODEX_HOME'),
 'claudeConfigHome':os.environ.get('CLAUDE_CONFIG_DIR'),
 'effort':os.environ.get('CLAUDE_CODE_EFFORT_LEVEL')}))
with Path(os.environ['NAMED_AGENT_FIXTURE_LOG']+'.calls').open('a') as calls:
 calls.write('model-start\n')
if os.environ.get('FIXTURE_MODEL_GATE'):
 while not Path(os.environ['FIXTURE_MODEL_GATE']).exists(): time.sleep(0.01)
if Path(sys.argv[0]).name=='claude':
 print(json.dumps({'type':'system','subtype':'init','session_id':'fixture-session'}),flush=True)
 print(json.dumps({'type':'assistant','message':{'content':[
  {'type':'tool_use','name':'Read','input':{'file_path':'fixture.py'}},
  {'type':'text','text':'対象ファイルを確認しています。'}]}}),flush=True)
 print(json.dumps({'type':'result','is_error':False,'session_id':'fixture-session',
  'modelUsage':{os.environ.get('NAMED_AGENT_FIXTURE_MODEL','claude-opus-5-5'):{}},
  'result':'fixture review result'}),flush=True)
else:
 print('fixture Codex is working',flush=True)
 if not os.environ.get('FIXTURE_NO_REPORT'):
  Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('fixture implementation result\n')
sys.exit(int(os.environ.get('NAMED_AGENT_FIXTURE_EXIT','0')))
'''


class TaskSessionTests(unittest.TestCase):
    def test_specialist_task_launches_and_collects_with_only_three_entry_homes(self):
        self.env['FIXTURE_ONLY_ENTRIES'] = '1'
        for role in ('kiwi', 'melon', 'potato'):
            with self.subTest(role=role):
                result = self.fixture.launch(role, '--task', 'Fixture scoped request', env=self.env)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = Path((self.state / 'latest').read_text())
                self.assertTrue((run / 'finished.json').is_file())
                request = json.loads((run / 'request.json').read_text())
                self.assertEqual(request['roleRouting']['homeRole'], 'peach' if role == 'potato' else 'banana')

    def setUp(self):
        self.fixture = test_named_agents.NamedAgentsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.env = self.fixture.env
        self.state = self.fixture.root / 'tasks'
        self.env['NAMED_TEAM_TASK_DIR'] = str(self.state)
        self.env['ORCA_CLI_COMMAND'] = str(self.fixture.bin / 'orca-fixture')
        self.env['NAMED_TEAM_TAB_WAIT_SECONDS'] = '1'
        self.env['NAMED_TEAM_RECEIPT_WAIT_SECONDS'] = '3'
        self.env['NAMED_TEAM_CLEANUP_WAIT_SECONDS'] = '0.2'
        for name, content in [('orca-fixture', ORCA_FIXTURE), ('codex', MODEL_FIXTURE), ('claude', MODEL_FIXTURE)]:
            (self.fixture.bin / name).write_text(content)

    def launch(self, role, *args):
        return self.fixture.launch(role, *args)

    def calls(self):
        return [json.loads(line) for line in (self.state / 'calls.jsonl').read_text().splitlines()]

    def run_dir(self):
        return Path((self.state / 'latest').read_text())

    def test_default_requests_show_progress_save_report_and_close_only_the_new_tab(self):
        for role in ('tomato', 'banana', 'melon', 'kiwi', 'potato'):
            with self.subTest(role=role):
                result = self.launch(role, 'task request')
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()
                create = [call for call in calls if call[:2] == ['terminal','create']][-1]
                self.assertNotIn('--focus', create)
                self.assertIn(role.capitalize(), create[create.index('--title') + 1])
                show = [call for call in calls if call[:2] == ['worktree','show']][-1]
                self.assertEqual(show[show.index('--worktree') + 1], 'id:fixture-workspace')
                self.assertFalse(any(c[:2] == ['terminal','wait'] for c in calls))
                self.assertEqual(calls[-1][:2], ['terminal','close'])
                self.assertEqual(calls[-1][calls[-1].index('--terminal') + 1], 'term_fixture')
                self.assertIn('--tab', calls[-1])
                run = self.run_dir()
                routing = json.loads((run / 'request.json').read_text())['roleRouting']
                if role in ('kiwi', 'potato'):
                    self.assertEqual(routing['parentRole'], 'banana')
                    self.assertEqual(routing['consultation'], ['tomato', 'fable'])
                elif role in ('tomato', 'banana'):
                    self.assertEqual(routing['layer'], 'upper')
                    self.assertIsNone(routing['parentRole'])
                self.assertTrue((run / 'closed.json').is_file())
                self.assertTrue((run / 'progress.log').read_text())
                visible = (run / 'visible.txt').read_text()
                self.assertIn('タスクを開始', visible)
                self.assertIn('実行中: Read' if role == 'potato' else 'fixture Codex is working', visible)
                self.assertIn('fixture review result' if role == 'potato' else 'fixture implementation result', result.stdout)

    def test_ambiguous_home_stops_before_starting_a_model_or_creating_a_tab(self):
        self.env['FIXTURE_DUPLICATE_ROLE'] = 'tomato'
        result = self.launch('tomato', 'task request')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Ambiguous workspace', result.stderr)
        self.assertFalse(self.fixture.log.exists())
        self.assertEqual([c[:2] for c in self.calls()], [['worktree','list']])

    def test_exec_compatibility_and_orca_prompt_also_use_new_sessions(self):
        runs = []
        for flag in ('--exec','--orca','--task'):
            result = self.launch('potato', flag, '--json', 'review request')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['modelUsage'], {'claude-opus-5-5':{}})
            runs.append(self.run_dir())
        self.assertEqual(len(set(runs)), 3)

    def test_create_timeout_recovers_same_tab_without_a_second_launch(self):
        self.env['FIXTURE_CREATE_TIMEOUT'] = '1'
        result = self.launch('potato', 'review request')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(c[:2] == ['terminal','create'] for c in self.calls()), 1)
        self.assertTrue((self.run_dir() / 'closed.json').exists())

    def test_absent_tab_aborts_without_model_or_second_create(self):
        # Absence after a timeout cannot rule out later renderer adoption.
        self.env['FIXTURE_CREATE_TIMEOUT'] = '1'
        self.env['FIXTURE_LIST_EMPTY'] = '1'
        self.env['FIXTURE_CREATE_TIMEOUT_ONCE'] = '1'
        self.env['NAMED_TEAM_TAB_WAIT_SECONDS'] = '1'
        result = self.launch('potato', 'review request')
        self.assertNotEqual(result.returncode, 0, result.stderr)
        creates = [c for c in self.calls() if c[:2] == ['terminal', 'create']]
        self.assertEqual(len(creates), 1, creates)
        self.assertNotIn('--focus', creates[0])
        self.assertTrue((self.run_dir() / 'launch-aborted.json').exists())
        self.assertFalse(self.fixture.log.exists())
        self.assertFalse((self.run_dir() / 'closed.json').exists())
        late = self.invoke_worker(self.run_dir())
        self.assertEqual(late.returncode, 4, late.stdout)
        self.assertFalse(self.fixture.log.exists())

    def invoke_worker(self, run, handle='term_fixture', env=None):
        settings = (env or self.env).copy()
        settings['ORCA_TERMINAL_HANDLE'] = handle
        return subprocess.run([sys.executable, str(test_named_agents.PACKAGE / 'lib/task_session.py'),
                               '--worker', str(run)], env=settings,
                              text=True, capture_output=True, timeout=5)

    def pending_run(self):
        run = self.fixture.root / 'pending-task'
        run.mkdir()
        request = {'role':'melon', 'cwd':str(self.fixture.workspace), 'collector':'codex',
                   'environment':{}, 'command':[str(self.fixture.bin / 'codex'), '--', 'fixture request']}
        (run / 'request.json').write_text(json.dumps(request))
        (run / 'terminal.json').write_text(json.dumps({'handle':'term_fixture','tabId':'fixture-tab'}))
        return run

    def test_completed_task_replay_preserves_all_reports_without_model_call(self):
        result = self.launch('melon', 'request')
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.run_dir()
        before = {f.name:f.read_bytes() for f in run.iterdir() if f.is_file()}
        calls = Path(str(self.fixture.log) + '.calls').read_text()
        replay = self.invoke_worker(run, handle='term_restored')
        self.assertEqual(replay.returncode, 4, replay.stdout)
        self.assertEqual(Path(str(self.fixture.log) + '.calls').read_text(), calls)
        self.assertEqual({name:(run/name).read_bytes() for name in before}, before)

    def test_started_or_legacy_finished_claim_never_retries_even_with_dead_pid(self):
        run = self.pending_run()
        for name, value in [('started.json', {'pid':999999999}),
                            ('finished.json', {'returncode':0}), ('closed.json', {'closed':True})]:
            with self.subTest(marker=name):
                (run/name).write_text(json.dumps(value))
                replay = self.invoke_worker(run)
                self.assertEqual(replay.returncode, 4, replay.stdout)
                self.assertFalse(self.fixture.log.exists())
                (run/name).unlink()

    def test_new_incarnation_and_missing_receipt_cannot_start_a_model(self):
        run = self.pending_run()
        replay = self.invoke_worker(run, handle='term_restored')
        self.assertEqual(replay.returncode, 4, replay.stdout)
        self.assertFalse(self.fixture.log.exists())
        (run / 'terminal.json').unlink()
        settings = self.env.copy(); settings['NAMED_TEAM_RECEIPT_WAIT_SECONDS'] = '0.05'
        late = self.invoke_worker(run, env=settings)
        self.assertEqual(late.returncode, 4, late.stdout)
        self.assertFalse(self.fixture.log.exists())
        self.assertFalse((run / 'started.json').exists())

    def test_overlapping_workers_start_only_one_model(self):
        run = self.pending_run()
        settings = self.env.copy()
        settings['ORCA_TERMINAL_HANDLE'] = 'term_fixture'
        gate = self.fixture.root / 'model-exit-gate'
        settings['FIXTURE_MODEL_GATE'] = str(gate)
        first = subprocess.Popen([sys.executable, str(test_named_agents.PACKAGE / 'lib/task_session.py'),
                                  '--worker', str(run)], env=settings,
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 3
            while not self.fixture.log.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(self.fixture.log.exists())
            second = self.invoke_worker(run, env=settings)
            self.assertEqual(second.returncode, 4, second.stdout)
            self.assertFalse((run / 'finished.json').exists())
            self.assertEqual(Path(str(self.fixture.log) + '.calls').read_text(), 'model-start\n')
        finally:
            gate.write_text('exit')
            stdout, stderr = first.communicate(timeout=5)
        self.assertEqual(first.returncode, 0, stdout + stderr)
        self.assertEqual(json.loads((run / 'finished.json').read_text())['returncode'], 0)

    def test_literal_request_and_config_are_preserved_in_fresh_terminal(self):
        marker = self.fixture.root / 'must-not-exist'
        request = '引用 " ; $(touch ' + str(marker) + ') `touch ' + str(marker) + '`\n$HOME'
        result = self.launch('potato', '--worktree', 'path:' + str(self.fixture.workspace), request)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.fixture.log.read_text())
        self.assertTrue(log['argv'][-1].endswith('今回の依頼:\n' + request))
        self.assertEqual(log['cwd'], str(self.fixture.workspace))
        self.assertEqual(log['claudeConfigHome'], str(self.fixture.claude_config))
        self.assertEqual(log['effort'], 'high')
        self.assertEqual(log['argv'][log['argv'].index('--output-format') + 1], 'stream-json')
        self.assertIn('--restricted', log['argv'])
        self.assertFalse(marker.exists())

    def test_wrong_actual_model_is_blocked_and_failure_is_saved_before_close(self):
        self.env['NAMED_AGENT_FIXTURE_MODEL'] = 'claude-sonnet-5-5'
        result = self.launch('potato', 'review request')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('BLOCKED', result.stderr)
        self.assertEqual((self.run_dir() / 'result.txt').read_text(), '')
        self.assertNotIn('実モデル検証済みの結果', (self.run_dir() / 'visible.txt').read_text())
        self.assertTrue((self.run_dir() / 'closed.json').is_file())

    def test_model_failure_returns_its_exit_code_after_recorded_cleanup(self):
        self.env['NAMED_AGENT_FIXTURE_EXIT'] = '7'
        result = self.launch('potato', 'review request')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('rc=7', (self.run_dir() / 'error.txt').read_text())
        self.assertTrue((self.run_dir() / 'closed.json').exists())

    def test_missing_codex_report_cannot_be_reported_as_completed(self):
        self.env['FIXTURE_NO_REPORT'] = '1'
        result = self.launch('melon', 'request')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('BLOCKED', (self.run_dir() / 'error.txt').read_text())

    def test_missing_result_retains_terminal_and_does_not_relaunch(self):
        self.env['FIXTURE_NO_RESULT'] = '1'
        result = self.launch('kiwi', 'request')
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(sum(c[:2] == ['terminal','create'] for c in self.calls()), 1)
        self.assertFalse(any(c[:2] == ['terminal','close'] for c in self.calls()))
        self.assertIn('タブを保持', result.stderr)

    def test_failed_durable_close_is_not_cleanup_success(self):
        self.env['FIXTURE_CLOSE_FAIL'] = '1'
        result = self.launch('kiwi', 'request')
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertTrue((self.run_dir() / 'result.txt').is_file())
        self.assertFalse((self.run_dir() / 'closed.json').exists())

    def test_only_wrapper_stays_alive_after_model_exit_until_cleanup(self):
        run = self.pending_run()
        settings = self.env.copy()
        settings['ORCA_TERMINAL_HANDLE'] = 'term_fixture'
        settings['NAMED_TEAM_CLEANUP_WAIT_SECONDS'] = '3'
        wrapper = subprocess.Popen([sys.executable, str(test_named_agents.PACKAGE / 'lib/task_session.py'),
                                    '--worker', str(run)], env=settings,
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 3
            while not (run / 'finished.json').exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((run / 'finished.json').exists())
            self.assertIsNone(wrapper.poll())
            self.assertEqual(Path(str(self.fixture.log) + '.calls').read_text(), 'model-start\n')
            self.assertEqual((run / 'result.txt').read_text(), 'fixture implementation result\n')
        finally:
            (run / 'closed.json').write_text(json.dumps({'closed':True}))
            stdout, stderr = wrapper.communicate(timeout=5)
        self.assertEqual(wrapper.returncode, 0, stdout + stderr)

    def test_collection_failure_stops_child_before_publishing_finished(self):
        sys.path.insert(0, str(test_named_agents.PACKAGE / 'lib'))
        self.addCleanup(sys.path.remove, str(test_named_agents.PACKAGE / 'lib'))
        import task_session
        run = self.pending_run()
        settings = self.env.copy()
        settings['FIXTURE_MODEL_GATE'] = str(self.fixture.root / 'never-released')
        children = []
        def fail_collection(child):
            children.append(child)
            deadline = time.monotonic() + 3
            while not self.fixture.log.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            raise OSError('fixture collection unavailable')
        with mock.patch.dict(os.environ, settings, clear=True), \
                mock.patch.object(task_session, 'lines_with_activity', side_effect=fail_collection):
            rc = task_session.execute_worker(run, json.loads((run / 'request.json').read_text()))
        self.assertEqual(rc, 3)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        children[0].stdout.close()
        self.assertEqual(json.loads((run / 'finished.json').read_text())['returncode'], 3)
        self.assertIn('collection unavailable', (run / 'error.txt').read_text())


if __name__ == '__main__':
    unittest.main()
