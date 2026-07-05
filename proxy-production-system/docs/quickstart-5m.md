# Quickstart 5 phút

Mục tiêu: chạy proxy local trong vài phút để demo nhanh.

## Bước 1: chạy service

```bash
cp .env.example .env
docker compose up --build -d
```

## Bước 2: kiểm tra trạng thái

```bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/readyz
curl -s http://localhost:8080/version
```

Kỳ vọng: trả `200 OK`.

## Bước 3: gửi request qua proxy

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/
curl -i http://localhost:8080/
```

Bạn sẽ thấy response luân phiên giữa các upstream mẫu (`echo-a`, `echo-b`).

## Bước 4: xem metrics

```bash
curl -s http://localhost:8080/metrics | rg "proxy_requests_total|proxy_request_duration_seconds"
```

## Bước 5: dừng môi trường demo

```bash
docker compose down
```

## Tuỳ chọn: bật auth nhanh

Sửa `.env`:

```bash
PROXY_AUTH_TOKEN=demo-token
```

Khởi động lại:

```bash
docker compose up --build -d
```

Request có token:

```bash
curl -H "X-Proxy-Token: demo-token" http://localhost:8080/
```
