#!/usr/bin/env python3
"""Parse TikTok Seller Center URL and decode embedded state for V2 mapping."""

import argparse
import base64
import json
import sys
import urllib.parse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Decode TikTok Seller Center URL state and export V2 mapping JSON."
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Full TikTok seller-vn URL containing state query parameter.",
    )
    parser.add_argument(
        "--strict-host",
        action="store_true",
        help="Fail unless host is seller-vn.tiktok.com.",
    )
    return parser.parse_args()


def decode_state(raw_state):
    if not raw_state:
        return None, "missing_state"
    try:
        value = urllib.parse.unquote(raw_state)
        padding = "=" * ((4 - len(value) % 4) % 4)
        decoded = base64.b64decode((value + padding).encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "state_not_object"
    except Exception as exc:
        return None, f"state_decode_error: {exc}"


def main():
    args = parse_args()
    parsed_url = urllib.parse.urlparse(args.url)
    host = parsed_url.netloc.lower()
    if args.strict_host and host != "seller-vn.tiktok.com":
        print(f"Unexpected host for seller URL: {host}", file=sys.stderr)
        return 2

    query = urllib.parse.parse_qs(parsed_url.query)
    state_raw = (query.get("state") or [""])[0]
    state_obj, state_error = decode_state(state_raw)

    result = {
        "source_url": args.url,
        "host": host,
        "path": parsed_url.path,
        "is_seller_center_url": host.endswith("tiktok.com") and "/services/" in parsed_url.path,
        "state_present": bool(state_raw),
        "state_valid": state_error is None,
        "state_error": state_error,
        "state_decoded": state_obj if state_error is None else None,
        "v2_mapping": None,
    }

    if state_obj:
        result["v2_mapping"] = {
            "platform": "tiktokshop",
            "shop_id": state_obj.get("shop_id"),
            "warehouse_id": state_obj.get("warehouse_id"),
            "sync": {
                "quantity": bool(state_obj.get("is_sync_quantity", False)),
                "price": bool(state_obj.get("is_sync_price", False)),
                "to_pos": bool(state_obj.get("is_sync_to_pos", False)),
            },
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if state_error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
