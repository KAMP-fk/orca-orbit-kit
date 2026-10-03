"""Shared role routing and the version-matched Orca executable selection."""
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
ROLES = json.loads((ROOT / 'roles.json').read_text(encoding='utf-8'))
NAMES = {name: role['workspace'] for name, role in ROLES.items()}
LAUNCH_ROLES = tuple(name for name, role in ROLES.items() if role['backend'] != 'reviewer')


def workspace_root(role):
    return Path(ROLES[role]['workspaceRoot']).expanduser().absolute()


def role_routing(role):
    return {key: ROLES[role][key] for key in ('layer', 'parentRole', 'consultation') if key in ROLES[role]}


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
