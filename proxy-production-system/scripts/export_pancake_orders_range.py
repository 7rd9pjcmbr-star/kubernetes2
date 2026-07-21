#!/usr/bin/env python3
"""Export Pancake POS orders for the last N days to Excel (+ optional Telegram)."""

from __future__ import annotations

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
except ImportError:  # pragma: no cover
    Workbook = None

from pancake_pos_client import (
    auth_ready,
    fetch_shop_orders,
    missing_auth_names,
    resolve_credentials,
)


DEFAULT_TZ = "Asia/Ho_Chi_Minh"
DEFAULT_OUT = "/tmp/pancake_reports"


def load_extra_env():
    for path in (
        Path("/home/ubuntu/.config/scantool/asunmee.env"),
        Path(__file__).resolve().parent / ".env.vn-platforms",
    ):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def parse_args():
    load_extra_env()
    parser = argparse.ArgumentParser(description="Export last N days of Pancake orders.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--shop-id", default=os.getenv("PANCAKE_POS_SHOP_IDS", "714934229").split(",")[0].strip())
    parser.add_argument("--base-url", default=os.getenv("PANCAKE_POS_BASE_URL", "https://pos.pages.fm/api/v1"))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--timezone", default=os.getenv("REPORT_TIMEZONE", DEFAULT_TZ))
    parser.add_argument("--output-dir", default=os.getenv("REPORT_OUTPUT_DIR", DEFAULT_OUT))
    parser.add_argument("--telegram-bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    parser.add_argument("--telegram-chat-id", default=os.getenv("TELEGRAM_CHAT_ID", "").strip())
    parser.add_argument("--no-telegram", action="store_true")
    return parser.parse_args()


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


def customer_fields(order: dict) -> tuple[str, str]:
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    name = (
        order.get("recipient_name")
        or order.get("customer_name")
        or order.get("bill_full_name")
        or customer.get("name")
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
    return str(name or ""), str(phone or "")


def fetch_range(creds, shop_id, base_url, cutoff, page_size, max_pages, tz):
    collected = []
    stop = False
    for page in range(1, max_pages + 1):
        rows = fetch_shop_orders(
            creds,
            shop_id,
            base_url,
            params={"limit": page_size, "page_number": page, "page": page},
        )
        if not rows:
            break
        for order in rows:
            inserted = parse_dt(order.get("inserted_at") or order.get("created_at"), tz)
            if inserted is None:
                collected.append(order)
                continue
            if inserted < cutoff:
                stop = True
                continue
            collected.append(order)
        if stop:
            break
    return collected


def build_excel(orders, output_dir: Path, now_tz: datetime, days: int, shop_id: str) -> Path:
    if Workbook is None:
        raise RuntimeError("openpyxl required: pip install openpyxl")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"asunmee-orders-last{days}d-{now_tz.strftime('%Y%m%d-%H%M%S')}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = f"last_{days}d"
    ws.append(
        [
            "shop_id",
            "order_id",
            "inserted_at",
            "updated_at",
            "status_name",
            "total_price",
            "customer_name",
            "customer_phone",
        ]
    )
    for order in orders:
        name, phone = customer_fields(order)
        ws.append(
            [
                shop_id,
                order.get("id", ""),
                order.get("inserted_at") or order.get("created_at") or "",
                order.get("updated_at", ""),
                order.get("status_name") or order.get("status") or "",
                order.get("total_price") or order.get("total") or 0,
                name,
                phone,
            ]
        )
    wb.save(path)
    return path


def send_telegram(bot_token, chat_id, file_path: Path, caption: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with file_path.open("rb") as handle:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (file_path.name, handle)},
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"telegram failed: {payload}")


def main():
    args = parse_args()
    creds = resolve_credentials()
    if not auth_ready(creds):
        print("Missing Pancake key: " + ", ".join(missing_auth_names(creds)), file=sys.stderr)
        return 2

    tz = ZoneInfo(args.timezone)
    now = datetime.now(tz)
    cutoff = now - timedelta(days=max(1, args.days))
    orders = fetch_range(
        creds,
        args.shop_id,
        args.base_url,
        cutoff,
        max(1, args.page_size),
        max(1, args.max_pages),
        tz,
    )
    orders.sort(key=lambda o: str(o.get("inserted_at") or ""), reverse=True)
    excel = build_excel(orders, Path(args.output_dir), now, args.days, args.shop_id)

    summary = {
        "shop_id": args.shop_id,
        "shop_name": os.getenv("PANCAKE_SHOP_NAME", "ASUNMEE"),
        "days": args.days,
        "cutoff": cutoff.isoformat(),
        "order_count": len(orders),
        "excel": str(excel),
        "base_url": args.base_url,
    }
    meta = Path(args.output_dir) / f"asunmee-last{args.days}d-summary.json"
    meta.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.no_telegram and args.telegram_bot_token and args.telegram_chat_id:
        caption = (
            f"ASUNMEE orders last {args.days} days\n"
            f"Shop: {args.shop_id}\n"
            f"Count: {len(orders)}\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        send_telegram(args.telegram_bot_token, args.telegram_chat_id, excel, caption)
        print(json.dumps({"telegram_sent": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
