#!/usr/bin/env python3
"""Đóng gói quy trình giải mã AES + key đầy đủ → gửi Telegram.

Tạo kit tự chứa:
  - mapper_decrypt_workflow.py
  - mapper_aes_codec.py
  - README (hướng dẫn)
  - mapper_aes.key          (key đầy đủ, mode 600 trong zip)
  - env.sh                  (export MAPPER_AES_KEY_B64=...)
  - run_decrypt.sh          (một lệnh giải mã)

Rồi gửi zip + caption về TELEGRAM_CHAT_ID.

Usage:
  python3 scripts/send_mapper_decrypt_kit_telegram.py
  python3 scripts/send_mapper_decrypt_kit_telegram.py --also-sample /tmp/icon-call-pii-aes.json
  python3 scripts/send_mapper_decrypt_kit_telegram.py --dry-run   # chỉ tạo zip, không gửi
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_KEY = Path(
    os.getenv("MAPPER_AES_KEY_FILE", "/home/ubuntu/.config/scantool/mapper_aes.key")
)
OUT_ROOT = Path(os.getenv("MAPPER_KIT_OUT", "/tmp/mapper_decrypt_telegram"))


def load_env() -> None:
    for path in (
        Path("/home/ubuntu/.config/scantool/asunmee.env"),
        SCRIPT_DIR / ".env.vn-platforms",
    ):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def read_key_b64(key_file: Path) -> str:
    if not key_file.exists():
        raise FileNotFoundError(f"Missing AES key file: {key_file}")
    raw = key_file.read_bytes().strip()
    if len(raw) == 32:
        return base64.b64encode(raw).decode("ascii")
    # already base64 text
    text = raw.decode("ascii").strip()
    decoded = base64.b64decode(text)
    if len(decoded) != 32:
        raise ValueError(f"AES key must be 32 bytes, got {len(decoded)}")
    return text


def write_readme(dest: Path, key_b64: str) -> None:
    guide = SCRIPT_DIR / "reference" / "mapper_decrypt_workflow_vi.md"
    extra = f"""# Mapper decrypt kit (Telegram)

Gói này gồm **script giải mã + key đầy đủ** để dùng khi cần, trên máy bất kỳ.

## Quick start

```bash
unzip mapper-decrypt-kit-*.zip
cd mapper-decrypt-kit-*
chmod +x run_decrypt.sh
./run_decrypt.sh /path/to/icon-call-aes.json
# hoặc
source ./env.sh
python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary
```

## Key (đã kèm trong gói)

- File: `mapper_aes.key` (1 dòng base64, 32-byte AES-256)
- Env helper: `source ./env.sh` → set `MAPPER_AES_KEY_B64`
- Key preview: `{key_b64[:8]}...{key_b64[-8:]}`

## Phụ thuộc

```bash
pip install cryptography
```

## Lớp mã hóa

- Outer: AES-256-GCM (`aad=mapper-icon-aes-v1`)
- Inner: mask envelope (PII Pancake vẫn có `*` — AES không giải che tên/SĐT thật)

## Bảo mật

- Chỉ giữ trên máy / chat Telegram của bạn
- Không forward công khai, không commit git
- Nếu lộ: tạo key mới bằng `mapper_aes_codec` rồi gửi kit lại

