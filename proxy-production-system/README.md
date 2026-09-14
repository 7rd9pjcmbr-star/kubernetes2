# Proxy Production System

Scaffold dự án proxy production-ready ở mức nền tảng:

- Reverse proxy round-robin nhiều upstream.
- **Gateway proxy kiểu dân chơi VN**: HTTP + SOCKS5, xoay IP, sticky session, auth, whitelist IP.
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
│   ├── gateway.go
│   ├── forward_http.go
│   ├── socks5_server.go
│   ├── auth.go
│   ├── health.go
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
| `PROXY_STATIC_ROOT` | Không | _(trống)_ | Thư mục static root để bật route UI (`/v2`, `/v3`) |
| `PROXY_LISTEN_ADDRESS` | Không | `:8080` | Địa chỉ listen của proxy |
| `PROXY_READ_TIMEOUT` | Không | `15s` | Read timeout cho HTTP server |
| `PROXY_WRITE_TIMEOUT` | Không | `15s` | Write timeout cho HTTP server |
| `PROXY_IDLE_TIMEOUT` | Không | `60s` | Idle timeout cho keep-alive |
| `PROXY_SHUTDOWN_TIMEOUT` | Không | `20s` | Timeout cho graceful shutdown |

### Gateway proxy (HTTP/SOCKS5 — kiểu seller/automation VN)

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `PROXY_GATEWAY_ENABLED` | Không | `false` (auto `true` nếu có `PROXY_POOL`) | Bật gateway forward proxy |
| `PROXY_POOL` | Có (khi bật gateway) | - | CSV entry dạng `url\|kind\|region` |
| `PROXY_GATEWAY_HTTP_ADDRESS` | Không | `:8888` | HTTP/HTTPS proxy listen |
| `PROXY_GATEWAY_SOCKS_ADDRESS` | Không | `:1080` | SOCKS5 proxy listen |
| `PROXY_GATEWAY_ADMIN_ADDRESS` | Không | _(trống)_ | Admin API (`/healthz`, `/api/v1/pool/stats`) |
| `PROXY_GATEWAY_USER` / `PROXY_GATEWAY_PASS` | Khuyến nghị | _(trống)_ | Auth kiểu `user:pass` cho client |
| `PROXY_ROTATION` | Không | `round_robin` | `round_robin`, `random`, `sticky`, `quality` |
| `PROXY_STICKY_TTL` | Không | `10m` | Thời gian giữ IP khi dùng sticky |
| `PROXY_CLIENT_WHITELIST` | Không | _(trống)_ | Chỉ cho phép IP client (sandbox) |
| `PROXY_HEALTH_INTERVAL` | Không | `30s` | Chu kỳ health check upstream |
| `PROXY_ADMIN_TOKEN` | Không | _(trống)_ | Header `X-Admin-Token` cho stats API |
| `PROXY_ELITE_MODE` | Không | `true` | Xóa header lộ proxy (`X-Forwarded-For`, `Via`, …) trước khi forward |

**Loại node (`kind`)**: `residential`, `4g`, `isp`, `datacenter`.

**Model MongoDB (`internal/model/proxy_backend.go`)** — mỗi backend có `latency`, `success_rate`, `anonymity` (`elite|anonymous|transparent`), `status` (`active|dead|testing`). Gateway mode `quality` ưu tiên node elite, latency thấp, success rate cao.

**PROXY_POOL mở rộng** (tùy chọn thêm metrics bootstrap):

```text
http://ip:port|4g|VN|elite|45|99.5
           ^url ^kind ^country ^anonymity ^latency_ms ^success_rate
```

**Sticky session theo username** (pattern phổ biến VN):

```text
player-session-shop123:change-me
```

Client dùng username `player-session-shop123` sẽ giữ cùng exit IP trong `PROXY_STICKY_TTL`.

**Test nhanh gateway**:

```bash
# HTTP proxy
curl -x http://player:change-me@localhost:8888 https://api.ipify.org

# SOCKS5 (cần curl hỗ trợ socks5)
curl --socks5 player:change-me@localhost:1080 https://api.ipify.org

# Stats pool
curl -H "X-Admin-Token: your-token" http://localhost:9090/api/v1/pool/stats
```

