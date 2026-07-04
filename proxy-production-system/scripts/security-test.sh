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

run_step "Race checks" make test-race
run_step "Static analysis" make vet
run_step "Dependency vulnerability scan (govulncheck)" \
  env GOWORK=off go run golang.org/x/vuln/cmd/govulncheck@latest ./...

echo "==> Container runtime policy checks"
if ! rg --quiet 'distroless/static-debian12:nonroot' deployments/docker/Dockerfile; then
  echo "Dockerfile must use a non-root runtime image."
  exit 1
fi
if ! rg --quiet '^ENTRYPOINT \["/proxy"\]' deployments/docker/Dockerfile; then
  echo "Dockerfile entrypoint must be explicit for runtime predictability."
  exit 1
fi

echo "Security test suite passed."
