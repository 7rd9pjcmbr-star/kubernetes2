# Kiểm thử trước khi sử dụng thật (Preflight)

Chạy bộ này **trước mọi lần đưa proxy vào staging/production**.

## Chạy một lệnh

```bash
cd proxy-production-system
./scripts/preflight-test.sh
```

Hoặc:

```bash
make preflight
```

## Bộ kiểm thử gồm gì

1. **Quality gate** — format, unit/integration test, race, vet, build  
2. **Security suite** — race, vet, govulncheck, Dockerfile policy  
3. **Runtime functional** — `/healthz`, `/readyz`, `/version`, `/metrics`  
4. **Security behavior** — thiếu token / sai token = 401, security headers, `X-Request-Id`  
5. **Proxy behavior** — round-robin, rate limit 429  
6. **Timeout protection** — upstream chậm bị 503  
7. **Concurrent smoke** — 40 request song song, yêu cầu gần như tất cả 200  

## Kết quả

- `PREFLIGHT PASSED - OK TO USE IN STAGING` → được phép dùng thử môi trường thật/staging  
- `PREFLIGHT FAILED - DO NOT USE IN PRODUCTION` → dừng, xem báo cáo  

Báo cáo mặc định:

```text
/tmp/proxy-preflight/preflight-report.txt
```

## Quy tắc sử dụng thật

| Kết quả preflight | Hành động |
|---|---|
| PASS | Được đưa staging / pilot có giám sát |
| FAIL | Không deploy production |
| PASS nhưng chưa có TLS/Secret thật | Chỉ staging, chưa production công khai |

## Sau khi PASS

1. Cấu hình upstream thật + auth token từ Secret  
2. Bật TLS ở Ingress  
3. Deploy staging  
4. Theo dõi `/metrics` + log trong 24–72h trước production rộng  
