#!/usr/bin/env bash

set -euo pipefail

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required but not found in PATH." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required but not found in PATH." >&2
  exit 1
fi

OUT_FILE="${1:-k8s-resource-audit.csv}"
EXCLUDE_NAMESPACES_REGEX="${EXCLUDE_NAMESPACES_REGEX:-^(kube-system|kube-public|kube-node-lease)$}"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
CLUSTER_CONTEXT="$(kubectl config current-context)"

CPU_TOP_FILE="$(mktemp)"
MEM_TOP_FILE="$(mktemp)"
trap 'rm -f "${CPU_TOP_FILE}" "${MEM_TOP_FILE}"' EXIT

# Metrics can be unavailable in some clusters; keep audit running with usage=0.
kubectl top pods -A --no-headers 2>/dev/null >"${CPU_TOP_FILE}" || true
cp "${CPU_TOP_FILE}" "${MEM_TOP_FILE}"

echo "timestamp,cluster,namespace,pod_count,cpu_request_m,cpu_limit_m,cpu_usage_m,cpu_usage_vs_request_pct,cpu_usage_vs_limit_pct,mem_request_mib,mem_limit_mib,mem_usage_mib,mem_usage_vs_request_pct,mem_usage_vs_limit_pct,missing_requests_limits_count,restart_count,oomkilled_count,quota_present,limitrange_present,status" >"${OUT_FILE}"

NAMESPACE_LIST="$(
  kubectl get namespaces -o jsonpath='{.items[*].metadata.name}' \
  | tr ' ' '\n' \
  | rg -v "${EXCLUDE_NAMESPACES_REGEX}" || true
)"

