"""Write a browser smoke checklist for staging dashboard validation."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
DEFAULT_OUTPUT = ".tmp/staging-smoke/browser-checklist.md"


def checklist(encrypted_pages_url: str, plain_local_url: str) -> str:
    return f"""# Reponomics Staging Browser Smoke Checklist

Do not paste dashboard keys into this file or into the transcript. Record only pass/fail/incomplete status and non-sensitive observations.

## Encrypted Fresh Pages Dashboard

- [ ] Open encrypted Pages URL: `{encrypted_pages_url}`
- [ ] Confirm the dashboard shell loads without a blank page or visible JavaScript error.
- [ ] Confirm an incorrect key does not unlock the dashboard, if this can be tested without exposing keys.
- [ ] Unlock with the active `DASHBOARD_SECRET_DO_NOT_REPLACE` value.
- [ ] Confirm summary cards, main chart, repo selector, metric selector, and collection calendar render.
- [ ] Focus one repository and confirm the focused chart redraws.
- [ ] Switch to at least one non-traffic growth metric such as stars, watchers, or forks and confirm the chart is not blank.
- [ ] Switch to at least one traffic metric such as views, visitors, clones, or unique clones and confirm the chart is not visibly clipped or truncated.
- [ ] Select multiple repositories for comparison and confirm the comparison state is understandable.
- [ ] Confirm collection calendar statuses are plausible for the latest retained data.
- [ ] After key rotation and republish, confirm the dashboard unlocks with the promoted new key.

## Plain History Local HTML Artifact

- [ ] Download `html-dashboard-plain` from the latest plain-history collect/publish run.
- [ ] Serve the artifact locally, for example from `.tmp/staging-smoke/plain-html`.
- [ ] Open local URL: `{plain_local_url}`
- [ ] Confirm the plain dashboard renders without a hosted Pages deployment.
- [ ] Confirm summary cards, main chart, repo selector, metric selector, and collection calendar render.
- [ ] Switch to at least one non-traffic growth metric and one traffic metric.
- [ ] Confirm README dashboard values are coherent with the rendered HTML dashboard at a smoke-test level.

## Result

- Status: incomplete
- Browser/tool used:
- Encrypted Pages notes:
- Plain artifact notes:
- Follow-up:
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encrypted-pages-url", default="<encrypted-pages-url>")
    parser.add_argument("--plain-local-url", default="http://localhost:8765")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(checklist(args.encrypted_pages_url, args.plain_local_url), encoding="utf-8")
    print(f"Wrote browser smoke checklist: {path}")


if __name__ == "__main__":
    main()
