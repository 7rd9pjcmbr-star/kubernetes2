#!/usr/bin/env python3
"""Fetch ASUNMEE orders and attempt PII unmask.

Pancake Open API keys return masked name/phone by design.
Full unmask needs a logged-in POS session cookie (or page access_token).

Usage:
  # API key only (orders OK, PII usually masked)
  python3 fetch_unmasked_orders.py --days 1

  # Session cookie from logged-in pos.pancake.vn tab:
  PANCAKE_POS_COOKIE='token=...; ...' python3 fetch_unmasked_orders.py --days 1
"""

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


ASUNMEE_ENV = Path("/home/ubuntu/.config/scantool/asunmee.env")
DEFAULT_SHOP = "714934229"
DEFAULT_BASE = "https://pos.pages.fm/api/v1"


def load_extra_env() -> None:
    for path in (ASUNMEE_ENV, Path(__file__).resolve().parent / ".env.vn-platforms"):
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
    p = argparse.ArgumentParser(description="Fetch orders and measure/unmask PII fields.")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--shop-id", default=os.getenv("PANCAKE_POS_SHOP_IDS", DEFAULT_SHOP).split(",")[0].strip())
    p.add_argument("--base-url", default=os.getenv("PANCAKE_POS_BASE_URL", DEFAULT_BASE))
    p.add_argument("--api-key", default=os.getenv("PANCAKE_POS_API_KEY", "").strip())
    p.add_argument(
        "--cookie",
        default=os.getenv("PANCAKE_POS_COOKIE", "").strip(),
        help="Cookie header from logged-in pos.pancake.vn session.",
    )
    p.add_argument("--max-pages", type=int, default=500)
    p.add_argument("--output-dir", default="/tmp/pancake_reports")
    p.add_argument("--telegram", action="store_true")
    return p.parse_args()


def parse_dt(value, tz):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def extract_pii(order: dict) -> dict:
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    ship = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else {}
    name = order.get("bill_full_name") or ship.get("full_name") or customer.get("name") or ""
    phone = order.get("bill_phone_number") or ship.get("phone_number") or ""
    address = ship.get("full_address") or ship.get("address") or ""
    masked = any("*" in str(x) for x in (name, phone, address))
    return {
        "customer_name": str(name or ""),
        "customer_phone": str(phone or ""),
        "address": str(address or ""),
        "is_masked": masked,
    }


def request_orders_page(base_url, shop_id, page, api_key="", cookie=""):
    url = f"{base_url.rstrip('/')}/shops/{shop_id}/orders"
    headers = {"Accept": "application/json"}
    params = {"limit": 100, "page_number": page, "page": page}
    if cookie:
        headers["Cookie"] = cookie
        headers["Origin"] = "https://pos.pancake.vn"
        headers["Referer"] = f"https://pos.pancake.vn/shop/{shop_id}/order"
        # Many POS session calls also accept token cookie as Bearer-ish access.
    if api_key:
        params["api_key"] = api_key
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is False:
        raise RuntimeError(payload.get("message") or "orders request failed")
    return payload.get("data") or []


def fetch_range(args, cutoff, tz):
    collected = []
    for page in range(1, max(1, args.max_pages) + 1):
        rows = request_orders_page(args.base_url, args.shop_id, page, args.api_key, args.cookie)
        if not rows:
            break
        stop = False
        for order in rows:
            inserted = parse_dt(order.get("inserted_at"), tz)
            if inserted is not None and inserted < cutoff:
                stop = True
                continue
            collected.append(order)
        if stop:
            break
    return collected


def write_excel(rows, path: Path):
    if Workbook is None:
        raise RuntimeError("openpyxl required")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "orders"
    ws.append(
        [
            "shop_id",
            "order_id",
            "inserted_at",
            "status_name",
            "total_price",
            "customer_name",
            "customer_phone",
            "address",
            "source",
            "is_masked",
        ]
    )
    for row in rows:
        ws.append(
            [
                row["shop_id"],
                row["order_id"],
                row["inserted_at"],
                row["status_name"],
                row["total_price"],
                row["customer_name"],
                row["customer_phone"],
                row["address"],
                row["source"],
                int(row["is_masked"]),
            ]
        )
    wb.save(path)


def main():
    args = parse_args()
    if not args.api_key and not args.cookie:
        print("Need PANCAKE_POS_API_KEY and/or PANCAKE_POS_COOKIE", file=sys.stderr)
        return 2

    tz = ZoneInfo(os.getenv("REPORT_TIMEZONE", "Asia/Ho_Chi_Minh"))
    now = datetime.now(tz)
    cutoff = now - timedelta(days=max(1, args.days))
    orders = fetch_range(args, cutoff, tz)

    rows = []
    masked = 0
    for order in orders:
        pii = extract_pii(order)
        if pii["is_masked"]:
            masked += 1
        rows.append(
            {
                "shop_id": args.shop_id,
                "order_id": order.get("id"),
                "inserted_at": order.get("inserted_at"),
                "status_name": order.get("status_name"),
                "total_price": order.get("total_price") or order.get("total") or 0,
                "source": order.get("order_sources_name") or "",
                **pii,
            }
        )

    out_dir = Path(args.output_dir)
    excel = out_dir / f"asunmee-unmask-attempt-last{args.days}d-{now.strftime('%Y%m%d-%H%M%S')}.xlsx"
    write_excel(rows, excel)

    summary = {
        "shop_id": args.shop_id,
        "shop_name": os.getenv("PANCAKE_SHOP_NAME", "ASUNMEE"),
        "days": args.days,
        "order_count": len(rows),
        "masked_count": masked,
        "unmasked_count": len(rows) - masked,
        "auth_mode": "cookie+api_key" if args.cookie and args.api_key else ("cookie" if args.cookie else "api_key"),
        "excel": str(excel),
        "note": (
            "Open API key keeps PII masked. "
            "Paste POS session Cookie into PANCAKE_POS_COOKIE or use pancake_orders_unmask_hook.js on logged-in tab."
            if not args.cookie
            else "Fetched with session cookie; check masked_count."
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.telegram:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if token and chat:
            caption = (
                f"ASUNMEE giai che attempt\n"
                f"Don: {len(rows)} | mask: {masked} | clear: {len(rows)-masked}\n"
                f"Auth: {summary['auth_mode']}\n"
                f"{summary['note']}"
            )
            with excel.open("rb") as handle:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat, "caption": caption},
                    files={"document": (excel.name, handle)},
                    timeout=120,
                )
            print(json.dumps({"telegram_ok": response.json().get("ok")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
