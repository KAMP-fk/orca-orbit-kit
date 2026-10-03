"""Offline acquisition, outbox, launch fencing and native worker lifecycle tests."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import event_monitor as monitor

NOW = '2026-10-03T10:00:00Z'


class FakeClient:
    def __init__(self):
        self.calls = []
        self.busy = False
        self.launch_error = None
        self.release_error = False
        self.effective = {'model': 'gpt-6.1-sol', 'effort': 'medium'}
        self.rows = []
        self.started = 0
        self.current_run = 'run-monitor'

    def call(self, *args, mutation=False):
        self.calls.append(args)
        if args[:2] == ('orchestration', 'run-current'):
            return {'run': {'id': self.current_run}}
        if args[:2] == ('worktree', 'ps'):
            return {'truncated': False, 'hostScope': {'omittedHostIds': []},
                    'worktrees': [{'worktreeId': role+'-home', 'path': str(monitor.ROOT.parents[1]/'workspaces/orca'/role.capitalize())
                                  if role in ('kiwi','potato','melon') else str(Path(value['workspaceRoot']).expanduser()),
                                  'displayName': value['workspace'], 'agents': [{'state':'working'}] if self.busy else [],
                                  'hostId': 'local'} for role,value in monitor.ROLES.items()]}
        if args[:2] == ('orchestration', 'worker-start'):
            self.started += 1
            if self.launch_error:
                raise monitor.AcquisitionError(self.launch_error)
            return {'state': 'ready', 'dispatchId': 'dispatch-'+str(self.started), 'taskId': 'task-'+str(self.started),
                    'launch': {'requested': {'model':'gpt-6.1-sol','effort':'medium'}, 'effective': self.effective}}
        if args[:2] == ('orchestration', 'worker-list'):
            return {'workers':self.rows, 'scope':{'source':'flag'}, 'page':{'hasMore':False}}
        if args[:2] == ('orchestration', 'worker-release'):
            if self.release_error:
                raise monitor.AcquisitionError('release_unconfirmed')
            return {'state':'released', 'archive':{'status':'saved'}}
        raise AssertionError(args)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='event-monitor-')
        self.config = json.loads(monitor.CONFIG.read_text())
        self.config['stateRoot'] = self.directory.name
        self.context = monitor.state(self.config)
        self.db = self.context.__enter__()
        with self.db:
            self.db.execute('INSERT INTO meta VALUES (?,?)', ('run','run-monitor'))
        self.client = FakeClient()

    def tearDown(self):
        self.context.__exit__(None,None,None)
        self.directory.cleanup()

    def changed(self, source='linear', **fields):
        row={'key':'CAF-100','title':'before','url':'https://linear.app/example','labels':[]}
        monitor.observe(self.db,source,[row],NOW)
        row.update(title='after',**fields)
        monitor.observe(self.db,source,[row],NOW)

    def events(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM events ORDER BY rowid')]

    def settled(self, worker='succeeded', dispatch='completed'):
        return {'runId':'run-monitor','dispatchId':'dispatch-1','workerState':worker,
                'dispatchStatus':dispatch,'terminalState':'reclaimable'}

    def test_initial_baseline_and_unchanged_reads_do_not_wake_models(self):
        row={'key':'CAF-1','title':'existing'}
        for _ in range(2): monitor.observe(self.db,'linear',[row],NOW)
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),0)
        self.assertEqual(self.events(),[])
        self.assertEqual(self.client.started,0)

    def test_pending_versions_coalesce_without_destroying_audit(self):
        self.changed()
        monitor.observe(self.db,'linear',[{'key':'CAF-100','title':'newest'}],NOW)
        self.assertEqual([row['status'] for row in self.events()],['superseded','pending'])

    def test_dispatch_uses_exact_existing_home_and_profile_defaults_once(self):
        self.changed()
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),1)
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),0)
        launch=next(c for c in self.client.calls if c[:2]==('orchestration','worker-start'))
        self.assertEqual(launch[launch.index('--worktree')+1],'id:banana-home')
        self.assertEqual(launch[launch.index('--model')+1],'gpt-6.1-sol')
        self.assertEqual(launch[launch.index('--effort')+1],'medium')
        self.assertNotIn('claude',launch)
        self.assertEqual(self.client.started,1)

    def test_busy_home_keeps_changes_pending(self):
        self.changed();self.client.busy=True
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),0)
        self.assertEqual(self.events()[0]['status'],'pending')
        self.client.busy=False
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),1)

    def test_missing_native_worktree_identity_does_not_prepare_or_launch(self):
        self.changed()
        original = self.client.call
        def call(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[:2] == ('worktree', 'ps'):
                for home in result['worktrees']:
                    home['id'] = home.pop('worktreeId')
            return result
        self.client.call = call
        with self.assertRaisesRegex(RuntimeError, 'native worktree identity'):
            monitor.dispatch(self.db,self.client,self.config)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)
        self.assertEqual(self.events()[0]['status'],'pending')
        self.assertEqual(self.client.started,0)

    def test_later_changes_wait_while_same_role_is_active(self):
        self.changed();monitor.dispatch(self.db,self.client,self.config)
        monitor.observe(self.db,'linear',[{'key':'CAF-101','title':'new'}],NOW)
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),0)
        self.assertEqual(self.client.started,1)

    def test_unknown_launch_is_never_retried_even_when_missing_from_inventory(self):
        self.changed();self.client.launch_error='command_unconfirmed'
        monitor.dispatch(self.db,self.client,self.config)
        self.client.launch_error=None
        for _ in range(2):monitor.dispatch(self.db,self.client,self.config)
        self.assertEqual(self.client.started,1)
        self.assertEqual(self.events()[0]['status'],'unknown')

    def test_wrong_effective_model_retains_dispatch_evidence_and_fences_role(self):
        self.changed();self.client.effective={'model':'unexpected','effort':'ultra'}
        monitor.dispatch(self.db,self.client,self.config)
        batch=self.db.execute('SELECT * FROM batches').fetchone()
        self.assertEqual(batch['status'],'unknown')
        self.assertEqual(batch['dispatch'],'dispatch-1')
        self.assertEqual(json.loads(batch['receipt'])['receipt']['launch']['effective']['model'],'unexpected')

    def test_accepted_settlement_releases_only_its_worker_and_allows_next_batch(self):
        self.changed();monitor.dispatch(self.db,self.client,self.config)
        self.client.rows=[self.settled()]
        monitor.reconcile(self.db,self.client,'run-monitor')
        self.assertEqual(self.events()[0]['status'],'completed')
        self.assertIn(('orchestration','worker-release','--dispatch','dispatch-1'),self.client.calls)
        self.assertFalse(any(c[:2]==('terminal','close') for c in self.client.calls))
        monitor.observe(self.db,'linear',[{'key':'CAF-101','title':'next'}],NOW)
        self.assertEqual(monitor.dispatch(self.db,self.client,self.config),1)

    def test_missing_worker_is_not_completion_or_release(self):
        self.changed();monitor.dispatch(self.db,self.client,self.config)
        monitor.reconcile(self.db,self.client,'run-monitor')
        self.assertEqual(self.events()[0]['status'],'active')
        self.assertFalse(any(c[:2]==('orchestration','worker-release') for c in self.client.calls))

    def test_release_uncertainty_is_saved_before_mutation_and_never_repeated(self):
        self.changed();monitor.dispatch(self.db,self.client,self.config)
        self.client.rows=[self.settled()];self.client.release_error=True
        with self.assertRaises(monitor.AcquisitionError):monitor.reconcile(self.db,self.client,'run-monitor')
        monitor.reconcile(self.db,self.client,'run-monitor')
        self.assertEqual(sum(c[:2]==('orchestration','worker-release') for c in self.client.calls),1)
        self.assertEqual(self.db.execute('SELECT status FROM batches').fetchone()['status'],'release_pending')

    def test_source_failure_preserves_facts_and_only_alerts_once_at_threshold(self):
        row={'key':'CAF-1','title':'last success'}
        monitor.observe(self.db,'linear',[row],NOW)
        for _ in range(5):monitor.failed(self.db,'linear','timeout',NOW,3)
        self.assertEqual(len(self.events()),1)
        self.assertEqual(self.events()[0]['role'],'kiwi')
        self.assertEqual(json.loads(self.db.execute('SELECT payload FROM facts').fetchone()['payload']),row)
        monitor.observe(self.db,'linear',[row],NOW,3)
        self.assertEqual([e['status'] for e in self.events()],['superseded','pending'])
        self.assertEqual(self.events()[-1]['kind'],'recovered')

    def test_duplicate_source_snapshot_does_not_advance_baseline(self):
        with self.assertRaises(monitor.AcquisitionError):
            monitor.observe(self.db,'linear',[{'key':'same'},{'key':'same'}],NOW)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sources').fetchone()[0],0)

    def test_decision_updates_go_to_tomato(self):
        self.changed(labels=['type:decision'])
        self.assertEqual(self.events()[0]['role'],'tomato')

    def test_routine_ci_progress_is_observed_without_launching(self):
        row={'key':'42','head':'a'*40,'checks':[{'status':'queued','conclusion':None}],'statuses':[]}
        monitor.observe(self.db,'ci:42',[row],NOW)
        row['checks'][0]['status']='in_progress'
        monitor.observe(self.db,'ci:42',[row],NOW)
        self.assertEqual(self.events()[0]['status'],'observed')
        row['checks'][0].update(status='completed',conclusion='failure')
        monitor.observe(self.db,'ci:42',[row],NOW)
        self.assertEqual(self.events()[-1]['status'],'pending')
        self.assertEqual(self.events()[-1]['role'],'banana')

    def test_wrong_run_does_not_prepare_or_launch_a_batch(self):
        self.changed();self.client.current_run='another-run'
        with self.assertRaisesRegex(RuntimeError,'coordinator terminal'):
            monitor.dispatch(self.db,self.client,self.config)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)

    def test_pending_batch_cannot_enable_a_claude_role(self):
        self.changed()
        with self.db:self.db.execute("UPDATE events SET role='potato'")
        with self.assertRaisesRegex(RuntimeError,'not permitted'):
            monitor.dispatch(self.db,self.client,self.config)
        self.assertEqual(self.client.started,0)


class AcquisitionTests(unittest.TestCase):
    def test_truncated_linear_response_without_cursor_is_not_empty_success(self):
        config=json.loads(monitor.CONFIG.read_text())
        fake=type('C',(),{'call':lambda *a: {'issues':[], 'truncated':True,
                   'meta':{'workspaceId':config['linearWorkspace'],'hasMore':True}}})()
        with self.assertRaisesRegex(monitor.AcquisitionError,'cursor'):
            monitor.collect_linear(fake,config)

    def test_pagination_rejects_changing_counts_and_duplicate_rows(self):
        for second in ({'check_runs':[{'id':101}],'total_count':102},
                       {'check_runs':[{'id':1}],'total_count':101}):
            responses=iter([{'check_runs':[{'id':n} for n in range(1,101)],'total_count':101},second])
            fake=type('C',(),{'github':lambda *a:next(responses)})()
            with self.assertRaises(monitor.AcquisitionError):monitor.pages(fake,'checks','check_runs')

    def test_head_change_discards_ci_observation(self):
        config=json.loads(monitor.CONFIG.read_text())
        def api(_,endpoint):
            if '/check-runs' in endpoint:return {'check_runs':[],'total_count':0}
            if '/statuses' in endpoint:return []
            return {'head':{'sha':'b'*40},'state':'open'}
        fake=type('C',(),{'github':api})()
        with self.assertRaisesRegex(monitor.AcquisitionError,'head_changed'):
            monitor.collect_ci(fake,config,{'head':{'sha':'a'*40},'number':1,'html_url':'https://github.com/x'})

    def test_scheduler_request_never_calls_a_model_and_always_skips_generic_provider(self):
        with tempfile.TemporaryDirectory(prefix='event-clock-') as directory:
            p=subprocess.run([str(PACKAGE/'bin/event-watch'),'request','--scheduler','--state-root',directory],
                             capture_output=True,text=True,timeout=10,
                             env={k:v for k,v in os.environ.items() if k not in ('ORCA_ENVIRONMENT','ORCA_PAIRING_CODE')})
            self.assertEqual(p.returncode,75,p.stderr+p.stdout)
            self.assertEqual(json.loads(p.stdout)['starts'],0)
            db=sqlite3.connect(str(Path(directory)/'monitor.sqlite3'))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)
            db.close()

    def test_state_scope_and_symlinks_are_not_silently_replaced(self):
        config=json.loads(monitor.CONFIG.read_text())
        with tempfile.TemporaryDirectory(prefix='event-state-') as directory:
            config['stateRoot']=directory
            with monitor.state(config):pass
            wrong=dict(config,linearProject='other-project')
            with self.assertRaisesRegex(RuntimeError,'another project'):
                with monitor.state(wrong):pass
            link=Path(directory)/'linked'
            link.symlink_to(Path(directory)/'monitor.sqlite3')
            with self.assertRaisesRegex(RuntimeError,'symlink'):
                with monitor.state(config,link):pass

    def test_model_free_coordinator_owns_run_and_consumes_clock_request_once(self):
        with tempfile.TemporaryDirectory(prefix='event-coordinator-') as directory:
            root=Path(directory)
            config=json.loads(monitor.CONFIG.read_text())
            config['stateRoot']=str(root/'state')
            config_path=root/'config.json';config_path.write_text(json.dumps(config))
            fake_orca=root/'orca'
            fake_orca.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with Path(os.environ['FIXTURE_CALLS']).open('a') as f:f.write(json.dumps(args)+'\\n')
if args[:2]==['orchestration','run-create']:result={'run':{'id':'run-fixture'}}
elif args[:2] in (['orchestration','run-current'],['orchestration','run-use']):result={'run':{'id':'run-fixture'}}
elif args[:2]==['linear','list-issues']:result={'issues':[],'truncated':False,'meta':{'workspaceId':'610becb0-951f-43eb-853c-0b1b28cd3d3f','hasMore':False}}
else:sys.exit('Unexpected operation: '+repr(args))
print(json.dumps({'ok':True,'result':result}))
''');fake_orca.chmod(0o755)
            fake_gh=root/'gh';fake_gh.write_text('#!/usr/bin/env python3\nprint("[]")\n');fake_gh.chmod(0o755)
            env={k:v for k,v in os.environ.items() if k not in ('ORCA_ENVIRONMENT','ORCA_PAIRING_CODE')}
            env.update(ORCA_CLI_COMMAND=str(fake_orca),ORCA_TERMINAL_HANDLE='fixture-owned-handle',
                       FIXTURE_CALLS=str(root/'calls.jsonl'),PATH=str(root)+os.pathsep+os.environ['PATH'])
            entry=[str(PACKAGE/'bin/event-watch')]
            process=subprocess.Popen(entry+['serve','--config',str(config_path)],env=env,
                                     stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            try:
                def meta():
                    db_path=root/'state/monitor.sqlite3'
                    if not db_path.exists():return {}
                    with sqlite3.connect(str(db_path)) as db:
                        try:return dict(db.execute('SELECT key,value FROM meta'))
                        except sqlite3.OperationalError:return {}
                deadline=time.monotonic()+8
                while 'coordinatorHandle' not in meta() and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(meta().get('coordinatorHandle'),'fixture-owned-handle')
                duplicate=subprocess.run(entry+['serve','--config',str(config_path)],env=env,
                                         capture_output=True,text=True,timeout=5)
                self.assertEqual(duplicate.returncode,2)
                clock=subprocess.run(entry+['request','--scheduler','--config',str(config_path)],env=env,
                                     capture_output=True,text=True,timeout=5)
                self.assertEqual(clock.returncode,75,clock.stdout+clock.stderr)
                requested=json.loads(clock.stdout)['requested']
                deadline=time.monotonic()+8
                while meta().get('handledRequest')!=requested and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(meta().get('handledRequest'),requested)
                self.assertEqual(meta().get('lastTickError'),'')
                calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
                self.assertEqual(sum(c[:2]==['orchestration','run-create'] for c in calls),1)
                self.assertEqual(sum(c[:2]==['linear','list-issues'] for c in calls),1)
                self.assertFalse(any(c[:2]==['orchestration','worker-start'] for c in calls))
                self.assertFalse(any('--from' in c for c in calls))
            finally:
                process.terminate()
                _,error=process.communicate(timeout=5)
                self.assertEqual(process.returncode,0,error)


if __name__=='__main__':
    unittest.main()
