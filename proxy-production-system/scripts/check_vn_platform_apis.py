#!/usr/bin/env python3
"""Check connectivity and auth-gate behavior for VN ecommerce platform APIs."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


CHECKS = [
    {
        "platform": "Pancake POS",
        "method": "GET",
        "url": "https://pos.pages.fm/api/v1/shops",
        "expected_http": [200],
        "expected_substring": "Missing access_token",
        "notes": "Requires access_token for real API calls.",
    },
    {
        "platform": "GHTK",
        "method": "GET",
        "url": "https://services.giaohangtietkiem.vn/services/authenticated",
        "expected_http": [401],
        "expected_substring": "token",
        "notes": "Requires Token and X-Client-Source headers.",
    },
    {
        "platform": "Nhanh.vn POS v3",
        "method": "POST",
        "url": "https://pos.open.nhanh.vn/v3.0/product/list",
        "payload": "{}",
        "content_type": "application/json",
        "expected_http": [200],
        "expected_substring": "ERR_INVALID_APP_ID",
        "notes": "Requires appId, businessId, Authorization token.",
    },
    {
        "platform": "Sapo OAuth Docs",
        "method": "GET",
        "url": "https://support.sapo.vn/oauth",
        "expected_http": [200, 403],
        "expected_substring": "",
        "notes": "Docs endpoint; 403 can occur due to edge firewall by source IP.",
    },
    {
        "platform": "Haravan Commerce API",
        "method": "GET",
        "url": "https://apis.haravan.com/com/shop.json",
        "expected_http": [401],
        "expected_substring": "",
        "notes": "Requires Authorization: Bearer <token>.",
    },
]


def perform_check(item, timeout):
    headers = {}
    data = None
    if item.get("content_type"):
        headers["Content-Type"] = item["content_type"]
    if item.get("payload") is not None:
        data = item["payload"].encode("utf-8")

    req = urllib.request.Request(item["url"], method=item["method"], data=data, headers=headers)
    body = ""
    status = None
    error = None

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        error = f"{type(exc).__name__}: {exc}"

    expected_http = item["expected_http"]
    expected_substring = item.get("expected_substring", "")
    http_ok = status in expected_http if status is not None else False
    body_ok = expected_substring.lower() in body.lower() if expected_substring else True
    passed = error is None and http_ok and body_ok

    return {
        "platform": item["platform"],
        "method": item["method"],
        "url": item["url"],
        "status_code": status,
        "expected_http": expected_http,
        "expected_substring": expected_substring,
        "passed": passed,
        "error": error,
        "notes": item["notes"],
    }


def main():
    parser = argparse.ArgumentParser(description="Check VN ecommerce platform API availability.")
    parser.add_argument("--timeout", type=float, default=12.0, help="Request timeout in seconds.")
    parser.add_argument("--output", default="", help="Optional JSON output file.")
    args = parser.parse_args()

    results = [perform_check(item, args.timeout) for item in CHECKS]
    failed = [r for r in results if not r["passed"]]
    payload = {
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failed:
        print(
            "API check failed for one or more platforms. "
            "See 'results[].error' and expected fields for actionable fixes.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
