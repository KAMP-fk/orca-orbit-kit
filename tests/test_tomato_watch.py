#!/usr/bin/env python3
"""One-shot Tomato observations; fixtures never connect to hosted services."""
import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

WATCH = Path('/Users/kamp/orca/agents/team/roles/tomato/skill/bin/watch')
SHA = 'a' * 40
MOCK = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
name=Path(sys.argv[0]).name; args=sys.argv[1:]
cfg=json.loads(Path(os.environ['WATCH_FIXTURE']).read_text())
with open(os.environ['WATCH_CALLS'],'a') as f: f.write(json.dumps([name]+args)+'\n')
def emit(value): print(json.dumps(value))
def fail(key):
 if cfg.get(key): sys.exit(cfg[key])
if name=='git':
 if cfg.get('deny_git_overrides') and any(key.startswith('GIT_') for key in os.environ): sys.exit('Git environment override was inherited')
 if 'fetch' in args: fail('fetch_rc')
 elif 'worktree' in args: sys.stdout.buffer.write(('worktree '+args[1]+'\0HEAD '+'a'*40+'\0branch refs/heads/main\0\0').encode())
 elif 'rev-list' in args: print('0')
 elif 'rev-parse' in args: print(args[1] if '--show-toplevel' in args else cfg.get('main_sha','a'*40))
 elif 'log' in args: fail('log_rc');print('fixture commit')
 else: sys.exit('unexpected git call')
elif name=='gh':
 if args[:2]==['pr','list']: fail('prs_rc');emit(cfg.get('prs',[]))
 elif args[:2]==['pr','checks']:
  n=args[2];fail('checks_fetch_rc');fail('checks_fetch_rc_'+n)
  emit(cfg.get('checks_'+n,cfg.get('checks',[{'name':'build','bucket':'pass'}])))
  sys.exit(cfg.get('checks_rc',0))
 elif args[:2]==['pr','view']:
  n=args[2];fail('view_rc');emit(cfg.get('view',{'headRefOid':cfg.get('confirmed_head_'+n,cfg.get('confirmed_head','a'*40))}))
 elif args[:1]==['api']:
  if any('/actions/runs?' in value for value in args):
   target=next(value for value in args if '/actions/runs?' in value)
   page={'total_count':0,'workflow_runs':[]};emit(page if 'status=success' in target else [page])
  else: fail('statuses_rc');emit(cfg.get('statuses',[]))
 else: sys.exit('unexpected gh call')
