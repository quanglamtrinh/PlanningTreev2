#!/usr/bin/env python3
"""Validate Phase 14 full-rollout/rollback env profiles.

Usage:
  python scripts/phase14_full_rollout_preflight.py --mode full --env-file deploy/env/streaming-rollout-full.env.example
  python scripts/phase14_full_rollout_preflight.py --mode rollback --env-file deploy/env/streaming-rollout-rollback.env.example
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _validate_full(values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    if values.get("VITE_THREAD_STREAM_LOW_LATENCY", "").lower() != "true":
        errors.append("VITE_THREAD_STREAM_LOW_LATENCY must be true in full mode")
    if values.get("VITE_THREAD_STREAM_CADENCE_PROFILE", "").lower() not in {"standard", "high"}:
        errors.append("VITE_THREAD_STREAM_CADENCE_PROFILE should be standard/high in full mode")

    be_profile = values.get("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "").lower()
    if be_profile not in {"standard", "high"}:
        errors.append("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE should be standard/high in full mode")

    raw_ms = values.get("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS", "").strip()
    if raw_ms:
        try:
            ms = int(raw_ms)
        except ValueError:
            errors.append("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS must be integer")
        else:
            if ms < 10 or ms > 80:
                errors.append("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS must be in range 10..80")
            if ms > 30:
                errors.append("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS > 30 is not recommended for full smooth rollout")

    return errors


def _validate_rollback(values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    if values.get("VITE_THREAD_STREAM_LOW_LATENCY", "").lower() != "false":
        errors.append("VITE_THREAD_STREAM_LOW_LATENCY must be false in rollback mode")
    if values.get("VITE_THREAD_STREAM_CADENCE_PROFILE", "").lower() != "low":
        errors.append("VITE_THREAD_STREAM_CADENCE_PROFILE must be low in rollback mode")

    if values.get("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "").lower() != "low":
        errors.append("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE must be low in rollback mode")

    raw_ms = values.get("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS", "").strip()
    if raw_ms != "50":
        errors.append("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS should be 50 in rollback mode")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["full", "rollback"], required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.env_file.exists():
        raise SystemExit(f"env file not found: {args.env_file}")

    values = _parse_env_file(args.env_file)
    errors = _validate_full(values) if args.mode == "full" else _validate_rollback(values)

    if errors:
        print("[FAIL] preflight checks:")
        for err in errors:
            print(f" - {err}")
        return 1

    print(f"[PASS] {args.mode} preflight checks for {args.env_file.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
