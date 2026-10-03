"""Visible task lifecycle regressions; only fixture backends and Orca are called."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

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
   'displayName':v.get('workspaceAliases',[v['workspace']])[0]} for v in roles.values()]
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
  executed=subprocess.run(['/bin/sh','-c',command], text=True, capture_output=True)
  (run/'visible.txt').write_text(executed.stdout+executed.stderr)
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
 result={'terminal':{'status':'exited'}}
elif a[:2]==['terminal','wait']:
 result={'wait':{'satisfied':not bool(os.environ.get('FIXTURE_EXIT_UNKNOWN'))}}
elif a[:2]==['terminal','close']:
 run=Path((root/'latest').read_text())
 # A close is only accepted after both result and status have been saved.
 assert (run/'result.txt').is_file() and (run/'finished.json').is_file()
 assert (run/'error.txt').is_file()
 if os.environ.get('FIXTURE_CLOSE_FAIL'): sys.exit('fixture close unavailable')
 result={}
else: sys.exit('Unexpected Orca call: '+repr(a))
print(json.dumps({'ok':True,'result':result}))
'''


MODEL_FIXTURE = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
Path(os.environ['NAMED_AGENT_FIXTURE_LOG']).write_text(json.dumps({
 'argv':sys.argv,'cwd':os.getcwd(),'configHome':os.environ.get('CODEX_HOME'),
 'claudeConfigHome':os.environ.get('CLAUDE_CONFIG_DIR'),
 'effort':os.environ.get('CLAUDE_CODE_EFFORT_LEVEL')}))
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
    def setUp(self):
        self.fixture = test_named_agents.NamedAgentsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.env = self.fixture.env
        self.state = self.fixture.root / 'tasks'
        self.env['NAMED_TEAM_TASK_DIR'] = str(self.state)
        self.env['ORCA_CLI_COMMAND'] = str(self.fixture.bin / 'orca-fixture')
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
                self.assertIn('--focus', create)
                self.assertIn(role.capitalize(), create[create.index('--title') + 1])
                show = [call for call in calls if call[:2] == ['worktree','show']][-1]
                self.assertEqual(show[show.index('--worktree') + 1], 'id:fixture-workspace')
                self.assertEqual(calls[-2][:2], ['terminal','wait'])
                self.assertEqual(calls[-1][:2], ['terminal','close'])
                self.assertEqual(calls[-1][calls[-1].index('--terminal') + 1], 'term_fixture')
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

    def test_absent_tab_is_recreated_once_without_focus(self):
        # --focus waits for the UI to switch; measured 2026-10-03 it times out and
        # creates nothing. After confirming absence, recover with one no-focus create.
        self.env['FIXTURE_CREATE_TIMEOUT'] = '1'
        self.env['FIXTURE_LIST_EMPTY'] = '1'
        self.env['FIXTURE_CREATE_TIMEOUT_ONCE'] = '1'
        self.env['NAMED_TEAM_TAB_WAIT_SECONDS'] = '1'
        result = self.launch('potato', 'review request')
        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [c for c in self.calls() if c[:2] == ['terminal', 'create']]
        self.assertEqual(len(creates), 2, creates)
        self.assertIn('--focus', creates[0])
        self.assertNotIn('--focus', creates[1])
        self.assertTrue((self.run_dir() / 'closed.json').exists())

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

    def test_unconfirmed_exit_or_failed_close_is_not_cleanup_success(self):
        for key in ('FIXTURE_EXIT_UNKNOWN', 'FIXTURE_CLOSE_FAIL'):
            with self.subTest(key=key):
                self.env[key] = '1'
                result = self.launch('kiwi', 'request')
                self.assertEqual(result.returncode, 4, result.stderr)
                self.assertTrue((self.run_dir() / 'result.txt').is_file())
                self.assertFalse((self.run_dir() / 'closed.json').exists())
                del self.env[key]


if __name__ == '__main__':
    unittest.main()
