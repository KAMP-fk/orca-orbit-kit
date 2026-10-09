#!/usr/bin/env bash
set -euo pipefail

script_path="${BASH_SOURCE[0]}"
while [[ -L "$script_path" ]]; do
  script_dir="$(cd "$(dirname "$script_path")" && pwd)"
  script_path="$(readlink "$script_path")"
  [[ "$script_path" = /* ]] || script_path="$script_dir/$script_path"
done
script_dir="$(cd "$(dirname "$script_path")" && pwd)"

repo_dir="${1:-$PWD}"
act_args=(push -j validate -W .github/workflows/ci.yml)
if [[ "${2:-}" == "--dry-run" ]]; then
  act_args+=(-n)
elif [[ -n "${2:-}" ]]; then
  echo "Usage: $0 /absolute/path/to/concafe-techo-worktree [--dry-run]" >&2
  exit 2
fi
if [[ ! -f "$repo_dir/.github/workflows/ci.yml" ]]; then
  echo "Usage: $0 /absolute/path/to/concafe-techo-worktree [--dry-run]" >&2
  exit 2
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop を起動してから再実行してください。" >&2
  exit 2
fi

if ! docker image inspect concafe-act:local-arm64 >/dev/null 2>&1; then
  docker build --platform linux/arm64 -t concafe-act:local-arm64 \
    -f "$script_dir/CONCAFE-ACT.Dockerfile" "$script_dir"
fi

cd "$repo_dir"
exec act "${act_args[@]}" \
  -P ubuntu-latest=concafe-act:local-arm64 \
  --container-architecture linux/arm64 \
  --container-daemon-socket - \
  --secret-file /dev/null --env-file /dev/null --var-file /dev/null \
  --pull=false --action-offline-mode
