# Hỗ trợ đặc biệt cho người khuyết tật (Pancake / ScanTool)

## Mục tiêu
Giúp người dùng khiếm thị / hạn chế vận động đọc và xử lý đơn hàng ASUNMEE khi giao diện đang **che** tên/SĐT.

## Đổi code → giải che (OAuth)

Sau login `account.pancake.vn`, browser redirect về callback có `code=...`.
Đổi code bằng **GET** `pancake_id_login_success` (không dùng `/oauth/token` — 404).

```bash
# 1) Login (email), copy URL callback đầy đủ có code=
# 2) Đổi code → lưu cookie local + probe PII
python3 scripts/pancake_code_unmask.py \
  --callback-url 'https://pancake.vn/api/v1/users/pancake_id_login_success?code=YOUR_CODE&state=...' \
  --require-pos-login

# Hoặc dán Cookie từ DevTools (Application → Cookies → pos.pancake.vn)
python3 scripts/pancake_code_unmask.py --cookie 'token=...; ...' --probe
```

Cookie/token ghi vào `/home/ubuntu/.config/scantool/asunmee.env` (local, không commit).
Nếu probe báo `unmask_ready`, chạy tiếp `speak_orders_accessibility.py`.

## Giải mã AES mapper (portable)

```bash
python3 scripts/mapper_decrypt_workflow.py decrypt --input icon-call-pii-aes.json --summary
python3 scripts/mapper_decrypt_workflow.py bundle --output-dir ./mapper-decrypt-kit
```

Chi tiết: `scripts/reference/mapper_decrypt_workflow_vi.md`

## Gửi kit + key về Telegram (khi cần mang theo)

```bash
python3 scripts/send_mapper_decrypt_kit_telegram.py
# hoặc
make mapper-decrypt-telegram
```

Bot gửi:
1. `mapper-decrypt-kit-*.zip` — script + `mapper_aes.key` + `env.sh` + `run_decrypt.sh`
2. Tin nhắn chứa **MAPPER_AES_KEY_B64 đầy đủ** (copy nhanh)
3. `KEY_FULL.txt` — lưu riêng

Trên điện thoại/máy khác: unzip → `pip install cryptography` → `./run_decrypt.sh file-aes.json`

## Công cụ
- `scripts/send_mapper_decrypt_kit_telegram.py` — đóng gói + gửi Telegram (kèm key)
- `scripts/mapper_decrypt_workflow.py` — quy trình giải mã AES dùng lại everywhere
- `scripts/pancake_code_unmask.py` — đổi OAuth code / cookie → giải che
- `scripts/pancake_oauth_helper.py` — parse callback + in curl exchange
- `scripts/pancake_a11y_unmask_hook.js` — bộ hỗ trợ AT trên tab POS
- `scripts/pancake_orders_unmask_hook.js` — bắt response mạng + nhận dữ liệu a11y

## Cách dùng (NVDA / JAWS / VoiceOver)
1. Đăng nhập `https://pos.pancake.vn/shop/714934229/order`
2. Mở DevTools Console, dán `pancake_a11y_unmask_hook.js`
3. Dùng phím tắt (không cần chuột):

| Phím | Việc |
|------|------|
| `Alt+Shift+S` | Quét Accessibility tree |
| `Alt+Shift+P` | Vá ô bị mask |
| `Alt+Shift+E` | Xuất JSON |
| `Alt+Shift+H` | Tương phản cao + chữ lớn |
| `Alt+Shift+R` | Đọc tóm tắt qua `aria-live` |
| `Alt+Shift+/` | Trợ giúp |

4. Screen reader sẽ nghe thông báo từ vùng `aria-live`
5. Gửi file JSON export lại pipeline để Excel / Telegram

## Vì sao cần a11y?
- Open API key Pancake **giữ mask PII** theo thiết kế
- Accessible name / `aria-label` đôi khi vẫn chứa giá trị đầy đủ để AT đọc
- Cách này bám nguyên tắc **parity với công nghệ hỗ trợ**, trên session shop của bạn

## Frida — hỗ trợ đặc biệt (TalkBack / hạn chế vận động)

Dùng khi cần đọc accessibility tree trên **app POS Android** hoặc tiêm a11y vào WebView.

```bash
# Cloud / không có máy: demo mapper + TTS + AES
python3 scripts/frida_a11y_assist.py --offline-demo --telegram

# Máy thật (USB), app Pancake POS đã cài frida-server
python3 scripts/frida_a11y_assist.py -U --list-processes
python3 scripts/frida_a11y_assist.py -U -n <tên_process> --scan --speak --export --aes
```

Script Frida: `scripts/frida_a11y_disability.js`  
- Hook `AccessibilityNodeInfo.getText` / `getContentDescription` (TalkBack parity)  
- Tiêm live region vào WebView Pancake  
- RPC: `ping` / `scan` / `exportNodes` / `speak`

Chỉ dùng trên thiết bị và tài khoản shop bạn được phép (ASUNMEE).

## Fingerprint spoof (máy test / a11y)

Ổn định phiên automation a11y trên **thiết bị của bạn** (không dùng để farm / gian lận).

```bash
# Frida: a11y + spoof Build/ANDROID_ID/UA
python3 scripts/frida_a11y_assist.py -U -n <process_pos> \
  --spoof-fingerprint --fp-randomize --scan --speak

# Hoặc load tay
frida -U -n <process> \
  -l scripts/frida_a11y_disability.js \
  -l scripts/frida_fingerprint_spoof.js
```

Browser (tab POS đã login): dán `scripts/fingerprint_spoof_lite.js` trước hook a11y.


## Không thể thao tác UI?
Chạy một lệnh (tự lấy đơn + đọc to):

```bash
python3 scripts/speak_orders_accessibility.py --days 7 --telegram
```

Nhận trên Telegram:
- Excel 7 ngày
- MP3 đọc to tiếng Việt
- HTML tự đọc khi mở

## Xem đơn hàng chi tiết (mapper → endpoint → DB)

Luồng 3 lớp:
1. UI: mã hiển thị (`order_code` / `display_id`)
2. Mapper: resolve → `shop_id` + `order_id`
3. Endpoint/DB: `GET /shops/{shop}/orders/{id}` + cache SQLite

```bash
# Đồng bộ 7 ngày vào DB local
python3 scripts/query_order_detail.py --sync-days 7 --detail-limit 0

# Xem chi tiết (ưu tiên DB; --refresh để gọi lại endpoint)
python3 scripts/query_order_detail.py --order-code <order_id> --refresh --full --telegram

# Liệt kê đơn gần nhất trong DB
python3 scripts/query_order_detail.py --list 20
```

DB mặc định: `/home/ubuntu/.config/scantool/asunmee_orders.db`  
Map: `/home/ubuntu/.config/scantool/asunmee_display_map.json`
