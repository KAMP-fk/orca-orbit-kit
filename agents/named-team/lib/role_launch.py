"""Canonical named-role argv; shared by home, direct, and project-task launches."""
import json
import os
from pathlib import Path
import shutil
from role_contract import LAUNCH_ROLES, ROLES, skill_root

ROOT = Path(__file__).resolve().parent.parent
EFFORT = {name: ROLES[name]['effort'] for name in LAUNCH_ROLES}
REVIEW_MODEL = 'claude-opus-5-5'


def launch_spec(role, cwd, prompt=None, model=None, effort=None, batch=False, dry_run=False, read_only=False):
    if role not in EFFORT:
        raise ValueError('この入口で実行する role ではない: ' + role)
    if model is not None and (not model.strip() or model.startswith('-')):
        raise ValueError('--model はモデル ID を指定する')
    if role == 'potato' and ((model and model != REVIEW_MODEL) or (effort and effort != 'high')):
        raise ValueError('Potato のレビューは claude-opus-5-5 / high を指定する')
    skill = skill_root(role) / 'SKILL.md'
    config_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().resolve()
    claude_home = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))).expanduser().resolve()
    if role == 'potato':
        profile = ROOT / 'roles/potato/claude/agent.md'
        installed = claude_home / 'agents/potato.md'
    else:
        profile = ROOT / 'roles' / role / 'codex/profile.config.toml'
        installed = config_home / (role + '.config.toml')
    if not skill.is_file() or not profile.is_file() or installed.resolve() != profile.resolve() or not installed.is_file():
        raise ValueError('role / profile の配線が未完了。named-team/install.py --check を確認する')
    effort = effort or EFFORT[role]
    if role == 'potato':
        backend = 'claude'
        settings = ROOT / 'roles/potato/claude/settings.json'
        if not settings.is_file():
            raise ValueError('Potato の Claude settings が無い')
        policy = json.loads(settings.read_text())
        if policy.get('model') != REVIEW_MODEL or policy.get('effortLevel') != 'high' or policy.get('disableAllHooks') is not True or policy.get('permissions', {}).get('disableBypassPermissionsMode') != 'disable':
            raise ValueError('Potato の model / effort / permissions 設定が一致しない')
        from review_routing import is_concafe_path
        if is_concafe_path(cwd):
            raise ValueError('concafe のレビューは Owner 指示の未関与の別 Codex タスク経路を使う。汎用 Claude は起動しない')
        definition = {'potato': {'description': 'Independent technical reviewer',
                      'prompt': skill.read_text().split('\n---\n', 1)[-1].strip(),
                      'model': REVIEW_MODEL, 'effort': 'high', 'tools': ['Read', 'Glob', 'Grep'],
                      'permissionMode': 'dontAsk'}}
        command = ['claude', '--model', REVIEW_MODEL, '--effort', 'high', '--restricted', '--disable-slash-commands',
                   '--tools', 'Read,Glob,Grep', '--permission-mode', 'dontAsk',
                   '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                   '--settings', str(settings), '--agents', json.dumps(definition, ensure_ascii=False),
                   '--agent', 'potato', '--add-dir', str(skill.parent),
                   '--add-dir', str(ROOT / 'references')]
        if batch:
            command += ['--print', '--output-format', 'json', '--permission-prompts', 'none']
        environment = {'CLAUDE_CODE_EFFORT_LEVEL': 'high'}
        # Setting this variable changes Claude's global config-file location.
        # Preserve its native default unless the caller explicitly selected one.
        if os.environ.get('CLAUDE_CONFIG_DIR'):
            environment['CLAUDE_CONFIG_DIR'] = str(claude_home)
    else:
        backend = 'codex'
        command = ['codex', '-p', role, '-c', 'model_reasoning_effort="' + effort + '"', '-C', str(cwd)]
        if read_only:
            command += ['-c', 'sandbox_mode="read-only"']
        if model:
            command += ['-m', model]
        if batch:
            command += ['exec']
        else:
            # A manually opened role tab should reach its input prompt directly.
            # Keep the installed version and all trust/permission settings intact.
            command += ['-c', 'check_for_update_on_startup=false']
        environment = {'CODEX_HOME': str(config_home)}
    executable = shutil.which(backend)
    if not executable and not dry_run:
        raise ValueError(backend + ' が見つからない')
    if executable:
        command[0] = str(Path(executable).absolute())
    if prompt is not None:
        prompt = 'あなたは ' + role.capitalize() + '。最初に ' + str(skill) + ' を読み、現在のユーザー指示と対象プロジェクトの契約を適用してください。\n\n今回の依頼:\n' + prompt
        command += ['--', prompt]
    return {'command': command, 'environment': environment, 'backend': backend,
            'skill': str(skill), 'profile': str(installed), 'effort': effort,
            'requestedModel': REVIEW_MODEL if role == 'potato' else model}
