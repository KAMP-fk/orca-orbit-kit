"""Keep the Banana coordinator separate from its implementation engine."""
from pathlib import Path
import shutil

from role_contract import skill_root, ROLES
from role_launch import launch_spec


def execution_spec(role, cwd, prompt, model=None, effort=None, dry_run=False,
                   read_only=False, worker_backend='codex'):
    if worker_backend in ('codex', 'claude'):
        if worker_backend == 'claude' and ROLES[role]['backend'] != 'claude':
            raise ValueError('この担当は Claude を使わない')
        return launch_spec(role, cwd, prompt, model=model, effort=effort,
                           batch=True, dry_run=dry_run, read_only=read_only)
    if worker_backend != 'devin' or role != 'banana' or read_only:
        raise ValueError('Devin の編集実行は Banana の develop 入口を使う')
    if model or effort:
        raise ValueError('Devin はベンダー設定を使う。Codex model / effort を流用しない')
    executable = shutil.which('devin')
    if not executable:
        raise ValueError('ベンダー Devin CLI が見つからない。別モデルへ fallback しない')
    skill = skill_root('banana') / 'SKILL.md'
    if not skill.is_file():
        raise ValueError('Banana の役割契約が見つからない')
    instructions = ('最初に ' + str(skill) + ' と対象プロジェクトの現行契約を読む。'
                    '\nBanana の実装エンジンとして、この checkout だけで依頼を実装し、必要な検査を行う。'
                    '\n成果はこの branch に commit し、最終報告に full SHA・変更・検査・残件を書く。'
                    '\n契約・受入範囲が不明なら Tomato に質問を返す。追加 worktree / agent を作らない。'
                    '\n独立承認、Ready、merge、Done の確定を行わず、Potato への引渡しを待つ。'
                    '\n\n' + prompt)
    return {'command': [str(Path(executable).absolute()), '--print', '--', instructions],
            'environment': {}, 'backend': 'devin', 'collector': 'devin-print',
            'skill': str(skill), 'profile': None, 'effort': None, 'requestedModel': None}
