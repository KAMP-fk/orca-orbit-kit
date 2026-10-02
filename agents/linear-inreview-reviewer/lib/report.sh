#!/usr/bin/env bash
# Shared entry-point/library globals are consumed across sourced modules.
# shellcheck disable=SC2034
# Sourced by bin/linear-inreview-reviewer; does not run on its own.

# --- 判定台帳 -----------------------------------------------------------------
# 1行1判定。挙動を横に並べて見るための唯一の場所。
ledger_append() { # issue verdict ci tests pr commit model secs packet
  mkdir -p "$STATE_HOME" 2>/dev/null || return 0
  if [ ! -f "$LEDGER" ]; then
    printf '#ts_utc\tissue\tverdict\tci\ttests\tpr\tcommit\tmodel\tsecs\tpacket\n' > "$LEDGER" 2>/dev/null || return 0
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(printf '%s' "${1:--}" | tr '\t\n' '  ')" \
    "$(printf '%s' "${2:--}" | tr '\t\n' '  ')" \
    "$(printf '%s' "${3:--}" | tr '\t\n' '  ')" \
    "$(printf '%s' "${4:--}" | tr '\t\n' '  ')" \
    "$(printf '%s' "${5:--}" | tr '\t\n' '  ')" \
    "$(printf '%s' "${6:--}" | tr '\t\n' '  ')" \
    "$(printf '%s' "${7:--}" | tr '\t\n' '  ')" \
    "${8:--}" "${9:--}" >> "$LEDGER" 2>/dev/null || true
}

# --- 判定形式での停止 ---------------------------------------------------------
ISSUE_TITLE_FOR_REPORT=""
blocked() {
  local summary="$1"
  if [ -n "${EVIDENCE_LOG:-}" ] && [ -f "$EVIDENCE_LOG" ]; then finalize_evidence; fi
  ledger_append "${IDENT:-${ISSUE:--}}" "BLOCKED" "UNKNOWN" "UNKNOWN" "-" "-" \
                "${BACKEND}/${USE_MODEL:-?}/${USE_EFFORT:-?}" "$(( $(date +%s) - START_EPOCH ))" "${PACKET:--}"
  cat <<REPORT
Issue: ${ISSUE:-<unknown>} ${ISSUE_TITLE_FOR_REPORT}

Verdict: BLOCKED

Summary:
${summary}

Acceptance Criteria:

* [?] レビューに着手できなかったため未評価

Findings:

* なし

Required Changes:

* なし

Verification:

* PR: UNKNOWN
* Commit: UNKNOWN
* CI: UNKNOWN
* Tests: UNKNOWN
REPORT
  exit 3
}

die() { printf '%s: %s\n' "$REVIEWER_NAME" "$1" >&2; exit 2; }

record_verdict() {
  if [ "$RC" -ne 0 ]; then
    blocked "レビュアーの実行または結果保存に失敗した（rc=${RC}）。部分的な出力を有効な判定として記録しない。観測資料: ${PACKET}"
  fi
  recheck_github
  recheck_linear final
  write_packet
  assert_evidence_ready
  # codex exec は最終メッセージを末尾にも出す。判定ブロックだけを verdict.md に残す
  awk '/^Issue: /{found=NR} {l[NR]=$0} END{if(found){for(i=found;i<=NR;i++) print l[i]}else{for(i=1;i<=NR;i++) print l[i]}}' \
    "$PACKET/verdict.raw" > "$PACKET/verdict.md" 2>/dev/null \
    || blocked "判定レポートを保存できなかった。部分出力を判定として記録しない。観測資料: ${PACKET}"

  if ! python3 "$LIB_ROOT/evidence.py" verdict "$PACKET" > "$PACKET/verdict-validation.json" 2> "$PACKET/verdict-validation.err"; then
    blocked "判定レポートが形式または Issue / PR / full head SHA / CI / Tests の取得事実と一致しない。無効な PASS を記録しない。診断: ${PACKET}/verdict-validation.err"
  fi
  V_OUT="$(jq -r '.verdict' "$PACKET/verdict-validation.json")"
  grab() { jq -r --arg k "$1" '.[$k]' "$PACKET/verdict-validation.json"; }
  ledger_append "$IDENT" "$V_OUT" "$(grab CI)" "$(grab Tests)" "$(grab PR)" "$(grab Commit)" \
                "${BACKEND}/${USE_MODEL}/${USE_EFFORT}" "$(( $(date +%s) - START_EPOCH ))" "$PACKET"

  printf '%s: verdict=%s (%s)\n' "$REVIEWER_NAME" "$PACKET/verdict.md" "$V_OUT" >&2
  printf '%s: ledger=%s\n' "$REVIEWER_NAME" "$LEDGER" >&2
  cat "$PACKET/verdict.md"
}
