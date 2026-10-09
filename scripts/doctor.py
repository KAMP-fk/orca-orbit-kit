#!/usr/bin/env python3
"""Check source layout and installed tools; never log in or launch agents."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
required = ['git', 'python3', 'bash', 'jq', 'node', 'pnpm', 'orca']
tools = {name: bool(shutil.which(name)) for name in required}
sources = {name: (root / name).is_file() for name in
           ['agents/team/install.py', 'agents/team/roles/tomato/skill/SKILL.md',
            'apps/orbit/package.json', 'apps/orbit/pnpm-lock.yaml']}
modules = subprocess.run(['git', '-C', str(root), 'submodule', 'status'],
                         capture_output=True, text=True)
ready = modules.returncode == 0 and not any(
    line.startswith(('-', '+', 'U')) for line in modules.stdout.splitlines())
print(json.dumps({'tools': tools, 'source_layout': sources,
                  'submodules_at_recorded_sha': ready,
                  'optional': {name: bool(shutil.which(name)) for name in
                               ['tailscale', 'gh', 'codex', 'claude']},
                  'authentication': 'Not checked; log in through each official client.',
                  'machine_config': 'Real .env, auth and state must remain outside Git.'},
                 ensure_ascii=False, indent=2))
sys.exit(0 if all(tools.values()) and all(sources.values()) and ready else 1)
