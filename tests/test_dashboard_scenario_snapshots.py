from __future__ import annotations

import csv
import difflib
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from dashboard_action import run
from scripts import dashboard_scenarios


SNAPSHOT_ROOT = Path(__file__).parent / "fixtures" / "dashboard_scenario_snapshots"
UPDATE_SNAPSHOTS = os.environ.get("UPDATE_DASHBOARD_SCENARIO_SNAPSHOTS") == "1"
FIXED_GENERATED_AT = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
SNAPSHOT_ACTION_VERSION = "0.13.1"
README_SVG_REF_RE = re.compile(r'(?:src|srcset)="([^"]+\.svg)"')
README_MARKDOWN_IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+\.svg)(?:\s+[^)]*)?\)")
MARKDOWN_LINK_REF_RE = re.compile(r"(?<!!)\[[^\]\n]+]\(([^)\s]+)(?:\s+[^)]*)?\)")
MARKDOWN_IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+[^)]*)?\)")
README_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


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


class HtmlLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for name, value in attrs:
            if value is None:
                continue
            if name in {"href", "src"}:
                self.links.append(value)
            elif name == "srcset":
                self.links.extend(_split_srcset(value))


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
    _write_csv(
        data_dir / "collection-days.csv",
        run.storage.COLLECTION_DAY_FIELDS,
        dataset.collection_day_rows,
    )
    _write_csv(
        data_dir / "traffic-coverage.csv",
        run.storage.TRAFFIC_COVERAGE_FIELDS,
        dataset.traffic_coverage_rows,
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
    for env_name in (
        run.DOCS_ACTION_VERSION_ENV,
        run.DOCS_SYNC_STATE_ENV,
        run.DOCS_UPDATED_AT_ENV,
    ):
        monkeypatch.delenv(env_name, raising=False)
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
        comparison_secret="",
        data_mode="plaintext",
        repo_is_public=False,
        config_path=workdir / "config.yaml",
        data_dir=data_dir,
        retention_days=90,
        artifact_run_id="",
        publish_pages_requested=True,
        generate_readme=True,
        allow_docs_sync=True,
        pages_index_path=workdir / "docs" / "index.html",
        readme_path=workdir / "README.md",
        incident_confirm_mode="",
        incident_confirm_purge="",
        incident_confirm_next_secret="",
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
    visible_readme = README_HTML_COMMENT_RE.sub("", readme)
    return set(README_SVG_REF_RE.findall(visible_readme))


def _readme_image_refs(readme: str) -> set[str]:
    visible_readme = README_HTML_COMMENT_RE.sub("", readme)
    return _readme_svg_refs(readme) | set(README_MARKDOWN_IMAGE_REF_RE.findall(visible_readme))


def _split_srcset(value: str) -> list[str]:
    refs = []
    for candidate in value.split(","):
        parts = candidate.strip().split()
        if parts:
            refs.append(parts[0])
    return refs


def _document_links(document: str, *, markdown: bool) -> list[str]:
    visible_document = README_HTML_COMMENT_RE.sub("", document)
    parser = HtmlLinkParser()
    parser.feed(visible_document)
    links = list(parser.links)
    if markdown:
        links.extend(MARKDOWN_LINK_REF_RE.findall(visible_document))
        links.extend(MARKDOWN_IMAGE_REF_RE.findall(visible_document))
    return links


def _is_relative_repo_link(ref: str) -> bool:
    if not ref or ref.startswith("#") or ref.startswith("/"):
        return False
    parsed = urlsplit(ref)
    return not parsed.scheme and not parsed.netloc


def _assert_local_links_resolve(
    root: Path,
    documents: dict[Path, tuple[str, bool]],
) -> None:
    """Assert generated README/dashboard links do not point at missing repo files.

    This checker deliberately enforces only the generated repository's local
    filesystem contract. It prohibits relative links that point outside the
    rendered repository or to files/directories that were not generated, because
    those are broken for every user who receives the template or rendered
    dashboard output. It allows external links, root-absolute links, and
    fragment-only links because those are not resolvable from the local output
    tree. For `target.md#heading`, it verifies `target.md` exists but does not
    validate the fragment; heading-anchor semantics differ across renderers and
    belong in a separate check if we choose to enforce them.
    """
    failures = []
    root = root.resolve()
    for source_path, (document, markdown) in documents.items():
        source = (root / source_path).resolve()
        for ref in _document_links(document, markdown=markdown):
            if not _is_relative_repo_link(ref):
                continue
            path = unquote(urlsplit(url=ref).path)
            if not path:
                continue
            target = (source.parent / path).resolve()
            if root not in {target, *target.parents}:
                failures.append(f"{source_path}: {ref} escapes rendered repo")
                continue
            if path.endswith("/"):
                exists = target.is_dir()
            else:
                exists = target.is_file() or target.is_dir()
            if not exists:
                failures.append(f"{source_path}: {ref} -> {target.relative_to(root)}")

    assert not failures, "Broken local links in generated output:\n" + "\n".join(failures)


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
    assert "encrypted-dashboard-data" not in rendered.dashboard
    assert "plaintext-dashboard-data" in rendered.dashboard
    assert "plaintextDashboardData" in rendered.dashboard
    assert "dashboardPayload" not in rendered.dashboard
    assert "Dashboard disabled" not in rendered.dashboard


def _assert_generated_local_links_resolve(rendered: RenderedScenario) -> None:
    _assert_local_links_resolve(
        rendered.workdir,
        {
            Path("README.md"): (rendered.readme, True),
            Path("docs/index.html"): (rendered.dashboard, False),
        },
    )


@pytest.mark.parametrize(
    ("source_path", "document", "markdown", "expected_failure"),
    [
        (
            Path("README.md"),
            "[Setup & Docs](docs/README.md)",
            True,
            "README.md: docs/README.md -> docs/README.md",
        ),
        (
            Path("README.md"),
            "![Missing chart](docs/assets/missing.svg)",
            True,
            "README.md: docs/assets/missing.svg -> docs/assets/missing.svg",
        ),
        (
            Path("README.md"),
            '<a href="docs/missing.html">Missing</a>',
            True,
            "README.md: docs/missing.html -> docs/missing.html",
        ),
        (
            Path("docs/index.html"),
            '<script src="assets/missing.js"></script>',
            False,
            "docs/index.html: assets/missing.js -> docs/assets/missing.js",
        ),
        (
            Path("docs/index.html"),
            '<img srcset="assets/missing-small.png 1x, assets/missing-large.png 2x">',
            False,
            "docs/index.html: assets/missing-small.png -> docs/assets/missing-small.png",
        ),
        (
            Path("README.md"),
            "[Outside](../outside.md)",
            True,
            "README.md: ../outside.md escapes rendered repo",
        ),
    ],
)
def test_generated_link_checker_rejects_broken_local_links(
    tmp_path: Path,
    source_path: Path,
    document: str,
    markdown: bool,
    expected_failure: str,
) -> None:
    with pytest.raises(AssertionError) as excinfo:
        _assert_local_links_resolve(
            tmp_path,
            {source_path: (document, markdown)},
        )

    assert expected_failure in str(excinfo.value)


def test_generated_link_checker_allows_supported_link_classes(tmp_path: Path) -> None:
    docs_readme = tmp_path / "docs" / "reponomics" / "README.md"
    docs_readme.parent.mkdir(parents=True)
    docs_readme.write_text("local docs\n", encoding="utf-8")
    assets_dir = tmp_path / "docs" / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "chart.umd.min.js").write_text("window.Chart = {}\n", encoding="utf-8")
    (assets_dir / "hero-stats.svg").write_text("<svg></svg>\n", encoding="utf-8")
    (assets_dir / "hero-stats-light.svg").write_text("<svg></svg>\n", encoding="utf-8")

    readme = "\n".join(
        [
            "[Setup & Docs](docs/reponomics/README.md)",
            "[External docs](https://github.com/reponomics/reponomics-dashboard)",
            "[Root absolute](/docs/reponomics/README.md)",
            "[Fragment only](#summary)",
            "[Fragment target](docs/reponomics/README.md#start-here)",
            "![Hero](docs/assets/hero-stats.svg)",
            "<!-- [Commented local link](docs/missing.md) -->",
        ]
    )
    dashboard = "\n".join(
        [
            '<script src="assets/chart.umd.min.js"></script>',
            '<img srcset="assets/hero-stats.svg 1x, assets/hero-stats-light.svg 2x">',
            '<a href="https://github.com/reponomics">External</a>',
            '<a href="#top">Fragment</a>',
        ]
    )

    _assert_local_links_resolve(
        tmp_path,
        {
            Path("README.md"): (readme, True),
            Path("docs/index.html"): (dashboard, False),
        },
    )


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
    _assert_generated_local_links_resolve(rendered)

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
