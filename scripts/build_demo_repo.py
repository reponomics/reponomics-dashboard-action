"""Build or verify the generated public demo repository."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
RUNTIME_SCRIPTS_DIR = ROOT / "dashboard_action" / "runtime" / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SCRIPTS_DIR))

from scripts import template_contract, template_provenance  # noqa: E402

import render_dashboard  # noqa: E402
import render_readme  # noqa: E402
import storage  # noqa: E402
import traffic_reporting  # noqa: E402


DATASET_PATH = ROOT / "demo" / "dataset.yml"
TEMPLATE_DIR = ROOT / "dist" / "template"
DEMO_DIR = ROOT / "dist" / "demo"
DEMO_PROVENANCE_PATH = Path(".reponomics/demo-provenance.json")
DEMO_PAGES_WORKFLOW = Path(".github/workflows/publish-demo-dashboard.yml")
DEMO_README_NOTICE = """\
> **Public synthetic demo.** This repository is generated as a Reponomics showcase. The dashboard data is synthetic, the Pages dashboard key is intentionally public, and this README dashboard is published because no private repository metrics are present.

"""


class DemoBuildError(RuntimeError):
    """Raised when the demo repository cannot be built or verified."""


@dataclass(frozen=True)
class RepoSpec:
    full_name: str
    name: str
    index: int
    shape: str
    base_views: int
    clone_ratio: float
    language: str


@contextmanager
def _pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _load_dataset(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DemoBuildError(f"Demo dataset must be a mapping: {path}")
    if payload.get("schema_version") != 1:
        raise DemoBuildError("Demo dataset schema_version must be 1.")
    repos = payload.get("repositories")
    if not isinstance(repos, list) or not repos:
        raise DemoBuildError("Demo dataset must define repositories.")
    return payload


def _repo_specs(dataset: dict[str, Any]) -> list[RepoSpec]:
    owner = str(dataset.get("owner", "")).strip()
    if not owner:
        raise DemoBuildError("Demo dataset owner is required.")
    specs: list[RepoSpec] = []
    for index, raw in enumerate(dataset["repositories"]):
        if not isinstance(raw, dict):
            raise DemoBuildError("Each demo repository entry must be a mapping.")
        name = str(raw.get("name", "")).strip()
        if not name:
            raise DemoBuildError("Each demo repository needs a name.")
        specs.append(
            RepoSpec(
                full_name=f"{owner}/{name}",
                name=name,
                index=index,
                shape=str(raw.get("shape", "steady_growth")),
                base_views=int(raw.get("base_views", 10)),
                clone_ratio=float(raw.get("clone_ratio", 0.1)),
                language=str(raw.get("language", "TypeScript")),
            )
        )
    return specs


def _day_factor(spec: RepoSpec, offset: int, day: date) -> float:
    weekend = 0.68 if day.weekday() >= 5 else 1.0
    wave = 1.0 + ((((offset + 3) * (spec.index + 5)) % 17) - 8) / 70
    growth = 1.0
    if spec.shape == "launch":
        growth += max(0.0, 1.9 - abs(offset - 45) / 6)
        growth += 0.35 if offset > 45 else 0
    elif spec.shape == "docs_growth":
        growth += offset / 140
    elif spec.shape == "clone_heavy":
        growth += 0.15 + offset / 220
    elif spec.shape == "release_spike":
        growth += max(0.0, 1.15 - abs(offset - 63) / 5)
    elif spec.shape == "high_attention":
        growth += max(0.0, 0.8 - abs(offset - 50) / 10)
    elif spec.shape == "business_growth":
        growth += 0.1 + max(0, offset - 30) / 130
    elif spec.shape == "late_riser":
        growth = 0.35 if offset < 65 else 1.0 + (offset - 65) / 18
    elif spec.shape == "declining":
        growth = max(0.25, 1.4 - offset / 95)
    elif spec.shape == "background":
        growth = 0.75 + (spec.index % 3) * 0.08
    elif spec.shape == "long_tail":
        growth = 0.82 + offset / 260
    return max(0.05, weekend * wave * growth)


def _daily_row(spec: RepoSpec, day: date, offset: int) -> dict[str, str]:
    views = max(0, int(spec.base_views * _day_factor(spec, offset, day)))
    uniques = max(1, int(views * (0.52 + (spec.index % 5) * 0.025))) if views else 0
    clones = max(0, int(views * spec.clone_ratio))
    cloners = max(0, int(clones * 0.58))
    ts = day.isoformat()
    return {
        "repo": spec.full_name,
        "ts": ts,
        "views_count": str(views),
        "views_uniques": str(uniques),
        "clones_count": str(clones),
        "clones_uniques": str(cloners),
        "captured_at": f"{ts}T12:00:00Z",
        "source": "reponomics-demo-synthetic",
        "schema_version": storage.SCHEMA_VERSION,
    }


def _aggregate_views(rows: list[dict[str, str]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["repo"]] = totals.get(row["repo"], 0) + int(row["views_count"])
    return totals


def _referrer_rows(specs: list[RepoSpec], daily_rows: list[dict[str, str]], as_of: date) -> list[dict[str, str]]:
    totals = _aggregate_views(daily_rows)
    referrers = [
        ("github.com", 0.34),
        ("google.com", 0.22),
        ("docs.github.com", 0.13),
        ("news.ycombinator.com", 0.08),
        ("reddit.com", 0.06),
        ("stackoverflow.com", 0.05),
        ("npmjs.com", 0.04),
        ("pypi.org", 0.03),
    ]
    rows: list[dict[str, str]] = []
    captured_at = f"{as_of.isoformat()}T12:00:00Z"
    for spec in specs:
        for referrer, ratio in referrers:
            count = max(1, int(totals.get(spec.full_name, 0) * ratio / 5))
            rows.append(
                {
                    "repo": spec.full_name,
                    "captured_at": captured_at,
                    "referrer": referrer,
                    "count": str(count),
                    "uniques": str(max(1, int(count * 0.61))),
                    "schema_version": storage.SCHEMA_VERSION,
                }
            )
    return rows


def _path_rows(specs: list[RepoSpec], daily_rows: list[dict[str, str]], as_of: date) -> list[dict[str, str]]:
    totals = _aggregate_views(daily_rows)
    templates = [
        ("", "Repository overview", 0.40),
        ("/blob/main/README.md", "README", 0.18),
        ("/tree/main/docs", "Documentation", 0.13),
        ("/releases", "Releases", 0.10),
        ("/tree/main/examples", "Examples", 0.08),
        ("/issues", "Issues", 0.05),
        ("/actions/workflows/ci.yml", "Workflow", 0.03),
    ]
    rows: list[dict[str, str]] = []
    captured_at = f"{as_of.isoformat()}T12:00:00Z"
    for spec in specs:
        for suffix, title, ratio in templates:
            count = max(1, int(totals.get(spec.full_name, 0) * ratio / 6))
            rows.append(
                {
                    "repo": spec.full_name,
                    "captured_at": captured_at,
                    "path": f"/{spec.full_name}{suffix}",
                    "title": title,
                    "count": str(count),
                    "uniques": str(max(1, int(count * 0.57))),
                    "schema_version": storage.SCHEMA_VERSION,
                }
            )
    return rows


def _metric_rows(specs: list[RepoSpec], daily_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_repo_day = {
        (row["repo"], row["ts"]): int(row["views_count"])
        for row in daily_rows
    }
    days = sorted({row["ts"] for row in daily_rows})
    rows: list[dict[str, str]] = []
    for spec in specs:
        cumulative = 0
        for day_index, ts in enumerate(days):
            cumulative += by_repo_day.get((spec.full_name, ts), 0)
            stars = 18 + spec.index * 7 + cumulative // 390 + day_index // 20
            watchers = 4 + spec.index * 2 + cumulative // 1200
            forks = 2 + spec.index + cumulative // 1800
            health = 98 - ((spec.index * 7) % 34)
            rows.append(
                {
                    "repo": spec.full_name,
                    "repo_id": str(9000 + spec.index),
                    "node_id": f"R_DEMO_{spec.index}",
                    "ts": ts,
                    "captured_at": f"{ts}T12:00:00Z",
                    "stargazers_count": str(stars),
                    "subscribers_count": str(watchers),
                    "forks_count": str(forks),
                    "open_issues_count": str(1 + spec.index % 6),
                    "size_kb": str(180 + spec.index * 42),
                    "created_at": "2025-01-01T00:00:00Z",
                    "pushed_at": f"{ts}T11:00:00Z",
                    "updated_at": f"{ts}T11:30:00Z",
                    "language": spec.language,
                    "visibility": "public",
                    "default_branch": "main",
                    "has_pages": "True" if spec.name in {"docs", "website", "status-page"} else "False",
                    "has_discussions": "True",
                    "archived": "True" if spec.shape == "declining" else "False",
                    "disabled": "False",
                    "community_health_percentage": str(health),
                    "community_documentation": "README.md",
                    "community_updated_at": f"{ts}T11:30:00Z",
                    "community_content_reports_enabled": "True",
                    "community_has_code_of_conduct": "True",
                    "community_has_contributing": "True" if spec.index % 4 else "False",
                    "community_has_issue_template": "True",
                    "community_has_pull_request_template": "True",
                    "community_has_readme": "True",
                    "community_has_license": "True",
                    "source": "reponomics-demo-synthetic",
                    "schema_version": storage.SCHEMA_VERSION,
                }
            )
    return rows


def _status_rows(daily_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in daily_rows:
        views = int(row["views_count"])
        clones = int(row["clones_count"])
        rows.append(
            {
                "repo": row["repo"],
                "ts": row["ts"],
                "captured_at": row["captured_at"],
                "run_id": "reponomics-demo",
                "status": "ok_with_data" if views or clones else "ok_zero_data",
                "metric_source": "synthetic-demo",
                "traffic_days": "1",
                "referrer_rows": "8",
                "path_rows": "7",
                "error_type": "",
                "error_message": "",
                "schema_version": storage.SCHEMA_VERSION,
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _materialize_data(output_dir: Path, dataset: dict[str, Any], as_of: date) -> None:
    specs = _repo_specs(dataset)
    window_days = int(dataset.get("window_days", 90))
    start = as_of - timedelta(days=window_days - 1)
    daily_rows = [
        _daily_row(spec, start + timedelta(days=offset), offset)
        for offset in range(window_days)
        for spec in specs
    ]
    status_rows = _status_rows(daily_rows)
    data_dir = output_dir / "data"
    _write_csv(data_dir / "traffic-log.csv", daily_rows, storage.LOG_FIELDS)
    _write_csv(data_dir / "traffic-daily.csv", daily_rows, storage.DAILY_FIELDS)
    _write_csv(
        data_dir / "traffic-snapshots.csv",
        [{key: row[key] for key in storage.SNAPSHOT_FIELDS} for row in daily_rows],
        storage.SNAPSHOT_FIELDS,
    )
    _write_csv(data_dir / "traffic-referrers.csv", _referrer_rows(specs, daily_rows, as_of), storage.REFERRER_FIELDS)
    _write_csv(data_dir / "traffic-paths.csv", _path_rows(specs, daily_rows, as_of), storage.PATH_FIELDS)
    _write_csv(data_dir / "repo-metrics.csv", _metric_rows(specs, daily_rows), storage.REPO_METRIC_FIELDS)
    _write_csv(data_dir / "collection-status.csv", status_rows, storage.COLLECTION_STATUS_FIELDS)
    _write_csv(data_dir / "collection-days.csv", traffic_reporting.collection_day_rows(status_rows), storage.COLLECTION_DAY_FIELDS)
    _write_csv(
        data_dir / "traffic-coverage.csv",
        traffic_reporting.traffic_coverage_rows(daily_rows, status_rows),
        storage.TRAFFIC_COVERAGE_FIELDS,
    )
    manifest = storage._default_manifest()
    manifest["created_at"] = f"{start.isoformat()}T12:00:00Z"
    manifest["last_updated"] = f"{as_of.isoformat()}T12:00:00Z"
    manifest["selection_state"] = {
        "auto_seeded_at": f"{start.isoformat()}T12:00:00Z",
        "auto_cutoff_created_at": "2025-01-01T00:00:00Z",
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _write_demo_workflow(output_dir: Path) -> None:
    workflow = """\
