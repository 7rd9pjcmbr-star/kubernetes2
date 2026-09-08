# Logistics_tool

Công cụ logistics độc lập: J&T Vietnam + TPOS (TikTok livestream orders).

## Cấu trúc

```text
Logistics_tool/
├── configs/
│   ├── config_jt.json       # J&T Express VN
│   └── config_tiktok.json   # TPOS (.tpos.vn)
├── outputs/                 # Excel + session (tự tạo khi chạy)
│   ├── báo_cáo_đơn_đang_giao.xlsx
│   ├── báo_cáo_đơn_hàng_tpos.xlsx
│   └── tpos_sessions/
├── jt_vietnam_api.py
├── tiktok_automation.py
└── requirements.txt
```

## Cấu hình

### `configs/config_jt.json`

| Trường | Bắt buộc | Mô tả |
|---|---|---|
| `username` | Có | Tên shop hiển thị trên báo cáo Excel |
| `cookies.PHPSESSID` | Một trong hai | Cookie session J&T VIP |
| `cookies.user_auth` | Một trong hai | Cookie session J&T VIP |
| `cookie_excel` | Thay thế cookies | File Excel export cookie |
| `proxy` | Không | Proxy HTTP/S cho từng tài khoản |

### `configs/config_tiktok.json`

| Trường | Bắt buộc | Mô tả |
|---|---|---|
| `shop` | Có | Subdomain TPOS (`myshop` → `myshop.tpos.vn`) |
| `username` | Có | Email đăng nhập TPOS |
| `password` | Có | Mật khẩu TPOS |
| `proxy` | Không | Proxy Playwright cho từng tài khoản |

Settings TPOS: `omocaptcha_api_key`, `output_excel`, `session_dir`, `days_back`, `headless`.

## Chạy

```bash
cd Logistics_tool
pip install -r requirements.txt
playwright install chromium
python jt_vietnam_api.py
python tiktok_automation.py
```

Hai script hoàn toàn độc lập — mỗi script chỉ đọc file config của riêng nó.
