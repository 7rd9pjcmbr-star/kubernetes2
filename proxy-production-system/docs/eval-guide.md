# Hướng dẫn nghiệm thu chất lượng (Evaluation Guide)

Mục tiêu: chạy được bản proxy **ngay trên máy** để bạn tự đánh giá chất lượng trước khi bàn giao/bán.

## Cách 1: Kiểm thử tự động (khuyến nghị lần đầu)

Không cần Docker. Chỉ cần Go + curl.

```bash
cd proxy-production-system
./scripts/run-eval.sh
```

Script sẽ:
1. Build proxy + upstream mẫu
2. Khởi động stack local (port mặc định `18080`)
3. Kiểm tra:
   - `/healthz`, `/readyz`, `/version`, `/metrics`
   - auth token (401 khi thiếu)
   - round-robin upstream
   - rate limit (429 khi vượt burst)
   - security headers
4. In kết quả PASS/FAIL

Nếu PASS: sản phẩm **đã chạy được để nghiệm thu**.

## Cách 2: Chạy stack để bạn tự thử tay

```bash
cd proxy-production-system
./scripts/start-eval-stack.sh
```

Giữ terminal này mở, mở terminal khác:

```bash
curl -i http://127.0.0.1:18080/healthz
curl -s http://127.0.0.1:18080/version
curl -i -H "X-Proxy-Token: eval-token" http://127.0.0.1:18080/
curl -s http://127.0.0.1:18080/metrics | head
```

Dừng: `Ctrl+C` ở terminal chạy stack.

## Cách 3: Docker Compose (nếu máy bạn có Docker)

```bash
cp .env.example .env
docker compose up --build
```

Kiểm tra:

```bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/
```

## Checklist đánh giá chất lượng nhanh

- [ ] Proxy lên trong < 10 giây, `/readyz` = 200
- [ ] Request có token đi qua upstream đúng
- [ ] Request không token bị 401
- [ ] Burst traffic bị 429
- [ ] `/metrics` có `proxy_requests_total`
- [ ] Log JSON có `request_id`
- [ ] Round-robin xoay `echo-a` / `echo-b`

## Ports mặc định (eval local)

| Thành phần | Port |
|---|---|
| Proxy | `18080` |
| Upstream A | `18081` |
| Upstream B | `18082` |

Token mặc định: `eval-token`

## Ghi chú

- Đây là bản **đánh giá kỹ thuật**, chưa phải gói bán lẻ hoàn chỉnh.
- Sau khi bạn nghiệm thu ổn, tiếp tục đóng các gap retail trong `docs/retail-readiness.md`.
