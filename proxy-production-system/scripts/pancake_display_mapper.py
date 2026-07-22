#!/usr/bin/env python3
"""
Pancake display mapping & unmask flow (3 layers).

1) UI      — user-facing values (order code, icon, virtual account)
2) Mapper  — order code → shop_id, icon → Fa*, account → bank endpoint
3) Endpoint — source of truth:
     primary:  https://pancake.vn/api/v1/pages/{shop_id}
     fallback: https://pos.pages.fm/api/v1/shops/{shop_id}  (Open API key)

ASUNMEE defaults: shop_id=714934229
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests


DEFAULT_PAGE_BASE = "https://pancake.vn/api/v1/pages"
DEFAULT_SHOP_BASE = "https://pos.pages.fm/api/v1"
DEFAULT_MAP_FILE = "/tmp/pancake_display_map.json"
DEFAULT_SHOP_ID = os.getenv("PANCAKE_POS_SHOP_IDS", "714934229").split(",")[0].strip() or "714934229"
ASUNMEE_ENV = Path("/home/ubuntu/.config/scantool/asunmee.env")

ICON_MAP = {
    "cart": "FaShoppingCart",
    "giỏ hàng": "FaShoppingCart",
    "gio hang": "FaShoppingCart",
    "🛒": "FaShoppingCart",
    "shopping_cart": "FaShoppingCart",
    "user": "FaUser",
    "phone": "FaPhone",
    "bank": "FaUniversity",
    "qr": "FaQrcode",
}

BANK_ENDPOINT_MAP = {
    "VCB": "https://api.vietcombank.com.vn/inquiry/{account}",
    "TCB": "https://api.techcombank.com.vn/inquiry/{account}",
    "MB": "https://api.mbbank.com.vn/inquiry/{account}",
    "ACB": "https://api.acb.com.vn/inquiry/{account}",
    "VPB": "https://api.vpbank.com.vn/inquiry/{account}",
    "DEFAULT": "https://bank.local/inquiry/{account}",
}


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


@dataclass
class UiView:
    """Layer 1 — values shown to the user (may be masked / friendly)."""

    order_code: str = ""
    icon: str = ""
    account_display: str = ""
    customer_name_masked: str = ""
    customer_phone_masked: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class MappedView:
    """Layer 2 — resolved internal references."""

    shop_id: str | int | None = None
    icon_real: str = ""
    bank_endpoint: str = ""
    page_endpoint: str = ""
    shop_endpoint: str = ""
    order_code: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class EndpointRecord:
    """Layer 3 — raw / true payload fields from API."""

    shop_id: str = ""
    source_url: str = ""
    success: bool | None = None
    error_code: Any = None
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class DisplayMapper:
    """Maps UI display values to shop IDs and real endpoints."""

    def __init__(self, map_file: str | Path | None = None, shop_id: str = ""):
        self.shop_id = (shop_id or DEFAULT_SHOP_ID).strip()
        self.order_code_to_shop: dict[str, str] = {}
        if map_file:
            self.load(map_file)

    def load(self, path: str | Path):
        p = Path(path)
        if not p.exists():
            return
        payload = json.loads(p.read_text(encoding="utf-8"))
        self.shop_id = str(payload.get("shop_id") or payload.get("page_id") or self.shop_id)
        rows = payload.get("orders") or payload.get("order_code_to_shop") or {}
        if isinstance(rows, dict):
            for code, shop in rows.items():
                self.register_order(str(code), shop)
        elif isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                code = row.get("order_code") or row.get("display_id")
                shop = row.get("shop_id") or row.get("internal_order_id") or row.get("id")
                if code is not None and shop is not None:
                    self.register_order(str(code), shop)

    def save(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "shop_id": self.shop_id,
            "shop_name": os.getenv("PANCAKE_SHOP_NAME", "ASUNMEE"),
            "orders": [
                {"order_code": code, "shop_id": shop}
                for code, shop in sorted(self.order_code_to_shop.items())
            ],
            "endpoints": {
                "pages": f"{DEFAULT_PAGE_BASE}/{{shop_id}}",
                "shops": f"{DEFAULT_SHOP_BASE}/shops/{{shop_id}}",
            },
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def register_order(self, order_code: str, shop_id: str | int):
        code = str(order_code).strip()
        if not code:
            return
        self.order_code_to_shop[code] = str(shop_id).strip()

    def map_icon(self, icon_display: str) -> str:
        key = (icon_display or "").strip()
        if key in ICON_MAP:
            return ICON_MAP[key]
        lower = key.lower()
        if lower in ICON_MAP:
            return ICON_MAP[lower]
        slug = re.sub(r"[^a-z0-9_]+", "", lower.replace(" ", "_"))
        return ICON_MAP.get(slug, icon_display or "")

    def map_bank_endpoint(self, account_display: str) -> str:
        text = (account_display or "").strip()
        if not text:
            return ""
        prefix = "DEFAULT"
        for bank in BANK_ENDPOINT_MAP:
            if bank == "DEFAULT":
                continue
            if text.upper().startswith(bank) or f"/{bank}/" in text.upper():
                prefix = bank
                break
        return BANK_ENDPOINT_MAP[prefix].format(account=text)

    def map_ui(self, ui: UiView) -> MappedView:
        notes: list[str] = []
        shop = self.order_code_to_shop.get(ui.order_code)
        if shop is None:
            shop = self.shop_id
            if ui.order_code:
                notes.append("order_code_uses_default_shop")
        mapped = MappedView(
            shop_id=shop,
            icon_real=self.map_icon(ui.icon),
            bank_endpoint=self.map_bank_endpoint(ui.account_display),
            page_endpoint=f"{DEFAULT_PAGE_BASE}/{shop}",
            shop_endpoint=f"{DEFAULT_SHOP_BASE}/shops/{shop}",
            order_code=ui.order_code,
            notes=notes,
        )
        return mapped


def fetch_page_endpoint(shop_id: str, access_token: str = "", timeout: int = 20) -> EndpointRecord:
    """Layer 3a — pages API (often needs page access_token)."""
    token = (
        access_token
        or os.getenv("PANCAKE_PAGE_ACCESS_TOKEN", "")
        or os.getenv("PANCAKE_POS_ACCESS_TOKEN", "")
    ).strip()
    url = f"{DEFAULT_PAGE_BASE.rstrip('/')}/{shop_id}"
    params = {"access_token": token} if token else {}
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:500]}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    return EndpointRecord(
        shop_id=str(shop_id),
        source_url=url,
        success=payload.get("success"),
        error_code=payload.get("error_code"),
        message=str(payload.get("message") or ""),
        data=payload,
    )


def fetch_shop_endpoint(shop_id: str, api_key: str = "", timeout: int = 20) -> EndpointRecord:
    """Layer 3b — POS shop endpoint (ASUNMEE Open API key works here)."""
    key = (
        api_key
        or os.getenv("PANCAKE_POS_API_KEY", "")
        or os.getenv("PANCAKE_API_KEY", "")
        or os.getenv("CENTRAL_API_KEY", "")
    ).strip()
    url = f"{DEFAULT_SHOP_BASE.rstrip('/')}/shops/{shop_id}"
    response = requests.get(url, params={"api_key": key}, headers={"Accept": "application/json"}, timeout=timeout)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:500]}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    return EndpointRecord(
        shop_id=str(shop_id),
        source_url=url,
        success=payload.get("success"),
        error_code=payload.get("error_code"),
        message=str(payload.get("message") or ""),
        data=payload,
    )


def unmask_bundle(ui: UiView, mapper: DisplayMapper, endpoint: EndpointRecord | None = None) -> dict[str, Any]:
    mapped = mapper.map_ui(ui)
    shop = endpoint.data.get("shop") if endpoint and isinstance(endpoint.data, dict) else None
    return {
        "ui": asdict(ui),
        "mapper": asdict(mapped),
        "endpoint": asdict(endpoint) if endpoint else None,
        "resolved": {
            "order_code": ui.order_code,
            "shop_id": mapped.shop_id,
            "shop_name": (shop or {}).get("name") if isinstance(shop, dict) else os.getenv("PANCAKE_SHOP_NAME", ""),
            "icon_real": mapped.icon_real,
            "bank_endpoint": mapped.bank_endpoint,
            "page_endpoint": mapped.page_endpoint,
            "shop_endpoint": mapped.shop_endpoint,
            "endpoint_ok": bool(endpoint and endpoint.success is True),
            "endpoint_message": endpoint.message if endpoint else "",
            "true_fields": {
                "id": (shop or {}).get("id") if isinstance(shop, dict) else None,
                "avatar_url": (shop or {}).get("avatar_url") if isinstance(shop, dict) else None,
                "currency": (shop or {}).get("currency") if isinstance(shop, dict) else None,
                "pages": (shop or {}).get("pages") if isinstance(shop, dict) else None,
            }
            if endpoint and endpoint.success
            else {},
        },
    }


def parse_args():
    load_extra_env()
    parser = argparse.ArgumentParser(description="Map UI display values and fetch shop/page endpoint.")
    parser.add_argument("--order-code", default="DH-2026-001")
    parser.add_argument("--icon", default="cart")
    parser.add_argument("--account-display", default="VCB-QR-VIRTUAL-001")
    parser.add_argument("--shop-id", default=os.getenv("PANCAKE_POS_SHOP_IDS", DEFAULT_SHOP_ID).split(",")[0].strip())
    parser.add_argument("--map-file", default=DEFAULT_MAP_FILE)
    parser.add_argument(
        "--register",
        default="",
        help="Register mapping order_code:shop_id (example: DH-2026-001:714934229)",
    )
    parser.add_argument("--fetch-endpoint", action="store_true", help="Call pages + shops endpoints.")
    parser.add_argument("--access-token", default="", help="Optional page access_token.")
    parser.add_argument("--demo", action="store_true", help="Seed demo DH-2026-001 → ASUNMEE shop.")
    return parser.parse_args()


def main():
    args = parse_args()
    load_extra_env()
    mapper = DisplayMapper(map_file=args.map_file, shop_id=args.shop_id)

    if args.demo:
        mapper.register_order("DH-2026-001", args.shop_id)
        mapper.shop_id = args.shop_id
        mapper.save(args.map_file)

    if args.register:
        if ":" not in args.register:
            print("Invalid --register, expected order_code:shop_id", file=sys.stderr)
            return 2
        code, shop = args.register.split(":", 1)
        mapper.register_order(code.strip(), shop.strip())
        mapper.save(args.map_file)

    ui = UiView(
        order_code=args.order_code,
        icon=args.icon,
        account_display=args.account_display,
        customer_name_masked="N*****n",
        customer_phone_masked="09****1234",
    )

    endpoint = None
    if args.fetch_endpoint:
        page = fetch_page_endpoint(args.shop_id, access_token=args.access_token)
        if page.success is True:
            endpoint = page
        else:
            # Open API key path used by ASUNMEE
            endpoint = fetch_shop_endpoint(args.shop_id)
            if endpoint.success is not True:
                print(
                    f"Endpoint gated/failed: pages={page.message}; shops={endpoint.message}",
                    file=sys.stderr,
                )

    result = unmask_bundle(ui, mapper, endpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.fetch_endpoint and endpoint and endpoint.success is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
