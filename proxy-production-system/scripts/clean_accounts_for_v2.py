#!/usr/bin/env python3
"""Clean account dump and prepare sanitized input for V2 automation."""

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


NULLISH_PASSWORDS = {"null", "none", "empty", "n/a", "-"}
DEFAULT_UPLOADS_DIR = "/home/ubuntu/.cursor/projects/workspace/uploads"
DEFAULT_OUTPUT_DIR = "/tmp/v2-cleaned"
DEFAULT_STATE_FILE = "/tmp/v2-cleaned/state.json"


@dataclass
class Entry:
    username: str
    password: str
    source_line: int


def parse_args():
    parser = argparse.ArgumentParser(description="Clean account list and export V2-ready files.")
    parser.add_argument("--input-file", default="", help="Input text file (user:password per line).")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-select newest .txt file from uploads dir and process only new input.",
    )
    parser.add_argument("--uploads-dir", default=DEFAULT_UPLOADS_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    parser.add_argument(
        "--drop-weak-passwords",
        action="store_true",
        help="Drop entries with weak passwords (score < 3).",
    )
    parser.add_argument(
        "--v2-command",
        default="",
        help="Optional command to run after successful cleaning, e.g. '/home/ubuntu/run_v2.sh'.",
    )
    parser.add_argument("--force", action="store_true", help="Process even if source file unchanged in auto mode.")
    return parser.parse_args()


def choose_input_file(args):
    if args.input_file:
        path = Path(args.input_file)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        return path

    if not args.auto:
        raise ValueError("Provide --input-file or use --auto.")

    pattern = str(Path(args.uploads_dir) / "*.txt")
    candidates = [Path(path) for path in glob.glob(pattern)]
    if not candidates:
        raise FileNotFoundError(f"No .txt file found under uploads dir: {args.uploads_dir}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(path):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def username_type(username):
    if "@" in username:
        return "email"
    if re.fullmatch(r"\d{8,15}", username):
        return "phone_or_numeric"
    return "other"


def password_score(password):
    score = 0
    if len(password) >= 8:
        score += 1
    if re.search(r"[a-z]", password):
        score += 1
    if re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"\d", password):
        score += 1
    if re.search(r"[^A-Za-z0-9]", password):
        score += 1
    return score


def strength_label(score):
    if score <= 1:
        return "very_weak"
    if score == 2:
        return "weak"
    if score == 3:
        return "medium"
    if score == 4:
        return "strong"
    return "very_strong"


def parse_entries(path):
    raw_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    stats = {
        "total_lines": 0,
        "malformed_no_colon": 0,
        "empty_username": 0,
        "empty_password": 0,
        "nullish_password": 0,
    }
    entries = []

    for idx, line in enumerate(raw_lines, start=1):
        text = line.strip()
        if not text:
            continue
        stats["total_lines"] += 1
        if ":" not in text:
            stats["malformed_no_colon"] += 1
            continue
        username, password = text.split(":", 1)
        username = username.strip()
        password = password.strip()
        if not username:
            stats["empty_username"] += 1
            continue
        if not password:
            stats["empty_password"] += 1
            continue
        if password.lower() in NULLISH_PASSWORDS:
            stats["nullish_password"] += 1
            continue
        entries.append(Entry(username=username, password=password, source_line=idx))
    return entries, stats


def dedupe_entries(entries):
    dedup_exact = {}
    for entry in entries:
        dedup_exact[(entry.username, entry.password)] = entry
    exact_values = list(dedup_exact.values())

    best_by_user = {}
    replaced = 0
    for entry in exact_values:
        current = best_by_user.get(entry.username)
        if current is None:
            best_by_user[entry.username] = entry
            continue
        current_score = password_score(current.password)
        new_score = password_score(entry.password)
        should_replace = new_score > current_score or (
            new_score == current_score and len(entry.password) > len(current.password)
        )
        if should_replace:
            best_by_user[entry.username] = entry
            replaced += 1
    return list(best_by_user.values()), {"exact_dedup_removed": len(entries) - len(exact_values), "user_dedup_replaced": replaced}


def export_outputs(entries, output_dir):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"accounts_v2_cleaned_{timestamp}.csv"
    json_path = out_dir / f"accounts_v2_cleaned_{timestamp}.json"

    rows = []
    for entry in entries:
        score = password_score(entry.password)
        rows.append(
            {
                "username": entry.username,
                "password": entry.password,
                "username_type": username_type(entry.username),
                "password_score": score,
                "password_strength": strength_label(score),
                "source_line": entry.source_line,
            }
        )

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "username",
                "password",
                "username_type",
                "password_score",
                "password_strength",
                "source_line",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path, rows


def maybe_run_v2_command(command):
    if not command:
        return {"ran": False}
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    return {
        "ran": True,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-1000:],
        "stderr": proc.stderr[-1000:],
    }


def main():
    args = parse_args()
    source_file = choose_input_file(args)
    source_sha = sha256_file(source_file)
    source_mtime = source_file.stat().st_mtime

    state = load_state(args.state_file)
    if args.auto and not args.force:
        if (
            state.get("last_source_file") == str(source_file)
            and state.get("last_source_sha256") == source_sha
        ):
            print(f"No new input to process: {source_file}")
            return 0

    parsed_entries, parse_stats = parse_entries(source_file)
    cleaned_entries, dedupe_stats = dedupe_entries(parsed_entries)

    if args.drop_weak_passwords:
        cleaned_entries = [entry for entry in cleaned_entries if password_score(entry.password) >= 3]

    csv_path, json_path, rows = export_outputs(cleaned_entries, args.output_dir)
    command_result = maybe_run_v2_command(args.v2_command)

    report = {
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source_file),
        "source_sha256": source_sha,
        "source_mtime": source_mtime,
        "parse_stats": parse_stats,
        "dedupe_stats": dedupe_stats,
        "drop_weak_passwords": args.drop_weak_passwords,
        "final_entries": len(rows),
        "output_csv": str(csv_path),
        "output_json": str(json_path),
        "v2_command_result": command_result,
    }

    save_state(
        args.state_file,
        {
            "last_processed_at_utc": report["processed_at_utc"],
            "last_source_file": report["source_file"],
            "last_source_sha256": report["source_sha256"],
            "last_source_mtime": report["source_mtime"],
            "last_output_csv": report["output_csv"],
            "last_output_json": report["output_json"],
            "last_final_entries": report["final_entries"],
        },
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if command_result.get("ran") and command_result.get("exit_code", 0) != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
