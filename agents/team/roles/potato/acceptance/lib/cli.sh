#!/usr/bin/env bash
# Shared entry-point/library globals are consumed across sourced modules.
# shellcheck disable=SC2034
# Sourced by bin/linear-inreview-reviewer; does not run on its own.

usage() {
  cat <<USAGE
${REVIEWER_NAME} — Linear "In Review" Issue 専用レビュアー（判定のみ / read-only）

  ${REVIEWER_NAME} --list
      Linear の status が厳密に "In Review" の Issue を横断で一覧する

  ${REVIEWER_NAME} --ledger [N]
      これまでに出した判定を新しい順に見る（既定 30 件）

  ${REVIEWER_NAME} <ISSUE-ID|URL> [options]
      その Issue をレビューし、PASS / CHANGES_REQUIRED / BLOCKED を出す

Options:
  --orca / --task          一件を新しい見える Orca タブで実行。保存・回収・終了後にそのタブだけ閉じる
  --worktree path:<ABS>    --orca 用のタブ配置先。省略時は Banana の受付
  --dry-run               Orca タスクの起動内容を確認。サービス取得もモデル起動もしない
  --backend claude        Claude Opus 5.5 / high 固定（別 backend は拒否）
                           restricted / Read,Glob,Grep のみ、user/project/local hook・MCP 無効
  --pr <owner/repo#N>      対象 PR を明示指定（複数可）。推測させたくないときに使う
  --expected-repo <owner/repo>  共通 Potato 受付の対象。別 repo の候補ではモデルを起動しない
  --run <owner/repo:RUN_ID>  受入条件が参照する GitHub Actions の run を一次データとして
                           パケットに入れる（複数可）。github/runs/ に run・job・ログを保存する
  --test-check <NAME>       テストを実行する CI チェック名を明示（複数可、完全一致）
  --draft-light-ci          risk:high / risk:low とも Draft の軽い CI でレビューする（T4 2026-10-08）。
                           Draft でいずれかの risk ラベルが完全一致で在るときだけ、
                           skipped の必須チェックを merge の関門（CI / full）へ委ねたものとして記録し、
                           走ったチェックがすべて success なら CI: PASS とする。fail / pending は読み替えない
                           一般名の CI/full 等のテスト根拠を操作者が指定するときに使う
  --packet-only            レビューパケットを作るだけで Agent を起動しない
  --ledger [N]             これまでの判定を新しい順に N 件表示する（既定 30）
  --board                  常設タブ用。直近の判定と、いま In Review の Issue を並べて出す
  --no-preflight           モデル固定のプリフライト検証を省く（非推奨）
  -h, --help               このヘルプ

モデルは固定。軽量モデルへの自動フォールバックはしない。
承認モデルを使えない場合は BLOCKED で停止する。
USAGE
}


