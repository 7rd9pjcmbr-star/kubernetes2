#!/usr/bin/env python3
"""Platform-aware scanner runner using generated credential JSON files."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


DEFAULT_CREDENTIALS_DIR = "/home/ubuntu/scan-tool-integration/credentials"


def parse_args():
    parser = argparse.ArgumentParser(description="Run platform-aware scanner against generated credentials.")
    parser.add_argument("--credentials-dir", default=DEFAULT_CREDENTIALS_DIR)
    parser.add_argument("--max-files", type=int, default=200)
    return parser.parse_args()


def looks_like_pancake_api_key(value):
    return bool(re.fullmatch(r"[a-f0-9]{32}", (value or "").strip(), re.IGNORECASE))


def try_pancake_account(credential):
    username = credential.get("username", "")
    password = credential.get("password", "")
    candidates = [password, username]
    for candidate in candidates:
        if not looks_like_pancake_api_key(candidate):
            continue
        try:
            resp = requests.get(
                "https://pos.pages.fm/api/v1/shops",
                params={"api_key": candidate},
                timeout=12,
            )
            if resp.status_code == 200 and resp.json().get("success"):
                return True, "api_key_ok"
        except Exception:
            pass
    return False, "no_valid_api_key"


def try_cookie_bundle(credential):
    platform = credential.get("platform")
    cookie_header = credential.get("cookie_header", "")
    if not cookie_header:
        return False, "missing_cookie_header"

    headers = {"Cookie": cookie_header, "User-Agent": "Mozilla/5.0"}
    targets = {
        "tiktokshop": "https://seller-vn.tiktok.com/",
        "shopee": "https://seller.shopee.vn/",
        "ghn": "https://khachhang.giaohangtietkiem.vn/web",
    }
    target = targets.get(platform)
    if not target:
        return False, "unsupported_cookie_platform"
    try:
        resp = requests.get(target, headers=headers, timeout=12, allow_redirects=False)
        return (resp.status_code in (200, 302, 307)), f"http_{resp.status_code}"
    except Exception as exc:
        return False, f"request_error:{exc.__class__.__name__}"


def main():
    args = parse_args()
    cred_dir = Path(args.credentials_dir)
    files = sorted(cred_dir.glob("*.json"))[: args.max_files]
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "credentials_dir": str(cred_dir),
        "files_scanned": len(files),
        "success": 0,
        "failed": 0,
        "per_platform": {},
    }

    for path in files:
        try:
            credential = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        platform = credential.get("platform", "unknown")
        p = result["per_platform"].setdefault(platform, {"success": 0, "failed": 0, "reasons": {}})

        credential_type = credential.get("credential_type", "account_pair")
        if platform == "pancake" and credential_type == "account_pair":
            ok, reason = try_pancake_account(credential)
        elif credential_type == "cookie_bundle":
            ok, reason = try_cookie_bundle(credential)
        else:
            ok, reason = False, "unsupported_credential_type"

        if ok:
            result["success"] += 1
            p["success"] += 1
        else:
            result["failed"] += 1
            p["failed"] += 1
        p["reasons"][reason] = p["reasons"].get(reason, 0) + 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
