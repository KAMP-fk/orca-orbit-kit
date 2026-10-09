"""Scoped delivery evidence. No permissions bypass, self-verdict or Ready/merge operation."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
from state_io import write_json

REPO = 'KAMP-fk/concafe-techo'
DEFAULT_STORE = Path.home() / '.local/share/orbit-console'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def call(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=45)
    # Never include raw terminal output, provider errors or credentials in errors.
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise ValueError('command response unconfirmed') from None
    if argv[0] == 'gh':
        if result.returncode:
            raise ValueError('GitHub response unconfirmed')
        return value
    if value.get('ok') is not True:
        raise ValueError('Orca response unconfirmed: ' + str(value.get('error', {}).get('code', 'unknown')))
    return value['result']


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError('oversized evidence')
    return json.loads(data)


def write(path, value):
    write_json(path, value, prefix='.delivery-')


@contextmanager
def lock(root):
    root = Path(root).expanduser().absolute()
    for parent in (root, *root.parents):
        if parent.is_symlink() and parent not in (Path('/tmp'), Path('/var')):
            raise ValueError('linked evidence store')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(root / 'delivery.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield root


def publish_pool(decision, invoke=call):
    if decision.get('decision') not in ('APPROVED', 'APPROVED_WITH_CONDITIONS') or not decision.get('authority'):
        raise ValueError('approved scoped decision required')
    when = datetime.fromisoformat(decision['decidedAt'].replace('Z', '+00:00'))
    age = (datetime.now(timezone.utc) - when).total_seconds()
    if not 0 <= age < 7 * 86400:
        raise ValueError('decision is not current')
    items = decision.get('issues')
    if not isinstance(items, list) or not 0 <= sum(r.get('implementationApproved') is True for r in items) <= 5:
        raise ValueError('bounded implementation pool required')
    safe = []
    seen = set()
    for row in items:
        identifier = row.get('identifier', '')
        if not re.fullmatch(r'CAF-[1-9][0-9]*', identifier) or identifier in seen:
            raise ValueError('invalid or repeated issue')
        seen.add(identifier)
        if row.get('implementationApproved') is not True:
            continue
        for field in ('acceptance', 'allowedScope', 'excludedScope', 'sharedPaths', 'ownerExecutionGates', 'evidence'):
            if not isinstance(row.get(field), list) or any(not isinstance(x, str) or len(x) > 1000 for x in row[field]):
                raise ValueError('scoped acceptance and gates required')
        if not row['acceptance'] or not row['allowedScope'] or not row['sharedPaths']:
            raise ValueError('empty implementation scope')
        if any(p.startswith('/') or '..' in p.split('/') for p in row['sharedPaths']):
            raise ValueError('repository relative scope required')
        detail = invoke(['orca', 'linear', 'issue', '--id', identifier, '--relations', '--json'])
        description = detail.get('issue', {}).get('description')
        meta = detail.get('meta', {})
        if not isinstance(description, str) or meta.get('partial') or meta.get('includeErrors'):
            raise ValueError('current issue evidence incomplete')
        safe.append({k: row[k] for k in ('identifier', 'priority', 'acceptance', 'allowedScope', 'excludedScope',
                                        'sharedPaths', 'implementationApproved', 'ownerExecutionGates', 'evidence')})
        current_digest = hashlib.sha256(description.encode()).hexdigest()
        if row.get('acceptanceDigest') != current_digest:
            raise ValueError('acceptance changed since independent decision')
        safe[-1]['acceptanceDigest'] = current_digest
        from event_monitor import digest as observed_digest
        safe[-1]['observationDigest'] = observed_digest(description)
    return {'version': 1, 'repo': REPO, 'decision': decision['decision'], 'decidedAt': decision['decidedAt'],
            'authority': decision['authority'], 'issues': safe,
            'readyPool': {'targetMinimum': 3, 'approved': len(safe), 'shortfall': max(0, 3 - len(safe))}}


def start_review(args, root, invoke=call):
    """Attach a fresh independently prepared terminal; ambiguous dispatch is lookup-only."""
    if not re.fullmatch(r'[a-f0-9]{40}', args.sha) or args.pr < 1:
        raise ValueError('exact PR and full head SHA required')
    uuid.UUID(args.action_id)
    if not re.fullmatch(r'term_[a-f0-9-]+', args.terminal) or not re.fullmatch(r'task_[a-z0-9]+', args.task):
        raise ValueError('runtime-issued task and terminal required')
    path = root / ('review-action-' + args.action_id + '.json')
    identity = {'repo': REPO, 'number': args.pr, 'head': args.sha, 'taskId': args.task,
                'terminal': args.terminal, 'worktree': str(Path(args.worktree).resolve())}
    saved = read(path) if path.exists() else {'identity': identity, 'state': 'prepared'}
    if saved.get('identity') != identity:
        raise ValueError('action identity changed')
    if saved['state'] in ('dispatching', 'outcome_unknown'):
        # The exact durable request must be resolved by its receipt. Never create another task/turn.
        raise ValueError('dispatch outcome unknown; use the recorded retry-request lookup, do not resend')
    if saved['state'] == 'recorded':
        return saved['receipt']
    # A prepared reviewer must inspect exactly the pinned clean checkout.
    from checkout_context import require_checkout
    from project_identity import github_repository
    checkout = require_checkout(Path(args.worktree))
    if checkout['headSha'] != args.sha or checkout['dirty'] or github_repository(Path(args.worktree)) != REPO:
        raise ValueError('review checkout is not the clean pinned repository')
    pr = invoke(['gh', 'pr', 'view', str(args.pr), '--repo', REPO, '--json', 'headRefOid,state'])
    if pr.get('headRefOid') != args.sha or pr.get('state') != 'OPEN':
        raise ValueError('PR head changed or closed')
    terminal = invoke(['orca', 'terminal', 'show', '--terminal', args.terminal, '--json'])['terminal']
    if Path(terminal.get('worktreePath', '')).resolve() != Path(args.worktree).resolve() or terminal.get('agentIdentity') != 'codex':
        raise ValueError('independent Codex terminal/worktree mismatch')
    screen = invoke(['orca', 'terminal', 'read', '--terminal', args.terminal, '--limit', '50', '--json'])
    rendered = json.dumps(screen, ensure_ascii=False)
    if not re.search(r'GPT-6-Astra\s+high', rendered, re.I):
        saved.update(state='blocked', reason='effective Astra high native prompt unconfirmed')
        write(path, saved)
        raise ValueError(saved['reason'])
    ready = invoke(['orca', 'terminal', 'wait', '--terminal', args.terminal, '--for', 'tui-idle', '--timeout-ms', '10000', '--json'])
    if ready.get('wait', {}).get('satisfied') is not True:
        raise ValueError('native agent readiness unconfirmed')
    saved.update(state='dispatching', requestId=args.action_id)
    write(path, saved)
    try:
        started = invoke(['orca', 'orchestration', 'worker-start', '--task', args.task, '--terminal', args.terminal,
                          '--worktree', 'path:' + identity['worktree'], '--from', args.sender, '--run', args.run,
                          '--retry-request', args.action_id, '--timeout-ms', '15000', '--json'])
        receipt = {**{k: identity[k] for k in ('repo', 'number', 'head', 'taskId')},
                   'dispatchId': started['dispatchId'], 'createdAt': stamp(),
                   'requestId': started.get('prompt', {}).get('requestId'),
                   'promptStages': started.get('prompt', {}).get('stages', []),
                   'processIncarnation': started.get('prompt', {}).get('processIncarnation'),
                   'requestedModel': 'gpt-6-astra', 'requestedEffort': 'high',
                   'effectiveModel': 'gpt-6-astra', 'effectiveEffort': 'high', 'modelEvidence': 'native_prompt'}
        # Resolve actual live provider identity instead of relying solely on requested arguments.
        observed = invoke(['orca', 'orchestration', 'worker-show', '--dispatch', receipt['dispatchId'], '--json'])
        if observed.get('projection', {}).get('provider', {}).get('model') != 'gpt-6-astra':
            raise ValueError('actual reviewer model unconfirmed')
        if observed.get('terminal', {}).get('incarnationId') != receipt['processIncarnation']:
            raise ValueError('review session changed')
        old = read(root / 'review-receipts.json') if (root / 'review-receipts.json').exists() else {'items': []}
        items = [r for r in old.get('items', []) if r.get('repo') == REPO and not (r.get('number') == args.pr and r.get('head') == args.sha)]
        write(root / 'review-receipts.json', {'version': 1, 'items': (items + [receipt])[-50:]})
        saved.update(state='recorded', receipt=receipt)
        write(path, saved)
        return receipt
    except Exception:
        saved.update(state='outcome_unknown', reason='dispatch or proof unconfirmed; no resubmission')
        write(path, saved)
        raise


def record_review(path, root, invoke=call):
    report = read(path)
    reviewer = report.get('reviewer', {})
    sha = report.get('head_sha', '')
    match = re.fullmatch(r'https://github.com/KAMP-fk/concafe-techo/pull/([1-9][0-9]*)', report.get('pr', ''))
    if not match or not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise ValueError('fixed repository/PR/head report required')
    number = int(match.group(1))
    if (not reviewer.get('session_id') or not reviewer.get('implementer_session_id')
            or reviewer.get('independent') is not True or reviewer.get('effective_model') != 'gpt-6-astra'
            or reviewer.get('effective_effort') != 'high' or reviewer.get('session_id') == reviewer.get('implementer_session_id')):
        raise ValueError('independent actual Astra high report required')
    when = datetime.fromisoformat(report['reviewed_at'].replace('Z', '+00:00'))
    if not 0 <= (datetime.now(timezone.utc) - when).total_seconds() < 7 * 86400:
        raise ValueError('review report is not current')
    if report.get('verdict') not in ('PASS', 'CHANGES_REQUIRED', 'BLOCKED'):
        raise ValueError('explicit review result required')
    pr = invoke(['gh', 'pr', 'view', str(number), '--repo', REPO, '--json', 'headRefOid,state'])
    if pr.get('headRefOid') != sha or pr.get('state') != 'OPEN':
        raise ValueError('report is not current open PR head')
    dispatch = reviewer.get('dispatch_id', '')
    if not re.fullmatch(r'ctx_[a-z0-9]+', dispatch):
        raise ValueError('exact dispatch required')
    observed = invoke(['orca', 'orchestration', 'worker-show', '--dispatch', dispatch, '--json'])
    if observed.get('projection', {}).get('provider', {}).get('model') != 'gpt-6-astra' or observed.get('dispatch', {}).get('taskId') != reviewer.get('task_id'):
        raise ValueError('review report runtime identity mismatch')
    terminal = observed.get('terminal', {})
    incarnation = terminal.get('incarnationId')
    if not incarnation:
        raise ValueError('review process incarnation unconfirmed')
    old = read(root / 'review-receipts.json') if (root / 'review-receipts.json').exists() else {'items': []}
    items = [r for r in old.get('items', []) if r.get('repo') == REPO and not (r.get('number') == number and r.get('head') == sha)]
    receipt = {'repo': REPO, 'number': number, 'head': sha, 'taskId': reviewer['task_id'], 'dispatchId': dispatch,
               'processIncarnation': incarnation, 'sessionId': reviewer['session_id'], 'createdAt': report['reviewed_at'],
               'stage': 'review_started', 'reportHead': sha,
               'reportDigest': hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
               'reportVerdict': report.get('verdict'), 'codeVerdict': report.get('code_review_verdict'),
               'effectiveModel': 'gpt-6-astra', 'effectiveEffort': 'high', 'modelEvidence': 'independent_report_and_runtime'}
    write(root / 'review-receipts.json', {'version': 1, 'items': (items + [receipt])[-50:]})
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--store', type=Path, default=DEFAULT_STORE)
    sub = parser.add_subparsers(dest='command', required=True)
    pool = sub.add_parser('publish-pool', allow_abbrev=False)
    pool.add_argument('--decision-file', type=Path, required=True)
    record = sub.add_parser('record-review', allow_abbrev=False)
    record.add_argument('--report-file', type=Path, required=True)
    review = sub.add_parser('review-start', allow_abbrev=False)
    for key in ('sha', 'task', 'terminal', 'worktree', 'sender', 'run', 'action-id'):
        review.add_argument('--' + key, required=True)
    review.add_argument('--pr', required=True, type=int)
    args = parser.parse_args(argv)
    try:
        from role_contract import local_orca_only
        local_orca_only()
        with lock(args.store) as root:
            if args.command == 'publish-pool':
                value = publish_pool(read(args.decision_file))
                write(root / 'start-pool.json', value)
            elif args.command == 'record-review':
                value = record_review(args.report_file, root)
            else:
                value = start_review(args, root)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print('delivery flow: ' + str(error)[:240], file=__import__('sys').stderr)
        return 2
