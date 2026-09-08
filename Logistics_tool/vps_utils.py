# -*- coding: utf-8 -*-
"""Shared VPS anti-block helpers for Logistics_tool scripts."""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_PROXY_FILE = ROOT_DIR / "configs" / "proxy.txt"

CHROME_UAS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
]

STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-infobars",
]


def is_vps_environment() -> bool:
    if os.getenv("LOGISTICS_FORCE_VPS", "").strip().lower() in {"1", "true", "yes"}:
        return True
    if os.name != "posix":
        return False
    if os.getenv("DISPLAY"):
        return False
    return bool(os.getenv("SSH_CONNECTION") or os.getenv("SSH_CLIENT") or Path("/.dockerenv").exists())


def anti_block_settings(settings: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "enabled": True,
        "delay_between_accounts_min": 8,
        "delay_between_accounts_max": 18,
        "max_retries": 3,
        "retry_backoff_seconds": 6,
        "require_proxy_on_vps": True,
        "reuse_tpos_session": True,
        "headless_on_vps": True,
        "human_typing_delay_ms": 80,
    }
    custom = settings.get("anti_block") or {}
    if not isinstance(custom, dict):
        return defaults
    merged = defaults.copy()
    merged.update(custom)
    return merged


def sleep_between_accounts(settings: dict[str, Any]) -> None:
    ab = anti_block_settings(settings)
    if not ab.get("enabled"):
        return
    low = float(ab["delay_between_accounts_min"])
    high = float(ab["delay_between_accounts_max"])
    delay = random.uniform(low, high)
    print(f"[*] Chờ {delay:.1f}s trước tài khoản tiếp theo (tránh rate-limit)...")
    time.sleep(delay)


def pick_user_agent(settings: dict[str, Any]) -> str:
    configured = str(settings.get("user_agent", "")).strip()
    if configured:
        return configured
    return random.choice(CHROME_UAS)


def parse_proxy_line(line: str) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    parts = [p.strip() for p in raw.split(":")]
    if len(parts) == 4:
        return {
            "enabled": True,
            "scheme": "http",
            "host": parts[0],
            "port": int(parts[1]),
            "username": parts[2],
            "password": parts[3],
        }
    if len(parts) == 2:
        return {
            "enabled": True,
            "scheme": "http",
            "host": parts[0],
            "port": int(parts[1]),
            "username": "",
            "password": "",
        }
    return None


def load_proxy_pool(config: dict[str, Any]) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for item in config.get("proxy_pool") or []:
        if isinstance(item, dict) and item.get("host") and item.get("port"):
            entry = {"enabled": True, "scheme": "http", "username": "", "password": ""}
            entry.update(item)
            entry["enabled"] = True
            pool.append(entry)

    proxy_file = config.get("proxy_file") or "configs/proxy.txt"
    proxy_path = Path(proxy_file)
    if not proxy_path.is_absolute():
        proxy_path = ROOT_DIR / proxy_path
    if proxy_path.exists():
        for line in proxy_path.read_text(encoding="utf-8-sig").splitlines():
            parsed = parse_proxy_line(line)
            if parsed:
                pool.append(parsed)
    return pool


def account_proxy_enabled(proxy_cfg: dict[str, Any] | None) -> bool:
    if not proxy_cfg:
        return False
    if not proxy_cfg.get("enabled"):
        return False
    return bool(str(proxy_cfg.get("host", "")).strip() and proxy_cfg.get("port"))


def resolve_account_proxy(
    account: dict[str, Any],
    index: int,
    proxy_pool: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    account_proxy = account.get("proxy") or {}
    if account_proxy_enabled(account_proxy):
        return account_proxy

    ab = anti_block_settings(settings)
    on_vps = is_vps_environment()
    if proxy_pool:
        chosen = proxy_pool[index % len(proxy_pool)]
        print(f"[*] Gán proxy pool #{index % len(proxy_pool) + 1} cho tài khoản.")
        return chosen

    if on_vps and ab.get("require_proxy_on_vps"):
        print(
            "[!] VPS không có proxy: IP datacenter dễ bị J&T/TPOS chặn. "
            "Thêm proxy vào account hoặc configs/proxy.txt."
        )
    return {"enabled": False}


def build_requests_proxy(proxy_cfg: dict[str, Any]) -> dict[str, str] | None:
    if not account_proxy_enabled(proxy_cfg):
        return None
    host = str(proxy_cfg.get("host", "")).strip()
    port = proxy_cfg.get("port")
    scheme = str(proxy_cfg.get("scheme", "http")).strip() or "http"
    username = str(proxy_cfg.get("username", "")).strip()
    password = str(proxy_cfg.get("password", "")).strip()
    if username:
        proxy_url = f"{scheme}://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"{scheme}://{host}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def build_playwright_proxy(proxy_cfg: dict[str, Any]) -> dict[str, str] | None:
    if not account_proxy_enabled(proxy_cfg):
        return None
    host = str(proxy_cfg.get("host", "")).strip()
    port = proxy_cfg.get("port")
    scheme = str(proxy_cfg.get("scheme", "http")).strip() or "http"
    username = str(proxy_cfg.get("username", "")).strip()
    password = str(proxy_cfg.get("password", "")).strip()
    server = f"{scheme}://{host}:{port}"
    if username:
        return {"server": server, "username": username, "password": password}
    return {"server": server}


def browser_context_options(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "viewport": {"width": 1366, "height": 768},
        "locale": "vi-VN",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "user_agent": pick_user_agent(settings),
    }


def resolve_headless(settings: dict[str, Any]) -> bool:
    ab = anti_block_settings(settings)
    if "headless" in settings:
        return bool(settings.get("headless"))
    if is_vps_environment():
        return bool(ab.get("headless_on_vps", True))
    return False


def with_retries(
    action: Callable[[], Any],
    *,
    settings: dict[str, Any],
    label: str,
    retryable_status: Callable[[Any], bool] | None = None,
) -> Any:
    ab = anti_block_settings(settings)
    max_retries = int(ab.get("max_retries", 3))
    backoff = float(ab.get("retry_backoff_seconds", 6))

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            result = action()
            if retryable_status and retryable_status(result):
                raise RuntimeError(f"{label} returned retryable status")
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            wait = backoff * attempt + random.uniform(0.5, 2.0)
            print(f"[!] {label} lỗi (lần {attempt}/{max_retries}): {exc}. Retry sau {wait:.1f}s...")
            time.sleep(wait)
    if last_error:
        raise last_error
    raise RuntimeError(f"{label} failed without exception")


def apply_stealth_init_script(page: Any) -> None:
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        """
    )
