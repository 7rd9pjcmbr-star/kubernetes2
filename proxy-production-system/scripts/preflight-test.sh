#!/usr/bin/env bash
set -euo pipefail

# Preflight test: bắt buộc PASS trước khi đưa proxy vào môi trường thật.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

REPORT_DIR="${REPORT_DIR:-/tmp/proxy-preflight}"
REPORT_FILE="${REPORT_DIR}/preflight-report.txt"
PROXY_PORT="${PROXY_PORT:-18180}"
UPSTREAM_A_PORT="${UPSTREAM_A_PORT:-18181}"
UPSTREAM_B_PORT="${UPSTREAM_B_PORT:-18182}"
SLOW_UPSTREAM_PORT="${SLOW_UPSTREAM_PORT:-18183}"
AUTH_TOKEN="${AUTH_TOKEN:-preflight-token}"
BASE_URL="http://127.0.0.1:${PROXY_PORT}"

mkdir -p "${REPORT_DIR}"
: > "${REPORT_FILE}"

PIDS=()
PASS_COUNT=0
FAIL_COUNT=0

log() {
  echo "$*" | tee -a "${REPORT_FILE}"
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  log "[PASS] $*"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  log "[FAIL] $*"
}

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

section() {
  log ""
  log "==> $*"
}

expect_code() {
  local name="$1"
  local expected="$2"
  local code="$3"
  if [[ "$code" == "$expected" ]]; then
    pass "${name} => ${code}"
  else
    fail "${name} expected ${expected} got ${code}"
  fi
}

log "Proxy Preflight Test"
log "Started at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Report: ${REPORT_FILE}"

section "1) Quality gate"
if ./scripts/quality-gate.sh >>"${REPORT_FILE}" 2>&1; then
  pass "quality-gate"
else
  fail "quality-gate"
fi

section "2) Security suite"
if ./scripts/security-test.sh >>"${REPORT_FILE}" 2>&1; then
  pass "security-test"
else
  fail "security-test"
fi

section "3) Build runtime binaries"
GOWORK=off CGO_ENABLED=0 go build -o bin/proxy ./cmd/proxy
GOWORK=off CGO_ENABLED=0 go build -o bin/eval-upstream ./cmd/eval-upstream
pass "build proxy + eval-upstream"

section "4) Start preflight stack"
LISTEN=":${UPSTREAM_A_PORT}" NAME=echo-a ./bin/eval-upstream >"${REPORT_DIR}/upstream-a.log" 2>&1 &
PIDS+=($!)
LISTEN=":${UPSTREAM_B_PORT}" NAME=echo-b ./bin/eval-upstream >"${REPORT_DIR}/upstream-b.log" 2>&1 &
PIDS+=($!)
LISTEN=":${SLOW_UPSTREAM_PORT}" NAME=slow DELAY_MS=3000 ./bin/eval-upstream >"${REPORT_DIR}/upstream-slow.log" 2>&1 &
PIDS+=($!)

PROXY_LISTEN_ADDRESS=":${PROXY_PORT}" \
PROXY_UPSTREAMS="http://127.0.0.1:${UPSTREAM_A_PORT},http://127.0.0.1:${UPSTREAM_B_PORT}" \
PROXY_AUTH_TOKEN="${AUTH_TOKEN}" \
PROXY_RATE_LIMIT_RPS=8 \
PROXY_RATE_LIMIT_BURST=8 \
PROXY_REQUEST_TIMEOUT=1s \
PROXY_LOG_FORMAT=json \
PROXY_SERVICE_NAME=proxy-preflight \
./bin/proxy >"${REPORT_DIR}/proxy.log" 2>&1 &
PIDS+=($!)

ready=0
for i in $(seq 1 50); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.2
done
if [[ "$ready" == "1" ]]; then
  pass "proxy ready at ${BASE_URL}"
else
  fail "proxy did not become ready"
  log "---- proxy.log ----"
  cat "${REPORT_DIR}/proxy.log" | tee -a "${REPORT_FILE}" || true
fi

section "5) Runtime functional checks"
code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/healthz")"
expect_code "/healthz" "200" "$code"

code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/readyz")"
expect_code "/readyz" "200" "$code"

code="$(curl -s -o "${REPORT_DIR}/version.json" -w '%{http_code}' "${BASE_URL}/version")"
expect_code "/version" "200" "$code"

code="$(curl -s -o "${REPORT_DIR}/metrics.txt" -w '%{http_code}' "${BASE_URL}/metrics")"
expect_code "/metrics" "200" "$code"
if rg -q "proxy_requests_total" "${REPORT_DIR}/metrics.txt"; then
  pass "metrics includes proxy_requests_total"
else
  fail "metrics missing proxy_requests_total"
fi

section "6) Security behavior checks"
code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/")"
expect_code "missing token" "401" "$code"

code="$(curl -s -o /dev/null -w '%{http_code}' -H "X-Proxy-Token: wrong-token" "${BASE_URL}/")"
expect_code "invalid token" "401" "$code"

headers="$(curl -sI "${BASE_URL}/healthz")"
if echo "$headers" | rg -qi "X-Content-Type-Options:\s*nosniff"; then
  pass "header X-Content-Type-Options=nosniff"
