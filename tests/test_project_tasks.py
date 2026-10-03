"""Banana project intake against real isolated Git checkouts and fake backends."""
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest
from unittest import mock

import test_named_task_sessions

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
sys.path.insert(0, str(PACKAGE / 'lib'))
import project_tasks
import project_workspaces
import role_contract


class ProjectTaskTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_named_task_sessions.TaskSessionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.fixture.root
        self.repo = self.base / 'repo with spaces'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        (self.repo / 'AGENTS.md').write_text('Fixture source contract.\n')
        (self.repo / 'base.txt').write_text('original\n')
        (self.repo / '.gitignore').write_text('ignored.cache\n')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture base')
        self.env = dict(self.fixture.env, NAMED_TEAM_PROJECT_TASK_DIR=str(self.base / 'projects'),
                        NAMED_TEAM_PROJECT_CREATE_WAIT_SECONDS='0.1', NAMED_TEAM_PROJECT_CLOSE_WAIT_SECONDS='0.1')
        self.calls = []
        self.worktrees = []
        self.terminals = {}
        self.latest = None
        self.workers = []
        self.timeout_create = False
        self.missing_create = False
        self.default_agent = False
        self.extra_terminal = False
        self.fail_bulk_close = False
        self.context = mock.patch.dict(os.environ, self.env, clear=True)
        self.context.start()
        self.addCleanup(self.context.stop)
        self.native = mock.patch.object(project_workspaces, 'call', side_effect=self.call)
        self.native.start()
        self.addCleanup(self.native.stop)
        self.launch_calls = mock.patch('task_session.call', side_effect=self.call)
        self.launch_calls.start()
        self.addCleanup(self.launch_calls.stop)
        # Fixtures are real executables; no model/provider is invoked.
        model = test_named_task_sessions.MODEL_FIXTURE.replace("else:\n print('fixture Codex is working'", """else:
 behavior=os.environ.get('FIXTURE_PROJECT_BEHAVIOR','none')
 if behavior in ('dirty','commit'):
  Path('change.txt').write_text('new work\\n')
 if behavior=='commit':
  import subprocess
  subprocess.run(['git','add','change.txt'],check=True)
  subprocess.run(['git','commit','-m','fixture change'],check=True,stdout=subprocess.DEVNULL)
 if behavior=='ignored': Path('ignored.cache').write_text('owned artifact')
 print('fixture Codex is working'""")
        (self.fixture.fixture.bin / 'codex').write_text(model)

    def git(self, *args, cwd=None):
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        result = subprocess.run(['git', '-C', str(cwd or self.repo), *args], env=env,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def call(self, orca, *args):
        self.calls.append(args)
        if args[:2] == ('repo', 'list'):
            return {'repos': [{'id': 'fixture-repo', 'path': str(self.repo), 'kind': 'git'}]}
        if args[:2] == ('worktree', 'list'):
            homes = [{'id': role + '::' + str(role_contract.workspace_root(role)),
                      'path': str(role_contract.workspace_root(role)), 'displayName': info['workspace']}
                     for role, info in role_contract.ROLES.items()]
            source = {'id': 'fixture-repo::' + str(self.repo), 'path': str(self.repo)}
            return {'worktrees': [*homes, source, *self.worktrees], 'truncated': False}
        if args[:2] == ('worktree', 'create'):
            if self.missing_create:
                raise RuntimeError('fixture create timeout before confirmation')
            name = args[args.index('--name') + 1]
            root = self.base / name
            base = args[args.index('--base-branch') + 1] if '--base-branch' in args else 'main'
            self.git('worktree', 'add', '-b', name, str(root), base)
            target = {'id': 'fixture-repo::' + str(root), 'path': str(root), 'displayName': name,
                      'comment': args[args.index('--comment') + 1], 'hostId': 'local'}
            self.worktrees.append(target)
            self.terminals[target['id']] = [{'handle': 'term_initial', 'agentIdentity': 'claude'}] if self.default_agent else [{'handle': 'term_initial'}]
            if self.timeout_create:
                raise RuntimeError('fixture create response timeout')
            return {'worktree': target}
        if args[:2] == ('worktree', 'show'):
            selected = args[args.index('--worktree') + 1][3:]
            return {'worktree': {'id': selected}}
        if args[:2] == ('terminal', 'list'):
            selected = args[args.index('--worktree') + 1][3:]
            return {'terminals': self.terminals.get(selected, []), 'truncated': False}
        if args[:2] == ('terminal', 'create'):
            run = Path(shlex.split(args[args.index('--command') + 1])[-1])
            self.latest = run
            selected = args[args.index('--worktree') + 1][3:]
            self.terminals.setdefault(selected, []).append({'handle': 'term_worker'})
            with (run / 'visible.txt').open('w') as output:
                worker_env = os.environ.copy()
                worker_env['ORCA_TERMINAL_HANDLE'] = 'term_worker'
                child = subprocess.Popen(['/bin/sh', '-c', args[args.index('--command') + 1]],
                                         env=worker_env, stdout=output, stderr=subprocess.STDOUT)
            self.workers.append(child)
            self.addCleanup(lambda process=child: process.wait(timeout=5))
            return {'terminal': {'handle': 'term_worker', 'tabId': 'fixture-job-tab'}}
        if args[:2] == ('terminal', 'read'):
            return {'terminal': {'status': 'running'}}
        if args[:2] == ('terminal', 'close'):
            if '--all' in args:
                if self.fail_bulk_close:
                    raise RuntimeError('fixture close unavailable')
                selected = args[args.index('--worktree') + 1][3:]
                self.terminals[selected] = []
            else:
                self.assertIn('--tab', args)
                self.assertTrue((self.latest / 'finished.json').is_file())
                for selected in self.terminals:
                    self.terminals[selected] = [t for t in self.terminals[selected] if t['handle'] != 'term_worker']
                    if self.extra_terminal:
                        self.terminals[selected].append({'handle': 'term_other_person'})
            return {}
        if args[:2] == ('worktree', 'rm'):
            selected = args[args.index('--worktree') + 1][3:]
            target = next(w for w in self.worktrees if w['id'] == selected)
            self.git('worktree', 'remove', target['path'])
            self.worktrees.remove(target)
            return {'removed': True}
        raise AssertionError('Unexpected call: ' + repr(args))

    def plan(self, **kwargs):
        return project_tasks.request_plan('kiwi', self.repo, 'Fixture implementation request', task_id='fixture-task', **kwargs)

    def run_job(self, plan=None):
        plan = plan or self.plan()
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            rc = project_tasks.dispatch('/fixture/orca', plan, 'Fixture implementation request')
        self.output = output.getvalue()
        return rc, json.loads((Path(plan['jobPath']) / 'record.json').read_text())

    def model_calls(self):
        path = Path(str(self.fixture.fixture.log) + '.calls')
        return len(path.read_text().splitlines()) if path.exists() else 0

    def test_edit_creates_one_checkout_collects_report_and_removes_only_clean_owned_work(self):
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['stage'], 'collected')
        self.assertEqual(record['cleanup'], 'removed')
        self.assertEqual(record['handoff']['nextRole'], 'banana')
        self.assertEqual(record['handoff']['formalVerdict'], 'not-issued')
        self.assertIn('fixture implementation result', self.output)
        self.assertEqual(self.model_calls(), 1)
        self.assertTrue(self.repo.is_dir())
        self.assertFalse(Path(record['targetPath']).exists())
        self.assertEqual(sum(c[:2] == ('worktree', 'create') for c in self.calls), 1)
        self.assertFalse(any('--force' in c or '--agent' in c for c in self.calls))
        request = json.loads((Path(record['jobPath']) / 'session/request.json').read_text())
        self.assertEqual(request['projectTask']['coordinatorRole'], 'banana')
        self.assertEqual(request['cwd'], record['targetPath'])

    def test_repeat_same_id_returns_saved_result_without_another_model_or_checkout(self):
        plan = self.plan()
        self.assertEqual(self.run_job(plan)[0], 0)
        calls = len(self.calls)
        rc, _ = self.run_job(plan)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(self.model_calls(), 1)
        self.assertIn('fixture implementation result', self.output)
        changed = dict(plan, requestHash='different')
        with self.assertRaisesRegex(ValueError, '内容・担当・設定が異なる'):
            self.run_job(changed)

    def test_source_dirty_changes_are_preserved_and_new_code_is_handed_back(self):
        (self.repo / 'base.txt').write_text('another person\n')
        os.environ['FIXTURE_PROJECT_BEHAVIOR'] = 'dirty'
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'changes-retained')
        self.assertTrue(record['source']['dirty'])
        self.assertEqual((self.repo / 'base.txt').read_text(), 'another person\n')
        self.assertEqual((Path(record['targetPath']) / 'base.txt').read_text(), 'original\n')
        self.assertTrue((Path(record['targetPath']) / 'change.txt').is_file())

    def test_unintegrated_commit_is_retained_then_explicit_integrated_cleanup_runs_no_model(self):
        os.environ['FIXTURE_PROJECT_BEHAVIOR'] = 'commit'
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'unintegrated-commits-retained')
        self.git('merge', '--ff-only', record['after']['headSha'])
        with contextlib.redirect_stdout(io.StringIO()):
            result = project_tasks.cleanup('/fixture/orca', self.repo, 'fixture-task', 'main')
        self.assertEqual(result, 0)
        self.assertEqual(self.model_calls(), 1)
        self.assertFalse(Path(record['targetPath']).exists())
        self.assertTrue((self.repo / 'change.txt').is_file())

    def test_read_job_reuses_checkout_with_read_only_sandbox_and_never_removes_it(self):
        plan = self.plan(access='read')
        rc, record = self.run_job(plan)
        self.assertEqual(rc, 0)
        self.assertFalse(record['ownsWorktree'])
        self.assertEqual(record['cleanup'], 'existing-workspace-retained')
        self.assertFalse(any(c[:2] == ('worktree', 'create') for c in self.calls))
        request = json.loads((Path(record['jobPath']) / 'session/request.json').read_text())
        self.assertIn('sandbox_mode="read-only"', request['command'])
        self.assertEqual(request['cwd'], str(self.repo))

    def test_explicit_existing_edit_workspace_is_retained(self):
        os.environ['FIXTURE_PROJECT_BEHAVIOR'] = 'dirty'
        rc, record = self.run_job(self.plan(workspace=self.repo))
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'existing-workspace-retained')
        self.assertTrue((self.repo / 'change.txt').exists())

    def test_read_jobs_in_one_checkout_have_distinct_recovery_titles(self):
        first = project_tasks.request_plan('kiwi', self.repo, 'Fixture implementation request',
                                           access='read', task_id='read-first')
        second = project_tasks.request_plan('kiwi', self.repo, 'Fixture implementation request',
                                            access='read', task_id='read-second')
        self.assertEqual(self.run_job(first)[0], 0)
        self.assertEqual(self.run_job(second)[0], 0)
        launches = [c for c in self.calls if c[:2] == ('terminal', 'create')]
        self.assertEqual(len(launches), 2)
        self.assertEqual(launches[0][launches[0].index('--worktree') + 1],
                         launches[1][launches[1].index('--worktree') + 1])
        self.assertNotEqual(launches[0][launches[0].index('--title') + 1],
                            launches[1][launches[1].index('--title') + 1])
        self.assertEqual(self.model_calls(), 2)
        self.assertTrue(self.repo.is_dir())

    def test_ambiguous_create_response_recovers_same_marker_without_duplicate_create(self):
        self.timeout_create = True
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'removed')
        self.assertEqual(sum(c[:2] == ('worktree', 'create') for c in self.calls), 1)
        self.assertEqual(self.model_calls(), 1)

    def test_unconfirmed_creation_is_not_retried_and_starts_no_model(self):
        self.missing_create = True
        plan = self.plan()
        rc, record = self.run_job(plan)
        self.assertEqual(rc, 4)
        self.assertEqual(record['stage'], 'creation-unconfirmed')
        self.assertEqual(self.run_job(plan)[0], 4)
        self.assertEqual(sum(c[:2] == ('worktree', 'create') for c in self.calls), 1)
        self.assertEqual(self.model_calls(), 0)

    def test_concurrent_intake_claim_stops_before_any_orca_mutation(self):
        plan = self.plan()
        job = Path(plan['jobPath'])
        job.mkdir(parents=True)
        with (job / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, '受付・実行中'):
                self.run_job(plan)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.model_calls(), 0)

    def test_incomplete_native_inventory_blocks_allocation_and_model(self):
        for command in (('worktree', 'list'), ('repo', 'list')):
            with self.subTest(command=command):
                def incomplete(orca, *args):
                    result = self.call(orca, *args)
                    if args[:2] == command:
                        result['truncated'] = True
                    return result

                plan = project_tasks.request_plan('kiwi', self.repo, 'Fixture implementation request',
                                                  task_id='incomplete-' + command[0])
                with mock.patch.object(project_workspaces, 'call', side_effect=incomplete):
                    rc, record = self.run_job(plan)
                self.assertEqual(rc, 4)
                self.assertEqual(record['stage'], 'unconfirmed')
                self.assertEqual(self.model_calls(), 0)
                self.assertFalse(any(c[:2] == ('worktree', 'create') for c in self.calls))

    def test_incomplete_terminal_inventory_after_collection_retains_checkout(self):
        def incomplete_after_work(orca, *args):
            result = self.call(orca, *args)
            if (args[:2] == ('terminal', 'list') and self.latest is not None
                    and (self.latest / 'finished.json').is_file()):
                result['hostScope'] = {'omittedHostIds': ['fixture-missing-host']}
            return result

        with mock.patch.object(project_workspaces, 'call', side_effect=incomplete_after_work):
            rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'terminal-inventory-unconfirmed-retained')
        self.assertTrue(Path(record['targetPath']).is_dir())
        self.assertEqual(self.model_calls(), 1)
        self.assertFalse(any(c[:2] == ('worktree', 'rm') for c in self.calls))

    def test_repo_default_base_is_used_instead_of_current_feature_branch(self):
        initial = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-b', 'unrelated-feature')
        (self.repo / 'unrelated.txt').write_text('other work')
        self.git('add', 'unrelated.txt')
        self.git('commit', '-m', 'other work')
        _, record = self.run_job()
        self.assertNotEqual(record['source']['headSha'], initial)
        self.assertEqual(record['baseSha'], initial)
        create = next(c for c in self.calls if c[:2] == ('worktree', 'create'))
        self.assertIn('--no-parent', create)
        self.assertIn('inherit', create)
        self.assertNotIn('--base-branch', create)

    def test_explicit_base_is_fixed_to_full_sha(self):
        plan = self.plan(base_ref='main')
        _, record = self.run_job(plan)
        create = next(c for c in self.calls if c[:2] == ('worktree', 'create'))
        self.assertEqual(create[create.index('--base-branch') + 1], self.git('rev-parse', 'main'))
        self.assertEqual(record['baseSha'], plan['requestedBaseSha'])

    def test_other_agent_default_tab_blocks_additional_model_launch_and_is_preserved(self):
        self.default_agent = True
        rc, record = self.run_job()
        self.assertEqual(rc, 4)
        self.assertTrue(Path(record['targetPath']).exists())
        self.assertFalse(any(c[:2] == ('terminal', 'close') for c in self.calls))
        self.assertEqual(self.model_calls(), 0)

    def test_new_unowned_terminal_prevents_cleanup(self):
        self.extra_terminal = True
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'other-terminal-retained')
        self.assertTrue(Path(record['targetPath']).exists())
        self.assertFalse(any(c[:2] == ('worktree', 'rm') for c in self.calls))

    def test_ignored_artifact_prevents_cleanup_even_if_git_status_is_clean(self):
        os.environ['FIXTURE_PROJECT_BEHAVIOR'] = 'ignored'
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertFalse(record['after']['dirty'])
        self.assertEqual(record['cleanup'], 'ignored-files-retained')
        self.assertTrue((Path(record['targetPath']) / 'ignored.cache').exists())

    def test_cleanup_failure_is_not_cached_as_success(self):
        self.fail_bulk_close = True
        plan = self.plan()
        rc, record = self.run_job(plan)
        self.assertEqual(rc, 4)
        self.assertEqual(record['stage'], 'unconfirmed')
        self.assertTrue(Path(record['targetPath']).exists())
        self.assertEqual(self.run_job(plan)[0], 4)
        self.assertEqual(self.model_calls(), 1)

    def test_read_role_edit_and_concafe_claude_route_are_rejected_before_mutation(self):
        with self.assertRaisesRegex(ValueError, '編集依頼'):
            project_tasks.request_plan('tomato', self.repo, 'request', access='edit')
        marker = self.repo / '.agents/skills/concafe-orchestration/SKILL.md'
        marker.parent.mkdir(parents=True)
        marker.write_text('Fixture concafe contract.')
        with self.assertRaisesRegex(ValueError, '別 Codex タスク'):
            project_tasks.request_plan('potato', self.repo, 'request')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.model_calls(), 0)

    def test_inherited_git_redirection_is_cleared_for_context_and_worker(self):
        os.environ['GIT_DIR'] = '/must-not-use-this-git-dir'
        os.environ['GIT_WORK_TREE'] = '/must-not-use-this-work-tree'
        os.environ['FIXTURE_PROJECT_BEHAVIOR'] = 'commit'
        rc, record = self.run_job()
        self.assertEqual(rc, 0)
        self.assertEqual(record['cleanup'], 'unintegrated-commits-retained')

    def test_common_banana_entry_preview_keeps_literal_request_and_mutates_nothing(self):
        marker = self.base / 'must-not-be-created'
        prompt = self.base / 'request with spaces.md'
        prompt.write_text('literal $(touch ' + str(marker) + ') `touch ' + str(marker) + '`\n')
        env = os.environ.copy()
        result = subprocess.run([str(PACKAGE / 'roles/banana/skill/bin/task'), '--role', 'kiwi',
                                 '--repo', str(self.repo), '--task-id', 'preview', '--prompt-file', str(prompt),
                                 '--dry-run'], env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['worktreePlan'], 'create')
        self.assertFalse(json.loads(result.stdout)['startsSession'])
        self.assertFalse(marker.exists())
        self.assertFalse((self.base / 'projects').exists())
        self.assertEqual(self.model_calls(), 0)


if __name__ == '__main__':
    unittest.main()
