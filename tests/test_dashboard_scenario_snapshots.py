from __future__ import annotations

import csv
import difflib
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path

import pytest

from dashboard_action import run
from scripts import dashboard_scenarios


SNAPSHOT_ROOT = Path(__file__).parent / "fixtures" / "dashboard_scenario_snapshots"
UPDATE_SNAPSHOTS = os.environ.get("UPDATE_DASHBOARD_SCENARIO_SNAPSHOTS") == "1"
FIXED_GENERATED_AT = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
SNAPSHOT_ACTION_VERSION = "0.13.1"
README_SVG_REF_RE = re.compile(r'(?:src|srcset)="([^"]+\.svg)"')
README_MARKDOWN_IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+\.svg)(?:\s+[^)]*)?\)")


@dataclass(frozen=True)
class RenderedScenario:
    readme: str
    dashboard: str
    workdir: Path


class FixedDashboardDatetime:
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return FIXED_GENERATED_AT.replace(tzinfo=None)
        return FIXED_GENERATED_AT.astimezone(tz)

    strptime = staticmethod(datetime.strptime)


SCENARIOS = {scenario.key: scenario for scenario in dashboard_scenarios.build_scenarios()}


def _write_csv(path: Path, fieldnames: Sequence[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_scenario_data(
    data_dir: Path,
    dataset: dashboard_scenarios.ScenarioDataset,
) -> None:
    _write_csv(data_dir / "traffic-daily.csv", run.storage.DAILY_FIELDS, dataset.daily_rows)
    _write_csv(
        data_dir / "traffic-referrers.csv",
        run.storage.REFERRER_FIELDS,
        dataset.referrer_rows,
    )
    _write_csv(data_dir / "traffic-paths.csv", run.storage.PATH_FIELDS, dataset.path_rows)
    _write_csv(
        data_dir / "repo-metrics.csv",
        run.storage.REPO_METRIC_FIELDS,
        dataset.metric_rows,
    )
    _write_csv(
        data_dir / "collection-status.csv",
        run.storage.COLLECTION_STATUS_FIELDS,
        dataset.status_rows,
    )


def _render_production_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dataset: dashboard_scenarios.ScenarioDataset,
) -> RenderedScenario:
    workdir = tmp_path / dataset.key
    data_dir = workdir / "data"
    workdir.mkdir(parents=True)
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(run, "VERSION", SNAPSHOT_ACTION_VERSION)
    monkeypatch.setattr(run.render_dashboard, "datetime", FixedDashboardDatetime)
    monkeypatch.setattr(
        run.version_status,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v0.13.1",
                "draft": False,
                "prerelease": False,
            }
        ],
    )
    _write_scenario_data(data_dir, dataset)

    config = run.RuntimeConfig(
        mode="publish",
        collection_token="ghp_collection",
        use_github_app=False,
        github_token="ghp_test",
        dashboard_secret="",
        dashboard_next_secret="",
        privacy_mode="plain",
        repo_is_public=False,
        config_path=workdir / "config.yaml",
        data_dir=data_dir,
        retention_days=90,
        artifact_run_id="",
        generate_readme=True,
        allow_docs_sync=True,
        pages_index_path=workdir / "docs" / "index.html",
        readme_path=workdir / "README.md",
        incident_confirm_mode="",
        incident_confirm_purge="",
        incident_confirm_irreversible="",
        action_ref="v0.13.0",
        action_repository="reponomics/reponomics-dashboard-action",
    )

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    readme = config.readme_path.read_text(encoding="utf-8")
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert (config.pages_index_path.parent / "assets" / "chart.umd.min.js").is_file()
    return RenderedScenario(
        readme=_normalize(readme),
        dashboard=_normalize(dashboard),
        workdir=workdir,
    )


def _normalize(value: str) -> str:
    lines = value.replace("\r\n", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"


def _assert_snapshot(actual: str, path: Path) -> None:
    if UPDATE_SNAPSHOTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")

    if not path.exists():
        raise AssertionError(
            f"missing snapshot {path}; rerun with UPDATE_DASHBOARD_SCENARIO_SNAPSHOTS=1"
        )

    expected = path.read_text(encoding="utf-8")
    if actual == expected:
        return

    diff = "\n".join(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=path.as_posix(),
            tofile="actual",
            lineterm="",
        )
    )
    pytest.fail(f"snapshot mismatch for {path}\n{diff}")


