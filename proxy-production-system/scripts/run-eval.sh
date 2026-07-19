#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PROXY_PORT="${PROXY_PORT:-18080}"
UPSTREAM_A_PORT="${UPSTREAM_A_PORT:-18081}"
UPSTREAM_B_PORT="${UPSTREAM_B_PORT:-18082}"
AUTH_TOKEN="${AUTH_TOKEN:-eval-token}"
BASE_URL="http://127.0.0.1:${PROXY_PORT}"

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

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
PROXY_RATE_LIMIT_RPS=5 \
PROXY_RATE_LIMIT_BURST=5 \
PROXY_REQUEST_TIMEOUT=5s \
PROXY_LOG_FORMAT=json \
PROXY_SERVICE_NAME=proxy-eval \
./bin/proxy > /tmp/proxy-eval-proxy.log 2>&1 &
PIDS+=($!)

echo "==> Wait for readiness"
for i in $(seq 1 40); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 40 ]]; then
    echo "Proxy logs:"
    cat /tmp/proxy-eval-proxy.log || true
    fail "proxy did not become ready"
  fi
  sleep 0.25
done
pass "proxy ready at ${BASE_URL}"

echo "==> Functional checks"
code="$(curl -s -o /tmp/proxy-eval-healthz.body -w '%{http_code}' "${BASE_URL}/healthz")"
[[ "$code" == "200" ]] || fail "/healthz expected 200 got ${code}"
pass "/healthz => 200"

code="$(curl -s -o /tmp/proxy-eval-version.body -w '%{http_code}' "${BASE_URL}/version")"
[[ "$code" == "200" ]] || fail "/version expected 200 got ${code}"
pass "/version => 200"

code="$(curl -s -o /tmp/proxy-eval-metrics.body -w '%{http_code}' "${BASE_URL}/metrics")"
[[ "$code" == "200" ]] || fail "/metrics expected 200 got ${code}"
grep -q "proxy_requests_total" /tmp/proxy-eval-metrics.body || fail "/metrics missing proxy_requests_total"
pass "/metrics exposes proxy_requests_total"

code="$(curl -s -o /tmp/proxy-eval-unauth.body -w '%{http_code}' "${BASE_URL}/")"
[[ "$code" == "401" ]] || fail "missing token expected 401 got ${code}"
pass "auth rejects missing token with 401"

bodies=()
for i in 1 2 3 4; do
  body="$(curl -fsS -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/")"
  bodies+=("$body")
done
[[ "${bodies[0]}" == "echo-a" && "${bodies[1]}" == "echo-b" && "${bodies[2]}" == "echo-a" && "${bodies[3]}" == "echo-b" ]] \
  || fail "round-robin unexpected sequence: ${bodies[*]}"
pass "round-robin distributes echo-a/echo-b"

limited=0
for i in $(seq 1 20); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/")"
  if [[ "$code" == "429" ]]; then
    limited=1
    break
  fi
done
[[ "$limited" == "1" ]] || fail "rate limit did not return 429 under burst traffic"
pass "rate limit returns 429 when burst exceeded"

headers="$(curl -sI -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/healthz")"
echo "$headers" | rg -qi "X-Content-Type-Options:\s*nosniff" || fail "missing X-Content-Type-Options"
echo "$headers" | rg -qi "X-Frame-Options:\s*DENY" || fail "missing X-Frame-Options"
pass "security headers present"

echo
echo "========================================"
echo " EVALUATION PASSED - product is runnable"
echo " Base URL: ${BASE_URL}"
echo " Auth header: X-Proxy-Token: ${AUTH_TOKEN}"
echo " Logs: /tmp/proxy-eval-*.log"
echo "========================================"
echo
echo "For interactive evaluation, run:"
echo "  ./scripts/start-eval-stack.sh"
echo

HOLD_SECONDS="${EVAL_HOLD_SECONDS:-0}"
if [[ "${HOLD_SECONDS}" != "0" ]]; then
  echo "Holding stack for ${HOLD_SECONDS}s for manual inspection..."
  sleep "${HOLD_SECONDS}"
fi
