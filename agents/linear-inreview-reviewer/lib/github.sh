#!/usr/bin/env bash
# Shared entry-point/library globals are consumed across sourced modules.
# shellcheck disable=SC2034
# Sourced by bin/linear-inreview-reviewer; does not run on its own.

collect_candidates() {
  # --- 4. PR 候補の特定 ---------------------------------------------------------
  CAND="$PACKET/github/candidates.json"
  : > "$PACKET/github/.cand.raw"

  add_cand() { # owner repo number source
    jq -cn --arg owner "$1" --arg repo "$2" --argjson number "$3" --arg source "$4" \
      '{owner:$owner, repo:$repo, number:$number, source:$source}' >> "$PACKET/github/.cand.raw"
}

# 4a. 明示指定
for spec in "${EXPLICIT_PRS[@]:-}"; do
  [ -n "$spec" ] || continue
  if [[ "$spec" =~ ^([^/]+)/([^#]+)#([0-9]+)$ ]]; then
    add_cand "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "explicit --pr"
  else
    die "--pr の形式は owner/repo#N（例: KAMP-fk/concafe-techo#232）"
  fi
done

if [ "${#EXPLICIT_PRS[@]}" -eq 0 ]; then
  # 4b. Issue 本文 / コメント / 添付 に現れる PR URL
  jq -r '[ .result.issue.description // "",
           ((.result.comments // []) | map(.body) | join("\n")),
           ((.result.attachments // []) | map(.url) | join("\n")) ] | join("\n")' \
      "$PACKET/linear/issue.json" \
    | grep -oE 'https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/pull/[0-9]+' \
    | sed -E 's#https://github\.com/([^/]+)/([^/]+)/pull/([0-9]+)#\1 \2 \3#' \
    | sort -u \
    | while read -r o r n; do add_cand "$o" "$r" "$n" "linear text/attachment"; done || true

  # 4c. Orca 登録リポジトリを横断して、identifier / branch 名で探す
  IDENT_LC="$(printf '%s' "$IDENT" | tr 'A-Z' 'a-z')"
  BRANCH_LC="$(printf '%s' "$BRANCHNAME" | tr 'A-Z' 'a-z')"
  if ! evidence_capture github.repo-scan "$PACKET/github/repositories.json" true "$IDENT" "$ORCA_BIN" repo list --json; then
    blocked "Orca 登録 repository の取得に失敗した。候補無しとは扱わない。"
  fi
  jq -e '.result.repos | type == "array"' "$PACKET/github/repositories.json" >/dev/null \
    || blocked "Orca 登録 repository の応答が不正。候補無しとは扱わない。"
  jq -r '.result.repos[]? | select(.gitRemoteIdentity != null)
             | select(.gitRemoteIdentity.canonicalKey | startswith("github.com/"))
             | .gitRemoteIdentity.canonicalKey' \
    "$PACKET/github/repositories.json" \
    | sed 's#^github\.com/##' | sort -u > "$PACKET/github/.repos"
  while IFS= read -r slug; do
    [ -n "$slug" ] || continue
    SCAN_FILE="$PACKET/github/scan-${slug//\//-}.json"
    if ! evidence_capture "github.scan.$slug" "$SCAN_FILE" true "$slug" gh pr list --repo "$slug" --state all --limit 200 \
        --json number,headRefName,title,body,url; then continue; fi
    if ! jq -e 'type == "array" and length < 200' "$SCAN_FILE" >/dev/null; then
      evidence_invalid "github.scan.$slug" "$SCAN_FILE" true "$slug" "malformed or capped PR search; specify --pr"
      continue
    fi
    jq -r --arg id "$IDENT_LC" --arg br "$BRANCH_LC" --arg slug "$slug" '
          .[]
          | select(
              ((.headRefName // "") | ascii_downcase | contains($id))
              or (($br != "") and (((.headRefName // "") | ascii_downcase) == $br))
              or ((.title // "") | ascii_downcase | contains($id))
              or ((.body  // "") | ascii_downcase | contains($id))
            )
          | "\($slug)\t\(.number)"' "$SCAN_FILE" \
      | while IFS=$'\t' read -r s n; do
          add_cand "${s%%/*}" "${s#*/}" "$n" "repo scan (${s})"
        done
  done < "$PACKET/github/.repos"
fi

jq -s 'group_by(.owner + "/" + .repo + "#" + (.number|tostring))
       | map({owner: .[0].owner, repo: .[0].repo, number: .[0].number,
              evidence: (map(.source) | unique)})' \
   "$PACKET/github/.cand.raw" > "$CAND" || blocked "PR 候補の集約に失敗した。候補無しとは扱わない。"
rm -f "$PACKET/github/.cand.raw"

N_CAND="$(jq 'length' "$CAND")"
if [ "$N_CAND" -eq 0 ]; then
  blocked "${IDENT} から対象 PR を特定できなかった。Linear の本文・コメント・添付に GitHub PR の URL が無く、Orca 登録リポジトリ（$(tr '\n' ' ' < "$PACKET/github/.repos" 2>/dev/null))の PR にも identifier '${IDENT}' / branch '${BRANCHNAME}' との対応が見つからない。推測で進めない。対象 PR が分かっているなら --pr owner/repo#N で明示して再実行する。"
fi
if [ "$N_CAND" -gt "$MAX_PR_CANDIDATES" ]; then
  blocked "${IDENT} に対する PR 候補が ${N_CAND} 件あり、絞り込めない。推測で進めない。--pr owner/repo#N で明示して再実行する。候補: $(jq -r 'map("\(.owner)/\(.repo)#\(.number)") | join(", ")' "$CAND")"
fi

}

# Fetch exact commit objects, including base; refs that move are never used as evidence.
prepare_source() { # local_path slug number src head base
  local local_path="$1" slug="$2" number="$3" src="$4" head="$5" base="$6" sha actual merge_base
  if [ -n "$local_path" ] && git -C "$local_path" rev-parse --git-dir >/dev/null 2>&1; then
    git clone --quiet --no-hardlinks --no-checkout "$local_path" "$src" || return
  else
    gh repo clone "$slug" "$src" -- --quiet --no-checkout || return
  fi
  git -C "$src" remote set-url origin "https://github.com/${slug}.git" || return
  for sha in "$head" "$base"; do
    if ! git -C "$src" cat-file -e "${sha}^{commit}" 2>/dev/null; then
      git -C "$src" fetch --quiet origin "$sha" || return
    fi
    git -C "$src" cat-file -e "${sha}^{commit}" || return
  done
  git -C "$src" checkout --quiet --detach "$head" || return
  actual="$(git -C "$src" rev-parse HEAD)" || return
  [ "$actual" = "$head" ] || return 1
  git -C "$src" update-ref refs/inreview/base "$base" || return
  merge_base="$(git -C "$src" merge-base "$base" "$head")" || return
  [[ "$merge_base" =~ ^[a-fA-F0-9]{40}$ ]] || return 1
  jq -cn --arg slug "$slug" --argjson number "$number" --arg head "$head" --arg base "$base" --arg merge "$merge_base" \
    '{repository:$slug,number:$number,headSha:$head,baseSha:$base,mergeBaseSha:$merge}'
}

source_commits() { # src base head
  git -C "$1" log --format='%H' "$2..$3" | jq -Rsc 'split("\n") | map(select(length > 0))'
}

fetch_pr_snapshot() { # directory phase
  local dir="$1" phase="$2" path
  path="$dir/pr-${phase}.json"
  if ! evidence_capture "${SLUG}#${N}.snapshot.${phase}" "$path" true "${SLUG}#${N}" \
      gh pr view "$N" --repo "$SLUG" --json "$PR_FIELDS"; then
    blocked "${SLUG}#${N} の現在の PR を再取得できない。更新の有無を確認できないため停止した。診断: ${path}.err"
  fi
  if ! python3 "$LIB_ROOT/evidence.py" same-pr "$dir/pr.json" "$path"; then
    evidence_invalid "${SLUG}#${N}.snapshot.${phase}" "$path" true "${SLUG}#${N}" "PR changed during acquisition/review"
    blocked "${SLUG}#${N} の head / base / 状態 / 更新時刻が取得中またはレビュー中に変わった。混在した証拠で判定せず、新しいパケットで再実行する。"
  fi
}

validate_threads() { # file
  jq -e '
    (.errors // [] | length) == 0 and
    (.data.repository.pullRequest.reviewThreads | type == "object") and
    (.data.repository.pullRequest.reviewThreads.nodes | type == "array") and
    .data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage == false and
    all(.data.repository.pullRequest.reviewThreads.nodes[];
      (.isResolved | type == "boolean") and (.isOutdated | type == "boolean") and
      (.comments.nodes | type == "array") and .comments.pageInfo.hasNextPage == false)
  ' "$1" >/dev/null 2>&1
}

fetch_github() {
  PR_FIELDS='number,title,body,state,isDraft,url,headRefName,baseRefName,headRefOid,baseRefOid,mergeable,mergeStateStatus,additions,deletions,changedFiles,files,commits,labels,reviews,reviewDecision,statusCheckRollup,comments,author,createdAt,updatedAt,closedAt,mergedAt'
  PRIMARY_SRC=""
  for i in $(seq 0 $((N_CAND - 1))); do
    O="$(jq -r ".[$i].owner" "$CAND")"; R="$(jq -r ".[$i].repo" "$CAND")"; N="$(jq -r ".[$i].number" "$CAND")"
    SLUG="$O/$R"; D="$PACKET/github/pr-${O}-${R}-${N}"
    [ ! -e "$D" ] || blocked "PR のパケット保存先が別候補と衝突した。--pr で対象を1件に絞る。"
    mkdir -p "$D"
    if ! evidence_capture "${SLUG}#${N}.pr" "$D/pr.json" true "${SLUG}#${N}" gh pr view "$N" --repo "$SLUG" --json "$PR_FIELDS"; then
      continue
    fi
    if ! jq -e --argjson n "$N" --arg url "https://github.com/$SLUG/pull/$N" '
      .number == $n and .url == $url and
      (.headRefOid | type == "string" and test("^[a-fA-F0-9]{40}$")) and
      (.baseRefOid | type == "string" and test("^[a-fA-F0-9]{40}$")) and
      (.changedFiles | type == "number" and . >= 0 and . == floor) and
      (.baseRefName | type == "string" and length > 0) and
      (.commits | type == "array")' "$D/pr.json" >/dev/null 2>&1; then
      evidence_invalid "${SLUG}#${N}.pr" "$D/pr.json" true "${SLUG}#${N}" "malformed PR identity/full head or base SHA"
      blocked "${SLUG}#${N} の PR 情報または full head / base SHA が不正。固定した証拠を確認できないため停止した。"
    fi
    HEAD_SHA="$(jq -r '.headRefOid' "$D/pr.json")"; BASE_SHA="$(jq -r '.baseRefOid' "$D/pr.json")"
    SCOPE="${SLUG}#${N} base=${BASE_SHA} head=${HEAD_SHA}"
    LOCAL_PATH=""
    if evidence_capture "${SLUG}#${N}.local-repos" "$D/local-repos.json" false "$SLUG" "$ORCA_BIN" repo list --json; then
      LOCAL_PATH="$(jq -r --arg key "github.com/$SLUG" '.result.repos[]? | select(.gitRemoteIdentity.canonicalKey == $key) | .path' "$D/local-repos.json" | head -1)"
    fi
    SRC="$D/src"
    if ! evidence_capture "${SLUG}#${N}.source" "$D/source.json" true "$SCOPE" prepare_source "$LOCAL_PATH" "$SLUG" "$N" "$SRC" "$HEAD_SHA" "$BASE_SHA"; then
      blocked "${SLUG}#${N} のクローンを固定 head SHA ${HEAD_SHA} と base SHA ${BASE_SHA} へ揃えられなかった。別 SHA のソースでレビューを続けない。診断: ${D}/source.json.err"
    fi
    [ -n "$PRIMARY_SRC" ] || PRIMARY_SRC="$SRC"
    # These artifacts are derived from verified immutable objects, not the live PR ref.
    evidence_capture "${SLUG}#${N}.diff" "$D/diff.patch" true "$SCOPE" \
      git -C "$SRC" diff --binary "$BASE_SHA...$HEAD_SHA" || true
    if evidence_capture "${SLUG}#${N}.files" "$D/files.json" true "$SCOPE" \
        python3 "$LIB_ROOT/evidence.py" files "$SRC" "$BASE_SHA" "$HEAD_SHA"; then
      if ! jq -e --argjson expected "$(jq '.changedFiles' "$D/pr.json")" 'type == "array" and length == $expected' "$D/files.json" >/dev/null; then
        evidence_invalid "${SLUG}#${N}.files" "$D/files.json" true "$SCOPE" "local diff file count differs from PR changedFiles"
      fi
    fi
    evidence_capture "${SLUG}#${N}.commits" "$D/commits.json" true "$SCOPE" \
      source_commits "$SRC" "$BASE_SHA" "$HEAD_SHA" || true
    if evidence_capture "${SLUG}#${N}.check-runs" "$D/check-runs.json" true "$SCOPE" \
        gh api --paginate --slurp "repos/${SLUG}/commits/${HEAD_SHA}/check-runs?per_page=100&filter=latest"; then
      : # normalization below requires both endpoints
    fi
    if evidence_capture "${SLUG}#${N}.statuses" "$D/statuses.json" true "$SCOPE" \
        gh api --paginate --slurp "repos/${SLUG}/commits/${HEAD_SHA}/status?per_page=100"; then
      :
    fi
    evidence_capture "${SLUG}#${N}.checks" "$D/checks.json" true "$SCOPE" \
      python3 "$LIB_ROOT/evidence.py" checks "$D/check-runs.json" "$D/statuses.json" "$HEAD_SHA" || true
    fetch_test_jobs "$D" "$HEAD_SHA" ""
    if evidence_capture "${SLUG}#${N}.required-checks" "$D/required-checks.json" true "$SCOPE" gh pr checks "$N" --repo "$SLUG" --required --json name,state,bucket,link,workflow,completedAt; then
      evidence_capture "${SLUG}#${N}.verification" "$D/verification.json" true "$SCOPE" \
        python3 "$LIB_ROOT/evidence.py" verification "$D/checks.json" "$D/required-checks.json" "$PACKET/verification-policy.json" "$D/workflow-jobs.json" || true
    fi
    if evidence_capture "${SLUG}#${N}.review-threads" "$D/review-threads.json" true "$SCOPE" \
      gh api graphql -F owner="$O" -F name="$R" -F number="$N" -f query='
        query($owner:String!,$name:String!,$number:Int!){ repository(owner:$owner,name:$name){ pullRequest(number:$number){
          reviewDecision
          reviewThreads(first:100){ pageInfo{hasNextPage} nodes{
            isResolved isOutdated isCollapsed path line startLine
            comments(first:100){ pageInfo{hasNextPage} nodes{author{login} body createdAt url} }
          } }
        } } }'; then
      validate_threads "$D/review-threads.json" \
        || evidence_invalid "${SLUG}#${N}.review-threads" "$D/review-threads.json" true "$SCOPE" "malformed GraphQL response or truncated review threads/comments"
    fi
    fetch_pr_snapshot "$D" acquired
  done
  if [ "$N_CAND" -eq 1 ] && [ -n "$PRIMARY_SRC" ]; then
    ln -sfn "$PRIMARY_SRC" "$PACKET/src"
  fi
  fetch_workflow_runs
  recheck_linear acquired
}

fetch_test_jobs() { # directory head suffix; snapshots belong to current check-run job IDs
  local dir="$1" head="$2" suffix="$3" rid run_files=() run_scope
  run_scope="${SLUG}#${N} head=${head}${suffix}"
  if ! evidence_capture "${SLUG}#${N}.action-runs${suffix}" "$dir/action-runs${suffix}.txt" true "$run_scope" \
    python3 "$LIB_ROOT/evidence.py" action-runs "$dir/checks${suffix}.json" "$SLUG"; then return; fi
  while IFS= read -r rid; do
    [ -n "$rid" ] || continue
    run_files+=("$dir/workflow-run-${rid}${suffix}.json")
    evidence_capture "${SLUG}#${N}.workflow-run.${rid}${suffix}" "$dir/workflow-run-${rid}${suffix}.json" true "$run_scope run=$rid" \
      gh run view "$rid" --repo "$SLUG" --json databaseId,headSha,attempt,url,jobs || true
  done < "$dir/action-runs${suffix}.txt"
  if [ "${#run_files[@]}" -gt 0 ]; then jq -s '.' "${run_files[@]}" > "$dir/workflow-runs${suffix}.json"
  else printf '[]\n' > "$dir/workflow-runs${suffix}.json"; fi
  evidence_capture "${SLUG}#${N}.workflow-jobs${suffix}" "$dir/workflow-jobs${suffix}.json" true "$run_scope" \
    python3 "$LIB_ROOT/evidence.py" workflow-jobs "$dir/workflow-runs${suffix}.json" "$dir/checks${suffix}.json" "$head" "$SLUG" || true
}

fetch_workflow_runs() {
  local spec rslug rid rd run_sha
  for spec in "${EXPLICIT_RUNS[@]:-}"; do
    [ -n "$spec" ] || continue
    rslug="${spec%:*}"; rid="${spec##*:}"; rd="$PACKET/github/runs/${rslug//\//-}-${rid}"
    mkdir -p "$rd"
    if ! evidence_capture "run.${spec}.metadata" "$rd/run.json" true "$spec" gh api "repos/${rslug}/actions/runs/${rid}"; then continue; fi
    if ! jq -e --argjson id "$rid" --arg repo "$rslug" '.id == $id and .repository.full_name == $repo and (.head_sha | type == "string" and test("^[a-fA-F0-9]{40}$"))' "$rd/run.json" >/dev/null; then
      evidence_invalid "run.${spec}.metadata" "$rd/run.json" true "$spec" "run identity/head SHA mismatch"
      continue
    fi
    run_sha="$(jq -r '.head_sha' "$rd/run.json")"
    if evidence_capture "run.${spec}.jobs" "$rd/jobs.json" true "$spec head=$run_sha" \
      gh api --paginate --slurp "repos/${rslug}/actions/runs/${rid}/jobs?per_page=100"; then
      if jq -e --arg sha "$run_sha" --argjson id "$rid" '
          [.[].jobs[]] as $jobs |
          type == "array" and length > 0 and all(.[]; (.jobs | type == "array")) and
          all(.[]; .total_count == ($jobs | length)) and
          all($jobs[]; .head_sha == $sha and .run_id == $id)' "$rd/jobs.json" >/dev/null; then
        jq -c '.[].jobs[] | {id,name,status,conclusion,started_at,completed_at,head_sha,steps}' "$rd/jobs.json" > "$rd/jobs.jsonl"
      else evidence_invalid "run.${spec}.jobs" "$rd/jobs.json" true "$spec" "incomplete jobs or head/run mismatch"; fi
    fi
    evidence_capture "run.${spec}.log" "$rd/log.txt" true "$spec head=$run_sha" gh run view "$rid" -R "$rslug" --log || true
    # A failed command can still emit a partial log. Sanitize both streams before leaving a packet behind.
    for run_log_path in "$rd/log.txt" "$rd/log.txt.err"; do
      if [ -s "$run_log_path" ] && grep -q -E 'postgres(ql)?://[^*[:space:]]+:[^*@[:space:]]+@|sbp_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}' "$run_log_path"; then
        rm -f "$run_log_path"
        evidence_invalid "run.${spec}.log" "$run_log_path" true "$spec" "log removed because it may contain a secret; owner investigation required"
      fi
    done
  done
}

recheck_github() { # before any result is accepted
  local i
  for i in $(seq 0 $((N_CAND - 1))); do
    O="$(jq -r ".[$i].owner" "$CAND")"; R="$(jq -r ".[$i].repo" "$CAND")"; N="$(jq -r ".[$i].number" "$CAND")"; SLUG="$O/$R"
    fetch_pr_snapshot "$PACKET/github/pr-${O}-${R}-${N}" final
    recheck_ci "$PACKET/github/pr-${O}-${R}-${N}"
    fetch_pr_snapshot "$PACKET/github/pr-${O}-${R}-${N}" final-ci
  done
}

recheck_ci() { # directory
  local dir="$1" head scope
  head="$(jq -r '.headRefOid' "$dir/pr.json")"; scope="${SLUG}#${N} head=${head} final"
  evidence_capture "${SLUG}#${N}.check-runs.final" "$dir/check-runs-final.json" true "$scope" \
    gh api --paginate --slurp "repos/${SLUG}/commits/${head}/check-runs?per_page=100&filter=latest" || true
  evidence_capture "${SLUG}#${N}.statuses.final" "$dir/statuses-final.json" true "$scope" \
    gh api --paginate --slurp "repos/${SLUG}/commits/${head}/status?per_page=100" || true
  evidence_capture "${SLUG}#${N}.checks.final" "$dir/checks-final.json" true "$scope" \
    python3 "$LIB_ROOT/evidence.py" checks "$dir/check-runs-final.json" "$dir/statuses-final.json" "$head" || true
  fetch_test_jobs "$dir" "$head" -final
  evidence_capture "${SLUG}#${N}.required-checks.final.required-checks" "$dir/required-checks-final.json" true "$scope" \
    gh pr checks "$N" --repo "$SLUG" --required --json name,state,bucket,link,workflow,completedAt || true
  if evidence_capture "${SLUG}#${N}.verification.final" "$dir/verification-final.json" true "$scope" \
    python3 "$LIB_ROOT/evidence.py" verification "$dir/checks-final.json" "$dir/required-checks-final.json" "$PACKET/verification-policy.json" "$dir/workflow-jobs-final.json"; then
    if ! python3 "$LIB_ROOT/evidence.py" same-verification "$dir/verification.json" "$dir/verification-final.json"; then
      evidence_invalid "${SLUG}#${N}.verification.final" "$dir/verification-final.json" true "$scope" "CI or test evidence changed during review"
    fi
  fi
}
