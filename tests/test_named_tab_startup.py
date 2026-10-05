"""Exercise new-tab wiring with isolated profiles and fake model executables."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1] / 'agents/named-team'
HOOK = PACKAGE / 'shell/tab-autostart.zsh'
INSTALLER = PACKAGE / 'install.py'


class TabStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tab-startup-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / 'home with spaces'
        self.home.mkdir()
        self.bin = self.home / '.local/bin'
        self.bin.mkdir(parents=True)
        self.log = self.home / 'launches.jsonl'
        self.env = os.environ.copy()
        for key in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE', 'NAMED_TEAM_TAB_AUTOSTART_HANDLE',
                    'ORCA_SHELL_FEATURES', 'ZDOTDIR'):
            self.env.pop(key, None)
        self.env.update(HOME=str(self.home), CODEX_HOME=str(self.home / '.codex'),
                        CLAUDE_CONFIG_DIR=str(self.home / '.claude'),
                        TERM_PROGRAM='Orca', ORCA_TERMINAL_HANDLE='term_fixture',
                        NAMED_TAB_FIXTURE_LOG=str(self.log))
        self.roles = json.loads((PACKAGE / 'roles.json').read_text())
        self.roots = {role: Path(data['workspaceRoot'].replace('~', str(self.home), 1))
                      for role, data in self.roles.items()}
        for role, root in self.roots.items():
            root.mkdir(parents=True, exist_ok=True)
            if role not in ('peach', 'potato'):
                profile = self.home / '.codex' / (role + '.config.toml')
                profile.parent.mkdir(parents=True, exist_ok=True)
                profile.symlink_to(PACKAGE / 'roles' / role / 'codex/profile.config.toml')
        for role, source in [('potato', PACKAGE / 'roles/potato/claude/agent.md'),
                             ('peach', PACKAGE.parent / 'linear-inreview-reviewer/claude/agent.md')]:
            profile = self.home / '.claude/agents' / (role + '.md')
            profile.parent.mkdir(parents=True, exist_ok=True)
            profile.symlink_to(source)
        tomato_skill = self.home / '.claude/skills/Tomato/SKILL.md'
        tomato_skill.parent.mkdir(parents=True)
        tomato_skill.write_text('---\nname: tomato\n---\nFixture role.\n')
        fixture = '''#!/usr/bin/python3
import json, os, sys
with open(os.environ['NAMED_TAB_FIXTURE_LOG'], 'a') as output:
    output.write(json.dumps({'argv': sys.argv, 'cwd': os.getcwd(),
                            'marker': os.environ.get('NAMED_TEAM_TAB_AUTOSTART_HANDLE')}) + '\\n')
'''
        for backend in ('codex', 'claude'):
            executable = self.bin / backend
            executable.write_text(fixture)
            executable.chmod(0o755)

    def shell(self, role='banana', env=None, cwd=None, options='-flic', before='', after=''):
        selected = (env or self.env).copy()
        path = cwd or self.roots[role]
        selected.setdefault('ORCA_WORKTREE_ID', 'fixture::' + str(path))
        command = before + '\nsource ' + shlex.quote(str(HOOK)) + '\n' + after
        return subprocess.run(['/bin/zsh', '-d', options, command], cwd=str(path), env=selected,
                              text=True, capture_output=True, timeout=15)

    def launches(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def install(self, target, *args):
        return subprocess.run([sys.executable, str(INSTALLER), '--home', str(target), *args],
                              text=True, capture_output=True, timeout=15)

    def test_only_conversation_homes_start_models_and_review_is_model_free(self):
        for role in self.roots:
            with self.subTest(role=role):
                self.log.unlink(missing_ok=True)
                result = self.shell(role)
                self.assertEqual(result.returncode, 0, result.stderr)
                launches = self.launches()
                if role not in ('tomato', 'banana'):
                    self.assertEqual(launches, [], result.stdout + result.stderr)
                    if role == 'peach':
                        self.assertIn('Review｜受入・技術レビュー', result.stdout)
                        self.assertIn('--kind final', result.stdout)
                    continue
                self.assertEqual(len(launches), 1)
                argv = launches[0]['argv']
                self.assertEqual(launches[0]['cwd'], str(self.roots[role]))
                self.assertEqual(launches[0]['marker'], 'term_fixture')
                self.assertNotIn('--', argv, 'an unsolicited prompt was supplied')
                self.assertNotIn('exec', argv)
                self.assertEqual(Path(argv[0]).name, 'codex')
                self.assertEqual(argv[argv.index('-p') + 1], role)
                self.assertIn('model_reasoning_effort="medium"', argv)
                self.assertIn('check_for_update_on_startup=false', argv)

    def test_other_surfaces_shells_and_worktrees_never_start_a_model(self):
        cases = [('other-app', {'TERM_PROGRAM': 'Apple_Terminal'}, None, '-flic'),
                 ('missing-handle', {'ORCA_TERMINAL_HANDLE': ''}, None, '-flic'),
                 ('wrong-worktree', {'ORCA_WORKTREE_ID': 'fixture::/different/path'}, None, '-flic'),
                 ('remote', {'ORCA_ENVIRONMENT': 'remote'}, None, '-flic'),
                 ('noninteractive', {}, None, '-flc'),
                 ('nested-nonlogin-shell', {}, None, '-fic'),
                 ('other-project', {}, self.home, '-flic')]
        subtree = self.roots['kiwi'] / 'subdirectory'
        subtree.mkdir()
        cases.append(('home-subdirectory', {}, subtree, '-flic'))
        for name, changes, cwd, options in cases:
            with self.subTest(case=name):
                env = dict(self.env, **changes)
                result = self.shell(env=env, cwd=cwd, options=options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.launches(), [])

    def test_explicit_orca_startup_command_keeps_priority_over_autostart(self):
        for before, changes in [('typeset -ga _orca_shell_features=(history markers ready identity)', {}),
                                ('', {'ORCA_SHELL_FEATURES': 'history,markers,ready,identity'})]:
            nested = 'source ' + shlex.quote(str(HOOK))
            result = self.shell(before=before, env=dict(self.env, **changes),
                                after='/bin/zsh -d -flic ' + shlex.quote(nested))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.launches(), [])

    def test_plain_orca_overlay_still_opens_the_role_session(self):
        result = self.shell(before='typeset -ga _orca_shell_features=(overlay history markers)')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.launches()), 1)

    def test_reload_and_nested_login_shell_do_not_start_a_second_model(self):
        nested = 'source ' + shlex.quote(str(HOOK))
        result = self.shell(after=nested + '\n/bin/zsh -d -flic ' + shlex.quote(nested))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.launches()), 1)
        self.log.unlink()
        result = self.shell(env=dict(self.env, NAMED_TEAM_TAB_AUTOSTART_HANDLE='term_other_tab'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.launches()), 1, 'a new tab was suppressed by an inherited old handle')

    def test_missing_owned_profile_returns_to_shell_without_a_model(self):
        (self.home / '.codex/banana.config.toml').unlink()
        result = self.shell(after='print shell-still-usable')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shell-still-usable', result.stdout)
        self.assertIn('配線が未完了', result.stderr)
        self.assertEqual(self.launches(), [])

    def test_install_opt_in_is_idempotent_and_uninstall_preserves_user_config(self):
        target = self.home / 'install target'
        target.mkdir()
        config = target / '.zshrc'
        original = b'# user config\nexport CUSTOM_VALUE="quoted value"'
        config.write_bytes(original)
        config.chmod(0o600)
        self.assertEqual(self.install(target).returncode, 0)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(self.install(target, '--check', '--tab-autostart').returncode, 1)
        first = self.install(target, '--tab-autostart')
        self.assertEqual(first.returncode, 0, first.stderr)
        enabled = config.read_bytes()
        self.assertEqual(self.install(target, '--tab-autostart').returncode, 0)
        self.assertEqual(config.read_bytes(), enabled)
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.install(target, '--check', '--tab-autostart').returncode, 0)
        config.write_bytes(enabled + b'# later user addition\n')
        self.assertEqual(self.install(target, '--uninstall').returncode, 0)
        self.assertEqual(config.read_bytes(), original + b'# later user addition\n')

    def test_modified_block_or_symlink_is_preserved_before_link_mutation(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                target = self.home / ('conflict-link' if symlink else 'conflict-block')
                target.mkdir()
                config = target / '.zshrc'
                if symlink:
                    config.symlink_to(self.home / 'nonexistent-dotfile')
                else:
                    config.write_text('# >>> named-team Orca tab autostart >>>\nforeign command\n')
                result = self.install(target, '--tab-autostart')
                self.assertEqual(result.returncode, 2)
                self.assertFalse((target / '.local/bin').exists())
                if symlink:
                    self.assertTrue(config.is_symlink())
                else:
                    self.assertIn('foreign command', config.read_text())


if __name__ == '__main__':
    unittest.main()
