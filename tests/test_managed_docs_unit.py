from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dashboard_action import run


managed_docs = run.managed_docs

PRERELEASE_WARNING = " ".join(
    [
        "The Reponomics Dashboard template is currently in a pre-release public hardening phase.",
        "It is not intended for public use, and documentation in this managed-docs bundle",
        "should not be considered authoritative.",
    ]
)


def _write_bundle(root: Path, files: dict[str, str]) -> Path:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _sync(
    tmp_path: Path,
    *,
    files: dict[str, str],
    action_version: str = "1.0.0",
    allowed: bool = True,
) -> managed_docs.ManagedDocsResult:
    bundle_dir = _write_bundle(tmp_path / "bundle", files)
    return managed_docs.sync_managed_docs(
        namespace=tmp_path / "repo" / "docs" / "reponomics",
        bundle_dir=bundle_dir,
        action_repository="reponomics/reponomics-dashboard-action",
        action_version=action_version,
        allowed=allowed,
    )


def test_bundled_managed_docs_include_user_guides() -> None:
    files = {
        path.relative_to(run.MANAGED_DOCS_BUNDLE_DIR).as_posix()
        for path in run.MANAGED_DOCS_BUNDLE_DIR.rglob("*")
        if path.is_file()
    }

    assert {
        "README.md",
        "configuration.md",
        "faq.md",
        "privacy-and-artifacts.md",
        "privacy-configuration-matrix.md",
        "provenance.md",
        "repository-guide.md",
        "secure-dashboard-key.md",
        "security.md",
        "support.md",
        "trust-boundary.md",
        "upgrade.md",
    } <= files

    for path in run.MANAGED_DOCS_BUNDLE_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert PRERELEASE_WARNING in text
        assert "architecture/PRIVACY_CONFIGURATION_MATRIX.md" not in text
        assert "SECURE_DASHBOARD_KEY.md" not in text
        assert "TRUST_BOUNDARY.md" not in text
        assert "PROVENANCE.md" not in text
        assert "FAQ.md" not in text
        assert "template-action-release.yml" not in text
        assert "reponomics-dashboard-dev" not in text

    support = (run.MANAGED_DOCS_BUNDLE_DIR / "support.md").read_text(encoding="utf-8")
    security = (run.MANAGED_DOCS_BUNDLE_DIR / "security.md").read_text(encoding="utf-8")
    assert "placeholder support document" in support
    assert "does not define a support policy" in support
    assert "placeholder security document" in security
    assert "does not define a security policy" in security


def test_sync_writes_missing_managed_docs_and_manifest(tmp_path: Path) -> None:
    result = _sync(
        tmp_path,
        files={"README.md": "Action {{ACTION_VERSION}}\n"},
    )

    namespace = result.namespace
    manifest = json.loads((namespace / ".manifest.json").read_text(encoding="utf-8"))

    assert result.state == managed_docs.STATE_WRITTEN
    assert result.changed is True
    assert (namespace / "README.md").read_text(encoding="utf-8") == "Action 1.0.0\n"
    assert manifest["managed_namespace"] == namespace.as_posix()
    assert manifest["action_version"] == "1.0.0"
    assert manifest["updated_at"] == result.docs_updated_at
    assert result.docs_updated_at.endswith("Z")
    assert sorted(manifest["files"]) == ["README.md"]


def test_sync_updates_clean_managed_docs_and_removes_stale_files(tmp_path: Path) -> None:
    first = _sync(
        tmp_path,
        files={"README.md": "old\n", "stale.md": "remove me\n"},
        action_version="1.0.0",
    )

    second = _sync(
        tmp_path,
        files={"README.md": "new\n"},
        action_version="1.1.0",
    )

    manifest = json.loads((second.namespace / ".manifest.json").read_text(encoding="utf-8"))
    assert first.state == managed_docs.STATE_WRITTEN
    assert second.state == managed_docs.STATE_WRITTEN
    assert (second.namespace / "README.md").read_text(encoding="utf-8") == "new\n"
    assert not (second.namespace / "stale.md").exists()
    assert manifest["action_version"] == "1.1.0"
    assert manifest["updated_at"] == second.docs_updated_at
    assert sorted(manifest["files"]) == ["README.md"]


