#!/usr/bin/env python3
"""Sapo login via Playwright — password only; abort immediately if OTP UI appears."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

EXIT_OTP_FORBIDDEN = 3

SSO_LOGIN_BASE = "https://accounts.sapo.vn"
PARTNER_LOGIN_URL = "https://developers.sapo.vn/services/partners/auth/login"
ENV_USERNAME = "SAPO_USERNAME"
ENV_PASSWORD = "SAPO_PASSWORD"

OTP_URL_FRAGMENTS = (
    "/login/with-otp",
    "/with-otp",
    "/otp-verify",
    "/verify-otp",
)

OTP_TEXT_PATTERNS = (
    r"đăng nhập bằng mã otp",
    r"nhập mã otp",
    r"mã xác thực otp",
    r"\bmã otp\b",
    r"\botp\b",
    r"one[- ]time password",
    r"gửi mã otp",
    r"zalo otp",
)

OTP_INPUT_SELECTORS = (
    'input[name*="otp" i]',
    'input[id*="otp" i]',
    'input[autocomplete="one-time-code"]',
    'input[inputmode="numeric"][maxlength="6"]',
)


class OtpForbiddenError(RuntimeError):
    """Raised when OTP flow is detected — login must stop."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sapo Playwright login (password path only). Stops with exit code 3 if OTP appears.",
    )
    parser.add_argument(
        "--target",
        choices=("merchant", "partner"),
        default="merchant",
        help="merchant=accounts.sapo.vn SSO; partner=developers.sapo.vn form login.",
    )
    parser.add_argument("--username", default="", help=f"Email/phone (env {ENV_USERNAME}).")
    parser.add_argument("--password", default="", help=f"Password (env {ENV_PASSWORD}).")
    parser.add_argument("--account-file", default="", help="File with username:password line.")
    parser.add_argument(
        "--shop-domain",
        default="",
        help="Shop slug when SSO asks for store domain (multi-store accounts).",
    )
    parser.add_argument("--service-type", default="retail", help="SSO serviceType (merchant).")
    parser.add_argument("--headless", action="store_true", help="Run Chromium headless.")
    parser.add_argument("--slowmo-ms", type=int, default=0, help="Playwright slow motion (debug).")
    parser.add_argument(
        "--proxy-server",
        default="",
        help="Proxy for browser, e.g. http://user:pass@host:8888 (residential VN recommended).",
    )
    parser.add_argument(
        "--storage-state-in",
        default="",
        help="Reuse Playwright storage JSON to reduce re-auth / OTP risk.",
    )
    parser.add_argument(
        "--storage-state-out",
        default="",
        help="Save Playwright storage JSON after successful login.",
    )
    parser.add_argument(
        "--cookie-jar",
        default="",
        help="Also export cookies to Netscape jar (optional).",
    )
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Navigation/action timeout.")
    return parser.parse_args()


def env_or(key: str, cli_value: str, required: bool = False) -> str:
    value = (cli_value or os.getenv(key, "")).strip()
    if required and not value:
        raise SystemExit(f"Missing {key}: pass flag or set environment variable.")
    return value


