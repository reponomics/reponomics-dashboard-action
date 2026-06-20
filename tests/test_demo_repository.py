from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from scripts.repo_paths import find_repo_root


ROOT = find_repo_root(Path(__file__))
RUNTIME_SCRIPTS = ROOT / "dashboard_action" / "runtime" / "scripts"
if str(RUNTIME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SCRIPTS))

from render_dashboard_support.html import build_encrypted_html  # noqa: E402
from scripts import build_demo_repo  # noqa: E402
from scripts import publish_demo_repo  # noqa: E402


def _encrypted_html(**kwargs) -> str:
    return build_encrypted_html(
        {
            "version": 2,
            "cipher": "AES-GCM",
            "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iterations": 600000},
            "salt": "AA==",
            "summary": "encrypted-summary",
            "chunks": {},
            "chunk_count": 0,
        },
        '<script src="assets/chart.umd.min.js"></script>',
        None,
        **kwargs,
    )


def test_encrypted_html_omits_demo_unlock_by_default() -> None:
    html = _encrypted_html()

    assert 'id="demo-unlock-panel"' not in html
    assert 'id="demo-unlock-button"' not in html
    assert 'id="demo-unlock-key"' not in html
    assert "Public demo key" not in html


def test_encrypted_html_embedded_mode_includes_unlock_runtime() -> None:
    html = _encrypted_html()

    assert '<script id="encrypted-dashboard-data" type="application/json">' in html
    assert '<script id="export-manifest" type="application/json">' in html
    assert "function readEmbeddedJson(id)" in html
    assert "const encryptedDashboardData = readEmbeddedJson('encrypted-dashboard-data');" in html
    assert "decryptDashboardData" in html
    assert "unlockForm.addEventListener('submit'" in html
    assert "import { createDashboardApp }" not in html
    assert "await readJsonAsset" not in html


def test_encrypted_html_renders_escaped_demo_unlock_panel() -> None:
    html = _encrypted_html(
        demo_unlock={
            "label": "Public <demo> key",
            "key": 'demo-key-"quoted"',
            "note": "Synthetic <data>; do not reuse.",
            "button_label": "Unlock <demo>",
        }
    )

    assert 'id="demo-unlock-panel"' in html
    assert 'id="demo-unlock-key"' in html
    assert "Public &lt;demo&gt; key" in html
    assert "demo-key-&quot;quoted&quot;" in html
    assert "Synthetic &lt;data&gt;; do not reuse." in html
    assert "Unlock &lt;demo&gt;" in html


@pytest.mark.parametrize(
    ("demo_unlock", "error_type"),
    [
        ({"label": "Public demo key", "key": "demo", "note": "Synthetic data."}, ValueError),
        (
            {
                "label": "Public demo key",
                "key": "demo",
                "note": "Synthetic data.",
                "button_label": "Unlock",
                "unexpected": "value",
            },
            ValueError,
        ),
        (
            {
                "label": "Public demo key",
                "key": "demo",
                "note": "Synthetic data.",
                "button_label": 42,
            },
            TypeError,
        ),
        ("demo", TypeError),
    ],
)
def test_encrypted_html_rejects_malformed_demo_unlock_metadata(
    demo_unlock: object,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        _encrypted_html(demo_unlock=demo_unlock)


def test_public_action_surface_has_no_demo_unlock_input() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))

    inputs = action["inputs"]
    assert "demo-unlock" not in inputs
    assert "demo-key" not in inputs
    assert "allow-public-readme" not in inputs


def test_demo_dataset_has_single_owner_and_expected_size() -> None:
    dataset = yaml.safe_load((ROOT / "demo" / "dataset.yml").read_text(encoding="utf-8"))
    owner = dataset["owner"]
    repos = dataset["repositories"]

    assert owner == "reponomics-demo"
    assert len(repos) == 30
    assert len(dataset["featured_repositories"]) == 10
    assert all("/" not in repo["name"] for repo in repos)
    assert all(repo["name"].startswith("demo-") for repo in repos)
    assert all(item.startswith(f"{owner}/") for item in dataset["featured_repositories"])
    assert all("/demo-" in item for item in dataset["featured_repositories"])


def test_demo_dataset_rejects_ambiguous_public_brand_names(tmp_path: Path) -> None:
    dataset = {
        "schema_version": 1,
        "dataset_revision": "test",
        "owner": "reponomics-labs",
        "window_days": 90,
        "demo_key": "public-demo-key",
        "featured_repositories": ["reponomics-labs/app-starter"],
        "repositories": [
            {
                "name": "app-starter",
                "shape": "launch",
                "base_views": 10,
                "clone_ratio": 0.1,
                "language": "TypeScript",
            }
        ],
    }
    path = tmp_path / "dataset.yml"
    path.write_text(yaml.safe_dump(dataset), encoding="utf-8")

    with pytest.raises(build_demo_repo.DemoBuildError, match="owner must be"):
        build_demo_repo._load_dataset(path)


def test_demo_verifier_rejects_brand_risk_terms_in_generated_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "README.md").write_text("Synthetic repo: reponomics-labs/demo", encoding="utf-8")

    with pytest.raises(build_demo_repo.DemoBuildError, match="brand-risk term"):
        build_demo_repo._assert_no_demo_brand_risk_terms(output)


