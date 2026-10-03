"""Banana's one-request lifecycle: checkout, isolated work, collection, safe release."""
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from role_contract import LAUNCH_ROLES, find_workspace, role_routing
from role_launch import launch_spec
from task_session import call, launch_task, save

ROOT = Path(__file__).resolve().parent.parent
EDIT_ROLES = ('banana', 'kiwi', 'melon')
loader = importlib.machinery.SourceFileLoader('banana_checkout_context', str(ROOT / 'roles/banana/skill/bin/context'))
context_spec = importlib.util.spec_from_loader(loader.name, loader)
checkout = importlib.util.module_from_spec(context_spec)
loader.exec_module(checkout)


def observe(path):
    result = checkout.observe(Path(path).expanduser().resolve())
    if result['status'] != 'complete':
        raise ValueError(result['error'])
    return result


def common_dir(source):
    root = Path(source['repositoryRoot'])
    return Path(checkout.git_read(shutil.which('git'), root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()


def request_plan(role, repo, prompt, access=None, base_ref=None, task_id=None, origin='owner',
                 model=None, effort=None, workspace=None, dry_run=False):
    if role not in LAUNCH_ROLES:
        raise ValueError('Peach の受入判定は既存の peach <ISSUE-ID> pipeline を使う')
    access = access or ('edit' if role in EDIT_ROLES else 'read')
    if access == 'edit' and role not in EDIT_ROLES:
        raise ValueError('この役の編集依頼を実装担当 Banana / Kiwi / Melon へ渡してください')
    if access not in ('edit', 'read') or not prompt or not prompt.strip():
        raise ValueError('access と空でない今回の依頼が必要')
    if base_ref and (access != 'edit' or workspace or base_ref.startswith('-')):
        raise ValueError('base-ref は新規の編集 worktree 用 ref を指定する')
    source = observe(repo)
    # Preserve the existing concafe separate-Codex route; this shared intake is
    # not an individual Owner request to start a Claude review there.
    if role == 'potato' and any(c['present'] and c['path'].endswith('concafe-orchestration/SKILL.md')
                                for c in source['contractSources']):
        raise ValueError('concafe のレビューは現行の別 Codex タスク経路を使う')
    root = Path(source['repositoryRoot'])
    common = common_dir(source)
    target = observe(workspace) if workspace else source
    if workspace and (Path(workspace).resolve() != Path(target['repositoryRoot']) or common_dir(target) != common):
        raise ValueError('再利用する worktree は同じ repo の checkout root を指定する')
    base_sha = checkout.git_read(shutil.which('git'), root, 'rev-parse', '--verify', base_ref + '^{commit}') if base_ref else None
    # Use the canonical launcher to validate persona/model/settings before a mutation.
    spec = launch_spec(role, Path(target['repositoryRoot']), prompt, model, effort, True, dry_run, access == 'read')
    identity = {'role': role, 'access': access, 'prompt': prompt, 'baseRef': base_ref,
                'originRole': origin, 'model': model, 'effort': spec['effort'],
                'existingWorkspace': str(Path(workspace).resolve()) if workspace else None}
    request_hash = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    task_id = task_id or request_hash[:20]
    if not task_id.strip() or len(task_id) > 160:
        raise ValueError('task-id は1〜160文字の依頼 ID を指定する')
    key = hashlib.sha256((str(common) + '\0' + task_id).encode()).hexdigest()
    state_root = Path(os.environ.get('NAMED_TEAM_PROJECT_TASK_DIR', str(Path.home() / '.local/share/named-team/projects')))
    slug = re.sub('[^a-z0-9-]+', '-', task_id.lower()).strip('-')[:24] or 'task'
    return {'schemaVersion': 1, 'taskId': task_id, 'key': key, 'requestHash': request_hash,
            'role': role, 'originRole': origin, 'coordinatorRole': 'banana' if role in EDIT_ROLES else origin,
            'access': access, 'source': source, 'commonDir': str(common), 'baseRef': base_ref,
            'requestedBaseSha': base_sha, 'worktreePlan': 'create' if access == 'edit' and not workspace else 'reuse',
            'roleRouting': role_routing(role), 'profile': spec['profile'], 'backend': spec['backend'],
            'targetPath': target['repositoryRoot'], 'ownsWorktree': False,
            'name': role + '-' + slug + '-' + key[:8], 'jobPath': str(state_root / key),
            'requestedModel': spec['requestedModel'], 'requestedEffort': spec['effort'],
            'startsSession': False}


def inventory(orca, repo_id=None):
    args = ('worktree', 'list', '--repo', 'id:' + repo_id) if repo_id else ('worktree', 'list')
    data = call(orca, *args)
    if data.get('truncated') or data.get('hostScope', {}).get('omittedHostIds'):
        raise RuntimeError('Orca の worktree 一覧が不完全。作成・起動を止める')
    return data['worktrees']


def registered_repo(orca, plan):
    matches = []
    listing = call(orca, 'repo', 'list')
    if listing.get('truncated') or listing.get('hostScope', {}).get('omittedHostIds'):
        raise RuntimeError('Orca repo 一覧が不完全')
    for repo in listing['repos']:
        if repo.get('kind') != 'git':
            continue
        try:
            if common_dir(observe(repo['path'])) == Path(plan['commonDir']):
                matches.append(repo)
        except (ValueError, OSError, RuntimeError):
            continue
    if len(matches) != 1:
        raise RuntimeError('対象 Git repo の Orca 登録を一意に確認できない。repo add / repo list を確認する')
    return matches[0]


def create_checkout(orca, record, job):
    repo = registered_repo(orca, record)
    record['repoId'] = repo['id']
    marker = 'named-task:' + record['key']
    record.update(stage='create-requested', createMarker=marker)
    save(job / 'record.json', record)
    argv = ['worktree', 'create', '--repo', 'id:' + repo['id'], '--name', record['name'],
            '--no-parent', '--setup', 'inherit', '--comment', marker]
    if record['requestedBaseSha']:
        argv += ['--base-branch', record['requestedBaseSha']]
    try:
        target = call(orca, *argv)['worktree']
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        # A timeout can create a checkout later. Recover the same marker only;
        # never issue a second create or launch on an unconfirmed receipt.
        deadline = time.monotonic() + float(os.environ.get('NAMED_TEAM_PROJECT_CREATE_WAIT_SECONDS') or 30)
        target = None
        while time.monotonic() < deadline:
            rows = [w for w in inventory(orca, repo['id']) if w.get('comment') == marker
                    and not w.get('isArchived') and w.get('hostId', 'local') == 'local']
            if len(rows) == 1:
                target = rows[0]
                break
            if len(rows) > 1:
                break
            time.sleep(0.25)
        if target is None:
            record.update(stage='creation-unconfirmed', failure='同じ worktree の作成を確認できない')
            save(job / 'record.json', record)
            raise RuntimeError('worktree の作成は未確認。再作成・再実行しない: ' + str(job)) from exc
    checkout_info = observe(target['path'])
    if (target['id'] != repo['id'] + '::' + str(Path(target['path']).absolute())
            or common_dir(checkout_info) != Path(record['commonDir'])
            or target.get('hostId', 'local') != 'local'):
        record['unverifiedWorktree'] = {'id': target.get('id'), 'path': target.get('path')}
        raise RuntimeError('作成した checkout の repo / 完全な ID / host が一致しない。保持して停止')
    if record['requestedBaseSha'] and checkout_info['headSha'] != record['requestedBaseSha']:
        record['unverifiedWorktree'] = {'id': target['id'], 'path': target['path']}
        raise RuntimeError('指定した base SHA と新規 checkout が一致しない。保持して停止')
    record.update(stage='created', ownsWorktree=True, worktreeId=target['id'], targetPath=checkout_info['repositoryRoot'],
                  baseSha=checkout_info['headSha'], initialTerminals=[])
    save(job / 'record.json', record)
    terminals = call(orca, 'terminal', 'list', '--worktree', 'id:' + target['id'])
    if terminals.get('truncated') or terminals.get('hostScope', {}).get('omittedHostIds'):
        raise RuntimeError('新規 worktree の terminal 一覧が不完全。追加起動を止める')
    # Native repo default tabs are intentional. Do not replace/stop their agents.
    if any(t.get('agentIdentity') for t in terminals['terminals']):
        raise RuntimeError('repo の既定タブに別 agent が存在する。二重起動せず worktree を保持')
    record['initialTerminals'] = [t['handle'] for t in terminals['terminals']]
    save(job / 'record.json', record)


def existing_checkout(orca, record):
    matches = [w for w in inventory(orca) if Path(w['path']).resolve() == Path(record['targetPath'])
               and not w.get('isArchived') and w.get('hostId', 'local') == 'local']
    if len(matches) != 1:
        raise RuntimeError('既存 checkout の Orca workspace を一意に確認できない')
    record.update(worktreeId=matches[0]['id'], baseSha=observe(record['targetPath'])['headSha'])


def task_prompt(record, prompt):
    target = Path(record['targetPath'])
    sources = [str(target / Path(item['path']).relative_to(record['source']['repositoryRoot']))
               for item in record['source']['contractSources'] if item['present']]
    return ('共通の進行・完了・回収は Banana の手順を参照する: ' + str(ROOT / 'roles/banana/skill/references/contracts.md')
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


def release_checkout(orca, record, job, merged_into=None):
    if not record.get('ownsWorktree'):
        return 'existing-workspace-retained'
    current = observe(record['targetPath'])
    if common_dir(current) != Path(record['commonDir']):
        raise RuntimeError('cleanup 対象の repo が一致しない')
    if current['dirty']:
        return 'changes-retained'
    git = shutil.which('git')
    root = Path(record['targetPath'])
    ignored = checkout.git_read(git, root, 'status', '--porcelain=v1', '--ignored=matching', '--untracked-files=normal')
    if ignored:
        return 'ignored-files-retained'
    destination = checkout.git_read(git, root, 'rev-parse', '--verify', merged_into + '^{commit}') if merged_into else record['baseSha']
    ancestry = checkout.git_process(git, root, 'merge-base', '--is-ancestor', current['headSha'], destination)
    if ancestry.returncode == 1:
        return 'unintegrated-commits-retained'
    if ancestry.returncode:
        raise RuntimeError('統合先への到達を確認できない')
    session = job / 'session'
    if not (session / 'finished.json').is_file() or not (session / 'closed.json').is_file():
        return 'execution-unconfirmed-retained'
    data = call(orca, 'terminal', 'list', '--worktree', 'id:' + record['worktreeId'])
    if data.get('truncated') or data.get('hostScope', {}).get('omittedHostIds'):
        return 'terminal-inventory-unconfirmed-retained'
    own_handle = json.loads((session / 'terminal.json').read_text())['handle']
    allowed = set(record.get('initialTerminals', [])) | {own_handle}
    if any(t['handle'] not in allowed or (t.get('agentIdentity') and t['handle'] != own_handle) for t in data['terminals']):
        return 'other-terminal-retained'
    # This workspace was created for this request. The role home is never closed.
    call(orca, 'terminal', 'close', '--worktree', 'id:' + record['worktreeId'], '--all')
    deadline = time.monotonic() + float(os.environ.get('NAMED_TEAM_PROJECT_CLOSE_WAIT_SECONDS') or 10)
    while True:
        rows = call(orca, 'terminal', 'list', '--worktree', 'id:' + record['worktreeId'])
        if not rows.get('truncated') and not rows.get('hostScope', {}).get('omittedHostIds') and not rows['terminals']:
            break
        if time.monotonic() >= deadline:
            return 'terminal-close-unconfirmed-retained'
        time.sleep(0.25)
    final = observe(root)
    if (final['dirty'] or final['headSha'] != current['headSha']
            or checkout.git_read(git, root, 'status', '--porcelain=v1', '--ignored=matching', '--untracked-files=normal')):
        return 'checkout-changed-retained'
    removed = call(orca, 'worktree', 'rm', '--worktree', 'id:' + record['worktreeId'])
    if removed.get('removed') is not True or root.exists() or any(w['id'] == record['worktreeId'] for w in inventory(orca)):
        return 'removal-unconfirmed'
    record['cleanupTargetSha'] = destination
    return 'removed'


def dispatch(orca, plan, prompt, model=None, effort=None, metadata=False):
    job = Path(plan['jobPath'])
    job.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (job / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('同じ依頼は受付・実行中。追加の worktree / model を起動しない')
        if (job / 'record.json').exists():
            old = json.loads((job / 'record.json').read_text())
            if old['requestHash'] != plan['requestHash']:
                raise ValueError('同じ依頼 ID の内容・担当・設定が異なる。既存の依頼を保持')
            print('既存の依頼を保持。再実行しません: ' + str(job), file=sys.stderr)
            if old.get('stage') == 'collected':
                result = job / 'session/result.txt'
                if result.is_file() and not metadata:
                    print(result.read_text(), end='')
                elif metadata and (job / 'session/metadata.json').is_file():
                    print((job / 'session/metadata.json').read_text())
                return old['returncode']
            return 4
        record = dict(plan, stage='accepted', startsSession=False)
        save(job / 'record.json', record)
        (job / 'request.md').write_text(prompt, encoding='utf-8')
        try:
            # Resolve homes before any worktree mutation; keep their cards intact.
            homes = inventory(orca)
            find_workspace(record['role'], {'worktrees': homes})
            if record['role'] in EDIT_ROLES:
                record['coordinatorWorktreeId'] = find_workspace('banana', {'worktrees': homes})['id']
            if record['worktreePlan'] == 'create':
                create_checkout(orca, record, job)
            else:
                existing_checkout(orca, record)
            spec = launch_spec(record['role'], Path(record['targetPath']), task_prompt(record, prompt), model,
                               effort, True, False, record['access'] == 'read')
            record.update(stage='execution-requested', startsSession=True)
            save(job / 'record.json', record)
            rc = launch_task(record['role'], spec['command'], Path(record['targetPath']), spec['environment'], orca,
                             metadata, 'id:' + record['worktreeId'], run_dir=job / 'session',
                             project_context={'taskId': record['taskId'], 'jobPath': str(job),
                                              'coordinatorRole': record['coordinatorRole']})
            record.update(returncode=rc, stage='collected' if (job / 'session/closed.json').is_file() else 'execution-unconfirmed')
            record['after'] = observe(record['targetPath'])
            record['cleanup'] = release_checkout(orca, record, job) if not rc and record['stage'] == 'collected' else 'failure-retained'
            record['handoff'] = {'resultPath': str(job / 'session/result.txt'), 'nextRole': record['coordinatorRole'],
                                 'worktreeId': record['worktreeId'], 'headSha': record['after']['headSha'],
                                 'dirty': record['after']['dirty'], 'cleanup': record['cleanup'],
                                 'externalState': 'not-verified', 'formalVerdict': 'not-issued'}
            if record['cleanup'] in ('removal-unconfirmed', 'terminal-close-unconfirmed-retained'):
                record['returncode'] = 4
            save(job / 'record.json', record)
            print('結果・引き渡し: ' + str(job / 'record.json') + ' / ' + record['cleanup'], file=sys.stderr)
            return 4 if record['cleanup'] in ('removal-unconfirmed', 'terminal-close-unconfirmed-retained') else rc
        except (RuntimeError, OSError, ValueError, KeyError) as exc:
            record.update(stage=record['stage'] if record['stage'] == 'creation-unconfirmed' else 'unconfirmed', failure=str(exc))
            save(job / 'record.json', record)
            print('作成・実行・回収は未確認。再実行せず保持: ' + str(job) + '\n' + str(exc), file=sys.stderr)
            return 4


def cleanup(orca, repo, task_id, merged_into):
    if not merged_into or merged_into.startswith('-'):
        raise ValueError('統合済み ref を指定する')
    source = observe(repo)
    key = hashlib.sha256((str(common_dir(source)) + '\0' + task_id).encode()).hexdigest()
    state_root = Path(os.environ.get('NAMED_TEAM_PROJECT_TASK_DIR', str(Path.home() / '.local/share/named-team/projects')))
    job = state_root / key
    with (job / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = json.loads((job / 'record.json').read_text())
        if record.get('cleanup') == 'removed':
            print('削除済み: ' + record['worktreeId'])
            return 0
        record['cleanup'] = release_checkout(orca, record, job, merged_into)
        save(job / 'record.json', record)
        print(record['cleanup'] + ': ' + record['worktreeId'])
        return 0 if record['cleanup'] == 'removed' else 4
