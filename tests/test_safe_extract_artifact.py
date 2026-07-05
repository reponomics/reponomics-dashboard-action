from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from dashboard_action import run  # noqa: F401
import crypto_artifact
import safe_extract_artifact


def _write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_safe_extract_artifact_allows_registered_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    _write_zip(
        archive_path,
        {
            "manifest.json": "{}",
            "traffic-daily.csv": "repo,ts\n",
        },
    )

    safe_extract_artifact.extract(archive_path, tmp_path / "data")

    assert (tmp_path / "data" / "manifest.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "data" / "traffic-daily.csv").read_text(encoding="utf-8") == "repo,ts\n"


def test_safe_extract_artifact_allows_encrypted_artifact(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    _write_zip(archive_path, {"dashboard-data.enc": "ciphertext"})

    safe_extract_artifact.extract(archive_path, tmp_path / "data")

    assert (tmp_path / "data" / "dashboard-data.enc").read_text(encoding="utf-8") == "ciphertext"


@pytest.mark.parametrize(
    "member",
    [
        "../manifest.json",
        "/manifest.json",
        "nested/manifest.json",
        "unexpected.txt",
    ],
)
def test_safe_extract_artifact_rejects_unsafe_or_unexpected_members(
    tmp_path: Path,
    member: str,
) -> None:
    archive_path = tmp_path / "artifact.zip"
    _write_zip(archive_path, {member: "bad"})

    with pytest.raises(safe_extract_artifact.ArtifactExtractionError):
        safe_extract_artifact.extract(archive_path, tmp_path / "data")


def test_safe_extract_artifact_rejects_symlink_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    link_info = zipfile.ZipInfo("manifest.json")
    link_info.external_attr = (stat.S_IFLNK | 0o777) << 16

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link_info, "target")

    with pytest.raises(safe_extract_artifact.ArtifactExtractionError):
        safe_extract_artifact.extract(archive_path, tmp_path / "data")


def test_safe_extract_artifact_rejects_oversized_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "artifact.zip"
    _write_zip(archive_path, {"manifest.json": "123456"})
    monkeypatch.setattr(safe_extract_artifact, "MAX_MEMBER_BYTES", 5)

    with pytest.raises(safe_extract_artifact.ArtifactExtractionError, match="oversized"):
        safe_extract_artifact.extract(archive_path, tmp_path / "data")


def test_safe_extract_artifact_rejects_oversized_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "artifact.zip"
    _write_zip(
        archive_path,
        {
            "manifest.json": "12345",
            "traffic-daily.csv": "123456",
        },
    )
    monkeypatch.setattr(safe_extract_artifact, "MAX_MEMBER_BYTES", 10)
    monkeypatch.setattr(safe_extract_artifact, "MAX_TOTAL_BYTES", 10)

    with pytest.raises(safe_extract_artifact.ArtifactExtractionError, match="archive"):
        safe_extract_artifact.extract(archive_path, tmp_path / "data")


def test_crypto_artifact_encrypt_packs_only_registered_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (data_dir / "unexpected.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", "test-secret")

    encrypted = tmp_path / "dashboard-data.enc"
    crypto_artifact.encrypt(data_dir, encrypted, "DASHBOARD_SECRET_DO_NOT_REPLACE")
    restored = tmp_path / "restored"
    crypto_artifact.decrypt(encrypted, restored, "DASHBOARD_SECRET_DO_NOT_REPLACE")

    assert (restored / "manifest.json").read_text(encoding="utf-8") == "{}"
    assert not (restored / "unexpected.txt").exists()


def test_crypto_artifact_safe_extract_rejects_unexpected_member(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"bad"
        info = tarfile.TarInfo("unexpected.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="unexpected artifact member"):
        crypto_artifact._safe_extract(buffer.getvalue(), tmp_path / "data")