def _readme_svg_refs(readme: str) -> set[str]:
    return set(README_SVG_REF_RE.findall(readme))


def _readme_image_refs(readme: str) -> set[str]:
    return _readme_svg_refs(readme) | set(README_MARKDOWN_IMAGE_REF_RE.findall(readme))


def _assert_readme_contract(rendered: RenderedScenario) -> None:
    lower_readme = rendered.readme.lower()
    assert "<script" not in lower_readme
    assert "javascript:" not in lower_readme
    assert "<svg" not in lower_readme
    assert "data:image/svg" not in lower_readme

    svg_refs = _readme_svg_refs(rendered.readme)
    assert svg_refs, "README output should reference generated SVG assets"
    for ref in sorted(svg_refs):
        assert not ref.startswith("/")
        assert "://" not in ref
        assert (rendered.workdir / ref).is_file(), ref

    for ref in sorted(svg_refs):
        if not ref.endswith("-light.svg"):
            continue
        dark_ref = ref.removesuffix("-light.svg") + ".svg"
        assert dark_ref in svg_refs

    for ref in sorted(_readme_image_refs(rendered.readme)):
        if ref.startswith("docs/assets/"):
            assert (rendered.workdir / ref).is_file(), ref


def _assert_readme_asset_snapshots(rendered: RenderedScenario, snapshot_dir: Path) -> None:
    for ref in sorted(_readme_image_refs(rendered.readme)):
        asset_path = rendered.workdir / ref
        if not asset_path.is_file():
            continue
        _assert_snapshot(_normalize(asset_path.read_text(encoding="utf-8")), snapshot_dir / ref)


def _assert_snapshot_image_refs_resolve(snapshot_path: Path) -> None:
    # Navigation links can remain product-relative; image references must be backed by fixtures.
    readme = snapshot_path.read_text(encoding="utf-8")
    refs = _readme_image_refs(readme)
    assert refs, "README snapshot should include image references"

    for ref in sorted(refs):
        assert not ref.startswith("/")
        assert "://" not in ref
        assert (snapshot_path.parent / ref).is_file(), ref


def _assert_dashboard_contract(rendered: RenderedScenario) -> None:
    lower_dashboard = rendered.dashboard.lower()
    assert "<!doctype html>" in lower_dashboard
    assert 'http-equiv="content-security-policy"' in lower_dashboard
    assert 'src="assets/chart.umd.min.js"' in rendered.dashboard
    assert (rendered.workdir / "docs" / "assets" / "chart.umd.min.js").is_file()
    assert "cdn.jsdelivr.net" not in rendered.dashboard
    assert "fonts.googleapis.com" not in rendered.dashboard
    assert "encrypted-payload" not in rendered.dashboard
    assert "Dashboard disabled" not in rendered.dashboard


@pytest.mark.parametrize("scenario_key", sorted(SCENARIOS))
def test_production_dashboard_outputs_match_scenario_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario_key: str,
) -> None:
    rendered = _render_production_outputs(
        monkeypatch,
        tmp_path,
        SCENARIOS[scenario_key],
    )
    _assert_readme_contract(rendered)
    _assert_dashboard_contract(rendered)

    snapshot_dir = SNAPSHOT_ROOT / scenario_key
    _assert_snapshot(rendered.readme, snapshot_dir / "README.snapshot.md")
    _assert_readme_asset_snapshots(rendered, snapshot_dir)
    _assert_snapshot(rendered.dashboard, snapshot_dir / "dashboard.snapshot.html")


@pytest.mark.parametrize(
    "snapshot_path",
    sorted(SNAPSHOT_ROOT.glob("*/README.snapshot.md")),
    ids=lambda path: path.parent.name,
)
def test_readme_snapshot_image_references_resolve(snapshot_path: Path) -> None:
    _assert_snapshot_image_refs_resolve(snapshot_path)
