#!/usr/bin/env bash
# Peach — 配線スクリプト
#
# エージェントの実体はこのフォルダ1つに収まっている。
# 各ツールが「ここを見る」と決めている場所へ、シンボリックリンクだけを張る。
#
#   ./install.sh              張る（既存の実ファイルは壊さず中断する）
#   ./install.sh --check      いまの配線状態を見る
#   ./install.sh --uninstall  このフォルダを指すリンクだけ剥がす
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="peach"
LEGACY_NAME="linear-inreview-reviewer"

# 「リンク先の実体」→「ツールが見る場所」
LINKS="
$ROOT/bin/$LEGACY_NAME|$HOME/.local/bin/$NAME
$ROOT/skill|$HOME/.agents/skills/$NAME
$ROOT/claude/agent.md|$HOME/.claude/agents/$NAME.md
$ROOT/codex/profile.config.toml|$HOME/.codex/$NAME.config.toml
$ROOT/bin/$LEGACY_NAME|$HOME/.local/bin/$LEGACY_NAME
$ROOT/codex/profile.config.toml|$HOME/.codex/$LEGACY_NAME.config.toml
$ROOT/claude/legacy-agent.md|$HOME/.claude/agents/$LEGACY_NAME.md
"

MODE="install"
case "${1:-}" in
  --check) MODE="check" ;;
  --uninstall) MODE="uninstall" ;;
  "") ;;
  *) echo "usage: $0 [--check|--uninstall]" >&2; exit 2 ;;
esac

matches() {
  [ -L "$2" ] || return 1
  python3 - "$1" "$2" <<'PY'
import os, sys
raise SystemExit(0 if os.path.realpath(sys.argv[1]) == os.path.realpath(sys.argv[2]) else 1)
PY
}

# Inspect all destinations before mutating links; migrate only the known old agent link.
if [ "$MODE" = "install" ]; then
  while IFS='|' read -r src dst; do
    [ -n "${src:-}" ] || continue
    [ -e "$src" ] || { printf 'ERROR   実体が無い: %s\n' "$src" >&2; exit 1; }
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      if matches "$src" "$dst"; then continue; fi
      if [ "$dst" = "$HOME/.claude/agents/$LEGACY_NAME.md" ] && matches "$ROOT/claude/agent.md" "$dst"; then continue; fi
      printf 'ERROR   別のファイル/リンクを保持したため中断: %s\n' "$dst" >&2
      exit 1
    fi
  done <<< "$LINKS"
fi

rc=0
printf '%s\n' "root: $ROOT"
printf '%s\n' ""

while IFS='|' read -r src dst; do
  [ -n "${src:-}" ] || continue
  short="${dst/#$HOME/~}"

  case "$MODE" in
    check)
      if [ -L "$dst" ]; then
        cur="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$dst" 2>/dev/null || true)"
        want="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$src" 2>/dev/null || true)"
        if [ "$cur" = "$want" ] && [ -e "$src" ]; then printf 'OK      %s\n' "$short"
        else printf 'WRONG   %s -> %s\n' "$short" "$cur"; rc=1; fi
      elif [ -e "$dst" ]; then
        printf 'CONFLICT %s (リンクではない実ファイルがある)\n' "$short"; rc=1
      else
        printf 'MISSING %s\n' "$short"; rc=1
      fi
      ;;

    uninstall)
      if [ -L "$dst" ]; then
        cur="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$dst" 2>/dev/null || true)"
        if matches "$src" "$dst"; then rm -f "$dst"; printf 'removed %s\n' "$short"
        else printf 'skip    %s (この定義を指していない)\n' "$short"; fi
      else
        printf 'skip    %s (リンク無し)\n' "$short"
      fi
      ;;

    install)
      [ -e "$src" ] || { printf 'ERROR   実体が無い: %s\n' "$src"; rc=1; continue; }
      mkdir -p "$(dirname "$dst")"
      if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        printf 'ERROR   %s に実ファイルがある。中身を確認してから手で退避すること\n' "$short"
        rc=1; continue
      fi
      ln -sfn "$src" "$dst"
      printf 'linked  %s\n' "$short"
      ;;
  esac
done <<< "$LINKS"

if [ "$MODE" = "install" ]; then
  # Remove our old skill discovery link so a single Peach entry is listed.
  old_skill="$HOME/.agents/skills/$LEGACY_NAME"
  if matches "$ROOT/skill" "$old_skill"; then rm -f "$old_skill"; printf 'retired %s\n' "$old_skill"; fi
  chmod +x "$ROOT/bin/$LEGACY_NAME"
  printf '\n'
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) printf 'PATH: ~/.local/bin は通っている\n' ;;
    *) printf 'PATH: ~/.local/bin が通っていない。shell の設定に足すこと\n'; rc=1 ;;
  esac
  printf '\n確認: %s --check\n使う: %s --board\n' "$0" "$NAME"
fi

exit "$rc"
