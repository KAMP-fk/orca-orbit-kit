"""Idempotent metadata setup for known homes, preserving all existing sessions."""
from pathlib import Path
from datetime import datetime, timezone
import re
import shlex
import sys
import time

from activity import TITLE, call, complete
from role_contract import ROOT, ROLES, workspace_root


def specs():
    home = Path.home()
    return [
        (ROOT.parent.parent, 'Orca｜エージェント基盤',
         'Banana担当の共有基盤。ソースはagents/team、役別定義はroles。エージェント状況タブで稼働・Devin receipt・品質待ちを観測。', True),
        (workspace_root('tomato'), ROLES['tomato']['workspace'],
         'Fable / medium で広い相談・意図・判断材料を整理。開発領域はBananaと依頼・質問・報告で連携。調査・実装はCodex。', True),
        (workspace_root('banana'), ROLES['banana']['workspace'],
         '独立した開発窓口。Ownerの直接依頼とTomatoからの依頼を受領。技術判断・開発案件・Potatoへの引渡しを担当。Tomatoには意図や受入範囲を相談する。', True),
        (workspace_root('review'), 'Potato｜レビュー受付',
         'Opus 5.5 / high 固定の独立レビュー窓口。実レビューは案件ごとの別ワークツリーで実行。指摘はBananaへ返し、正式判定は対象プロジェクトの独立タスクへ引き渡す。別モデルへ切り替えない。', False),
        (home / '.agents/skills', 'Skills｜スキル管理',
         'スキル管理。相談はTomato、開発窓口はBanana、実装はCodex、品質ゲートはPotato。', False),
    ]


def parent_paths():
    board = ROOT.parent.parent
    return {
        str(workspace_root('tomato')): None,
        str(workspace_root('banana')): None,
        str(workspace_root('review')): None,
        # Orca requires lineage parents in the same repository/host/project.
        # These source repositories have Banana supervision, not brain lineage.
        str(board): None,
    }


def plan(snapshot):
    complete(snapshot)
    result = []
    for path, title, comment, required in specs():
        matches = [w for w in snapshot['worktrees'] if w.get('path') == str(path)
                   and w.get('hostId', 'local') == 'local' and not w.get('isArchived')]
        if len(matches) > 1:
            raise RuntimeError('Ambiguous display home; no changes made')
        if not matches:
            if required:
                raise RuntimeError('Missing display home; no changes made: ' + str(path))
            continue
        row = matches[0]
        result.append({'id': row['id'], 'path': str(path), 'title': title, 'comment': comment,
                       'parentId': row.get('parentWorktreeId'),
                       'parentChanged': False,
                       'changed': row.get('displayName') != title or row.get('comment') != comment})
    by_path = {row['path']: row for row in result}
    for path, parent in parent_paths().items():
        if path not in by_path:
            continue
        if parent is not None and parent not in by_path:
            raise RuntimeError('Missing parent home; no changes made: ' + parent)
        row = by_path[path]
        parent_id = by_path[parent]['id'] if parent is not None else None
        row['parentChanged'] = row['parentId'] != parent_id
        row['parentId'] = parent_id
        row['changed'] |= row['parentChanged']
    return result


def prepare():
    targets = plan(call('worktree', 'list', '--limit', '1000'))
    board = targets[0]
    tabs = call('terminal', 'list', '--worktree', 'id:' + board['id'], '--limit', '1000')
    complete(tabs)
    matches = [tab for tab in tabs['terminals'] if tab.get('title') == TITLE and tab.get('connected')]
    if len(matches) > 1:
        raise RuntimeError('Ambiguous activity tabs; no changes made')
    if matches and not healthy(matches[0]['handle']):
        raise RuntimeError('Activity tab exists but observation is stale; inspect instead of duplicating it')
    return targets, matches[0] if matches else None


def healthy(handle):
    receipt = call('terminal', 'read', '--terminal', handle, '--limit', '500')['terminal']
    lines = [re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line).strip()
             for line in receipt.get('tail', []) if isinstance(line, str)]
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        match = re.fullmatch(r'\[([^\]]+)\] 観測', line)
        if match:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(match[1])).total_seconds()
                return 0 <= age < 120 and 'Devin / Orca エージェント状況' in lines[index + 1:]
            except (ValueError, TypeError):
                return False
    return False


def confirm(handle):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if healthy(handle):
            return
        time.sleep(0.2)
    raise RuntimeError('Activity observation startup unconfirmed; inspect before retry')


def apply(targets, existing):
    by_id = {row['id']: row for row in targets}

    def depth(row):
        seen = {row['id']}
        count = 0
        parent = row['parentId']
        while parent in by_id:
            if parent in seen:
                raise RuntimeError('Display hierarchy cycle; no changes made')
            seen.add(parent)
            count += 1
            parent = by_id[parent]['parentId']
        return count

    # Parents are assigned first so an earlier reversed hierarchy cannot
    # create a temporary cycle. This changes Orca metadata, not Git branches.
    for target in sorted(targets, key=depth):
        if target['changed']:
            args = ['worktree', 'set', '--worktree', 'id:' + target['id'],
                    '--display-name', target['title'], '--comment', target['comment']]
            if target['parentChanged']:
                args += ['--parent-worktree', 'id:' + target['parentId']] if target['parentId'] else ['--no-parent']
            call(*args)
    if existing:
        return existing['handle']
    # Explicit model-free command. Root is not a dialogue auto-start home.
    command = 'exec ' + shlex.join([sys.executable, '-B', str(ROOT / 'bin/activity'), '--observe-devin', '--screen'])
    result = call('terminal', 'create', '--worktree', 'id:' + targets[0]['id'],
                  '--title', TITLE, '--command', command)['terminal']
    if not isinstance(result.get('handle'), str):
        raise RuntimeError('Activity terminal creation unconfirmed; inspect before retry')
    return result['handle']


def verify(targets, snapshot):
    complete(snapshot)
    rows = {row['id']: row for row in snapshot['worktrees']}
    for target in targets:
        row = rows.get(target['id'], {})
        if (row.get('path') != target['path'] or row.get('displayName') != target['title']
                or row.get('comment') != target['comment']
                or row.get('parentWorktreeId') != target['parentId']):
            raise RuntimeError('Workspace display or hierarchy unconfirmed; inspect before retry')
