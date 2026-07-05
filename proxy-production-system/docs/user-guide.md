# Hướng dẫn sử dụng Proxy Production System

Tài liệu này tập trung vào cách sử dụng thực tế cho dev và vận hành.

Nếu cần chạy demo nhanh, xem thêm: `docs/quickstart-5m.md`.

## 1) Mục tiêu hệ thống

Proxy thực hiện reverse proxy tới nhiều upstream với các khả năng:
- Round-robin load balancing.
- Health/readiness endpoint.
- Auth token tùy chọn.
- Rate limit theo client IP.
- Timeout bảo vệ request treo.
- Metrics, tracing và structured logging.

## 2) Chạy local nhanh

```bash
cp .env.example .env
docker compose up --build
```

Kiểm tra nhanh:

```bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/readyz
curl -s http://localhost:8080/metrics | rg proxy_requests_total
curl -s http://localhost:8080/version
```

## 3) Sử dụng các tính năng chính

### 3.1 Bật auth token

Trong `.env` hoặc ConfigMap:

```bash
PROXY_AUTH_TOKEN=your-secret-token
```

Request hợp lệ:

```bash
curl -H "X-Proxy-Token: your-secret-token" http://localhost:8080/
```

Nếu thiếu/sai token, proxy trả `401`.

### 3.2 Bật rate limit theo IP

```bash
PROXY_RATE_LIMIT_RPS=100
PROXY_RATE_LIMIT_BURST=200
```

Khi vượt ngưỡng, proxy trả `429`.

### 3.3 Cấu hình timeout request

```bash
PROXY_REQUEST_TIMEOUT=30s
```

Nếu request vượt timeout này, proxy trả `503 request timeout`.

### 3.4 Bật tracing OTLP

```bash
PROXY_TRACE_OTLP_ENDPOINT=otel-collector.observability.svc.cluster.local:4317
PROXY_TRACE_OTLP_INSECURE=true
PROXY_TRACE_SAMPLE_RATIO=0.2
```

### 3.5 Logging

```bash
PROXY_LOG_FORMAT=json
```

Log có các trường chính: `request_id`, `trace_id`, `method`, `path`, `status`, `duration_ms`.

## 4) Deploy Kubernetes

Deploy application baseline:

```bash
kubectl apply -f deployments/k8s/
```

Kiểm tra:

```bash
kubectl get pods
kubectl get svc proxy-system
```

### 4.1 Ingress NGINX

Cài ingress controller:

```bash
./scripts/install-nginx-ingress-controller.sh
```

Apply ingress route:

```bash
kubectl apply -f deployments/k8s/ingress.yaml
```

Lưu ý:
- Đổi host `proxy.example.com` theo domain thật.
- Môi trường production cần cấu hình TLS trong ingress.

## 5) Vận hành và giám sát

### 5.1 Probe endpoints

- Liveness: `/healthz`
- Readiness: `/readyz`

### 5.2 Quan sát

- Metrics: `/metrics`
- Version metadata: `/version`

Ví dụ:

```bash
curl -s http://<proxy-host>/version
```

## 6) Quy trình release chuẩn

Chạy quality gate:

```bash
./scripts/quality-gate.sh
```

Chạy security test:

```bash
./scripts/security-test.sh
```

Đóng gói artifact:

```bash
./scripts/package-release.sh v1.0.0
```

Hoặc chạy one-shot:

```bash
make release-ready VERSION=v1.0.0
```

Checklist bàn giao:
- `docs/release-checklist.md`
- `docs/release-standard.md`
