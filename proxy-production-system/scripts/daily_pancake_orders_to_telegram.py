#!/usr/bin/env python3
"""Export last-24h Pancake orders to Excel and send once per day to Telegram."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - runtime dependency
    Workbook = None

from pancake_pos_client import (
    auth_ready,
    fetch_shop_orders,
    fetch_shops,
    missing_auth_names,
    resolve_credentials,
)


DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_STATE_FILE = "/tmp/pancake_daily_telegram_state.json"
DEFAULT_OUTPUT_DIR = "/tmp"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 20


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send one daily Telegram Excel report for Pancake orders from last 24h."
    )
    parser.add_argument("--api-key", default=os.getenv("PANCAKE_POS_API_KEY", "").strip())
    parser.add_argument(
        "--access-token",
        default=(
            os.getenv("PANCAKE_POS_ACCESS_TOKEN", "").strip()
            or os.getenv("PANCAKE_POS_TOKEN", "").strip()
            or os.getenv("PANCAKE_TOKEN", "").strip()
        ),
        help="Bearer token (pancake_token / pancake_pos_token).",
    )
    parser.add_argument("--telegram-bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    parser.add_argument("--telegram-chat-id", default=os.getenv("TELEGRAM_CHAT_ID", "").strip())
    parser.add_argument("--timezone", default=os.getenv("REPORT_TIMEZONE", DEFAULT_TIMEZONE))
    parser.add_argument("--state-file", default=os.getenv("REPORT_STATE_FILE", DEFAULT_STATE_FILE))
    parser.add_argument("--output-dir", default=os.getenv("REPORT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--force", action="store_true", help="Send even if already sent today.")
    return parser.parse_args()


def require_inputs(args, creds):
    missing = []
    if not auth_ready(creds):
        missing.extend(missing_auth_names(creds))
    if not args.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN / --telegram-bot-token")
    if not args.telegram_chat_id:
        missing.append("TELEGRAM_CHAT_ID / --telegram-chat-id")
    if Workbook is None:
        missing.append("python package openpyxl (install: pip install openpyxl)")

    if missing:
        raise ValueError("Missing required inputs: " + ", ".join(missing))


def load_state(path):
    state_path = Path(path)
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path, state):
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_dt(value, tz):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def fetch_recent_orders_for_shop(creds, shop_id, base_url, now_tz, page_size, max_pages):
    cutoff = now_tz - timedelta(days=1)
    collected = []

    for page in range(1, max_pages + 1):
        orders = fetch_shop_orders(
            creds,
            shop_id,
            base_url,
            params={"limit": page_size, "page_number": page},
        )
        if not orders:
            break

        stop_scan = False
        for order in orders:
            inserted_at = parse_dt(order.get("inserted_at"), now_tz.tzinfo)
            if inserted_at is None:
                continue
            if inserted_at < cutoff:
                stop_scan = True
                continue
            collected.append(order)

        if stop_scan:
            break

    return collected


def _extract_customer_phone(customer):
    if not isinstance(customer, dict):
        return ""
    if customer.get("phone_number"):
        return str(customer.get("phone_number"))
    phone_numbers = customer.get("phone_numbers")
    if isinstance(phone_numbers, list) and phone_numbers:
        return ", ".join(str(item) for item in phone_numbers if item)
    return ""


def build_excel_file(orders, output_dir, now_tz):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"pancake-orders-{now_tz.strftime('%Y%m%d')}.xlsx"
    file_path = output_path / filename

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "orders_last_24h"
    worksheet.append(
        [
            "shop_id",
            "shop_name",
            "order_id",
            "inserted_at",
            "updated_at",
            "status_name",
            "total_price",
            "customer_name",
            "customer_phone",
            "customer_id",
        ]
    )

    for row in orders:
        customer = row.get("customer") or {}
        worksheet.append(
            [
                row.get("shop_id", ""),
                row.get("shop_name", ""),
                row.get("id", ""),
                row.get("inserted_at", ""),
                row.get("updated_at", ""),
                row.get("status_name", ""),
                row.get("total_price", 0),
                customer.get("name", ""),
                _extract_customer_phone(customer),
                customer.get("customer_id", ""),
            ]
        )
    workbook.save(file_path)
    return file_path


def send_to_telegram(bot_token, chat_id, file_path, now_tz, order_count, base_url):
    caption = (
        f"Bao cao don hang 24h gan nhat\n"
        f"Thoi gian: {now_tz.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"So don: {order_count}\n"
        f"API: {base_url}"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, "rb") as file_handle:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (file_path.name, file_handle)},
            timeout=60,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"telegram send failed: {payload}")


def main():
    args = parse_args()
    creds = resolve_credentials(api_key=args.api_key, access_token=args.access_token)
    try:
        require_inputs(args, creds)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        tz = ZoneInfo(args.timezone)
    except Exception:
        print(f"Invalid timezone: {args.timezone}", file=sys.stderr)
        return 2

    now_tz = datetime.now(tz)
    today_key = now_tz.strftime("%Y-%m-%d")
    state = load_state(args.state_file)
    last_sent = state.get("last_sent_date")
    if last_sent == today_key and not args.force:
        print(f"Skip sending: report already sent for {today_key}. Use --force to override.")
        return 0

    shops, base_url = fetch_shops(creds)
    all_orders = []
    for shop in shops:
        shop_id = shop.get("id")
        if not shop_id:
            continue
        shop_orders = fetch_recent_orders_for_shop(
            creds, shop_id, base_url, now_tz, args.page_size, args.max_pages
        )
        for order in shop_orders:
            order["shop_name"] = shop.get("name", "")
            order["shop_id"] = shop_id
        all_orders.extend(shop_orders)

    all_orders.sort(key=lambda item: item.get("inserted_at", ""), reverse=True)
    file_path = build_excel_file(all_orders, args.output_dir, now_tz)
    send_to_telegram(
        args.telegram_bot_token,
        args.telegram_chat_id,
        file_path,
        now_tz,
        len(all_orders),
        base_url,
    )

    state.update(
        {
            "last_sent_date": today_key,
            "last_sent_at": now_tz.isoformat(),
            "last_file": str(file_path),
            "last_order_count": len(all_orders),
            "last_base_url": base_url,
            "auth_mode": "api_key" if creds.get("api_key") else "bearer",
        }
    )
    save_state(args.state_file, state)

    print(
        f"Report sent successfully. date={today_key} orders={len(all_orders)} file={file_path} "
        f"base_url={base_url} state={args.state_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
