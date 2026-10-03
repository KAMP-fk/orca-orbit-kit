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
