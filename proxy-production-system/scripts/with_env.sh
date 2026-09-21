#!/usr/bin/env bash
# Usage: scripts/with_env.sh python3 scripts/platforms_login_sapo_playwright.py ...
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eval "$(python3 "${ROOT}/scripts/load_env.py" --shell)"
exec "$@"
