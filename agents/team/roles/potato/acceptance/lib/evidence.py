#!/usr/bin/env python3
"""Validate launcher-owned acquisition facts and bind a report to its packet."""
import json
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r"[0-9a-fA-F]{40}")
TEST_JOB_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:tests?|vitest|pytest|jest|playwright|specs?)(?![A-Za-z0-9])", re.I
)
OPUS_MODEL_ID = re.compile(r"claude-opus-5-5(?:\[1m\])?")


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_issue(before, after):
    a, b = read(before), read(after)
    require(b.get('ok') is True, 'Issue response is not successful')
    keys = ('identifier', 'title', 'description', 'state', 'updatedAt', 'labels', 'parent')
    for key in keys:
        require(a['result']['issue'].get(key) == b['result']['issue'].get(key), 'Issue changed: ' + key)
    # Comments and relationships can change the acceptance conditions too.
    for key in ('comments', 'children', 'relations', 'attachments'):
        require(a['result'].get(key) == b['result'].get(key), 'Issue context changed: ' + key)


def same_pr(before, after):
    a, b = read(before), read(after)
    for key in ('number', 'url', 'headRefOid', 'baseRefOid', 'baseRefName', 'state', 'updatedAt',
                'title', 'body', 'isDraft', 'labels', 'reviews', 'reviewDecision', 'comments'):
        require(a.get(key) == b.get(key), 'PR snapshot changed: ' + key)


def files(repo, base, head):
    raw = subprocess.check_output(['git', '-C', repo, 'diff', '--name-status', '-z', '--find-renames', base + '...' + head])
    tokens = raw.decode('utf-8', errors='strict').split('\0')
    result, pos = [], 0
    while pos < len(tokens) and tokens[pos]:
        status, name = tokens[pos:pos + 2]
        pos += 2
        row = {'filename': name, 'status': status}
        if status[0] in ('R', 'C'):
            row['previous_filename'] = name
            row['filename'] = tokens[pos]
            pos += 1
        result.append(row)
    return result


def normalize_checks(runs_path, statuses_path, head):
    runs, statuses = read(runs_path), read(statuses_path)
    require(isinstance(runs, list) and bool(runs), 'check-runs pages are missing')
    require(isinstance(statuses, list) and bool(statuses), 'status pages are missing')
    normalized = []
    all_runs, all_statuses = [], []
    for page in runs:
        require(isinstance(page, dict) and isinstance(page.get('check_runs'), list), 'malformed check-runs page')
        require(isinstance(page.get('total_count'), int), 'check-runs count is missing')
        all_runs += page['check_runs']
    require(all(page['total_count'] == len(all_runs) for page in runs), 'incomplete check-runs pagination')
    require(len({r['id'] for r in all_runs}) == len(all_runs), 'duplicate check-run page')
    for run in all_runs:
        require(run.get('head_sha', '').lower() == head.lower(), 'check-run belongs to another head SHA')
        require(isinstance(run.get('name'), str) and bool(run['name']), 'check-run name is missing')
        state = run.get('conclusion') if run.get('status') == 'completed' else 'pending'
        bucket = 'pass' if state == 'success' else 'fail' if state in ('failure', 'timed_out', 'action_required', 'startup_failure') else 'pending' if state == 'pending' else 'unknown'
        normalized.append({'name': run['name'], 'state': state, 'bucket': bucket, 'headSha': head,
                           'link': run.get('html_url'), 'completedAt': run.get('completed_at'), 'source': 'check-run'})
    for page in statuses:
        require(isinstance(page, dict) and page.get('sha', '').lower() == head.lower(), 'statuses belong to another head SHA')
        require(isinstance(page.get('statuses'), list) and isinstance(page.get('total_count'), int), 'malformed status page')
        all_statuses += page['statuses']
    require(all(page['total_count'] == len(all_statuses) for page in statuses), 'incomplete status pagination')
    require(len({s['id'] for s in all_statuses}) == len(all_statuses), 'duplicate status page')
    for status in all_statuses:
        require(isinstance(status.get('context'), str) and bool(status['context']), 'status context is missing')
        state = status.get('state')
        bucket = 'pass' if state == 'success' else 'fail' if state in ('failure', 'error') else 'pending' if state == 'pending' else 'unknown'
        normalized.append({'name': status['context'], 'state': state, 'bucket': bucket, 'headSha': head,
                           'link': status.get('target_url'), 'completedAt': status.get('updated_at'), 'source': 'commit-status'})
    return normalized


