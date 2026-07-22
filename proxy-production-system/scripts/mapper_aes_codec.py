#!/usr/bin/env python3
"""AES-GCM codec for mapper icon-call responses (local key only).

Encrypts the JSON envelope returned by mapper_icon_call so the wire/file
payload is AES ciphertext. Does NOT decrypt Pancake PII masks — those stay
masked inside the plaintext before encryption.

Key file (mode 600): /home/ubuntu/.config/scantool/mapper_aes.key
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


DEFAULT_KEY_PATH = Path(
    os.getenv("MAPPER_AES_KEY_FILE", "/home/ubuntu/.config/scantool/mapper_aes.key")
)
DEFAULT_KEY_ENV = "MAPPER_AES_KEY_B64"


def load_or_create_key(path: Path | None = None) -> bytes:
    """32-byte AES-256 key from env or local file (created if missing)."""
    env = os.getenv(DEFAULT_KEY_ENV, "").strip()
    if env:
        return base64.b64decode(env)

    key_path = Path(path or DEFAULT_KEY_PATH)
    if key_path.exists():
        raw = key_path.read_bytes().strip()
        # allow raw 32 bytes or base64 text
        if len(raw) == 32:
            return raw
        return base64.b64decode(raw)

    key = AESGCM.generate_key(bit_length=256)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(base64.b64encode(key).decode("ascii") + "\n", encoding="utf-8")
    key_path.chmod(0o600)
    return key


def encrypt_payload(payload: dict[str, Any] | list[Any] | str | bytes, key: bytes | None = None) -> dict[str, Any]:
    """AES-256-GCM encrypt JSON payload → portable envelope."""
    aes_key = key or load_or_create_key()
    if isinstance(payload, (dict, list)):
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        plaintext = payload.encode("utf-8")
    else:
        plaintext = payload

    nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(aes_key)
    # Bind AAD to mapper protocol version
    aad = b"mapper-icon-aes-v1"
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return {
        "encoding": "aes-256-gcm",
        "alg": "AESGCM",
        "v": 1,
        "aad": "mapper-icon-aes-v1",
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_sha256_16": __import__("hashlib").sha256(plaintext).hexdigest()[:16],
        "encrypted_at": datetime.now(timezone.utc).isoformat(),
    }


def decrypt_envelope(envelope: dict[str, Any], key: bytes | None = None) -> Any:
    """Decrypt AES envelope back to JSON object / text."""
    if envelope.get("encoding") != "aes-256-gcm":
        raise ValueError(f"unsupported encoding: {envelope.get('encoding')}")
    aes_key = key or load_or_create_key()
    nonce = base64.b64decode(envelope["nonce_b64"])
    ciphertext = base64.b64decode(envelope["ciphertext_b64"])
    aad = (envelope.get("aad") or "mapper-icon-aes-v1").encode("utf-8")
    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    try:
        return json.loads(plaintext.decode("utf-8"))
    except json.JSONDecodeError:
        return plaintext.decode("utf-8")


def wrap_icon_response(icon: str, response: dict[str, Any], key: bytes | None = None) -> dict[str, Any]:
    """Attach AES ciphertext as the primary wire response for an icon call."""
    encrypted = encrypt_payload(response, key=key)
    return {
        "ok": bool(response.get("ok", True)),
        "call": {
            "icon_input": icon,
            "icon_real": (response.get("call") or {}).get("icon_real"),
            "transport": "aes-256-gcm",
        },
        "encoding": {
            "mode": "aes-256-gcm",
            "layer": "outer",
            "inner": (response.get("encoding") or {}).get("mode", "mask"),
            "inner_layer": (response.get("encoding") or {}).get("layer", "inner"),
            "note": "Outer AES wraps inner masked PII mapper envelope. AES does not unmask Pancake PII.",
        },
        "aes": encrypted,
        # optional tiny plaintext meta (no PII)
        "meta": {
            "domain": (response.get("backend") or {}).get("domain"),
            "path": (response.get("backend") or {}).get("list_path"),
            "http_status": (response.get("response") or {}).get("http_status"),
            "count": (response.get("response") or {}).get("count"),
            "total_entries": (response.get("response") or {}).get("total_entries"),
        },
    }


def parse_args():
    p = argparse.ArgumentParser(description="AES codec for mapper icon responses.")
    p.add_argument("--encrypt-json", default="", help="Encrypt a JSON file")
    p.add_argument("--decrypt-json", default="", help="Decrypt an AES envelope JSON file")
    p.add_argument("--key-file", default=str(DEFAULT_KEY_PATH))
    p.add_argument("--output", default="")
    p.add_argument(
        "--summary",
        action="store_true",
        help="With --decrypt-json: prefer mapper_decrypt_workflow summary via hint.",
    )
    return p.parse_args()


def _decrypt_any(envelope: dict[str, Any], key: bytes) -> Any:
    """Accept raw aes block, {aes: ...}, or {calls: [{aes: ...}]}."""
    if envelope.get("encoding") == "aes-256-gcm" and "ciphertext_b64" in envelope:
        return decrypt_envelope(envelope, key=key)
    if isinstance(envelope.get("aes"), dict):
        return decrypt_envelope(envelope["aes"], key=key)
    calls = envelope.get("calls")
    if isinstance(calls, list):
        out = []
        for item in calls:
            if isinstance(item, dict) and isinstance(item.get("aes"), dict):
                out.append(decrypt_envelope(item["aes"], key=key))
            elif isinstance(item, dict) and item.get("encoding") == "aes-256-gcm":
                out.append(decrypt_envelope(item, key=key))
            else:
                out.append(item)
        return {"calls": out}
    raise ValueError("No AES block found in JSON")


def main():
    args = parse_args()
    key = load_or_create_key(Path(args.key_file))
    if args.encrypt_json:
        payload = json.loads(Path(args.encrypt_json).read_text(encoding="utf-8"))
        out = encrypt_payload(payload, key=key)
    elif args.decrypt_json:
        envelope = json.loads(Path(args.decrypt_json).read_text(encoding="utf-8"))
        out = _decrypt_any(envelope, key)
        if args.summary:
            print(
                json.dumps(
                    {
                        "hint": "Use mapper_decrypt_workflow.py decrypt --summary for rich PII summary",
                        "ok": True,
                    },
                    ensure_ascii=False,
                ),
                file=__import__("sys").stderr,
            )
    else:
        print(json.dumps({"error": "use --encrypt-json or --decrypt-json", "key_file": args.key_file}, indent=2))
        return 2

    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
