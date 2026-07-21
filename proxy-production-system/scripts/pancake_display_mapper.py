#!/usr/bin/env python3
"""
Pancake display mapping & unmask flow (3 layers).

1) UI      — what the user sees (order code, icon name, virtual account)
2) Mapper  — maps display values ↔ internal IDs / real icons / bank endpoints
3) Endpoint — source of truth API (requires access_token)

Example endpoint:
  https://pancake.vn/api/v1/pages/{page_id}
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
DEFAULT_MAP_FILE = "/tmp/pancake_display_map.json"

# Display icon name → real icon component / asset key
ICON_MAP = {
    "cart": "FaShoppingCart",
    "giỏ hàng": "FaShoppingCart",
    "gio hang": "FaShoppingCart",
    "shopping_cart": "FaShoppingCart",
    "user": "FaUser",
    "phone": "FaPhone",
    "bank": "FaUniversity",
    "qr": "FaQrcode",
}

# Virtual / display account prefixes → bank inquiry endpoint templates
BANK_ENDPOINT_MAP = {
    "VCB": "https://api.vietcombank.com.vn/inquiry/{account}",
    "TCB": "https://api.techcombank.com.vn/inquiry/{account}",
    "MB": "https://api.mbbank.com.vn/inquiry/{account}",
    "ACB": "https://api.acb.com.vn/inquiry/{account}",
    "VPB": "https://api.vpbank.com.vn/inquiry/{account}",
    "DEFAULT": "https://bank.local/inquiry/{account}",
}


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

    internal_order_id: str | int | None = None
    icon_real: str = ""
    bank_endpoint: str = ""
    page_id: str = ""
    order_code: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class EndpointRecord:
    """Layer 3 — raw / true payload fields from API."""

    page_id: str = ""
    source_url: str = ""
    success: bool | None = None
    error_code: Any = None
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class DisplayMapper:
    """Maps UI display values to internal IDs and real endpoints."""

    def __init__(self, map_file: str | Path | None = None, page_id: str = ""):
        self.page_id = page_id.strip()
        self.order_code_to_id: dict[str, str | int] = {}
        self.id_to_order_code: dict[str, str] = {}
        if map_file:
            self.load(map_file)

    def load(self, path: str | Path):
        p = Path(path)
        if not p.exists():
            return
        payload = json.loads(p.read_text(encoding="utf-8"))
        self.page_id = str(payload.get("page_id") or self.page_id)
        orders = payload.get("orders") or payload.get("order_code_to_id") or {}
        if isinstance(orders, dict):
            for code, internal_id in orders.items():
                self.register_order(str(code), internal_id)
        elif isinstance(orders, list):
            for row in orders:
                if not isinstance(row, dict):
                    continue
                code = row.get("order_code") or row.get("display_id")
                internal = row.get("internal_order_id") or row.get("id")
                if code is not None and internal is not None:
                    self.register_order(str(code), internal)

    def save(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "page_id": self.page_id,
            "orders": [
                {"order_code": code, "internal_order_id": internal_id}
                for code, internal_id in sorted(self.order_code_to_id.items())
            ],
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def register_order(self, order_code: str, internal_id: str | int):
        code = str(order_code).strip()
        if not code:
            return
        self.order_code_to_id[code] = internal_id
        self.id_to_order_code[str(internal_id)] = code

    def map_icon(self, icon_display: str) -> str:
        key = (icon_display or "").strip().lower()
        if key in ICON_MAP:
            return ICON_MAP[key]
        # strip emoji / keep alphanumeric slug
        slug = re.sub(r"[^a-z0-9_]+", "", key.replace(" ", "_"))
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
        template = BANK_ENDPOINT_MAP[prefix]
        return template.format(account=text)

    def map_ui(self, ui: UiView) -> MappedView:
        notes: list[str] = []
        internal = self.order_code_to_id.get(ui.order_code)
        if internal is None and ui.order_code:
            # Accept already-internal numeric IDs pasted into UI field.
            if re.fullmatch(r"\d{6,}", ui.order_code.strip()):
                internal = ui.order_code.strip()
                notes.append("order_code_looks_internal_id")
            else:
                notes.append("order_code_unmapped")

        mapped = MappedView(
            internal_order_id=internal,
            icon_real=self.map_icon(ui.icon),
            bank_endpoint=self.map_bank_endpoint(ui.account_display),
            page_id=self.page_id,
            order_code=ui.order_code,
            notes=notes,
        )
        return mapped


def fetch_page_endpoint(
    page_id: str,
    access_token: str = "",
    base_url: str = DEFAULT_PAGE_BASE,
    timeout: int = 20,
) -> EndpointRecord:
    """Layer 3 — fetch true page payload (masked away from UI)."""
    page_id = page_id.strip()
    token = (access_token or os.getenv("PANCAKE_PAGE_ACCESS_TOKEN") or os.getenv("PANCAKE_POS_ACCESS_TOKEN") or "").strip()
    url = f"{base_url.rstrip('/')}/{page_id}"
    params = {}
    headers = {"Accept": "application/json"}
    if token:
        params["access_token"] = token
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:500]}

    if not isinstance(payload, dict):
        payload = {"data": payload}

    return EndpointRecord(
        page_id=page_id,
        source_url=url,
        success=payload.get("success"),
        error_code=payload.get("error_code"),
        message=str(payload.get("message") or ""),
        data=payload,
    )


def unmask_bundle(ui: UiView, mapper: DisplayMapper, endpoint: EndpointRecord | None = None) -> dict[str, Any]:
    """Combine all 3 layers into one resolution result."""
    mapped = mapper.map_ui(ui)
    return {
        "ui": asdict(ui),
        "mapper": asdict(mapped),
        "endpoint": asdict(endpoint) if endpoint else None,
        "resolved": {
            "order_code": ui.order_code,
            "internal_order_id": mapped.internal_order_id,
            "icon_real": mapped.icon_real,
            "bank_endpoint": mapped.bank_endpoint,
            "page_id": mapped.page_id or (endpoint.page_id if endpoint else ""),
            "endpoint_ok": bool(endpoint and endpoint.success is True),
            "endpoint_message": endpoint.message if endpoint else "",
        },
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Map UI display values and optionally fetch page endpoint.")
    parser.add_argument("--order-code", default="DH-2026-001")
    parser.add_argument("--icon", default="cart")
    parser.add_argument("--account-display", default="VCB-QR-VIRTUAL-001")
    parser.add_argument("--page-id", default=os.getenv("PANCAKE_PAGE_ID", "spo_90679120"))
    parser.add_argument("--map-file", default=DEFAULT_MAP_FILE)
    parser.add_argument(
        "--register",
        default="",
        help="Register mapping order_code:internal_id (example: DH-2026-001:430238387)",
    )
    parser.add_argument("--fetch-endpoint", action="store_true", help="Call page API (needs access_token).")
    parser.add_argument("--access-token", default="", help="Pancake page access_token.")
    parser.add_argument("--demo", action="store_true", help="Seed demo mapping DH-2026-001 → 430238387.")
    return parser.parse_args()


def main():
    args = parse_args()
    mapper = DisplayMapper(map_file=args.map_file, page_id=args.page_id)

    if args.demo:
        mapper.register_order("DH-2026-001", 430238387)
        mapper.page_id = args.page_id
        mapper.save(args.map_file)

    if args.register:
        if ":" not in args.register:
            print("Invalid --register, expected order_code:internal_id", file=sys.stderr)
            return 2
        code, internal = args.register.split(":", 1)
        mapper.register_order(code.strip(), internal.strip())
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
        endpoint = fetch_page_endpoint(args.page_id, access_token=args.access_token)
        if endpoint.success is not True:
            print(
                f"Endpoint gated/failed: error_code={endpoint.error_code} message={endpoint.message}",
                file=sys.stderr,
            )

    result = unmask_bundle(ui, mapper, endpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.fetch_endpoint and endpoint and endpoint.success is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