> Gateway là **lớp quản lý pool** — bạn cắm upstream thật (4G dongle, residential provider, SOCKS5 supplier) vào `PROXY_POOL`. Hệ thống lo auth, xoay IP, sticky, health check.

## 3.1) Kiến trúc tối ưu (MongoDB + CRUD + hot reload)

```text
Client (AdsPower/curl)
    -> HTTP :8888 / SOCKS5 :1080
        -> PoolManager (quality/sticky rotation)
            -> Upstream exit IP (4G/residential)
Admin/Dashboard
    -> REST :9090 /api/v1/backends
        -> MongoDB (ProxyBackend collection)
            -> sync every 10s + hot reload on CRUD
```

| Thành phần | Vai trò |
|---|---|
| `internal/model/proxy_backend.go` | Schema MongoDB |
| `internal/store/mongo.go` | Persistence + metrics flush |
| `internal/proxy/pool_manager.go` | Hot reload pool không downtime |
| `internal/proxy/sync.go` | Bootstrap từ `PROXY_POOL`, sync định kỳ |
| Admin API | CRUD backend + `/api/v1/pool/reload` |

**Env MongoDB**:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `MONGO_URI` | _(trống = in-memory)_ | URI MongoDB |
| `MONGO_DATABASE` | `proxy_gateway` | Database |
| `MONGO_COLLECTION` | `backends` | Collection |
| `MONGO_SYNC_INTERVAL` | `10s` | Reload pool từ Mongo |
| `MONGO_METRICS_FLUSH_INTERVAL` | `30s` | Ghi latency/success_rate về Mongo |

**Admin CRUD** (header `X-Admin-Token` nếu có `PROXY_ADMIN_TOKEN`):

```bash
# Thêm backend mới (hot reload ngay)
curl -X POST http://localhost:9090/api/v1/backends \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: change-me-admin" \
  -d '{"ip":"203.0.113.10","port":3128,"type":"4g","country":"VN","anonymity":"elite","status":"active","latency":35,"success_rate":99}'

# List / update / delete
curl http://localhost:9090/api/v1/backends
curl -X PUT http://localhost:9090/api/v1/backends/{id} ...
curl -X DELETE http://localhost:9090/api/v1/backends/{id}

# Force reload pool từ Mongo
curl -X POST http://localhost:9090/api/v1/pool/reload
```

Lần chạy đầu: nếu Mongo trống, gateway **seed** từ `PROXY_POOL` rồi dùng Mongo làm nguồn sự thật.

## 3.2) @TondaithanhBot (Telegram + MongoDB)

Bot Telegram doc/ghi trực tiếp collection `backends` trong MongoDB — gateway tự sync pool sau ~10s.

```bash
# .env
TELEGRAM_BOT_TOKEN=<token cua @TondaithanhBot>
TELEGRAM_ADMIN_CHAT_IDS=123456789   # chat ID admin, CSV neu nhieu nguoi
MONGO_URI=mongodb://mongo:27017
```

`docker compose up` chạy service `tondaithanh-bot` song song với gateway.

**Bảng điều khiển Telegram** (inline + menu nhanh):

Gửi `/start` hoặc `/panel` để mở bảng nút bấm:

- 📊 Thống kê — active/dead/testing/latency
- 📋 Danh sách — phân trang 8 backend/trang (150 proxy)
- 📁 150 Proxy files — đếm 2 file HCM/HN
- ☠️ Node dead — liệt kê backend lỗi
- 🔔/🔕 Subscribe cảnh báo

**Lenh text** (nâng cao):

| Lenh | Mo ta |
|---|---|
| `/add 203.0.113.1 3128 4g VN` | Them backend vao Mongo |
| `/del <id>` | Xoa backend |
| `/status <id> dead` | Doi trang thai thu cong |

Bot tu dong broadcast khi backend chuyen sang `dead` (poll Mongo moi 30s).

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

Khi chạy qua image Docker mặc định của dự án, static assets được mount tại `/static`
và có thể truy cập trên cùng domain:

- V2: `http://<host>:8080/v2/`
- V3: `http://<host>:8080/v3/`