def aggregate(checks):
    if any(c['bucket'] == 'fail' for c in checks):
        return 'FAIL'
    return 'PASS' if checks and all(c['bucket'] == 'pass' for c in checks) else 'UNKNOWN'


def action_links(checks, slug):
    require(isinstance(checks, list) and all(isinstance(c, dict) for c in checks), 'malformed check list for job acquisition')
    pattern = re.compile(r'https://github\.com/' + re.escape(slug) + r'/actions/runs/([1-9][0-9]*)/job/([1-9][0-9]*)(?:\?[^\s]*)?$')
    links = []
    for check in checks:
        match = pattern.fullmatch(check.get('link') or '')
        if check.get('source') == 'check-run' and match:
            links.append((int(match[1]), int(match[2]), check))
    return links


def workflow_jobs(runs_path, checks_path, head, slug):
    runs, checks = read(runs_path), read(checks_path)
    require(isinstance(runs, list), 'workflow job snapshots are missing')
    require(all(isinstance(r, dict) for r in runs), 'malformed workflow snapshot')
    require(all(type(r.get('databaseId')) is int and r['databaseId'] > 0 for r in runs), 'invalid workflow run ID')
    links = action_links(checks, slug)
    expected = {run_id for run_id, _, _ in links}
    require(len(runs) == len(expected), 'workflow run snapshots are incomplete or duplicated')
    require({r.get('databaseId') for r in runs} == expected, 'workflow run identity mismatch')
    result = []
    seen = set()
    for run in runs:
        run_id = run['databaseId']
        require(isinstance(run.get('headSha'), str) and run['headSha'].lower() == head.lower(), 'workflow jobs belong to another head SHA')
        require(run.get('url') == f'https://github.com/{slug}/actions/runs/{run_id}', 'workflow repository/run URL mismatch')
        require(type(run.get('attempt')) is int and run['attempt'] > 0, 'workflow attempt is missing')
        require(isinstance(run.get('jobs'), list), 'workflow job list is missing')
        require(all(isinstance(j, dict) for j in run['jobs']), 'malformed workflow job')
        for job in run['jobs']:
            job_id = job.get('databaseId')
            require(type(job_id) is int and job_id > 0 and job_id not in seen, 'workflow job ID is missing or duplicated')
            seen.add(job_id)
            require(isinstance(job.get('name'), str) and bool(job['name']), 'workflow job name is missing')
            require(job.get('status') in ('queued', 'waiting', 'pending', 'requested', 'in_progress', 'completed'), 'workflow job status is missing or invalid')
            require(job.get('conclusion') is None or isinstance(job['conclusion'], str), 'workflow job conclusion is invalid')
            matched = [check for rid, jid, check in links if rid == run_id and jid == job_id]
            require(len(matched) <= 1, 'workflow job matches ambiguous check-runs')
            if matched:
                require(matched[0]['name'] == job['name'], 'workflow job/check name mismatch')
            conclusion = job.get('conclusion')
            state = conclusion if job['status'] == 'completed' else 'pending'
            bucket = 'pass' if state == 'success' else 'fail' if state in ('failure', 'timed_out', 'action_required', 'startup_failure') else 'pending' if state == 'pending' else 'unknown'
            result.append({'id': job_id, 'runId': run_id, 'attempt': run['attempt'], 'name': job['name'],
                           'status': job['status'], 'conclusion': conclusion, 'bucket': bucket,
                           'headSha': head, 'source': 'workflow-job', 'currentCheck': bool(matched)})
        require(all(jid in seen for rid, jid, _ in links if rid == run_id), 'check-run job is absent from workflow job list')
    return result


