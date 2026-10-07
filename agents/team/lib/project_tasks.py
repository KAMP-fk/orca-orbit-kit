"""Shared infrastructure request plan, execution coordination, and durable result handoff."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from checkout_context import common_dir, require_checkout as observe, resolve_ref
import project_workspaces as workspaces
from role_contract import ROLES, LAUNCH_ROLES, find_workspace, role_routing, home_role
from worker_launch import execution_spec
from task_session import launch_task, save

ROOT = Path(__file__).resolve().parent.parent
EDIT_ROLES = tuple(name for name, role in ROLES.items() if role.get('access') == 'edit')


def job_key(common, task_id):
    return hashlib.sha256((str(common) + '\0' + task_id).encode()).hexdigest()


def job_path(key):
    root = Path(os.environ.get('NAMED_TEAM_PROJECT_TASK_DIR', str(Path.home() / '.local/share/named-team/projects')))
    return root / key


def is_development(record):
    """Only unmarked legacy Devin records infer development from the engine."""
    return record.get('development', record.get('workerBackend') == 'devin')


@contextmanager
def locked_job(job):
    with (job / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('同じ依頼は受付・実行中。追加の worktree / model を起動しない') from None
        yield


def request_plan(role, repo, prompt, access=None, base_ref=None, task_id=None, origin='owner',
                 model=None, effort=None, workspace=None, dry_run=False, worker_backend='codex', expected_sha=None,
                 development=False):
    if role not in LAUNCH_ROLES:
        raise ValueError('受入判定は review --kind acceptance を使う')
    access = access or ('edit' if role in EDIT_ROLES else 'read')
    if access == 'edit' and role not in EDIT_ROLES:
        raise ValueError('編集依頼は開発窓口 Banana へ渡してください')
    if access not in ('edit', 'read') or not prompt or not prompt.strip():
        raise ValueError('access と空でない今回の依頼が必要')
    if development and (role != 'banana' or access != 'edit'):
        raise ValueError('開発依頼は Banana の編集案件を指定する')
    if development and workspace:
        raise ValueError('開発は専用 checkout を作る。既存 checkout は追加実行しない')
    if base_ref and (access != 'edit' or workspace or base_ref.startswith('-')):
        raise ValueError('base-ref は新規の編集 worktree 用 ref を指定する')
    source = observe(repo)
    # Preserve the existing concafe separate-Codex route; this shared intake is
    # not an individual Owner request to start a Claude review there.
    if role == 'review' and any(c['present'] and c['path'].endswith('concafe-orchestration/SKILL.md')
                                for c in source['contractSources']):
        raise ValueError('concafe のレビューは現行の別 Codex タスク経路を使う')
    root = Path(source['repositoryRoot'])
    common = common_dir(source)
    target = observe(workspace) if workspace else source
    if expected_sha and (access != 'read' or target['dirty'] or expected_sha != target['headSha']):
        raise ValueError('固定した読み取り対象の full HEAD SHA / clean checkout が一致しない')
    if workspace and (Path(workspace).resolve() != Path(target['repositoryRoot']) or common_dir(target) != common):
        raise ValueError('再利用する worktree は同じ repo の checkout root を指定する')
    base_sha = resolve_ref(root, base_ref) if base_ref else None
    # Use the canonical launcher to validate persona/model/settings before a mutation.
    spec = execution_spec(role, Path(target['repositoryRoot']), prompt, model=model, effort=effort,
                          dry_run=dry_run, read_only=access == 'read', worker_backend=worker_backend)
    effective_backend = spec['backend']
    identity = {'role': role, 'access': access, 'prompt': prompt, 'baseRef': base_ref,
                'originRole': origin, 'model': model, 'effort': spec['effort'],
                'existingWorkspace': str(Path(workspace).resolve()) if workspace else None,
                'workerBackend': effective_backend, 'expectedSha': expected_sha}
    if development:
        # Preserve ordinary maintenance/read request hashes and replay behavior.
        identity['development'] = True
    if effective_backend == 'claude':
        # Prior Codex results cannot satisfy a newly pinned Claude request.
        identity['model'] = spec['requestedModel']
    request_hash = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    task_id = task_id or request_hash[:20]
    if not task_id.strip() or len(task_id) > 160:
        raise ValueError('task-id は1〜160文字の依頼 ID を指定する')
    key = job_key(common, task_id)
    slug = re.sub('[^a-z0-9-]+', '-', task_id.lower()).strip('-')[:24] or 'task'
    name = role + '-' + slug + '-' + key[:8]
    requested_branch = None
    if development:
        from project_identity import is_concafe_path
        if is_concafe_path(root):
            issue = re.fullmatch(r'caf-([1-9][0-9]*)(?:-.+)?', task_id, re.I)
            if not issue:
                raise ValueError('concafe の開発は task-id に CAF-<番号> の案件 ID を指定する')
            requested_branch = name = 'codex/caf-' + issue[1] + '-' + key[:8]
    return {'schemaVersion': 1, 'taskId': task_id, 'key': key, 'requestHash': request_hash,
            'role': role, 'originRole': origin, 'coordinatorRole': home_role(role) if role in EDIT_ROLES else origin,
            'access': access, 'source': source, 'commonDir': str(common), 'baseRef': base_ref,
            'requestedBaseSha': base_sha, 'worktreePlan': 'create' if access == 'edit' and not workspace else 'reuse',
            'roleRouting': role_routing(role), 'profile': spec['profile'], 'backend': spec['backend'],
            'targetPath': target['repositoryRoot'], 'ownsWorktree': False,
            'name': name, 'requestedBranch': requested_branch, 'jobPath': str(job_path(key)),
            'requestedModel': spec['requestedModel'], 'requestedEffort': spec['effort'],
            'workerBackend': effective_backend, 'development': development,
            'expectedSha': expected_sha,
            'startsSession': False}


def task_prompt(record, prompt):
    target = Path(record['targetPath'])
    sources = [str(target / Path(item['path']).relative_to(record['source']['repositoryRoot']))
               for item in record['source']['contractSources'] if item['present']]
    return ('共通の進行・完了・回収契約: ' + str(ROOT / 'references/contracts.md')
            + '\n役割・相談・正式なレビューの契約: ' + str(ROOT / 'references/roles.md')
            + '\n案件の共通手順: ' + str(ROOT / 'references/project-tasks.md')
            + '\n対象 checkout: ' + str(target) + '\n開始 full SHA: ' + record['baseSha']
            + '\n依頼 ID: ' + record['taskId'] + '\n依頼元: ' + record['originRole']
            + '\n通常の回収担当: ' + record['coordinatorRole']
            + '\n対象の現行契約を着手前に読み、現在のユーザー委任・編集範囲・受入条件・完了条件を確認する: '
            + ', '.join(sources)
            + '\n依頼元 checkout の契約も比較し、直接指示の更新や違いを失わない: '
            + ', '.join(item['path'] for item in record['source']['contractSources'] if item['present'])
            + '\n読み取り依頼は編集しない。元 checkout の未コミット変更はコピーしていない。'
            + '\nbrain・人格・鍵・権限設定には書かない。最終報告に成果の full SHA、変更、検査、残件を付ける。'
            + '\nこの packet は追加の承認ではない。別担当の正式なレビュー・判断と人間ゲートを維持する。'
            + '\n\n今回の依頼:\n' + prompt)


def _replay_result(job, record, request_hash, metadata):
    if record['requestHash'] != request_hash:
        raise ValueError('同じ依頼 ID の内容・担当・設定が異なる。既存の依頼を保持')
    print('既存の依頼を保持。再実行しません: ' + str(job), file=sys.stderr)
    if record.get('stage') != 'collected':
        return 4
    result = job / 'session/result.txt'
    if result.is_file() and not metadata:
        print(result.read_text(), end='')
    elif metadata and (job / 'session/metadata.json').is_file():
        print((job / 'session/metadata.json').read_text())
    return record['returncode']


def _execute(orca, record, job, prompt, model, effort, metadata):
    # Resolve the shared entry before any worktree mutation, not a specialist's
    # retired home. The task itself runs in its assigned checkout.
    homes = workspaces.inventory(orca)
    home = find_workspace(home_role(record['role']), {'worktrees': homes})
    if record['role'] in EDIT_ROLES:
        record['coordinatorWorktreeId'] = home['id']
    if record['worktreePlan'] == 'create':
        workspaces.create_checkout(orca, record, job)
    else:
        workspaces.existing_checkout(orca, record)
    if is_development(record) and not record.get('requestedBranch'):
        record['requestedBranch'] = observe(record['targetPath'])['branch']
    if record.get('expectedSha') and (observe(record['targetPath'])['dirty'] or record['baseSha'] != record['expectedSha']):
        raise ValueError('実行直前にレビューの固定版が変化している')
    spec = execution_spec(record['role'], Path(record['targetPath']), task_prompt(record, prompt),
                          model=model, effort=effort, read_only=record['access'] == 'read',
                          worker_backend=record.get('workerBackend', 'codex'))
    record.update(stage='execution-requested', startsSession=True)
    save(job / 'record.json', record)
    return launch_task(record['role'], spec['command'], Path(record['targetPath']), spec['environment'],
                       orca, metadata=metadata, workspace='id:' + record['worktreeId'],
                       run_dir=job / 'session', collector=spec['collector'], project_context={
                           'taskId': record['taskId'], 'jobPath': str(job),
                           'coordinatorRole': record['coordinatorRole']})


def _collect(orca, record, job, returncode):
    record.update(returncode=returncode,
                  stage='collected' if (job / 'session/closed.json').is_file() else 'execution-unconfirmed')
    record['after'] = observe(record['targetPath'])
    if record.get('requestedBranch') and record['after']['branch'] != record['requestedBranch']:
        raise ValueError('開発の成果 branch が案件の固定 branch と一致しない。保持して停止')
    development = is_development(record)
    record['cleanup'] = ('review-pending-retained' if development and not returncode and record['stage'] == 'collected'
                         else workspaces.release_checkout(orca, record, job)
                         if not returncode and record['stage'] == 'collected' else 'failure-retained')
    record['handoff'] = {'resultPath': str(job / 'session/result.txt'), 'nextRole': record['coordinatorRole'],
                         'worktreeId': record['worktreeId'], 'headSha': record['after']['headSha'],
                         'dirty': record['after']['dirty'], 'cleanup': record['cleanup'],
                         'externalState': 'not-verified', 'formalVerdict': 'not-issued'}
    if development and not returncode and record['stage'] == 'collected':
        from engineering_handoff import prepare_review
        if record['after']['dirty'] or record['after']['headSha'] == record['baseSha']:
            record['handoff'].update(nextRole='banana', status='pending-coordinator-commit')
        else:
            record['handoff'].update(prepare_review(orca, record, job))
    if record['cleanup'] in ('removal-unconfirmed', 'terminal-close-unconfirmed-retained'):
        record['returncode'] = 4
    save(job / 'record.json', record)
    print('結果・引き渡し: ' + str(job / 'record.json') + ' / ' + record['cleanup'], file=sys.stderr)
    return record['returncode']


def dispatch(orca, plan, prompt, model=None, effort=None, metadata=False):
    job = Path(plan['jobPath'])
    job.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked_job(job):
        if (job / 'record.json').exists():
            record = json.loads((job / 'record.json').read_text())
            return _replay_result(job, record, plan['requestHash'], metadata)
        record = dict(plan, stage='accepted', startsSession=False)
        save(job / 'record.json', record)
        (job / 'request.md').write_text(prompt, encoding='utf-8')
        try:
            returncode = _execute(orca, record, job, prompt, model, effort, metadata)
            return _collect(orca, record, job, returncode)
        except (RuntimeError, OSError, ValueError, KeyError) as exc:
            record.update(stage=record['stage'] if record['stage'] == 'creation-unconfirmed' else 'unconfirmed', failure=str(exc))
            save(job / 'record.json', record)
            print('作成・実行・回収は未確認。再実行せず保持: ' + str(job) + '\n' + str(exc), file=sys.stderr)
            return 4


def cleanup(orca, repo, task_id, merged_into):
    if not merged_into or merged_into.startswith('-'):
        raise ValueError('統合済み ref を指定する')
    source = observe(repo)
    job = job_path(job_key(common_dir(source), task_id))
    with locked_job(job):
        record = json.loads((job / 'record.json').read_text())
        if record.get('cleanup') == 'removed':
            print('削除済み: ' + record['worktreeId'])
            return 0
        record['cleanup'] = workspaces.release_checkout(orca, record, job, merged_into)
        save(job / 'record.json', record)
        print(record['cleanup'] + ': ' + record['worktreeId'])
        return 0 if record['cleanup'] == 'removed' else 4
