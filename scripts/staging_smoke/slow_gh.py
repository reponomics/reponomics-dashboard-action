"""Run gh, then sleep briefly to avoid rapid GitHub API bursts."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def _delay_seconds() -> float:
    raw = os.environ.get("STAGING_SMOKE_GH_DELAY_SECONDS", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def main() -> None:
    if len(sys.argv) == 1:
        print("usage: slow_gh.py <gh-args...>", file=sys.stderr)
        raise SystemExit(2)

    result = subprocess.run(["gh", *sys.argv[1:]], check=False)
    delay = _delay_seconds()
    if delay:
        time.sleep(delay)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
