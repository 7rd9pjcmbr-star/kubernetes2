#!/usr/bin/env bash
# Sequential master pipeline wrapper.
# Usage:
#   ./run_pipeline.sh
#   ./run_pipeline.sh --force-clean --force-telegram
#   ./run_pipeline.sh --steps clean,credentials,scanner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PIPELINE_ENV_FILE:-$SCRIPT_DIR/.env.vn-platforms}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

exec python3 "$SCRIPT_DIR/run_pipeline.py" "$@"
