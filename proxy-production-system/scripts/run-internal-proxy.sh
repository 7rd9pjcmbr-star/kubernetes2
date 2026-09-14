#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — creating from internal profile."
  cp .env.internal.example .env
  echo "Edit .env if you need PROXY_UPSTREAM_BASIC_AUTH=user:password"
fi

# Load env without exporting comments/empty lines.
set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ -z "${PROXY_UPSTREAMS:-}" ]]; then
  echo "PROXY_UPSTREAMS is required in .env"
  exit 1
fi

echo "Building proxy..."
GOWORK=off CGO_ENABLED=0 go build -o bin/proxy ./cmd/proxy

echo "Starting internal proxy"
echo "  listen:    ${PROXY_LISTEN_ADDRESS:-:8080}"
echo "  upstreams: ${PROXY_UPSTREAMS}"
echo "  tls_skip:  ${PROXY_INSECURE_SKIP_VERIFY:-false}"
echo "  basic_auth_enabled: $([[ -n "${PROXY_UPSTREAM_BASIC_AUTH:-}" ]] && echo true || echo false)"
echo
echo "Probe: curl -i http://127.0.0.1${PROXY_LISTEN_ADDRESS:-:8080}/healthz"
echo "Proxy: curl -i http://127.0.0.1${PROXY_LISTEN_ADDRESS:-:8080}/"
echo

exec ./bin/proxy
