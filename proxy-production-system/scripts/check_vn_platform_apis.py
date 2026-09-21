#!/usr/bin/env python3
"""Check connectivity and authenticated smoke tests for VN ecommerce platform APIs."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
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
    {
        "platform": "TikTok Shop",
        "method": "GET",
        "url": "https://open-api.tiktokglobalshop.com/authorization/202309/shops",
        "expected_http": [400],
        "expected_substring": "Invalid credentials",
        "notes": "Endpoint reachable; requires app_key/sign/timestamp and x-tts-access-token.",
    },
    {
        "platform": "Shopee",
        "method": "GET",
        "url": "https://partner.shopeemobile.com/api/v2/shop/get_shop_info",
        "expected_http": [200],
        "expected_substring": "partner_id",
        "notes": "Endpoint reachable; requires partner_id/timestamp/sign/access_token/shop_id.",
    },
    {
        "platform": "GHN",
        "method": "GET",
        "url": "https://dev-online-gateway.ghn.vn/shiip/public-api/master-data/province",
        "expected_http": [401],
        "expected_substring": "Authorization header is required",
        "notes": "Endpoint reachable; requires Token (and usually ShopId for order APIs).",
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


def _decode_jwt_payload(token):
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # pragma: no cover - token shape varies
        return None
    return None


def _extract_pancake_token_candidates(raw_token):
    candidates = []
    if raw_token:
        candidates.append(("provided", raw_token))

    payload = _decode_jwt_payload(raw_token) if raw_token else None
    nested_access_token = payload.get("accessToken") if isinstance(payload, dict) else None
    if isinstance(nested_access_token, str) and nested_access_token and nested_access_token != raw_token:
        candidates.append(("nested_access_token", nested_access_token))

    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for source, token in candidates:
        if token in seen:
            continue
        unique.append((source, token))
        seen.add(token)
    return unique


def _parse_json_body(body):
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def perform_check(item, timeout):
    headers = {}
    if item.get("content_type"):
        headers["Content-Type"] = item["content_type"]
    status, body, error = _request(
        item["url"], item["method"], timeout, headers=headers, payload=item.get("payload")
    )

    expected_http = item["expected_http"]
    expected_substring = item.get("expected_substring", "")
    disallow_substrings = item.get("disallow_substrings", [])
    http_ok = status in expected_http if status is not None else False
    body_ok = expected_substring.lower() in body.lower() if expected_substring else True
    disallow_ok = all(token.lower() not in body.lower() for token in disallow_substrings)
    passed = error is None and http_ok and body_ok and disallow_ok

    return {
        "platform": item["platform"],
        "method": item["method"],
        "url": item["url"],
        "status_code": status,
        "expected_http": expected_http,
        "expected_substring": expected_substring,
        "disallow_substrings": disallow_substrings,
        "passed": passed,
        "error": error,
        "notes": item["notes"],
    }


def _tiktok_sign(path, query_params, app_secret):
    sorted_keys = sorted(query_params)
    flattened = "".join(f"{key}{query_params[key]}" for key in sorted_keys)
    message = f"{app_secret}{path}{flattened}{app_secret}".encode("utf-8")
    signature = hmac.new(app_secret.encode("utf-8"), message, hashlib.sha256).hexdigest().upper()
    return signature


def build_authenticated_checks():
    checks = []

    pancake_api_key = os.getenv("PANCAKE_POS_API_KEY", "").strip()
    pancake_token = os.getenv("PANCAKE_POS_ACCESS_TOKEN", "").strip()
    if pancake_api_key:
        checks.append(
            {
                "platform": "Pancake POS",
                "method": "GET",
                "url": "https://pos.pages.fm/api/v1/shops",
                "headers": {},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "query_params": {"api_key": pancake_api_key},
                "pancake_auth_mode": "api_key",
                "disallow_substrings": ["api_key is invalid", "access_token is invalid", "token is expired"],
                "notes": "Authenticated call with PANCAKE_POS_API_KEY.",
                "missing_env": [],
            }
        )
    elif pancake_token:
        pancake_candidates = _extract_pancake_token_candidates(pancake_token)
        checks.append(
            {
                "platform": "Pancake POS",
                "method": "GET",
                "url": "https://pos.pages.fm/api/v1/shops",
                "headers": {},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "token_candidates": pancake_candidates,
                "pancake_auth_mode": "access_token",
                "disallow_substrings": ["access_token is invalid", "token is expired"],
                "notes": (
                    "Authenticated call with PANCAKE_POS_ACCESS_TOKEN; "
                    "auto-retries nested accessToken when token is a wrapped JWT."
                ),
                "missing_env": [],
            }
        )
    else:
        checks.append(
            {
                "platform": "Pancake POS",
                "missing_env": ["PANCAKE_POS_API_KEY or PANCAKE_POS_ACCESS_TOKEN"],
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

    tiktok_app_key = os.getenv("TIKTOKSHOP_APP_KEY", "").strip()
    tiktok_app_secret = os.getenv("TIKTOKSHOP_APP_SECRET", "").strip()
    tiktok_access_token = os.getenv("TIKTOKSHOP_ACCESS_TOKEN", "").strip()
    if tiktok_app_key and tiktok_app_secret and tiktok_access_token:
        path = "/authorization/202309/shops"
        timestamp = int(time.time())
        params = {"app_key": tiktok_app_key, "timestamp": str(timestamp)}
        sign = _tiktok_sign(path, params, tiktok_app_secret)
        params["sign"] = sign
        tiktok_url = "https://open-api.tiktokglobalshop.com" + path + "?" + urllib.parse.urlencode(params)
        checks.append(
            {
                "platform": "TikTok Shop",
                "method": "GET",
                "url": tiktok_url,
                "headers": {"x-tts-access-token": tiktok_access_token, "Content-Type": "application/json"},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "disallow_substrings": ["Invalid credentials", "invalid sign"],
                "notes": "Authenticated call with app_key/app_secret/access_token signature.",
                "missing_env": [],
            }
        )
    else:
        missing = []
        if not tiktok_app_key:
            missing.append("TIKTOKSHOP_APP_KEY")
        if not tiktok_app_secret:
            missing.append("TIKTOKSHOP_APP_SECRET")
        if not tiktok_access_token:
            missing.append("TIKTOKSHOP_ACCESS_TOKEN")
        checks.append(
            {
                "platform": "TikTok Shop",
                "missing_env": missing,
                "notes": "Missing TikTok Shop credentials.",
            }
        )

    shopee_partner_id = os.getenv("SHOPEE_PARTNER_ID", "").strip()
    shopee_partner_key = os.getenv("SHOPEE_PARTNER_KEY", "").strip()
    shopee_shop_id = os.getenv("SHOPEE_SHOP_ID", "").strip()
    shopee_access_token = os.getenv("SHOPEE_ACCESS_TOKEN", "").strip()
    if shopee_partner_id and shopee_partner_key and shopee_shop_id and shopee_access_token:
        shopee_path = "/api/v2/shop/get_shop_info"
        timestamp = int(time.time())
        base = f"{shopee_partner_id}{shopee_path}{timestamp}{shopee_access_token}{shopee_shop_id}"
        sign = hmac.new(
            shopee_partner_key.encode("utf-8"), base.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        shopee_url = (
            "https://partner.shopeemobile.com"
            + shopee_path
            + "?"
            + urllib.parse.urlencode(
                {
                    "partner_id": shopee_partner_id,
                    "timestamp": str(timestamp),
                    "access_token": shopee_access_token,
                    "shop_id": shopee_shop_id,
                    "sign": sign,
                }
            )
        )
        checks.append(
            {
                "platform": "Shopee",
                "method": "GET",
                "url": shopee_url,
                "headers": {"Content-Type": "application/json"},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "disallow_substrings": ["error_auth", "error_sign", "error_param"],
                "notes": "Authenticated call with partner_id/partner_key/shop_id/access_token.",
                "missing_env": [],
            }
        )
    else:
        missing = []
        if not shopee_partner_id:
            missing.append("SHOPEE_PARTNER_ID")
        if not shopee_partner_key:
            missing.append("SHOPEE_PARTNER_KEY")
        if not shopee_shop_id:
            missing.append("SHOPEE_SHOP_ID")
        if not shopee_access_token:
            missing.append("SHOPEE_ACCESS_TOKEN")
        checks.append(
            {
                "platform": "Shopee",
                "missing_env": missing,
                "notes": "Missing Shopee credentials.",
            }
        )

    ghn_token = os.getenv("GHN_API_TOKEN", "").strip()
    ghn_shop_id = os.getenv("GHN_SHOP_ID", "").strip()
    if ghn_token and ghn_shop_id:
        checks.append(
            {
                "platform": "GHN",
                "method": "GET",
                "url": "https://dev-online-gateway.ghn.vn/shiip/public-api/master-data/province",
                "headers": {"Token": ghn_token, "ShopId": ghn_shop_id},
                "payload": None,
                "expected_http": [200],
                "expected_substring": "",
                "disallow_substrings": ["Authorization header is required", '"code":401'],
                "notes": "Authenticated call with GHN token and shop id.",
                "missing_env": [],
            }
        )
    else:
        missing = []
        if not ghn_token:
            missing.append("GHN_API_TOKEN")
        if not ghn_shop_id:
            missing.append("GHN_SHOP_ID")
        checks.append(
            {
                "platform": "GHN",
                "missing_env": missing,
                "notes": "Missing GHN credentials.",
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

    pancake_attempts = []
    if item["platform"] == "Pancake POS" and item.get("pancake_auth_mode") == "api_key":
        params = item.get("query_params", {})
        url = item["url"] + "?" + urllib.parse.urlencode(params)
        status, body, error = _request(
            url,
            item["method"],
            timeout,
            headers=item.get("headers", {}),
            payload=item.get("payload"),
        )
        response_json = _parse_json_body(body)
        pancake_attempts.append(
            {
                "token_source": "api_key",
                "status_code": status,
                "error_code": response_json.get("error_code") if response_json else None,
                "message": response_json.get("message") if response_json else body[:120],
            }
        )
        evaluated_url = item["url"]
    elif item["platform"] == "Pancake POS" and item.get("token_candidates"):
        status = None
        body = ""
        error = None
        for source, candidate_token in item["token_candidates"]:
            url = item["url"] + "?" + urllib.parse.urlencode({"access_token": candidate_token})
            status, body, error = _request(
                url,
                item["method"],
                timeout,
                headers=item.get("headers", {}),
                payload=item.get("payload"),
            )
            response_json = _parse_json_body(body)
            pancake_attempts.append(
                {
                    "token_source": source,
                    "status_code": status,
                    "error_code": response_json.get("error_code") if response_json else None,
                    "message": response_json.get("message") if response_json else body[:120],
                }
            )
            # Stop as soon as we get a successful response structure.
            if response_json and response_json.get("success") is True:
                break
        evaluated_url = item["url"]
    else:
        status, body, error = _request(
            item["url"],
            item["method"],
            timeout,
            headers=item.get("headers", {}),
            payload=item.get("payload"),
        )
        evaluated_url = item["url"]

    expected_http = item["expected_http"]
    expected_substring = item.get("expected_substring", "")
    disallow_substrings = item.get("disallow_substrings", [])
    http_ok = status in expected_http if status is not None else False
    body_ok = expected_substring.lower() in body.lower() if expected_substring else True
    disallow_ok = all(token.lower() not in body.lower() for token in disallow_substrings)
    response_json = _parse_json_body(body)
    pancake_success = (
        item["platform"] == "Pancake POS"
        and response_json is not None
        and response_json.get("success") is True
    )
    passed = error is None and ((http_ok and body_ok and disallow_ok) or pancake_success)

    diagnostics = {}
    if item["platform"] == "Pancake POS":
        diagnostics["attempts"] = pancake_attempts
        if response_json and response_json.get("success") is False:
            message = str(response_json.get("message", "")).lower()
            if "api_key is invalid" in message:
                diagnostics["classification"] = "invalid_api_key"
                diagnostics["hint"] = "Generate a valid API key in Pancake POS settings and retry."
            elif "expired" in message:
                diagnostics["classification"] = "expired_token"
                diagnostics["hint"] = "Refresh/reissue token and retry."
            else:
                diagnostics["classification"] = "invalid_or_wrong_token_type"
                diagnostics["hint"] = (
                    "Use POS Open API token/key. "
                    "If you pasted a login JWT, provide the inner accessToken claim."
                )

    return {
        "platform": item["platform"],
        "mode": "authenticated",
        "method": item["method"],
        "url": evaluated_url,
        "status_code": status,
        "expected_http": expected_http,
        "expected_substring": expected_substring,
        "disallow_substrings": disallow_substrings,
        "passed": passed,
        "skipped": False,
        "error": error,
        "notes": item["notes"],
        "diagnostics": diagnostics,
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
