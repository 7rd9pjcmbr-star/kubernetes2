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

### `configs/config_tiktok.json`

| Trường | Bắt buộc | Mô tả |
|---|---|---|
| `username` | Có | Tài khoản TikTok Seller |
| `password` | Có | Mật khẩu |
| `access_token` | Khuyến nghị | Token TikTok Shop Open API để lấy đơn |
| `shop_id` | Không | Shop ID nếu có nhiều shop |
| `proxy` | Không | Proxy HTTP/S cho từng tài khoản |

Điền danh sách tài khoản vào file config tương ứng. Mỗi phần tử trong `accounts` là một tài khoản riêng.

## Chạy

```bash
cd tpos_crawler
pip install -r requirements.txt
python jt_vietnam_api.py
python tiktok_automation.py
```

Mỗi script chỉ đọc file config của riêng nó, không phụ thuộc lẫn nhau.
