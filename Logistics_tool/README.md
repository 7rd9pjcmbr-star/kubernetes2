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

## Chạy trên VPS (tránh bị chặn)

Cloud VPS thường dùng IP datacenter — J&T và TPOS dễ chặn nếu không có proxy.

1. **Bắt buộc dùng proxy residential/VN** — điền vào từng account hoặc `configs/proxy.txt`:

```text
103.1.2.3:8080
103.1.2.4:8080:user:pass
```

2. **Copy config từ máy Windows lên VPS:**

```powershell
# Trên Windows
scp -r C:\Users\Administrator\Documents\tpos_crawler\configs\* user@VPS_IP:/path/Logistics_tool/configs/
```

Hoặc copy thủ công: `config_jt.json`, `config_tiktok.json`, `proxy.txt`, `cookie_tho.xlsx`.

3. **Chạy trên VPS** (tự bật headless + delay giữa tài khoản):

```bash
cd Logistics_tool
pip install -r requirements.txt
playwright install chromium
python jt_vietnam_api.py
python tiktok_automation.py
```

4. **Tái sử dụng session TPOS** — lần chạy sau sẽ thử dùng `outputs/tpos_sessions/*.json` trước khi login lại (giảm captcha).

5. **Tuning** trong `settings.anti_block`:
   - `delay_between_accounts_min/max` — nghỉ giữa shop
   - `require_proxy_on_vps` — cảnh báo nếu thiếu proxy
   - `reuse_tpos_session` — bật/tắt dùng lại session
   - `headless_on_vps` — mặc định `true` trên VPS
