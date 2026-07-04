#!/usr/bin/env bash
set -euo pipefail

# Pin a controller release so production installs are repeatable.
INGRESS_NGINX_VERSION="${INGRESS_NGINX_VERSION:-controller-v1.12.1}"
MANIFEST_URL="https://raw.githubusercontent.com/kubernetes/ingress-nginx/${INGRESS_NGINX_VERSION}/deploy/static/provider/cloud/deploy.yaml"

echo "Installing ingress-nginx controller from: ${MANIFEST_URL}"
kubectl apply -f deployments/k8s/ingress-nginx/namespace.yaml
kubectl apply -f "${MANIFEST_URL}"
kubectl apply -f deployments/k8s/ingress-class.yaml

echo "ingress-nginx installation request submitted."
echo "Check rollout with: kubectl -n ingress-nginx get pods"
