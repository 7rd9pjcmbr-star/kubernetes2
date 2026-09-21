#!/usr/bin/env python3
"""Sapo.vn OAuth login automation: authorize URL, callback verify, access token exchange."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Dict, List, Optional, Tuple


DEFAULT_SCOPES = "read_orders,read_products,read_customers,read_content,write_orders"
ENV_CLIENT_ID = "SAPO_CLIENT_ID"
ENV_CLIENT_SECRET = "SAPO_CLIENT_SECRET"
ENV_SHOP = "SAPO_SHOP_DOMAIN"
ENV_REDIRECT = "SAPO_REDIRECT_URI"
ENV_SCOPES = "SAPO_SCOPES"
ENV_ACCESS_TOKEN = "SAPO_ACCESS_TOKEN"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sapo.vn OAuth: build install URL, verify callback, exchange access token.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth-url", help="Print (and optionally open) OAuth authorize URL.")
    auth.add_argument("--open-browser", action="store_true", help="Open authorize URL in default browser.")
    _add_common_oauth_flags(auth)

    complete = sub.add_parser(
        "complete",
        help="Parse OAuth callback URL, verify HMAC, exchange code for access token.",
    )
    complete.add_argument(
        "--callback-url",
        required=True,
        help="Redirect URL containing code (and hmac/signature, timestamp, store).",
    )
    complete.add_argument(
        "--skip-hmac",
        action="store_true",
        help="Skip HMAC check (only for local debugging).",
    )
    complete.add_argument(
        "--exchange",
        action="store_true",
        help="POST to /admin/oauth/access_token (default: only print curl).",
    )
    complete.add_argument(
        "--verify-shop",
        action="store_true",
        help="After exchange, call GET /admin/shop.json with the new token.",
    )
    complete.add_argument(
        "--write-env",
        metavar="PATH",
        default="",
        help="Append SAPO_SHOP_DOMAIN and SAPO_ACCESS_TOKEN to a dotenv file.",
    )
    _add_common_oauth_flags(complete)

    verify = sub.add_parser("verify-token", help="Smoke-test an existing SAPO_ACCESS_TOKEN.")
    verify.add_argument("--shop", default="", help="Shop host or slug (default: env SAPO_SHOP_DOMAIN).")
    verify.add_argument("--token", default="", help="Access token (default: env SAPO_ACCESS_TOKEN).")

    return parser.parse_args()


def _add_common_oauth_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--shop", default="", help=f"Shop slug or host (env {ENV_SHOP}).")
    parser.add_argument("--client-id", default="", help=f"App API key (env {ENV_CLIENT_ID}).")
    parser.add_argument("--client-secret", default="", help=f"App secret (env {ENV_CLIENT_SECRET}).")
    parser.add_argument(
        "--redirect-uri",
        default="",
        help=f"Registered redirect URI (env {ENV_REDIRECT}).",
    )
    parser.add_argument(
        "--scopes",
        default="",
        help=f"Comma-separated scopes (env {ENV_SCOPES}, default: {DEFAULT_SCOPES}).",
    )


def env_or(key: str, cli_value: str, required: bool = False) -> str:
    value = (cli_value or os.getenv(key, "")).strip()
    if required and not value:
        raise SystemExit(f"Missing {key}: pass flag or set environment variable.")
    return value


def normalize_shop_host(raw: str) -> str:
    raw = raw.strip().lower()
    if not raw:
        raise SystemExit("Shop is required (e.g. ten-cua-hang or ten-cua-hang.mysapo.net).")
    raw = raw.replace("https://", "").replace("http://", "").split("/")[0]
    if raw.endswith(".mysapo.net"):
        return raw
    if "." in raw:
        return raw
    return f"{raw}.mysapo.net"


def shop_admin_base(host: str) -> str:
    return f"https://{host}/admin"


def build_authorize_url(
    shop_host: str,
    client_id: str,
    redirect_uri: str,
    scopes: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "scope": scopes,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{shop_admin_base(shop_host)}/oauth/authorize?{query}"


def parse_query(url: str) -> Dict[str, str]:
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.query:
        raise SystemExit("Callback URL has no query string.")
    pairs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1] for key, values in pairs.items()}


def _sorted_message(params: Dict[str, str]) -> str:
    items = sorted((key, value) for key, value in params.items())
    return "&".join(f"{key}={value}" for key, value in items)


def compute_hmac_base64(secret: str, message: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def compute_hmac_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_callback(params: Dict[str, str], secret: str) -> Tuple[bool, str, Dict[str, str]]:
    """Validate Sapo callback per support.sapo.vn/oauth (HMAC-SHA256, base64)."""
    if "hmac" in params:
        provided = params["hmac"]
        unsigned = {k: v for k, v in params.items() if k not in {"hmac", "signature"}}
        expected = compute_hmac_base64(secret, _sorted_message(unsigned))
        if hmac.compare_digest(expected, provided):
            return True, "hmac_base64", unsigned
        return False, f"hmac mismatch: expected {expected}, got {provided}", unsigned

    if "signature" in params:
        provided = params["signature"].lower()
        unsigned = {k: v for k, v in params.items() if k not in {"hmac", "signature"}}
        expected_hex = compute_hmac_hex(secret, _sorted_message(unsigned))
        if hmac.compare_digest(expected_hex, provided):
            return True, "signature_hex", unsigned
        expected_b64 = compute_hmac_base64(secret, _sorted_message(unsigned))
        if hmac.compare_digest(expected_b64, provided):
            return True, "signature_base64", unsigned
        return False, f"signature mismatch: expected hex {expected_hex}, got {provided}", unsigned

    return False, "callback missing hmac or signature parameter", params


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "..." + value[-keep:]


def http_post_json(url: str, payload: dict, timeout: float) -> Tuple[int, str, Optional[str]]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    return _http_request(req, timeout)


def http_post_form(url: str, payload: dict, timeout: float) -> Tuple[int, str, Optional[str]]:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return _http_request(req, timeout)


def http_get(url: str, headers: dict, timeout: float) -> Tuple[int, str, Optional[str]]:
    req = urllib.request.Request(url, method="GET", headers=headers)
    return _http_request(req, timeout)


def _http_request(req: urllib.request.Request, timeout: float) -> Tuple[int, str, Optional[str]]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="ignore"), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="ignore"), None
    except Exception as exc:  # pragma: no cover - network dependent
        return 0, "", f"{type(exc).__name__}: {exc}"


def exchange_access_token(
    shop_host: str,
    client_id: str,
    client_secret: str,
    code: str,
    timeout: float,
) -> Tuple[Optional[str], dict]:
    url = f"{shop_admin_base(shop_host)}/oauth/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }

    status, body, err = http_post_json(url, payload, timeout)
    meta = {"url": url, "status": status, "body_preview": body[:500], "transport_error": err}
    if err or status >= 400:
        status2, body2, err2 = http_post_form(url, payload, timeout)
        meta["fallback_form"] = {"status": status2, "body_preview": body2[:500], "transport_error": err2}
        if not err2 and status2 < 400:
            body = body2
            status = status2
        else:
            return None, meta

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        meta["parse_error"] = "response is not JSON"
        return None, meta

    token = parsed.get("access_token") if isinstance(parsed, dict) else None
    meta["response_keys"] = list(parsed.keys()) if isinstance(parsed, dict) else []
    if not token:
        meta["parse_error"] = "access_token missing in response"
        return None, meta
    return str(token), meta


def verify_shop_token(shop_host: str, token: str, timeout: float) -> Tuple[bool, dict]:
    url = f"https://{shop_host}/admin/shop.json"
    status, body, err = http_get(url, {"X-Sapo-Access-Token": token}, timeout)
    info = {"url": url, "status": status, "transport_error": err}
    if err or status >= 400:
        info["ok"] = False
        info["body_preview"] = body[:400]
        return False, info
    try:
        shop = json.loads(body)
    except json.JSONDecodeError:
        info["ok"] = False
        info["parse_error"] = "invalid JSON"
        return False, info
    info["ok"] = True
    if isinstance(shop, dict) and "shop" in shop and isinstance(shop["shop"], dict):
        info["shop_name"] = shop["shop"].get("name")
        info["shop_domain"] = shop["shop"].get("domain")
    return True, info


def append_env_file(path: str, shop_host: str, token: str) -> None:
    lines: List[str] = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    updates = {
        ENV_SHOP: shop_host,
        ENV_ACCESS_TOKEN: token,
    }
    seen = set()
    out: List[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out).rstrip() + "\n")


def load_oauth_config(args: argparse.Namespace) -> Tuple[str, str, str, str, str]:
    shop = normalize_shop_host(env_or(ENV_SHOP, args.shop, required=True))
    client_id = env_or(ENV_CLIENT_ID, args.client_id, required=True)
    client_secret = env_or(ENV_CLIENT_SECRET, args.client_secret, required=True)
    redirect_uri = env_or(ENV_REDIRECT, args.redirect_uri, required=True)
    scopes = env_or(ENV_SCOPES, args.scopes) or DEFAULT_SCOPES
    return shop, client_id, client_secret, redirect_uri, scopes


def cmd_auth_url(args: argparse.Namespace) -> int:
    shop, client_id, _secret, redirect_uri, scopes = load_oauth_config(args)
    url = build_authorize_url(shop, client_id, redirect_uri, scopes)
    print(url)
    if args.open_browser:
        webbrowser.open(url)
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    shop, client_id, client_secret, redirect_uri, scopes = load_oauth_config(args)
    params = parse_query(args.callback_url)

    callback_shop = params.get("store", "").strip()
    if callback_shop:
        shop = normalize_shop_host(callback_shop)

    code = params.get("code", "").strip()
    if not code:
        print("Callback URL missing code parameter.", file=sys.stderr)
        return 2

    hmac_ok = True
    hmac_detail = "skipped"
    if not args.skip_hmac:
        hmac_ok, hmac_detail, _unsigned = verify_callback(params, client_secret)
        if not hmac_ok:
            print(f"HMAC verification failed: {hmac_detail}", file=sys.stderr)
            return 1

    report = {
        "shop_host": shop,
        "redirect_uri": redirect_uri,
        "scopes_requested": scopes,
        "code_present": True,
        "code_preview": mask_secret(code, keep=3),
        "hmac_valid": hmac_ok,
        "hmac_detail": hmac_detail,
        "timestamp": params.get("timestamp"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    token_url = f"{shop_admin_base(shop)}/oauth/access_token"
    curl_cmd = (
        f"curl -sS -X POST '{token_url}' -H 'Content-Type: application/json' "
        f"-d '{json.dumps({'client_id': client_id, 'client_secret': '<SECRET>', 'code': code}, ensure_ascii=False)}'"
    )
    print("\nToken exchange (replace <SECRET>):")
    print(curl_cmd)

    if not args.exchange:
        return 0

    token, meta = exchange_access_token(shop, client_id, client_secret, code, timeout=30.0)
    print("\nExchange result:")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if not token:
        return 1

    print("\nAccess token (store securely):")
    print(token)

    if args.verify_shop:
        ok, shop_info = verify_shop_token(shop, token, timeout=30.0)
        print("\nShop verification:")
        print(json.dumps(shop_info, ensure_ascii=False, indent=2))
        if not ok:
            return 1

    if args.write_env:
        append_env_file(args.write_env, shop, token)
        print(f"\nWrote {ENV_SHOP} and {ENV_ACCESS_TOKEN} to {args.write_env}")

    return 0


def cmd_verify_token(args: argparse.Namespace) -> int:
    shop = normalize_shop_host(env_or(ENV_SHOP, args.shop, required=True))
    token = env_or(ENV_ACCESS_TOKEN, args.token, required=True)
    ok, info = verify_shop_token(shop, token, timeout=30.0)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main() -> int:
    args = parse_args()
    if args.command == "auth-url":
        return cmd_auth_url(args)
    if args.command == "complete":
        return cmd_complete(args)
    if args.command == "verify-token":
        return cmd_verify_token(args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