## 8) Kiểm tra API các nền tảng TMDT VN

Script kiểm tra nhanh khả dụng endpoint và hành vi auth-gate:

```bash
python3 scripts/check_vn_platform_apis.py
```

Ghi báo cáo JSON:

```bash
python3 scripts/check_vn_platform_apis.py --output /tmp/platform-api-report.json
```

Chạy thêm authenticated smoke test (đọc token từ biến môi trường):

```bash
set -a
source scripts/.env.vn-platforms.example
set +a
python3 scripts/check_vn_platform_apis.py --authenticated
```

Yêu cầu fail nếu thiếu credential:

```bash
python3 scripts/check_vn_platform_apis.py --authenticated --require-auth
```

Script hiện kiểm tra: Pancake POS, GHTK, Nhanh.vn POS v3, Sapo, Haravan, TikTok Shop, Shopee, GHN.

Lưu ý cho Pancake POS:
- Ưu tiên `PANCAKE_POS_API_KEY` nếu có.
- Nếu dùng token, script tự thử cả token bạn cung cấp và `accessToken` lồng bên trong (nếu token là JWT bọc ngoài).
- Khi lỗi, kết quả sẽ có `diagnostics.classification` và `diagnostics.hint` để chỉ rõ khả năng:
  - sai API key
  - sai loại token
  - token hết hạn
  - token không thuộc POS Open API

## 9) Theo dõi đơn hàng Pancake POS realtime

```bash
PANCAKE_POS_API_KEY=your_key python3 scripts/monitor_pancake_orders.py
```

Tuỳ chọn:

```bash
python3 scripts/monitor_pancake_orders.py --api-key your_key --poll-seconds 30 --limit 5
```

## 10) Gửi Excel Telegram mỗi ngày 1 lần (đơn 24h gần nhất)

Script này:
- chỉ lấy đơn hàng trong **1 ngày gần nhất** (24 giờ gần nhất)
- chỉ gửi báo cáo **1 lần/ngày** (dựa trên state file)
- gửi file `.xlsx` lên Telegram

Chuẩn bị:

```bash
pip install openpyxl
```

Chạy thủ công:

```bash
PANCAKE_POS_API_KEY=your_key \
TELEGRAM_BOT_TOKEN=your_bot_token \
TELEGRAM_CHAT_ID=your_chat_id \
python3 scripts/daily_pancake_orders_to_telegram.py
```

Chạy ép gửi lại trong ngày (bỏ qua khóa 1 lần/ngày):

```bash
python3 scripts/daily_pancake_orders_to_telegram.py --force
```

Gợi ý cron chạy mỗi ngày lúc 08:00:

```cron
0 8 * * * cd /path/to/proxy-production-system && /usr/bin/env bash -lc 'source scripts/.env.vn-platforms.example && python3 scripts/daily_pancake_orders_to_telegram.py'
```

## 11) Làm sạch dữ liệu account cho V2 (auto-run)

Script `scripts/clean_accounts_for_v2.py`:
- chỉ loại trùng lặp **exact line**
- giữ nguyên định dạng từng dòng còn lại để tránh sai lệch khi import vào node V2
- xuất file `.txt` sẵn cho luồng **thêm tài khoản hàng loạt**
- ràng buộc đúng nền tảng (`--platform`) hoặc suy luận từ tên file (`accounts.sapo.vn...`)
- với file cookie (tab-separated), script còn kiểm tra nền tảng theo domain trong nội dung để tránh đẩy nhầm nền tảng

Chạy 1 file cụ thể:

```bash
python3 scripts/clean_accounts_for_v2.py --input-file /path/to/input.txt --platform sapo
```

Auto chạy file `.txt` mới nhất trong uploads:

```bash
python3 scripts/clean_accounts_for_v2.py --auto
```

Auto + chỉ định nền tảng bắt buộc đúng:

```bash
python3 scripts/clean_accounts_for_v2.py --auto --platform sapo
```

Auto + chạy lệnh V2 ngay sau khi làm sạch:

```bash
python3 scripts/clean_accounts_for_v2.py --auto --v2-command "/home/ubuntu/run_v2.sh"
```

