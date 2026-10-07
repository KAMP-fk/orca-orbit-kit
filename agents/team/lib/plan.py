"""Banana's morning count: read Linear through the Orca CLI and GitHub through gh. Never write.

Counts Todo / In Progress / In Review / open PR / recent 起票・Done・merge, lists one heuristic
"次の一手" per open PR, and ranks implementation candidates with explicit exclusion reasons.
Dependencies and scoped authorization need the issue --relations and approved delivery pool; this older count only ranks candidates. Nothing here starts a
model or agent, and the only output is stdout.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import shutil
import subprocess
import sys

from role_contract import local_orca_only, orca_command

STATES = ('Todo', 'In Progress', 'In Review')
BRANCH_ALLOWED = re.compile(r'^(claude|codex|kakeru9917)/.+$')
WORKTREE_PREFIXES = '(codex|claude|kakeru9917)'
MECHANISM_WORDS = ('レビュー', 'ゲート', 'workflow', 'relay', 'launcher', 'actions')
MECHANISM_CI = re.compile(r'(?<![A-Za-z])CI(?![A-Za-z])')
DEPENDENCY_WORDS = ('blockedBy', 'ブロック', '依存')
OWNER_LABELS = ('human-approval', 'risk:high')
PRIORITY_RANK = {1: 0, 2: 1, 3: 2, 4: 3}  # urgent → low; none / unknown last
STALE_HOURS = 1.5
TIMEOUT = 60
PR_LIMIT = 200
PR_FIELDS = 'number,title,isDraft,headRefName,labels,updatedAt,body'


def now_utc():
    return datetime.now(timezone.utc)


def stamp(moment):
    return moment.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def clean(value, limit=120):
    """Titles and reasons are display data; control sequences and long bodies are not."""
    if not isinstance(value, str):
        return ''
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)[:limit]


# ---------------------------------------------------------------- sources


def run(name, argv, timeout=TIMEOUT):
    """Run one read-only command. Returns (parsed JSON or None, source record)."""
    record = {'name': name, 'command': list(argv), 'status': 'error', 'observed_at': stamp(now_utc())}
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        record['reason'] = argv[0] + ' が見つからない'
        return None, record
    except subprocess.TimeoutExpired:
        record['reason'] = str(timeout) + 's で応答なし'
        return None, record
    except OSError as error:
        record['reason'] = clean(str(error), 80)
        return None, record
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or '').strip().splitlines()
        first = clean(lines[0], 80) if lines else ''
        record['reason'] = 'exit ' + str(result.returncode) + (': ' + first if first else '')
        return None, record
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        record['reason'] = 'JSON ではない出力'
        return None, record
    record['status'] = 'success'
    return payload, record


def orca_result(payload, record, key):
    """Unwrap {ok, result:{<key>:[...]}} or mark the record as an error."""
    result = payload.get('result') if isinstance(payload, dict) else None
    rows = result.get(key) if isinstance(result, dict) else None
    if payload is None or payload.get('ok') is not True or not isinstance(rows, list):
        record['status'] = 'error'
        record['reason'] = record.get('reason') or 'ok な ' + key + ' 応答ではない'
        return None
    meta = result.get('meta') if isinstance(result.get('meta'), dict) else {}
    if result.get('truncated') or meta.get('partial') or meta.get('workspaceErrors'):
        record['status'] = 'truncated'
    return rows


def linear_issues(team, project, extra, name):
    argv = [orca_command(), 'linear', 'list-issues', '--team', team]
    if project:
        argv += ['--project', project]
    argv += list(extra) + ['--json']
    payload, record = run(name, argv)
    return (orca_result(payload, record, 'issues') if payload is not None else None), record


def orca_worktrees():
    payload, record = run('worktree list', [orca_command(), 'worktree', 'list', '--json'])
    rows = orca_result(payload, record, 'worktrees') if payload is not None else None
    if rows is None:
        return None, record
    return [row for row in rows if isinstance(row, dict) and not row.get('isArchived')], record


def gh_prs(repo, state, fields, name, search=None):
    argv = [shutil.which('gh') or 'gh', 'pr', 'list', '-R', repo, '--state', state]
    if search:
        argv += ['--search', search]
    argv += ['--json', fields, '--limit', str(PR_LIMIT)]
    payload, record = run(name, argv)
    if payload is None:
        return None, record
    if not isinstance(payload, list):
        record.update(status='error', reason='PR 一覧ではない応答')
        return None, record
    rows = [row for row in payload if isinstance(row, dict)]
    if len(rows) >= PR_LIMIT:
        record['status'] = 'truncated'
    return rows, record


# ---------------------------------------------------------------- derivations


def label_names(row):
    return [label.get('name', '') for label in row.get('labels') or [] if isinstance(label, dict)]


def issue_number(identifier):
    match = re.search(r'-(\d+)$', identifier or '')
    return int(match.group(1)) if match else None


def is_mechanism(title):
    lowered = (title or '').lower()
    return bool(MECHANISM_CI.search(title or '')) or any(word in lowered for word in MECHANISM_WORDS)


def pr_issue(team, pr):
    """Issue id from the title (start / HOLD: / trailing parens), else branch, else body Closes."""
    key = re.escape(team)
    title = pr.get('title') or ''
    for pattern in (r'^\s*(?:HOLD\s*:\s*)?(' + key + r'-\d+)', r'\((' + key + r'-\d+)\)\s*$'):
        match = re.search(pattern, title, re.I)
        if match:
            return match.group(1).upper(), 'title'
    match = re.search(r'/' + key + r'-(\d+)(?:-|$)', pr.get('headRefName') or '', re.I)
    if match:
        return team.upper() + '-' + match.group(1), 'branch'
    match = re.search(r'\bCloses\s+(' + key + r'-\d+)', pr.get('body') or '', re.I)
    if match:
        return match.group(1).upper(), 'body'
    return None, None


def age_hours(updated_at, now):
    moment = parse_time(updated_at)
    return None if moment is None else max((now - moment).total_seconds() / 3600, 0.0)


def format_age(hours):
    if hours is None:
        return '更新 不明'
    if hours < 1:
        return '更新 ' + str(int(hours * 60)) + 'm前'
    if hours < 48:
        return '更新 ' + str(int(hours)) + 'h前'
    return '更新 ' + str(int(hours // 24)) + 'd前'


def next_move(pr):
    """Heuristic only: a hint for who or what the PR waits on."""
    labels = pr['labels']
    parts = []
    if not pr['branch_allowed']:
        parts.append('branch 名が許可外 → 新しい ref で PR を作り直す')
    elif pr['draft']:
        parts.append('Draft・HOLD → review 待ち' if pr['hold']
                     else 'Draft・HOLD なし → title を HOLD: <issue> の形にして review へ')
    elif 'auto-ready:enabled' in labels:
        parts.append('Ready・auto-ready:enabled → CI/merge の機械待ち')
    else:
        parts.append('Ready・auto-ready なし → 進行担当が auto-ready:enabled を付けるか判断')
    if 'risk:high' in labels:
        parts.append('risk:high → 持ち主の合図')
    if pr['age_hours'] is None:
        parts.append('更新時刻が読めない')
    elif pr['age_hours'] >= STALE_HOURS:
        parts.append('90分以上更新なし → 誰の手か確かめる')
    return '／'.join(parts)


def describe_pr(team, row, now):
    issue, source = pr_issue(team, row)
    branch = row.get('headRefName') or ''
    pr = {
        'number': row.get('number'),
        'title': clean(row.get('title'), 80),
        'issue': issue,
        'issue_source': source,
        'draft': bool(row.get('isDraft')),
        'hold': bool(re.match(r'^\s*HOLD\b', row.get('title') or '', re.I)),
        'labels': label_names(row),
        'branch': branch,
        'branch_allowed': bool(BRANCH_ALLOWED.match(branch)),
        'updated_at': row.get('updatedAt'),
        'age_hours': age_hours(row.get('updatedAt'), now),
    }
    pr['hint'] = next_move(pr)
    return pr


def worktree_matches(team, identifier, rows):
    number = issue_number(identifier)
    pattern = re.compile(r'^' + WORKTREE_PREFIXES + '/' + re.escape(team.lower()) + '-' + str(number) + r'(?:-|$)', re.I)
    found = []
    for row in rows or []:
        branch = re.sub(r'^refs/heads/', '', row.get('branch') or '')
        linked = row.get('linkedLinearIssue')
        if (number is not None and pattern.match(branch)) or (
                isinstance(linked, str) and linked.upper() == (identifier or '').upper()):
            found.append(branch or clean(row.get('displayName'), 60))
    return found


def candidate_entry(issue):
    return {
        'identifier': issue.get('identifier'),
        'number': issue_number(issue.get('identifier')),
        'title': clean(issue.get('title'), 80),
        'priority': issue.get('priority'),
        'priority_label': '-' if not issue.get('priority') else clean(issue.get('priorityLabel'), 20) or '-',
        'labels': label_names(issue),
        'url': issue.get('url'),
    }


def classify(team, todo, worktrees, worktree_record, prs, pr_record):
    """Split Todo into 着手可 / 除外 (with reasons). Dependency mentions are 未確認, not 着手可."""
    by_issue = {}
    for pr in prs or []:
        if pr['issue']:
            by_issue.setdefault(pr['issue'], []).append(pr['number'])
    ready, excluded = [], []
    for issue in todo:
        if not isinstance(issue, dict):
            continue
        entry = candidate_entry(issue)
        identifier = entry['identifier'] or ''
        reasons = []
        owner = [label for label in entry['labels'] if label.lower() in OWNER_LABELS]
        if owner:
            reasons.append(' / '.join(owner) + ' → 持ち主の合図待ち')
        branches = worktree_matches(team, identifier, worktrees)
        if branches:
            reasons.append('既存 worktree ' + ', '.join(branches) + ' → 補充しない')
        numbers = by_issue.get(identifier.upper())
        if numbers:
            reasons.append('既存 PR ' + ', '.join('#' + str(n) for n in numbers) + ' → 補充しない')
        if reasons:
            entry.update(verdict='除外', reasons=reasons)
            excluded.append(entry)
            continue
        description = issue.get('description') if isinstance(issue.get('description'), str) else ''
        words = [word for word in DEPENDENCY_WORDS if word in description]
        if words:
            entry.update(verdict='未確認', reasons=['本文に ' + '/'.join(words) + ' の記述 → 未確認（CLI は返さない。Linear で見る）'])
            excluded.append(entry)
            continue
        # A missing or truncated ownership inventory cannot establish absence.
        unknown = []
        if worktrees is None or worktree_record.get('status') != 'success':
            unknown.append('既存 worktree 未確認（' + worktree_record.get('reason', '一覧が不完全') + '）')
        if prs is None or pr_record.get('status') != 'success':
            unknown.append('PR 未確認（' + pr_record.get('reason', '一覧が不完全') + '）')
        if unknown:
            entry.update(verdict='未確認', reasons=unknown)
            excluded.append(entry)
            continue
        notes = []
        if worktrees is None:
            notes.append('既存 worktree 未確認（' + worktree_record.get('reason', 'worktree list') + '）')
        elif worktree_record.get('status') == 'truncated':
            notes.append('既存 worktree なし（一覧が切れている。未確認）')
        else:
            notes.append('既存 worktree なし')
        if prs is None:
            notes.append('PR 未確認（' + pr_record.get('reason', 'gh') + '）')
        else:
            notes.append('PR なし')
        entry.update(verdict='着手候補', reasons=notes + ['依存・受入範囲・委任は着手前に現物確認'])
        ready.append(entry)
    ready.sort(key=lambda e: (PRIORITY_RANK.get(e['priority'], 9), e['number'] if e['number'] is not None else 10 ** 9))
    excluded.sort(key=lambda e: e['number'] if e['number'] is not None else 10 ** 9)
    return ready, excluded


# ---------------------------------------------------------------- the count


def count_entry(rows, record):
    if rows is None:
        return {'count': None, 'lower_bound': False, 'reason': record.get('reason', record['name'])}
    return {'count': len(rows), 'lower_bound': record['status'] == 'truncated'}


def compute(team, repo, project=None, days=3, wip=2, now=None):
    now = now or now_utc()
    sources, issues, counts = [], {}, {}
    for state in STATES:
        rows, record = linear_issues(team, project, ['--state', state], 'list-issues ' + state)
        sources.append(record)
        issues[state] = rows
        counts[state] = count_entry(rows, record)
    window = '-P' + str(days) + 'D'
    done, record = linear_issues(team, project, ['--state', 'Done', '--updated-at', window], 'list-issues Done')
    sources.append(record)
    counts['done'] = count_entry(done, record)
    created, record = linear_issues(team, project, ['--created-at', window], 'list-issues created')
    sources.append(record)
    counts['created'] = count_entry(created, record)

    worktrees, worktree_record = orca_worktrees()
    sources.append(worktree_record)

    open_rows, open_record = gh_prs(repo, 'open', PR_FIELDS, 'gh pr list open')
    sources.append(open_record)
    prs = None if open_rows is None else [describe_pr(team, row, now) for row in open_rows]
    if prs is not None:
        prs.sort(key=lambda p: p['number'] if isinstance(p['number'], int) else 10 ** 9)
    counts['open_pr'] = count_entry(open_rows, open_record)
    counts['draft_pr'] = ({'count': sum(1 for p in prs if p['draft']), 'lower_bound': open_record['status'] == 'truncated'}
                          if prs is not None else count_entry(None, open_record))

    since = (now - timedelta(days=days)).strftime('%Y-%m-%d')
    merged, merged_record = gh_prs(repo, 'merged', 'number,mergedAt', 'gh pr list merged', 'merged:>=' + since)
    sources.append(merged_record)
    counts['merged'] = count_entry(merged, merged_record)

    open_issues = [row for state in STATES if issues[state] is not None for row in issues[state] if isinstance(row, dict)]
    missing = [state for state in STATES if issues[state] is None]
    mechanism = {
        'mechanism': sum(1 for row in open_issues if is_mechanism(row.get('title'))),
        'product': sum(1 for row in open_issues if not is_mechanism(row.get('title'))),
        'open_issues': len(open_issues),
        'words': ['CI', 'レビュー', 'ゲート', 'workflow', 'relay', 'launcher', 'Actions'],
        'missing_states': missing,
    }

    if issues['Todo'] is None:
        candidates = {'ready': [], 'excluded': [], 'reason': counts['Todo']['reason']}
    else:
        ready, excluded = classify(team, issues['Todo'], worktrees, worktree_record, prs, open_record)
        candidates = {'ready': ready, 'excluded': excluded, 'shown': min(len(ready), 2 * wip)}

    unverified = [record['name'] + ': ' + record.get('reason', '') for record in sources if record['status'] == 'error']
    linear_ok = any(record['status'] != 'error' for record in sources if record['name'].startswith('list-issues'))
    return {
        'team': team, 'repo': repo, 'project': project, 'days': days, 'wip': wip,
        'observed_at': stamp(now),
        'sources': sources,
        'counts': counts,
        'mechanism': mechanism,
        'open_prs': prs,
        'merged_since_utc': since,
        'candidates': candidates,
        'unverified': unverified,
        'linear_available': linear_ok,
        'notes': [
            '+ は上限で切れた下限値（result.truncated / meta.partial）',
            'Done は「updatedAt が窓内で state=Done」の件数。completedAt は CLI が返さない',
            '機構 / 製品は title の語（CI・レビュー・ゲート・workflow・relay・launcher・Actions）だけで分けた粗い分類',
            'state / team 名が違っても CLI は ok・0 件を返す。0 件は名前も確かめる',
            '依存（blockedBy）は issue --relations で別途完全取得する。本文の語だけでは着手許可にしない',
            'open PR の次の一手は推測。確かめてから動く',
        ],
    }


# ---------------------------------------------------------------- rendering


def number(entry):
    if entry['count'] is None:
        return '未確認'
    return str(entry['count']) + ('+' if entry['lower_bound'] else '')


def render(value):
    counts = value['counts']
    lines = ['# plan ' + value['team'] + ' / ' + value['repo']
             + '  （観測 ' + value['observed_at'] + '。数字は Linear / GitHub の読み取り。依存（blockedBy）は CLI が返さないので未確認）']
    lines.append('## 数字')
    lines.append('Todo ' + number(counts['Todo']) + ' / In Progress ' + number(counts['In Progress'])
                 + ' / In Review ' + number(counts['In Review'])
                 + ' / open PR ' + number(counts['open_pr']) + '（Draft ' + number(counts['draft_pr']) + '）'
                 + '/ 直近' + str(value['days']) + '日: 起票 ' + number(counts['created'])
                 + '・Done ' + number(counts['done']) + '・merge ' + number(counts['merged'])
                 + '（merged:>=' + value['merged_since_utc'] + ' UTC）')
    mech = value['mechanism']
    if mech['open_issues'] or not mech['missing_states']:
        suffix = ('。' + ' / '.join(mech['missing_states']) + ' は未確認で含まない') if mech['missing_states'] else ''
        lines.append('機構 vs 製品: 機構 ' + str(mech['mechanism']) + ' / 製品 ' + str(mech['product'])
                     + '（open issue ' + str(mech['open_issues']) + ' 件の title 語分類。粗い' + suffix + '）')
    else:
        lines.append('機構 vs 製品: 未確認（open issue が読めない）')
    for item in value['unverified']:
        lines.append('未確認（' + item + '）')

    lines.append('## open PR（次の一手の候補。推測）')
    prs = value['open_prs']
    if prs is None:
        lines.append('未確認（' + next(r['name'] + ': ' + r.get('reason', '') for r in value['sources'] if r['name'] == 'gh pr list open') + '）')
    elif not prs:
        lines.append('open PR なし')
    else:
        for pr in prs:
            shown = [label for label in pr['labels'] if label.split(':')[0] in ('risk', 'review', 'auto-ready')]
            lines.append('#' + str(pr['number']).ljust(5) + ' ' + (pr['issue'] or '-').ljust(8)
                         + ' ' + ('Draft' if pr['draft'] else 'Ready').ljust(5)
                         + (' HOLD' if pr['hold'] else '')
                         + '  ' + (' '.join(shown) or '-')
                         + '  ' + format_age(pr['age_hours']) + '  → ' + pr['hint'])
        if counts['open_pr']['lower_bound']:
            lines.append('（一覧は ' + str(PR_LIMIT) + ' 件で切れている。下限）')

    lines.append('## 実装候補（WIP 上限 ' + str(value['wip']) + '。順: priority → 番号。除外理由つき）')
    cands = value['candidates']
    if 'reason' in cands:
        lines.append('未確認（list-issues Todo: ' + cands['reason'] + '）')
    else:
        lines.append('着手可の候補:')
        shown = cands['ready'][:cands['shown']]
        if not shown:
            lines.append('  なし')
        for entry in shown:
            lines.append('  ' + entry['identifier'].ljust(8) + ' ' + entry['priority_label'].capitalize().ljust(7)
                         + ' ' + entry['title'][:40].ljust(40) + '  ' + '・'.join(entry['reasons']))
        rest = len(cands['ready']) - len(shown)
        if rest > 0:
            lines.append('  （他 ' + str(rest) + ' 件）')
        lines.append('除外:')
        if not cands['excluded']:
            lines.append('  なし')
        for entry in cands['excluded']:
            lines.append('  ' + entry['identifier'].ljust(8) + ' ' + entry['priority_label'].capitalize().ljust(7)
                         + ' ' + '・'.join(entry['reasons']))
    lines.append('## 注記')
    lines.extend('- ' + note for note in value['notes'])
    return '\n'.join(lines)


# ---------------------------------------------------------------- entry


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog='plan', allow_abbrev=False,
        description='Banana の朝の数え。Linear（Orca CLI）と GitHub（gh）を読むだけ。何も書かず、モデルも起こさない。',
        epilog='exit 0: 出力あり（未確認の節があっても）。exit 1: Linear が全部読めず数字も候補も出せない。exit 2: 引数不正。')
    parser.add_argument('--team', required=True, help='Linear team key（例: CAF）')
    parser.add_argument('--repo', required=True, help='GitHub owner/name（例: KAMP-fk/concafe-techo）')
    parser.add_argument('--project', help='Linear project 名で絞る（任意）')
    parser.add_argument('--days', type=int, default=3, help='起票 / Done / merge を数える窓（日。既定 3）')
    parser.add_argument('--wip', type=int, default=2, help='実装 WIP 上限（既定 2。候補は 2×wip まで表示）')
    parser.add_argument('--json', action='store_true', help='観測と計算を1つの JSON で出す')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
        parser.error('--repo は owner/name の形')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', args.team):
        parser.error('--team は Linear の team key（英数字）')
    if args.days < 1:
        parser.error('--days は 1 以上')
    if args.wip < 1:
        parser.error('--wip は 1 以上')
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        local_orca_only()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    value = compute(args.team, args.repo, args.project, args.days, args.wip)
    if args.json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(value))
    return 0 if value['linear_available'] else 1
