# Proxy Production System

Scaffold dự án proxy production-ready ở mức nền tảng:

- Reverse proxy round-robin nhiều upstream.
- Health check endpoint (`/healthz`) và readiness endpoint (`/readyz`).
- Graceful shutdown để tránh rớt request khi rollout.
- Runtime config bằng environment variables.
- Optional token auth qua header `X-Proxy-Token`.
- Optional rate limiting theo client IP.
- Request logging có `request_id` để trace.
- Dockerfile + docker-compose để chạy local.
- Kubernetes manifests mẫu để deploy.

## 1) Cấu trúc

```text
proxy-production-system/
├── cmd/proxy/main.go
├── internal/config/config.go
├── internal/proxy/
│   ├── pool.go
│   ├── pool_test.go
│   ├── middleware.go
│   ├── middleware_test.go
│   ├── rate_limiter.go
│   ├── rate_limiter_test.go
│   └── reverse_proxy.go
├── deployments/
│   ├── docker/Dockerfile
│   └── k8s/
│       ├── configmap.yaml
│       ├── deployment.yaml
│       ├── hpa.yaml
│       └── service.yaml
└── .env.example
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
| `PROXY_AUTH_TOKEN` | Không | rỗng | Nếu set, yêu cầu request gửi header `X-Proxy-Token` trùng giá trị này |
| `PROXY_RATE_LIMIT_RPS` | Không | `0` | Số request/giây theo mỗi IP (`0` = tắt) |
| `PROXY_RATE_LIMIT_BURST` | Không | `0` | Burst cho token bucket (`>0` khi bật RPS) |
| `PROXY_TRUST_FORWARDED` | Không | `false` | Tin `X-Forwarded-For`/`X-Real-Ip` khi đứng sau LB/reverse proxy |

## 4) Chạy test

```bash
GOWORK=off go test ./...
```

## 5) Deploy Kubernetes (mẫu)

```bash
kubectl apply -f deployments/k8s/
```

> Manifest là baseline để bắt đầu. Trước khi dùng production thật, nên bổ sung:
> - TLS termination / mTLS
> - Metrics, tracing, alerting
> - PodDisruptionBudget và NetworkPolicy
