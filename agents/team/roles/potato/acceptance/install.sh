#!/usr/bin/env bash
# Acceptance pipeline shares the canonical team installer.
set -euo pipefail
REVIEW_INSTALL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$REVIEW_INSTALL_ROOT/../../../install.py" "$@"