Khi `--v2-command` được gọi, script set:
- `V2_BULK_ACCOUNTS_FILE`: path file `.txt` đã dedupe
- `V2_BULK_PLATFORM`: nền tảng đích (sapo/pancake/shopee/tiktokshop/ghn)

Script luôn ghi thêm bản đường dẫn cố định cho V2 loader:
- `/tmp/v2-cleaned/latest/v2_bulk_accounts_<platform>.txt`

Tách file hỗn hợp thành từng nền tảng và đẩy từng file vào V2:

```bash
python3 scripts/clean_accounts_for_v2.py \
  --input-file /path/to/mixed_cookie.txt \
  --split-by-platform \
  --v2-command "/home/ubuntu/run_v2.sh"
```

Bỏ nhóm `unknown` khi split:

```bash
python3 scripts/clean_accounts_for_v2.py \
  --input-file /path/to/mixed_cookie.txt \
  --split-by-platform \
  --exclude-unknown \
  --v2-command "/home/ubuntu/run_v2.sh"
```

Chỉ đẩy 1 nền tảng duy nhất:

```bash
python3 scripts/clean_accounts_for_v2.py \
  --input-file /path/to/mixed_cookie.txt \
  --split-by-platform \
  --only-platform tiktokshop \
  --v2-command "/home/ubuntu/run_v2.sh"
```

## 12) Pancake OAuth callback helper (lấy code -> đổi token)

Script `scripts/pancake_oauth_helper.py` giúp:
- parse callback URL sau khi login OAuth
- decode/validate `state` (base64 JSON)
- in sẵn lệnh `curl` để đổi `code` thành token

Ví dụ:

```bash
python3 scripts/pancake_oauth_helper.py \
  --callback-url 'https://pancake.vn/api/v1/users/pancake_id_login_success?code=YOUR_CODE&state=BASE64_STATE' \
  --client-id '53e2d5e33a8940f4a30ba22a4011e52a' \
  --client-secret 'YOUR_CLIENT_SECRET' \
  --require-pos-login
```

## 13) TikTok Seller URL helper (decode state -> mapping V2)

Script `scripts/tiktok_seller_url_helper.py`:
- parse URL từ Seller Center
- decode `state` (base64 JSON)
- xuất mapping chuẩn cho V2 (`platform/shop_id/warehouse_id/sync flags`)

Ví dụ:

```bash
python3 scripts/tiktok_seller_url_helper.py \
  --url 'https://seller-vn.tiktok.com/services/market/service-detail/...&state=BASE64...'
```

## 14) Sanitize JSON hồ sơ trước khi đưa vào V2

Script `scripts/sanitize_profile_json.py`:
- ẩn/mask trường nhạy cảm (password, token, email, phone, ip, ...)
- bỏ các block quá nhạy cảm (`metadata`, `socialMedia`, `guid`, `uuid`)
- hỗ trợ best-effort parse cho JSON bị cắt dở (`--allow-trailing-fragment`)

Ví dụ từ file:

```bash
python3 scripts/sanitize_profile_json.py \
  --input-file /path/to/profile.json \
  --output-file /tmp/profile.sanitized.json
```

Ví dụ cho payload dở:

```bash
python3 scripts/sanitize_profile_json.py \
  --input-file /path/to/profile.partial.json \
  --allow-trailing-fragment \
  --output-file /tmp/profile.sanitized.json
```

## 15) Build credentials cho order scanner

Script `scripts/build_scanner_credentials.py` tạo các file `.json` credentials từ
`/tmp/v2-cleaned/latest/v2_bulk_accounts_<platform>.txt` để scanner có input.

Ví dụ:

```bash
python3 scripts/build_scanner_credentials.py --clear-output --max-per-platform 300
```

Output mặc định:
- `/home/ubuntu/scan-tool-integration/credentials/*.json`

Script cũng tự sinh cookie bundle cho nền tảng cookie-based (nếu có dữ liệu tab-cookie):
- `<platform>_cookie_bundle.json`

Chạy scanner platform-aware:

```bash
python3 scripts/order_scanner_runner.py --credentials-dir /home/ubuntu/scan-tool-integration/credentials
```