name: Publish Demo Dashboard

on:
  push:
    branches: [main]
    paths:
      - docs/**
      - .github/workflows/publish-demo-dashboard.yml
  workflow_dispatch:

permissions: {}

concurrency:
  group: reponomics-demo-pages-${{ github.ref }}
  cancel-in-progress: true

jobs:
  deploy-pages:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3

      - name: Configure GitHub Pages
        uses: actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d # v6
        with:
          enablement: "false"

      - name: Upload demo dashboard artifact
        uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5
        with:
          path: docs

      - name: Deploy demo dashboard
        id: deployment
        uses: actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128 # v5
"""
    path = output_dir / DEMO_PAGES_WORKFLOW
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow, encoding="utf-8")


def _prepend_readme_notice(readme_path: Path) -> None:
    content = readme_path.read_text(encoding="utf-8")
    if content.startswith(DEMO_README_NOTICE):
        return
    readme_path.write_text(DEMO_README_NOTICE + content, encoding="utf-8")


def _write_demo_provenance(output_dir: Path, dataset: dict[str, Any], as_of: date) -> None:
    digest = template_provenance.payload_tree_digest(output_dir)
    payload = {
        "schema_version": 1,
        "demo_repository": "reponomics/reponomics-dashboard-demo",
        "source_repository": _git_value("config", "--get", "remote.origin.url") or "unknown",
        "source_commit": _git_value("rev-parse", "HEAD") or "unknown",
        "template_version": template_contract.load_contract(ROOT).template_version,
        "dataset_revision": dataset["dataset_revision"],
        "as_of": as_of.isoformat(),
        "synthetic_data": True,
        "public_demo_key_sha256": hashlib.sha256(str(dataset["demo_key"]).encode("utf-8")).hexdigest(),
        "payload_digest": {
            "algorithm": "sha256",
            "format": template_provenance.TREE_MANIFEST_FORMAT,
            "digest": digest.digest,
            "file_count": digest.file_count,
            "byte_count": digest.byte_count,
        },
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path = output_dir / DEMO_PROVENANCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_demo_outputs(output_dir: Path, dataset: dict[str, Any]) -> None:
    os.environ["DASHBOARD_KEY"] = str(dataset["demo_key"])
    os.environ["DASHBOARD_ACCESS_MODE"] = "encrypted"
    os.environ["REPONOMICS_MANAGED_DOCS_README_LINK"] = "docs/reponomics/README.md"
    os.environ["REPONOMICS_MANAGED_DOCS_DASHBOARD_LINK"] = "reponomics/README.md"
    os.environ["REPONOMICS_VERSION_STATUS"] = json.dumps(
        {
            "state": "demo",
            "current_version": "demo",
            "current_ref": "reponomics-demo",
            "latest_version": "",
            "latest_url": "",
            "action_repository": "reponomics/reponomics-dashboard-action",
        },
        separators=(",", ":"),
    )
    with _pushd(output_dir):
        render_dashboard.render(
            demo_unlock={
                "label": "Public demo key",
                "key": str(dataset["demo_key"]),
                "note": "This demo uses synthetic data. The key is intentionally public and must not be reused.",
                "button_label": "Unlock demo dashboard",
            }
        )
        render_readme.render()
    _prepend_readme_notice(output_dir / "README.md")


def build_demo(output_dir: Path, dataset_path: Path, as_of: date) -> None:
    if not TEMPLATE_DIR.exists():
        raise DemoBuildError("dist/template does not exist; run make build-template first.")
    dataset = _load_dataset(dataset_path)
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.copytree(TEMPLATE_DIR, output_dir)
    _materialize_data(output_dir, dataset, as_of)
    _write_demo_workflow(output_dir)
    _render_demo_outputs(output_dir, dataset)
    _write_demo_provenance(output_dir, dataset, as_of)
    verify_demo(output_dir, dataset_path)
    print(f"Demo repository written to {output_dir}")


def _assert_csv_header(path: Path, expected: list[str]) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        actual = next(reader, [])
    if actual != expected:
        raise DemoBuildError(f"{path} header mismatch: expected {expected}, got {actual}")


def verify_demo(output_dir: Path, dataset_path: Path = DATASET_PATH) -> None:
    dataset = _load_dataset(dataset_path)
    required = [
        output_dir / "README.md",
        output_dir / "docs/index.html",
        output_dir / "docs/assets/chart.umd.min.js",
        output_dir / DEMO_PAGES_WORKFLOW,
        output_dir / DEMO_PROVENANCE_PATH,
    ]
    for path in required:
        if not path.is_file():
            raise DemoBuildError(f"Missing demo output: {path}")
    for filename, (fields, _date_field) in storage.CSV_REGISTRY.items():
        _assert_csv_header(output_dir / "data" / filename, fields)
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    html = (output_dir / "docs/index.html").read_text(encoding="utf-8")
    workflow = (output_dir / DEMO_PAGES_WORKFLOW).read_text(encoding="utf-8")
    if "Public synthetic demo" not in readme:
        raise DemoBuildError("Demo README is missing synthetic-data disclosure.")
    if "demo-unlock-panel" not in html or "Unlock demo dashboard" not in html:
        raise DemoBuildError("Demo Pages dashboard is missing the public demo unlock panel.")
    if str(dataset["demo_key"]) not in html:
        raise DemoBuildError("Demo Pages dashboard does not expose the configured public demo key.")
    if "COLLECTION_TOKEN" in workflow or "DASHBOARD_SECRET_DO_NOT_REPLACE" in workflow:
        raise DemoBuildError("Demo workflow must not require collection or dashboard secrets.")
    provenance = json.loads((output_dir / DEMO_PROVENANCE_PATH).read_text(encoding="utf-8"))
    if provenance.get("dataset_revision") != dataset.get("dataset_revision"):
        raise DemoBuildError("Demo provenance dataset_revision does not match dataset.yml.")
    if provenance.get("synthetic_data") is not True:
        raise DemoBuildError("Demo provenance must mark synthetic_data=true.")
    print(f"Verified demo repository at {output_dir}")


def _parse_as_of(raw: str | None) -> date:
    if not raw:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise DemoBuildError(f"--as-of must be YYYY-MM-DD, got {raw!r}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEMO_DIR)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--as-of")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        verify_demo(args.output, args.dataset)
    else:
        build_demo(args.output, args.dataset, _parse_as_of(args.as_of))


if __name__ == "__main__":
    try:
        main()
    except DemoBuildError as exc:
        print(f"Demo build error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
