"""Shared role routing and the version-matched Orca executable selection."""
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent


def validate_roles(roles):
    """Reject broken routing before any caller resolves a home or starts a model."""
    roots = set()
    for name, role in roles.items():
        home = role.get('homeRole')
        if home not in roles or roles[home].get('activation') != 'home':
            raise ValueError('role の受付が常設ホームではない: ' + name)
        if role.get('activation') not in ('home', 'on-demand'):
            raise ValueError('role の起動条件が不明: ' + name)
        if role['activation'] == 'home':
            root = str(Path(role['workspaceRoot']).expanduser().resolve())
            if home != name or root in roots:
                raise ValueError('常設ホームの自己参照・一意性が不正: ' + name)
            roots.add(root)
        elif role.get('tabAutostart'):
            raise ValueError('必要時の専門担当を自動待機起動しない: ' + name)
        seen = {name}
        parent = role.get('parentRole')
        while parent is not None:
            if parent not in roles or parent in seen:
                raise ValueError('role の進行担当が不明または循環している: ' + name)
            seen.add(parent)
            parent = roles[parent].get('parentRole')
    return roles


ROLES = json.loads((ROOT / 'roles.json').read_text(encoding='utf-8'))
validate_roles(ROLES)
NAMES = {name: role['workspace'] for name, role in ROLES.items()}
LAUNCH_ROLES = tuple(name for name, role in ROLES.items() if role['backend'] != 'reviewer')
HOME_ROLES = tuple(name for name, role in ROLES.items() if role['activation'] == 'home')


def home_role(role):
    """An on-demand specialist uses an existing entry, never a required extra home."""
    return ROLES[role]['homeRole']


def workspace_root(role):
    return Path(ROLES[role]['workspaceRoot']).expanduser().absolute()


def role_routing(role):
    return {key: ROLES[role][key] for key in ('layer', 'parentRole', 'consultation', 'activation', 'homeRole', 'entrypoint') if key in ROLES[role]}


def find_workspace(role, snapshot, required=True):
    """Resolve the declared role home, preserving old titles and existing history."""
    if snapshot.get('truncated') or 'local' in snapshot.get('hostScope', {}).get('omittedHostIds', []):
        raise RuntimeError('Incomplete Orca workspace inventory; no changes made')
    names = {NAMES[role], *ROLES[role].get('workspaceAliases', [])}
    root = str(workspace_root(role))
    matches = [w for w in snapshot['worktrees']
               if w.get('path') == root and w.get('displayName') in names
               and not w.get('isArchived') and w.get('hostId', 'local') == 'local']
    if len(matches) > 1:
        raise RuntimeError('Ambiguous workspace: ' + role + '; no changes made')
    if not matches and required:
        raise RuntimeError('Missing role home: ' + role + ' at ' + root)
    return matches[0] if matches else None


def skill_root(role):
    location = ROLES[role]['skill']
    return (Path(location).expanduser() if location.startswith('~/') else ROOT / location).resolve()


def orca_command():
    selected = os.environ.get('ORCA_CLI_COMMAND') or (
        'orca-dev' if os.environ.get('ORCA_DEV_REPO_ROOT') else
        'orca-ide' if sys.platform.startswith('linux') else 'orca')
    executable = shutil.which(selected)
    # Never fall through to a different build when the selected one is unavailable.
    return str(Path(executable).absolute()) if executable else selected


def local_orca_only():
    if os.environ.get('ORCA_ENVIRONMENT') or os.environ.get('ORCA_PAIRING_CODE'):
        raise ValueError('この role はローカル配線。remote 環境指定のある shell からは起動しない')
