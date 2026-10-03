# Sourced from the owned .zshrc block. A model exits back to this shell.
function {
  emulate -L zsh
  [[ -o interactive && -o login && ${TERM_PROGRAM:-} == Orca ]] || return 0
  [[ -n ${ORCA_TERMINAL_HANDLE:-} && -n ${ORCA_WORKTREE_ID:-} ]] || return 0
  [[ ${NAMED_TEAM_TAB_AUTOSTART_HANDLE:-} != "$ORCA_TERMINAL_HANDLE" ]] || return 0

  # Orca's explicit startup commands use its shell-ready wrapper. Let that
  # command reach its first prompt; never put another TUI in front of it.
  if (( ${_orca_shell_features[(Ie)ready]:-0} || ${_orca_shell_features[(Ie)identity]:-0} )) ||
     [[ ,${ORCA_SHELL_FEATURES:-}, == *,ready,* || ,${ORCA_SHELL_FEATURES:-}, == *,identity,* ]]; then
    # Nested login shells in this command belong to the same explicit launch.
    export NAMED_TEAM_TAB_AUTOSTART_HANDLE="$ORCA_TERMINAL_HANDLE"
    return 0
  fi

  local named_team_role
  local -x PATH="$HOME/.local/bin:$PATH"
  named_team_role=$(/usr/bin/python3 "$1" --resolve) || return 0
  [[ -n $named_team_role ]] || return 0
  export NAMED_TEAM_TAB_AUTOSTART_HANDLE="$ORCA_TERMINAL_HANDLE"
  /usr/bin/python3 "$1"
} "${${(%):-%x}:A:h:h}/bin/tab-agent"
