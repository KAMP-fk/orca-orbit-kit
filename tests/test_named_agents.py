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

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/team'
LAUNCHER = PACKAGE / 'bin/agent'
INSTALLER = PACKAGE / 'install.py'
ROLES = ('tomato', 'banana', 'review')
PUBLIC_NAMES = {'review': 'potato'}


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
        self.env['NAMED_TEAM_ROLE_CONTRACT'] = str(PACKAGE / 'roles.json')
        self.env['ORCA_CLI_COMMAND'] = str(self.bin / 'orca-fixture')
        self.env['NAMED_TEAM_TASK_DIR'] = str(self.root / 'tasks')
        self.env['NAMED_AGENT_FIXTURE_EXIT'] = '0'
        for role in ROLES:
            public = PUBLIC_NAMES.get(role, role)
            if role in ('tomato', 'review'):
                profile = PACKAGE / ('roles/tomato/claude/settings.json' if role == 'tomato'
                                     else 'roles/potato/acceptance/claude/settings.json')
                installed = self.claude_config / 'named-team' / (public + '.settings.json')
                installed.parent.mkdir(exist_ok=True)
            else:
                profile = PACKAGE / 'roles' / public / 'codex/profile.config.toml'
                installed = self.config / (public + '.config.toml')
            installed.symlink_to(profile)
            if public != role and role not in ('tomato', 'review'):
                (self.config / (role + '.config.toml')).symlink_to(profile)
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
                self.assertEqual(preview['backend'], 'codex' if role == 'banana' else 'claude')
                public = PUBLIC_NAMES.get(role, role)
                expected_profile = self.config / (public + '.config.toml') if role == 'banana' else self.claude_config / 'named-team' / (public + '.settings.json')
                self.assertEqual(preview['profile'], str(expected_profile))
                self.assertEqual(preview['displayName'], public.capitalize())
                self.assertEqual(preview['requestedEffort'], 'high' if role == 'review' else 'medium')
                self.assertTrue(preview['argv'][-1].endswith('今回の依頼:\n確認対象'))
                if role != 'banana':
                    model = 'fable' if role == 'tomato' else 'claude-opus-5-5'
                    self.assertEqual(preview['requestedModel'], model)
                    self.assertEqual(preview['argv'][preview['argv'].index('--model') + 1], model)
                    self.assertIn('--print', preview['argv'])
                else:
                    self.assertEqual(preview['argv'][preview['argv'].index('-p') + 1], public)
                if role == 'review':
                    self.assertIn('--restricted', preview['argv'])
                    self.assertIn('--disable-slash-commands', preview['argv'])
                    self.assertEqual(preview['argv'][preview['argv'].index('--tools') + 1], 'Read,Glob,Grep')
                    self.assertNotIn('--fallback-model', preview['argv'])
                    definition = json.loads(preview['argv'][preview['argv'].index('--agents') + 1])['potato']
                    self.assertEqual(definition['model'], 'claude-opus-5-5')
                    self.assertEqual(definition['effort'], 'high')


    def test_generic_entry_accepts_options_between_role_and_request(self):
        preview = self.preview('Banana', '--cwd', str(self.workspace), '差分を確認', generic=True)
        self.assertEqual(preview['role'], 'banana')


    def test_prompt_file_preserves_literal_multiline_input_without_shell_expansion(self):
        marker = self.root / 'must-not-be-created'
        content = '引用 " ; $(touch ' + str(marker) + ') `touch ' + str(marker) + '`\n$HOME\n'
        request = self.root / 'request with spaces.md'
        request.write_text(content, encoding='utf-8')
        result = self.launch('banana', '--interactive', '--prompt-file', str(request))
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertTrue(log['argv'][-1].endswith('今回の依頼:\n' + content))
        self.assertFalse(marker.exists())

    def test_bad_prompt_file_stops_before_backend_or_orca(self):
        request = self.root / 'empty.md'
        request.write_text('  \n')
        cases = [('--prompt-file', str(self.root / 'missing.md')),
                 ('--prompt-file', str(request)),
                 ('--prompt-file', str(request), 'second request')]
        for args in cases:
            with self.subTest(args=args):
                result = self.launch('tomato', *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.log.exists())

    def test_explicit_model_and_effort_are_preserved(self):
        preview = self.preview('banana', '--model', 'chosen-model', '--effort', 'high', '調査')
        argv = preview['argv']
        self.assertEqual(argv[argv.index('-m') + 1], 'chosen-model')
        self.assertEqual(argv[argv.index('-c') + 1], 'model_reasoning_effort="high"')

    def test_idle_interactive_role_does_not_invent_a_request(self):
        preview = self.preview('banana')
        self.assertEqual(preview['mode'], 'interactive')
        self.assertNotIn('--', preview['argv'])
        self.assertNotIn('exec', preview['argv'])

    def test_batch_backend_receives_one_literal_prompt_and_propagates_status(self):
        marker = self.root / 'should-not-exist'
        request = '$(touch ' + str(marker) + ') `touch ' + str(marker) + '`\n日本語 / $HOME'
        self.env['NAMED_AGENT_FIXTURE_EXIT'] = '7'
        result = self.launch('banana', '--batch-worker', request)
        self.assertEqual(result.returncode, 7, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertIn('exec', log['argv'])
        self.assertTrue(log['argv'][-1].endswith('今回の依頼:\n' + request))
        self.assertEqual(log['cwd'], str(self.workspace))
        self.assertEqual(log['configHome'], str(self.config))
        self.assertFalse(marker.exists())


    def test_invalid_requests_do_not_start_a_backend(self):
        cases = [('--batch-worker',), ('--batch-worker', '  '), ('--cwd', str(self.root / 'missing')),
                 ('--model', ''), ('--model=--invalid',), ('--worktree', 'path:' + str(self.workspace)),
                 ('--exec', '--orca', 'request')]
        for args in cases:
            with self.subTest(args=args):
                result = self.launch('banana', *args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_wrong_profile_link_is_rejected_before_launch(self):
        profile = self.config / 'banana.config.toml'
        profile.unlink()
        profile.symlink_to(PACKAGE / 'roles/tomato/codex/profile.config.toml')
        result = self.launch('banana', 'request')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())








    def test_orca_worktree_path_drives_both_targets(self):
        preview = self.preview('banana', '--orca', '--interactive', '--worktree', 'path:' + str(self.workspace), cwd=self.root)
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
                result = self.launch('banana', '--orca', '--interactive', '--worktree', selector)
                self.assertEqual(result.returncode, 2)
        result = self.launch('banana', '--orca', '--interactive', '--worktree', 'path:' + str(self.root),
                             '--cwd', str(self.workspace))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())



    def test_remote_orca_context_is_rejected(self):
        for key in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE'):
            with self.subTest(key=key):
                env = self.env.copy()
                env[key] = 'fixture-remote-context'
                result = self.launch('banana', '--orca', '--interactive', 'request', env=env)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_relative_config_path_is_fixed_before_direct_cwd_change(self):
        env = self.env.copy()
        env['CODEX_HOME'] = self.config.name
        result = self.launch('banana', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertEqual(log['configHome'], str(self.config))
        self.assertEqual(log['cwd'], str(self.workspace))

    def test_relative_config_path_is_fixed_for_new_orca_shell(self):
        env = self.env.copy()
        env['CODEX_HOME'] = self.config.name
        preview = self.preview('banana', '--orca', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        nested = self.terminal_command(preview['argv'])
        self.assertEqual(nested[1], 'CODEX_HOME=' + str(self.config))

    def test_relative_backend_paths_are_fixed_before_workspace_change(self):
        env = self.env.copy()
        env['PATH'] = 'bin:/usr/bin:/bin'
        result = self.launch('banana', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.log.read_text())['argv'][0], str(self.bin / 'codex'))
        self.log.unlink()
        env['ORCA_CLI_COMMAND'] = 'bin/orca-fixture'
        result = self.launch('banana', '--orca', '--interactive', '--cwd', str(self.workspace), 'request', env=env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        log = json.loads(self.log.read_text())
        self.assertEqual(log['argv'][0], str(self.bin / 'orca-fixture'))
        nested = self.terminal_command(log['argv'])
        self.assertEqual(nested[2], str(self.bin / 'codex'))

    def test_install_is_idempotent_and_owned_uninstall_cleans_all_links(self):
        target = self.root / 'isolated-home'
        for _ in range(2):
            result = self.install(target)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.install(target, '--check').returncode, 0)
        for role in ROLES:
            public = PUBLIC_NAMES.get(role, role)
            expected = PACKAGE / ('bin/' + public) if role in ('banana', 'review') else LAUNCHER
            self.assertEqual((target / '.local/bin' / role).resolve(), expected)
            if role in ('tomato', 'review'):
                source = PACKAGE / ('roles/tomato/claude/settings.json' if role == 'tomato'
                                    else 'roles/potato/acceptance/claude/settings.json')
                self.assertEqual((target / '.claude/named-team' / (public + '.settings.json')).resolve(), source)
                self.assertFalse((target / '.codex' / (role + '.config.toml')).exists())
            else:
                self.assertEqual((target / '.codex' / (role + '.config.toml')).resolve(), PACKAGE / 'roles' / public / 'codex/profile.config.toml')
            self.assertTrue((target / '.agents/skills' / public).is_symlink())
        self.assertFalse((target / '.agents/skills/review').exists())
        self.assertEqual((target / '.claude/skills/Banana').resolve(), PACKAGE / 'roles/banana/skill')
        self.assertEqual((target / '.local/share/named-team/entries/potato/README.md').resolve(),
                         PACKAGE / 'roles/potato/entry/README.md')
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 19)
        self.assertEqual((target / '.local/bin/team-mail').resolve(), PACKAGE / 'bin/team-mail')
        self.assertEqual((target / '.local/bin/delivery-flow').resolve(), PACKAGE / 'bin/delivery-flow')
        self.assertEqual(self.install(target, '--uninstall').returncode, 0)
        self.assertFalse([p for p in target.rglob('*') if p.is_symlink()])
        self.assertEqual(self.install(target, '--check').returncode, 1)

    def test_install_repoints_owned_compatibility_paths_to_canonical_sources(self):
        target = self.root / 'layout-migration-home'
        self.assertEqual(self.install(target).returncode, 0)
        alias = self.root / 'old-package'
        alias.symlink_to(PACKAGE, target_is_directory=True)
        command = target / '.local/bin/banana'
        command.unlink()
        command.symlink_to(alias / 'bin/banana')
        self.assertEqual(self.install(target, '--check').returncode, 1)
        self.assertEqual(self.install(target).returncode, 0)
        self.assertEqual(os.readlink(command), str(PACKAGE / 'bin/banana'))
        self.assertEqual(self.install(target, '--check').returncode, 0)


    def test_install_preserves_vendor_devin_cli(self):
        target = self.root / 'isolated-home'
        vendor = self.root / 'vendor-devin'
        vendor.write_text('vendor executable')
        cli = target / '.local/bin/devin'
        cli.parent.mkdir(parents=True)
        cli.symlink_to(vendor)
        result = self.install(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cli.resolve(), vendor)
        self.assertEqual((target / '.local/bin/devin-flow').resolve(), PACKAGE / 'bin/devin')

    def test_install_collision_preserves_file_before_any_links_are_created(self):
        target = self.root / 'isolated-home'
        conflict = target / '.local/bin/kiwi'
        conflict.parent.mkdir(parents=True)
        conflict.write_text('existing command')
        result = self.install(target)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(conflict.read_text(), 'existing command')
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 0)

    def test_install_retires_only_owned_codex_review_profiles_for_opus_pin(self):
        target = self.root / 'isolated-home'
        legacy = target / '.codex/potato.config.toml'
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(PACKAGE / 'roles/potato/codex/profile.config.toml')
        old_alias = legacy.parent / 'review.config.toml'
        old_alias.symlink_to(PACKAGE / 'roles/potato/codex/profile.config.toml')
        self.assertEqual(self.install(target).returncode, 0)
        self.assertFalse(os.path.lexists(legacy))
        self.assertFalse(os.path.lexists(old_alias))
        self.assertEqual((target / '.claude/named-team/potato.settings.json').resolve(),
                         PACKAGE / 'roles/potato/acceptance/claude/settings.json')
        self.assertEqual(self.install(target, '--check').returncode, 0)

    def test_install_migrates_review_skill_without_registering_another_role(self):
        target = self.root / 'rename-home'
        old = target / '.agents/skills/review'
        old.parent.mkdir(parents=True)
        old.symlink_to(PACKAGE / 'roles/review/skill')
        self.assertEqual(self.install(target).returncode, 0)
        self.assertFalse(os.path.lexists(old))
        self.assertEqual((old.parent / 'potato').resolve(), PACKAGE / 'roles/potato/skill')
        self.assertEqual({p.name for p in old.parent.iterdir()}, {'tomato', 'banana', 'potato'})
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
        command = target / '.local/bin/banana'
        command.unlink()
        command.write_text('replacement command')
        self.assertEqual(self.install(target, '--uninstall').returncode, 0)
        self.assertEqual(command.read_text(), 'replacement command')
        self.assertEqual(len([p for p in target.rglob('*') if p.is_symlink()]), 0)


    def test_migration_restores_banana_and_retires_maintenance_links(self):
        target = self.root / 'migration-home'
        retired = [(target / '.local/bin/maintenance', LAUNCHER),
                   (target / '.agents/skills/maintenance', PACKAGE / 'roles/maintenance/skill'),
                   (target / '.codex/maintenance.config.toml', PACKAGE / 'roles/maintenance/codex/profile.config.toml')]
        old_banana = target / '.local/bin/banana'
        old_banana.parent.mkdir(parents=True)
        old_banana.symlink_to(LAUNCHER)
        for path, source in retired:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(source)
        claude_banana = target / '.claude/skills/Banana'
        claude_banana.parent.mkdir(parents=True)
        claude_banana.symlink_to(PACKAGE / 'roles/banana/skill')
        result = self.install(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(not os.path.lexists(path) for path, _ in retired))
        self.assertEqual(old_banana.resolve(), PACKAGE / 'bin/banana')
        self.assertEqual(claude_banana.resolve(), PACKAGE / 'roles/banana/skill')
        self.assertEqual(self.install(target, '--check').returncode, 0)
        self.assertEqual((target / '.local/bin/devin-flow').resolve(), PACKAGE / 'bin/devin')

    def test_foreign_banana_link_blocks_migration_before_any_new_links(self):
        target = self.root / 'foreign-migration-home'
        foreign = target / '.agents/skills/banana'
        foreign.parent.mkdir(parents=True)
        foreign.symlink_to(self.root / 'unknown-skill')
        result = self.install(target)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(foreign.is_symlink())
        self.assertFalse((target / '.local/bin').exists())

    def test_retired_role_names_are_not_launchable_and_review_cannot_change_model(self):
        for role in ('kiwi', 'melon', 'peach', 'maintenance'):
            result = self.launch(role, 'request', generic=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(self.log.exists())
        for options in [('--model', 'another-model'), ('--effort', 'medium')]:
            result = self.launch('review', *options, 'request')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(self.log.exists())

    def test_old_pipeline_installer_migrates_without_recreating_a_named_reviewer(self):
        target = self.root / 'reviewer-migration'
        old = PACKAGE / 'roles/potato/acceptance'
        retired = [(target / '.local/bin/peach', old / 'bin/linear-inreview-reviewer'),
                   (target / '.agents/skills/peach', old / 'skill'),
                   (target / '.codex/peach.config.toml', old / 'codex/profile.config.toml'),
                   (target / '.claude/agents/peach.md', old / 'claude/agent.md'),
                   (target / '.local/bin/linear-inreview-reviewer', old / 'bin/linear-inreview-reviewer')]
        for path, source in retired:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(source)
        for _ in range(2):
            result = subprocess.run(['bash', str(old / 'install.sh'), '--home', str(target)],
                                    env=self.env, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(any(os.path.lexists(path) for path, _ in retired))
            self.assertEqual((target / '.local/bin/review').resolve(), PACKAGE / 'bin/potato')

    def test_review_metadata_validator_keeps_legacy_pipeline_fail_closed(self):
        sys.path.insert(0, str(PACKAGE / 'lib'))
        from task_session import review_result
        valid = dict(type='result', is_error=False, session_id='fixture',
                     modelUsage={'claude-opus-5-5':{}}, result='review result')
        self.assertEqual(review_result(valid)['result'], 'review result')
        for update in [dict(is_error=True), dict(modelUsage={'claude-sonnet-5-5':{}}),
                       dict(modelUsage={'claude-opus-5-5':{}, 'claude-sonnet-5-5':{}}),
                       dict(result=''), dict(session_id='')]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                review_result(dict(valid, **update))

    def test_direct_review_batch_refuses_wrong_actual_model_without_fallback(self):
        self.env['NAMED_AGENT_FIXTURE_MODEL'] = 'claude-sonnet-5-5'
        result = self.launch('review', '--batch-worker', 'fixture review')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('BLOCKED', result.stderr)
        self.assertEqual(json.loads(self.log.read_text())['argv'][0], str(self.bin / 'claude'))

    def test_tomato_fable_interactive_and_read_requests_have_distinct_tool_scope(self):
        interactive = self.preview('tomato')
        argv = interactive['argv']
        self.assertEqual(Path(argv[0]).name, 'claude')
        self.assertEqual(argv[argv.index('--effort') + 1], 'medium')
        self.assertNotIn('--print', argv)
        self.assertNotIn('--', argv)
        self.assertNotIn('--permission-mode', argv)
        self.assertNotIn('--dangerously-skip-permissions', argv)
        readonly = self.preview('tomato', '--read-only', 'read this repository')['argv']
        self.assertEqual(readonly[readonly.index('--tools') + 1], 'Read,Grep,Glob')
        self.assertIn('--strict-mcp-config', readonly)
        self.assertEqual(readonly[readonly.index('--mcp-config') + 1], '{"mcpServers":{}}')

    def test_tomato_rejects_missing_owned_profile_and_other_models_before_start(self):
        for args in [('--model', 'opus', 'request'), ('--effort', 'ultra', 'request')]:
            self.assertEqual(self.launch('tomato', *args).returncode, 2)
            self.assertFalse(self.log.exists())
        (self.claude_config / 'named-team/tomato.settings.json').unlink()
        self.assertEqual(self.launch('tomato', 'request').returncode, 2)
        self.assertFalse(self.log.exists())

    def test_tomato_profile_migration_preserves_global_claude_settings(self):
        target = self.root / 'tomato-migration-home'
        old = target / '.codex/tomato.config.toml'
        old.parent.mkdir(parents=True)
        old.symlink_to(PACKAGE / 'roles/tomato/codex/profile.config.toml')
        settings = target / '.claude/settings.json'
        settings.parent.mkdir()
        original = '{"model":"other-user-model"}\n'
        settings.write_text(original)
        self.assertEqual(self.install(target).returncode, 0)
        self.assertFalse(old.exists())
        self.assertEqual(settings.read_text(), original)
        self.assertEqual(self.install(target, '--check').returncode, 0)

    def test_consultation_validator_rejects_fallback_mixed_models_and_incomplete_results(self):
        sys.path.insert(0, str(PACKAGE / 'lib'))
        from task_session import consultation_result
        valid = dict(type='result', is_error=False, session_id='fixture',
                     modelUsage={'claude-fable-5-1':{}}, result='consultation')
        self.assertEqual(consultation_result(valid), valid)
        for update in [dict(is_error=True), dict(modelUsage={'claude-opus-5-5':{}}),
                       dict(modelUsage={'claude-fable-5-1':{}, 'claude-opus-5-5':{}}),
                       dict(modelUsage={}), dict(result=''), dict(session_id='')]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                consultation_result(dict(valid, **update))


if __name__ == '__main__':
    unittest.main()
