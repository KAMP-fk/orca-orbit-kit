"""Acceptance checks for named-role installation and process boundaries.

All launches use fixture executables. No model, Orca service, or live persona is used.
"""
import json
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
LAUNCHER = PACKAGE / 'bin/agent'
INSTALLER = PACKAGE / 'install.py'
ROLES = ('melon', 'kiwi', 'potato')


class NamedAgentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='named-agent-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / 'workspace with spaces'
        self.workspace.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.config = self.root / 'config with spaces'
        self.config.mkdir()
        self.claude_config = self.root / 'claude config with spaces'
        (self.claude_config / 'agents').mkdir(parents=True)
        self.env = os.environ.copy()
        for key in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE', 'ORCA_CLI_COMMAND', 'ORCA_DEV_REPO_ROOT'):
            self.env.pop(key, None)
        # Native config variable points only this fixture process at isolated profiles.
        self.env['CODEX_HOME'] = str(self.config)
        self.env['CLAUDE_CONFIG_DIR'] = str(self.claude_config)
        self.env['PATH'] = str(self.bin) + os.pathsep + self.env.get('PATH', '')
        self.log = self.root / 'fixture-log.json'
        self.env['NAMED_AGENT_FIXTURE_LOG'] = str(self.log)
        self.env['NAMED_AGENT_FIXTURE_EXIT'] = '0'
        for role in ROLES:
            if role == 'potato':
                (self.claude_config / 'agents/potato.md').symlink_to(PACKAGE / 'roles/potato/claude/agent.md')
            else:
                (self.config / (role + '.config.toml')).symlink_to(PACKAGE / 'roles' / role / 'codex/profile.config.toml')
            (self.bin / role).symlink_to(LAUNCHER)
        fixture = """#!/usr/bin/python3
import json, os, shlex, subprocess, sys
from pathlib import Path
Path(os.environ['NAMED_AGENT_FIXTURE_LOG']).write_text(json.dumps({
    'argv': sys.argv, 'cwd': os.getcwd(), 'configHome': os.environ.get('CODEX_HOME'),
    'claudeConfigHome': os.environ.get('CLAUDE_CONFIG_DIR'), 'effort': os.environ.get('CLAUDE_CODE_EFFORT_LEVEL')
}, ensure_ascii=False))
if Path(sys.argv[0]).name == 'claude':
    default_result=json.dumps({'type':'result','is_error':False,'session_id':'fixture-session',
        'modelUsage':{os.environ.get('NAMED_AGENT_FIXTURE_MODEL','claude-opus-5-5'):{}},
        'result':'fixture review result'})
    print(os.environ.get('NAMED_AGENT_FIXTURE_RESULT',default_result))
elif Path(sys.argv[0]).name == 'orca-fixture' and os.environ.get('NAMED_AGENT_FIXTURE_TERMINAL_CWD'):
    command = shlex.split(sys.argv[sys.argv.index('--command') + 1])
    raise SystemExit(subprocess.run(command, cwd=os.environ['NAMED_AGENT_FIXTURE_TERMINAL_CWD']).returncode)
else:
    print(json.dumps({'fixture': True}))
raise SystemExit(int(os.environ.get('NAMED_AGENT_FIXTURE_EXIT', '0')))
"""
        for name in ('codex', 'claude', 'orca-fixture'):
            executable = self.bin / name
            executable.write_text(fixture)
            executable.chmod(0o755)

    def launch(self, role, *args, generic=False, env=None, cwd=None):
        entry = [str(LAUNCHER), role] if generic else [str(self.bin / role)]
        return subprocess.run([sys.executable] + entry + list(args),
                              cwd=str(cwd or self.workspace), env=env or self.env,
                              text=True, capture_output=True, timeout=15)

    def preview(self, role, *args, **kwargs):
        result = self.launch(role, '--dry-run', *args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists(), 'dry-run invoked a backend')
        return json.loads(result.stdout)

    def install(self, target, *args):
        return subprocess.run([sys.executable, str(INSTALLER), '--home', str(target)] + list(args),
                              env=self.env, text=True, capture_output=True, timeout=15)

    def terminal_command(self, argv):
        wrapper = shlex.split(argv[argv.index('--command') + 1])
        self.assertEqual(wrapper[:2], ['/bin/sh', '-c'])
        self.assertEqual(len(wrapper), 3)
        command = shlex.split(wrapper[2])
        self.assertEqual(command[:4], ['cd', str(self.workspace), '&&', 'exec'])
        return command[4:]

    def test_all_aliases_select_their_profile_and_role(self):
        for role in ROLES:
            with self.subTest(role=role):
                preview = self.preview(role, '確認対象')
                self.assertEqual(preview['role'], role)
                self.assertEqual(preview['displayName'], role.capitalize())
                self.assertEqual(preview['profile'], str(self.claude_config / 'agents/potato.md') if role == 'potato' else str(self.config / (role + '.config.toml')))
                self.assertEqual(preview['requestedEffort'], 'high' if role == 'potato' else 'medium')
                argv = preview['argv']
                self.assertTrue(argv[-1].endswith('今回の依頼:\n確認対象'))
                if role == 'potato':
                    self.assertEqual(preview['backend'], 'claude')
                    self.assertEqual(argv[argv.index('--model') + 1], 'claude-opus-5-5')
                    self.assertEqual(argv[argv.index('--effort') + 1], 'high')
                    self.assertIn('--restricted', argv)
                    self.assertIn('--disable-slash-commands', argv)
                    self.assertTrue(json.loads(Path(argv[argv.index('--settings') + 1]).read_text())['disableAllHooks'])
                    self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep')
                    self.assertIn('--strict-mcp-config', argv)
                    self.assertEqual(json.loads(argv[argv.index('--mcp-config') + 1]), {'mcpServers': {}})
                    self.assertEqual(argv[argv.index('--permission-mode') + 1], 'dontAsk')
                    self.assertEqual(argv[argv.index('--agent') + 1], 'potato')
                    definition = json.loads(argv[argv.index('--agents') + 1])['potato']
                    self.assertEqual(definition['model'], 'claude-opus-5-5')
                    self.assertEqual(definition['effort'], 'high')
                    self.assertEqual(definition['tools'], ['Read', 'Glob', 'Grep'])
                    self.assertEqual(definition['permissionMode'], 'dontAsk')
                    self.assertEqual(definition['prompt'],
                                     (PACKAGE / 'roles/potato/skill/SKILL.md').read_text().split('\n---\n', 1)[-1].strip())
                    self.assertNotIn('--fallback-model', argv)
                else:
                    self.assertEqual(argv[argv.index('-p') + 1], role)

    def test_generic_entry_accepts_options_between_role_and_request(self):
        preview = self.preview('Potato', '--cwd', str(self.workspace), '差分を確認', generic=True)
        self.assertEqual(preview['role'], 'potato')
        self.assertEqual(preview['cwd'], str(self.workspace))
        self.assertTrue(preview['argv'][-1].endswith('差分を確認'))

    def test_explicit_model_and_effort_are_preserved(self):
        preview = self.preview('melon', '--model', 'chosen-model', '--effort', 'high', '調査')
        argv = preview['argv']
        self.assertEqual(argv[argv.index('-m') + 1], 'chosen-model')
        self.assertEqual(argv[argv.index('-c') + 1], 'model_reasoning_effort="high"')

    def test_idle_interactive_role_does_not_invent_a_request(self):
        preview = self.preview('kiwi')
        self.assertEqual(preview['mode'], 'interactive')
        self.assertNotIn('--', preview['argv'])
        self.assertNotIn('exec', preview['argv'])

    def test_batch_backend_receives_one_literal_prompt_and_propagates_status(self):
        marker = self.root / 'should-not-exist'
        request = '引用 " \' ; $(touch ' + str(marker) + ') `touch ' + str(marker) + '`\n日本語 / $HOME'
        self.env['NAMED_AGENT_FIXTURE_EXIT'] = '7'
        result = self.launch('potato', '--batch-worker', request)
        self.assertEqual(result.returncode, 7, result.stderr)
        log = json.loads(self.log.read_text())
        argv = log['argv']
        self.assertIn('--print', argv)
        self.assertEqual(argv[argv.index('--permission-prompts') + 1], 'none')
        self.assertEqual(argv[-2], '--')
        self.assertTrue(argv[-1].endswith('今回の依頼:\n' + request))
        self.assertEqual(argv[argv.index('--model') + 1], 'claude-opus-5-5')
        self.assertEqual(argv[argv.index('--effort') + 1], 'high')
        self.assertEqual(log['cwd'], str(self.workspace))
        self.assertEqual(log['claudeConfigHome'], str(self.claude_config))
        self.assertEqual(log['effort'], 'high')
        self.assertFalse(marker.exists())

    def test_invalid_requests_do_not_start_a_backend(self):
        cases = [('--batch-worker',), ('--batch-worker', '  '), ('--cwd', str(self.root / 'missing')),
                 ('--model', ''), ('--model=--invalid',), ('--worktree', 'path:' + str(self.workspace)),
                 ('--exec', '--orca', 'request')]
        for args in cases:
            with self.subTest(args=args):
                result = self.launch('melon', *args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_wrong_profile_link_is_rejected_before_launch(self):
        profile = self.config / 'melon.config.toml'
        profile.unlink()
        profile.symlink_to(PACKAGE / 'roles/kiwi/codex/profile.config.toml')
        result = self.launch('melon', 'request')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_potato_batch_publishes_only_verified_model_metadata(self):
        for model in ('claude-opus-5-5', 'claude-opus-5-5[1m]'):
            with self.subTest(model=model):
                self.env['NAMED_AGENT_FIXTURE_MODEL'] = model
                result = self.launch('potato', '--batch-worker', '--json', 'review request')
                self.assertEqual(result.returncode, 0, result.stderr)
                metadata = json.loads(result.stdout)
                self.assertEqual(list(metadata['modelUsage']), [model])
                self.assertEqual(metadata['result'], 'fixture review result')

    def test_potato_rejects_other_actual_models_without_publishing_review(self):
        for model in ('claude-opus-4-6', 'claude-opus-5', 'claude-sonnet-5-5'):
            with self.subTest(model=model):
                self.env['NAMED_AGENT_FIXTURE_MODEL'] = model
                result = self.launch('potato', '--batch-worker', 'review request')
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertIn('BLOCKED', result.stderr)

    def test_potato_rejects_unknown_error_and_mixed_model_results(self):
        valid = {'type':'result', 'is_error':False, 'session_id':'fixture-session',
                 'modelUsage':{'claude-opus-5-5':{}}, 'result':'must not publish'}
        cases = ['not JSON', json.dumps({}), json.dumps({**valid, 'session_id':''}),
                 json.dumps({**valid, 'is_error':True}),
                 json.dumps({**valid, 'modelUsage':{'claude-opus-5-5':{}, 'claude-opus-5':{}}})]
        for raw in cases:
            with self.subTest(raw=raw):
                self.env['NAMED_AGENT_FIXTURE_RESULT'] = raw
                result = self.launch('potato', '--batch-worker', '--json', 'review request')
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertEqual(result.stdout, '')

    def test_potato_rejects_model_or_effort_downgrade_before_start(self):
        for args in (('--model','opus'), ('--model','claude-opus-5'), ('--effort','medium')):
            with self.subTest(args=args):
                result = self.launch('potato', *args, 'review request')
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_potato_fixes_relative_claude_config_before_cwd_change(self):
        env = self.env.copy()
        env['CLAUDE_CONFIG_DIR'] = self.claude_config.name
        result = self.launch('potato', '--batch-worker', '--cwd', str(self.workspace), 'review request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertEqual(log['claudeConfigHome'], str(self.claude_config))
        self.assertEqual(log['cwd'], str(self.workspace))

    def test_potato_rejects_inconsistent_settings_before_backend_start(self):
        loader = importlib.machinery.SourceFileLoader('named_launcher_settings_gate', str(LAUNCHER))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        settings_path = PACKAGE / 'roles/potato/claude/settings.json'
        policy = json.loads(settings_path.read_text())
        native_read = Path.read_text
        cases = [
            {**policy, 'model': 'claude-sonnet-5'},
            {**policy, 'effortLevel': 'medium'},
            {**policy, 'disableAllHooks': False},
            {key: value for key, value in policy.items() if key != 'disableAllHooks'},
            {**policy, 'permissions': {**policy['permissions'], 'disableBypassPermissionsMode': 'enable'}},
        ]
        for candidate in cases:
            def read(path, *args, **kwargs):
                return json.dumps(candidate) if path == settings_path else native_read(path, *args, **kwargs)
            with self.subTest(candidate=candidate), mock.patch.dict(os.environ, self.env, clear=True), \
                 mock.patch.object(sys, 'argv', [str(self.bin / 'potato'), '--batch-worker', '--cwd', str(self.workspace), 'review']), \
                 mock.patch.object(launcher.Path, 'read_text', autospec=True, side_effect=read), \
                 mock.patch.object(launcher.subprocess, 'run') as backend, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                launcher.main()
            self.assertEqual(stopped.exception.code, 2)
            backend.assert_not_called()

    def test_potato_preserves_native_default_global_config_location(self):
        loader = importlib.machinery.SourceFileLoader('named_launcher_default_config', str(LAUNCHER))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        native_home = self.root / 'native-home'
        native_agents = native_home / '.claude/agents'
        native_agents.mkdir(parents=True)
        (native_agents / 'potato.md').symlink_to(PACKAGE / 'roles/potato/claude/agent.md')
        env = self.env.copy()
        env.pop('CLAUDE_CONFIG_DIR')
        valid_result = json.dumps({'type': 'result', 'is_error': False, 'session_id': 'fixture-native',
                                   'modelUsage': {'claude-opus-5-5': {}}, 'result': 'verified'})
        backend_result = subprocess.CompletedProcess([], 0, valid_result, '')
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(launcher.Path, 'home', return_value=native_home), \
             mock.patch.object(sys, 'argv', [str(self.bin / 'potato'), '--batch-worker', 'check']), \
             mock.patch.object(launcher.os, 'chdir'), \
             mock.patch.object(launcher.subprocess, 'run', return_value=backend_result) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(), 0)
        child_environment = run.call_args.kwargs['env']
        self.assertNotIn('CLAUDE_CONFIG_DIR', child_environment)
        self.assertEqual(child_environment['CLAUDE_CODE_EFFORT_LEVEL'], 'high')

    def test_orca_worktree_path_drives_both_targets(self):
        preview = self.preview('kiwi', '--orca', '--interactive', '--worktree', 'path:' + str(self.workspace), cwd=self.root)
        self.assertEqual(preview['cwd'], str(self.workspace))
        argv = preview['argv']
        self.assertEqual(argv[argv.index('--worktree') + 1], 'path:' + str(self.workspace))
        nested = self.terminal_command(argv)
        self.assertEqual(nested[nested.index('-C') + 1], str(self.workspace))
        self.assertEqual(nested[:2], ['/usr/bin/env', 'CODEX_HOME=' + str(self.config)])

    def test_orca_rejects_ambiguous_or_mismatched_target(self):
        cases = [('active',), ('path:relative',), ('path:',)]
        for (selector,) in cases:
            with self.subTest(selector=selector):
                result = self.launch('melon', '--orca', '--interactive', '--worktree', selector)
                self.assertEqual(result.returncode, 2)
        result = self.launch('melon', '--orca', '--interactive', '--worktree', 'path:' + str(self.root),
                             '--cwd', str(self.workspace))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_orca_backend_command_preserves_prompt_and_exit_status(self):
        self.env['ORCA_CLI_COMMAND'] = str(self.bin / 'orca-fixture')
        self.env['NAMED_AGENT_FIXTURE_EXIT'] = '8'
        request = '"引用" $variable ; $(not-a-command)\n引継ぎ'
        result = self.launch('potato', '--orca', '--interactive', request)
        self.assertEqual(result.returncode, 8, result.stderr)
        log = json.loads(self.log.read_text())
        argv = log['argv']
        self.assertEqual(argv[1:3], ['terminal', 'create'])
        self.assertEqual(argv[argv.index('--title') + 1], 'Potato')
        self.assertEqual(argv[argv.index('--worktree') + 1], 'path:' + str(self.workspace))
        nested = self.terminal_command(argv)
        self.assertEqual(nested[0], '/usr/bin/env')
        self.assertEqual(dict(item.split('=', 1) for item in nested[1:3]),
                         {'CLAUDE_CONFIG_DIR': str(self.claude_config), 'CLAUDE_CODE_EFFORT_LEVEL': 'high'})
        self.assertEqual(nested[nested.index('--model') + 1], 'claude-opus-5-5')
        self.assertEqual(nested[nested.index('--effort') + 1], 'high')
        self.assertIn('--restricted', nested)
        self.assertEqual(nested[-2], '--')
        self.assertTrue(nested[-1].endswith('今回の依頼:\n' + request))

    def test_orca_potato_changes_to_target_before_claude_starts(self):
        self.env['ORCA_CLI_COMMAND'] = str(self.bin / 'orca-fixture')
        self.env['NAMED_AGENT_FIXTURE_TERMINAL_CWD'] = str(self.root)
        request = '空白 "引用" ; $(not-a-command)\n対象固定'
        result = self.launch('potato', '--orca', '--interactive', '--worktree', 'path:' + str(self.workspace), request)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertEqual(Path(log['argv'][0]).name, 'claude')
        self.assertEqual(log['cwd'], str(self.workspace))
        self.assertEqual(log['effort'], 'high')
        self.assertTrue(log['argv'][-1].endswith('今回の依頼:\n' + request))

    def test_remote_orca_context_is_rejected(self):
        for key in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE'):
            with self.subTest(key=key):
                env = self.env.copy()
                env[key] = 'fixture-remote-context'
                result = self.launch('kiwi', '--orca', '--interactive', 'request', env=env)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_relative_config_path_is_fixed_before_direct_cwd_change(self):
        env = self.env.copy()
        env['CODEX_HOME'] = self.config.name
        result = self.launch('melon', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertEqual(log['configHome'], str(self.config))
        self.assertEqual(log['cwd'], str(self.workspace))

    def test_relative_config_path_is_fixed_for_new_orca_shell(self):
        env = self.env.copy()
        env['CODEX_HOME'] = self.config.name
        preview = self.preview('melon', '--orca', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        nested = self.terminal_command(preview['argv'])
        self.assertEqual(nested[1], 'CODEX_HOME=' + str(self.config))

    def test_relative_backend_paths_are_fixed_before_workspace_change(self):
        env = self.env.copy()
        env['PATH'] = 'bin:/usr/bin:/bin'
        result = self.launch('melon', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.log.read_text())['argv'][0], str(self.bin / 'codex'))
        self.log.unlink()
        env['ORCA_CLI_COMMAND'] = 'bin/orca-fixture'
        result = self.launch('melon', '--orca', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertEqual(log['argv'][0], str(self.bin / 'orca-fixture'))
        nested = self.terminal_command(log['argv'])
        self.assertEqual(nested[2], str(self.bin / 'codex'))

    def test_install_is_idempotent_and_owned_uninstall_cleans_all_nine_links(self):
        target = self.root / 'isolated-home'
        for _ in range(2):
            result = self.install(target)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.install(target, '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 9)
        for role in ROLES:
            self.assertEqual((target / '.local/bin' / role).resolve(), LAUNCHER)
            self.assertEqual((target / '.agents/skills' / role).resolve(), PACKAGE / 'roles' / role / 'skill')
            if role == 'potato':
                self.assertEqual((target / '.claude/agents/potato.md').resolve(), PACKAGE / 'roles/potato/claude/agent.md')
                self.assertFalse(os.path.lexists(target / '.codex/potato.config.toml'))
            else:
                self.assertEqual((target / '.codex' / (role + '.config.toml')).resolve(),
                                 PACKAGE / 'roles' / role / 'codex/profile.config.toml')
        self.assertEqual(self.install(target, '--uninstall').returncode, 0)
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 0)
        self.assertEqual(self.install(target, '--check').returncode, 1)

    def test_install_collision_preserves_file_before_any_links_are_created(self):
        target = self.root / 'isolated-home'
        conflict = target / '.local/bin/kiwi'
        conflict.parent.mkdir(parents=True)
        conflict.write_text('existing command')
        result = self.install(target)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(conflict.read_text(), 'existing command')
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 0)

    def test_install_retires_only_owned_old_codex_review_profile(self):
        target = self.root / 'isolated-home'
        legacy = target / '.codex/potato.config.toml'
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(PACKAGE / 'roles/potato/codex/profile.config.toml')
        result = self.install(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(legacy))
        self.assertTrue((target / '.claude/agents/potato.md').is_symlink())
        self.assertEqual(self.install(target, '--check').returncode, 0)

    def test_install_preserves_foreign_old_review_profile_before_mutation(self):
        target = self.root / 'isolated-home'
        legacy = target / '.codex/potato.config.toml'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('foreign review profile')
        result = self.install(target)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(legacy.read_text(), 'foreign review profile')
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 0)

    def test_install_collision_preserves_dangling_foreign_symlink(self):
        target = self.root / 'isolated-home'
        conflict = target / '.agents/skills/potato'
        conflict.parent.mkdir(parents=True)
        conflict.symlink_to(self.root / 'does-not-exist')
        result = self.install(target)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(os.readlink(conflict), str(self.root / 'does-not-exist'))
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 1)

    def test_uninstall_preserves_foreign_replacement(self):
        target = self.root / 'isolated-home'
        self.assertEqual(self.install(target).returncode, 0)
        command = target / '.local/bin/kiwi'
        command.unlink()
        command.write_text('replacement command')
        self.assertEqual(self.install(target, '--uninstall').returncode, 0)
        self.assertEqual(command.read_text(), 'replacement command')
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 0)


if __name__ == '__main__':
    unittest.main()