def test_sync_overwrites_local_file_edits_when_allowed(tmp_path: Path) -> None:
    first = _sync(tmp_path, files={"README.md": "generated\n"})
    (first.namespace / "README.md").write_text("user edit\n", encoding="utf-8")

    second = _sync(
        tmp_path,
        files={"README.md": "new generated\n"},
        action_version="1.1.0",
    )

    assert second.state == managed_docs.STATE_WRITTEN
    assert second.changed is True
    assert (second.namespace / "README.md").read_text(encoding="utf-8") == "new generated\n"


def test_sync_removes_untracked_file_inside_managed_namespace_when_allowed(tmp_path: Path) -> None:
    first = _sync(tmp_path, files={"README.md": "generated\n"})
    (first.namespace / "notes.md").write_text("user note\n", encoding="utf-8")

    second = _sync(
        tmp_path,
        files={"README.md": "new generated\n"},
        action_version="1.1.0",
    )

    assert second.state == managed_docs.STATE_WRITTEN
    assert not (second.namespace / "notes.md").exists()


def test_sync_replaces_local_directory_with_managed_file_when_allowed(tmp_path: Path) -> None:
    namespace = tmp_path / "repo" / "docs" / "reponomics"
    (namespace / "README.md").mkdir(parents=True)
    (namespace / "README.md" / "notes.md").write_text("local note\n", encoding="utf-8")

    result = _sync(tmp_path, files={"README.md": "generated\n"})

    assert result.state == managed_docs.STATE_WRITTEN
    assert (namespace / "README.md").read_text(encoding="utf-8") == "generated\n"


def test_sync_blocks_managed_file_symlink_even_when_target_hash_matches(tmp_path: Path) -> None:
    first = _sync(tmp_path, files={"README.md": "generated\n"})
    outside = tmp_path / "outside.md"
    outside.write_text("generated\n", encoding="utf-8")
    readme = first.namespace / "README.md"
    readme.unlink()
    try:
        readme.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    second = _sync(
        tmp_path,
        files={"README.md": "new generated\n"},
        action_version="1.1.0",
    )

    assert second.state == managed_docs.STATE_MANIFEST_INCONSISTENT
    assert outside.read_text(encoding="utf-8") == "generated\n"


def test_sync_blocks_symlinked_namespace_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside-docs"
    outside.mkdir()
    repo.mkdir()
    try:
        (repo / "docs").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    bundle_dir = _write_bundle(tmp_path / "bundle", {"README.md": "generated\n"})

    result = managed_docs.sync_managed_docs(
        namespace=repo / "docs" / "reponomics",
        bundle_dir=bundle_dir,
        action_repository="reponomics/reponomics-dashboard-action",
        action_version="1.0.0",
        allowed=True,
    )

    assert result.state == managed_docs.STATE_MANIFEST_INCONSISTENT
    assert not (outside / "reponomics" / "README.md").exists()


def test_sync_disabled_writes_nothing(tmp_path: Path) -> None:
    result = _sync(tmp_path, files={"README.md": "generated\n"}, allowed=False)

    assert result.state == managed_docs.STATE_DISABLED
    assert result.changed is False
    assert not result.namespace.exists()


def test_sync_overwrites_namespace_without_manifest_when_allowed(tmp_path: Path) -> None:
    namespace = tmp_path / "repo" / "docs" / "reponomics"
    namespace.mkdir(parents=True)
    (namespace / "README.md").write_text("existing\n", encoding="utf-8")

    result = _sync(tmp_path, files={"README.md": "generated\n"})

    assert result.state == managed_docs.STATE_WRITTEN
    assert (namespace / "README.md").read_text(encoding="utf-8") == "generated\n"


def test_sync_rejects_manifest_path_traversal_without_writing_outside_namespace(tmp_path: Path) -> None:
    namespace = tmp_path / "repo" / "docs" / "reponomics"
    namespace.mkdir(parents=True)
    (namespace / ".manifest.json").write_text(
        json.dumps(
            {
                "schema_version": managed_docs.MANIFEST_SCHEMA_VERSION,
                "managed_namespace": namespace.as_posix(),
                "action_repository": "reponomics/reponomics-dashboard-action",
                "action_version": "1.0.0",
                "updated_at": "2026-05-29T12:00:00Z",
                "files": {"../escape.md": "0" * 64},
            }
        ),
        encoding="utf-8",
    )

    result = _sync(tmp_path, files={"README.md": "generated\n"})

    assert result.state == managed_docs.STATE_WRITTEN
    assert not (tmp_path / "repo" / "docs" / "escape.md").exists()
