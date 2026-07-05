# Resource governance quickstart

This directory provides two scripts:

- `audit-namespaces.sh`: inventories requests/limits/usage and emits a CSV report.
- `bootstrap-policies.sh`: applies baseline `LimitRange` + `ResourceQuota` across namespaces.

## Requirements

- `kubectl` configured for the target cluster
- `jq`
- `rg` (ripgrep)
- `metrics-server` if you want non-zero usage values in the audit output

## 1) Generate current-state report

```bash
./hack/resource-governance/audit-namespaces.sh
```

Output file defaults to `k8s-resource-audit.csv`. You can override:

```bash
./hack/resource-governance/audit-namespaces.sh /tmp/prod-audit.csv
```

Exclude additional namespaces:

```bash
EXCLUDE_NAMESPACES_REGEX='^(kube-system|kube-public|kube-node-lease|monitoring)$' \
  ./hack/resource-governance/audit-namespaces.sh
```

## 2) Dry-run policy bootstrap

Start with dry-run so the API server validates the manifests without persisting:

```bash
./hack/resource-governance/bootstrap-policies.sh --dry-run
```

Target specific namespaces only:

```bash
./hack/resource-governance/bootstrap-policies.sh --dry-run --namespaces team-a,team-b
```

## 3) Apply baseline policies

Tune values in `./hack/resource-governance/defaults.env`, then apply:

```bash
./hack/resource-governance/bootstrap-policies.sh
```

## Notes

- Script behavior is idempotent (`kubectl apply`), so reruns are safe.
- Existing workloads that exceed new quotas will fail to create/scale until adjusted.
- `audit-namespaces.sh` marks `status=critical` when OOMKilled is detected.