else
  fail "missing X-Content-Type-Options"
fi
if echo "$headers" | rg -qi "X-Frame-Options:\s*DENY"; then
  pass "header X-Frame-Options=DENY"
else
  fail "missing X-Frame-Options"
fi
if echo "$headers" | rg -qi "X-Request-Id:"; then
  pass "response includes X-Request-Id"
else
  fail "missing X-Request-Id"
fi

section "7) Proxy behavior checks"
bodies=()
for _ in 1 2 3 4; do
  bodies+=("$(curl -fsS -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/")")
done
if [[ "${bodies[0]}" == "echo-a" && "${bodies[1]}" == "echo-b" && "${bodies[2]}" == "echo-a" && "${bodies[3]}" == "echo-b" ]]; then
  pass "round-robin sequence echo-a/echo-b"
else
  fail "round-robin unexpected: ${bodies[*]}"
fi

limited=0
for _ in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/")"
  if [[ "$code" == "429" ]]; then
    limited=1
    break
  fi
done
if [[ "$limited" == "1" ]]; then
  pass "rate limit returns 429"
else
  fail "rate limit did not return 429"
fi

section "8) Timeout protection check"
# Restart proxy against slow upstream only.
cleanup
PIDS=()
LISTEN=":${SLOW_UPSTREAM_PORT}" NAME=slow DELAY_MS=3000 ./bin/eval-upstream >"${REPORT_DIR}/upstream-slow.log" 2>&1 &
PIDS+=($!)
PROXY_LISTEN_ADDRESS=":${PROXY_PORT}" \
PROXY_UPSTREAMS="http://127.0.0.1:${SLOW_UPSTREAM_PORT}" \
PROXY_AUTH_TOKEN="${AUTH_TOKEN}" \
PROXY_REQUEST_TIMEOUT=1s \
PROXY_LOG_FORMAT=json \
PROXY_SERVICE_NAME=proxy-preflight-timeout \
./bin/proxy >"${REPORT_DIR}/proxy-timeout.log" 2>&1 &
PIDS+=($!)

for i in $(seq 1 50); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

code="$(curl -s -o /dev/null -w '%{http_code}' -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/")"
expect_code "slow upstream timeout" "503" "$code"

section "9) Concurrent smoke"
cleanup
PIDS=()
LISTEN=":${UPSTREAM_A_PORT}" NAME=echo-a ./bin/eval-upstream >"${REPORT_DIR}/upstream-a.log" 2>&1 &
PIDS+=($!)
LISTEN=":${UPSTREAM_B_PORT}" NAME=echo-b ./bin/eval-upstream >"${REPORT_DIR}/upstream-b.log" 2>&1 &
PIDS+=($!)
PROXY_LISTEN_ADDRESS=":${PROXY_PORT}" \
PROXY_UPSTREAMS="http://127.0.0.1:${UPSTREAM_A_PORT},http://127.0.0.1:${UPSTREAM_B_PORT}" \
PROXY_AUTH_TOKEN="${AUTH_TOKEN}" \
PROXY_RATE_LIMIT_RPS=0 \
PROXY_RATE_LIMIT_BURST=0 \
PROXY_REQUEST_TIMEOUT=5s \
PROXY_LOG_FORMAT=json \
PROXY_SERVICE_NAME=proxy-preflight-concurrent \
./bin/proxy >"${REPORT_DIR}/proxy-concurrent.log" 2>&1 &
PIDS+=($!)

for i in $(seq 1 50); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

ok=0
fail_http=0
CONCURRENT_PIDS=()
for i in $(seq 1 40); do
  (
    code="$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' -H "X-Proxy-Token: ${AUTH_TOKEN}" "${BASE_URL}/" || echo 000)"
    echo "$code" >"${REPORT_DIR}/concurrent-${i}.code"
  ) &
  CONCURRENT_PIDS+=($!)
done
for pid in "${CONCURRENT_PIDS[@]}"; do
  wait "$pid" || true
done
for i in $(seq 1 40); do
  code="$(cat "${REPORT_DIR}/concurrent-${i}.code" 2>/dev/null || echo 000)"
  if [[ "$code" == "200" ]]; then
    ok=$((ok + 1))
  else
    fail_http=$((fail_http + 1))
  fi
done
if [[ "$ok" -ge 38 ]]; then
  pass "concurrent smoke ok=${ok}/40 fail=${fail_http}"
else
  fail "concurrent smoke too many failures ok=${ok}/40 fail=${fail_http}"
fi

section "Result"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
log "Passed: ${PASS_COUNT}"
log "Failed: ${FAIL_COUNT}"
log "Total checks: ${TOTAL}"
log "Finished at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "$FAIL_COUNT" -eq 0 ]]; then
  log ""
  log "========================================"
  log " PREFLIGHT PASSED - OK TO USE IN STAGING"
  log " Report: ${REPORT_FILE}"
  log "========================================"
  exit 0
fi

log ""
log "========================================"
log " PREFLIGHT FAILED - DO NOT USE IN PRODUCTION"
log " Report: ${REPORT_FILE}"
log "========================================"
exit 1
