#!/usr/bin/env python3
"""Standalone Pancake order sync worker (ported from BM OrderSyncWorker).

Defaults match reverse-mapped workers:
- shop_id: 1530618
- endpoint: https://pos.pancake.vn/api/v1/shops/{shop_id}/orders
- auth: PANCAKE_POS_API_KEY or Bearer token

Optional HTTP(S) proxy via --proxy / PANCAKE_HTTP_PROXY / HTTPS_PROXY.
Does not ingest bulk third-party credential dumps.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from pancake_pos_client import auth_ready, missing_auth_names, resolve_credentials


DEFAULT_SHOP_IDS = "1530618"
DEFAULT_BASE = "https://pos.pancake.vn/api/v1"
DEFAULT_STATE = "/tmp/pancake_order_sync_state.json"
DEFAULT_OUT_DIR = "/tmp/pancake_order_sync"


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Pancake POS orders for configured shops.")
    parser.add_argument("--shop-ids", default=os.getenv("PANCAKE_POS_SHOP_IDS", DEFAULT_SHOP_IDS))
    parser.add_argument("--base-url", default=os.getenv("PANCAKE_POS_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--api-key", default=os.getenv("PANCAKE_POS_API_KEY", "").strip())
    parser.add_argument(
        "--access-token",
        default=(
            os.getenv("PANCAKE_POS_ACCESS_TOKEN", "").strip()
            or os.getenv("PANCAKE_POS_TOKEN", "").strip()
            or os.getenv("PANCAKE_TOKEN", "").strip()
        ),
    )
    parser.add_argument("--page-size", type=int, default=int(os.getenv("ORDER_SYNC_PAGE_SIZE", "20")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("ORDER_SYNC_MAX_PAGES", "50")))
    parser.add_argument("--state-file", default=os.getenv("ORDER_SYNC_STATE_FILE", DEFAULT_STATE))
    parser.add_argument("--output-dir", default=os.getenv("ORDER_SYNC_OUTPUT_DIR", DEFAULT_OUT_DIR))
    parser.add_argument(
        "--proxy",
        default=(
            os.getenv("PANCAKE_HTTP_PROXY", "").strip()
            or os.getenv("HTTPS_PROXY", "").strip()
            or os.getenv("HTTP_PROXY", "").strip()
        ),
        help="Optional proxy URL, e.g. http://user:pass@host:port or host:port",
    )
    parser.add_argument("--once", action="store_true", help="Run one sync cycle and exit (default).")
    parser.add_argument("--loop-seconds", type=int, default=0, help="If >0, loop forever with this sleep.")
    return parser.parse_args()


def normalize_proxy(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" in text:
        return text
    # host:port or host:port:user:pass
    parts = text.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    return f"http://{text}"


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"shops": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"shops": {}}


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def request_orders(session: requests.Session, base_url: str, shop_id: str, creds: dict, page: int, page_size: int):
    url = f"{base_url.rstrip('/')}/shops/{shop_id}/orders"
    params = {"limit": page_size, "page": page, "page_number": page}
    headers = {"Accept": "application/json"}
    if creds.get("api_key"):
        params["api_key"] = creds["api_key"]
    elif creds.get("access_token"):
        headers["Authorization"] = f"Bearer {creds['access_token']}"
        params["access_token"] = creds["access_token"]
    else:
        raise ValueError("missing credential")

    response = session.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected response type")
    if payload.get("success") is False:
        raise RuntimeError(payload.get("message") or f"error_code={payload.get('error_code')}")
    return payload


def sync_shop(session, base_url, shop_id, creds, page_size, max_pages, state, out_dir: Path):
    known = set(state.get("shops", {}).get(str(shop_id), {}).get("seen_ids", []))
    new_orders = []
    pages_fetched = 0
    checked = 0

    for page in range(1, max_pages + 1):
        payload = request_orders(session, base_url, shop_id, creds, page, page_size)
        rows = payload.get("data") or []
        if not rows:
            break
        pages_fetched = page
        checked += len(rows)

        page_ids = [str(item.get("id") or "").strip() for item in rows if item.get("id") is not None]
        if page_ids and all(pid in known for pid in page_ids):
            break

        for item in rows:
            oid = str(item.get("id") or "").strip()
            if not oid or oid in known:
                continue
            known.add(oid)
            new_orders.append(item)

        total = int(payload.get("total") or 0)
        if total and page * page_size >= total:
            break

    shop_dir = out_dir / f"shop_{shop_id}"
    shop_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if new_orders:
        out_file = shop_dir / f"new_orders_{stamp}.json"
        out_file.write_text(json.dumps(new_orders, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        out_file = None

    state.setdefault("shops", {})[str(shop_id)] = {
        "seen_ids": sorted(known)[-5000:],
        "last_sync_at_utc": datetime.now(timezone.utc).isoformat(),
        "last_new_count": len(new_orders),
        "last_output_file": str(out_file) if out_file else "",
    }

    return {
        "shop_id": shop_id,
        "pages_fetched": pages_fetched,
        "orders_checked": checked,
        "new_orders": len(new_orders),
        "output_file": str(out_file) if out_file else "",
    }


def sync_once(args) -> dict:
    creds = resolve_credentials(api_key=args.api_key, access_token=args.access_token)
    if not auth_ready(creds):
        raise ValueError("Missing required inputs: " + ", ".join(missing_auth_names(creds)))

    shop_ids = [s.strip() for s in str(args.shop_ids).split(",") if s.strip()]
    if not shop_ids:
        shop_ids = [DEFAULT_SHOP_IDS]

    page_size = max(10, min(20, int(args.page_size)))
    state_path = Path(args.state_file)
    out_dir = Path(args.output_dir)
    state = load_state(state_path)

    session = requests.Session()
    proxy = normalize_proxy(args.proxy)
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    details = {"shops": {}, "total_new": 0, "base_url": args.base_url, "proxy_enabled": bool(proxy)}
    for shop_id in shop_ids:
        shop_result = sync_shop(
            session,
            args.base_url,
            shop_id,
            creds,
            page_size,
            max(1, args.max_pages),
            state,
            out_dir,
        )
        details["shops"][shop_id] = shop_result
        details["total_new"] += shop_result["new_orders"]

    state["last_run_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["last_details"] = details
    save_state(state_path, state)
    return details


def main():
    args = parse_args()
    loop_seconds = int(args.loop_seconds or 0)

    while True:
        try:
            details = sync_once(args)
            print(json.dumps(details, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(json.dumps({"error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
            if loop_seconds <= 0:
                return 2
        if loop_seconds <= 0:
            return 0
        time.sleep(loop_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
