#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULTS_FILE="${DEFAULTS_FILE:-${SCRIPT_DIR}/defaults.env}"

if [ -f "${DEFAULTS_FILE}" ]; then
  # shellcheck disable=SC1090
  source "${DEFAULTS_FILE}"
fi

LIMITRANGE_NAME="${LIMITRANGE_NAME:-baseline-limits}"
RESOURCEQUOTA_NAME="${RESOURCEQUOTA_NAME:-baseline-quota}"
EXCLUDE_NAMESPACES_REGEX="${EXCLUDE_NAMESPACES_REGEX:-^(kube-system|kube-public|kube-node-lease)$}"

DEFAULT_REQUEST_CPU="${DEFAULT_REQUEST_CPU:-200m}"
DEFAULT_REQUEST_MEMORY="${DEFAULT_REQUEST_MEMORY:-256Mi}"
DEFAULT_LIMIT_CPU="${DEFAULT_LIMIT_CPU:-500m}"
DEFAULT_LIMIT_MEMORY="${DEFAULT_LIMIT_MEMORY:-512Mi}"
MIN_CPU="${MIN_CPU:-50m}"
MIN_MEMORY="${MIN_MEMORY:-64Mi}"
MAX_CPU="${MAX_CPU:-2}"
MAX_MEMORY="${MAX_MEMORY:-2Gi}"

QUOTA_REQUESTS_CPU="${QUOTA_REQUESTS_CPU:-8}"
QUOTA_REQUESTS_MEMORY="${QUOTA_REQUESTS_MEMORY:-16Gi}"
QUOTA_LIMITS_CPU="${QUOTA_LIMITS_CPU:-16}"
QUOTA_LIMITS_MEMORY="${QUOTA_LIMITS_MEMORY:-32Gi}"
QUOTA_PODS="${QUOTA_PODS:-100}"

DRY_RUN_MODE="none"
TARGET_NAMESPACES=""

print_help() {
  cat <<'EOF'
Usage:
  ./bootstrap-policies.sh [--dry-run] [--namespaces ns1,ns2]

Options:
  --dry-run              Render + server-validate without persisting.
  --namespaces LIST      Comma-separated namespace list. When omitted, applies to all non-system namespaces.
  -h, --help             Show this message.

Config:
  Edit defaults in defaults.env or override via environment variables.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN_MODE="server"
      shift
      ;;
    --namespaces)
      if [ "$#" -lt 2 ]; then
        echo "--namespaces requires a value." >&2
        exit 1
      fi
      TARGET_NAMESPACES="$2"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_help >&2
      exit 1
      ;;
  esac
done

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required but not found in PATH." >&2
  exit 1
fi

if [ -n "${TARGET_NAMESPACES}" ]; then
  NAMESPACE_LIST="$(tr ',' '\n' <<<"${TARGET_NAMESPACES}" | tr -d ' ')"
else
  NAMESPACE_LIST="$(
    kubectl get namespaces -o jsonpath='{.items[*].metadata.name}' \
    | tr ' ' '\n' \
    | rg -v "${EXCLUDE_NAMESPACES_REGEX}" || true
  )"
fi

if [ -z "${NAMESPACE_LIST}" ]; then
  echo "No target namespaces found. Check filters or input list." >&2
  exit 1
fi

manifest_file="$(mktemp)"
trap 'rm -f "${manifest_file}"' EXIT

for namespace in ${NAMESPACE_LIST}; do
  cat >"${manifest_file}" <<EOF
apiVersion: v1
kind: LimitRange
metadata:
  name: ${LIMITRANGE_NAME}
  namespace: ${namespace}
spec:
  limits:
  - type: Container
    defaultRequest:
      cpu: "${DEFAULT_REQUEST_CPU}"
      memory: "${DEFAULT_REQUEST_MEMORY}"
    default:
      cpu: "${DEFAULT_LIMIT_CPU}"
      memory: "${DEFAULT_LIMIT_MEMORY}"
    min:
      cpu: "${MIN_CPU}"
      memory: "${MIN_MEMORY}"
    max:
      cpu: "${MAX_CPU}"
      memory: "${MAX_MEMORY}"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: ${RESOURCEQUOTA_NAME}
  namespace: ${namespace}
spec:
  hard:
    requests.cpu: "${QUOTA_REQUESTS_CPU}"
    requests.memory: "${QUOTA_REQUESTS_MEMORY}"
    limits.cpu: "${QUOTA_LIMITS_CPU}"
    limits.memory: "${QUOTA_LIMITS_MEMORY}"
    pods: "${QUOTA_PODS}"
EOF

  if [ "${DRY_RUN_MODE}" = "server" ]; then
    kubectl apply --dry-run=server -f "${manifest_file}" >/dev/null
    echo "[dry-run] validated policies for namespace: ${namespace}"
  else
    kubectl apply -f "${manifest_file}" >/dev/null
    echo "Applied policies for namespace: ${namespace}"
  fi
done