def verification(checks_path, required_path, policy_path, jobs_path, pr_path=None):
    checks, required, policy = read(checks_path), read(required_path), read(policy_path)
    require(isinstance(checks, list) and isinstance(required, list), 'malformed required-check list')
    selected = []
    resolved = {}
    for item in required:
        require(isinstance(item.get('name'), str) and isinstance(item.get('bucket'), str), 'malformed required check')
        require(item['name'] not in resolved, 'duplicate required check: ' + item['name'])
        matched = [c for c in checks if c['name'] == item['name']]
        # filter=latest can return the same job name from different check suites.
        # Bind duplicates to the exact link selected by gh pr checks --required.
        if len(matched) != 1:
            link = item.get('link')
            require(isinstance(link, str) and bool(link), 'ambiguous required check lacks identity: ' + item['name'])
            matched = [c for c in matched if c.get('link') == link]
        require(len(matched) == 1, 'required check is missing or ambiguous at pinned head: ' + item['name'])
        if item.get('link'):
            require(matched[0].get('link') == item['link'], 'required check identity changed: ' + item['name'])
        required_bucket = item['bucket'] if item['bucket'] in ('pass', 'fail', 'pending') else 'unknown'
        require(matched[0]['bucket'] == required_bucket, 'required check changed during acquisition: ' + item['name'])
        selected.append(matched[0])
        resolved[item['name']] = matched[0]
    mapped = policy['testChecks']
    test_names = set(mapped) | {c['name'] for c in checks if TEST_JOB_TOKEN.search(c['name'])}
    test_sources = {}
    for name in test_names:
        matched = [resolved[name]] if name in resolved else [c for c in checks if c['name'] == name]
        require(len(matched) == 1, 'test check is missing or ambiguous: ' + name)
        test_sources[name] = matched[0]
    jobs = read(jobs_path)
    require(isinstance(jobs, list), 'workflow job evidence is missing')
    tests = []
    for job in jobs:
        if not job['currentCheck'] or job['name'] not in test_sources:
            continue
        check = test_sources[job['name']]
        match = re.fullmatch(r'https://github\.com/[^/]+/[^/]+/actions/runs/([1-9][0-9]*)/job/([1-9][0-9]*)(?:\?[^\s]*)?', check.get('link') or '')
        if check.get('source') == 'check-run' and match and (int(match[1]), int(match[2])) == (job['runId'], job['id']):
            tests.append(job)
    ci = aggregate(selected)
    deferred = []
    draft_light = policy.get('draftLightCi') is True
    if draft_light:
        # T4 2026-10-08: risk:high / risk:low are reviewed in Draft on the light CI; the
        # heavy jobs are guarded by the merge gate (CI / full completed/success). Only a
        # genuinely skipped required check is deferred; fail / pending / unknown never are.
        require(pr_path is not None, 'draft light CI requires the PR snapshot')
        pr = read(pr_path)
        require(pr.get('isDraft') is True, 'draft light CI applies only to a Draft PR')
        labels = pr.get('labels')
        require(isinstance(labels, list) and any(
            isinstance(label, dict) and label.get('name') in ('risk:high', 'risk:low')
            for label in labels), 'draft light CI requires an exact risk:high / risk:low label')
        ran = [c for c in selected if c.get('state') != 'skipped']
        deferred = [c for c in selected if c.get('state') == 'skipped']
        if ci == 'UNKNOWN' and ran and deferred and all(c['bucket'] == 'pass' for c in ran):
            ci = 'PASS'
    return {'CI': ci, 'Tests': aggregate(tests), 'requiredChecks': selected,
            'draftLightCi': draft_light, 'deferredToMergeGate': deferred,
            'deferredPolicy': 'Draft with an exact risk:high / risk:low label only. Skipped required checks are not evidence; they are left to the CI / full merge gate.',
            'testChecks': tests, 'explicitTestChecks': mapped,
            'workflowJobs': jobs,
            'testEvidencePolicy': 'pinned head/run/attempt and current check-run job ID; named completed/success workflow jobs only',
            'testEvidenceLimit': 'job success proves that job ran, not that every test inside it ran; CI / full success can coexist with skipped db/e2e (#279)',
            'possiblePostReviewConditions': [c for c in selected if re.search(r'review|verdict', c['name'], re.I)],
            'postReviewPolicy': 'Classification only. Required gates remain required; no success is inferred.'}


def same_verification(before, after):
    a, b = read(before), read(after)
    for key in ('CI', 'Tests'):
        require(a[key] == b[key], 'verification changed: ' + key)
    for key in ('requiredChecks', 'testChecks'):
        fingerprint = lambda rows: sorted((row['name'], row['bucket'], row['headSha'], row.get('link') or '', row.get('source') or '', row.get('runId', 0),
                                          row.get('attempt', 0), row.get('id', 0), row.get('status', ''),
                                          row.get('conclusion') or '') for row in rows)
        require(fingerprint(a[key]) == fingerprint(b[key]), 'verification evidence changed: ' + key)