for namespace in ${NAMESPACE_LIST}; do
  pod_count="$(kubectl get pods -n "${namespace}" --no-headers 2>/dev/null | wc -l | tr -d ' ')"

  aggregate_json="$(
    kubectl get pods -n "${namespace}" -o json \
    | jq '
      def cpu_to_m:
        if . == null then 0
        elif test("n$") then (sub("n$";"") | tonumber / 1000000)
        elif test("u$") then (sub("u$";"") | tonumber / 1000)
        elif test("m$") then (sub("m$";"") | tonumber)
        else (tonumber * 1000)
        end;
      def mem_to_mib:
        if . == null then 0
        elif test("Ki$") then (sub("Ki$";"") | tonumber / 1024)
        elif test("Mi$") then (sub("Mi$";"") | tonumber)
        elif test("Gi$") then (sub("Gi$";"") | tonumber * 1024)
        elif test("Ti$") then (sub("Ti$";"") | tonumber * 1024 * 1024)
        elif test("Pi$") then (sub("Pi$";"") | tonumber * 1024 * 1024 * 1024)
        elif test("Ei$") then (sub("Ei$";"") | tonumber * 1024 * 1024 * 1024 * 1024)
        elif test("K$") then (sub("K$";"") | tonumber / 1000)
        elif test("M$") then (sub("M$";"") | tonumber)
        elif test("G$") then (sub("G$";"") | tonumber * 1000)
        elif test("T$") then (sub("T$";"") | tonumber * 1000 * 1000)
        elif test("P$") then (sub("P$";"") | tonumber * 1000 * 1000 * 1000)
        elif test("E$") then (sub("E$";"") | tonumber * 1000 * 1000 * 1000 * 1000)
        else (. | tonumber / (1024 * 1024))
        end;
      reduce .items[] as $pod (
        {cpu_req: 0, cpu_lim: 0, mem_req: 0, mem_lim: 0, missing: 0, restarts: 0, ooms: 0};
        .cpu_req += ([$pod.spec.containers[]?.resources.requests.cpu] | map(cpu_to_m) | add // 0) |
        .cpu_lim += ([$pod.spec.containers[]?.resources.limits.cpu] | map(cpu_to_m) | add // 0) |
        .mem_req += ([$pod.spec.containers[]?.resources.requests.memory] | map(mem_to_mib) | add // 0) |
        .mem_lim += ([$pod.spec.containers[]?.resources.limits.memory] | map(mem_to_mib) | add // 0) |
        .missing += (
          [$pod.spec.containers[]? |
            ((.resources.requests.cpu == null) or
             (.resources.requests.memory == null) or
             (.resources.limits.cpu == null) or
             (.resources.limits.memory == null))
          ] | map(select(. == true)) | length
        ) |
        .restarts += ([$pod.status.containerStatuses[]?.restartCount] | add // 0) |
        .ooms += (
          [$pod.status.containerStatuses[]? |
            select(.lastState.terminated.reason == "OOMKilled" or .state.terminated.reason == "OOMKilled")
          ] | length
        )
      )
    '
  )"

  cpu_request_m="$(jq -r '.cpu_req | floor' <<<"${aggregate_json}")"
  cpu_limit_m="$(jq -r '.cpu_lim | floor' <<<"${aggregate_json}")"
  mem_request_mib="$(jq -r '.mem_req | floor' <<<"${aggregate_json}")"
  mem_limit_mib="$(jq -r '.mem_lim | floor' <<<"${aggregate_json}")"
  missing_requests_limits_count="$(jq -r '.missing' <<<"${aggregate_json}")"
  restart_count="$(jq -r '.restarts' <<<"${aggregate_json}")"
  oomkilled_count="$(jq -r '.ooms' <<<"${aggregate_json}")"

  cpu_usage_m="$(
    awk -v n="${namespace}" '
      $1 == n {
        v=$3
        if (v ~ /m$/) {
          sub("m$", "", v)
          s += v
        } else if (v ~ /n$/) {
          sub("n$", "", v)
          s += v / 1000000
        } else if (v ~ /u$/) {
          sub("u$", "", v)
          s += v / 1000
        } else {
          s += v * 1000
        }
      }
      END { printf "%.0f", s + 0 }
    ' "${CPU_TOP_FILE}"
  )"

  mem_usage_mib="$(
    awk -v n="${namespace}" '
      $1 == n {
        v=$4
        if (v ~ /Ki$/) {
          sub("Ki$", "", v)
          s += v / 1024
        } else if (v ~ /Mi$/) {
          sub("Mi$", "", v)
          s += v
        } else if (v ~ /Gi$/) {
          sub("Gi$", "", v)
          s += v * 1024
        } else {
          s += v / (1024 * 1024)
        }
      }
      END { printf "%.0f", s + 0 }
    ' "${MEM_TOP_FILE}"
  )"

  cpu_usage_vs_request_pct="$(awk -v u="${cpu_usage_m}" -v r="${cpu_request_m}" 'BEGIN { if (r == 0) print "0.0"; else printf "%.1f", (u / r) * 100 }')"
  cpu_usage_vs_limit_pct="$(awk -v u="${cpu_usage_m}" -v l="${cpu_limit_m}" 'BEGIN { if (l == 0) print "0.0"; else printf "%.1f", (u / l) * 100 }')"
  mem_usage_vs_request_pct="$(awk -v u="${mem_usage_mib}" -v r="${mem_request_mib}" 'BEGIN { if (r == 0) print "0.0"; else printf "%.1f", (u / r) * 100 }')"
  mem_usage_vs_limit_pct="$(awk -v u="${mem_usage_mib}" -v l="${mem_limit_mib}" 'BEGIN { if (l == 0) print "0.0"; else printf "%.1f", (u / l) * 100 }')"

  quota_present="$([ "$(kubectl get resourcequota -n "${namespace}" --no-headers 2>/dev/null | wc -l)" -gt 0 ] && echo "true" || echo "false")"
  limitrange_present="$([ "$(kubectl get limitrange -n "${namespace}" --no-headers 2>/dev/null | wc -l)" -gt 0 ] && echo "true" || echo "false")"

  status="ok"
  if awk -v c="${cpu_usage_vs_request_pct}" -v m="${mem_usage_vs_request_pct}" 'BEGIN { exit !((c > 95) || (m > 95)) }'; then
    status="critical"
  elif awk -v c="${cpu_usage_vs_request_pct}" -v m="${mem_usage_vs_request_pct}" 'BEGIN { exit !((c >= 80) || (m >= 80)) }'; then
    status="warning"
  fi

  if [ "${oomkilled_count}" -gt 0 ]; then
    status="critical"
  elif [ "${status}" = "ok" ] && [ "${missing_requests_limits_count}" -gt 0 ]; then
    status="warning"
  fi

  echo "${TIMESTAMP},${CLUSTER_CONTEXT},${namespace},${pod_count},${cpu_request_m},${cpu_limit_m},${cpu_usage_m},${cpu_usage_vs_request_pct},${cpu_usage_vs_limit_pct},${mem_request_mib},${mem_limit_mib},${mem_usage_mib},${mem_usage_vs_request_pct},${mem_usage_vs_limit_pct},${missing_requests_limits_count},${restart_count},${oomkilled_count},${quota_present},${limitrange_present},${status}" >>"${OUT_FILE}"
done

echo "Wrote report: ${OUT_FILE}"
