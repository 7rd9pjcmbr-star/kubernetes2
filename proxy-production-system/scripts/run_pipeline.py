#!/usr/bin/env python3
"""Sequential master run: clean → credentials → scanner → daily Telegram report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_PATH = "/tmp/v2-pipeline/last_run.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the V2/scanner pipeline in order: "
            "clean accounts → build credentials → scan → daily Telegram."
        )
    )
    parser.add_argument(
        "--steps",
        default="clean,credentials,scanner,telegram",
        help="Comma-separated steps to run (default: all).",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue remaining steps even if one fails.",
    )
    parser.add_argument(
        "--require-telegram-env",
        action="store_true",
        help="Fail (instead of skip) when PANCAKE/TELEGRAM env vars are missing.",
    )
    parser.add_argument("--uploads-dir", default="")
    parser.add_argument("--input-file", default="")
    parser.add_argument("--force-clean", action="store_true", help="Pass --force to cleaner.")
    parser.add_argument(
        "--platforms",
        default="pancake,sapo,ghn,shopee,tiktokshop",
        help="Platforms for credential build.",
    )
    parser.add_argument("--max-scanner-files", type=int, default=200)
    parser.add_argument("--force-telegram", action="store_true", help="Pass --force to daily report.")
    parser.add_argument("--report-file", default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands only; do not execute.",
    )
    return parser.parse_args()


def step_enabled(selected, name):
    return name in selected


def run_step(name, cmd, dry_run=False):
    started = datetime.now(timezone.utc)
    entry = {
        "step": name,
        "command": cmd,
        "started_at_utc": started.isoformat(),
        "exit_code": None,
        "duration_seconds": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "skipped": False,
        "error": "",
    }
    print(f"\n=== [{name}] ===", flush=True)
    print("$ " + " ".join(cmd), flush=True)

    if dry_run:
        entry["exit_code"] = 0
        entry["duration_seconds"] = 0.0
        entry["skipped"] = True
        entry["error"] = "dry_run"
        print("(dry-run) skipped execution", flush=True)
        return entry

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        entry["exit_code"] = 127
        entry["duration_seconds"] = round(time.monotonic() - t0, 3)
        entry["error"] = f"{exc.__class__.__name__}: {exc}"
        print(entry["error"], file=sys.stderr, flush=True)
        return entry

    entry["exit_code"] = proc.returncode
    entry["duration_seconds"] = round(time.monotonic() - t0, 3)
    entry["stdout_tail"] = (proc.stdout or "")[-4000:]
    entry["stderr_tail"] = (proc.stderr or "")[-2000:]

    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr, flush=True)
    print(f"[{name}] exit={proc.returncode} duration={entry['duration_seconds']}s", flush=True)
    return entry


def telegram_env_ready():
    missing = []
    has_pancake = any(
        os.getenv(key, "").strip()
        for key in (
            "PANCAKE_POS_API_KEY",
            "PANCAKE_POS_ACCESS_TOKEN",
            "PANCAKE_POS_TOKEN",
            "PANCAKE_TOKEN",
        )
    )
    if not has_pancake:
        missing.append("PANCAKE_POS_API_KEY|PANCAKE_POS_ACCESS_TOKEN")
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if not os.getenv(key, "").strip():
            missing.append(key)
    return missing


def build_commands(args):
    py = sys.executable
    clean_cmd = [
        py,
        str(SCRIPT_DIR / "clean_accounts_for_v2.py"),
        "--split-by-platform",
        "--exclude-unknown",
    ]
    if args.input_file:
        clean_cmd.extend(["--input-file", args.input_file])
    else:
        clean_cmd.append("--auto")
    if args.uploads_dir:
        clean_cmd.extend(["--uploads-dir", args.uploads_dir])
    if args.force_clean:
        clean_cmd.append("--force")

    credentials_cmd = [
        py,
        str(SCRIPT_DIR / "build_scanner_credentials.py"),
        "--clear-output",
        "--platforms",
        args.platforms,
    ]

    scanner_cmd = [
        py,
        str(SCRIPT_DIR / "order_scanner_runner.py"),
        "--max-files",
        str(args.max_scanner_files),
    ]

    telegram_cmd = [py, str(SCRIPT_DIR / "daily_pancake_orders_to_telegram.py")]
    if args.force_telegram:
        telegram_cmd.append("--force")

    return {
        "clean": clean_cmd,
        "credentials": credentials_cmd,
        "scanner": scanner_cmd,
        "telegram": telegram_cmd,
    }


def main():
    args = parse_args()
    selected = [item.strip().lower() for item in args.steps.split(",") if item.strip()]
    valid = {"clean", "credentials", "scanner", "telegram"}
    unknown = [item for item in selected if item not in valid]
    if unknown:
        print(f"Unknown steps: {', '.join(unknown)}. Valid: {', '.join(sorted(valid))}", file=sys.stderr)
        return 2
    if not selected:
        print("No steps selected.", file=sys.stderr)
        return 2

    commands = build_commands(args)
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "finished_at_utc": "",
        "steps_requested": selected,
        "continue_on_error": args.continue_on_error,
        "dry_run": args.dry_run,
        "results": [],
        "overall_exit_code": 0,
    }

    for name in selected:
        if name == "telegram":
            missing = telegram_env_ready()
            if missing and not args.require_telegram_env:
                skipped = {
                    "step": "telegram",
                    "command": commands["telegram"],
                    "started_at_utc": datetime.now(timezone.utc).isoformat(),
                    "exit_code": 0,
                    "duration_seconds": 0.0,
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "skipped": True,
                    "error": "missing_env:" + ",".join(missing),
                }
                print("\n=== [telegram] ===", flush=True)
                print(f"skipped: missing env {', '.join(missing)}", flush=True)
                report["results"].append(skipped)
                continue
            if missing and args.require_telegram_env:
                failed = {
                    "step": "telegram",
                    "command": commands["telegram"],
                    "started_at_utc": datetime.now(timezone.utc).isoformat(),
                    "exit_code": 2,
                    "duration_seconds": 0.0,
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "skipped": False,
                    "error": "missing_env:" + ",".join(missing),
                }
                print("\n=== [telegram] ===", flush=True)
                print(f"failed: missing env {', '.join(missing)}", file=sys.stderr, flush=True)
                report["results"].append(failed)
                report["overall_exit_code"] = 2
                if not args.continue_on_error:
                    break
                continue

        entry = run_step(name, commands[name], dry_run=args.dry_run)
        report["results"].append(entry)
        if entry["exit_code"] not in (0, None):
            report["overall_exit_code"] = entry["exit_code"] or 1
            if not args.continue_on_error:
                break

    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nPipeline report: {report_path}", flush=True)
    print(json.dumps({"overall_exit_code": report["overall_exit_code"], "report_file": str(report_path)}, indent=2))
    return report["overall_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
