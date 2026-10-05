"""Explicit review selection; preserve request scope across execution and handoff."""
import hashlib
from pathlib import Path
import re
import sys

from checkout_context import require_checkout
from project_identity import github_repository, is_concafe_path
from role_contract import ROOT, role_routing


def review_plan(kind, repo, issue=None, pr=None, prompt_file=None, sha=None):
    source = require_checkout(repo)
    root = Path(source['repositoryRoot'])
    head = source['headSha']
    if sha and (not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha) or sha != head):
        raise ValueError('--sha は対象 checkout の現在の full HEAD SHA を指定する')
    request = None
    if prompt_file:
        path = Path(prompt_file).expanduser().resolve()
        content = path.read_bytes()
        text = content.decode('utf-8')
        if not text.strip():
            raise ValueError('--prompt-file は空でない UTF-8 の依頼を指定する')
        request = {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest(), 'text': text}
    if kind == 'acceptance':
        if not issue or not re.fullmatch(r'[A-Z][A-Z0-9]*-[1-9][0-9]*', issue):
            raise ValueError('受入確認には --issue に Issue ID が必要')
        if pr or sha:
            raise ValueError('--pr / --sha の固定 PR 判定は --kind final で正式経路に引き渡す')
        if prompt_file:
            raise ValueError('受入確認は Issue の AC を使う。--prompt-file は technical / final 用')
    elif kind == 'technical':
        if issue or pr:
            raise ValueError('技術確認は --prompt-file で対象と依頼を書く。--issue / --pr は final 用')
        if not request:
            raise ValueError('技術確認には空でない --prompt-file が必要')
    elif kind == 'final':
        if not sha:
            raise ValueError('最終レビューの引渡しには --sha に現在の full HEAD SHA が必要')
        if issue and not re.fullmatch(r'[A-Z][A-Z0-9]*-[1-9][0-9]*', issue):
            raise ValueError('--issue は Issue ID を指定する')
        if pr and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+#[1-9][0-9]*', pr):
            raise ValueError('--pr は owner/repo#N を指定する')
        if pr and pr.split('#', 1)[0].lower() != github_repository(root).lower():
            raise ValueError('--pr の repository と対象 checkout が一致しない')
    else:
        raise ValueError('review kind が不明')
    concafe = is_concafe_path(root)
    executor = 'potato' if kind == 'technical' else 'peach' if kind == 'acceptance' else None
    plan = {'kind': kind, 'entrypoint': 'review', 'repo': str(root), 'headSha': head,
            'checkoutDirty': source['dirty'], 'roleRouting': role_routing('peach'),
            'executorRole': executor, 'startsSession': False, 'request': request,
            'requiresUninvolvedTask': True, 'requiresFinalVerdict': kind == 'final',
            'isFinalVerdict': False, 'issue': issue, 'pr': pr,
            'policy': 'Owner CAF-279' if concafe else 'target-project-contract'}
    if kind == 'final' or concafe:
        plan.update(route='separate-project-task', executableHere=False, argv=None,
                    requiredModel='gpt-6-astra' if concafe and kind == 'final' else 'gpt-6.1-sol' if concafe else None,
                    requiredEffort=('high' if kind in ('technical', 'final') else 'medium') if concafe else None,
                    reason='未関与の別タスク・実モデル/effort・固定版を正式経路で確認する。受付の計画を PASS と扱わない')
        return plan
    if kind == 'acceptance':
        slug = github_repository(root)
        command = [sys.executable, str(ROOT / 'bin/peach-task'), issue, '--expected-repo', slug]
        plan.update(route='peach', executableHere=True, argv=command, repository=slug,
                    reviewHeadSource='PR full SHA pinned by evidence pipeline')
    else:
        command = [sys.executable, str(ROOT / 'bin/agent'), 'potato', '--repo', str(root),
                   '--access', 'read', '--prompt-file', request['path']]
        plan.update(route='potato', executableHere=True, argv=command)
    return plan
