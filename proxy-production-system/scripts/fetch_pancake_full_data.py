#!/usr/bin/env python3
"""Fetch full Pancake order payloads via get_orders (unmask source).

Ported from uploaded fetch_pancake_full_data script, without BM DB deps.

Endpoint:
  POST https://pos.pancake.vn/api/v1/shops/{shop_id}/orders/get_orders

Auth (first match wins):
  PANCAKE_POS_API_KEY / PANCAKE_API_TOKEN / PANCAKE_POS_ACCESS_TOKEN / ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


DEFAULT_SHOP_ID = "714934229"  # ASUNMEE
DEFAULT_BASE = "https://pos.pages.fm/api/v1"
DEFAULT_OUT = "/tmp/pancake_full_orders"
ASUNMEE_ENV = Path("/home/ubuntu/.config/scantool/asunmee.env")


def load_extra_env() -> None:
    """Load durable local env files without hardcoding tokens in source."""
    candidates = [
        ASUNMEE_ENV,
        Path(__file__).resolve().parent / ".env.vn-platforms",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def resolve_token(cli_token: str = "") -> str:
    load_extra_env()
    return (
        cli_token
        or os.getenv("PANCAKE_POS_API_KEY", "")
        or os.getenv("PANCAKE_API_KEY", "")
        or os.getenv("CENTRAL_API_KEY", "")
        or os.getenv("PANCAKE_API_TOKEN", "")
        or os.getenv("PANCAKE_POS_ACCESS_TOKEN", "")
        or os.getenv("PANCAKE_POS_TOKEN", "")
        or os.getenv("PANCAKE_TOKEN", "")
    ).strip()


def parse_args():
    load_extra_env()
    parser = argparse.ArgumentParser(description="Fetch full Pancake orders via get_orders.")
    parser.add_argument("--shop-id", default=os.getenv("PANCAKE_POS_SHOP_IDS", DEFAULT_SHOP_ID).split(",")[0].strip())
    parser.add_argument("--token", default="", help="API token / access_token / api_key")
    parser.add_argument("--base-url", default=os.getenv("PANCAKE_POS_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output-dir", default=DEFAULT_OUT)
    parser.add_argument(
        "--auth-mode",
        choices=["auto", "access_token", "api_key", "bearer"],
        default="api_key",
        help="How to send the credential. ASUNMEE Open API key uses api_key.",
    )
    return parser.parse_args()


def extract_customer(order: dict) -> dict:
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    name = (
        order.get("recipient_name")
        or order.get("customer_name")
        or order.get("bill_full_name")
        or customer.get("name")
        or customer.get("full_name")
        or ""
    )
    phone = (
        order.get("recipient_phone")
        or order.get("customer_phone")
        or order.get("bill_phone_number")
        or customer.get("phone_number")
        or ""
    )
    if not phone and isinstance(customer.get("phone_numbers"), list):
        phone = ", ".join(str(x) for x in customer["phone_numbers"] if x)
    return {"customer_name": str(name or ""), "customer_phone": str(phone or "")}


def summarize(orders: list[dict]) -> dict:
    named = phoned = masked = 0
    for order in orders:
        cust = extract_customer(order)
        if cust["customer_name"]:
            named += 1
        if cust["customer_phone"]:
            phoned += 1
        if "*" in cust["customer_name"] or "*" in cust["customer_phone"]:
            masked += 1
    return {
        "count": len(orders),
        "with_name": named,
        "with_phone": phoned,
        "masked_fields": masked,
    }


def call_get_orders(base_url: str, shop_id: str, token: str, limit: int, offset: int, auth_mode: str):
    url = f"{base_url.rstrip('/')}/shops/{shop_id}/orders/get_orders"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    params = {}
    mode = auth_mode
    if mode == "auto":
        # 32-hex Open API keys work with api_key; JWTs use access_token/bearer.
        mode = "api_key" if len(token) == 32 else "access_token"

    if mode == "access_token":
        params["access_token"] = token
    elif mode == "api_key":
        params["api_key"] = token
    elif mode == "bearer":
        headers["Authorization"] = f"Bearer {token}"
        params["access_token"] = token

    payload = {
        "limit": limit,
        "offset": offset,
        "sort_type": "desc",
        "sort_field": "updated_at",
    }
    response = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:500]}
    return response.status_code, body


def main():
    args = parse_args()
    token = resolve_token(args.token)
    if not token:
        print(
            "Missing token. Set PANCAKE_POS_API_KEY / PANCAKE_API_TOKEN / PANCAKE_POS_ACCESS_TOKEN.",
            file=sys.stderr,
        )
        return 2

    status, body = call_get_orders(
        args.base_url,
        args.shop_id,
        token,
        max(1, args.limit),
        max(0, args.offset),
        args.auth_mode,
    )
    orders = body.get("data") if isinstance(body, dict) else None
    if not isinstance(orders, list):
        orders = []

    # Fallback: classic list endpoint (ASUNMEE Open API key works here).
    if (not orders) and (status >= 400 or body.get("success") is False):
        list_url = f"{args.base_url.rstrip('/')}/shops/{args.shop_id}/orders"
        params = {"limit": max(1, args.limit), "page_number": 1, "api_key": token}
        headers = {"Accept": "application/json"}
        resp = requests.get(list_url, params=params, headers=headers, timeout=30)
        status = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}
        orders = body.get("data") if isinstance(body, dict) else []
        if not isinstance(orders, list):
            orders = []

    result = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "shop_id": args.shop_id,
        "base_url": args.base_url,
        "http_status": status,
        "success": body.get("success") if isinstance(body, dict) else None,
        "error_code": body.get("error_code") if isinstance(body, dict) else None,
        "message": body.get("message") if isinstance(body, dict) else None,
        "summary": summarize(orders),
        "orders": [
            {
                "order_id": o.get("id"),
                "display_id": o.get("display_id") or o.get("order_number") or o.get("code"),
                "inserted_at": o.get("inserted_at") or o.get("created_at"),
                "updated_at": o.get("updated_at"),
                "status_name": o.get("status_name") or o.get("status"),
                "total_price": o.get("total_price") or o.get("total"),
                **extract_customer(o),
            }
            for o in orders
        ],
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = out_dir / f"shop_{args.shop_id}_full_{stamp}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Print without dumping every customer row by default.
    public = dict(result)
    public["orders_preview"] = public.pop("orders")[:3]
    public["output_file"] = str(out_file)
    print(json.dumps(public, ensure_ascii=False, indent=2))

    if status >= 400 or result.get("success") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
