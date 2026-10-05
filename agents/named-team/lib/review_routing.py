"""Explicit review selection; final verdicts stay in the project's independent route."""
from pathlib import Path
import re
import shutil
import sys

from checkout_context import git_process, require_checkout
from role_contract import ROOT, role_routing


def is_concafe_path(path):
    """Recognize worktrees too; never expose remote URLs or read credential files."""
    path = Path(path).resolve()
    if (path / '.agents/skills/concafe-orchestration/SKILL.md').is_file():
        return True
    git = shutil.which('git')
    if not git:
        raise ValueError('git が見つからない。対象の契約を確認できない')
    result = git_process(git, path, 'rev-parse', '--show-toplevel')
    if result.returncode:
        return False  # Manual non-repository sessions have no project review scope.
    root = Path(result.stdout.strip())
    if root.name == 'concafe-techo' or (root / '.agents/skills/concafe-orchestration/SKILL.md').is_file():
        return True
    remotes = git_process(git, root, 'config', '--get-regexp', r'^remote\..*\.url$')
    if remotes.returncode not in (0, 1):
        raise ValueError('対象 repo の識別を確認できない')
    return any(re.search(r'[:/]KAMP-fk/concafe-techo(?:\.git)?/?$', line, re.I)
               for line in remotes.stdout.splitlines())


def review_plan(kind, repo, issue=None, pr=None, prompt_file=None, sha=None):
    source = require_checkout(repo)
    root = Path(source['repositoryRoot'])
    head = source['headSha']
    if sha and (not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha) or sha != head):
        raise ValueError('--sha は対象 checkout の現在の full HEAD SHA を指定する')
    if kind == 'acceptance':
        if not issue or not re.fullmatch(r'[A-Z][A-Z0-9]*-[1-9][0-9]*', issue):
            raise ValueError('受入確認には --issue に Issue ID が必要')
        if pr:
            raise ValueError('--pr を伴う固定 PR 判定は --kind final で正式経路に引き渡す')
    elif kind == 'technical':
        if not prompt_file or not Path(prompt_file).is_file() or not Path(prompt_file).read_text(encoding='utf-8').strip():
            raise ValueError('技術確認には空でない --prompt-file が必要')
    elif kind == 'final':
        if not sha:
            raise ValueError('最終レビューの引渡しには --sha に現在の full HEAD SHA が必要')
    else:
        raise ValueError('review kind が不明')
    concafe = is_concafe_path(root)
    plan = {'kind': kind, 'entrypoint': 'review', 'repo': str(root), 'headSha': head,
            'roleRouting': role_routing('peach'), 'startsSession': False,
            'requiresUninvolvedTask': True, 'isFinalVerdict': kind == 'final',
            'issue': issue, 'pr': pr, 'policy': 'Owner CAF-279' if concafe else 'target-project-contract'}
    if kind == 'final' or concafe:
        plan.update(route='separate-project-task', executableHere=False, argv=None,
                    requiredModel='gpt-6-astra' if concafe and kind == 'final' else 'gpt-6.1-sol' if concafe else None,
                    requiredEffort='high' if concafe else None,
                    reason='未関与の別タスク・実モデル/effort・固定版を正式経路で確認する。受付の計画を PASS と扱わない')
        return plan
    if kind == 'acceptance':
        command = [sys.executable, str(ROOT / 'bin/peach-task'), issue]
        plan.update(route='peach', executableHere=True, argv=command)
    elif kind == 'technical':
        command = [sys.executable, str(ROOT / 'bin/agent'), 'potato', '--repo', str(root),
                   '--access', 'read', '--prompt-file', str(Path(prompt_file).resolve())]
        plan.update(route='potato', executableHere=True, argv=command)
    else:
        raise ValueError('review kind が不明')
    return plan
