"""Offline evidence tests. Never uses the real Orca, GitHub, issues, agents or store."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents/team/lib'))
from delivery_flow import publish_pool, start_review, record_review

class DeliveryFlowTest(unittest.TestCase):
    def test_collect_current_independent_report_without_external_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'pr':'https://github.com/KAMP-fk/concafe-techo/pull/1', 'head_sha':'a'*40,
                      'reviewed_at':datetime.now(timezone.utc).isoformat(), 'verdict':'BLOCKED',
                      'code_review_verdict':'NO_REMAINING_FINDINGS',
                      'reviewer':{'independent':True,'effective_model':'gpt-6-astra','effective_effort':'high',
                                  'session_id':'review-session','implementer_session_id':'implementation-session',
                                  'task_id':'task_fixture','dispatch_id':'ctx_fixture'}}
            path = root / 'report.json'
            path.write_text(json.dumps(report))
            calls = []
            def invoke(argv):
                calls.append(argv)
                if argv[0] == 'gh':return {'headRefOid':'a'*40,'state':'OPEN'}
                return {'projection':{'provider':{'model':'gpt-6-astra'}},
                        'dispatch':{'taskId':'task_fixture'},'terminal':{'incarnationId':'session'}}
            receipt = record_review(path, root, invoke)
            self.assertEqual(receipt['head'], report['head_sha'])
            self.assertEqual(receipt['reportVerdict'], 'BLOCKED')
            self.assertEqual(len(receipt['reportDigest']), 64)
            self.assertEqual([a[:3] for a in calls], [['gh','pr','view'],['orca','orchestration','worker-show']])
            with self.assertRaisesRegex(ValueError, 'current open PR head'):
                record_review(path, root, lambda a:{'headRefOid':'b'*40,'state':'OPEN'})
            report['reviewer']['session_id'] = 'implementation-session'
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'independent'):
                record_review(path, root, invoke)
            self.assertEqual(len(calls), 2)

    def test_scoped_pool_and_actual_acceptance(self):
        issue = {'acceptance':['usable outcome'], 'allowedScope':['implement/test/PR'], 'excludedScope':['production'],
                 'sharedPaths':['apps/web/src/one.ts'], 'ownerExecutionGates':['production'], 'evidence':['fixture'],
                 'implementationApproved':True,'priority':2,'acceptanceDigest':hashlib.sha256(b'AC').hexdigest()}
        value={'decision':'APPROVED_WITH_CONDITIONS','decidedAt':datetime.now(timezone.utc).isoformat(),'authority':'Owner + decision',
               'issues':[{**issue,'identifier':f'CAF-{i}'} for i in range(1,4)]}
        result=publish_pool(value,lambda argv:{'issue':{'description':'AC'},'meta':{}})
        self.assertEqual(len(result['issues']),3)
        self.assertEqual(result['issues'][0]['acceptanceDigest'],hashlib.sha256(b'AC').hexdigest())
        self.assertEqual(result['issues'][0]['ownerExecutionGates'],['production'])
        with self.assertRaisesRegex(ValueError, 'acceptance changed'):publish_pool(value,lambda argv:{'issue':{'description':'new AC'},'meta':{}})
        with self.assertRaises(ValueError): publish_pool({**value,'decision':'BLOCKED'})
        self.assertEqual(publish_pool({**value,'issues':value['issues'][:2]},lambda argv:{'issue':{'description':'AC'},'meta':{}})['readyPool']['shortfall'],1)

    def test_start_proof_idempotency_and_ambiguous_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            args=argparse.Namespace(pr=1,sha='a'*40,task='task_fixture',terminal='term_aaaaaaaa-aaaa',worktree=directory,
                                    sender='term_sender',run='run_fixture',action_id=str(uuid.uuid4()))
            commands=[]
            def invoke(argv):
                commands.append(argv)
                if argv[0]=='gh':return {'headRefOid':args.sha,'state':'OPEN'}
                if argv[1:3]==['terminal','show']:return {'terminal':{'worktreePath':directory,'agentIdentity':'codex'}}
                if argv[1:3]==['terminal','read']:return {'terminal':{'tail':['GPT-6-Astra high · '+directory]}}
                if argv[1:3]==['terminal','wait']:return {'wait':{'satisfied':True}}
                if argv[1:3]==['orchestration','worker-start']:return {'dispatchId':'ctx_fixture','prompt':{'requestId':'prompt','stages':['input_accepted','turn_started'],'processIncarnation':'session'}}
                if argv[1:3]==['orchestration','worker-show']:return {'projection':{'provider':{'model':'gpt-6-astra'}},'terminal':{'incarnationId':'session'}}
                self.fail(argv)
            with patch('checkout_context.require_checkout',return_value={'headSha':args.sha,'dirty':False}), patch('project_identity.github_repository',return_value='KAMP-fk/concafe-techo'):
                receipt=start_review(args,root,invoke)
                count=len(commands)
                self.assertEqual(start_review(args,root,invoke),receipt)
                self.assertEqual(len(commands),count)
                self.assertEqual(receipt['promptStages'],['input_accepted','turn_started'])
                self.assertEqual(receipt['effectiveEffort'],'high')
                self.assertEqual(json.loads((root/'review-receipts.json').read_text())['items'][0],receipt)
                args.action_id=str(uuid.uuid4())
                def uncertain(argv):
                    if argv[1:3]==['orchestration','worker-start']:raise ValueError('fixture transport uncertain')
                    return invoke(argv)
                with self.assertRaises(ValueError):start_review(args,root,uncertain)
                before=len(commands)
                with self.assertRaisesRegex(ValueError,'outcome unknown'):start_review(args,root,invoke)
                self.assertEqual(len(commands),before)
                self.assertFalse(any('--dangerously-bypass-approvals-and-sandbox' in a for a in commands))

    def test_wrong_head_or_effective_model_never_submits(self):
        with tempfile.TemporaryDirectory() as directory:
            args=argparse.Namespace(pr=1,sha='a'*40,task='task_fixture',terminal='term_aaaaaaaa',worktree=directory,
                                    sender='term_sender',run='run_fixture',action_id=str(uuid.uuid4()))
            with patch('checkout_context.require_checkout',return_value={'headSha':'b'*40,'dirty':False}),patch('project_identity.github_repository',return_value='KAMP-fk/concafe-techo'):
                calls=[]
                with self.assertRaises(ValueError):start_review(args,Path(directory),lambda a:calls.append(a))
                self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