def test_demo_pages_workflow_has_no_collection_or_dashboard_secrets(tmp_path: Path) -> None:
    build_demo_repo._write_demo_workflow(tmp_path)

    workflow = (tmp_path / build_demo_repo.DEMO_PAGES_WORKFLOW).read_text(encoding="utf-8")
    assert "COLLECTION_TOKEN" not in workflow
    assert "DASHBOARD_SECRET_DO_NOT_REPLACE" not in workflow
    assert "Seed And Publish Demo Dashboard" in workflow
    assert "workflow_dispatch:" in workflow
    assert "generated-demo-dashboard-data" in workflow
    assert "github-token: ${{ github.token }}" in workflow
    assert "actions/download-artifact@" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "name: dashboard-data" in workflow
    assert "actions/upload-pages-artifact@" in workflow
    assert "actions/deploy-pages@" in workflow
    assert "# v6.0.0" in workflow
    assert "# v5.0.0" in workflow
    assert "permissions: {}" in workflow
    assert "reponomics/reponomics-dashboard-action@" not in workflow


def test_demo_publisher_rejects_committed_retained_data(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    (output / ".reponomics").mkdir(parents=True)
    (output / ".reponomics" / "demo-provenance.json").write_text("{}", encoding="utf-8")
    (output / "data").mkdir()

    with pytest.raises(publish_demo_repo.DemoPublishError, match="must not include data"):
        publish_demo_repo._assert_publish_tree_shape(output)


def test_demo_publisher_rejects_gitignored_publish_files(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    (output / ".reponomics").mkdir(parents=True)
    (output / ".reponomics" / "demo-provenance.json").write_text("{}", encoding="utf-8")
    (output / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (output / "README.md").write_text("demo\n", encoding="utf-8")
    (output / "ignored.txt").write_text("intended generated file\n", encoding="utf-8")
    expected_files = publish_demo_repo._output_files(output)

    with pytest.raises(publish_demo_repo.DemoPublishError, match="missing from git add -A: ignored.txt"):
        publish_demo_repo._assert_git_add_stages_publish_tree(output, "main", expected_files)


def test_source_demo_publish_workflow_is_manual_or_scheduled_and_repo_scoped() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "publish-demo.yml").read_text(encoding="utf-8")
    )

    assert workflow["permissions"] == {}
    assert "workflow_dispatch" in workflow[True]
    assert "schedule" in workflow[True]
    assert workflow["env"]["DEMO_DAILY_SOURCE_REF"] == "${{ vars.DEMO_DAILY_SOURCE_REF || 'main' }}"

    build_job = workflow["jobs"]["build-demo-artifact"]
    assert build_job["if"] == (
        "${{ github.event_name == 'schedule' || "
        + "(github.event_name == 'workflow_dispatch' && inputs.confirm_demo_publish) }}"
    )
    assert "environment" not in build_job
    assert build_job["permissions"] == {"contents": "read"}
    build_step_names = [step["name"] for step in build_job["steps"]]
    assert build_step_names.index("Resolve publication source") < build_step_names.index("Checkout source")
    resolve_step = next(step for step in build_job["steps"] if step["name"] == "Resolve publication source")
    assert "DEMO_DAILY_SOURCE_REF" in resolve_step["run"]
    assert "demo-stable" in resolve_step["run"]
    build_step = next(step for step in build_job["steps"] if step["name"] == "Build and verify generated demo")
    assert "make build-demo" not in build_step["run"]
    assert "make verify-demo" in build_step["run"]
    assert any(step["name"] == "Upload generated demo artifact" for step in build_job["steps"])
    assert any(step["name"] == "Upload encrypted demo dashboard data seed" for step in build_job["steps"])

    publish_job = workflow["jobs"]["publish-demo"]
    assert publish_job["needs"] == "build-demo-artifact"
    assert "environment" not in publish_job
    assert publish_job["permissions"] == {"actions": "read"}
    steps = publish_job["steps"]
    step_names = [step["name"] for step in steps]
    assert step_names.index("Validate downloaded demo artifact") < step_names.index(
        "Create demo publication app token"
    )
    token_step = next(step for step in steps if step["name"] == "Create demo publication app token")
    assert token_step["with"]["client-id"] == "${{ vars.DEMO_PUBLISH_APP_CLIENT_ID }}"
    assert token_step["with"]["private-key"] == "${{ secrets.DEMO_PUBLISH_APP_PRIVATE_KEY }}"
    assert token_step["with"]["repositories"] == "reponomics-dashboard-demo"
    assert token_step["with"]["permission-contents"] == "write"
    assert token_step["with"]["permission-workflows"] == "write"
    assert token_step["with"]["permission-actions"] == "write"
    publish_step = next(step for step in steps if step["name"] == "Publish generated demo repository")
    assert "make publish-demo" not in publish_step["run"]
    assert "git push" in publish_step["run"]
    assert "seed-and-publish-demo-dashboard.yml/dispatches" in publish_step["run"]
