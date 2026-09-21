#!/usr/bin/env python3
"""Sanitize user profile JSON by removing/masking sensitive fields."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


REDACT_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
    "client_secret",
    "identificationCardNumber",
}

DROP_KEYS = {
    "metadata",
    "socialMedia",
    "guid",
    "uuid",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Sanitize JSON profile payload for safe sharing/import.")
    parser.add_argument("--input-file", default="", help="Path to input JSON file. If empty, read stdin.")
    parser.add_argument("--output-file", default="", help="Path to output sanitized JSON.")
    parser.add_argument("--allow-trailing-fragment", action="store_true", help="Try best-effort parse for truncated JSON.")
    return parser.parse_args()


def mask_email(value):
    if not isinstance(value, str) or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        local_masked = "*" * len(local)
    else:
        local_masked = local[:2] + "***"
    return f"{local_masked}@{domain}"


def mask_phone(value):
    if not isinstance(value, str):
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def hash_value(value):
    if not isinstance(value, str):
        return value
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def sanitize_obj(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in DROP_KEYS:
                continue
            lower_key = key.lower()
            if key in REDACT_KEYS or lower_key in REDACT_KEYS:
                out[key] = "[REDACTED]"
                continue
            if lower_key in {"email", "originalemail"}:
                out[key] = mask_email(value)
                continue
            if lower_key in {"mobilenumber", "contactnumber", "phone", "phonenumber"}:
                out[key] = mask_phone(value)
                continue
            if lower_key in {"ipaddress", "clientuseragent"}:
                out[key] = hash_value(value)
                continue
            out[key] = sanitize_obj(value)
        return out
    if isinstance(obj, list):
        return [sanitize_obj(item) for item in obj]
    return obj


def try_parse(text, allow_fragment=False):
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        if not allow_fragment:
            return None, f"invalid_json: {exc}"
        trimmed = text.rstrip()

        # 1) Keep only content before last comma to drop partial trailing key/value.
        if "," in trimmed:
            candidate = trimmed[: trimmed.rfind(",")]
        else:
            candidate = trimmed

        # 2) Close open braces/brackets based on simple balance.
        open_curly = candidate.count("{")
        close_curly = candidate.count("}")
        open_square = candidate.count("[")
        close_square = candidate.count("]")
        if close_square < open_square:
            candidate += "]" * (open_square - close_square)
        if close_curly < open_curly:
            candidate += "}" * (open_curly - close_curly)

        # 3) Fallback: if still invalid, try cutting to last closing token.
        attempts = [candidate]
        last_idx = max(trimmed.rfind("}"), trimmed.rfind("]"))
        if last_idx != -1:
            attempts.append(trimmed[: last_idx + 1])

        for item in attempts:
            try:
                return json.loads(item), "parsed_with_fragment_recovery"
            except json.JSONDecodeError:
                continue
        return None, f"invalid_json_unrecoverable: {exc}"


def main():
    args = parse_args()

    if args.input_file:
        raw = Path(args.input_file).read_text(encoding="utf-8", errors="ignore")
    else:
        raw = sys.stdin.read()

    obj, note = try_parse(raw, allow_fragment=args.allow_trailing_fragment)
    if obj is None:
        print(note, file=sys.stderr)
        return 2

    sanitized = sanitize_obj(obj)
    result = {
        "sanitization_note": note,
        "sanitized_payload": sanitized,
    }
    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_file:
        Path(args.output_file).write_text(output_text, encoding="utf-8")
        print(f"Sanitized JSON written to {args.output_file}")
    else:
        print(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
