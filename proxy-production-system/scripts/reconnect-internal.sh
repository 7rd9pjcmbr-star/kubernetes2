#!/usr/bin/env bash
set -euo pipefail

# Reconnect internal proxy to configured upstream(s).
# Usage:
#   ./scripts/reconnect-internal.sh
#   ./scripts/reconnect-internal.sh --check-only

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=1
fi

if [[ ! -f .env ]]; then
  echo "Creating .env from internal profile..."
  cp .env.internal.example .env
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

UPSTREAMS="${PROXY_UPSTREAMS:-}"
if [[ -z "$UPSTREAMS" ]]; then
  echo "PROXY_UPSTREAMS is empty. Set it in .env"
  exit 1
fi

LISTEN="${PROXY_LISTEN_ADDRESS:-:8080}"
INSECURE="${PROXY_INSECURE_SKIP_VERIFY:-false}"

echo "========================================"
echo " Internal proxy reconnect"
echo "========================================"
echo " listen:    ${LISTEN}"
echo " upstreams: ${UPSTREAMS}"
echo " tls_skip:  ${INSECURE}"
echo

ok_any=0
IFS=',' read -r -a upstream_list <<< "$UPSTREAMS"
for raw in "${upstream_list[@]}"; do
  upstream="$(echo "$raw" | xargs)"
  [[ -z "$upstream" ]] && continue

  echo "Checking upstream: ${upstream}"
  curl_opts=(-sS -o /tmp/proxy-reconnect-body -w '%{http_code}' --connect-timeout 5 --max-time 12)
  if [[ "$INSECURE" == "true" ]] || [[ "$upstream" == https://* ]]; then
    # Internal/self-signed endpoints often need -k when skip-verify is enabled.
    if [[ "$INSECURE" == "true" ]]; then
      curl_opts+=(-k)
    fi
  fi

  code="$(curl "${curl_opts[@]}" "$upstream" || true)"
  if [[ "$code" =~ ^[23][0-9][0-9]$ ]]; then
    echo "  [OK] HTTP ${code}"
    ok_any=1
  else
    echo "  [WARN] unreachable or unexpected status=${code:-000}"
    echo "         Ensure VPN/LAN access to this host from your machine."
  fi
done

echo
if [[ "$ok_any" -eq 0 ]]; then
  echo "[WARN] No upstream responded from this environment."
  echo "If you are on the correct VPN/LAN, continue starting local proxy anyway."
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "Check-only mode complete."
  exit 0
fi

echo "Building proxy binary..."
GOWORK=off CGO_ENABLED=0 go build -o bin/proxy ./cmd/proxy

# Free previous listener if still held.
listen_port="${LISTEN#:}"
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${listen_port}/tcp" >/dev/null 2>&1 || true
fi

echo
echo "Starting proxy..."
echo "  Health: curl -i http://127.0.0.1${LISTEN}/healthz"
echo "  Proxy:  curl -i http://127.0.0.1${LISTEN}/"
echo "  Path:   curl -i http://127.0.0.1${LISTEN}/config.html"
echo
exec ./bin/proxy
