#!/usr/bin/env bash
# Shared entry-point/library globals are consumed across sourced modules.
# shellcheck disable=SC2034
# Acquisition facts are written by the launcher, never inferred by the model.
init_evidence() {
  EVIDENCE_LOG="$PACKET/evidence.jsonl"
  : > "$EVIDENCE_LOG"
  FETCH_ERRORS=""
  jq -n --argjson tests "$(printf '%s\n' "${EXPLICIT_TEST_CHECKS[@]:-}" | jq -Rsc 'split("\n") | map(select(length > 0))')" \
    '{testChecks:$tests,source:"launcher --test-check; exact-name classification only"}' > "$PACKET/verification-policy.json"
}

evidence_record() { # key path required status started_at finished_at rc scope detail
  jq -cn --arg key "$1" --arg path "${2#"$PACKET/"}" --argjson required "$3" \
    --arg status "$4" --arg started "$5" --arg finished "$6" --argjson rc "$7" \
    --arg scope "$8" --arg detail "${9:-}" \
    '{key:$key,path:$path,required:$required,status:$status,startedAt:$started,observedAt:$finished,exitCode:$rc,scope:$scope,detail:$detail}' \
    >> "$EVIDENCE_LOG"
  if [ "$4" != acquired ]; then
    FETCH_ERRORS="${FETCH_ERRORS}\n- ${1}: ${4} (${8}); ${9:-see acquisition error file}"
  fi
}

evidence_capture() { # key path required scope command ...
  local key="$1" path="$2" required="$3" scope="$4" started rc=0
  shift 4
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$@" > "$path" 2> "$path.err" || rc=$?
  local semantic_exit=0
  if [[ "$key" == *.required-checks ]] && { [ "$rc" -eq 1 ] || [ "$rc" -eq 8 ]; } &&
    jq -e 'type == "array" and length > 0 and all(.[]; (.name | type == "string") and (.bucket | type == "string"))' "$path" >/dev/null 2>&1; then
    semantic_exit=1
  fi
  if [ "$rc" -eq 0 ] || [ "$semantic_exit" -eq 1 ]; then
    evidence_record "$key" "$path" "$required" acquired "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" "$scope" "semantic check exit=$semantic_exit"
  else
    # A partial stdout is retained for diagnosis, never relabelled as an empty success.
    evidence_record "$key" "$path" "$required" failed "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" "$scope" "see ${path#"$PACKET/"}.err"
  fi
  [ "$semantic_exit" -ne 1 ] || rc=0
  return "$rc"
}

evidence_invalid() { # key path required scope detail
  local now
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  evidence_record "$1" "$2" "$3" invalid "$now" "$now" 0 "$4" "$5"
}

finalize_evidence() {
  jq -s '{schemaVersion:1,observations:.,complete:all(.[]; .required != true or .status == "acquired"),
    missing:map(select(.required == true and .status != "acquired"))}' "$EVIDENCE_LOG" > "$PACKET/evidence.json"
}

assert_evidence_ready() {
  if ! jq -e '.evidence.complete == true' "$PACKET/meta.json" >/dev/null; then
    blocked "必須の証拠が未取得または不正。空の成功として扱わずレビューを停止した。取得状況: ${PACKET}/evidence.json。$(printf '%b' "$FETCH_ERRORS")"
  fi
}