def claude_metadata(path, requested_model, phase):
    result = read(path)
    require(requested_model == 'claude-opus-5-5', 'unsupported requested Claude model policy')
    require(result.get('type') == 'result' and result.get('is_error') is False, 'Claude result metadata is not successful')
    require(isinstance(result.get('session_id'), str) and bool(result['session_id']), 'Claude actual session is missing')
    usage = result.get('modelUsage')
    require(isinstance(usage, dict) and bool(usage), 'Claude actual model usage is missing')
    require(len(usage) == 1, 'Claude actual model usage mixes multiple model IDs')
    require(all(OPUS_MODEL_ID.fullmatch(model) is not None for model in usage), 'Claude actual model usage contains unknown or unapproved model IDs')
    require(all(isinstance(details, dict) for details in usage.values()), 'Claude model usage metadata is malformed')
    require(isinstance(result.get('result'), str) and bool(result['result'].strip()), 'Claude result text is missing')
    if phase == 'preflight':
        require(result['result'].strip() == 'PREFLIGHT_OK', 'Claude probe did not return the expected result')
    return {'requestedModel': requested_model, 'actualModelIds': sorted(usage), 'sessionId': result['session_id'], 'phase': phase}


def disclaims_fixed_review_role(report, summary):
    # Enumerated direct Japanese denials only, not natural-language proof.
    # Fold prose continuations, but never join sections or distinct list items.
    def blocks(text):
        current = []
        for raw in text.splitlines():
            line = raw.strip()
            boundary = not line or re.match(r'^(?:\* |\- |\d+\. |[A-Za-z ]+:$|#+ )', line)
            if boundary and current:
                yield ' '.join(current)
                current = []
            if line:
                current.append(re.sub(r'[ \t]+', ' ', line.replace('`', '').replace('**', '')))
        if current:
            yield ' '.join(current)
    target = r'(?:最終独立レビュー(?:・署名\s*verdict)?|最終独立ゲート|最終ゲート(?:充足)?|review:passed(?:\s*status)?|R\s*段)'
    suffix = r'(?:の代わりには?な(?:りません|らない)|の根拠には?ならない|と別の条件(?!を要求しない)|を代替しない|へ(?:転用|昇格)しない|(?:を|は)(?:満たさない|充足しない)(?!項目))'
    denial = target + r'\s*' + suffix
    cue = r'(?:この|本)(?:汎用 Issue reviewer の)?\s*(?:PASS|判定|レビュー)[^。\n]{0,100}'
    for text, need_cue in ((summary, False), (report, True)):
        for block in blocks(text):
            for sentence in re.split(r'。', block):
                if re.search((cue if need_cue else '') + denial, sentence):
                    return True
    return False


