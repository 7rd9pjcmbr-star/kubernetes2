# Cấu hình proxy nội bộ

Hướng dẫn nối proxy tới upstream nội bộ (ví dụ IP LAN/VPN).

## 1) Tạo cấu hình local

```bash
cd proxy-production-system
cp .env.internal.example .env
```

Mặc định trong profile nội bộ:

- Upstream: `https://42.115.10.251`
- `PROXY_INSECURE_SKIP_VERIFY=true` (cho chứng chỉ self-signed nội bộ)
- `PROXY_TRUST_FORWARDED=true`

## 2) Basic Auth upstream (nếu hệ thống đích yêu cầu)

Chỉ set trong `.env` local (file này đã gitignore):

```bash
PROXY_UPSTREAM_BASIC_AUTH=username:password
```

**Không commit mật khẩu vào git.**

## 3) Chạy proxy nội bộ

```bash
./scripts/run-internal-proxy.sh
```

Kiểm tra:

```bash
curl -i http://127.0.0.1:8080/healthz
curl -i http://127.0.0.1:8080/
# nếu upstream có path cụ thể:
curl -i http://127.0.0.1:8080/config.html
```

## 4) Nhiều upstream

Trong `.env`:

```bash
PROXY_UPSTREAMS=https://42.115.10.251,https://fast-hrm.jtexpress.vn:8080
```

Proxy sẽ round-robin giữa các upstream.

## 5) Biến cấu hình mới

| Biến | Ý nghĩa |
|---|---|
| `PROXY_INSECURE_SKIP_VERIFY` | Bỏ verify TLS upstream (chỉ dùng mạng nội bộ tin cậy) |
| `PROXY_UPSTREAM_BASIC_AUTH` | `user:pass` gửi Authorization Basic tới upstream |

## Lưu ý bảo mật

- Chỉ bật `PROXY_INSECURE_SKIP_VERIFY=true` trong mạng nội bộ/VPN.
- Token/mật khẩu để ở Secret hoặc `.env` local, không để ConfigMap công khai.
- Chạy `./scripts/preflight-test.sh` trước khi đưa staging.
