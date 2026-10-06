"""Exercise external-worker and quality-gate boundaries with offline command adapters."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import devin_flow as flow

FIXTURE = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
request=json.load(sys.stdin)
root=Path(sys.argv[1]); role=sys.argv[2]
with (root/'calls.jsonl').open('a') as out: out.write(json.dumps([role,request])+'\n')
cfg=json.loads((root/'responses.json').read_text())
op=request['operation']
response=dict(ok=True,repo=request['repo'],issue=request['issue'])
if op in cfg.get('failure',[]):
 print('private-authentication-value',file=sys.stderr);sys.exit(7)
if role=='worker':
 if op=='ticket': response.update(state='Todo',labels=['agent:devin'],acceptanceCriteria=['AC1'],activeExecution=None)
 elif op in ('start','lookup_start'): response.update(execution=request['execution'],session='session-'+request['issue'],branch='codex/'+request['issue'].lower()+'-fix',claimConfirmed=True,state='In Progress')
 elif op=='observe':
  sha=cfg.get('sha','a'*40)
  response.update(session=request['session'],branch=request['branch'],headSha=sha,
   pr=request['repo']+'#'+request['issue'].split('-')[1],workerState='working',
   validation=[dict(command='pnpm check',exitCode=0,headSha=sha)])
 elif op in ('revise','lookup_revision'): response.update(accepted=True,session=request['session'],branch=request['branch'],revision=request['revision'])
 elif op=='set_linear_state': response['state']=request['targetState']
 else: sys.exit(8)
else:
 assert op=='inspect'
 response.update(headSha=cfg.get('sha','a'*40),branch=request['branch'],pr=request['pr'],
  linkedIssue=request['issue'],prState='OPEN',decision='pending',evidenceRef='offline-evidence')
response.update(cfg.get(op,{}))
print(json.dumps(response))
'''


class DevinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='devin-flow-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / 'adapter with spaces'
        self.script.write_text(FIXTURE)
        self.script.chmod(0o755)
        self.cfg = dict(schemaVersion=1,repo='owner/repo',readyStates=['Todo'],workingState='In Progress',
                        reviewState='In Review',doneState='Done',requiredLabel='agent:devin',
                        requiredValidation=['pnpm check'],branchPattern=r'codex/caf-[0-9]+-.+',
                        implementationAdapter=[str(self.script),str(self.root),'worker'],
                        qualityAdapter=[str(self.script),str(self.root),'gate'])
        self.cfg_path = self.root / 'config.json'
        self.cfg_path.write_text(json.dumps(self.cfg))
        self.responses({})
        self.state = self.root / 'tasks'

    def responses(self, values):
        (self.root/'responses.json').write_text(json.dumps(values))

    def calls(self, operation=None):
        p=self.root/'calls.jsonl'
        values=[json.loads(v) for v in p.read_text().splitlines()] if p.exists() else []
        return [v for v in values if operation is None or v[1]['operation']==operation]

    def run_flow(self, action='start', issue='CAF-301'):
        return flow.run(flow.config(self.cfg_path),self.state,issue,action)

    def record(self, issue='CAF-301'):
        return json.loads((self.state/flow.key('owner/repo',issue)/'record.json').read_text())

    def approve(self, **fields):
        values=dict(decision='approved',reviewedSha='a'*40,independent=True,ciPassed=True,
                    acceptancePassed=True,validationPassed=True,evidenceRef='gate-proof')
        values.update(fields)
        self.responses({'inspect':values})

    def test_devin_starts_directly_with_issue_claim_and_validation_contract(self):
        result=self.run_flow()
        self.assertEqual(result['state'],'implementing')
        request=self.calls('start')[0][1]
        self.assertIn('Devin implements this issue directly',request['instructions'])
        self.assertEqual(request['requiredValidation'],['pnpm check'])
        self.assertFalse(self.calls('inspect'))

    def test_same_issue_case_and_repeated_start_never_launch_twice(self):
        first=self.run_flow(); second=self.run_flow(issue='caf-301')
        self.assertEqual(first,second)
        self.assertEqual(len(self.calls('start')),1)

    def test_different_issues_keep_distinct_sessions_branches_prs_and_records(self):
        results=[]
        for issue in ('CAF-301','CAF-302','CAF-303'):
            self.run_flow(issue=issue);results.append(self.run_flow('sync',issue))
        for key in ('session','branch','execution','pr'):
            self.assertEqual(len({r[key] for r in results}),3)

    def test_local_concurrent_claim_is_fenced_before_adapter_calls(self):
        with flow.fenced(self.state,'owner/repo','CAF-301'):
            result=subprocess.run([str(PACKAGE/'bin/devin'),'start','--issue','CAF-301',
                '--config',str(self.cfg_path),'--state-root',str(self.state)],capture_output=True,text=True)
        self.assertEqual(result.returncode,3)
        self.assertFalse(self.calls())

    def test_ineligible_state_label_ac_or_other_owner_cannot_start(self):
        for field,value in [('state','Done'),('labels',[]),('labels','agent:devin'),
                            ('acceptanceCriteria',[]),('acceptanceCriteria','  '),
                            ('acceptanceCriteria',[None]),('activeExecution','other'),('activeExecution',False)]:
            with self.subTest(field=field):
                self.responses({'ticket':{field:value}})
                with self.assertRaises(flow.Blocked):self.run_flow()
        self.assertFalse(self.calls('start'))

    def test_missing_ownership_observation_cannot_start(self):
        ticket = dict(state='Todo', labels=['agent:devin'], acceptanceCriteria=['AC1'])
        with mock.patch.object(flow, 'adapter', return_value=ticket) as adapter:
            with self.assertRaises(flow.Blocked):
                self.run_flow()
        self.assertEqual(adapter.call_count, 1)
        self.assertFalse(any(self.state.rglob('record.json')))

    def test_unconfirmed_start_is_durably_fenced_without_retry(self):
        self.responses({'failure':['start']})
        with self.assertRaises(flow.Blocked):self.run_flow()
        self.assertEqual(self.record()['state'],'start_unknown')
        self.responses({});self.run_flow()
        with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertEqual(len(self.calls('start')),1)

    def test_missing_claim_or_bad_branch_is_not_a_successful_start(self):
        for field,value in [('claimConfirmed',False),('branch','main'),('session',None),('state','Todo')]:
            with self.subTest(field=field):
                self.responses({'start':{field:value}})
                issue='CAF-'+str(400+len(self.calls('start')))
                with self.assertRaises(flow.Blocked):self.run_flow(issue=issue)
                self.assertEqual(self.record(issue)['state'],'start_unknown')

    def test_waiting_worker_does_not_enter_review_before_a_pr_exists(self):
        self.run_flow();self.responses({'observe':{'pr':None}})
        self.assertEqual(self.run_flow('sync')['state'],'implementing')
        self.assertFalse(self.calls('inspect'))
        self.assertFalse(self.calls('set_linear_state'))

    def test_pr_handoff_enters_review_only_after_current_sha_validation(self):
        self.run_flow();result=self.run_flow('sync')
        self.assertEqual(result['state'],'in_review')
        self.assertEqual(self.calls('set_linear_state')[-1][1]['targetState'],'In Review')
        self.assertEqual(self.calls('inspect')[0][0],'gate')

    def test_wrong_repo_issue_sha_or_branch_blocks_review(self):
        self.run_flow()
        for source,field,value in [('observe','pr','elsewhere/repo#301'),('inspect','linkedIssue','CAF-9'),
                                   ('inspect','headSha','b'*40),('observe','headSha',None),
                                   ('observe','branch','codex/caf-301-other')]:
            with self.subTest(field=field):
                self.responses({source:{field:value}})
                with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertFalse(self.calls('set_linear_state'))

    def test_no_validation_failed_validation_or_old_sha_cannot_enter_review(self):
        self.run_flow()
        for entries in ([],[dict(command='pnpm check',exitCode=1,headSha='a'*40)],
                         [dict(command='pnpm check',exitCode=0,headSha='b'*40)]):
            self.responses({'observe':{'validation':entries}})
            with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertFalse(self.calls('set_linear_state'))

    def test_changes_requested_go_to_same_session_once(self):
        original=self.run_flow();self.run_flow('sync')
        self.responses({'inspect':{'decision':'changes_requested','feedback':'Fix AC1'}})
        result=self.run_flow('sync');self.run_flow('sync')
        self.assertEqual(result['state'],'fixing')
        self.assertEqual(len(self.calls('revise')),1)
        request=self.calls('revise')[0][1]
        self.assertEqual((request['session'],request['branch']),(original['session'],original['branch']))
        self.assertEqual(len(self.calls('start')),1)

    def test_orca_can_return_failed_validation_to_original_session(self):
        self.run_flow()
        self.responses({'observe':{'validation':[]},'inspect':{'decision':'changes_requested','feedback':'Fix failing checks'}})
        self.assertEqual(self.run_flow('sync')['state'],'fixing')
        self.assertEqual(len(self.calls('revise')),1)
        self.assertFalse(self.calls('set_linear_state'))

    def test_unconfirmed_revision_cannot_redispatch(self):
        self.run_flow();self.responses({'inspect':{'decision':'changes_requested','feedback':'Fix'},'failure':['revise']})
        with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertEqual(self.record()['state'],'revision_unknown')
        with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertEqual(len(self.calls('revise')),1)

    def test_new_head_requires_new_independent_ci_ac_validation_evidence(self):
        self.run_flow();self.approve();self.assertEqual(self.run_flow('sync')['state'],'awaiting_merge')
        self.responses({'sha':'b'*40,'inspect':{'decision':'pending'}})
        record=self.run_flow('sync')
        self.assertEqual(record['state'],'in_review');self.assertNotIn('reviewedSha',record)
        self.assertNotIn('reviewEvidence',record)

    def test_review_withdrawal_or_failed_inspection_clears_prior_approval(self):
        self.run_flow()
        cases = [
            ({'inspect': {'decision': 'pending'}}, False, 'in_review'),
            ({'inspect': {'decision': 'changes_requested', 'feedback': 'Fix AC1'}}, False, 'fixing'),
            ({'inspect': {'decision': 'approved', 'ciPassed': False}}, True, 'in_review'),
            ({'inspect': {'headSha': 'b' * 40}}, True, 'in_review'),
            ({'failure': ['inspect']}, True, 'in_review'),
        ]
        for response, blocked, state in cases:
            with self.subTest(response=response):
                self.approve()
                self.assertEqual(self.run_flow('sync')['state'], 'awaiting_merge')
                self.responses(response)
                if blocked:
                    with self.assertRaises(flow.Blocked):
                        self.run_flow('sync')
                else:
                    self.run_flow('sync')
                record = self.record()
                self.assertEqual(record['state'], state)
                self.assertNotIn('reviewedSha', record)
                self.assertNotIn('reviewEvidence', record)
        self.assertEqual(len(self.calls('start')), 1)

    def test_repeated_correction_restores_fixing_state_without_resending(self):
        self.run_flow()
        feedback = {'inspect': {'decision': 'changes_requested', 'feedback': 'Fix AC1'}}
        self.responses(feedback)
        self.assertEqual(self.run_flow('sync')['state'], 'fixing')
        self.responses({})
        self.assertEqual(self.run_flow('sync')['state'], 'in_review')
        self.responses(feedback)
        self.assertEqual(self.run_flow('sync')['state'], 'fixing')
        self.assertEqual(len(self.calls('revise')), 1)

    def test_approval_requires_each_quality_gate_condition(self):
        self.run_flow()
        for field,value in [('independent',False),('reviewedSha','b'*40),('ciPassed',False),
                            ('acceptancePassed',False),('validationPassed',False),('evidenceRef',None)]:
            with self.subTest(field=field):
                self.approve(**{field:value})
                with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertFalse(self.calls('set_linear_state'))

    def test_merge_requires_postmerge_ac_evidence_before_done(self):
        self.run_flow()
        self.responses({'inspect':{'prState':'MERGED','doneReady':False,'mergeCommit':'c'*40}})
        with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertFalse(self.calls('set_linear_state'))
        self.responses({'inspect':{'prState':'MERGED','doneReady':True,'mergeCommit':'c'*40}})
        self.assertEqual(self.run_flow('sync')['state'],'done')
        self.assertEqual(self.calls('set_linear_state')[-1][1]['targetState'],'Done')
        writes=len(self.calls('set_linear_state'));self.run_flow('sync')
        self.assertEqual(len(self.calls('set_linear_state')),writes)
        self.assertFalse(any(v[1]['operation'] in ('merge','approve','post_status') for v in self.calls()))

    def test_failed_done_write_preserves_merged_record_and_reads_back_before_retry(self):
        self.run_flow();self.responses({'inspect':{'prState':'MERGED','doneReady':True,'mergeCommit':'c'*40},'failure':['set_linear_state']})
        with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.assertEqual(self.record()['state'],'merged')
        self.responses({'inspect':{'prState':'MERGED','doneReady':True,'mergeCommit':'c'*40}})
        self.assertEqual(self.run_flow('sync')['state'],'done')

    def test_reconcile_start_reads_original_execution_without_new_start(self):
        self.responses({'failure':['start']})
        with self.assertRaises(flow.Blocked):self.run_flow()
        execution=self.record()['execution']
        self.responses({})
        result=self.run_flow('reconcile')
        self.assertEqual(result['execution'],execution)
        self.assertEqual(result['state'],'implementing')
        self.assertEqual(len(self.calls('start')),1)
        self.assertEqual(len(self.calls('lookup_start')),1)
        self.assertEqual((self.state/flow.key('owner/repo','CAF-301')/'record.json').stat().st_mode & 0o777,0o600)

    def test_reconcile_revision_only_reads_original_receipt(self):
        self.run_flow()
        self.responses({'inspect':{'decision':'changes_requested','feedback':'Fix'},'failure':['revise']})
        with self.assertRaises(flow.Blocked):self.run_flow('sync')
        self.responses({})
        self.assertEqual(self.run_flow('reconcile')['state'],'fixing')
        self.assertEqual(len(self.calls('revise')),1)
        self.assertEqual(len(self.calls('lookup_revision')),1)

    def test_unmatched_reconciliation_keeps_unknown_fence(self):
        self.responses({'failure':['start']})
        with self.assertRaises(flow.Blocked):self.run_flow()
        self.responses({'lookup_start':{'execution':'other'}})
        with self.assertRaises(flow.Blocked):self.run_flow('reconcile')
        self.assertEqual(self.record()['state'],'start_unknown')
        self.assertEqual(len(self.calls('start')),1)

    def test_missing_adapter_and_default_config_cannot_create_state(self):
        with self.assertRaises(flow.Blocked):flow.config(PACKAGE/'config/devin.json')
        self.cfg['implementationAdapter']=[];self.cfg_path.write_text(json.dumps(self.cfg))
        with self.assertRaises(flow.Blocked):self.run_flow()
        self.assertFalse(self.state.exists());self.assertFalse(self.calls())

    def test_invalid_configuration_cannot_call_adapter_or_create_state(self):
        values = [[], None, dict(self.cfg, repo=None), dict(self.cfg, doneState=[]),
                  dict(self.cfg, readyStates=[None]), dict(self.cfg, requiredValidation=[' ']),
                  dict(self.cfg, branchPattern='('), dict(self.cfg, branchPattern=''),
                  dict(self.cfg, qualityAdapter=self.cfg['implementationAdapter'])]
        for value in values:
            with self.subTest(value=value):
                self.cfg_path.write_text(json.dumps(value))
                with self.assertRaises(flow.Blocked):
                    self.run_flow()
        self.assertFalse(self.state.exists())
        self.assertFalse(self.calls())

    def test_overlapping_linear_mapping_cannot_restart_done_or_active_issues(self):
        values = [dict(self.cfg, readyStates=[state]) for state in ('Done', 'In Progress', 'In Review')]
        values += [dict(self.cfg, workingState='Done'), dict(self.cfg, reviewState='In Progress')]
        self.responses({'ticket': {'state': 'Done'}})
        for value in values:
            with self.subTest(value=value):
                self.cfg_path.write_text(json.dumps(value))
                with self.assertRaises(flow.Blocked):
                    self.run_flow()
        self.assertFalse(self.state.exists())
        self.assertFalse(self.calls())

    def test_every_action_rejects_foreign_or_malformed_records_without_adapter_calls(self):
        original = self.run_flow()
        path = self.state / flow.key('owner/repo', 'CAF-301') / 'record.json'
        records = [[], dict(original, repo='other/repo'), dict(original, issue='CAF-9'),
                   dict(original, schemaVersion=2), dict(original, state='made-up'),
                   dict(original, execution=None)]
        calls = len(self.calls())
        for record in records:
            path.write_text(json.dumps(record))
            for action in ('start', 'sync', 'reconcile', 'status'):
                with self.subTest(record=record, action=action), self.assertRaises(flow.Blocked):
                    self.run_flow(action)
            self.assertEqual(json.loads(path.read_text()), record)
        self.assertEqual(len(self.calls()), calls)

    def test_repository_case_change_reuses_the_original_execution(self):
        original = self.run_flow()
        self.cfg['repo'] = 'Owner/Repo'
        self.cfg_path.write_text(json.dumps(self.cfg))
        self.assertEqual(self.run_flow(), original)
        self.assertEqual(self.run_flow('sync')['execution'], original['execution'])
        self.assertEqual(len(self.calls('start')), 1)

    def test_missing_assigned_session_or_branch_is_blocked_before_observation(self):
        original = self.run_flow()
        path = self.state / flow.key('owner/repo', 'CAF-301') / 'record.json'
        calls = len(self.calls())
        self.responses({'observe': {'pr': None}})
        for field in ('session', 'branch'):
            for value in (None, ' '):
                record = dict(original, **{field: value})
                path.write_text(json.dumps(record))
                for action in ('start', 'sync', 'reconcile', 'status'):
                    with self.subTest(field=field, value=value, action=action), self.assertRaises(flow.Blocked):
                        self.run_flow(action)
                self.assertEqual(json.loads(path.read_text()), record)
        self.assertEqual(len(self.calls()), calls)

    def test_unknown_action_is_rejected_without_creating_state(self):
        with self.assertRaises(flow.Blocked):
            self.run_flow('typo')
        self.assertFalse(self.state.exists())
        self.assertFalse(self.calls())

    def test_status_needs_no_adapter_and_does_not_create_missing_state(self):
        disconnected=dict(self.cfg,implementationAdapter=[],qualityAdapter=[])
        self.cfg_path.write_text(json.dumps(disconnected))
        cfg=flow.config(self.cfg_path,connected=False)
        with self.assertRaises(flow.Blocked):flow.run(cfg,self.state,'CAF-301','status')
        self.assertFalse(self.state.exists())
        self.cfg_path.write_text(json.dumps(self.cfg));self.run_flow()
        self.cfg_path.write_text(json.dumps(disconnected))
        cfg=flow.config(self.cfg_path,connected=False)
        self.assertEqual(flow.run(cfg,self.state,'CAF-301','status')['state'],'implementing')
        self.assertEqual(len(self.calls()),2)

    def test_untrusted_identifier_never_reaches_adapter_or_filesystem(self):
        for issue in ('../../private','CAF-301;touch file','CAF-0','CAF-301\n'):
            with self.assertRaises(flow.Blocked):self.run_flow(issue=issue)
        self.assertFalse(self.calls());self.assertFalse(self.state.exists())

    def test_adapter_failure_does_not_expose_credential_output(self):
        self.responses({'failure':['start']})
        result=subprocess.run([str(PACKAGE/'bin/devin'),'start','--issue','CAF-301',
            '--config',str(self.cfg_path),'--state-root',str(self.state)],capture_output=True,text=True)
        self.assertEqual(result.returncode,3)
        self.assertNotIn('private-authentication-value',result.stdout+result.stderr)

    def test_timeout_during_start_keeps_fence(self):
        original=flow.subprocess.run
        def execute(argv, **kwargs):
            if json.loads(kwargs['input'])['operation']=='start':
                raise subprocess.TimeoutExpired(argv,55)
            return original(argv,**kwargs)
        with mock.patch.object(flow.subprocess,'run',side_effect=execute),self.assertRaises(flow.Blocked):self.run_flow()
        self.assertEqual(self.record()['state'],'start_unknown')


if __name__=='__main__':unittest.main()