elif name=='guard': sys.exit(cfg.get('guard_rc',0))
elif name=='launchctl': pass
else: sys.exit('unexpected executable')
'''


class TomatoObservationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tomato-observation-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'; self.bin.mkdir()
        for name in ('git', 'gh', 'guard', 'launchctl'):
            path=self.bin/name;path.write_text(MOCK);path.chmod(0o755)
        self.fixture=self.root/'fixture.json';self.calls_file=self.root/'calls.jsonl'
        self.config={}
        self.state=self.root/'watch-state'
        self.brain=self.root/'brain';self.inbox=self.brain/'Tomato/inbox.md'
        self.inbox.parent.mkdir(parents=True);self.inbox.write_text('現在の窓口: fixture\n')
        self.socket_dir=self.root/'s';self.socket_dir.mkdir()
        self.env={key:value for key,value in os.environ.items() if not key.startswith(('GIT_','TOMATO_'))}
        self.env.update(PATH=str(self.bin)+':'+os.environ['PATH'],
            WATCH_FIXTURE=str(self.fixture),WATCH_CALLS=str(self.calls_file),
            TOMATO_STATE=str(self.state),TOMATO_BRAIN=str(self.brain),
            TOMATO_EXCLUDE=str(self.root/'exclude'),TOMATO_GUARD=str(self.bin/'guard'),
            TOMATO_SOCKET_DIR=str(self.socket_dir))

    def pr(self, number=1, **values):
        result=dict(number=number,title='fixture',isDraft=False,updatedAt='2020-01-01T00:00:00Z',
            headRefOid=SHA,labels=[{'name':'review:required'}])
        result.update(values);return result

    def run_watch(self, *args, executable=WATCH):
        self.fixture.write_text(json.dumps(self.config))
        return subprocess.run([str(executable),*args],env=self.env,text=True,capture_output=True,timeout=20)

    def observation(self, mode='all', rc=0, *flags):
        r=self.run_watch(mode,'--json',*flags)
        self.assertEqual(r.returncode,rc,r.stderr+r.stdout)
        value=json.loads(r.stdout)
        self.assertEqual(value['schema_version'],1)
        self.assertRegex(value['observed_at'],r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        return value

    def check(self, observation, name):
        return next(x for x in observation['checks'] if x['name']==name)

    def calls(self):
        return [json.loads(x) for x in self.calls_file.read_text().splitlines()] if self.calls_file.exists() else []

    def snapshot(self, name):
        return next(Path(str(self.state)+'.d').glob('*/'+name+'.json'))

    def test_help_and_arguments_do_not_fetch_or_save(self):
        for args,rc in [(('--help',),0),(('main','spin'),2),(('--bad',),2)]:
            with self.subTest(args=args): self.assertEqual(self.run_watch(*args).returncode,rc)
        self.assertFalse(self.calls());self.assertFalse(Path(str(self.state)+'.d').exists())

    def test_all_shares_one_pr_list_with_source_time(self):
        self.config['prs']=[self.pr()]
        value=self.observation()
        self.assertEqual(sum(c[:3]==['gh','pr','list'] for c in self.calls()),1)
        stuck=self.check(value,'stuck');spin=self.check(value,'spin')
        self.assertEqual(stuck['sources'][0],spin['sources'][0])
        self.assertEqual(spin['items'][0]['headRefOid'],SHA)
        self.assertEqual(spin['items'][0]['ci'],'pass')
        self.assertIn('unconfirmed',spin['items'][0]['coverage'])

    def test_changes_are_quiet_for_unchanged_observations(self):
        self.config['prs']=[self.pr()]
        first=self.observation('stuck');self.assertTrue(first['has_changes'])
        second=self.observation('stuck');self.assertFalse(second['has_changes'])
        self.assertEqual(self.run_watch('changes','stuck').stdout,'')
        self.assertEqual(self.run_watch('stuck','--changes').stdout,'')

    def test_healthy_pr_activity_does_not_trigger_stuck_change(self):
        now=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.config['prs']=[self.pr(updatedAt=now)]
        self.assertFalse(self.observation('stuck')['has_changes'])
        self.config['prs']=[self.pr(number=2,updatedAt=now)]
        self.assertFalse(self.observation('stuck')['has_changes'])

    def test_stalled_finding_resolution_is_a_change(self):
        self.config['prs']=[self.pr()];self.observation('stuck')
        self.config['prs']=[]
        check=self.check(self.observation('stuck'),'stuck')
        self.assertTrue(check['change']['changed']);self.assertEqual(check['findings'],[])
        self.assertEqual(check['change']['events'][0]['before']['findings'][0]['id'],'1')

    def test_failure_does_not_erase_last_success_and_recovery_changes(self):
        self.config['prs']=[self.pr()];self.observation('stuck')
        old=json.loads(self.snapshot('stuck').read_text())['last_success']
        self.config['prs_rc']=1
        failed=self.observation('stuck',1)
        self.assertEqual(failed['status'],'incomplete')
        snap=json.loads(self.snapshot('stuck').read_text())
        self.assertEqual(snap['last_success'],old)
        self.assertEqual(snap['latest']['status'],'error')
        self.assertFalse(self.observation('stuck',1)['has_changes'])
        del self.config['prs_rc']
        recovered=self.check(self.observation('stuck'),'stuck')
        self.assertEqual(recovered['change']['events'][0]['type'],'observation_recovered')

    def test_partial_read_reports_known_and_unknown_without_none(self):
        self.config['prs']=[self.pr(),self.pr(number=2)]
        self.config['checks_fetch_rc_2']=4
        value=self.observation('spin',1);check=self.check(value,'spin')
        self.assertEqual(check['status'],'partial')
        self.assertEqual(check['items'][0]['number'],1)
        self.assertEqual(len(check['errors']),1)
        self.assertNotIn('無し',check['text'])

    def test_head_change_invalidates_green_evidence(self):
        self.config.update(prs=[self.pr()],confirmed_head='b'*40)
        check=self.check(self.observation('spin',1),'spin')
        self.assertEqual(check['status'],'error');self.assertEqual(check['findings'],[])
        self.assertEqual(check['errors'][0]['source'],'head')
        self.assertNotIn('CI は緑。',check['text'])

    def test_head_recheck_failure_is_unknown(self):
        self.config.update(prs=[self.pr()],view_rc=4)
        self.assertEqual(self.check(self.observation('spin',1),'spin')['errors'][0]['source'],'head')

    def test_skipped_neutral_pending_failed_empty_and_exit_mismatch_not_green(self):
        self.config['prs']=[self.pr()]
        for bucket in ('skipping','neutral','pending','fail','cancel'):
            with self.subTest(bucket=bucket):
                self.config['checks']=[{'name':'build','bucket':bucket}]
                check=self.check(self.observation('spin'),'spin')
                self.assertEqual(check['items'][0]['ci'],'not_passed');self.assertFalse(check['findings'])
        self.config['checks']=[]
        self.assertEqual(self.check(self.observation('spin'),'spin')['items'][0]['ci'],'empty')
        self.config.update(checks=[{'name':'build','bucket':'pass'}],checks_rc=8)
        self.assertEqual(self.check(self.observation('spin'),'spin')['items'][0]['ci'],'not_passed')
        self.assertFalse(any(c[0:2]==['gh','api'] for c in self.calls()))

    def test_review_gate_excluded_from_other_checks(self):
        self.config.update(prs=[self.pr()],checks=[{'name':'review:passed','bucket':'pass'}])
        self.assertEqual(self.check(self.observation('spin'),'spin')['items'][0]['ci'],'empty')

    def test_failed_review_gate_does_not_hide_green_other_checks(self):
        self.config.update(prs=[self.pr()],checks=[{'name':'build','bucket':'pass'},
            {'name':'review:passed','bucket':'fail'}],checks_rc=1,
            statuses=[{'context':'review:passed','state':'failure'}])
        check=self.check(self.observation('spin'),'spin')
        self.assertEqual(check['items'][0]['ci'],'pass');self.assertTrue(check['findings'])

    def test_invalid_exclusion_file_is_not_treated_as_empty(self):
        self.config['prs']=[self.pr()];(self.root/'exclude').mkdir()
        check=self.check(self.observation('stuck',1),'stuck')
        self.assertEqual(check['errors'][0]['source'],'exclude');self.assertFalse(check['findings'])
        (self.root/'exclude').rmdir();(self.root/'exclude').write_text('all # invalid\n')
        check=self.check(self.observation('spin',1),'spin')
        self.assertEqual(check['errors'][0]['source'],'exclude');self.assertFalse(check['findings'])

    def test_all_status_pages_are_used(self):
        self.config.update(prs=[self.pr()],statuses=[[{'context':'other','state':'success'}],[{'context':'review:passed','state':'success'}]])
        check=self.check(self.observation('spin'),'spin')
        self.assertFalse(check['findings']);self.assertEqual(check['items'][0]['review_status'],'success')
        api=next(c for c in self.calls() if c[:2]==['gh','api'])
        self.assertIn('--paginate',api);self.assertIn('--slurp',api)

    def test_latest_status_wins_over_old_pass(self):
        self.config.update(prs=[self.pr()],statuses=[{'context':'review:passed','state':'failure'},{'context':'review:passed','state':'success'}])
        self.assertEqual(self.check(self.observation('spin'),'spin')['items'][0]['review_status'],'failure')

    def test_malformed_ci_status_and_head_are_not_missing(self):
        for update,source in [({'checks':[{'name':'build'}]},'ci'),({'statuses':{'state':'success'}},'status'),({'statuses':[{'context':'review:passed','state':'unknown'}]},'status'),({'view':{}},'head')]:
            with self.subTest(update=update):
                self.config=dict(prs=[self.pr()],**update)
                check=self.check(self.observation('spin',1),'spin')
                self.assertEqual(check['errors'][0]['source'],source);self.assertFalse(check['findings'])

    def test_incomplete_pr_lists_are_not_absence(self):
        for prs in ({'number':1},[self.pr(),self.pr()],[self.pr(title=None)],[self.pr(labels=None)],[self.pr(number=i+1) for i in range(1000)]):
            with self.subTest(length=len(prs)):
                self.config['prs']=prs
                check=self.check(self.observation('stuck',1),'stuck')
                self.assertEqual(check['status'],'error');self.assertNotIn('無し',check['text'])

    def test_bad_future_activity_is_unknown(self):
        for updated in ('broken','2999-01-01T00:00:00Z'):
            self.config['prs']=[self.pr(updatedAt=updated)]
            check=self.check(self.observation('stuck',1),'stuck')
            self.assertEqual(check['status'],'error');self.assertFalse(check['findings'])

    def test_state_is_scoped_by_repo_checkout_and_brain(self):
        self.observation('main')
        self.env['TOMATO_REPO']='test/repo';self.config['main_sha']='b'*40
        check=self.check(self.observation('main'),'main');self.assertEqual(check['change']['status'],'initial')
        self.env['TOMATO_WORK']=str(self.root/'another-checkout');self.observation('main')
        self.env['TOMATO_BRAIN']=str(self.root/'another-brain');self.observation('main')
        states=list(Path(str(self.state)+'.d').glob('*/main.json'))
        self.assertEqual(len(states),4)
        self.assertEqual(self.state.read_text(),'main='+SHA+'\n')

    def test_default_legacy_migration_and_failed_fetch_compatibility(self):
        self.state.write_text('main=aaaaaaa\nother=preserved\n')
        self.observation('main')
        self.assertEqual(self.state.read_text(),'other=preserved\nmain='+SHA+'\n')
        snapshot=self.snapshot('main').read_text();self.config['fetch_rc']=1
        failed=self.check(self.observation('main',1),'main')
        self.assertFalse(failed['items']);self.assertNotIn('動いていない',failed['text'])
        self.assertEqual(json.loads(self.snapshot('main').read_text())['last_success'],json.loads(snapshot)['last_success'])
        self.assertEqual(self.state.read_text(),'other=preserved\nmain='+SHA+'\n')

    def test_current_main_sha_must_be_full_and_error_keeps_success(self):
        self.observation('main')
        previous=json.loads(self.snapshot('main').read_text())['last_success']
        for current in ('aaaaaaa','a'*8,'a'*39,'a'*41,'A'*40,'invalid'):
            with self.subTest(current=current):
                self.config['main_sha']=current
                check=self.check(self.observation('main',1),'main')
                self.assertEqual(check['status'],'error');self.assertEqual(check['items'],[])
                self.assertEqual(check['errors'][0]['source'],'git')
                self.assertNotIn('動いていない',check['text'])
                self.assertEqual(json.loads(self.snapshot('main').read_text())['last_success'],previous)
                self.assertEqual(self.state.read_text(),'main='+SHA+'\n')
    def test_unbound_legacy_not_imported_for_another_repo(self):
        self.state.write_text('main=bbbbbbb\n');self.env['TOMATO_REPO']='test/repo'
        check=self.check(self.observation('main'),'main')
        self.assertIn('初回',check['text']);self.assertEqual(self.state.read_text(),'main=bbbbbbb\n')

    def test_git_environment_overrides_are_removed_before_observation(self):
        self.env.update(GIT_DIR=str(self.root/'foreign.git'),GIT_WORK_TREE=str(self.root/'foreign'),
            GIT_INDEX_FILE=str(self.root/'foreign-index'),GIT_COMMON_DIR=str(self.root/'foreign-common'),
            GIT_OBJECT_DIRECTORY=str(self.root/'foreign-objects'),GIT_CONFIG_COUNT='1',
            GIT_CONFIG_KEY_0='core.bare',GIT_CONFIG_VALUE_0='true')
        self.config['deny_git_overrides']=True
        self.assertEqual(self.check(self.observation('main'),'main')['items'][0]['sha'],SHA)

    def test_corrupt_state_is_preserved_and_reported(self):
        self.observation('main');path=self.snapshot('main');path.write_text('{broken')
        value=self.observation('main',1)
        self.assertEqual(value['status'],'incomplete');self.assertTrue(value['state_errors'])
        self.assertEqual(path.read_text(),'{broken')
        self.assertEqual(self.check(value,'main')['change']['status'],'unavailable')

    def test_concurrent_writer_lock_preserves_baseline(self):
        self.observation('main');path=self.snapshot('main');before=path.read_text()
        (path.parent/'.lock').mkdir()
        self.config['main_sha']='b'*40
        value=self.observation('main',1)
        self.assertTrue(value['state_errors']);self.assertEqual(path.read_text(),before)
        self.assertTrue((path.parent/'.lock').exists())

    def test_symlink_state_directory_is_not_followed(self):
        external=self.root/'external';external.mkdir()
        Path(str(self.state)+'.d').symlink_to(external,target_is_directory=True)
        value=self.observation('stuck',1)
        self.assertTrue(value['state_errors']);self.assertEqual(list(external.iterdir()),[])

    def test_inbox_read_records_identity_as_unconfirmed(self):
        check=self.check(self.observation('window'),'window')
        self.assertEqual(check['items'][0]['owner'],'fixture')
        self.assertIn('生存・本人は別に確認',check['text'])
        self.assertIn('unconfirmed',check['items'][1]['meaning'])

    def test_window_guard_and_socket_sources_are_fixture_only(self):
        session=socket.socket(socket.AF_UNIX);self.addCleanup(session.close)
        session.bind(str(self.socket_dir/'f.sock'))
        (self.socket_dir/'ordinary.sock').write_text('not a socket\n')
        passed=self.check(self.observation('window'),'window')
        self.assertEqual(passed['items'][1]['count'],1)
        self.assertEqual(passed['items'][1]['source'],str(self.socket_dir/'*.sock'))
        self.assertEqual(passed['items'][2]['status'],'ok')
        self.assertEqual(passed['items'][2]['source'],str(self.bin/'guard'))
        self.assertEqual(sum(c[0]=='guard' for c in self.calls()),1)
        self.config['guard_rc']=1
        failed=self.check(self.observation('window',1),'window')
        self.assertEqual(failed['items'][2]['status'],'error')
        self.assertEqual(failed['errors'][0]['target'],str(self.bin/'guard'))

    def test_missing_owner_is_a_finding_and_unreadable_inbox_is_an_error(self):
        self.inbox.write_text('窓口は main に書く\n')
        check=self.check(self.observation('window'),'window')
        self.assertIsNone(check['items'][0]['owner']);self.assertEqual(check['findings'][0]['id'],'missing-owner')
        self.inbox.unlink()
        check=self.check(self.observation('window',1),'window')
        self.assertTrue(check['errors']);self.assertEqual(check['status'],'partial')

    def test_json_changes_remains_parseable_even_when_unchanged(self):
        self.observation('main')
        value=self.observation('main',0,'--changes');self.assertFalse(value['has_changes'])

    def test_relocated_symlink_watch_loads_observation_module(self):
        moved=self.root/'relocated tomato';shutil.copytree(WATCH.parent.parent,moved,
            ignore=shutil.ignore_patterns('.state*'))
        self.assertFalse((moved/'bin/.state').exists())
        self.assertFalse((moved/'bin/.state.d').exists())
        link=self.root/'watch link';link.symlink_to(moved/'bin/watch')
        self.config['prs']=[self.pr()]
        r=self.run_watch('stuck','--json',executable=link)
        self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(json.loads(r.stdout)['has_changes'])

    def test_real_git_local_fetch_and_full_sha_transition(self):
        git=shutil.which('git');repo=self.root/'real checkout';remote=self.root/'local remote.git'
        env=dict(self.env,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',PATH=os.environ['PATH'])
        def run(*args): return subprocess.check_output([git,*args],env=env,text=True,stderr=subprocess.DEVNULL).strip()
        run('init','--bare','-q',str(remote));run('init','-q',str(repo))
        run('-C',str(repo),'checkout','-qb','main');run('-C',str(repo),'remote','add','origin',str(remote))
        def commit(text):
            (repo/'file.txt').write_text(text);run('-C',str(repo),'add','file.txt')
            run('-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','-qm','fixture','--no-gpg-sign')
            run('-C',str(repo),'push','-qu','origin','main');return run('-C',str(repo),'rev-parse','HEAD')
        sha1=commit('first\n');(self.bin/'git').unlink()
        self.env.update(TOMATO_WORK=str(repo),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
        first=self.check(self.observation('main'),'main');self.assertEqual(first['items'][0]['sha'],sha1)
        sha2=commit('second\n');second=self.check(self.observation('main'),'main')
        self.assertEqual(second['items'][0]['sha'],sha2);self.assertTrue(second['change']['changed'])
        self.assertEqual(second['change']['events'][0]['before']['items'][0]['sha'],sha1)

    def test_real_git_fixture_ignores_contaminated_parent_environment(self):
        polluted=dict(self.env,PATH=os.environ['PATH'],GIT_DIR=str(self.root/'outside.git'),GIT_WORK_TREE=str(self.root/'outside'),
            GIT_INDEX_FILE=str(self.root/'outside-index'),GIT_COMMON_DIR=str(self.root/'outside-common'),
            GIT_OBJECT_DIRECTORY=str(self.root/'outside-objects'),GIT_CONFIG_COUNT='1',
            GIT_CONFIG_KEY_0='core.bare',GIT_CONFIG_VALUE_0='true')
        result=subprocess.run([sys.executable,__file__,
            'TomatoObservationCase.test_real_git_local_fetch_and_full_sha_transition'],
            env=polluted,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.root/'outside.git').exists())
        self.assertFalse((self.root/'outside-index').exists())


if __name__=='__main__': unittest.main(verbosity=2)
