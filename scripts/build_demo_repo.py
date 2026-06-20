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

import storage  # noqa: E402
import traffic_reporting  # noqa: E402
import crypto_artifact  # noqa: E402


DATASET_PATH = ROOT / "demo" / "dataset.yml"
TEMPLATE_DIR = ROOT / "dist" / "template"
DEMO_DIR = ROOT / "dist" / "demo"
DEMO_SEED_DIR = ROOT / "dist" / "demo-seed"
DEMO_PROVENANCE_PATH = Path(".reponomics/demo-provenance.json")
DEMO_TARGET_WORKFLOW = Path(".github/workflows/seed-and-publish-demo-dashboard.yml")
DEMO_PAGES_WORKFLOW = DEMO_TARGET_WORKFLOW
DEMO_SEED_ARTIFACT_NAME = "generated-demo-dashboard-data"
DEMO_SEED_DASHBOARD_DATA_ARTIFACT_NAME = "dashboard-data"
DEMO_SEED_ARTIFACT_PATH = Path("dashboard-data.enc")
DEMO_EXCLUDED_PAYLOAD_PATHS = frozenset({DEMO_PROVENANCE_PATH.as_posix()})
DEMO_README_NOTICE = """\
> **Public synthetic demo.** This repository is generated as a Reponomics showcase. The dashboard data is synthetic, and the Pages dashboard key is intentionally public.

"""
DEMO_OWNER = "reponomics-demo"
DEMO_REPO_PREFIX = "demo-"
DEMO_DATASET_DENYLIST = ("reponomics-labs", "internal", "customer", "stealth")


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


@contextmanager
def _temporary_env(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
    _validate_public_demo_names(payload)
    return payload


def _validate_public_demo_names(dataset: dict[str, Any]) -> None:
    owner = str(dataset.get("owner", "")).strip()
    if owner != DEMO_OWNER:
        raise DemoBuildError(f"Demo dataset owner must be {DEMO_OWNER!r}.")
    featured = dataset.get("featured_repositories")
    if not isinstance(featured, list):
        raise DemoBuildError("Demo dataset must define featured_repositories.")
    for item in featured:
        if not isinstance(item, str) or not item.startswith(f"{DEMO_OWNER}/{DEMO_REPO_PREFIX}"):
            raise DemoBuildError("Demo featured repositories must use reponomics-demo/demo-* names.")
    for raw in dataset["repositories"]:
        if not isinstance(raw, dict):
            raise DemoBuildError("Each demo repository entry must be a mapping.")
        name = str(raw.get("name", "")).strip()
        if not name.startswith(DEMO_REPO_PREFIX):
            raise DemoBuildError("Demo repository names must start with demo-.")
    serialized = json.dumps(dataset, sort_keys=True).lower()
    for term in DEMO_DATASET_DENYLIST:
        if term in serialized:
            raise DemoBuildError(f"Demo dataset contains brand-risk term: {term}")


def _assert_no_demo_brand_risk_terms(output_dir: Path) -> None:
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        for term in DEMO_DATASET_DENYLIST:
            if term in content:
                relative = path.relative_to(output_dir)
                raise DemoBuildError(f"Generated demo output contains brand-risk term {term}: {relative}")


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
                    "has_pages": (
                        "True" if spec.name in {"demo-docs", "demo-website", "demo-status-page"} else "False"
                    ),
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


def _write_demo_workflow(output_dir: Path, demo_key: str = "public-demo-key") -> None:
    workflow = """\
name: Seed And Publish Demo Dashboard

on:
  workflow_dispatch:
    inputs:
      source_run_id:
        description: "Source reponomics-dashboard-action workflow run ID containing the demo seed artifact"
        required: true
        type: string
      source_repository:
        description: "Source repository that produced the demo seed artifact"
        required: true
        type: string
        default: reponomics/reponomics-dashboard-action

permissions: {}

concurrency:
  group: reponomics-demo-seed-publish-${{ github.ref }}
  cancel-in-progress: true

jobs:
  seed-and-publish:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      actions: write
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3

      - name: Download encrypted demo dashboard data seed
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: generated-demo-dashboard-data
          path: .dashboard-data-artifact
          repository: ${{ inputs.source_repository }}
          run-id: ${{ inputs.source_run_id }}
          github-token: ${{ github.token }}

      - name: Validate encrypted demo dashboard data seed
        shell: bash
        run: |
          set -euo pipefail
          test -s .dashboard-data-artifact/dashboard-data.enc
          python - <<'PY'
          import json
          from pathlib import Path

          payload = json.loads(Path(".dashboard-data-artifact/dashboard-data.enc").read_text())
          required = {"version", "created_at", "kdf", "iterations", "algorithm", "salt", "iv", "ciphertext"}
          missing = sorted(required - set(payload))
          if missing:
              raise SystemExit(f"encrypted seed is missing keys: {missing}")
          if payload["version"] != 1 or payload["algorithm"] != "AES-256-GCM":
              raise SystemExit("encrypted seed uses an unsupported format")
          PY

      - name: Store demo dashboard data artifact
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: dashboard-data
          path: .dashboard-data-artifact/dashboard-data.enc
          if-no-files-found: error
          retention-days: 90
          overwrite: true

      - name: Publish demo dashboard
        uses: ./.github/actions/reponomics
        env:
          DEMO_DASHBOARD_KEY: __DEMO_DASHBOARD_KEY_JSON__
        with:
          mode: publish
          artifact-run-id: ${{ github.run_id }}
          github-token: ${{ github.token }}
          dashboard-secret: ${{ env.DEMO_DASHBOARD_KEY }}
          data-mode: encrypted
          retention-days: "90"
          publish-pages: "true"
          generate-readme: "false"
""".replace("__DEMO_DASHBOARD_KEY_JSON__", json.dumps(demo_key))
    path = output_dir / DEMO_TARGET_WORKFLOW
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow, encoding="utf-8")


