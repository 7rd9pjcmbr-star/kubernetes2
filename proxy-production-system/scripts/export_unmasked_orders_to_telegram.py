#!/usr/bin/env python3
"""Send Excel from browser-exported pancake-orders-unmasked-*.json to Telegram."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover
    Workbook = None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert unmask-hook JSON export to Excel and send via Telegram."
    )
    parser.add_argument("--input-json", required=True, help="Path to exported JSON.")
    parser.add_argument("--telegram-bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    parser.add_argument("--telegram-chat-id", default=os.getenv("TELEGRAM_CHAT_ID", "").strip())
    parser.add_argument("--timezone", default=os.getenv("REPORT_TIMEZONE", "Asia/Ho_Chi_Minh"))
    parser.add_argument("--output-dir", default=os.getenv("REPORT_OUTPUT_DIR", "/tmp"))
    parser.add_argument("--dry-run", action="store_true", help="Build Excel only; do not send.")
    return parser.parse_args()


def load_orders(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        orders = payload.get("orders") or payload.get("data") or []
        if isinstance(orders, list):
            return orders
    raise ValueError("JSON must be a list or object with orders/data array.")


def build_excel(orders, output_dir: Path, now_tz: datetime) -> Path:
    if Workbook is None:
        raise RuntimeError("openpyxl is required (pip install openpyxl)")
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"pancake-unmasked-{now_tz.strftime('%Y%m%d-%H%M%S')}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "orders_unmasked"
    ws.append(
        [
            "shop_id",
            "order_id",
            "display_id",
            "inserted_at",
            "status_name",
            "total_price",
            "customer_name",
            "customer_phone",
            "customer_id",
            "captured_at",
        ]
    )
    for row in orders:
        ws.append(
            [
                row.get("shop_id", ""),
                row.get("order_id", ""),
                row.get("display_id", ""),
                row.get("inserted_at", ""),
                row.get("status_name", ""),
                row.get("total_price", ""),
                row.get("customer_name", ""),
                row.get("customer_phone", ""),
                row.get("customer_id", ""),
                row.get("captured_at", ""),
            ]
        )
    wb.save(file_path)
    return file_path


def send_document(bot_token, chat_id, file_path: Path, caption: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with file_path.open("rb") as handle:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (file_path.name, handle)},
            timeout=60,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"telegram send failed: {payload}")


def main():
    args = parse_args()
    path = Path(args.input_json)
    if not path.exists():
        print(f"Input not found: {path}", file=sys.stderr)
        return 2
    if not args.dry_run and (not args.telegram_bot_token or not args.telegram_chat_id):
        print("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID", file=sys.stderr)
        return 2

    orders = load_orders(path)
    now_tz = datetime.now(ZoneInfo(args.timezone))
    file_path = build_excel(orders, Path(args.output_dir), now_tz)
    caption = (
        f"Pancake unmasked export\n"
        f"Time: {now_tz.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"Orders: {len(orders)}\n"
        f"Source: browser tab hook"
    )
    print(f"excel={file_path} orders={len(orders)}")
    if args.dry_run:
        return 0
    send_document(args.telegram_bot_token, args.telegram_chat_id, file_path, caption)
    print("sent_to_telegram=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
