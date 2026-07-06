# Proxy Production System

Scaffold dự án proxy production-ready ở mức nền tảng:

- Reverse proxy round-robin nhiều upstream.
- Health check endpoint (`/healthz`) cho liveness/readiness.
- Graceful shutdown để tránh rớt request khi rollout.
- Runtime config bằng environment variables.
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
> - AuthN/AuthZ theo nhu cầu
> - Rate limiting, WAF
> - Metrics, tracing, alerting
> - PodDisruptionBudget và NetworkPolicy

## 6) Website mô hình kinh doanh Proxy SaaS

Trang landing page mẫu nằm tại `website/` để trình bày:

- Giá trị sản phẩm Proxy SaaS
- Bảng giá tham khảo theo mô hình subscription + usage
- Khung mô hình kinh doanh (khách hàng mục tiêu, doanh thu, chi phí, GTM)

Chạy nhanh bằng Python static server:

```bash
cd website
python3 -m http.server 8081
```

Sau đó mở: `http://localhost:8081`

## 7) ScanToolmanus V3 (giữ nguyên V2)

Giao diện V3 được đặt riêng tại `website-v3/` để chạy song song,
không ghi đè nội dung hiện có của `website/`.

```bash
cd website-v3
python3 -m http.server 8082
```

Sau đó mở: `http://localhost:8082`
