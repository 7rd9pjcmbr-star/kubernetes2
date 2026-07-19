#!/usr/bin/env python3
"""Monitor newest Pancake POS orders across shops."""

import argparse
import os
import sys
import time
from datetime import datetime

import requests


def call_api(base_url, creds, endpoint, params=None, timeout=10):
    url = f"{base_url.rstrip('/')}{endpoint}"
    query = dict(params or {})
    headers = {"Accept": "application/json"}
    if creds.get("api_key"):
        query["api_key"] = creds["api_key"]
    elif creds.get("access_token"):
        headers["Authorization"] = f"Bearer {creds['access_token']}"
    else:
        return {"_error": "missing_credential"}
    try:
        response = requests.get(url, params=query, headers=headers, timeout=timeout)
        if response.ok:
            return response.json()
        return {"_error": f"http_{response.status_code}", "_body": response.text[:200]}
    except requests.RequestException as exc:
        return {"_error": f"request_exception: {exc}"}


def monitor_orders(base_url, creds, poll_seconds, order_limit):
    print("Starting Pancake POS order monitor (Ctrl+C to stop).")
    last_order_ids = {}

    while True:
        shops_data = call_api(base_url, creds, "/shops")
        if not shops_data or "shops" not in shops_data:
            err = shops_data.get("_error") if isinstance(shops_data, dict) else "invalid_response"
            print(f"[{datetime.now().isoformat(timespec='seconds')}] failed to load shops: {err}")
            time.sleep(poll_seconds)
            continue

        for shop in shops_data["shops"]:
            shop_id = shop.get("id")
            shop_name = shop.get("name", f"shop-{shop_id}")
            if not shop_id:
                continue

            orders_data = call_api(
                base_url,
                creds,
                f"/shops/{shop_id}/orders",
                params={"limit": order_limit},
            )
            if not orders_data or "data" not in orders_data:
                continue

            orders = orders_data["data"]
            if not orders:
                continue

            latest_order = orders[0]
            order_id = latest_order.get("id")
            if order_id is None:
                continue

            if shop_id not in last_order_ids:
                last_order_ids[shop_id] = order_id
                customer_name = latest_order.get("customer", {}).get("name", "Khach le")
                amount = latest_order.get("total_price", 0)
                status = latest_order.get("status_name", "unknown")
                print(
                    f"[INIT] {shop_name} | customer={customer_name} | "
                    f"amount={amount:,.0f} VND | status={status}"
                )
            elif last_order_ids[shop_id] != order_id:
                last_order_ids[shop_id] = order_id
                customer_name = latest_order.get("customer", {}).get("name", "Khach le")
                amount = latest_order.get("total_price", 0)
                status = latest_order.get("status_name", "unknown")
                now = datetime.now().strftime("%H:%M:%S")
                print(
                    f"[NEW {now}] {shop_name} | customer={customer_name} | "
                    f"amount={amount:,.0f} VND | status={status}"
                )

        time.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description="Monitor Pancake POS orders in realtime.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PANCAKE_POS_BASE_URL", "https://pos.pages.fm/api/v1"),
        help="Pancake POS API base URL.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Pancake POS API key. If omitted, reads PANCAKE_POS_API_KEY.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="Polling interval in seconds.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of recent orders fetched per shop.",
    )
    args = parser.parse_args()

    from pancake_pos_client import resolve_credentials, auth_ready

    creds = resolve_credentials(api_key=args.api_key or "")
    if not auth_ready(creds):
        print(
            "Missing Pancake credential. Provide --api-key / PANCAKE_POS_API_KEY "
            "or PANCAKE_POS_ACCESS_TOKEN / PANCAKE_POS_TOKEN (Bearer).",
            file=sys.stderr,
        )
        return 2

    try:
        monitor_orders(args.base_url, api_key, max(5, args.poll_seconds), max(1, args.limit))
    except KeyboardInterrupt:
        print("\nStopped order monitor.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
