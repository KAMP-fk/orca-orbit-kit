"""Opt-in continuation of the existing Banana, using the model-free Orca clock.

This controller observes and wakes; Banana owns admission, implementation, collection
and review routing. A durable delivery fence survives crashes and uncertain sends.
It never creates agents, changes permissions, writes GitHub/Linear or edits job ledgers.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

from event_monitor import CONFIG, Client, collect_linear, collect_ci, pages, digest, utcnow
from role_contract import find_workspace, local_orca_only, ROOT

STATE_ROOT = Path.home() / '.local/share/named-team/continuation/concafe-techo'


def validate(config):
    if config.get('repo') != 'KAMP-fk/concafe-techo' or config.get('key') != 'concafe-techo':
        raise ValueError('Only the delegated concafe project is enabled')


def write(root, value):
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / 'control.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)


def state_directory(root):
    root = Path(root).absolute()
    for parent in (root, *root.parents):
        system_alias = parent in (Path('/var'), Path('/tmp')) and parent.resolve() == Path('/private') / parent.name
        if parent.is_symlink() and not system_alias:
            raise ValueError('Continuation state path is a symlink')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('control.json', 'control.lock', 'pause-requested'):
        if (root / name).is_symlink():
            raise ValueError('Continuation state file is a symlink')
    return root


@contextmanager
def control(root):
    root = state_directory(root)
    with (root / 'control.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = root / 'control.json'
        value = json.loads(path.read_text()) if path.exists() else {
            'schemaVersion': 1, 'repo': 'KAMP-fk/concafe-techo', 'enabled': False, 'wip': 2}
        if (value.get('schemaVersion') != 1 or value.get('repo') != 'KAMP-fk/concafe-techo'
                or value.get('wip') != 2 or not isinstance(value.get('enabled'), bool)):
            raise ValueError('Invalid continuation scope')
        yield root, value


def existing_agent(client):
    snapshot = client.call('worktree', 'ps', '--limit', '1000')
    home = find_workspace('banana', snapshot)
    agents = [a for a in home.get('agents', []) if not a.get('parentPaneKey')]
    if len(agents) != 1 or agents[0].get('agentType') not in ('codex', 'claude'):
        raise ValueError('Banana agent is missing or ambiguous; no agent created')
    agent = agents[0]
    if agent.get('interrupted'):
        return snapshot, home, agent, None, 'interrupted'
    # Background CI/review waits keep the workspace projection "working".
    # The main turn can nevertheless be done: native tui-idle below is still
    # required before input, so monitoring doesn't prevent independent progress.
    monitoring_idle = (agent.get('workingMode') == 'monitoring'
                       and (agent.get('mainAgent') or {}).get('state') == 'done')
    if agent.get('state') not in ('done', 'idle') and not monitoring_idle:
        return snapshot, home, agent, None, 'busy'
    listing = client.call('terminal', 'list', '--worktree', 'id:' + home['worktreeId'])
    if listing.get('truncated') or listing.get('hostScope', {}).get('omittedHostIds'):
        raise ValueError('Incomplete terminal inventory')
    terminals = [t for t in listing['terminals']
                 if t.get('tabId', '') + ':' + t.get('leafId', '') == agent.get('paneKey')
                 and t.get('worktreeId') == home['worktreeId']
                 and t.get('agentIdentity') == agent['agentType']
                 and t.get('connected') and t.get('writable') and not t.get('orphaned')
                 and t.get('executionHostId') == 'local' and t.get('incarnationId')]
    if len(terminals) != 1:
        raise ValueError('Exact Banana terminal is unconfirmed')
    return snapshot, home, agent, terminals[0], 'idle'


def observe(client, config, native):
    issues = [row for row in collect_linear(client, config)
              if row['stateType'] in ('unstarted', 'started') and not row.get('archivedAt')]
    if any(not re.fullmatch(r'CAF-[1-9][0-9]*', row['key']) for row in issues):
        raise ValueError('Invalid scoped issue identifier')
    pulls = pages(client, 'repos/' + config['repo'] + '/pulls?state=open')
    prs = []
    for pull in pulls:
        ci = collect_ci(client, config, pull)
        prs.append({'number': pull['number'], 'head': ci['head'], 'draft': pull['draft'],
                    'labels': sorted(label['name'] for label in pull['labels']),
                    'checks': sorted((check['name'], (check['conclusion'] or 'unknown') if check['status'] == 'completed'
                                      else 'pending') for check in ci['checks']),
                    'statuses': sorted((status['name'], status['state']) for status in ci['statuses'])})
    checkout = str(Path(config['checkout']).expanduser())
    repo_ids = {w['repoId'] for w in native['worktrees'] if w.get('path') == checkout}
    if len(repo_ids) != 1:
        raise ValueError('Exact project repo is unconfirmed')
    workspaces = [{'id': w['worktreeId'], 'issue': w.get('linkedLinearIssue'),
                   'branch': w.get('branch'),
                   'agents': sorted((a.get('agentType', ''), a.get('state', 'unknown')) for a in w.get('agents', []))}
                  for w in native['worktrees'] if w.get('repoId') in repo_ids and not w.get('isArchived')]
    # Collected dirty results and review handoffs can require progress without a
    # Linear/CI change. Read existing records, never mutate their authority.
    jobs = []
    ledger = Path.home() / '.local/share/named-team/projects'
    for path in sorted(ledger.glob('*/record.json')):
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Linked project ledger')
        row = json.loads(path.read_text())
        if row.get('source', {}).get('repositoryRoot') != checkout:
            continue
        handoff = row.get('handoff') or {}
        jobs.append({'task': row.get('taskId'), 'stage': row.get('stage'), 'returncode': row.get('returncode'),
                     'cleanup': row.get('cleanup'), 'handoff': handoff.get('status'),
                     'head': handoff.get('headSha')})
    facts = {'issues': sorted(issues, key=lambda r: r['key']), 'prs': sorted(prs, key=lambda r: r['number']),
             'jobs': jobs, 'workspaces': sorted(workspaces, key=lambda r: r['id'])}
    # Read only a fixed bounded pool. This is a wake signal, not start permission.
    approved = {}
    pool_path = Path.home() / '.local/share/orbit-console/start-pool.json'
    try:
        from delivery_flow import read
        pool = read(pool_path)
        from datetime import datetime, timezone
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(pool['decidedAt'].replace('Z', '+00:00'))).total_seconds()
        if pool.get('repo') == config['repo'] and pool.get('decision') in ('APPROVED', 'APPROVED_WITH_CONDITIONS') and 0 <= age < 7 * 86400:
            approved = {r['identifier']: r['observationDigest'] for r in pool.get('issues', [])
                        if r.get('implementationApproved') is True and re.fullmatch(r'CAF-[1-9][0-9]*', r.get('identifier', ''))
                        and re.fullmatch(r'[a-f0-9]{64}', r.get('observationDigest', ''))}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    facts['pool'] = sorted((key, value) for key, value in approved.items())
    candidates = [r['key'] for r in issues if r['stateType'] == 'unstarted' and not r.get('assignee')
                  and (not {'human-approval', 'risk:high'}.intersection(r['labels'])
                       or (r['key'] in approved and approved[r['key']] == r.get('descriptionHash')))]
    underway = any(r['stateType'] == 'started' for r in issues) or bool(prs)
    collection = any(j['stage'] in ('collected', 'execution-unconfirmed', 'unconfirmed')
                     and j['cleanup'] != 'removed' for j in jobs)
    return facts, bool(candidates or underway or collection)


def prompt(config, identifier, facts):
    # Only trusted controller instructions and identifiers enter the prompt;
    # titles, descriptions, PR bodies and terminal output are source data only.
    return ('Owner の依頼による Banana の自律進行。対象は ' + config['repo'] + ' の委任済み開発範囲。\n'
            '最初に ' + str(ROOT / 'roles/banana/skill/SKILL.md') + ' と '
            + str(Path.home() / '.codex/AGENTS.md') + ' の現在のユーザー恒久指示、'
            '対象 repo の concafe-orchestration の必要な手順を読む。現在の直接指示を古い資料より優先する。\n'
            '既存担当・worktree・branch・PR・未コミット成果・既存の監視を引き継ぎ、重複起動しない。'
            '実装 WIP は最大2本。完了成果を回収し、検査・commit/PR・指摘修正・独立レビュー・CI・'
            '自動 merge 後の完了確認を、実際の委任と各ゲートに沿って進める。'
            '実装枠が空いたら Todo の依存・既存担当・AC・共有ファイル競合・優先順位を現物で確認し補充する。'
            '着手候補の目標は3〜5件（実装WIPとは別）。'
            'Orbitの固定着手委任記録 ~/.local/share/orbit-console/start-pool.json を確認し、'
            '受入条件のdigest・期限・具体的な実装/検査/PR範囲と現物が一致する案件を選ぶ。'
            'human-approvalラベルの有無だけで委任を判定しない。本番・secret・課金等の本人操作は実装委任と分ける。'
            '候補が3件未満なら新たな上位判断のpacketを準備し、既存の担当経路で補充する。'
            '1件は独立して検証・mergeできる受入範囲に絞り、仕様判断・共通化・運用変更を混在させない。'
            'レビュー依頼は受付で止めず、実モデル/effort/session・固定SHA・開始証明・結果・必須CIを回収する。'
            '既存レビューがある案件の二重起動を避け、開始できない場合は拒否・認証・native startup等の原因を保持する。'
            'レビュー/CI/人間判断待ちの案件があっても、独立した進められる案件を続ける。'
            '同じ案件の別場所・別PR・二重監視を増やさない。\n'
            '通常の新規進行・実装は Sol medium、複雑な技術作業は Sol high。'
            'concafe の固定 full head SHA の最終独立レビュー・署名は未関与の別 Codex タスクの Astra high、'
            '具体的な上位判断は別 Codex タスクの Astra medium（Owner CAF-279）。'
            '新規 subagent 起動・追加依頼、自己 PASS、手動 Ready/merge、権限迂回、鍵配布をしない。'
            '必須CI、固定SHA署名、自動Ready/guarded auto-merge、人間ゲートを維持する。\n'
            '実装候補の検知は着手許可や依存確認の代わりにならない。'
            '外部取得失敗・利用上限・判断待ちを成功扱いしない。全件待ちならその理由を保持し、'
            '通常CI進捗や無変化だけで Owner に通知しない。重要な完成・失敗・必要な本人操作を報告する。\n'
            '今回の検知: issue=' + ','.join(row['key'] for row in facts['issues'])
            + '; PR=' + ','.join(str(row['number']) for row in facts['prs']) + '。現在値を取得してから行動する。\n'
            '今回の進行が一区切りついたら、返答前に必ず次を実行する:\n'
            'banana continue settle --id ' + identifier
            + ' --outcome progressed --note "確認した成果、次の担当と行動、または待機理由"\n'
            '（outcome は3択から1つ。進めたら progressed のまま、外部状態待ちは waiting に置き換え、'
            '利用上限や本人入力が不可欠なら blocked）。失敗しても新規送信せず記録を残す。'
            'Owner の停止指示は banana continue pause で継続運転も止める。')


def ready(client, terminal):
    status = client.call('status')
    if 'terminal.prompt-delivery.v1' not in status.get('runtime', {}).get('capabilities', []):
        raise ValueError('Durable prompt delivery is unavailable')
    shown = client.call('terminal', 'show', '--terminal', terminal['handle'])['terminal']
    if (shown.get('incarnationId') != terminal['incarnationId'] or not shown.get('connected')
            or not shown.get('writable') or shown.get('agentIdentity') != terminal['agentIdentity']):
        raise ValueError('Banana terminal incarnation changed')
    wait = client.call('terminal', 'wait', '--terminal', terminal['handle'], '--for', 'tui-idle', '--timeout-ms', '1000')
    if not wait.get('wait', {}).get('satisfied'):
        return False
    lines = client.call('terminal', 'read', '--terminal', terminal['handle'], '--limit', '20')['terminal'].get('tail')
    if not isinstance(lines, list):
        raise ValueError('Terminal input is unconfirmed')
    inputs = [line.strip() for line in lines if re.match(r'^\s*[❯›]', line)]
    # Native terminal read uses the current screen. A user draft must survive.
    return bool(inputs) and not inputs[-1][1:].strip()


def record_receipt(delivery, result):
    receipt = result.get('send', result)
    delivery['receipt'] = result
    durable = receipt.get('prompt') or {}
    accepted = (receipt.get('accepted') is True and bool(durable.get('requestId'))
                and durable.get('provider') != 'old-host')
    stages = durable.get('stages', [])
    turn_started = any((stage == 'turn_started' or isinstance(stage, dict)
                        and stage.get('stage', stage.get('name')) == 'turn_started') for stage in stages)
    delivery.update(status='accepted' if accepted else 'unconfirmed', turnStarted=turn_started)


def _tick(client, config, root, state):
    state['observationPhase'] = 'runtime'
    native, home, agent, terminal, mode = existing_agent(client)
    if mode == 'interrupted':
        state.update(enabled=False, reason='human-interruption', updatedAt=utcnow())
        write(root, state)
        return {'status': 'paused', 'reason': state['reason']}
    if mode == 'busy':
        return {'status': 'busy', 'starts': 0}
    delivery = state.get('delivery')
    if delivery and delivery['status'] in ('sending', 'unconfirmed'):
        return {'status': 'delivery-unconfirmed', 'id': delivery['id'], 'starts': 0}
    if delivery and delivery['status'] == 'accepted':
        # A send receipt alone is never completion. Explicit settlement is the
        # normal route; native evidence also recovers an omitted callback.
        if (terminal['incarnationId'] != delivery['incarnationId']
                or terminal['handle'] != delivery['handle']):
            return {'status': 'delivery-unconfirmed', 'id': delivery['id'], 'starts': 0}
        if not delivery.get('turnStarted'):
            # Observe the *same* durable request. A different human turn or
            # unrelated background work must not prove this request started.
            request_id = delivery['receipt']['send']['prompt']['requestId']
            result = client.call('terminal', 'send', '--terminal', terminal['handle'],
                                 '--text', delivery['text'], '--enter', '--wait-submit', '1',
                                 '--retry-request', request_id, mutation=True)
            record_receipt(delivery, result)
            write(root, state)
            if delivery['status'] != 'accepted':
                return {'status': 'delivery-unconfirmed', 'id': delivery['id'], 'starts': 0}
        message_hash = digest(agent.get('lastAssistantMessage'))
        if (not delivery.get('turnStarted') or message_hash == delivery['beforeMessage']
                or agent.get('updatedAt', 0) <= delivery['beforeUpdatedAt']):
            return {'status': 'awaiting-settlement', 'id': delivery['id'], 'starts': 0}
        delivery.update(status='settled', outcome='progressed', note='native idle and new assistant response')
        write(root, state)
    state['observationPhase'] = 'project'
    facts, actionable = observe(client, config, native)
    fingerprint = digest(facts)
    if not actionable:
        return {'status': 'waiting', 'reason': 'no-actionable-work', 'starts': 0}
    if delivery and delivery['status'] == 'settled' and delivery['fingerprint'] == fingerprint:
        if delivery['outcome'] in ('waiting', 'blocked'):
            return {'status': 'waiting', 'reason': delivery['outcome'], 'starts': 0}
        if state.get('unchangedRounds', 0) >= 3:
            return {'status': 'waiting', 'reason': 'no-observable-progress', 'starts': 0}
    state['observationPhase'] = 'readiness'
    if not ready(client, terminal):
        return {'status': 'busy-or-user-draft', 'starts': 0}
    # Observation may take seconds. Recheck human interruption and ownership
    # immediately before the send fence, including a concurrent CLI pause.
    if (root / 'pause-requested').exists():
        state.update(enabled=False, reason='owner-stop', updatedAt=utcnow())
        write(root, state)
        return {'status': 'paused', 'starts': 0}
    _, _, current_agent, current_terminal, current_mode = existing_agent(client)
    if current_mode == 'interrupted':
        state.update(enabled=False, reason='human-interruption', updatedAt=utcnow())
        write(root, state)
        return {'status': 'paused', 'starts': 0}
    if (current_mode != 'idle' or current_agent.get('paneKey') != agent['paneKey']
            or current_terminal['incarnationId'] != terminal['incarnationId']
            or current_agent.get('updatedAt') != agent.get('updatedAt')):
        return {'status': 'busy-or-user-draft', 'starts': 0}
    identifier = uuid.uuid4().hex
    text = prompt(config, identifier, facts)
    rounds = state.get('unchangedRounds', 0) + 1 if state.get('lastFingerprint') == fingerprint else 1
    state.update(lastFingerprint=fingerprint, unchangedRounds=rounds, updatedAt=utcnow(),
                 delivery={'id': identifier, 'status': 'sending', 'fingerprint': fingerprint,
                           'handle': terminal['handle'], 'incarnationId': terminal['incarnationId'],
                           'paneKey': agent['paneKey'],
                           'text': text,
                           'beforeMessage': digest(agent.get('lastAssistantMessage')),
                           'beforeUpdatedAt': agent.get('updatedAt', 0), 'promptHash': hashlib.sha256(text.encode()).hexdigest()})
    write(root, state)  # Fence before input; a crash here must never re-send.
    try:
        result = client.call('terminal', 'send', '--terminal', terminal['handle'], '--text', text,
                             '--enter', '--wait-submit', '1', mutation=True)
        # Store the complete receipt privately for reconciliation; don't mistake
        # enqueue for a started turn or an agent's acceptance of task ownership.
        record_receipt(state['delivery'], result)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        state['delivery'].update(status='unconfirmed')
    write(root, state)
    return {'status': state['delivery']['status'], 'id': identifier,
            'turnStarted': state['delivery'].get('turnStarted', False), 'starts': 0}


def tick(config, root=None, client=None):
    root = Path(root or STATE_ROOT)
    validate(config)
    local_orca_only()
    if not (root / 'control.json').exists():
        return {'status': 'disabled', 'starts': 0}
    try:
        with control(root) as (root, value):
            if (root / 'pause-requested').exists():
                value.update(enabled=False, reason='owner-stop', updatedAt=utcnow())
                write(root, value)
                return {'status': 'paused', 'starts': 0}
            if not value['enabled']:
                return {'status': 'disabled', 'starts': 0}
            try:
                result = _tick(client or Client(seconds=90), config, root, value)
                value['lastObservation'] = dict(result, at=utcnow())
                write(root, value)
                return result
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                # No arbitrary API error or terminal content enters diagnostics.
                value['lastObservation'] = {'status': 'unconfirmed', 'reason': type(exc).__name__,
                                            'phase': value.get('observationPhase'), 'at': utcnow()}
                write(root, value)
                return {'status': 'unconfirmed', 'reason': type(exc).__name__,
                        'phase': value.get('observationPhase'), 'starts': 0}
    except BlockingIOError:
        return {'status': 'tick-already-running', 'starts': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='banana continue', allow_abbrev=False)
    parser.add_argument('action', choices=('enable', 'pause', 'status', 'tick', 'settle'))
    parser.add_argument('--state-root', type=Path, default=STATE_ROOT)
    parser.add_argument('--id')
    parser.add_argument('--outcome', choices=('progressed', 'waiting', 'blocked'))
    parser.add_argument('--note')
    args = parser.parse_args(argv)
    try:
        local_orca_only()
        config = json.loads(CONFIG.read_text())
        validate(config)
        if args.action == 'tick':
            result = tick(config, args.state_root)
        elif args.action == 'pause':
            root = state_directory(args.state_root)
            # A stop request must not be lost while the clock owns its lock.
            marker = root / 'pause-requested'
            try:
                with marker.open('x') as stream:
                    stream.write(args.note or 'owner-stop')
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                pass
            try:
                with control(root) as (root, value):
                    value.update(enabled=False, reason=args.note or 'owner-stop', updatedAt=utcnow())
                    write(root, value)
                    result = value
            except BlockingIOError:
                result = {'enabled': False, 'status': 'pause-requested'}
        else:
            with control(args.state_root) as (root, value):
                if args.action == 'enable':
                    if not args.note or not args.note.strip():
                        raise ValueError('Record the direct Owner delegation with --note')
                    value.update(enabled=True, authorization=args.note, updatedAt=utcnow())
                    (root / 'pause-requested').unlink(missing_ok=True)
                    # Enabling never clears an uncertain delivery fence.
                    if not value.get('delivery') or value['delivery']['status'] == 'settled':
                        value.pop('delivery', None)
                        value['unchangedRounds'] = 0
                    write(root, value)
                elif args.action == 'settle':
                    delivery = value.get('delivery')
                    if (not delivery or args.id != delivery['id'] or not args.outcome
                            or not args.note or not args.note.strip()
                            or delivery['status'] not in ('accepted', 'settled')):
                        raise ValueError('Exact accepted delivery ID, outcome and note are required')
                    if delivery['status'] == 'settled' and delivery.get('outcome') != args.outcome:
                        raise ValueError('A settled outcome cannot be replaced')
                    delivery.update(status='settled', outcome=args.outcome, note=args.note, settledAt=utcnow())
                    write(root, value)
                result = dict(value, pauseRequested=(root / 'pause-requested').exists())
                if result['pauseRequested']:
                    result.update(enabled=False, status='paused')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print('Continuation state unconfirmed: ' + type(exc).__name__, file=sys.stderr)
        return 4
