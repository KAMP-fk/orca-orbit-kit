"""Manage only this package's opt-in zsh startup block, preserving user config."""
import os
from pathlib import Path
import shlex
import stat
import tempfile

ROOT = Path(__file__).resolve().parent.parent
BEGIN = '# >>> named-team Orca tab autostart >>>'
END = '# <<< named-team Orca tab autostart <<<'


def block():
    source = shlex.quote(str(ROOT / 'shell/tab-autostart.zsh'))
    return '\n' + BEGIN + '\n' + '[[ ! -r ' + source + ' ]] || source ' + source + '\n' + END + '\n'


def plan(path, enable):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('別の zshrc ファイル/リンクを保持したため中断: ' + str(path))
    previous = path.read_bytes() if path.exists() else b''
    text = previous.decode('utf-8')
    owned = block()
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.count(owned) != 1:
            raise ValueError('変更された自動起動 block を保持したため中断: ' + str(path))
        text = text.replace(owned, '')
    if enable:
        text += owned
    return previous, text.encode('utf-8')


def apply(path, previous, updated):
    path = Path(path)
    if previous == updated:
        return
    if path.is_symlink() or (path.read_bytes() if path.exists() else b'') != previous:
        raise ValueError('zshrc が同時に変更されたため中断: ' + str(path))
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix='.named-team-zshrc-', delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), mode)
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
