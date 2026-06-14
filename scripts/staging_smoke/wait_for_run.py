"""Wait for a recently dispatched GitHub Actions workflow run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root


ROOT = find_repo_root(Path(__file__))


class WaitRunError(RuntimeError):
    """Raised when a dispatched workflow run cannot be found or did not pass."""


def _delay_seconds() -> float:
    raw = os.environ.get("STAGING_SMOKE_GH_DELAY_SECONDS", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _poll_seconds() -> float:
    raw = os.environ.get("STAGING_SMOKE_WAIT_POLL_SECONDS", "10")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 10.0


GH_DELAY_SECONDS = _delay_seconds()


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _run_json(args: list[str]) -> Any:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if args and args[0] == "gh" and GH_DELAY_SECONDS:
        time.sleep(GH_DELAY_SECONDS)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WaitRunError(f"{' '.join(args)} failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WaitRunError(f"{' '.join(args)} did not return valid JSON") from exc


def _list_runs(repo: str, workflow: str, branch: str) -> list[dict[str, Any]]:
    payload = _run_json(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            branch,
            "--limit",
            "20",
            "--json",
            "databaseId,status,conclusion,createdAt,url,event,headBranch",
        ]
    )
    return payload if isinstance(payload, list) else []


def _run_id(run: dict[str, Any]) -> int | None:
    raw = run.get("databaseId")
    return raw if isinstance(raw, int) else None


def _created_at(run: dict[str, Any]) -> datetime | None:
    raw = run.get("createdAt")
    if not isinstance(raw, str):
        return None
    try:
        return _parse_timestamp(raw)
    except ValueError:
        return None


def select_run(
    runs: list[dict[str, Any]],
    *,
    created_after: datetime,
    event: str,
) -> dict[str, Any] | None:
    candidates = []
    for run in runs:
        created_at = _created_at(run)
        if created_at is None or created_at < created_after:
            continue
        if run.get("event") != event:
            continue
        if _run_id(run) is None:
            continue
        candidates.append((created_at, run))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def wait_for_run(args: argparse.Namespace) -> dict[str, Any]:
    created_after = _parse_timestamp(args.created_after)
    deadline = time.monotonic() + args.timeout_seconds
    selected_id: int | None = None
    selected_url = ""

    while time.monotonic() <= deadline:
        runs = _list_runs(args.repo, args.workflow, args.branch)
        if selected_id is None:
            selected = select_run(runs, created_after=created_after, event=args.event)
            if selected is not None:
                selected_id = _run_id(selected)
                selected_url = str(selected.get("url") or "")
                print(f"Watching workflow run {selected_id}: {selected_url}", flush=True)

        if selected_id is not None:
            current = next((run for run in runs if _run_id(run) == selected_id), None)
            if current is not None:
                status = current.get("status")
                conclusion = current.get("conclusion")
                print(
                    f"Run {selected_id} status={status!r} conclusion={conclusion!r}",
                    flush=True,
                )
                if status == "completed":
                    if conclusion == "success":
                        return current
                    raise WaitRunError(
                        f"Workflow run {selected_id} did not succeed: {conclusion!r} {selected_url}"
                    )

        time.sleep(args.poll_seconds)

    raise WaitRunError(
        " ".join(
            [
                "Timed out waiting for workflow run",
                f"repo={args.repo!r}",
                f"workflow={args.workflow!r}",
                f"branch={args.branch!r}",
                f"created_after={args.created_after!r}",
            ]
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--event", default="workflow_dispatch")
    parser.add_argument("--created-after", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--poll-seconds", type=float, default=_poll_seconds())
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    run = wait_for_run(args)
    print(f"Workflow run passed: {run.get('url')}")


if __name__ == "__main__":
    try:
        main()
    except WaitRunError as exc:
        print(f"Workflow wait error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