def validate_verdict(packet):
    root = Path(packet)
    meta = read(root / 'meta.json')
    report = (root / 'verdict.md').read_text()
    require(meta['evidence']['complete'] is True, 'packet has missing acquisition evidence')
    # Fixed labels and exactly one value prevent an earlier/different report being silently recorded.
    markers = {}
    def single(pattern, label):
        matches = list(re.finditer(pattern, report, re.MULTILINE))
        require(len(matches) == 1, label + ' must appear exactly once')
        markers[label] = matches[0]
        return matches[0].group(1).strip()
    issue = single(r'^Issue: (.+)$', 'Issue')
    require(issue == meta['issue']['identifier'] + ' ' + meta['issue']['title'], 'Issue does not match packet')
    verdict = single(r'^Verdict: (.+)$', 'Verdict')
    require(verdict in ('PASS', 'CHANGES_REQUIRED', 'BLOCKED'), 'invalid Verdict')
    for label in ('Summary', 'Acceptance Criteria', 'Findings', 'Required Changes', 'Verification'):
        single(r'^(' + re.escape(label) + r'):$', label)
    positions = [markers[label].start() for label in ('Issue', 'Verdict', 'Summary', 'Acceptance Criteria', 'Findings', 'Required Changes', 'Verification')]
    require(positions == sorted(positions), 'report sections are out of order')
    values = {key: single(r'^\* ' + key + r': (.+)$', key) for key in ('PR', 'Commit', 'CI', 'Tests')}
    for key in ('Reviewer', 'Involvement', 'Review Mode'):
        values[key] = single(r'^\* ' + key + r': (.+)$', key)
    mode = meta.get('reviewMode')
    require(mode in ('fixed-pr', 'issue'), 'packet review mode is missing or invalid')
    require(values['Review Mode'] == mode, 'Review Mode does not match launcher context')
    require(bool(values['Reviewer']) and values['Reviewer'].casefold() not in ('unknown', '-', 'n/a', '不明', 'なし') and re.search(r'<[^>]*>', values['Reviewer']) is None, 'Reviewer identity is missing or a placeholder')
    require(values['Involvement'] in ('NOT_INVOLVED', 'INVOLVED', 'UNKNOWN'), 'invalid Involvement declaration')
    summary = report[markers['Summary'].end():markers['Acceptance Criteria'].start()]
    require('<関与の表明（未関与なら定型文）>' not in summary, 'Summary involvement declaration is a placeholder')
    non_involvement = '本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。'
    require(values['Involvement'] == 'NOT_INVOLVED' or non_involvement not in report, 'non-involvement declaration contradicts Involvement')
    require(values['Involvement'] != 'NOT_INVOLVED' or non_involvement in summary, 'NOT_INVOLVED requires non-involvement declaration in Summary')
    require(values['CI'] in ('PASS', 'FAIL', 'UNKNOWN') and values['Tests'] in ('PASS', 'FAIL', 'UNKNOWN'), 'invalid CI or Tests value')
    selected = []
    for candidate in meta['prCandidates']:
        pr_root = root / 'github' / f"pr-{candidate['owner']}-{candidate['repo']}-{candidate['number']}"
        pr = read(pr_root / 'pr.json')
        # The protocol permits a PR number or its URL. A number must identify one candidate.
        if values['PR'] in (pr['url'], str(pr['number']), '#' + str(pr['number'])):
            selected.append((pr, pr_root))
    if verdict == 'BLOCKED' and values['PR'] == 'UNKNOWN' and values['Commit'] == 'UNKNOWN':
        require(values['CI'] == values['Tests'] == 'UNKNOWN', 'unidentified PR cannot have successful verification')
        return {'verdict': verdict, 'issue': meta['issue']['identifier'], **values}
    require(len(selected) == 1, 'PR is missing, ambiguous, or outside this packet')
    pr, pr_root = selected[0]
    require(SHA.fullmatch(values['Commit']) is not None and values['Commit'].lower() == pr['headRefOid'].lower(), 'Commit does not match full head SHA')
    facts = read(pr_root / 'verification.json')
    observed_ci = facts['CI']
    require(values['CI'] == observed_ci, 'CI does not match acquired check results: ' + observed_ci)
    observed_tests = facts['Tests']
    require(values['Tests'] == observed_tests, 'Tests does not match identifiable test jobs: ' + observed_tests)
    if verdict == 'PASS':
        require(values['Involvement'] == 'NOT_INVOLVED', 'PASS requires reviewer-declared non-involvement')
        if mode == 'fixed-pr':
            if pr['url'].lower().startswith('https://github.com/kamp-fk/concafe-techo/pull/'):
                require(meta.get('backend') == 'claude' and meta.get('model') == 'claude-opus-5-5', 'concafe fixed-pr PASS requires approved Claude Opus backend/model')
            require(not disclaims_fixed_review_role(report, summary), 'fixed-pr PASS disclaims its independent review role')
        require(values['CI'] == values['Tests'] == 'PASS', 'PASS requires CI and Tests PASS')
        criteria = report[markers['Acceptance Criteria'].end():markers['Findings'].start()]
        criteria_lines = [line for line in criteria.splitlines() if line.strip()]
        require(bool(criteria_lines), 'PASS requires at least one evaluated acceptance criterion')
        require(all(re.fullmatch(r'\* \[x\] \S.*', line) for line in criteria_lines), 'PASS acceptance criteria must all use the exact satisfied-item format')
        findings = report[markers['Findings'].end():markers['Required Changes'].start()]
        require(not re.search(r'\[(?:Critical|High|Medium)\]', findings), 'PASS cannot contain material severity findings')
        changes = report[markers['Required Changes'].end():markers['Verification'].start()]
        require(changes.strip() == '* なし', 'PASS cannot contain required changes')
    return {'verdict': verdict, 'issue': meta['issue']['identifier'], **values}


def main():
    action, *args = sys.argv[1:]
    if action == 'same-pr':
        same_pr(*args)
    elif action == 'same-issue':
        same_issue(*args)
    elif action == 'same-verification':
        same_verification(*args)
    elif action == 'claude-meta':
        print(json.dumps(claude_metadata(*args)))
    elif action == 'files':
        print(json.dumps(files(*args)))
    elif action == 'checks':
        print(json.dumps(normalize_checks(*args)))
    elif action == 'action-runs':
        checks_path, slug = args
        for run_id in sorted({rid for rid, _, _ in action_links(read(checks_path), slug)}):
            print(run_id)
    elif action == 'workflow-jobs':
        print(json.dumps(workflow_jobs(*args)))
    elif action == 'verdict':
        print(json.dumps(validate_verdict(*args)))
    elif action == 'verification':
        print(json.dumps(verification(*args)))
    else:
        raise ValueError('unknown validation action')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, IndexError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print('evidence validation failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
