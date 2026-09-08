#!/usr/bin/env python3
"""Unified logistics CLI for ScanToolmanus V3 runbooks.

Wraps existing platform scripts behind one entry point so operators can run
daily ops, scan pipelines, and health checks without memorizing script paths.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env.vn-platforms.example"

SCRIPT_COMMANDS = {
    "check-apis": "check_vn_platform_apis.py",
    "monitor-orders": "monitor_pancake_orders.py",
    "daily-report": "daily_pancake_orders_to_telegram.py",
    "clean-accounts": "clean_accounts_for_v2.py",
    "build-credentials": "build_scanner_credentials.py",
    "scan-orders": "order_scanner_runner.py",
    "oauth-helper": "pancake_oauth_helper.py",
    "tiktok-url": "tiktok_seller_url_helper.py",
    "sanitize-profile": "sanitize_profile_json.py",
}

ENV_CHECKS = {
    "PANCAKE_POS_API_KEY": "Pancake POS API key for order fetch and monitoring",
    "TELEGRAM_BOT_TOKEN": "Telegram bot token for daily reports",
    "TELEGRAM_CHAT_ID": "Telegram chat id for daily reports",
    "GHTK_TOKEN": "GHTK authenticated smoke test",
    "NHANH_POS_APP_ID": "Nhanh.vn POS authenticated smoke test",
    "SAPO_ACCESS_TOKEN": "Sapo authenticated smoke test",
    "HARAVAN_ACCESS_TOKEN": "Haravan authenticated smoke test",
    "TIKTOK_SHOP_ACCESS_TOKEN": "TikTok Shop authenticated smoke test",
    "SHOPEE_ACCESS_TOKEN": "Shopee authenticated smoke test",
    "GHN_TOKEN": "GHN authenticated smoke test",
}


def state_dir() -> Path:
    return Path(os.getenv("LOGISTICS_TOOL_STATE_DIR", "/tmp/logistics-tool"))


def state_file() -> Path:
    return state_dir() / "run_history.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_history() -> dict:
    path = state_file()
    if not path.exists():
        return {"runs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"runs": []}


def save_history(history: dict) -> None:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    state_file().write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def record_run(name: str, exit_code: int, extra: dict | None = None) -> None:
    history = load_history()
    entry = {
        "name": name,
        "exit_code": exit_code,
        "timestamp": utc_now_iso(),
    }
    if extra:
        entry.update(extra)
    history.setdefault("runs", []).append(entry)
    history["runs"] = history["runs"][-100:]
    save_history(history)


def script_path(name: str) -> Path:
    filename = SCRIPT_COMMANDS.get(name)
    if not filename:
        raise KeyError(name)
    return SCRIPT_DIR / filename


def run_script(name: str, args: Sequence[str], *, dry_run: bool = False) -> int:
    path = script_path(name)
    if not path.exists():
        print(f"logistics_tool: script missing: {path}", file=sys.stderr)
        return 2

    cmd = [sys.executable, str(path), *args]
    print(f"$ {' '.join(cmd)}")
    if dry_run:
        return 0

    completed = subprocess.run(cmd, check=False)
    record_run(name, completed.returncode, {"command": cmd})
    return completed.returncode


def env_status() -> list[dict]:
    rows = []
    for key, description in ENV_CHECKS.items():
        value = os.getenv(key, "").strip()
        rows.append(
            {
                "key": key,
                "configured": bool(value),
                "description": description,
            }
        )
    return rows


def print_status() -> int:
    history = load_history()
    runs = history.get("runs", [])
    last_by_name: dict[str, dict] = {}
    for run in reversed(runs):
        last_by_name.setdefault(run["name"], run)

    print("Logistics Tool status")
    print("=====================")
    print(f"State file: {state_file()}")
    print(f"Env template: {ENV_FILE} ({'found' if ENV_FILE.exists() else 'missing'})")
    print("")
    print("Scripts")
    for command, filename in SCRIPT_COMMANDS.items():
        path = SCRIPT_DIR / filename
        marker = "ok" if path.exists() else "missing"
        last = last_by_name.get(command)
        last_line = "never"
        if last:
            last_line = f"{last['timestamp']} (exit {last['exit_code']})"
        print(f"  - {command:18} [{marker:7}] last: {last_line}")

    print("")
    print("Environment")
    for row in env_status():
        state = "set" if row["configured"] else "unset"
        print(f"  - {row['key']:28} [{state:5}] {row['description']}")

    return 0


def runbook_scan_pipeline(args: argparse.Namespace) -> int:
    steps: list[tuple[str, list[str]]] = [
        ("clean-accounts", ["--auto", *([] if not args.platform else ["--platform", args.platform])]),
        ("build-credentials", ["--clear-output", f"--max-per-platform={args.max_per_platform}"]),
        ("scan-orders", [f"--max-files={args.max_files}"]),
    ]
    return run_steps(steps, dry_run=args.dry_run)


def runbook_daily_ops(args: argparse.Namespace) -> int:
    check_args = ["--output", str(state_dir() / "platform-api-report.json")]
    if args.authenticated:
        check_args.append("--authenticated")
        if args.require_auth:
            check_args.append("--require-auth")

    steps: list[tuple[str, list[str]]] = [
        ("check-apis", check_args),
        ("build-credentials", [f"--max-per-platform={args.max_per_platform}"]),
        ("scan-orders", [f"--max-files={args.max_files}"]),
    ]
    if not args.skip_report:
        report_args = []
        if args.force_report:
            report_args.append("--force")
        steps.append(("daily-report", report_args))

    return run_steps(steps, dry_run=args.dry_run)


def run_steps(steps: Iterable[tuple[str, list[str]]], *, dry_run: bool) -> int:
    for index, (name, step_args) in enumerate(steps, start=1):
        print(f"\n[runbook step {index}/{len(steps)}] {name}")
        code = run_script(name, step_args, dry_run=dry_run)
        if code != 0:
            print(f"logistics_tool: runbook stopped at {name} (exit {code})", file=sys.stderr)
            record_run(f"runbook:{name}", code, {"failed_step": name})
            return code

    record_run("runbook", 0, {"steps": [name for name, _ in steps]})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logistics_tool",
        description="Unified logistics CLI for ScanToolmanus V3 runbooks.",
    )
    parser.add_argument(
        "--load-env",
        action="store_true",
        help=f"Source environment variables from {ENV_FILE.name} before running.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show script availability, env vars, and last runs.")

    for command in SCRIPT_COMMANDS:
        cmd_parser = subparsers.add_parser(command, help=f"Run {SCRIPT_COMMANDS[command]}.")
        cmd_parser.add_argument(
            "script_args",
            nargs=argparse.REMAINDER,
            help="Arguments forwarded to the underlying script.",
        )

    scan_parser = subparsers.add_parser(
        "runbook-scan-pipeline",
        help="Clean accounts -> build credentials -> scan orders.",
    )
    scan_parser.add_argument("--platform", default="", help="Optional platform filter for clean-accounts.")
    scan_parser.add_argument("--max-per-platform", type=int, default=300)
    scan_parser.add_argument("--max-files", type=int, default=200)
    scan_parser.add_argument("--dry-run", action="store_true")

    daily_parser = subparsers.add_parser(
        "runbook-daily-ops",
        help="Check APIs -> build credentials -> scan orders -> optional daily report.",
    )
    daily_parser.add_argument("--authenticated", action="store_true")
    daily_parser.add_argument("--require-auth", action="store_true")
    daily_parser.add_argument("--skip-report", action="store_true")
    daily_parser.add_argument("--force-report", action="store_true")
    daily_parser.add_argument("--max-per-platform", type=int, default=300)
    daily_parser.add_argument("--max-files", type=int, default=200)
    daily_parser.add_argument("--dry-run", action="store_true")

    return parser


def load_env_file(path: Path) -> None:
    if not path.exists():
        print(f"logistics_tool: env file not found: {path}", file=sys.stderr)
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.load_env:
        load_env_file(ENV_FILE)

    if args.command == "status":
        return print_status()

    if args.command == "runbook-scan-pipeline":
        return runbook_scan_pipeline(args)

    if args.command == "runbook-daily-ops":
        return runbook_daily_ops(args)

    script_args = list(getattr(args, "script_args", []))
    if script_args and script_args[0] == "--":
        script_args = script_args[1:]
    return run_script(args.command, script_args)


if __name__ == "__main__":
    raise SystemExit(main())
