#!/usr/bin/env python3
"""Install owned skill/profile/command links without replacing unrelated files."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'lib'))
import installation
import tab_startup


def main():
    parser = argparse.ArgumentParser(description='名前付き role の command / skill / 起動 profile を配線')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--uninstall', action='store_true')
    parser.add_argument('--home', type=Path, default=Path.home(), help='対象 user home。通常は省略')
    parser.add_argument('--tab-autostart', action='store_true', help='新規 zsh タブで Tomato の対話、Banana のモデル無し受付を開始')
    args = parser.parse_args()
    target_home = args.home.expanduser().resolve()
    # Custom home is useful for an isolated installation check; the caller's env is untouched.
    config_home = Path(os.environ.get('CODEX_HOME', str(target_home / '.codex'))).expanduser() if target_home == Path.home().resolve() else target_home / '.codex'
    claude_home = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(target_home / '.claude'))).expanduser() if target_home == Path.home().resolve() else target_home / '.claude'
    links = installation.links(target_home, config_home, claude_home)
    retired = installation.retired_links(target_home, config_home, claude_home)
    replacements = installation.replaced_links(target_home)
    zshrc = target_home / '.zshrc'
    startup_plan = None
    if args.tab_autostart or args.uninstall:
        try:
            if args.tab_autostart and not args.uninstall:
                for source in (ROOT / 'shell/tab-autostart.zsh', ROOT / 'bin/tab-agent'):
                    if not source.is_file():
                        raise ValueError('自動起動の source が無い: ' + str(source))
            startup_plan = tab_startup.plan(zshrc, not args.uninstall)
        except (OSError, UnicodeError, ValueError) as exc:
            parser.error(str(exc))
    owned = installation.owned
    if args.check:
        bad = False
        for path, source in links:
            ok = owned(path, source) and source.exists() and os.readlink(path) == str(source)
            print(('OK  ' if ok else 'NG  ') + str(path))
            bad |= not ok
        for path, source in retired:
            if os.path.lexists(path):
                print('NG  retired link: ' + str(path));bad = True
        if args.tab_autostart:
            ok = startup_plan[0] == startup_plan[1]
            print(('OK  ' if ok else 'NG  ') + 'Orca tab autostart: ' + str(zshrc))
            bad |= not ok
        return 1 if bad else 0
    if args.uninstall:
        try:
            tab_startup.apply(zshrc, *startup_plan)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        for path, source in links + retired + replacements:
            if owned(path, source):
                path.unlink();print('removed ' + str(path))
        return 0
    # Inspect every destination before the first mutation, including dangling links.
    for path, source in links:
        if not source.exists():
            parser.error('source が無い: ' + str(source))
        if os.path.lexists(path) and not owned(path, source) and not any(
                old == path and owned(old, origin) for old, origin in replacements):
            parser.error('別のファイル/リンクを保持したため中断: ' + str(path))
    for path, source in retired:
        if os.path.lexists(path) and not owned(path, source):
            parser.error('別の廃止対象配線を保持したため中断: ' + str(path))
    created = []
    replaced = []
    try:
        for path, source in links:
            if owned(path, source) and os.readlink(path) == str(source):
                continue
            if os.path.lexists(path):
                replaced.append((path, os.readlink(path)))
                path.unlink()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(source);created.append((path, source))
        if startup_plan is not None:
            tab_startup.apply(zshrc, *startup_plan)
    except (OSError, ValueError) as exc:
        for path, source in reversed(created):
            if owned(path, source):
                path.unlink()
        for path, source in replaced:
            if not os.path.lexists(path):
                path.symlink_to(source)
        print('配線できない: ' + str(exc), file=sys.stderr)
        return 1
    for path, source in retired:
        if owned(path, source):
            path.unlink();print('retired ' + str(path))
    for path, _ in links:
        print('ready ' + str(path))
    if args.tab_autostart:
        print('ready Orca tab autostart: ' + str(zshrc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
