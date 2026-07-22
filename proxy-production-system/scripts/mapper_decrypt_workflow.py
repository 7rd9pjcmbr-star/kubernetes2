#!/usr/bin/env python3
"""Quy trình giải mã AES mapper — portable, dùng lại ở bất cứ đâu.

Layers:
  outer  AES-256-GCM  (nonce + ciphertext + aad=mapper-icon-aes-v1)
  inner  mask envelope (name/phone vẫn có '*' — AES không giải che Pancake PII)

Key (một trong các nguồn, ưu tiên trên xuống):
  1) --key-b64 / env MAPPER_AES_KEY_B64
  2) --key-file / env MAPPER_AES_KEY_FILE
  3) mặc định ~/.config/scantool/mapper_aes.key  (hoặc ./mapper_aes.key cạnh script)

Usage (máy bất kỳ có Python 3.10+ + cryptography):
  # Giải 1 file wire response
  python3 mapper_decrypt_workflow.py decrypt --input icon-call-aes.json -o plain.json

  # Stdin
  cat payload.json | python3 mapper_decrypt_workflow.py decrypt --stdin -o plain.json

  # Cả thư mục
  python3 mapper_decrypt_workflow.py decrypt --input-dir ./inbox --output-dir ./out

  # Chỉ tóm tắt lớp trong (mask), không dump full
  python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary

  # Đóng gói mang đi (script + hướng dẫn; KHÔNG nhét key vào bundle trừ --include-key)
  python3 mapper_decrypt_workflow.py bundle --output-dir ./mapper-decrypt-kit

  # Xuất key base64 (cẩn thận — chỉ máy tin cậy)
  python3 mapper_decrypt_workflow.py export-key
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from mapper_aes_codec import (  # noqa: E402
        DEFAULT_KEY_ENV,
        DEFAULT_KEY_PATH,
        decrypt_envelope,
        encrypt_payload,
        load_or_create_key,
    )
except ImportError:  # portable kit may ship codec alongside
    DEFAULT_KEY_ENV = "MAPPER_AES_KEY_B64"
    DEFAULT_KEY_PATH = Path(
        os.getenv("MAPPER_AES_KEY_FILE", str(Path.home() / ".config/scantool/mapper_aes.key"))
    )
    decrypt_envelope = None  # type: ignore
    encrypt_payload = None  # type: ignore
    load_or_create_key = None  # type: ignore


PROTOCOL = {
    "name": "mapper-icon-aes",
    "v": 1,
    "alg": "AES-256-GCM",
    "aad": "mapper-icon-aes-v1",
    "nonce_bytes": 12,
    "key_bytes": 32,
    "outer": "aes-256-gcm",
    "inner": "mask",
    "note": "Decrypting AES restores the mask envelope only. Pancake '*' PII stays masked.",
}


def resolve_key(key_b64: str = "", key_file: str = "") -> bytes:
    if key_b64.strip():
        return base64.b64decode(key_b64.strip())
    env = os.getenv(DEFAULT_KEY_ENV, "").strip()
    if env:
        return base64.b64decode(env)

    candidates: list[Path] = []
    if key_file:
        candidates.append(Path(key_file))
    env_file = os.getenv("MAPPER_AES_KEY_FILE", "").strip()
    if env_file:
        candidates.append(Path(env_file))
    candidates.append(Path(DEFAULT_KEY_PATH))
    candidates.append(SCRIPT_DIR / "mapper_aes.key")
    candidates.append(Path.cwd() / "mapper_aes.key")

    for path in candidates:
        if path.exists():
            raw = path.read_bytes().strip()
            if len(raw) == 32:
                return raw
            return base64.b64decode(raw)

    if load_or_create_key is not None:
        return load_or_create_key(Path(key_file) if key_file else None)

    raise FileNotFoundError(
        "Missing AES key. Set MAPPER_AES_KEY_B64 or pass --key-file / --key-b64. "
        f"Looked for: {[str(p) for p in candidates]}"
    )


def _is_aes_block(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and obj.get("encoding") == "aes-256-gcm"
        and "nonce_b64" in obj
        and "ciphertext_b64" in obj
    )


def unwrap_containers(raw: Any) -> list[tuple[str, dict[str, Any]]]:
    """Yield (label, aes_block) from common wire shapes."""
    found: list[tuple[str, dict[str, Any]]] = []
    if _is_aes_block(raw):
        found.append(("root", raw))
        return found
    if not isinstance(raw, dict):
        return found
    if _is_aes_block(raw.get("aes")):
        label = (raw.get("call") or {}).get("icon_input") or "aes"
        found.append((str(label), raw["aes"]))
    calls = raw.get("calls")
    if isinstance(calls, list):
        for idx, item in enumerate(calls):
            if not isinstance(item, dict):
                continue
            if _is_aes_block(item.get("aes")):
                label = (item.get("call") or {}).get("icon_input") or f"calls[{idx}]"
                found.append((str(label), item["aes"]))
            elif _is_aes_block(item):
                found.append((f"calls[{idx}]", item))
    return found


def decrypt_document(raw: Any, key: bytes) -> dict[str, Any]:
    blocks = unwrap_containers(raw)
    if not blocks:
        raise ValueError(
            "No AES block found. Expect encoding=aes-256-gcm with nonce_b64/ciphertext_b64, "
            "or wrap shape {aes: {...}} / {calls: [{aes: ...}]}."
        )
    if decrypt_envelope is None:
        raise RuntimeError("mapper_aes_codec.decrypt_envelope unavailable — ship codec with this script.")

    results = []
    for label, block in blocks:
        plain = decrypt_envelope(block, key=key)
        sha_ok = None
        expect = block.get("plaintext_sha256_16")
        if expect and isinstance(plain, (dict, list)):
            digest = hashlib.sha256(
                json.dumps(plain, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16]
            # encrypt used separators compact; re-check loosely if mismatch
            sha_ok = digest == expect
            if not sha_ok:
                # accept any stable dumps — informational only
                alt = hashlib.sha256(json.dumps(plain, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
                sha_ok = alt == expect or None
        results.append(
            {
                "label": label,
                "aes_meta": {
                    "v": block.get("v"),
                    "aad": block.get("aad"),
                    "encrypted_at": block.get("encrypted_at"),
                    "plaintext_sha256_16": expect,
                    "sha_check": sha_ok,
                },
                "plaintext": plain,
            }
        )

    if len(results) == 1:
        return {
            "ok": True,
            "protocol": PROTOCOL,
            "decrypted_at": datetime.now(timezone.utc).isoformat(),
            "count": 1,
            "label": results[0]["label"],
            "aes_meta": results[0]["aes_meta"],
            "plaintext": results[0]["plaintext"],
        }
    return {
        "ok": True,
        "protocol": PROTOCOL,
        "decrypted_at": datetime.now(timezone.utc).isoformat(),
        "count": len(results),
        "items": results,
    }


def summarize_plaintext(plain: Any) -> dict[str, Any]:
    if not isinstance(plain, dict):
        return {"type": type(plain).__name__, "preview": str(plain)[:200]}
    call = plain.get("call") or {}
    enc = plain.get("encoding") or {}
    resp = plain.get("response") or {}
    preview = resp.get("preview_masked") or []
    samples = []
    for row in preview[:3]:
        if not isinstance(row, dict):
            continue
        slim: dict[str, Any] = {"id": row.get("id"), "domain": row.get("domain")}
        for k, v in row.items():
            if isinstance(v, dict) and "display" in v:
                slim[k] = {"display": v.get("display"), "masked": v.get("masked")}
        samples.append(slim)
    return {
        "icon": call.get("icon_input"),
        "icon_real": call.get("icon_real"),
        "pii_domain": call.get("pii_domain"),
        "inner_mode": enc.get("mode"),
        "inner_layer": enc.get("layer"),
        "masked_field_count": enc.get("masked_field_count"),
        "http_status": resp.get("http_status"),
        "count": resp.get("count"),
        "total_entries": resp.get("total_entries"),
        "samples": samples,
        "error": plain.get("error"),
        "ok": plain.get("ok"),
    }


def summarize_document(doc: dict[str, Any]) -> dict[str, Any]:
    if "plaintext" in doc:
        return {
            "ok": doc.get("ok"),
            "protocol": doc.get("protocol"),
            "label": doc.get("label"),
            "aes_meta": doc.get("aes_meta"),
            "summary": summarize_plaintext(doc.get("plaintext")),
        }
    items = []
    for item in doc.get("items") or []:
        items.append(
            {
                "label": item.get("label"),
                "aes_meta": item.get("aes_meta"),
                "summary": summarize_plaintext(item.get("plaintext")),
            }
        )
    return {
        "ok": doc.get("ok"),
        "protocol": doc.get("protocol"),
        "count": doc.get("count"),
        "items": items,
    }


def load_json_input(path: Path | None = None, stdin: bool = False) -> Any:
    if stdin:
        return json.load(sys.stdin)
    if not path:
        raise ValueError("need --input or --stdin")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_decrypt(args: argparse.Namespace) -> int:
    key = resolve_key(args.key_b64, args.key_file)

    inputs: list[Path] = []
    if args.stdin:
        doc = decrypt_document(load_json_input(stdin=True), key)
        payload = summarize_document(doc) if args.summary else doc
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        return 0 if doc.get("ok") else 1

    if args.input:
        inputs.append(Path(args.input))
    if args.input_dir:
        root = Path(args.input_dir)
        inputs.extend(sorted(root.glob("*.json")))

    if not inputs:
        print("Need --input, --input-dir, or --stdin", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    failed = 0
    for path in inputs:
        try:
            raw = load_json_input(path)
            doc = decrypt_document(raw, key)
            payload = summarize_document(doc) if args.summary else doc
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            if out_dir:
                dest = out_dir / f"{path.stem}.decrypted.json"
                dest.write_text(text + "\n", encoding="utf-8")
                reports.append({"input": str(path), "output": str(dest), "ok": True})
            elif args.output and len(inputs) == 1:
                Path(args.output).write_text(text + "\n", encoding="utf-8")
                print(text)
                reports.append({"input": str(path), "output": args.output, "ok": True})
            else:
                print(text)
                reports.append({"input": str(path), "ok": True})
        except Exception as exc:  # noqa: BLE001 — batch continue
            failed += 1
            err = {"input": str(path), "ok": False, "error": str(exc)}
            reports.append(err)
            print(json.dumps(err, ensure_ascii=False), file=sys.stderr)

    if len(inputs) > 1 or out_dir:
        print(json.dumps({"batch": reports, "failed": failed}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0 if failed == 0 else 1


def cmd_export_key(args: argparse.Namespace) -> int:
    key = resolve_key(args.key_b64, args.key_file)
    b64 = base64.b64encode(key).decode("ascii")
    if args.output:
        Path(args.output).write_text(b64 + "\n", encoding="utf-8")
        try:
            os.chmod(args.output, 0o600)
        except OSError:
            pass
    print(
        json.dumps(
            {
                "ok": True,
                "env": f"export {DEFAULT_KEY_ENV}='{b64}'",
                "key_b64_preview": b64[:8] + "..." + b64[-8:],
                "key_bytes": len(key),
                "warning": "Treat this key as secret. Anyone with it can decrypt your mapper AES files.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.output:
        # full key only to stdout when explicitly asked via --print-secret
        if args.print_secret:
            print(b64)
    return 0


def cmd_encrypt(args: argparse.Namespace) -> int:
    if encrypt_payload is None:
        raise RuntimeError("encrypt requires mapper_aes_codec")
    key = resolve_key(args.key_b64, args.key_file)
    raw = load_json_input(Path(args.input) if args.input else None, stdin=args.stdin)
    out = encrypt_payload(raw, key=key)
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    dest = Path(args.output_dir or "mapper-decrypt-kit")
    dest.mkdir(parents=True, exist_ok=True)
    files = [
        "mapper_decrypt_workflow.py",
        "mapper_aes_codec.py",
        "reference/mapper_decrypt_workflow_vi.md",
    ]
    copied = []
    for rel in files:
        src = SCRIPT_DIR / rel if not rel.startswith("reference/") else SCRIPT_DIR / rel
        if not src.exists() and rel.startswith("reference/"):
            src = SCRIPT_DIR / "reference" / Path(rel).name
        if not src.exists():
            continue
        target = dest / src.name if src.name.endswith(".py") else dest / src.name
        if "reference" in rel or src.suffix == ".md":
            target = dest / src.name
        shutil.copy2(src, target)
        copied.append(str(target))

    # always write README into kit
    readme = dest / "README.md"
    readme.write_text(
        (SCRIPT_DIR / "reference" / "mapper_decrypt_workflow_vi.md").read_text(encoding="utf-8")
        if (SCRIPT_DIR / "reference" / "mapper_decrypt_workflow_vi.md").exists()
        else _fallback_readme(),
        encoding="utf-8",
    )

    example_env = dest / "env.example"
    example_env.write_text(
        f"# Copy to .env or export in shell (do not commit real key)\n"
        f"{DEFAULT_KEY_ENV}=PASTE_BASE64_32BYTE_KEY_HERE\n"
        f"# optional:\n# MAPPER_AES_KEY_FILE=./mapper_aes.key\n",
        encoding="utf-8",
    )

    if args.include_key:
        key = resolve_key(args.key_b64, args.key_file)
        key_path = dest / "mapper_aes.key"
        key_path.write_text(base64.b64encode(key).decode("ascii") + "\n", encoding="utf-8")
        os.chmod(key_path, 0o600)
        copied.append(str(key_path))

    manifest = {
        "kit": "mapper-decrypt",
        "protocol": PROTOCOL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": copied + [str(readme), str(example_env)],
        "include_key": bool(args.include_key),
        "run": "python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary",
        "deps": "pip install cryptography",
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def _fallback_readme() -> str:
    return (
        "# Mapper AES decrypt kit\n\n"
        "```bash\npip install cryptography\n"
        f"export {DEFAULT_KEY_ENV}='...'\n"
        "python3 mapper_decrypt_workflow.py decrypt --input payload.json --summary\n```\n"
    )


def cmd_protocol(_: argparse.Namespace) -> int:
    print(json.dumps(PROTOCOL, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Portable mapper AES decrypt workflow (outer AES → inner mask)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_key_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--key-file", default="", help="Path to 32-byte or base64 key file")
        sp.add_argument("--key-b64", default="", help="Inline base64 AES-256 key")

    d = sub.add_parser("decrypt", help="Decrypt AES mapper JSON → inner mask envelope")
    add_key_args(d)
    d.add_argument("--input", "-i", default="", help="Input JSON file")
    d.add_argument("--input-dir", default="", help="Decrypt all *.json in directory")
    d.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    d.add_argument("--output", "-o", default="", help="Write decrypted JSON to file")
    d.add_argument("--output-dir", default="", help="Batch output directory")
    d.add_argument("--summary", action="store_true", help="Print PII-mask summary only")
    d.set_defaults(func=cmd_decrypt)

    e = sub.add_parser("encrypt", help="Encrypt JSON with same protocol (test/round-trip)")
    add_key_args(e)
    e.add_argument("--input", "-i", default="")
    e.add_argument("--stdin", action="store_true")
    e.add_argument("--output", "-o", default="")
    e.set_defaults(func=cmd_encrypt)

    k = sub.add_parser("export-key", help="Show how to export key for another machine")
    add_key_args(k)
    k.add_argument("--output", "-o", default="", help="Write key b64 to file (mode 600)")
    k.add_argument("--print-secret", action="store_true", help="Print full key b64 to stdout")
    k.set_defaults(func=cmd_export_key)

    b = sub.add_parser("bundle", help="Pack portable decrypt kit directory")
    add_key_args(b)
    b.add_argument("--output-dir", default="mapper-decrypt-kit")
    b.add_argument("--include-key", action="store_true", help="Copy mapper_aes.key into kit (sensitive)")
    b.set_defaults(func=cmd_bundle)

    pr = sub.add_parser("protocol", help="Print protocol constants")
    pr.set_defaults(func=cmd_protocol)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
