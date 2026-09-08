#!/usr/bin/env python3
"""TikTok automation — standalone, reads configs/config_tiktok.json only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "configs" / "config_tiktok.json"
TIKTOK_SELLER_HOME = "https://seller-vn.tiktok.com/"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("config_tiktok.json must contain a non-empty 'accounts' list")
    return data


def build_proxy_url(proxy_cfg: dict[str, Any]) -> str | None:
    if not proxy_cfg.get("enabled"):
        return None
    host = str(proxy_cfg.get("host", "")).strip()
    port = proxy_cfg.get("port")
    if not host or not port:
        return None
    scheme = str(proxy_cfg.get("scheme", "http")).strip() or "http"
    username = str(proxy_cfg.get("username", "")).strip()
    password = str(proxy_cfg.get("password", "")).strip()
    if username:
        auth = f"{username}:{password}@"
        return f"{scheme}://{auth}{host}:{port}"
    return f"{scheme}://{host}:{port}"


def make_session(proxy_cfg: dict[str, Any], timeout: int) -> tuple[requests.Session, int]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
    )
    proxy_url = build_proxy_url(proxy_cfg)
    if proxy_url:
        session.proxies.update({"http": proxy_url, "https": proxy_url})
    return session, timeout


def login_and_fetch_orders(
    account: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    username = str(account.get("username", "")).strip()
    password = str(account.get("password", "")).strip()
    if not username or not password:
        raise ValueError("Each account needs non-empty username and password")

    access_token = str(account.get("access_token", "")).strip()
    shop_id = str(account.get("shop_id", "")).strip()
    timeout = int(settings.get("request_timeout_seconds", 30))
    session, timeout = make_session(account.get("proxy", {}), timeout)

    if access_token:
        headers = {"x-tts-access-token": access_token}
        params = {"shop_id": shop_id} if shop_id else {}
        response = session.get(
            "https://open-api.tiktokglobalshop.com/order/202309/orders/search",
            headers=headers,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return {
            "account": username,
            "mode": "open_api_token",
            "status": "ok",
            "orders": response.json(),
        }

    # Cookie/session based path: validate seller portal reachability with account context.
    probe = session.get(TIKTOK_SELLER_HOME, timeout=timeout, allow_redirects=False)
    return {
        "account": username,
        "mode": "seller_portal_probe",
        "status": "ok" if probe.status_code in (200, 302, 307) else "warning",
        "http_status": probe.status_code,
        "message": (
            "Portal reachable. Add access_token (+ optional shop_id) in config_tiktok.json "
            "to fetch orders via TikTok Shop Open API."
        ),
    }


def save_results(results: list[dict[str, Any]], settings: dict[str, Any]) -> Path:
    output_dir = ROOT_DIR / str(settings.get("output_dir", "output/tiktok"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"tiktok_orders_{stamp}.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    try:
        config = load_config()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"tiktok_automation: {exc}", file=sys.stderr)
        return 2

    settings = config.get("settings", {})
    results: list[dict[str, Any]] = []
    for index, account in enumerate(config["accounts"], start=1):
        label = str(account.get("username") or f"account_{index}")
        print(f"[{index}/{len(config['accounts'])}] TikTok account: {label}")
        try:
            results.append(login_and_fetch_orders(account, settings))
        except requests.RequestException as exc:
            print(f"  request failed: {exc}", file=sys.stderr)
            results.append({"account": label, "status": "error", "error": str(exc)})
        except ValueError as exc:
            print(f"  invalid account config: {exc}", file=sys.stderr)
            results.append({"account": label, "status": "error", "error": str(exc)})

    output_path = save_results(results, settings)
    print(f"Saved results to {output_path}")
    return 0 if any(item.get("status") == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
