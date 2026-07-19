#!/usr/bin/env bash
set -euo pipefail

# Starts a local evaluation stack and keeps it running until Ctrl+C.
# Use this when you want to manually inspect proxy quality.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PROXY_PORT="${PROXY_PORT:-18080}"
UPSTREAM_A_PORT="${UPSTREAM_A_PORT:-18081}"
UPSTREAM_B_PORT="${UPSTREAM_B_PORT:-18082}"
AUTH_TOKEN="${AUTH_TOKEN:-eval-token}"

PIDS=()
cleanup() {
  echo
  echo "Stopping evaluation stack..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "==> Build evaluation binaries"
GOWORK=off CGO_ENABLED=0 go build -o bin/proxy ./cmd/proxy
GOWORK=off CGO_ENABLED=0 go build -o bin/eval-upstream ./cmd/eval-upstream

echo "==> Start upstreams"
LISTEN=":${UPSTREAM_A_PORT}" NAME=echo-a ./bin/eval-upstream > /tmp/proxy-eval-upstream-a.log 2>&1 &
PIDS+=($!)
LISTEN=":${UPSTREAM_B_PORT}" NAME=echo-b ./bin/eval-upstream > /tmp/proxy-eval-upstream-b.log 2>&1 &
PIDS+=($!)

echo "==> Start proxy"
PROXY_LISTEN_ADDRESS=":${PROXY_PORT}" \
PROXY_UPSTREAMS="http://127.0.0.1:${UPSTREAM_A_PORT},http://127.0.0.1:${UPSTREAM_B_PORT}" \
PROXY_AUTH_TOKEN="${AUTH_TOKEN}" \
PROXY_RATE_LIMIT_RPS=20 \
PROXY_RATE_LIMIT_BURST=40 \
PROXY_REQUEST_TIMEOUT=10s \
PROXY_LOG_FORMAT=json \
PROXY_SERVICE_NAME=proxy-eval \
./bin/proxy > /tmp/proxy-eval-proxy.log 2>&1 &
PIDS+=($!)

for i in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PROXY_PORT}/readyz" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 40 ]]; then
    cat /tmp/proxy-eval-proxy.log || true
    echo "proxy failed to start"
    exit 1
  fi
  sleep 0.25
done

cat <<EOF

Evaluation stack is running.

  Health:   curl -i http://127.0.0.1:${PROXY_PORT}/healthz
  Ready:    curl -i http://127.0.0.1:${PROXY_PORT}/readyz
  Version:  curl -s http://127.0.0.1:${PROXY_PORT}/version
  Metrics:  curl -s http://127.0.0.1:${PROXY_PORT}/metrics | head
  Proxy:    curl -i -H "X-Proxy-Token: ${AUTH_TOKEN}" http://127.0.0.1:${PROXY_PORT}/

Logs:
  /tmp/proxy-eval-proxy.log
  /tmp/proxy-eval-upstream-a.log
  /tmp/proxy-eval-upstream-b.log

Press Ctrl+C to stop.
EOF

wait
