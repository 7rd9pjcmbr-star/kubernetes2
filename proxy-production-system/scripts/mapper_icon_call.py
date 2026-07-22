#!/usr/bin/env python3
"""Call backend by icon name via mapper; return masked/encoded response envelope.

Flow:
  icon name (cart / ShoppingCart / giỏ hàng / icon-setting)
    → IconMapper
    → ICON_BACKEND_MAP endpoint
    → POS API (direct; ignore exhausted HTTP_PROXY)
    → response envelope { encoding: "mask", payload: ... }

Examples:
  python3 mapper_icon_call.py --icon cart
  python3 mapper_icon_call.py --icon "đơn hàng" --deep
  python3 mapper_icon_call.py --icons cart,product,kho,user
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Ensure local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pancake_backend_deep_query import (  # noqa: E402
    ICON_BACKEND_MAP,
    deep_query,
    export_endpoint_map,
    load_extra_env,
)
from pancake_icon_mapper import DEFAULT_SHOP, IconMapper  # noqa: E402


MASK_RE = re.compile(r".*\*.*")


def clear_proxy_env() -> None:
    """DataImpulse is TRAFFIC_EXHAUSTED — always hit POS direct for mapper calls."""
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "PROXY_URL",
        "PANCAKE_HTTP_PROXY",
    ):
        os.environ.pop(key, None)


def is_masked_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return "*" in text


def encode_masked_field(value: Any) -> dict[str, Any]:
    """Wrap a field as mask-encoding metadata (no plaintext recovery)."""
    text = "" if value is None else str(value)
    masked = is_masked_value(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii") if text else ""
    return {
        "encoding": "mask" if masked else "plain",
        "display": text,
        "b64": b64,  # still masked chars if API masked — not a decrypt
        "sha256_16": digest,
        "masked": masked,
    }


PII_FIELD_KEYS = (
    "customer_name",
    "customer_phone",
    "name",
    "phone",
    "email",
    "address",
    "shipping",
)


def wrap_pii_row(row: dict[str, Any], domain: str = "orders") -> dict[str, Any]:
    """Encode PII-bearing preview rows for orders / customers / users."""
    if domain == "customers":
        return {
            "id": row.get("id"),
            "domain": "customers",
            "name": encode_masked_field(row.get("name") or row.get("customer") or row.get("customer_name")),
            "phone": encode_masked_field(row.get("phone") or row.get("customer_phone") or row.get("phone_number")),
            "email": encode_masked_field(row.get("email")),
            "address": encode_masked_field(
                row.get("address") or row.get("shipping") or row.get("shipping_full_address")
            ),
            "order_count": row.get("order_count"),
        }
    if domain == "users":
        return {
            "id": row.get("id"),
            "domain": "users",
            "name": encode_masked_field(row.get("name") or row.get("full_name") or row.get("username")),
            "email": encode_masked_field(row.get("email")),
            "phone": encode_masked_field(row.get("phone") or row.get("phone_number")),
            "role": row.get("role") or row.get("user_type"),
        }
    # orders (default) + any other domain that still carries customer fields
    return {
        "id": row.get("id") or row.get("order_id"),
        "domain": domain or "orders",
        "status_name": row.get("status_name") or row.get("status"),
        "total_price": row.get("total_price"),
        "inserted_at": row.get("inserted_at"),
        "customer_name": encode_masked_field(row.get("customer") or row.get("customer_name") or row.get("name")),
        "customer_phone": encode_masked_field(row.get("phone") or row.get("customer_phone")),
        "shipping": encode_masked_field(row.get("shipping_full_address") or row.get("shipping") or row.get("address")),
        "items": row.get("items") or row.get("items_preview") or row.get("items_text"),
    }


def wrap_order_row(row: dict[str, Any]) -> dict[str, Any]:
    return wrap_pii_row(row, domain="orders")


def count_masked_fields(rows: list[Any]) -> int:
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, field in row.items():
            if key in PII_FIELD_KEYS and isinstance(field, dict) and field.get("masked"):
                n += 1
    return n


def build_envelope(icon: str, query_result: dict[str, Any]) -> dict[str, Any]:
    mapper = query_result.get("mapper") or {}
    backend = query_result.get("backend") or {}
    domain = str(backend.get("domain") or "orders")
    primary = query_result.get("primary") or {}
    preview = primary.get("preview") or []
    details = query_result.get("details") or []

    encoded_preview = [
        wrap_pii_row(r, domain=domain) if isinstance(r, dict) else r for r in preview
    ]
    encoded_details = []
    for d in details:
        detail = d.get("detail") if isinstance(d, dict) else None
        if not isinstance(detail, dict):
            encoded_details.append(d)
            continue
        encoded_details.append(
            {
                "id": d.get("id"),
                "url": d.get("url"),
                "http_status": d.get("http_status"),
                "detail": {
                    "id": detail.get("id"),
                    "domain": domain,
                    "status_name": detail.get("status_name"),
                    "total_price": detail.get("total_price"),
                    "items_count": detail.get("items_count"),
                    "items_preview": detail.get("items_preview"),
                    "customer_name": encode_masked_field(detail.get("name") or detail.get("customer_name")),
                    "customer_phone": encode_masked_field(detail.get("phone") or detail.get("customer_phone")),
                    "email": encode_masked_field(detail.get("email")),
                    "address": encode_masked_field(detail.get("address") or detail.get("shipping")),
                    "keys": detail.get("keys"),
                },
            }
        )

    masked_fields = count_masked_fields(encoded_preview)

    return {
        "ok": bool(query_result.get("ok")),
        "called_at": datetime.now(timezone.utc).isoformat(),
        "call": {
            "icon_input": icon,
            "icon_real": mapper.get("real"),
            "icon_kind": mapper.get("kind"),
            "map_source": mapper.get("source"),
            "pii_domain": domain,
        },
        "backend": backend,
        "encoding": {
            "mode": "mask",
            "layer": "inner",
            "note": (
                "Inner mask envelope for PII fields (name/phone/email/address). "
                "Open API already returns '*'; b64/hash are not reversible to cleartext."
            ),
            "masked_field_count": masked_fields,
            "pii_fields": list(PII_FIELD_KEYS),
        },
        "response": {
            "http_status": primary.get("http_status"),
            "success": primary.get("success"),
            "total_entries": primary.get("total_entries"),
            "count": primary.get("count"),
            "preview_masked": encoded_preview,
            "details_masked": encoded_details,
            "related": query_result.get("related") or [],
        },
        "error": query_result.get("error"),
        "hint": query_result.get("hint"),
    }


def call_icon(
    icon: str,
    shop_id: str,
    base_url: str,
    deep: bool = False,
    detail_limit: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    clear_proxy_env()
    # Force requests to ignore residual env proxy
    session_trust = getattr(requests, "Session")
    # Patch deep_query's request path by clearing env again inside
    result = deep_query(
        icon,
        shop_id=shop_id,
        base_url=base_url,
        deep=deep,
        detail_limit=detail_limit,
        page_size=page_size,
    )
    return build_envelope(icon, result)


def parse_args():
    load_extra_env()
    clear_proxy_env()
    p = argparse.ArgumentParser(description="Mapper icon-name call → masked backend response.")
    p.add_argument("--icon", default="", help="Single icon name / label")
    p.add_argument("--icons", default="", help="Comma-separated icon names")
    p.add_argument(
        "--pii",
        action="store_true",
        help="Call PII-related icons: cart,đơn hàng,customer,phone,địa chỉ,user,users",
    )
    p.add_argument("--deep", action="store_true")
    p.add_argument("--detail-limit", type=int, default=1)
    p.add_argument("--page-size", type=int, default=10)
    p.add_argument("--shop-id", default=DEFAULT_SHOP)
    p.add_argument("--base-url", default=os.getenv("PANCAKE_POS_BASE_URL", "https://pos.pages.fm/api/v1"))
    p.add_argument("--aes", action="store_true", help="Wrap response in AES-256-GCM ciphertext.")
    p.add_argument("--decrypt-aes", default="", help="Decrypt an AES icon-call JSON file and print plaintext.")
    p.add_argument("--output", default="")
    return p.parse_args()


def main():
    args = parse_args()
    clear_proxy_env()

    if args.decrypt_aes:
        from mapper_aes_codec import decrypt_envelope, load_or_create_key

        raw = json.loads(Path(args.decrypt_aes).read_text(encoding="utf-8"))
        key = load_or_create_key()
        if isinstance(raw, dict) and "calls" in raw:
            out = []
            for item in raw["calls"]:
                if isinstance(item, dict) and "aes" in item:
                    out.append(decrypt_envelope(item["aes"], key=key))
                else:
                    out.append(item)
            payload = {"calls": out}
        elif isinstance(raw, dict) and "aes" in raw:
            payload = decrypt_envelope(raw["aes"], key=key)
        else:
            payload = decrypt_envelope(raw, key=key)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        return 0

    export_endpoint_map()

    icons: list[str] = []
    if args.icons:
        icons = [x.strip() for x in args.icons.split(",") if x.strip()]
    elif args.icon:
        icons = [args.icon]
    elif args.pii:
        icons = ["cart", "đơn hàng", "customer", "phone", "địa chỉ", "user", "users"]
    else:
        icons = ["cart"]

    # Bypass broken proxy inside requests globally for this process
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    # Monkeypatch request_api to disable trust_env
    import pancake_backend_deep_query as bd

    def request_api_direct(base: str, path: str, params: dict[str, Any] | None = None, timeout: int = 30):
        clear_proxy_env()
        key = (
            os.getenv("PANCAKE_POS_API_KEY", "")
            or os.getenv("PANCAKE_API_KEY", "")
            or os.getenv("CENTRAL_API_KEY", "")
        ).strip()
        if not key:
            raise RuntimeError("Missing PANCAKE_POS_API_KEY")
        url = f"{base.rstrip('/')}{path}"
        query = {"api_key": key, **(params or {})}
        headers = {"Accept": "application/json"}
        cookie = os.getenv("PANCAKE_POS_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie
        sess = requests.Session()
        sess.trust_env = False  # ignore HTTP_PROXY from env / broken DataImpulse
        resp = sess.get(url, params=query, headers=headers, timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}
        if not isinstance(body, dict):
            body = {"data": body}
        return {
            "url": url,
            "http_status": resp.status_code,
            "success": body.get("success"),
            "message": body.get("message"),
            "error_code": body.get("error_code"),
            "body": body,
        }

    bd.request_api = request_api_direct

    envelopes = [
        call_icon(
            i,
            args.shop_id,
            args.base_url,
            deep=args.deep,
            detail_limit=args.detail_limit,
            page_size=args.page_size,
        )
        for i in icons
    ]

    if args.aes:
        from mapper_aes_codec import load_or_create_key, wrap_icon_response

        aes_key = load_or_create_key()
        envelopes = [wrap_icon_response(icons[idx], env, key=aes_key) for idx, env in enumerate(envelopes)]

    payload = envelopes[0] if len(envelopes) == 1 else {"calls": envelopes}

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        out = Path(args.output)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = "aes" if args.aes else "masked"
        out = Path("/tmp/pancake_backend_deep") / f"icon-call-{suffix}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(json.dumps({"saved": str(out), "aes": bool(args.aes)}, ensure_ascii=False), file=sys.stderr)

    ok = payload.get("ok") if isinstance(payload, dict) and "ok" in payload else any(e.get("ok") for e in envelopes)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
