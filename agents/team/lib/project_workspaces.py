"""Orca checkout allocation and release; never owns a named role's home."""
import json
import os
from pathlib import Path
import shutil
import time

from checkout_context import common_dir, git_process, git_read, require_checkout as observe, resolve_ref
from task_session import call, save
from role_contract import role_label


def complete_listing(data):
    return not (data.get('truncated') or data.get('hostScope', {}).get('omittedHostIds'))


def inventory(orca, repo_id=None):
    args = ('worktree', 'list', '--repo', 'id:' + repo_id) if repo_id else ('worktree', 'list')
    data = call(orca, *args)
    if not complete_listing(data):
        raise RuntimeError('Orca の worktree 一覧が不完全。作成・起動を止める')
    return data['worktrees']


def registered_repo(orca, plan):
    matches = []
    listing = call(orca, 'repo', 'list')
    if not complete_listing(listing):
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


def checkout_parent(orca, record, repo):
    coordinator = record.get('coordinatorWorktreeId')
    if not coordinator:
        return None
    rows = [row for row in inventory(orca, repo['id'])
            if row['id'].startswith(repo['id'] + '::')
            and not row.get('isArchived') and row.get('hostId', 'local') == 'local']
    matches = [row for row in rows if row['id'] == coordinator]
    if not matches and record['role'] != 'review':
        # Banana may supervise a different project from its brain home.
        # Orca's lineage stays in that project's repository; the coordinator
        # remains recorded separately as the engineering window.
        source_path = str(Path(record['source']['repositoryRoot']).resolve())
        matches = [row for row in rows if str(Path(row['path']).resolve()) == source_path]
    if len(matches) != 1:
        raise RuntimeError('同じプロジェクトの親 workspace を一意に確認できない。作成を止める')
    return matches[0]['id']


def checkout_title(record):
    task = ''.join(ch for ch in record['taskId'] if ch.isprintable())[:100]
    purpose = role_label('review') if record['role'] == 'review' else (
        '開発（Devin）' if record.get('workerBackend') == 'devin' else '開発（Codex）')
    return task + '｜' + purpose


def create_checkout(orca, record, job):
    repo = registered_repo(orca, record)
    record['repoId'] = repo['id']
    parent = checkout_parent(orca, record, repo)
    record['lineageParentWorktreeId'] = parent
    marker = 'named-task:' + record['key']
    record.update(stage='create-requested', createMarker=marker)
    save(job / 'record.json', record)
    argv = ['worktree', 'create', '--repo', 'id:' + repo['id'], '--name', record['name'],
            '--setup', 'inherit', '--comment', marker]
    argv += ['--parent-worktree', 'id:' + parent] if parent else ['--no-parent']
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
    if record.get('requestedBranch') and checkout_info['branch'] != record['requestedBranch']:
        record['unverifiedWorktree'] = {'id': target['id'], 'path': target['path']}
        raise RuntimeError('案件 branch がプロジェクトの指定と一致しない。保持して停止')
    if parent and target.get('parentWorktreeId') != parent:
        record['unverifiedWorktree'] = {'id': target['id'], 'path': target['path']}
        raise RuntimeError('案件 checkout の親子関係を確認できない。保持して停止')
    record.update(stage='created', ownsWorktree=True, worktreeId=target['id'], targetPath=checkout_info['repositoryRoot'],
                  baseSha=checkout_info['headSha'], initialTerminals=[])
    save(job / 'record.json', record)
    title = checkout_title(record)
    updated = call(orca, 'worktree', 'set', '--worktree', 'id:' + target['id'],
                   '--display-name', title)['worktree']
    if updated.get('id') != target['id'] or updated.get('displayName') != title:
        raise RuntimeError('案件の表示名を確認できない。保持して停止')
    record['displayName'] = title
    save(job / 'record.json', record)
    terminals = call(orca, 'terminal', 'list', '--worktree', 'id:' + target['id'])
    if not complete_listing(terminals):
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
    ignored = git_read(git, root, 'status', '--porcelain=v1', '--ignored=matching', '--untracked-files=normal')
    if ignored:
        return 'ignored-files-retained'
    destination = resolve_ref(root, merged_into) if merged_into else record['baseSha']
    ancestry = git_process(git, root, 'merge-base', '--is-ancestor', current['headSha'], destination)
    if ancestry.returncode == 1:
        return 'unintegrated-commits-retained'
    if ancestry.returncode:
        raise RuntimeError('統合先への到達を確認できない')
    session = job / 'session'
    if not (session / 'finished.json').is_file() or not (session / 'closed.json').is_file():
        return 'execution-unconfirmed-retained'
    data = call(orca, 'terminal', 'list', '--worktree', 'id:' + record['worktreeId'])
    if not complete_listing(data):
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
        if complete_listing(rows) and not rows['terminals']:
            break
        if time.monotonic() >= deadline:
            return 'terminal-close-unconfirmed-retained'
        time.sleep(0.25)
    final = observe(root)
    if (final['dirty'] or final['headSha'] != current['headSha']
            or git_read(git, root, 'status', '--porcelain=v1', '--ignored=matching', '--untracked-files=normal')):
        return 'checkout-changed-retained'
    removed = call(orca, 'worktree', 'rm', '--worktree', 'id:' + record['worktreeId'])
    if removed.get('removed') is not True or root.exists() or any(w['id'] == record['worktreeId'] for w in inventory(orca)):
        return 'removal-unconfirmed'
    record['cleanupTargetSha'] = destination
    return 'removed'
