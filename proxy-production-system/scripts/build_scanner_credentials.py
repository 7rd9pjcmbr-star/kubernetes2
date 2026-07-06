#!/usr/bin/env python3
"""Build scanner credential JSON files from V2 latest account lists."""

import argparse
import json
from pathlib import Path


DEFAULT_LATEST_DIR = "/tmp/v2-cleaned/latest"
DEFAULT_OUTPUT_DIR = "/home/ubuntu/scan-tool-integration/credentials"


def parse_args():
    parser = argparse.ArgumentParser(description="Create scanner credentials from v2 latest files.")
    parser.add_argument("--latest-dir", default=DEFAULT_LATEST_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--platforms",
        default="pancake,sapo,ghn,shopee,tiktokshop",
        help="Comma-separated platform names to include.",
    )
    parser.add_argument(
        "--max-per-platform",
        type=int,
        default=300,
        help="Maximum credentials to emit per platform file.",
    )
    parser.add_argument(
        "--clear-output",
        action="store_true",
        help="Delete existing *.json in output dir before writing.",
    )
    return parser.parse_args()


def parse_line_as_pair(line):
    if ":" not in line:
        return None
    username, password = line.split(":", 1)
    username = username.strip()
    password = password.strip()
    if not username or not password:
        return None
    return username, password


def load_pairs(path, limit):
    pairs = []
    seen = set()
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.strip():
            continue
        parsed = parse_line_as_pair(raw)
        if not parsed:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        pairs.append(parsed)
        if len(pairs) >= limit:
            break
    return pairs


def main():
    args = parse_args()
    latest_dir = Path(args.latest_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.clear_output:
        for file in output_dir.glob("*.json"):
            file.unlink()

    platforms = [item.strip() for item in args.platforms.split(",") if item.strip()]
    written = 0
    summary = {}

    for platform in platforms:
        source = latest_dir / f"v2_bulk_accounts_{platform}.txt"
        if not source.exists():
            summary[platform] = {"source_found": False, "written": 0}
            continue

        pairs = load_pairs(source, args.max_per_platform)
        count = 0
        for idx, (username, password) in enumerate(pairs, start=1):
            payload = {
                "platform": platform,
                "username": username,
                "password": password,
                "source_file": str(source),
            }
            target = output_dir / f"{platform}_{idx:05d}.json"
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            count += 1
            written += 1
        summary[platform] = {"source_found": True, "written": count}

    print(
        json.dumps(
            {
                "latest_dir": str(latest_dir),
                "output_dir": str(output_dir),
                "max_per_platform": args.max_per_platform,
                "total_written": written,
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
