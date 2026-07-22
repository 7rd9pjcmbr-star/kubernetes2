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
| `PROXY_STATIC_ROOT` | Không | _(trống)_ | Thư mục static root để bật route UI (`/v2`, `/v3`) |
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

## 12) Pancake OAuth — đổi code giải che PII

POS login trả `code` về `pancake_id_login_success` (GET). Không dùng `account.pancake.vn/oauth/token` (404).

```bash
# Đổi code → lưu cookie local + probe mask/unmask
python3 scripts/pancake_code_unmask.py \
  --callback-url 'https://pancake.vn/api/v1/users/pancake_id_login_success?code=YOUR_CODE&state=BASE64_STATE' \
  --require-pos-login

# Chỉ parse + in curl
python3 scripts/pancake_oauth_helper.py \
  --callback-url 'https://pancake.vn/api/v1/users/pancake_id_login_success?code=YOUR_CODE&state=BASE64_STATE' \
  --client-id '53e2d5e33a8940f4a30ba22a4011e52a' \
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
