#!/usr/bin/env python3
"""Resolve and update generated-repository auto-doctor cadence state."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MARKER = Path(".reponomics") / "auto-doctor.json"
MIN_INTERVAL_DAYS = 0
MAX_INTERVAL_DAYS = 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_interval(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"auto_doctor_every_n_days must be an integer, got {raw!r}.") from exc
    if value < MIN_INTERVAL_DAYS or value > MAX_INTERVAL_DAYS:
        raise ValueError(
            "auto_doctor_every_n_days must be between "
            + f"{MIN_INTERVAL_DAYS} and {MAX_INTERVAL_DAYS}."
        )
    return value


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_marker(marker_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")
    print(f"{name}: {value}")


def _check(interval_days: int, marker_path: Path, now: datetime) -> int:
    if interval_days == 0:
        due = False
        reason = "disabled"
    elif not marker_path.exists():
        due = True
        reason = "no marker found"
    else:
        marker = _load_marker(marker_path)
        last_success = _parse_timestamp(marker.get("last_successful_at"))
        if last_success is None:
            due = True
            reason = "marker was unreadable"
        else:
            elapsed_days = (now.date() - last_success.date()).days
            due = elapsed_days >= interval_days
            reason = f"{elapsed_days} day(s) since last successful auto-doctor"

    _write_output("due", str(due).lower())
    _write_output("reason", reason)
    _write_output("checked-at", now.isoformat().replace("+00:00", "Z"))
    return 0


def _mark(interval_days: int, marker_path: Path, run_id: str, now: datetime) -> int:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "last_successful_at": now.isoformat().replace("+00:00", "Z"),
        "last_successful_run_id": run_id,
        "auto_doctor_every_n_days": interval_days,
    }
    marker_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_output("marker-path", marker_path.as_posix())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-days", required=True)
    parser.add_argument("--marker", default=DEFAULT_MARKER.as_posix())
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--now", default="")
    parser.add_argument("command", choices={"check", "mark"})
    args = parser.parse_args()

    try:
        interval_days = _parse_interval(args.interval_days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    now = _parse_timestamp(args.now) if args.now else _utc_now()
    if now is None:
        print(f"--now must be an ISO timestamp, got {args.now!r}.", file=sys.stderr)
        return 1

    marker_path = Path(args.marker)
    if args.command == "check":
        return _check(interval_days, marker_path, now)

    if not args.run_id.strip():
        print("--run-id or GITHUB_RUN_ID is required for mark.", file=sys.stderr)
        return 1
    return _mark(interval_days, marker_path, args.run_id.strip(), now)


if __name__ == "__main__":
    raise SystemExit(main())
