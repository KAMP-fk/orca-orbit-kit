#!/usr/bin/env python3
"""Inspect Git's actual index or reachable history without printing secret values.

This bounded pattern scan is a publication check, not a proof that no secret exists.
Run separately in every source repository, including submodules.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

PATTERNS = {
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=\r\n]{80,}'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{70,})\b'),
    'provider-token': re.compile(rb'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}|xox[baprs]-[A-Za-z0-9-]{20,}|tskey-(?:auth|api)-[A-Za-z0-9-]{20,})\b'),
    'aws-access-id': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-url': re.compile(rb'https?://[^\s/:@]{1,100}:[^\s/@]{8,100}@'),
}
FORBIDDEN = {'state', 'logs', 'log', 'node_modules', 'dist', 'artifacts', 'test-results', '.codex', '.claude', 'secrets'}
ALLOWED_SUBMODULES = {'apps/orbit', 'agents/team/roles/tomato/skill'}


def git(root, *args):
    env = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}
    return subprocess.check_output(['git', '-C', str(root), *args], env=env)


def findings(data):
    return [{'kind': name, 'line': data[:match.start()].count(b'\n') + 1,
             'fingerprint': hashlib.sha256(match.group()).hexdigest()[:16]}
            for name, pattern in PATTERNS.items() for match in pattern.finditer(data)]


def scan(root, history=False):
    results = []
    checked = 0
    if history:
        objects = git(root, 'rev-list', '--objects', 'HEAD').decode().splitlines()
        for row in objects:
            oid = row.split(' ', 1)[0]
            if git(root, 'cat-file', '-t', oid).strip() != b'blob':
                continue
            data = git(root, 'cat-file', 'blob', oid)
            checked += 1
            for result in findings(data):
                results.append(dict(result, object=oid))
    else:
        for entry in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
            if not entry:
                continue
            metadata, relative = entry.split(b'\t', 1)
            mode, oid, stage = metadata.decode().split()
            name = relative.decode()
            if stage != '0':
                results.append({'path': name, 'kind': 'unmerged-index'})
                continue
            if mode == '160000':
                if name not in ALLOWED_SUBMODULES:
                    results.append({'path': name, 'kind': 'unexpected-gitlink'})
                continue
            parts = PurePosixPath(name).parts
            base = parts[-1]
            if (any(p in FORBIDDEN for p in parts) or
                (base.startswith('.env') and base != '.env.example') or
                base.startswith('.state') or base == 'auth.json' or
                base.endswith(('.pem', '.key', '.token', '.p12', '.pfx', '.log'))):
                results.append({'path': name, 'kind': 'private-runtime-path'})
            data = git(root, 'cat-file', 'blob', oid)
            checked += 1
            if mode == '120000':
                link = Path(data.decode())
                target = root / Path(name).parent / link
                if link.is_absolute() or not target.resolve().is_relative_to(root.resolve()):
                    results.append({'path': name, 'kind': 'external-symlink'})
            for result in findings(data):
                results.append(dict(result, path=name))
    return {'scope': 'HEAD-history' if history else 'Git-index', 'checked': checked,
            'findings': results, 'limitations': 'Pattern coverage only; unknown secret formats and provenance require manual review.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--history', action='store_true')
    options = parser.parse_args()
    result = scan(options.repo.resolve(), options.history)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result['findings'] else 0)
