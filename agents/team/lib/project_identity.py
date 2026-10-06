"""Local project identity, shared by launch guards and review intake."""
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from checkout_context import git_process


def github_slug(url):
    """Return identity only; never include credentials or remote URLs in errors."""
    match = re.fullmatch(r'git@github\.com:([^\s]+)', url, re.I)
    if match:
        path = match[1]
    else:
        parsed = urlsplit(url)
        if parsed.scheme not in ('https', 'ssh') or parsed.hostname != 'github.com' or parsed.query or parsed.fragment:
            return None
        path = parsed.path.lstrip('/')
    path = path.removesuffix('/').removesuffix('.git')
    return path if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+', path) else None


def github_repository(root):
    """Acceptance scope must resolve explicitly from the checkout's origin."""
    git = shutil.which('git')
    if not git:
        raise ValueError('git が見つからない')
    result = git_process(git, root, 'config', '--get', 'remote.origin.url')
    slug = github_slug(result.stdout.strip()) if result.returncode == 0 else None
    if not slug:
        raise ValueError('受入確認の対象を origin の GitHub repository と照合できない')
    return slug


def is_concafe_path(path):
    """Recognize renamed worktrees; an unreadable repository is not a safe bypass."""
    path = Path(path).expanduser().resolve()
    if (path / '.agents/skills/concafe-orchestration/SKILL.md').is_file():
        return True
    git = shutil.which('git')
    if not git:
        raise ValueError('git が見つからない。対象の契約を確認できない')
    result = git_process(git, path, 'rev-parse', '--show-toplevel')
    if result.returncode:
        if result.returncode == 128 and 'not a git repository' in result.stderr.lower():
            return False  # Explicit manual sessions outside Git remain supported.
        raise ValueError('対象 checkout の識別を確認できない')
    root = Path(result.stdout.strip())
    if root.name == 'concafe-techo' or (root / '.agents/skills/concafe-orchestration/SKILL.md').is_file():
        return True
    remotes = git_process(git, root, 'config', '--get-regexp', r'^remote\..*\.url$')
    if remotes.returncode not in (0, 1):
        raise ValueError('対象 repo の識別を確認できない')
    urls = [line.split(None, 1)[1] for line in remotes.stdout.splitlines() if len(line.split(None, 1)) == 2]
    return any((github_slug(url) or '').lower() == 'kamp-fk/concafe-techo' for url in urls)
