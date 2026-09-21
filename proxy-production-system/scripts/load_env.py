#!/usr/bin/env python3
"""Load repo-root .env safely (quoted values, pipes in PROXY_POOL)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"


def find_env_file(explicit: Optional[str] = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Env file not found: {path}")
        return path.resolve()
    path = DEFAULT_ENV_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}. Create it locally (gitignored) — see README § Environment."
        )
    return path


def parse_dotenv(content: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


def load_env(path: Optional[str] = None, *, apply: bool = False) -> Dict[str, str]:
    env_path = find_env_file(path)
    parsed = parse_dotenv(env_path.read_text(encoding="utf-8", errors="replace"))
    if apply:
        for key, value in parsed.items():
            os.environ[key] = value
    parsed["__ENV_FILE__"] = str(env_path)
    return parsed


def rotating_proxy_url(env: Dict[str, str]) -> str:
    direct = env.get("ROTATING_PROXY_URL", "").strip()
    if direct:
        return direct
    pool = env.get("PROXY_POOL", "").strip()
    if not pool:
        return ""
    first = pool.split(",")[0].strip()
    if "|" in first:
        first = first.split("|", 1)[0].strip()
    return first


def cmd_check(env: Dict[str, str]) -> int:
    if not rotating_proxy_url(env):
        print(
            "Missing residential proxy: set ROTATING_PROXY_URL or PROXY_POOL in .env",
            file=sys.stderr,
        )
        return 1
    print(env["__ENV_FILE__"])
    print("ok")
    return 0


def cmd_print_shell(env: Dict[str, str]) -> None:
    for key, value in sorted(env.items()):
        if key == "__ENV_FILE__":
            continue
        escaped = value.replace("'", "'\"'\"'")
        print(f"export {key}='{escaped}'")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load wrapped .env for Python and shell.")
    parser.add_argument("--env-file", default="", help="Path to .env (default: repo root .env).")
    parser.add_argument("--apply", action="store_true", help="Apply variables to os.environ (in-process).")
    parser.add_argument("--check", action="store_true", help="Verify proxy-related keys exist.")
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print export statements for: eval \"$(python3 scripts/load_env.py --shell)\"",
    )
    args = parser.parse_args()

    try:
        env = load_env(args.env_file or None, apply=args.apply)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.check:
        return cmd_check(env)
    if args.shell:
        cmd_print_shell(env)
        return 0

    if args.apply:
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
