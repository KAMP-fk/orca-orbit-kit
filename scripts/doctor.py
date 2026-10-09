#!/usr/bin/env python3
"""Check source layout and installed tools; never log in or launch agents."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
selected_orca = os.environ.get('ORCA_CLI_COMMAND') or (
    'orca-dev' if os.environ.get('ORCA_DEV_REPO_ROOT') else
    'orca-ide' if sys.platform.startswith('linux') else 'orca')
required = ['git', 'python3', 'bash', 'jq', 'node', 'pnpm', selected_orca]
tools = {name: bool(shutil.which(name)) for name in required}
versions = {'python': sys.version.split()[0]}
compatible = {'python': sys.version_info >= (3, 11)}
for name, arguments in [('node', ['--version']), ('pnpm', ['--version'])]:
    if not tools[name]:
        compatible[name] = False
        continue
    value = subprocess.run([name, *arguments], cwd=root / 'apps/orbit', capture_output=True, text=True,
                           timeout=15)
    versions[name] = value.stdout.strip()
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', versions[name])
    parsed = tuple(int(part) for part in match.groups()) if match else ()
    compatible[name] = value.returncode == 0 and (
        parsed >= (22, 9, 0) if name == 'node' else parsed == (10, 33, 0))
sources = {name: (root / name).is_file() for name in
           ['agents/team/install.py', 'agents/team/roles/tomato/skill/SKILL.md',
            'apps/orbit/package.json', 'apps/orbit/pnpm-lock.yaml']}
modules = subprocess.run(['git', '-C', str(root), 'submodule', 'status'],
                         capture_output=True, text=True,
                         env={k: v for k, v in os.environ.items() if not k.startswith('GIT_')})
ready = modules.returncode == 0 and not any(
    line.startswith(('-', '+', 'U')) for line in modules.stdout.splitlines())
print(json.dumps({'tools': tools, 'versions': versions, 'compatible': compatible,
                  'source_layout': sources,
                  'submodules_at_recorded_sha': ready,
                  'optional': {name: bool(shutil.which(name)) for name in
                               ['tailscale', 'gh', 'codex', 'claude']},
                  'authentication': 'Not checked; log in through each official client.',
                  'machine_config': 'Real .env, auth and state must remain outside Git.'},
                 ensure_ascii=False, indent=2))
sys.exit(0 if all(tools.values()) and all(compatible.values()) and all(sources.values()) and ready else 1)
