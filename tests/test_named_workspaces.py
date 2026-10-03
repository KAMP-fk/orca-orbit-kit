"""Regressions for existing role homes; no live runtime or model calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
spec = importlib.util.spec_from_file_location('workspace_contract', PACKAGE / 'lib/role_contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class WorkspaceTests(unittest.TestCase):
    def snapshot(self):
        return {'truncated': False, 'hostScope': {'hostIds': ['local'], 'omittedHostIds': []},
                'worktrees': [{'id': role + '-existing', 'hostId': 'local',
                               'path': str(contract.workspace_root(role)),
                               'displayName': value.get('workspaceAliases', [value['workspace']])[0]}
                              for role, value in contract.ROLES.items()]}

    def test_old_titles_select_original_brain_and_reviewer_homes(self):
        snapshot = self.snapshot()
        for role in ('tomato', 'banana', 'peach'):
            self.assertEqual(contract.find_workspace(role, snapshot)['id'], role + '-existing')

    def test_same_role_name_in_another_project_does_not_change_the_home(self):
        snapshot = self.snapshot()
        for role, value in contract.ROLES.items():
            snapshot['worktrees'].append({'id': role + '-other-project', 'path': '/other/project',
                                          'displayName': value['workspace']})
            self.assertEqual(contract.find_workspace(role, snapshot)['id'], role + '-existing')

    def test_archived_or_remote_card_does_not_replace_a_missing_local_home(self):
        for field, value in [('isArchived', True), ('hostId', 'remote')]:
            snapshot = self.snapshot()
            snapshot['worktrees'][0][field] = value
            with self.assertRaisesRegex(RuntimeError, 'Missing role home'):
                contract.find_workspace('tomato', snapshot)

    def test_duplicate_titles_inside_the_same_home_are_ambiguous(self):
        snapshot = self.snapshot()
        snapshot['worktrees'].append(dict(snapshot['worktrees'][0], id='duplicate',
                                          displayName=contract.NAMES['tomato']))
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous workspace'):
            contract.find_workspace('tomato', snapshot)

    def test_incomplete_inventory_never_means_a_missing_role(self):
        for update in [{'truncated': True}, {'hostScope': {'omittedHostIds': ['local']}}]:
            snapshot = dict(self.snapshot(), **update)
            with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
                contract.find_workspace('tomato', snapshot, required=False)

    def startup(self, snapshot, *args):
        with tempfile.TemporaryDirectory(prefix='role-workspaces-') as directory:
            root = Path(directory)
            fixture = root / 'orca'
            data = root / 'snapshot.json'
            calls = root / 'calls.jsonl'
            data.write_text(json.dumps(snapshot))
            fixture.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
a = sys.argv[1:]
with Path(os.environ['FIXTURE_CALLS']).open('a') as f: f.write(json.dumps(a)+'\\n')
if a[:2] == ['worktree','list']: result = json.loads(Path(os.environ['FIXTURE_SNAPSHOT']).read_text())
elif a[:2] == ['terminal','list']: result = {'terminals': []}
else: sys.exit('Unexpected mutation: '+repr(a))
print(json.dumps({'ok':True,'result':result}))
""")
            fixture.chmod(0o755)
            env = {k:v for k,v in os.environ.items() if k not in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE')}
            env.update(ORCA_CLI_COMMAND=str(fixture), FIXTURE_CALLS=str(calls), FIXTURE_SNAPSHOT=str(data))
            result = subprocess.run([str(PACKAGE / 'bin/start-workspaces'), *args],
                                    env=env, capture_output=True, text=True, timeout=10)
            return result, [json.loads(line) for line in calls.read_text().splitlines()]

    def test_status_reuses_all_existing_homes_without_creating_cards(self):
        result, calls = self.startup(self.snapshot(), '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({json.loads(line)['worktreeId'] for line in result.stdout.splitlines()},
                         {role + '-existing' for role in contract.ROLES})
        self.assertEqual(calls[0][:2], ['worktree', 'list'])
        self.assertEqual(len(calls), 7)
        self.assertTrue(all(call[:2] == ['terminal', 'list'] for call in calls[1:]))

    def test_missing_brain_home_blocks_setup_instead_of_creating_a_skills_card(self):
        snapshot = self.snapshot()
        snapshot['worktrees'][0]['path'] = str(Path.home() / '.agents/skills')
        result, calls = self.startup(snapshot, 'tomato')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing role home', result.stderr)
        self.assertEqual([call[:2] for call in calls], [['worktree','list']])

    def test_duplicate_home_blocks_before_setup_or_runtime_mutations(self):
        snapshot = self.snapshot()
        snapshot['worktrees'].append(dict(snapshot['worktrees'][0], id='duplicate'))
        result, calls = self.startup(snapshot, 'tomato')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Ambiguous workspace', result.stderr)
        self.assertEqual([call[:2] for call in calls], [['worktree','list']])
