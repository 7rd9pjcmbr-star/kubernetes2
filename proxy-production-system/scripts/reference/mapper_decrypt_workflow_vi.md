# Quy trình giải mã mapper AES (dùng lại ở bất cứ đâu)

## Mục tiêu
Mang **cùng một quy trình** sang máy khác / CI / laptop để mở file mapper đã bọc AES.

```
[wire JSON]  --AES-256-GCM-->  [inner mask envelope]  --(không)--  [PII rõ]
     outer                         inner                    Pancake '*' vẫn che
```

AES **chỉ** mở lớp ngoài. Tên/SĐT dạng `T******z` không trở thành plaintext qua bước này.

## Protocol (ổn định)

| Field | Value |
|-------|--------|
| Alg | AES-256-GCM |
| Key | 32 bytes (base64 trong file/env) |
| Nonce | 12 bytes → `nonce_b64` |
| AAD | `mapper-icon-aes-v1` (bắt buộc đúng) |
| Wire | `encoding=aes-256-gcm` + `ciphertext_b64` |
| Wrap | `{ "aes": { ... } }` hoặc `{ "calls": [ { "aes": ... } ] }` |

## Chuẩn bị máy mới (1 lần)

```bash
pip install cryptography

# Cách A — env (khuyến nghị khi mang đi)
export MAPPER_AES_KEY_B64='<base64 32-byte key>'

# Cách B — file cạnh script
# ./mapper_aes.key  (1 dòng base64, chmod 600)
```

Xuất key từ máy nguồn (máy tin cậy):

```bash
python3 scripts/mapper_decrypt_workflow.py export-key --print-secret
# hoặc
python3 scripts/mapper_decrypt_workflow.py export-key -o /secure/mapper_aes.key.b64
```

## Giải mã (hàng ngày)

```bash
# 1 file → full plaintext inner
python3 scripts/mapper_decrypt_workflow.py decrypt \
  --input /path/to/icon-call-pii-aes.json \
  -o /tmp/plain.json

# Chỉ tóm tắt mask (nhanh, ít lộ)
python3 scripts/mapper_decrypt_workflow.py decrypt \
  --input /path/to/icon-call-pii-aes.json --summary

# Stdin (pipe từ curl / telegram / scp)
cat payload.json | python3 scripts/mapper_decrypt_workflow.py decrypt --stdin --summary

# Cả thư mục
python3 scripts/mapper_decrypt_workflow.py decrypt \
  --input-dir ./inbox --output-dir ./out --summary

# Key tường minh trên máy lạ
python3 scripts/mapper_decrypt_workflow.py decrypt \
  --key-b64 "$MAPPER_AES_KEY_B64" \
  --input payload.json --summary
```

Tương đương codec mỏng:

```bash
python3 scripts/mapper_aes_codec.py --decrypt-json payload.json -o plain.json
```

## Đóng gói mang đi

```bash
python3 scripts/mapper_decrypt_workflow.py bundle --output-dir ./mapper-decrypt-kit
# (tuỳ chọn, nhạy cảm) thêm key vào kit:
python3 scripts/mapper_decrypt_workflow.py bundle --output-dir ./kit --include-key

cd mapper-decrypt-kit
pip install cryptography
export MAPPER_AES_KEY_B64='...'
python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary
```

Kit gồm: `mapper_decrypt_workflow.py`, `mapper_aes_codec.py`, `README.md`, `env.example`, `manifest.json`.

## Tạo ciphertext (máy nguồn)

```bash
python3 scripts/mapper_icon_call.py --pii --deep --aes -o icon-call-pii-aes.json
```

## Checklist lỗi thường gặp

| Triệu chứng | Cách xử lý |
|-------------|------------|
| `Missing AES key` | Set `MAPPER_AES_KEY_B64` hoặc `--key-file` |
| `Unsupported encoding` | File không phải envelope AES mapper |
| `InvalidTag` / decrypt fail | Sai key hoặc ciphertext/nonce/aad bị cắt |
| Inner vẫn `masked: true` | Đúng thiết kế — cần cookie/OAuth POS để giải che PII |

## Bảo mật
- Không commit `mapper_aes.key` / `MAPPER_AES_KEY_B64`
- `--include-key` chỉ dùng USB/máy nội bộ
- File `*.decrypted.json` vẫn có thể chứa PII đã mask — không public nếu không cần
