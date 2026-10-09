"""External implementation sessions with a local issue fence and a separate gate.

This is our command-adapter protocol, not a Devin API implementation. No model,
merge, review-status posting, or secret management occurs in this controller.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
from state_io import write_json

UNCONFIRMED_STATES = ('start_pending', 'start_unknown', 'revision_pending', 'revision_unknown')
RECORD_STATES = {*UNCONFIRMED_STATES, 'implementing', 'in_review', 'fixing',
                 'validation_failed', 'awaiting_merge', 'merged', 'done'}


class Blocked(RuntimeError):
    pass


def save(path, value):
    """Persist the mutation fence before making a possibly billable external call."""
    write_json(path, value, indent=None, newline=False, sync_directory=True)


def config(path, connected=True):
    value = json.loads(Path(path).read_text())
    if (not isinstance(value, dict) or value.get('schemaVersion') != 1
            or not isinstance(value.get('repo'), str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value['repo'])):
        raise Blocked('Invalid configuration')
    if not connected:
        return value
    for key in ('workingState', 'reviewState', 'doneState', 'requiredLabel'):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise Blocked('Unconfigured Linear / validation mapping: ' + key)
    for key in ('readyStates', 'requiredValidation'):
        entries = value.get(key)
        if not isinstance(entries, list) or not entries or not all(isinstance(item, str) and item.strip() for item in entries):
            raise Blocked('State / validation lists required: ' + key)
    active_states = {value[key] for key in ('workingState', 'reviewState', 'doneState')}
    if len(active_states) != 3 or active_states.intersection(value['readyStates']):
        raise Blocked('Linear state mappings overlap')
    for key in ('implementationAdapter', 'qualityAdapter'):
        argv = value.get(key)
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
            raise Blocked('Adapter not configured: ' + key)
        if not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file() or not os.access(argv[0], os.X_OK):
            raise Blocked('Adapter executable must be an existing absolute path: ' + key)
    if value['implementationAdapter'] == value['qualityAdapter']:
        raise Blocked('Implementation and quality adapters must be separate')
    if not isinstance(value.get('branchPattern'), str) or not value['branchPattern'].strip():
        raise Blocked('Repository branch policy required')
    try:
        re.compile(value['branchPattern'])
    except re.error:
        raise Blocked('Invalid repository branch policy') from None
    return value


def issue_id(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*-[1-9][0-9]*', value):
        raise Blocked('Invalid issue identifier')
    return value.upper()


def key(repo, issue):
    return hashlib.sha256((repo.lower() + '\0' + issue_id(issue)).encode()).hexdigest()


def load_record(path, cfg, issue):
    record = json.loads(path.read_text())
    if (not isinstance(record, dict) or record.get('schemaVersion') != 1
            or not isinstance(record.get('repo'), str) or record['repo'].lower() != cfg['repo'].lower()
            or record.get('issue') != issue):
        raise Blocked('Record belongs to another assignment')
    if (not isinstance(record.get('state'), str) or record['state'] not in RECORD_STATES
            or not isinstance(record.get('execution'), str) or not record['execution'].strip()):
        raise Blocked('Invalid execution record')
    if record['state'] not in ('start_pending', 'start_unknown'):
        if any(not isinstance(record.get(key), str) or not record[key].strip() for key in ('session', 'branch')):
            raise Blocked('Execution record has no assigned session / branch')
    return record


@contextmanager
def fenced(root, repo, issue):
    job = Path(root) / key(repo, issue)
    job.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (job / 'lock').open('a') as lock:
        os.chmod(job / 'lock', 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked('Issue already executing; no second session') from None
        yield job


def adapter(cfg, kind, operation, record, timeout=55, **fields):
    request = dict(schemaVersion=1, operation=operation, repo=cfg['repo'],
                   issue=record['issue'], execution=record.get('execution'),
                   session=record.get('session'), branch=record.get('branch'),
                   pr=record.get('pr'), linearScope={key: cfg[key] for key in ('linearWorkspace', 'linearProject', 'linearTeam') if key in cfg}, **fields)
    try:
        result = subprocess.run(cfg[kind + 'Adapter'], input=json.dumps(request),
                                capture_output=True, text=True, timeout=timeout, check=False)
        value = json.loads(result.stdout)
        if result.returncode or not isinstance(value, dict) or value.get('ok') is not True:
            raise Blocked('Adapter operation unconfirmed: ' + operation)
        if not isinstance(value.get('repo'), str) or value['repo'].lower() != cfg['repo'].lower() or value.get('issue') != record['issue']:
            raise Blocked('Adapter identity mismatch: ' + operation)
        return value
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        # Never echo stderr or response bodies; they may contain credentials.
        raise Blocked('Adapter operation unconfirmed: ' + operation) from None


def session_receipt(cfg, value):
    if not isinstance(value.get('session'), str) or not value['session'].strip():
        raise Blocked('Missing external session receipt')
    if not isinstance(value.get('branch'), str) or not re.fullmatch(cfg['branchPattern'], value['branch']):
        raise Blocked('Branch violates repository policy')


def same_session(record, receipt):
    if receipt.get('session') != record['session'] or receipt.get('branch') != record['branch']:
        raise Blocked('Session / branch changed; retain original assignment')


def confirmed_start(cfg, record, receipt):
    session_receipt(cfg, receipt)
    if receipt.get('execution') != record['execution'] or receipt.get('claimConfirmed') is not True:
        raise Blocked('Atomic issue claim unconfirmed')


def pr_receipt(cfg, record, worker):
    head = worker.get('headSha', '')
    if not isinstance(head, str) or not re.fullmatch('[0-9a-f]{40}', head):
        raise Blocked('Missing full head SHA')
    pr = worker.get('pr')
    if not isinstance(pr, str) or not re.fullmatch(re.escape(cfg['repo']) + r'#[1-9][0-9]*', pr, re.I):
        raise Blocked('PR is missing or belongs to another repository')
    if record.get('pr') and record['pr'].lower() != pr.lower():
        raise Blocked('PR changed; no second PR for this issue')
    return head, pr


def inspect_pr(cfg, record):
    gate = adapter(cfg, 'quality', 'inspect', record)
    if (gate.get('headSha') != record['headSha'] or gate.get('branch') != record['branch']
            or not isinstance(gate.get('pr'), str) or gate['pr'].lower() != record['pr'].lower()):
        raise Blocked('GitHub / worker snapshot mismatch')
    if gate.get('linkedIssue') != record['issue']:
        raise Blocked('PR does not link the assigned issue')
    return gate


def validated(cfg, worker):
    entries = worker.get('validation')
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise Blocked('Invalid validation evidence')
    for command in cfg['requiredValidation']:
        if not any(item.get('command') == command and type(item.get('exitCode')) is int and item['exitCode'] == 0
                   and item.get('headSha') == worker['headSha'] for item in entries):
            raise Blocked('Required validation missing for current SHA: ' + command)


def linear(cfg, record, state):
    receipt = adapter(cfg, 'implementation', 'set_linear_state', record, targetState=state)
    if receipt.get('state') != state:
        raise Blocked('Linear read-back does not match target state')


def start(cfg, job, issue):
    path = job / 'record.json'
    if path.exists():
        return load_record(path, cfg, issue)  # Every prior attempt fences a new start.
    record = dict(schemaVersion=1, repo=cfg['repo'], issue=issue, state='start_pending',
                  execution=uuid.uuid4().hex, session=None, branch=None, pr=None)
    ticket = adapter(cfg, 'implementation', 'ticket', record)
    labels, criteria = ticket.get('labels'), ticket.get('acceptanceCriteria')
    has_criteria = (isinstance(criteria, str) and bool(criteria.strip())) or (
        isinstance(criteria, list) and bool(criteria) and all(isinstance(item, str) and item.strip() for item in criteria))
    if (ticket.get('state') not in cfg['readyStates'] or not isinstance(labels, list)
            or cfg['requiredLabel'] not in labels or not has_criteria
            or 'activeExecution' not in ticket or ticket['activeExecution'] is not None):
        raise Blocked('Issue is not eligible or already owned')
    save(path, record)  # Fence BEFORE the external claim/session mutation.
    try:
        receipt = adapter(cfg, 'implementation', 'start', record, ticket=ticket,
                          workingState=cfg['workingState'], branchPattern=cfg['branchPattern'],
                          requiredValidation=cfg['requiredValidation'],
                          instructions='Devin implements this issue directly, reads AGENTS.md and AC, validates, '
                          'creates one linked Draft PR, and handles corrections in this same session/branch. '
                          'Do not delegate implementation. Do not approve, mark Ready, merge, or mark Done. '
                          'Preserve repository CI, review and human gates. Never print credentials.')
        confirmed_start(cfg, record, receipt)
        if receipt.get('state') != cfg['workingState']:
            raise Blocked('In Progress read-back unconfirmed')
        record.update(state='implementing', session=receipt['session'], branch=receipt['branch'])
        save(path, record)
        return record
    except Blocked:
        record['state'] = 'start_unknown'
        save(path, record)
        raise


def sync(cfg, job, record):
    path = job / 'record.json'
    if record['state'] == 'done':
        return record
    if record['state'] in UNCONFIRMED_STATES:
        raise Blocked('External mutation unconfirmed; reconcile receipt without starting again')
    worker = adapter(cfg, 'implementation', 'observe', record)
    same_session(record, worker)
    if not worker.get('pr') and not record.get('pr'):
        if worker.get('workerState') not in ('working', 'validating'):
            raise Blocked('Worker is blocked or unconfirmed')
        return record
    head, pr = pr_receipt(cfg, record, worker)
    record.update(headSha=head, pr=pr, validation=worker.get('validation'))
    # A previous approval is no longer current until this inspection confirms it,
    # including when review is withdrawn or the quality adapter cannot respond.
    record.pop('reviewedSha', None)
    record.pop('reviewEvidence', None)
    if record['state'] == 'awaiting_merge':
        record['state'] = 'in_review'
    save(path, record)
    gate = inspect_pr(cfg, record)
    decision = gate.get('decision')
    # Return Orca's defects even when validation is failing. Validation gates
    # submission/approval/completion, not the request to correct a failing PR.
    if decision != 'changes_requested' or gate.get('prState') == 'MERGED':
        try:
            validated(cfg, worker)
        except Blocked:
            record['state'] = 'validation_failed'
            save(path, record)
            raise
    if gate.get('prState') == 'MERGED':
        # doneReady includes project AC, post-merge verification and the formal
        # gate evidence. The implementation backend cannot issue this receipt.
        if gate.get('doneReady') is not True or not gate.get('evidenceRef') or not isinstance(gate.get('mergeCommit'), str) or not re.fullmatch('[0-9a-f]{40}', gate['mergeCommit']):
            raise Blocked('Merge observed but completion criteria not confirmed by Orca')
        record.update(state='merged', completionEvidence=gate['evidenceRef'])
        save(path, record)
        linear(cfg, record, cfg['doneState'])
        record['state'] = 'done'
        save(path, record)
        return record
    if gate.get('prState') != 'OPEN':
        raise Blocked('PR is closed or unconfirmed; issue cannot complete')
    if decision == 'changes_requested':
        if not gate.get('feedback') or not gate.get('evidenceRef'):
            raise Blocked('Missing Orca correction evidence')
        revision = hashlib.sha256(json.dumps([head, gate['feedback'], gate['evidenceRef']], sort_keys=True).encode()).hexdigest()
        if record.get('revision') == revision:
            record['state'] = 'fixing'
            save(path, record)
            return record  # Do not resend an already accepted correction.
        record.update(state='revision_pending', revision=revision, feedback=gate['feedback'])
        save(path, record)
        try:
            receipt = adapter(cfg, 'implementation', 'revise', record, revision=revision,
                              feedback=gate['feedback'], headSha=head)
            same_session(record, receipt)
            if receipt.get('revision') != revision:
                raise Blocked('Correction was not accepted by the original session')
            record['state'] = 'fixing'
        except Blocked:
            record['state'] = 'revision_unknown'
            save(path, record)
            raise
    else:
        # This receipt is an observation of the formal Orca gate, never a verdict
        # generated by this controller. No GitHub Approve/status/merge write here.
        if decision == 'approved':
            if (gate.get('reviewedSha') != head or gate.get('independent') is not True
                    or gate.get('ciPassed') is not True or gate.get('acceptancePassed') is not True
                    or gate.get('validationPassed') is not True or not gate.get('evidenceRef')):
                raise Blocked('Orca quality gate is incomplete or stale')
            record.update(state='awaiting_merge', reviewedSha=head, reviewEvidence=gate['evidenceRef'])
        elif decision == 'pending':
            record['state'] = 'in_review'
        else:
            raise Blocked('Unknown quality gate decision')
    save(path, record)
    if decision != 'changes_requested':
        linear(cfg, record, cfg['reviewState'])
    return record


def reconcile(cfg, job, record):
    """Read the existing execution receipt; this path never starts/resends work."""
    if record['state'] in ('start_pending', 'start_unknown'):
        receipt = adapter(cfg, 'implementation', 'lookup_start', record)
        confirmed_start(cfg, record, receipt)
        record.update(state='implementing', session=receipt['session'], branch=receipt['branch'])
    elif record['state'] in ('revision_pending', 'revision_unknown'):
        receipt = adapter(cfg, 'implementation', 'lookup_revision', record, revision=record['revision'])
        same_session(record, receipt)
        if receipt.get('accepted') is not True or receipt.get('revision') != record['revision']:
            raise Blocked('Original revision remains unconfirmed')
        record['state'] = 'fixing'
    else:
        raise Blocked('Reconcile only an unconfirmed existing mutation')
    save(job / 'record.json', record)
    return record


def run(cfg, root, issue, action):
    if action not in ('start', 'sync', 'status', 'reconcile'):
        raise Blocked('Unknown flow action')
    issue = issue_id(issue)
    if action == 'status':
        path = Path(root) / key(cfg['repo'], issue) / 'record.json'
        if not path.is_file():
            raise Blocked('No assigned execution')
        return load_record(path, cfg, issue)
    with fenced(root, cfg['repo'], issue) as job:
        if action == 'start':
            return start(cfg, job, issue)
        path = job / 'record.json'
        if not path.exists():
            raise Blocked('No assigned execution; start is explicit')
        record = load_record(path, cfg, issue)
        if action == 'reconcile':
            return reconcile(cfg, job, record)
        return sync(cfg, job, record)
