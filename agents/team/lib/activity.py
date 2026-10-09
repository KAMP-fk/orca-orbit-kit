"""Read-only activity projection. Never launch, reconcile, sync or approve work."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

from devin_flow import Blocked, UNCONFIRMED_STATES, adapter, config, load_record, same_session
from role_contract import ROLES, local_orca_only, orca_command

TITLE = 'Activity｜エージェント状況'
SCREEN_HEADING = 'Orca エージェント状況'
SCREEN_HEADINGS = (SCREEN_HEADING, 'Devin / Orca エージェント状況')


def text(value):
    # Terminal control sequences and multiline ticket content are not display data.
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(value))[:240]


def call(*args):
    local_orca_only()
    result = subprocess.run([orca_command(), *args, '--json'], capture_output=True,
                            text=True, timeout=15, check=True)
    payload = json.loads(result.stdout)
    if payload.get('ok') is not True:
        raise RuntimeError('Orca response unconfirmed')
    return payload['result']


def complete(snapshot):
    if snapshot.get('truncated') or 'local' in snapshot.get('hostScope', {}).get('omittedHostIds', []):
        raise RuntimeError('Incomplete local Orca inventory')


def native_rows(snapshot):
    complete(snapshot)
    rows = []
    for workspace in snapshot['worktrees']:
        if workspace.get('hostId', 'local') != 'local' or workspace.get('isArchived'):
            continue
        for agent in workspace.get('agents', []):
            rows.append({'workspace': text(workspace.get('displayName')),
                         'backend': text(agent.get('agentType')),
                         'state': text(agent.get('state')),
                         'updatedAt': agent.get('updatedAt') if isinstance(agent.get('updatedAt'), (int, float)) else None})
    return sorted(rows, key=lambda row: (row['workspace'] or '', row['backend'] or '',
                                         row['state'] or '', row['updatedAt'] or 0))


def records(root):
    for path in sorted(Path(root).glob('*/record.json')):
        try:
            # Only regular local records; do not follow an injected link out of the ledger.
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError('Linked record')
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError('Invalid record')
            yield path, value
        except (OSError, ValueError):
            yield path, None


def devin_rows(cfg, root, observe=False):
    rows = []
    for path, value in records(root):
        try:
            if value is None:
                raise ValueError('Unreadable record')
            if str(value.get('repo', '')).lower() != cfg['repo'].lower():
                continue
            from devin_flow import issue_id
            record = load_record(path, cfg, issue_id(value.get('issue', '')))
            row = {key: text(record.get(key)) for key in ('issue', 'state', 'session', 'branch', 'pr', 'headSha')}
            row['recordedAt'] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
            row['remoteState'] = '未取得'
            if observe and record['state'] not in (*UNCONFIRMED_STATES, 'done'):
                try:
                    worker = adapter(cfg, 'implementation', 'observe', record, timeout=8)
                    same_session(record, worker)
                    row['remoteState'] = text(worker.get('workerState')) or '未確認'
                    # Remote observation is distinct from the authoritative local gate state.
                    row['remotePr'] = text(worker.get('pr'))
                except Blocked:
                    row['remoteState'] = '取得失敗・未確認'
            rows.append(row)
        except (Blocked, OSError, ValueError, TypeError, KeyError):
            rows.append({'state': '記録不正・未確認'})
    return rows


def project_rows(root):
    rows = []
    for _, value in records(root):
        if value is None:
            rows.append({'state': '記録不正・未確認'})
            continue
        rows.append({key: text(value.get(key)) for key in ('taskId', 'role', 'stage', 'cleanup', 'worktreeId')})
    return rows


def snapshot(config_path, devin_root, project_root, observe=False, native=None):
    cfg = config(config_path, connected=False)
    connected = False
    try:
        config(config_path)
        connected = True
    except Blocked:
        pass
    result = {'repo': cfg['repo'], 'connection': '接続設定済み（疎通は各観測で確認）' if connected else '未接続・起動不可',
              'devin': devin_rows(cfg, devin_root, observe=observe and connected),
              'projects': project_rows(project_root)}
    try:
        result['agents'] = native_rows(native if native is not None else call('worktree', 'ps', '--limit', '1000'))
        result['orcaObservation'] = '取得済み'
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        result['agents'] = []
        result['orcaObservation'] = '取得失敗・未確認'
    return result


def render(value):
    lines = [SCREEN_HEADING,
             '構成: Tomato（相談 / ' + ROLES['tomato']['model'] + '） ⇄ Banana（開発 / Codex） → Potato（独立レビュー）',
             'Devin 保存済み台帳（利用停止）: ' + value['connection'],
             'Orca: ' + value['orcaObservation'],
             '開発: Banana / Codex | 品質: Potato（CI・QA・独立レビュー・修正依頼）']
    for row in value['devin']:
        lines.append('Devin 保存済み案件 | ' + ' | '.join(f'{k}={v}' for k, v in row.items() if v is not None))
    if not value['devin']:
        lines.append('Devin 保存済み案件: このrepoの実行記録なし（起動済みとは扱わない）')
    for row in value['projects']:
        lines.append('Task | ' + ' | '.join(f'{k}={v}' for k, v in row.items() if v is not None))
    active = [row for row in value['agents'] if row['state'] != 'done']
    ended = sorted((row for row in value['agents'] if row['state'] == 'done'),
                   key=lambda row: row['updatedAt'] or 0, reverse=True)
    lines.append(f'Orca agents: 活動・待機 {len(active)} / 終了記録 {len(ended)}（直近3件を表示）')
    for row in [*active, *ended[:3]]:
        timestamp = row['updatedAt']
        try:
            updated = datetime.fromtimestamp(timestamp / 1000).astimezone().isoformat(timespec='seconds') if timestamp else '未確認'
        except (ValueError, OverflowError, OSError):
            updated = '未確認'
        lines.append(f"Orca agent | {row['workspace']} | {row['backend']} | {row['state']} | 最終イベント={updated}")
    lines.append('表示は観測値。最終verdict・merge・Doneの判定は既存ゲートに従う。')
    return '\n'.join(lines)
