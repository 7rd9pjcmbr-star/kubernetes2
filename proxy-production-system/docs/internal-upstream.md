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

## 3) Đấu nối lại (reconnect)

```bash
cd proxy-production-system
./scripts/reconnect-internal.sh
```

Chỉ kiểm tra upstream (không start proxy):

```bash
./scripts/reconnect-internal.sh --check-only
```

Script sẽ:
1. Load `.env` (tạo từ `.env.internal.example` nếu thiếu)
2. Kiểm tra kết nối tới từng upstream
3. Build + start proxy nội bộ

Nếu upstream báo timeout: máy bạn cần cùng mạng LAN/VPN với IP đích.
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
