#!/usr/bin/env python3
"""Check connectivity and authenticated smoke tests for VN ecommerce platform APIs."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


PUBLIC_CHECKS = [
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


def _request(url, method, timeout, headers=None, payload=None):
    req_headers = headers or {}
    data = payload.encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers=req_headers)

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
    return status, body, error


def perform_check(item, timeout):
    headers = {}
    if item.get("content_type"):
        headers["Content-Type"] = item["content_type"]
    status, body, error = _request(
        item["url"], item["method"], timeout, headers=headers, payload=item.get("payload")
    )

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


def build_authenticated_checks():
    checks = []

    pancake_token = os.getenv("PANCAKE_POS_ACCESS_TOKEN", "").strip()
    if pancake_token:
        pancake_url = (
            "https://pos.pages.fm/api/v1/shops?"
            + urllib.parse.urlencode({"access_token": pancake_token})
        )
        checks.append(
            {
                "platform": "Pancake POS",
                "method": "GET",
                "url": pancake_url,
                "headers": {},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "notes": "Authenticated call with PANCAKE_POS_ACCESS_TOKEN.",
                "missing_env": [],
            }
        )
    else:
        checks.append(
            {
                "platform": "Pancake POS",
                "missing_env": ["PANCAKE_POS_ACCESS_TOKEN"],
                "notes": "Missing Pancake credential.",
            }
        )

    ghtk_token = os.getenv("GHTK_API_TOKEN", "").strip()
    ghtk_partner = os.getenv("GHTK_PARTNER_CODE", "").strip()
    if ghtk_token and ghtk_partner:
        checks.append(
            {
                "platform": "GHTK",
                "method": "GET",
                "url": "https://services.giaohangtietkiem.vn/services/authenticated",
                "headers": {"Token": ghtk_token, "X-Client-Source": ghtk_partner},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "notes": "Authenticated call with Token and X-Client-Source.",
                "missing_env": [],
            }
        )
    else:
        missing = []
        if not ghtk_token:
            missing.append("GHTK_API_TOKEN")
        if not ghtk_partner:
            missing.append("GHTK_PARTNER_CODE")
        checks.append({"platform": "GHTK", "missing_env": missing, "notes": "Missing GHTK credentials."})

    nhanh_app_id = os.getenv("NHANH_APP_ID", "").strip()
    nhanh_business_id = os.getenv("NHANH_BUSINESS_ID", "").strip()
    nhanh_token = os.getenv("NHANH_ACCESS_TOKEN", "").strip()
    if nhanh_app_id and nhanh_business_id and nhanh_token:
        nhanh_url = (
            "https://pos.open.nhanh.vn/v3.0/product/list?"
            + urllib.parse.urlencode({"appId": nhanh_app_id, "businessId": nhanh_business_id})
        )
        checks.append(
            {
                "platform": "Nhanh.vn POS v3",
                "method": "POST",
                "url": nhanh_url,
                "headers": {"Authorization": nhanh_token, "Content-Type": "application/json"},
                "payload": '{"paginator":{"size":1}}',
                "expected_http": [200],
                "expected_substring": "",
                "notes": "Authenticated call with appId/businessId/access token.",
                "missing_env": [],
            }
        )
    else:
        missing = []
        if not nhanh_app_id:
            missing.append("NHANH_APP_ID")
        if not nhanh_business_id:
            missing.append("NHANH_BUSINESS_ID")
        if not nhanh_token:
            missing.append("NHANH_ACCESS_TOKEN")
        checks.append(
            {
                "platform": "Nhanh.vn POS v3",
                "missing_env": missing,
                "notes": "Missing Nhanh credentials.",
            }
        )

    sapo_shop_domain = os.getenv("SAPO_SHOP_DOMAIN", "").strip()
    sapo_token = os.getenv("SAPO_ACCESS_TOKEN", "").strip()
    if sapo_shop_domain and sapo_token:
        checks.append(
            {
                "platform": "Sapo",
                "method": "GET",
                "url": f"https://{sapo_shop_domain}/admin/shop.json",
                "headers": {"X-Sapo-Access-Token": sapo_token},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "notes": "Authenticated call with shop domain and access token.",
                "missing_env": [],
            }
        )
    else:
        missing = []
        if not sapo_shop_domain:
            missing.append("SAPO_SHOP_DOMAIN")
        if not sapo_token:
            missing.append("SAPO_ACCESS_TOKEN")
        checks.append({"platform": "Sapo", "missing_env": missing, "notes": "Missing Sapo credentials."})

    haravan_token = os.getenv("HARAVAN_ACCESS_TOKEN", "").strip()
    if haravan_token:
        checks.append(
            {
                "platform": "Haravan",
                "method": "GET",
                "url": "https://apis.haravan.com/com/shop.json",
                "headers": {"Authorization": f"Bearer {haravan_token}"},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "notes": "Authenticated call with bearer token.",
                "missing_env": [],
            }
        )
    else:
        checks.append(
            {
                "platform": "Haravan",
                "missing_env": ["HARAVAN_ACCESS_TOKEN"],
                "notes": "Missing Haravan credential.",
            }
        )
    return checks


def perform_authenticated_check(item, timeout):
    if item.get("missing_env"):
        return {
            "platform": item["platform"],
            "mode": "authenticated",
            "skipped": True,
            "passed": False,
            "missing_env": item["missing_env"],
            "notes": item["notes"],
        }

    status, body, error = _request(
        item["url"],
        item["method"],
        timeout,
        headers=item.get("headers", {}),
        payload=item.get("payload"),
    )
    expected_http = item["expected_http"]
    expected_substring = item.get("expected_substring", "")
    http_ok = status in expected_http if status is not None else False
    body_ok = expected_substring.lower() in body.lower() if expected_substring else True
    passed = error is None and http_ok and body_ok

    return {
        "platform": item["platform"],
        "mode": "authenticated",
        "method": item["method"],
        "url": item["url"],
        "status_code": status,
        "expected_http": expected_http,
        "expected_substring": expected_substring,
        "passed": passed,
        "skipped": False,
        "error": error,
        "notes": item["notes"],
    }


def main():
    parser = argparse.ArgumentParser(description="Check VN ecommerce platform API availability.")
    parser.add_argument("--timeout", type=float, default=12.0, help="Request timeout in seconds.")
    parser.add_argument("--output", default="", help="Optional JSON output file.")
    parser.add_argument(
        "--authenticated",
        action="store_true",
        help="Also run authenticated smoke checks using environment variables.",
    )
    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="Fail if authenticated checks are skipped due to missing credentials.",
    )
    args = parser.parse_args()

    results = [perform_check(item, args.timeout) for item in PUBLIC_CHECKS]
    for result in results:
        result["mode"] = "public"
        result["skipped"] = False
    auth_results = []
    if args.authenticated:
        auth_checks = build_authenticated_checks()
        auth_results = [perform_authenticated_check(item, args.timeout) for item in auth_checks]
        results.extend(auth_results)

    failed = [r for r in results if (not r.get("skipped", False)) and (not r["passed"])]
    skipped = [r for r in results if r.get("skipped", False)]
    require_auth_failed = args.require_auth and any(r.get("skipped", False) for r in auth_results)
    payload = {
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "public_total": len(PUBLIC_CHECKS),
        "authenticated_total": len(auth_results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "skipped": len(skipped),
        "results": results,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failed or require_auth_failed:
        print(
            "API check failed for one or more platforms. "
            "See 'results[].error', 'missing_env', and expected fields for actionable fixes.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
