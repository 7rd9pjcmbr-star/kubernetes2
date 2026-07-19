# Proxy Production Release Checklist

Checklist này dùng trước khi bàn giao bản build cho khách hàng.

## 1) Code quality gate (bắt buộc pass)

- [ ] `./scripts/preflight-test.sh` pass toàn bộ (quality + security + runtime).
- [ ] `./scripts/quality-gate.sh` pass toàn bộ.
- [ ] `./scripts/security-test.sh` pass toàn bộ.
- [ ] Không có thay đổi chưa commit (`git status --short` rỗng).
- [ ] PR đã có mô tả thay đổi, rủi ro, và rollback note.

## 2) Functional and resilience checks

- [ ] `/healthz`, `/readyz`, `/metrics`, `/version` trả về 200 trong điều kiện bình thường.
- [ ] Truy cập qua Ingress hostname trả về đúng response từ proxy service.
- [ ] Auth token hoạt động đúng (401 khi thiếu/sai token, 200 khi token đúng).
- [ ] Rate limiting hoạt động đúng ở ngưỡng cấu hình.
- [ ] Graceful shutdown không cắt request đang xử lý (test trong rollout hoặc test môi trường staging).

## 3) Observability checks

- [ ] Prometheus scrape thành công các metric:
  - `proxy_requests_total`
  - `proxy_request_duration_seconds`
  - `proxy_auth_rejections_total`
  - `proxy_rate_limit_rejections_total`
  - `proxy_upstream_errors_total`
- [ ] Trace được gửi về OTLP endpoint (nếu bật tracing).
- [ ] Log có đủ trường `request_id` và `trace_id`.

## 4) Security and runtime checks

- [ ] Không hardcode secret vào source/configmap (`PROXY_AUTH_TOKEN` phải lấy từ secret manager/K8s Secret trong môi trường thật).
- [ ] `PROXY_TRUST_FORWARDED=true` chỉ bật khi nằm sau LB/proxy tin cậy.
- [ ] Ingress hostname có TLS certificate hợp lệ trong môi trường production.
- [ ] Policy network, TLS/mTLS, và ACL upstream đúng với kiến trúc khách hàng.

## 5) Delivery and rollback checks

- [ ] Image tag immutable (không dùng `latest` cho production).
- [ ] Artifact release tarball và file checksum `.sha256` đã được tạo từ `./scripts/package-release.sh <version>`.
- [ ] Kế hoạch rollback đã kiểm tra (image/tag trước đó còn khả dụng).
- [ ] Tài liệu vận hành đã cập nhật (env vars, alert rules, dashboard links).
