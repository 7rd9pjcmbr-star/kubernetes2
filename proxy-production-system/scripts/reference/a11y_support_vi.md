# Hỗ trợ đặc biệt cho người khuyết tật (Pancake / ScanTool)

## Mục tiêu
Giúp người dùng khiếm thị / hạn chế vận động đọc và xử lý đơn hàng ASUNMEE khi giao diện đang **che** tên/SĐT.

## Công cụ
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

## Lưu ý
- Chỉ dùng trên tài khoản/shop bạn được phép truy cập (ASUNMEE)
- Không thay thế quyền pháp lý / chính sách bảo mật của nền tảng