parse_args() {
  EXPECTED_REPO=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --list) DO_LIST=1; shift ;;
      --board)
        printf '\n=== 直近の判定 ===\n\n'
        "$0" --ledger 10 2>/dev/null || true
        printf '\n=== いま In Review ===\n\n'
        "$0" --list 2>/dev/null || true
        printf '\n起動: %s <ISSUE-ID> [--pr owner/repo#N]\n\n' "$REVIEWER_NAME"
        exit 0
        ;;
      --ledger)
        shift
        LEDGER_N=30
        if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
          [[ "$1" =~ ^[0-9]+$ ]] || die "--ledger N は0以上の整数にする"
          LEDGER_N="$1"; shift
        fi
        if [ ! -f "$LEDGER" ]; then
          printf 'まだ判定がありません: %s\n' "$LEDGER"; exit 0
        fi
        { head -1 "$LEDGER"; tail -n +2 "$LEDGER" | sort -r | awk -v n="$LEDGER_N" 'NR <= n'; } \
          | awk -F'\t' 'BEGIN{OFS="\t"}
              {
                sub(/T/," ",$1); sub(/Z$/,"",$1); sub(/^#/,"",$1)
                if ($6 ~ /github\.com/) { sub(/^https?:\/\/github\.com\//,"",$6); sub(/\/pull\//,"#",$6) }
                if (length($7) > 12) $7 = substr($7,1,12)
                print $1,$2,$3,$4,$5,$6,$7,$8,$9
              }' \
          | { column -t -s "$(printf '\t')" 2>/dev/null || cat; }
        printf '\n台帳: %s\n' "$LEDGER"
        exit 0
        ;;
      --backend) [ $# -ge 2 ] || die "--backend needs a value"; BACKEND="$2"; shift 2 ;;
      --backend=*) BACKEND="${1#*=}"; shift ;;
      --pr) [ $# -ge 2 ] || die "--pr needs owner/repo#N"; EXPLICIT_PRS+=("$2"); shift 2 ;;
      --pr=*) EXPLICIT_PRS+=("${1#*=}"); shift ;;
      --expected-repo) [ $# -ge 2 ] && [ -n "$2" ] || die "--expected-repo needs owner/repo"; EXPECTED_REPO="$2"; shift 2 ;;
      --expected-repo=*) EXPECTED_REPO="${1#*=}"; [ -n "$EXPECTED_REPO" ] || die "--expected-repo needs owner/repo"; shift ;;
      --run) [ $# -ge 2 ] || die "--run needs owner/repo:RUN_ID"; EXPLICIT_RUNS+=("$2"); shift 2 ;;
      --run=*) EXPLICIT_RUNS+=("${1#*=}"); shift ;;
      --test-check) [ $# -ge 2 ] || die "--test-check needs a check name"; EXPLICIT_TEST_CHECKS+=("$2"); shift 2 ;;
      --test-check=*) EXPLICIT_TEST_CHECKS+=("${1#*=}"); shift ;;
      --draft-light-ci) DRAFT_LIGHT_CI=1; shift ;;
      --packet-only) PACKET_ONLY=1; shift ;;
      --no-preflight) PREFLIGHT=0; shift ;;
      -h|--help) usage; exit 0 ;;
      -*) die "unknown option: $1" ;;
      *) [ -z "$ISSUE" ] || die "issue is already set to '$ISSUE'"; ISSUE="$1"; shift ;;
    esac
  done

  # Validate selectors before any external request or packet creation.
  local spec
  if [ -n "$EXPECTED_REPO" ]; then
    [[ "$EXPECTED_REPO" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+$ ]] \
      || die "--expected-repo の形式は owner/repo"
    for spec in "${EXPLICIT_PRS[@]:-}" "${EXPLICIT_RUNS[@]:-}"; do
      [ -n "$spec" ] || continue
      [ "$(printf '%s' "${spec%%[#:]*}" | tr 'A-Z' 'a-z')" = "$(printf '%s' "$EXPECTED_REPO" | tr 'A-Z' 'a-z')" ] \
        || die "明示対象と --expected-repo が一致しない"
    done
  fi
  for spec in "${EXPLICIT_PRS[@]:-}"; do
    [ -n "$spec" ] || { [ "${#EXPLICIT_PRS[@]}" -eq 0 ] && continue; die "--pr needs owner/repo#N"; }
    [[ "$spec" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+#[1-9][0-9]*$ ]] \
      || die "--pr の形式は owner/repo#N（N は正の整数）"
  done
  for spec in "${EXPLICIT_RUNS[@]:-}"; do
    [ -n "$spec" ] || { [ "${#EXPLICIT_RUNS[@]}" -eq 0 ] && continue; die "--run needs owner/repo:RUN_ID"; }
    [[ "$spec" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+:[1-9][0-9]*$ ]] \
      || die "--run の形式は owner/repo:RUN_ID（RUN_ID は正の整数）"
  done
  for spec in "${EXPLICIT_TEST_CHECKS[@]:-}"; do
    [ -n "$spec" ] || continue
    [[ "$spec" != -* && "$spec" != *$'\n'* && "$spec" != *$'\r'* && "$spec" != *$'\t'* ]] \
      || die "check name must be a single non-option line"
  done
  if [ "${#EXPLICIT_TEST_CHECKS[@]}" -gt 0 ]; then
    for spec in "${EXPLICIT_TEST_CHECKS[@]}"; do [ -n "$spec" ] || die "--test-check needs a check name"; done
  fi
}
