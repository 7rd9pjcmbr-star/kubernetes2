#!/usr/bin/env python3
"""Parse Pancake OAuth callback URL and print code-exchange commands.

POS login does **not** use account.pancake.vn/oauth/token (404).
Real exchange is GET pancake_id_login_success?code=...&state=...

For full unmask save + probe, prefer:
  python3 scripts/pancake_code_unmask.py --callback-url '...'
"""

import argparse
import base64
import json
import sys
import urllib.parse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pancake OAuth helper: parse callback, validate state, generate exchange curl."
    )
    parser.add_argument(
        "--callback-url",
        default="",
        help="Full callback URL that contains ?code=...&state=...",
    )
    parser.add_argument(
        "--client-id",
        default="",
        help="OAuth client_id. If omitted, tries to read from callback query.",
    )
    parser.add_argument(
        "--client-secret",
        default="",
        help="Unused for POS pancake_id_login_success GET exchange; kept for compatibility.",
    )
    parser.add_argument(
        "--redirect-uri",
        default="https://pancake.vn/api/v1/users/pancake_id_login_success",
        help="redirect_uri used in OAuth authorization.",
    )
    parser.add_argument(
        "--token-endpoint",
        default="https://pancake.vn/api/v1/users/pancake_id_login_success",
        help="Code exchange endpoint (GET). Default: pancake_id_login_success.",
    )
    parser.add_argument(
        "--require-pos-login",
        action="store_true",
        help="Fail if decoded state does not contain pos_login=true.",
    )
    return parser.parse_args()


def decode_state(raw_state):
    if not raw_state:
        return None, "missing_state"
    try:
        # state may already be url-decoded by parse_qs; still normalize padding for base64.
        padding = "=" * ((4 - len(raw_state) % 4) % 4)
        decoded = base64.b64decode((raw_state + padding).encode("utf-8")).decode("utf-8")
        obj = json.loads(decoded)
        if isinstance(obj, dict):
            return obj, None
        return None, "state_not_object"
    except Exception as exc:
        return None, f"state_decode_error: {exc}"


def mask(value, keep=4):
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "..." + value[-keep:]


def main():
    args = parse_args()
    if not args.callback_url:
        print("Missing --callback-url", file=sys.stderr)
        return 2

    parsed = urllib.parse.urlparse(args.callback_url)
    query = urllib.parse.parse_qs(parsed.query)

    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    callback_client_id = (query.get("client_id") or [""])[0]
    client_id = args.client_id or callback_client_id

    if not code:
        print("Callback URL does not contain code parameter.", file=sys.stderr)
        return 2
    if not client_id:
        print("Missing client_id: provide --client-id or include in callback query.", file=sys.stderr)
        return 2

    state_obj, state_error = decode_state(state)
    state_valid = state_error is None
    if args.require_pos_login:
        if not state_valid or state_obj.get("pos_login") is not True:
            print("State validation failed: pos_login=true is required.", file=sys.stderr)
            return 1

    report = {
        "code_present": bool(code),
        "code_preview": mask(code, keep=3),
        "client_id": client_id,
        "redirect_uri": args.redirect_uri,
        "state_present": bool(state),
        "state_valid_json": state_valid,
        "state_error": state_error,
        "state_decoded": state_obj if state_valid else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    params = {"code": code, "client_id": client_id, "redirect_uri": args.redirect_uri}
    if state:
        params["state"] = state
    exchange_url = args.token_endpoint.rstrip("/") + "?" + urllib.parse.urlencode(params)
    curl_cmd = f"curl -sS -D - -o /tmp/pancake_exchange.body '{exchange_url}'"
    print("\nCode exchange command (GET — POS real path):")
    print(curl_cmd)
    print("\nUnmask helper (save cookie + probe PII):")
    print(
        "python3 scripts/pancake_code_unmask.py "
        f"--callback-url '{args.callback_url}' --require-pos-login"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
