"""Launch each role with its declared backend and owned configuration."""
import json
import os
from pathlib import Path
import shutil

from role_contract import ROOT, LAUNCH_ROLES, ROLES, skill_root, public_name, role_label, installed_profile, profile_source

EFFORT = {name: ROLES[name]['effort'] for name in LAUNCH_ROLES}


def claude_spec(role, cwd, skill, installed, model, effort, batch, dry_run, read_only):
    settings = json.loads(profile_source(role).read_text())
    review = role == 'review'
    if (settings.get('model') != ROLES[role]['model']
            or settings.get('effortLevel') != ROLES[role]['effort']):
        raise ValueError(role_label(role) + ' の Claude 設定が役割定義と一致しない')
    model = model or settings['model']
    if review and (model != 'claude-opus-5-5' or effort != 'high' or not settings.get('disableAllHooks')):
        raise ValueError('Potato は Opus 5.5 / high と hook 無効の専用設定に固定する')
    if not review and model != 'fable':
        raise ValueError('Tomato の会話は Fable。別モデルへ暗黙に切り替えない')
    if effort not in ('low', 'medium', 'high', 'xhigh', 'max'):
        raise ValueError('Fable の effort は low / medium / high / xhigh / max を指定する')
    instructions = ROOT / ROLES[role]['instructions']
    if not instructions.is_file():
        raise ValueError(role_label(role) + ' の起動指示が見つからない')
    command = ['claude', '--model', model, '--effort', effort, '--settings', str(installed),
               '--append-system-prompt', instructions.read_text()]
    if review:
        # One primary reviewer, restricted to file reads; no fallback or child agents.
        definition = {'potato': {'description': 'Independent review', 'prompt': instructions.read_text(),
                      'model': model, 'effort': effort, 'tools': ['Read', 'Glob', 'Grep'],
                      'permissionMode': 'dontAsk'}}
        command += ['--restricted', '--tools', 'Read,Glob,Grep', '--strict-mcp-config',
                    '--mcp-config', '{"mcpServers":{}}', '--disable-slash-commands',
                    '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
                    '--agents', json.dumps(definition, ensure_ascii=False), '--agent', 'potato',
                    '--add-dir', str(skill.parent), '--add-dir', str(ROOT / 'references')]
    elif read_only:
        # No command/write tools or MCP servers in a repository read request.
        command += ['--permission-mode', 'plan', '--tools', 'Read,Grep,Glob',
                    '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
    if batch:
        command += ['--print', '--output-format', 'json']
    executable = shutil.which('claude')
    if not executable and not dry_run:
        raise ValueError('Claude Code が見つからない。別モデル / Codex に fallback しない')
    if executable:
        command[0] = str(Path(executable).absolute())
    return {'command': command, 'environment': {'CLAUDE_CONFIG_DIR': str(installed.parent.parent)},
            'backend': 'claude', 'collector': 'claude' if review else 'claude-consultation', 'skill': str(skill),
            'profile': str(installed), 'effort': effort, 'requestedModel': model}


def launch_spec(role, cwd, prompt=None, model=None, effort=None, batch=False, dry_run=False, read_only=False):
    if role not in EFFORT:
        raise ValueError('この入口で実行する role ではない: ' + role)
    if effort is not None and effort not in ('low', 'medium', 'high', 'xhigh', 'max', 'ultra'):
        raise ValueError('--effort は low / medium / high / xhigh / max / ultra を指定する')
    if model is not None and (not model.strip() or model.startswith('-')):
        raise ValueError('--model はモデル ID を指定する')
    if role == 'review':
        from project_identity import is_concafe_path
        if is_concafe_path(cwd):
            raise ValueError('concafe のレビューは Owner 指示の未関与の別タスク経路を使う')
        if (model and model != 'claude-opus-5-5') or (effort and effort != 'high'):
            raise ValueError('Potato は Opus 5.5 / high に固定。最終判定は potato --kind final を使う')
        read_only = True
    skill = skill_root(role) / 'SKILL.md'
    profile = profile_source(role)
    installed = installed_profile(role)
    if not skill.is_file() or not profile.is_file() or installed.resolve() != profile.resolve() or not installed.is_file():
        raise ValueError('role / profile の配線が未完了。agents/team/install.py --check を確認する')
    effort = effort or EFFORT[role]
    if ROLES[role]['backend'] == 'claude':
        spec = claude_spec(role, cwd, skill, installed, model, effort, batch, dry_run, read_only)
        if prompt is not None:
            spec['command'] += ['--', ('最初に ' + str(skill) + ' を読み、現在のユーザー指示と対象プロジェクトの契約を適用してください。'
                                     + '\n担当: ' + role_label(role) + '\n\n今回の依頼:\n' + prompt)]
        return spec
    if ROLES[role]['backend'] != 'codex':
        raise ValueError('未対応の起動 backend: ' + ROLES[role]['backend'])
    config_home = installed.parent
    command = ['codex', '-p', public_name(role), '-c', 'model_reasoning_effort="' + effort + '"', '-C', str(cwd)]
    if read_only:
        command += ['-c', 'sandbox_mode="read-only"']
    if model:
        command += ['-m', model]
    if batch:
        command += ['exec']
    else:
        command += ['-c', 'check_for_update_on_startup=false']
    executable = shutil.which('codex')
    if not executable and not dry_run:
        raise ValueError('codex が見つからない')
    if executable:
        command[0] = str(Path(executable).absolute())
    if prompt is not None:
        prompt = ('最初に ' + str(skill) + ' を読み、現在のユーザー指示と対象プロジェクトの契約を適用してください。'
                  + '\n担当: ' + role_label(role) + '\n\n今回の依頼:\n' + prompt)
        command += ['--', prompt]
    return {'command': command, 'environment': {'CODEX_HOME': str(config_home)}, 'backend': 'codex', 'collector': 'codex',
            'skill': str(skill), 'profile': str(installed), 'effort': effort,
            'requestedModel': model}
