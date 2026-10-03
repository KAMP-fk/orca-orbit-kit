"""Read-only Git checkout facts shared by Banana's CLI and project intake."""
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import subprocess


def git_process(git, path, *args):
    # The requested checkout must not be redirected by an inherited Git environment.
    # Do not let a status observation refresh the index or invoke a filesystem monitor.
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env['GIT_OPTIONAL_LOCKS'] = '0'
    return subprocess.run([git, '-c', 'core.fsmonitor=false', '-C', str(path), *args],
                          text=True, capture_output=True, timeout=15, env=env)


def git_read(git, path, *args):
    proc = git_process(git, path, *args)
    if proc.returncode:
        raise RuntimeError('Git checkout を確認できない: ' + ' '.join(args))
    return proc.stdout.rstrip('\n')


def observe(repo, card=None):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    result = {'schemaVersion': 1, 'observedAt': now, 'scope': 'local-checkout',
              'status': 'error', 'requestedPath': str(repo),
              'remoteFreshness': 'not-checked', 'authorization': 'not-evaluated'}
    try:
        git = shutil.which('git')
        if not git:
            raise RuntimeError('git が見つからない')
        root = Path(git_read(git, repo, 'rev-parse', '--show-toplevel')).resolve()
        if repo != root and root not in repo.parents:
            raise RuntimeError('指定したパスと Git checkout の場所が一致しない')
        sha = git_read(git, root, 'rev-parse', '--verify', 'HEAD')
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', sha):
            raise RuntimeError('full HEAD SHA を確認できない')
        branch_result = git_process(git, root, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        if branch_result.returncode not in (0, 1):
            raise RuntimeError('branch を確認できない')
        branch = branch_result.stdout.rstrip('\n') if branch_result.returncode == 0 else None
        status = git_read(git, root, 'status', '--porcelain=v1', '--untracked-files=normal')
        if git_read(git, root, 'rev-parse', '--verify', 'HEAD') != sha:
            raise RuntimeError('観測中に HEAD が変わった。現在の checkout を再確認する')
        contracts = []
        for relative in ('AGENTS.md', 'CLAUDE.md', 'docs/WORKFLOW.md',
                         '.agents/skills/concafe-orchestration/SKILL.md'):
            source = root / relative
            contracts.append({'path': str(source), 'present': source.is_file(), 'contentRead': False})
        result.update(status='complete', repositoryRoot=str(root), branch=branch,
                      detached=branch is None, headSha=sha, dirty=bool(status),
                      changes=status.splitlines(), contractSources=contracts)
        if card is not None:
            info = {'path': str(card), 'present': card.is_file(), 'contentIncluded': False}
            if card.name.startswith('.env'):
                raise RuntimeError('状況カードには Markdown のカードを指定する。環境変数ファイルは読まない')
            if card.is_file():
                # Read only to count lines; never include the card's contents in output.
                info.update(lineCount=len(card.read_text().splitlines()), limit=50)
                info['withinLimit'] = info['lineCount'] <= info['limit']
            result['statusCard'] = info
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError) as exc:
        result.update(status='error', error=str(exc))
    return result


def require_checkout(path):
    result = observe(Path(path).expanduser().resolve())
    if result['status'] != 'complete':
        raise ValueError(result['error'])
    return result


def common_dir(source):
    root = Path(source['repositoryRoot'])
    return Path(git_read(shutil.which('git'), root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()


def resolve_ref(root, ref):
    return git_read(shutil.which('git'), root, 'rev-parse', '--verify', ref + '^{commit}')
