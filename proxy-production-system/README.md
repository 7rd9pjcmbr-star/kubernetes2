# Proxy Production System

Scaffold dự án proxy production-ready ở mức nền tảng:

- Reverse proxy round-robin nhiều upstream.
- Health check endpoint (`/healthz`) và readiness endpoint (`/readyz`).
- Graceful shutdown để tránh rớt request khi rollout.
- Runtime config bằng environment variables.
- Optional token auth qua header `X-Proxy-Token`.
- Optional rate limiting theo client IP.
- Structured logging (JSON/text) có `request_id` và `trace_id`.
- Prometheus metrics tại endpoint `/metrics`.
- OpenTelemetry tracing (OTLP gRPC exporter).
- Dockerfile + docker-compose để chạy local.
- Kubernetes manifests mẫu để deploy.

## 1) Cấu trúc

```text
proxy-production-system/
├── .dockerignore
├── cmd/proxy/main.go
├── internal/buildinfo/buildinfo.go
├── internal/config/config.go
├── internal/observability/
│   ├── logger.go
│   └── tracing.go
├── internal/proxy/
│   ├── pool.go
│   ├── pool_test.go
│   ├── middleware.go
│   ├── middleware_test.go
│   ├── metrics.go
│   ├── metrics_test.go
│   ├── rate_limiter.go
│   ├── rate_limiter_test.go
│   └── reverse_proxy.go
├── deployments/
│   ├── docker/Dockerfile
│   └── k8s/
│       ├── configmap.yaml
│       ├── deployment.yaml
│       ├── hpa.yaml
│       ├── ingress-class.yaml
│       ├── ingress.yaml
│       ├── ingress-nginx/
│       │   └── namespace.yaml
│       ├── service.yaml
│       └── servicemonitor.yaml
├── docs/
│   ├── release-checklist.md
│   ├── release-standard.md
│   └── user-guide.md
└── scripts/
    ├── install-nginx-ingress-controller.sh
    ├── package-release.sh
    ├── quality-gate.sh
    └── security-test.sh
```

## 2) Chạy local

```bash
cp .env.example .env
docker compose up --build
```

Test nhanh:

```bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/readyz
curl -s http://localhost:8080/metrics | rg proxy_requests_total
curl -s http://localhost:8080/version
curl -i http://localhost:8080
```

## 3) Các biến môi trường

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `PROXY_UPSTREAMS` | Có | - | Danh sách upstream dạng CSV (`http://a:8081,http://b:8082`) |
| `PROXY_LISTEN_ADDRESS` | Không | `:8080` | Địa chỉ listen của proxy |
| `PROXY_READ_TIMEOUT` | Không | `15s` | Read timeout cho HTTP server |
| `PROXY_WRITE_TIMEOUT` | Không | `15s` | Write timeout cho HTTP server |
| `PROXY_IDLE_TIMEOUT` | Không | `60s` | Idle timeout cho keep-alive |
| `PROXY_SHUTDOWN_TIMEOUT` | Không | `20s` | Timeout cho graceful shutdown |
| `PROXY_REQUEST_TIMEOUT` | Không | `30s` | Timeout tổng cho mỗi request proxy, quá ngưỡng sẽ trả 503 |
| `PROXY_AUTH_TOKEN` | Không | rỗng | Nếu set, yêu cầu request gửi header `X-Proxy-Token` trùng giá trị này |
| `PROXY_RATE_LIMIT_RPS` | Không | `0` | Số request/giây theo mỗi IP (`0` = tắt) |
| `PROXY_RATE_LIMIT_BURST` | Không | `0` | Burst cho token bucket (`>0` khi bật RPS) |
| `PROXY_TRUST_FORWARDED` | Không | `false` | Tin `X-Forwarded-For`/`X-Real-Ip` khi đứng sau LB/reverse proxy |
| `PROXY_LOG_FORMAT` | Không | `json` | Định dạng log: `json` hoặc `text` |
| `PROXY_SERVICE_NAME` | Không | `proxy-production-system` | Service name cho telemetry resource |
| `PROXY_TRACE_OTLP_ENDPOINT` | Không | rỗng | OTLP gRPC endpoint (ví dụ `otel-collector:4317`), rỗng = tắt exporter |
| `PROXY_TRACE_OTLP_INSECURE` | Không | `true` | Bật/tắt TLS cho OTLP gRPC |
| `PROXY_TRACE_SAMPLE_RATIO` | Không | `1.0` | Tỷ lệ sampling trace trong khoảng `[0,1]` |

## 4) Chạy test

```bash
GOWORK=off go test ./...
```

Quality gate trước release:

```bash
./scripts/quality-gate.sh
```

Security test trước release:

```bash
./scripts/security-test.sh
```

Đóng gói release artifact:

```bash
./scripts/package-release.sh v1.0.0
```

Chạy full pipeline chuẩn hoá (quality + security + package):

```bash
make release-ready VERSION=v1.0.0
```

Checklist bàn giao:

- `docs/release-checklist.md`
- `docs/release-standard.md`
- `docs/user-guide.md`

## 5) Deploy Kubernetes (mẫu)

```bash
kubectl apply -f deployments/k8s/
```

## 6) Bổ sung NGINX Ingress Controller

Cài ingress-nginx controller (pinned version):

```bash
./scripts/install-nginx-ingress-controller.sh
```

Deploy ingress cho proxy service:

```bash
kubectl apply -f deployments/k8s/ingress.yaml
```

Ghi chú:
- Mặc định `host` trong manifest là `proxy.example.com`, đổi theo domain thực tế.
- Nếu dùng TLS, thêm `spec.tls` + secret chứng chỉ vào `deployments/k8s/ingress.yaml`.
- Nếu ingress-nginx đã được cài sẵn trong cluster, chỉ cần apply `ingress-class.yaml` (nếu thiếu) và `ingress.yaml`.

Nếu cluster dùng Prometheus Operator, apply thêm:

```bash
kubectl apply -f deployments/k8s/servicemonitor.yaml
```

Ví dụ bật tracing tới OpenTelemetry Collector:

```bash
export PROXY_TRACE_OTLP_ENDPOINT=otel-collector.observability.svc.cluster.local:4317
export PROXY_TRACE_OTLP_INSECURE=true
export PROXY_TRACE_SAMPLE_RATIO=0.2
```

> Manifest là baseline để bắt đầu. Trước khi dùng production thật, nên bổ sung:
> - TLS termination / mTLS
> - Alerting theo SLO
> - PodDisruptionBudget và NetworkPolicy
