#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

run_step() {
  local name="$1"
  shift
  echo "==> $name"
  "$@"
}

run_step "Format check" make fmt-check
run_step "Unit and integration tests" make test
run_step "Race detector tests" make test-race
run_step "Static analysis (go vet)" make vet
run_step "Build artifact" make build

echo "Quality gate passed."
