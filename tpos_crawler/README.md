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
| `username` | Có | Mã/tài khoản J&T |
| `password` | Có | Mật khẩu plaintext |
| `customer_code` | Khuyến nghị | Mã khách hàng Open API |
| `api_account` | Khuyến nghị | apiAccount header |
| `private_key` | Khuyến nghị | Khóa ký request Open API |
| `proxy` | Không | Proxy HTTP/S cho từng tài khoản |

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
python jt_vietnam_api.py
python tiktok_automation.py
```

Mỗi script chỉ đọc file config của riêng nó, không phụ thuộc lẫn nhau.
