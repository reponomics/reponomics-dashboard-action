from __future__ import annotations

import json
import shutil
from pathlib import Path

from dashboard_action import run


managed_docs = run.managed_docs


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
    docs_bundle_version: str = "1.0.0",
    enabled: bool = True,
) -> managed_docs.ManagedDocsResult:
    bundle_dir = _write_bundle(tmp_path / "bundle", files)
    return managed_docs.sync_managed_docs(
        namespace=tmp_path / "repo" / "docs" / "reponomics",
        bundle_dir=bundle_dir,
        action_repository="reponomics/reponomics-dashboard-action",
        action_version=action_version,
        docs_bundle_version=docs_bundle_version,
        enabled=enabled,
    )


def test_sync_writes_missing_managed_docs_and_manifest(tmp_path: Path) -> None:
    result = _sync(
        tmp_path,
        files={"README.md": "Action {{ACTION_VERSION}}, docs {{DOCS_BUNDLE_VERSION}}\n"},
    )

    namespace = result.namespace
    manifest = json.loads((namespace / ".manifest.json").read_text(encoding="utf-8"))

    assert result.state == managed_docs.STATE_UPDATED
    assert result.changed is True
    assert (namespace / "README.md").read_text(encoding="utf-8") == "Action 1.0.0, docs 1.0.0\n"
    assert manifest["managed_namespace"] == namespace.as_posix()
    assert manifest["action_version"] == "1.0.0"
    assert manifest["docs_bundle_version"] == "1.0.0"
    assert sorted(manifest["files"]) == ["README.md"]


def test_sync_updates_clean_managed_docs_and_removes_stale_files(tmp_path: Path) -> None:
    first = _sync(
        tmp_path,
        files={"README.md": "old\n", "stale.md": "remove me\n"},
        action_version="1.0.0",
        docs_bundle_version="1.0.0",
    )

    second = _sync(
        tmp_path,
        files={"README.md": "new\n"},
        action_version="1.1.0",
        docs_bundle_version="1.1.0",
    )

    manifest = json.loads((second.namespace / ".manifest.json").read_text(encoding="utf-8"))
    assert first.state == managed_docs.STATE_UPDATED
    assert second.state == managed_docs.STATE_UPDATED
    assert (second.namespace / "README.md").read_text(encoding="utf-8") == "new\n"
    assert not (second.namespace / "stale.md").exists()
    assert manifest["action_version"] == "1.1.0"
    assert sorted(manifest["files"]) == ["README.md"]


def test_sync_blocks_user_modified_file(tmp_path: Path) -> None:
    first = _sync(tmp_path, files={"README.md": "generated\n"})
    (first.namespace / "README.md").write_text("user edit\n", encoding="utf-8")

    second = _sync(
        tmp_path,
        files={"README.md": "new generated\n"},
        action_version="1.1.0",
        docs_bundle_version="1.1.0",
    )

    assert second.state == managed_docs.STATE_USER_MODIFIED_CONFLICT
    assert second.changed is False
    assert (second.namespace / "README.md").read_text(encoding="utf-8") == "user edit\n"


def test_sync_blocks_untracked_file_inside_managed_namespace(tmp_path: Path) -> None:
    first = _sync(tmp_path, files={"README.md": "generated\n"})
    (first.namespace / "notes.md").write_text("user note\n", encoding="utf-8")

    second = _sync(
        tmp_path,
        files={"README.md": "new generated\n"},
        action_version="1.1.0",
        docs_bundle_version="1.1.0",
    )

    assert second.state == managed_docs.STATE_MANIFEST_INCONSISTENT
    assert (second.namespace / "notes.md").read_text(encoding="utf-8") == "user note\n"


def test_sync_disabled_writes_nothing(tmp_path: Path) -> None:
    result = _sync(tmp_path, files={"README.md": "generated\n"}, enabled=False)

    assert result.state == managed_docs.STATE_DISABLED
    assert result.changed is False
    assert not result.namespace.exists()


def test_sync_blocks_namespace_without_manifest(tmp_path: Path) -> None:
    namespace = tmp_path / "repo" / "docs" / "reponomics"
    namespace.mkdir(parents=True)
    (namespace / "README.md").write_text("existing\n", encoding="utf-8")

    result = _sync(tmp_path, files={"README.md": "generated\n"})

    assert result.state == managed_docs.STATE_MANIFEST_INCONSISTENT
    assert (namespace / "README.md").read_text(encoding="utf-8") == "existing\n"


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
                "docs_bundle_version": "1.0.0",
                "files": {"../escape.md": "0" * 64},
            }
        ),
        encoding="utf-8",
    )

    result = _sync(tmp_path, files={"README.md": "generated\n"})

    assert result.state == managed_docs.STATE_MANIFEST_INCONSISTENT
    assert not (tmp_path / "repo" / "docs" / "escape.md").exists()