"""
    body = extra
    if guide.exists():
        body += "\n---\n\n" + guide.read_text(encoding="utf-8")
    dest.write_text(body, encoding="utf-8")


def build_kit(key_file: Path, out_root: Path) -> tuple[Path, Path, str]:
    key_b64 = read_key_b64(key_file)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    kit_dir = out_root / f"mapper-decrypt-kit-{stamp}"
    if kit_dir.exists():
        shutil.rmtree(kit_dir)
    kit_dir.mkdir(parents=True)

    # core scripts
    for name in ("mapper_decrypt_workflow.py", "mapper_aes_codec.py"):
        src = SCRIPT_DIR / name
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copy2(src, kit_dir / name)

    # key full
    key_path = kit_dir / "mapper_aes.key"
    key_path.write_text(key_b64 + "\n", encoding="utf-8")
    os.chmod(key_path, 0o600)

    # env.sh with FULL key for one-liner use
    (kit_dir / "env.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# Source this file: source ./env.sh\n"
        f"export MAPPER_AES_KEY_B64='{key_b64}'\n"
        "export MAPPER_AES_KEY_FILE=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)/mapper_aes.key\"\n"
        "echo \"MAPPER_AES_KEY_B64 set ($(echo -n \"$MAPPER_AES_KEY_B64\" | wc -c) chars)\"\n",
        encoding="utf-8",
    )
    os.chmod(kit_dir / "env.sh", 0o700)

    # one-shot runner
    (kit_dir / "run_decrypt.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "DIR=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
        "cd \"$DIR\"\n"
        "# shellcheck disable=SC1091\n"
        "source \"$DIR/env.sh\"\n"
        "INPUT=\"${1:-}\"\n"
        "if [[ -z \"$INPUT\" ]]; then\n"
        "  echo \"Usage: ./run_decrypt.sh <aes-json> [--full]\" >&2\n"
        "  exit 2\n"
        "fi\n"
        "if [[ \"${2:-}\" == \"--full\" ]]; then\n"
        "  python3 \"$DIR/mapper_decrypt_workflow.py\" decrypt --input \"$INPUT\" -o \"${INPUT%.json}.decrypted.json\"\n"
        "  echo \"Wrote ${INPUT%.json}.decrypted.json\"\n"
        "else\n"
        "  python3 \"$DIR/mapper_decrypt_workflow.py\" decrypt --input \"$INPUT\" --summary\n"
        "fi\n",
        encoding="utf-8",
    )
    os.chmod(kit_dir / "run_decrypt.sh", 0o755)

    write_readme(kit_dir / "README.md", key_b64)

    # standalone key message file (plain, for quick copy)
    (kit_dir / "KEY_FULL.txt").write_text(
        "# MAPPER AES-256 key (base64) — giữ bí mật\n"
        f"MAPPER_AES_KEY_B64={key_b64}\n"
        f"# exported_at={stamp}\n"
        "# usage:\n"
        f"#   export MAPPER_AES_KEY_B64='{key_b64}'\n"
        "#   python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary\n",
        encoding="utf-8",
    )
    os.chmod(kit_dir / "KEY_FULL.txt", 0o600)

    manifest = {
        "kit": "mapper-decrypt-telegram",
        "created_at": stamp,
        "includes_full_key": True,
        "key_chars": len(key_b64),
        "key_preview": f"{key_b64[:8]}...{key_b64[-8:]}",
        "files": sorted(p.name for p in kit_dir.iterdir()),
        "run": "./run_decrypt.sh payload.json",
        "deps": "pip install cryptography",
    }
    (kit_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    zip_path = out_root / f"mapper-decrypt-kit-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(kit_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=f"{kit_dir.name}/{path.relative_to(kit_dir)}")

    return kit_dir, zip_path, key_b64


def send_telegram_document(token: str, chat_id: str, path: Path, caption: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with path.open("rb") as fh:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"document": (path.name, fh)},
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def send_telegram_message(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def parse_args() -> argparse.Namespace:
    load_env()
    p = argparse.ArgumentParser(description="Build mapper decrypt kit with full key → Telegram.")
    p.add_argument("--key-file", default=str(DEFAULT_KEY))
    p.add_argument("--out-dir", default=str(OUT_ROOT))
    p.add_argument("--also-sample", default="", help="Optional AES JSON sample to attach")
    p.add_argument("--dry-run", action="store_true", help="Build zip only, do not send")
    p.add_argument("--no-key-message", action="store_true", help="Do not send KEY_FULL as separate message")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    kit_dir, zip_path, key_b64 = build_kit(Path(args.key_file), Path(args.out_dir))

    report = {
        "ok": True,
        "kit_dir": str(kit_dir),
        "zip": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "key_preview": f"{key_b64[:8]}...{key_b64[-8:]}",
        "key_chars": len(key_b64),
        "telegram": None,
    }

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        report["ok"] = False
        report["error"] = "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    caption = (
        "Mapper decrypt kit + KEY đầy đủ\n"
        "Giải AES lớp ngoài → mask lớp trong.\n\n"
        "Cách dùng:\n"
        "1) Unzip\n"
        "2) pip install cryptography\n"
        "3) ./run_decrypt.sh <file-aes.json>\n"
        "   hoặc: source ./env.sh && python3 mapper_decrypt_workflow.py decrypt -i file.json --summary\n\n"
        f"Key preview: {key_b64[:8]}...{key_b64[-8:]} ({len(key_b64)} chars)\n"
        "Giữ riêng — không forward công khai."
    )

    tg = {"documents": [], "messages": []}
    doc = send_telegram_document(token, chat, zip_path, caption)
    tg["documents"].append({"file": zip_path.name, "ok": bool(doc.get("ok")), "result": doc.get("ok")})

    if not args.no_key_message:
        # Separate message with full key for quick copy on phone
        key_msg = (
            "MAPPER_AES_KEY_B64 (FULL) — copy khi cần:\n\n"
            f"`{key_b64}`\n\n"
            "export MAPPER_AES_KEY_B64='(dán key)'\n"
            "python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary"
        )
        # Telegram markdown with long key — send as plain text to avoid parse issues
        msg = send_telegram_message(
            token,
            chat,
            "MAPPER_AES_KEY_B64 (FULL) — copy khi cần:\n\n"
            f"{key_b64}\n\n"
            "export MAPPER_AES_KEY_B64='(dán key trên)'\n"
            "python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary",
        )
        tg["messages"].append({"ok": bool(msg.get("ok"))})
        # also send KEY_FULL.txt as document for easy save
        key_txt = kit_dir / "KEY_FULL.txt"
        kdoc = send_telegram_document(
            token,
            chat,
            key_txt,
            "KEY_FULL.txt — lưu riêng, chmod 600. Đi kèm zip kit.",
        )
        tg["documents"].append({"file": key_txt.name, "ok": bool(kdoc.get("ok"))})

    if args.also_sample:
        sample = Path(args.also_sample)
        if sample.exists():
            sdoc = send_telegram_document(
                token,
                chat,
                sample,
                "Sample AES payload — thử: ./run_decrypt.sh file-này.json",
            )
            tg["documents"].append({"file": sample.name, "ok": bool(sdoc.get("ok"))})

    report["telegram"] = tg
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(d.get("ok") for d in tg["documents"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
