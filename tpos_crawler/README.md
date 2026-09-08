# tpos_crawler

Crawler độc lập cho J&T Vietnam và TikTok.

## Cấu trúc

```text
tpos_crawler/
├── configs/
│   ├── config_jt.json
│   └── config_tiktok.json
├── jt_vietnam_api.py
└── tiktok_automation.py
```

## Cấu hình

### `configs/config_jt.json`

| Trường | Bắt buộc | Mô tả |
|---|---|---|
| `username` | Có | Tên shop hiển thị trên báo cáo Excel |
| `password` | Không | Dự phòng (chưa dùng cho login tự động) |
| `cookies.PHPSESSID` | Một trong hai | Cookie session J&T VIP |
| `cookies.user_auth` | Một trong hai | Cookie session J&T VIP |
| `cookie_excel` | Thay thế cookies | File Excel export cookie (cột name/value) |
| `proxy` | Không | Proxy HTTP/S cho từng tài khoản |

**Ưu tiên cookie:** `cookies` trong JSON → nếu trống thì đọc `cookie_excel`.

**Settings:**

| Trường | Mặc định | Mô tả |
|---|---|---|
| `output_excel` | `outputs/báo_cáo_đơn_đang_giao.xlsx` | File Excel đầu ra |
| `days_back` | `3` | Số ngày lùi để lấy đơn |
| `order_status` | `IN_TRANSIT` | Trạng thái đơn cần lọc |
| `api_url` | `https://jtexpress.vn` | Endpoint POST lấy đơn |

### `configs/config_tiktok.json` (TPOS / TikTok livestream orders)

| Trường | Bắt buộc | Mô tả |
|---|---|---|
| `shop` | Có | Subdomain TPOS (vd: `myshop` → `myshop.tpos.vn`) |
| `username` | Có | Email đăng nhập TPOS |
| `password` | Có | Mật khẩu TPOS |
| `proxy` | Không | Proxy Playwright cho từng tài khoản |

**Settings:**

| Trường | Mặc định | Mô tả |
|---|---|---|
| `omocaptcha_api_key` | _(trống)_ | API key OmoCaptcha giải ReCAPTCHA |
| `output_excel` | `outputs/báo_cáo_đơn_hàng_tpos.xlsx` | File Excel đầu ra |
| `session_dir` | `outputs/tpos_sessions` | Lưu session sau login |
| `days_back` | `3` | Số ngày lùi để lấy đơn |
| `headless` | `false` | `true` = chạy ẩn trình duyệt |

Điền danh sách tài khoản vào file config tương ứng. Mỗi phần tử trong `accounts` là một tài khoản riêng.

## Chạy

```bash
cd tpos_crawler
pip install -r requirements.txt
playwright install chromium
python jt_vietnam_api.py
python tiktok_automation.py
```

Mỗi script chỉ đọc file config của riêng nó, không phụ thuộc lẫn nhau.