def _prepend_readme_notice(readme_path: Path) -> None:
    content = readme_path.read_text(encoding="utf-8")
    if content.startswith(DEMO_README_NOTICE):
        return
    readme_path.write_text(DEMO_README_NOTICE + content, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_encrypted_seed_artifact(data_dir: Path, seed_output_dir: Path, dataset: dict[str, Any]) -> Path:
    shutil.rmtree(seed_output_dir, ignore_errors=True)
    seed_path = seed_output_dir / DEMO_SEED_ARTIFACT_PATH
    with _temporary_env({"REPONOMICS_DEMO_DASHBOARD_KEY": str(dataset["demo_key"])}):
        crypto_artifact.encrypt(data_dir, seed_path, "REPONOMICS_DEMO_DASHBOARD_KEY")
    return seed_path


def _prune_retained_data_from_publish_tree(output_dir: Path) -> None:
    for relative in ("data", "dist", ".dashboard-data-artifact"):
        shutil.rmtree(output_dir / relative, ignore_errors=True)


def _write_demo_config(output_dir: Path) -> None:
    payload = {
        "i_have_read_the_readme": True,
        "data_mode": "encrypted",
        "publish_pages_dashboard": True,
        "publish_readme_dashboard": False,
        "allow_docs_sync": False,
        "artifact_retention_days": 90,
        "use_github_app": False,
        "include_only": [],
        "exclude": [],
        "max_repos": 200,
        "include_others": True,
        "include_new": False,
        "include_private": True,
    }
    (output_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _write_demo_provenance(
    output_dir: Path,
    dataset: dict[str, Any],
    as_of: date,
    *,
    seed_artifact_path: Path,
) -> None:
    digest = template_provenance.payload_tree_digest(
        output_dir,
        excluded_paths=DEMO_EXCLUDED_PAYLOAD_PATHS,
    )
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
            "excluded_paths": sorted(DEMO_EXCLUDED_PAYLOAD_PATHS),
        },
        "retained_data_seed": {
            "source_artifact_name": DEMO_SEED_ARTIFACT_NAME,
            "target_artifact_name": DEMO_SEED_DASHBOARD_DATA_ARTIFACT_NAME,
            "path": DEMO_SEED_ARTIFACT_PATH.as_posix(),
            "sha256": _sha256_file(seed_artifact_path),
            "byte_count": seed_artifact_path.stat().st_size,
            "format": "reponomics-encrypted-dashboard-data-v1",
        },
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path = output_dir / DEMO_PROVENANCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_csv_headers(data_dir: Path) -> None:
    for filename, (fields, _date_field) in storage.CSV_REGISTRY.items():
        _assert_csv_header(data_dir / filename, fields)


def build_demo(output_dir: Path, dataset_path: Path, as_of: date, seed_output_dir: Path = DEMO_SEED_DIR) -> None:
    if not TEMPLATE_DIR.exists():
        raise DemoBuildError("dist/template does not exist; run make build-template first.")
    dataset = _load_dataset(dataset_path)
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.copytree(TEMPLATE_DIR, output_dir)
    _materialize_data(output_dir, dataset, as_of)
    _assert_csv_headers(output_dir / "data")
    seed_artifact_path = _write_encrypted_seed_artifact(output_dir / "data", seed_output_dir, dataset)
    _write_demo_config(output_dir)
    _write_demo_workflow(output_dir, str(dataset["demo_key"]))
    _prepend_readme_notice(output_dir / "README.md")
    _prune_retained_data_from_publish_tree(output_dir)
    _write_demo_provenance(output_dir, dataset, as_of, seed_artifact_path=seed_artifact_path)
    verify_demo(output_dir, dataset_path, seed_output_dir=seed_output_dir)
    print(f"Demo repository written to {output_dir}")


def _assert_csv_header(path: Path, expected: list[str]) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        actual = next(reader, [])
    if actual != expected:
        raise DemoBuildError(f"{path} header mismatch: expected {expected}, got {actual}")


def _load_encrypted_seed(seed_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DemoBuildError(f"Missing encrypted demo seed artifact: {seed_path}") from exc
    except json.JSONDecodeError as exc:
        raise DemoBuildError(f"Encrypted demo seed artifact is invalid JSON: {seed_path}") from exc
    if not isinstance(payload, dict):
        raise DemoBuildError(f"Encrypted demo seed artifact must be a JSON object: {seed_path}")
    required = {"version", "created_at", "kdf", "iterations", "algorithm", "salt", "iv", "ciphertext"}
    missing = sorted(required - set(payload))
    if missing:
        raise DemoBuildError(f"Encrypted demo seed artifact is missing keys: {missing}")
    if payload.get("version") != 1 or payload.get("algorithm") != "AES-256-GCM":
        raise DemoBuildError("Encrypted demo seed artifact uses an unsupported format.")
    return payload


def verify_demo(output_dir: Path, dataset_path: Path = DATASET_PATH, seed_output_dir: Path = DEMO_SEED_DIR) -> None:
    dataset = _load_dataset(dataset_path)
    required = [
        output_dir / "README.md",
        output_dir / "config.yaml",
        output_dir / DEMO_TARGET_WORKFLOW,
        output_dir / DEMO_PROVENANCE_PATH,
    ]
    for path in required:
        if not path.is_file():
            raise DemoBuildError(f"Missing demo output: {path}")
    for relative in ("data", "dist", ".dashboard-data-artifact"):
        if (output_dir / relative).exists():
            raise DemoBuildError(f"Generated demo publish tree must not include {relative}/.")
    for relative in ("docs/index.html", "docs/assets"):
        if (output_dir / relative).exists():
            raise DemoBuildError(f"Generated demo publish tree must not include {relative}.")
    seed_path = seed_output_dir / DEMO_SEED_ARTIFACT_PATH
    _load_encrypted_seed(seed_path)
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    config = yaml.safe_load((output_dir / "config.yaml").read_text(encoding="utf-8"))
    workflow = (output_dir / DEMO_TARGET_WORKFLOW).read_text(encoding="utf-8")
    if "Public synthetic demo" not in readme:
        raise DemoBuildError("Demo README is missing synthetic-data disclosure.")
    if config.get("i_have_read_the_readme") is not True:
        raise DemoBuildError("Demo config must be setup-ready.")
    if config.get("data_mode") != "encrypted" or config.get("publish_pages_dashboard") is not True:
        raise DemoBuildError("Demo config must publish encrypted Pages.")
    if config.get("publish_readme_dashboard") is not False:
        raise DemoBuildError("Demo config must not publish a README dashboard.")
    if str(dataset["demo_key"]) not in workflow:
        raise DemoBuildError("Demo Pages workflow does not expose the configured public demo key.")
    _assert_no_demo_brand_risk_terms(output_dir)
    if "COLLECTION_TOKEN" in workflow or "DASHBOARD_SECRET_DO_NOT_REPLACE" in workflow:
        raise DemoBuildError("Demo workflow must not require collection or dashboard secrets.")
    if "mode: publish" not in workflow or "artifact-run-id: ${{ github.run_id }}" not in workflow:
        raise DemoBuildError("Demo workflow must render Pages through the publish runtime.")
    provenance = json.loads((output_dir / DEMO_PROVENANCE_PATH).read_text(encoding="utf-8"))
    if provenance.get("dataset_revision") != dataset.get("dataset_revision"):
        raise DemoBuildError("Demo provenance dataset_revision does not match dataset.yml.")
    if provenance.get("synthetic_data") is not True:
        raise DemoBuildError("Demo provenance must mark synthetic_data=true.")
    expected_digest = template_provenance.payload_tree_digest(
        output_dir,
        excluded_paths=DEMO_EXCLUDED_PAYLOAD_PATHS,
    )
    payload_digest = provenance.get("payload_digest")
    if not isinstance(payload_digest, dict):
        raise DemoBuildError("Demo provenance payload_digest must be a mapping.")
    if payload_digest.get("digest") != expected_digest.digest:
        raise DemoBuildError("Demo provenance payload digest does not match generated publish tree.")
    if payload_digest.get("file_count") != expected_digest.file_count:
        raise DemoBuildError("Demo provenance file_count does not match generated publish tree.")
    if payload_digest.get("byte_count") != expected_digest.byte_count:
        raise DemoBuildError("Demo provenance byte_count does not match generated publish tree.")
    if payload_digest.get("excluded_paths") != sorted(DEMO_EXCLUDED_PAYLOAD_PATHS):
        raise DemoBuildError("Demo provenance excluded_paths does not match demo exclusions.")
    seed_evidence = provenance.get("retained_data_seed")
    if not isinstance(seed_evidence, dict):
        raise DemoBuildError("Demo provenance retained_data_seed must be a mapping.")
    if seed_evidence.get("source_artifact_name") != DEMO_SEED_ARTIFACT_NAME:
        raise DemoBuildError("Demo provenance retained_data_seed source artifact name is wrong.")
    if seed_evidence.get("target_artifact_name") != DEMO_SEED_DASHBOARD_DATA_ARTIFACT_NAME:
        raise DemoBuildError("Demo provenance retained_data_seed target artifact name is wrong.")
    if seed_evidence.get("sha256") != _sha256_file(seed_path):
        raise DemoBuildError("Demo provenance retained_data_seed digest does not match seed artifact.")
    if seed_evidence.get("byte_count") != seed_path.stat().st_size:
        raise DemoBuildError("Demo provenance retained_data_seed byte_count does not match seed artifact.")
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
    parser.add_argument("--seed-output", type=Path, default=DEMO_SEED_DIR)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--as-of")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        verify_demo(args.output, args.dataset, seed_output_dir=args.seed_output)
    else:
        build_demo(args.output, args.dataset, _parse_as_of(args.as_of), seed_output_dir=args.seed_output)


if __name__ == "__main__":
    try:
        main()
    except DemoBuildError as exc:
        print(f"Demo build error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