def load_credentials(args: argparse.Namespace) -> Tuple[str, str]:
    if args.account_file:
        with open(args.account_file, "r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                username, password = line.split(":", 1)
                username = username.strip()
                password = password.strip()
                if username and password:
                    return username, password
        raise SystemExit(f"No username:password line found in {args.account_file}")
    username = env_or(ENV_USERNAME, args.username, required=True)
    password = env_or(ENV_PASSWORD, args.password, required=True)
    return username, password


def mask(value: str, keep: int = 3) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "..." + value[-keep:]


def url_indicates_otp(url: str) -> bool:
    lowered = url.lower()
    return any(fragment in lowered for fragment in OTP_URL_FRAGMENTS)


def page_text_indicates_otp(text: str) -> Optional[str]:
    lowered = text.lower()
    for pattern in OTP_TEXT_PATTERNS:
        if re.search(pattern, lowered):
            return pattern
    return None


def assert_no_otp(page, *, where: str) -> None:
    if url_indicates_otp(page.url):
        raise OtpForbiddenError(f"OTP URL blocked ({where}): {page.url}")

    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    hit = page_text_indicates_otp(body)
    if hit:
        raise OtpForbiddenError(f"OTP copy detected ({where}), pattern={hit}")

    for selector in OTP_INPUT_SELECTORS:
        locator = page.locator(selector)
        if locator.count() > 0 and locator.first.is_visible():
            raise OtpForbiddenError(f"OTP input visible ({where}): {selector}")


def install_otp_guards(page) -> None:
    def on_nav(frame) -> None:
        if frame != page.main_frame:
            return
        if url_indicates_otp(frame.url):
            raise OtpForbiddenError(f"Navigation to OTP route blocked: {frame.url}")

    page.on("framenavigated", on_nav)

    def route_handler(route) -> None:
        url = route.request.url.lower()
        if any(fragment in url for fragment in OTP_URL_FRAGMENTS):
            raise OtpForbiddenError(f"Request to OTP route blocked: {route.request.url}")
        route.continue_()

    page.route("**/*", route_handler)


def fill_shop_domain_if_present(page, shop_domain: str) -> None:
    shop_domain = shop_domain.strip()
    if not shop_domain:
        return
    slug = shop_domain.replace(".mysapo.net", "").replace(".mysapogo.com", "")
    candidates = [
        'input[name="domain"]',
        'input[name="store"]',
        'input[placeholder*="domain" i]',
        'input[placeholder*="cửa hàng" i]',
    ]
    for selector in candidates:
        field = page.locator(selector)
        if field.count() > 0 and field.first.is_visible():
            field.first.fill(slug)
            return


def login_merchant(page, username: str, password: str, shop_domain: str, service_type: str) -> None:
    login_url = f"{SSO_LOGIN_BASE}/login?serviceType={urllib_parse_quote(service_type)}"
    page.goto(login_url, wait_until="domcontentloaded")
    assert_no_otp(page, where="merchant landing")

    page.locator("#phoneNumber, input[name=phoneNumber]").first.fill(username)
    page.locator('input[name=password], input[type=password]').first.fill(password)
    fill_shop_domain_if_present(page, shop_domain)

    assert_no_otp(page, where="before submit")
    page.get_by_role("button", name=re.compile(r"^Đăng nhập$", re.I)).first.click()

    page.wait_for_timeout(1500)
    assert_no_otp(page, where="after submit")

    try:
        page.wait_for_function(
            """() => {
                const href = location.href.toLowerCase();
                if (!href.includes('/login')) return true;
                const body = document.body ? document.body.innerText : '';
                if (body.includes('Thông tin đăng nhập không chính xác')) return true;
                if (body.includes('Incorrect login')) return true;
                return false;
            }""",
            timeout=30000,
        )
    except Exception:
        assert_no_otp(page, where="wait login outcome")
        raise

    assert_no_otp(page, where="final merchant")

    if "/login" in page.url.lower():
        body = page.inner_text("body")
        if "không chính xác" in body.lower() or "incorrect" in body.lower():
            raise RuntimeError("Invalid email/phone or password.")
        raise RuntimeError(f"Login did not leave SSO page: {page.url}")


def login_partner(page, email: str, password: str) -> None:
    page.goto(PARTNER_LOGIN_URL, wait_until="domcontentloaded")
    assert_no_otp(page, where="partner landing")

    page.locator('input[name=Email], #Email').first.fill(email)
    page.locator('input[name=Password], #Password').first.fill(password)
    assert_no_otp(page, where="before partner submit")

    page.locator('form[action*="partners/auth"] button[type=submit], form button[type=submit]').first.click()
    page.wait_for_timeout(2000)
    assert_no_otp(page, where="after partner submit")

    if "auth/login" in page.url.lower():
        body = page.inner_text("body")
        if "Thông tin đăng nhập" in body or "field-validation-error" in body:
            raise RuntimeError("Partner portal rejected credentials or account pending approval.")
        raise RuntimeError(f"Partner login stuck on login page: {page.url}")


def urllib_parse_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def export_cookies(context, cookie_jar_path: str) -> None:
    import http.cookiejar

    cookies = context.cookies()
    mozilla = http.cookiejar.MozillaCookieJar(cookie_jar_path)
    for item in cookies:
        mozilla.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=item["name"],
                value=item["value"],
                port=None,
                port_specified=False,
                domain=item.get("domain", ""),
                domain_specified=bool(item.get("domain")),
                domain_initial_dot=item.get("domain", "").startswith("."),
                path=item.get("path", "/"),
                path_specified=bool(item.get("path")),
                secure=bool(item.get("secure")),
                expires=int(item["expires"]) if item.get("expires") else None,
                discard=False,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": ""} if item.get("httpOnly") else {},
                rfc2109=False,
            )
        )
    mozilla.save(ignore_discard=True, ignore_expires=True)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright not installed. Run: pip install -r scripts/requirements-playwright.txt "
            "&& python3 -m playwright install chromium"
        ) from exc

    username, password = load_credentials(args)
    report: Dict[str, Any] = {
        "target": args.target,
        "username_preview": mask(username),
        "headless": args.headless,
        "otp_policy": "forbidden",
    }

    launch_kwargs: Dict[str, Any] = {"headless": args.headless, "slow_mo": args.slowmo_ms}
    if args.proxy_server.strip():
        launch_kwargs["proxy"] = {"server": args.proxy_server.strip()}

    context_kwargs: Dict[str, Any] = {
        "locale": "vi-VN",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    if args.storage_state_in.strip():
        context_kwargs["storage_state"] = args.storage_state_in.strip()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(args.timeout_ms)
        page = context.new_page()
        install_otp_guards(page)

        try:
            if args.target == "partner":
                login_partner(page, username, password)
            else:
                login_merchant(
                    page,
                    username,
                    password,
                    args.shop_domain.strip(),
                    args.service_type.strip() or "retail",
                )
        finally:
            assert_no_otp(page, where="pre-export")

        report["ok"] = True
        report["final_url"] = page.url

        if args.storage_state_out.strip():
            context.storage_state(path=args.storage_state_out.strip())
            report["storage_state_out"] = args.storage_state_out.strip()

        if args.cookie_jar.strip():
            export_cookies(context, args.cookie_jar.strip())
            report["cookie_jar"] = args.cookie_jar.strip()

        browser.close()

    return report


def main() -> int:
    args = parse_args()
    try:
        report = run(args)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except OtpForbiddenError as exc:
        payload = {
            "ok": False,
            "classification": "otp_forbidden",
            "error": str(exc),
            "otp_policy": "aborted — OTP must not appear; use password-only session/proxy/VN IP",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return EXIT_OTP_FORBIDDEN
    except RuntimeError as exc:
        payload = {"ok": False, "classification": "login_failed", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
