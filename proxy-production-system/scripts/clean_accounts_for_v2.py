#!/usr/bin/env python3
"""V2 cleaner: only dedupe lines, keep original format untouched."""

import argparse
import glob
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_UPLOADS_DIR = "/home/ubuntu/.cursor/projects/workspace/uploads"
DEFAULT_OUTPUT_DIR = "/tmp/v2-cleaned"
DEFAULT_STATE_FILE = "/tmp/v2-cleaned/state.json"
SUPPORTED_PLATFORMS = {"sapo", "pancake", "shopee", "tiktokshop", "ghn", "unknown"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prepare V2 bulk-account input by removing duplicate lines only."
    )
    parser.add_argument("--input-file", default="", help="Input txt file.")
    parser.add_argument("--auto", action="store_true", help="Pick newest txt from uploads dir.")
    parser.add_argument("--uploads-dir", default=DEFAULT_UPLOADS_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    parser.add_argument(
        "--platform",
        default="",
        help="Expected platform (sapo/pancake/shopee/tiktokshop/ghn). "
        "If omitted, infer from filename.",
    )
    parser.add_argument(
        "--dedupe-mode",
        choices=["exact-line"],
        default="exact-line",
        help="Current V2-safe mode: remove exact duplicate lines only.",
    )
    parser.add_argument(
        "--v2-command",
        default="",
        help="Optional command after cleaning. Receives env V2_BULK_ACCOUNTS_FILE and V2_BULK_PLATFORM.",
    )
    parser.add_argument("--force", action="store_true", help="Process even if unchanged in auto mode.")
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


def infer_platform_from_filename(path):
    name = path.name.lower()
    if "sapo" in name:
        return "sapo"
    if "pancake" in name:
        return "pancake"
    if "shopee" in name:
        return "shopee"
    if "tiktok" in name:
        return "tiktokshop"
    if "ghn" in name:
        return "ghn"
    return "unknown"


def detect_content_platforms(source_file):
    text = source_file.read_text(encoding="utf-8", errors="ignore")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    detected = set()

    # Cookie Netscape format usually has tab-separated fields and domain in first column.
    cookie_like = sum("\t" in ln for ln in lines) >= max(1, len(lines) // 2)
    if not cookie_like:
        return detected

    for line in lines:
        domain = line.split("\t", 1)[0].lower().strip()
        if not domain:
            continue
        if "pancake" in domain or "pages.fm" in domain:
            detected.add("pancake")
        if "sapo" in domain:
            detected.add("sapo")
        if "shopee" in domain:
            detected.add("shopee")
        if "tiktok" in domain:
            detected.add("tiktokshop")
        if "ghn.vn" in domain or "giaohangtietkiem" in domain or ".ghtk.vn" in domain:
            detected.add("ghn")
    return detected


def resolve_platform(expected, source_file):
    inferred = infer_platform_from_filename(source_file)
    content_platforms = detect_content_platforms(source_file)
    if expected:
        platform = expected.strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {expected}")
        if inferred != "unknown" and platform != inferred:
            raise ValueError(
                f"Platform mismatch: expected={platform}, inferred_from_file={inferred}, file={source_file.name}"
            )
        if content_platforms and platform not in content_platforms:
            raise ValueError(
                f"Platform mismatch by content: expected={platform}, "
                f"detected_content_platforms={sorted(content_platforms)}"
            )
        return platform, inferred, sorted(content_platforms)
    auto_platform = inferred if inferred != "unknown" else (
        sorted(content_platforms)[0] if len(content_platforms) == 1 else "unknown"
    )
    return auto_platform, inferred, sorted(content_platforms)


def dedupe_exact_lines(source_file):
    raw = source_file.read_text(encoding="utf-8", errors="ignore")
    lines = raw.splitlines()
    kept = []
    seen = set()
    duplicates = 0
    for line in lines:
        # Keep original line as-is; dedupe by exact byte-equivalent text line.
        if line in seen:
            duplicates += 1
            continue
        seen.add(line)
        kept.append(line)
    return kept, {"total_lines": len(lines), "duplicate_lines_removed": duplicates}


def write_output(kept_lines, output_dir, platform):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_file = out_dir / f"v2_bulk_accounts_{platform}_{timestamp}.txt"
    output_file.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
    return output_file


def maybe_run_v2(command, output_file, platform):
    if not command:
        return {"ran": False}
    env = os.environ.copy()
    env["V2_BULK_ACCOUNTS_FILE"] = str(output_file)
    env["V2_BULK_PLATFORM"] = platform
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, env=env)
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
    platform, inferred_platform, detected_content_platforms = resolve_platform(args.platform, source_file)

    state = load_state(args.state_file)
    if args.auto and not args.force:
        if (
            state.get("last_source_file") == str(source_file)
            and state.get("last_source_sha256") == source_sha
            and state.get("last_platform") == platform
        ):
            print(f"No new input to process: {source_file}")
            return 0

    kept_lines, dedupe_stats = dedupe_exact_lines(source_file)
    output_file = write_output(kept_lines, args.output_dir, platform)
    command_result = maybe_run_v2(args.v2_command, output_file, platform)

    report = {
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source_file),
        "source_sha256": source_sha,
        "platform": platform,
        "inferred_platform": inferred_platform,
        "detected_content_platforms": detected_content_platforms,
        "dedupe_mode": args.dedupe_mode,
        "dedupe_stats": dedupe_stats,
        "final_lines": len(kept_lines),
        "output_file": str(output_file),
        "v2_command_result": command_result,
    }

    save_state(
        args.state_file,
        {
            "last_processed_at_utc": report["processed_at_utc"],
            "last_source_file": report["source_file"],
            "last_source_sha256": report["source_sha256"],
            "last_platform": report["platform"],
            "last_output_file": report["output_file"],
            "last_final_lines": report["final_lines"],
        },
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if command_result.get("ran") and command_result.get("exit_code", 0) != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
