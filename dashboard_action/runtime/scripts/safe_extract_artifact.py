"""Safely extract a downloaded dashboard-data artifact zip."""

from __future__ import annotations

import argparse
import stat
import zipfile
from pathlib import Path, PurePosixPath

import storage


ALLOWED_MEMBERS = set(storage.ARTIFACT_FILES) | {"dashboard-data.enc"}


class ArtifactExtractionError(ValueError):
    """Raised when an artifact archive contains an unsafe or unexpected member."""


def _member_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0o170000


def _validate_member(info: zipfile.ZipInfo) -> str | None:
    raw_name = info.filename
    name = PurePosixPath(raw_name)
    if not raw_name or name.is_absolute():
        raise ArtifactExtractionError(f"Refusing unsafe artifact path: {raw_name!r}")
    if any(part in {"", ".", ".."} for part in name.parts):
        raise ArtifactExtractionError(f"Refusing unsafe artifact path: {raw_name!r}")
    if len(name.parts) != 1:
        raise ArtifactExtractionError(f"Refusing nested artifact path: {raw_name!r}")

    mode = _member_mode(info)
    if info.is_dir():
        return None
    if mode and not stat.S_ISREG(mode):
        raise ArtifactExtractionError(f"Refusing non-regular artifact member: {raw_name!r}")

    member_name = name.as_posix()
    if member_name not in ALLOWED_MEMBERS:
        raise ArtifactExtractionError(f"Refusing unexpected artifact member: {member_name}")
    return member_name


def extract(zip_path: Path, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            member_name = _validate_member(info)
            if member_name is None:
                continue
            target = data_dir / member_name
            with archive.open(info) as source, target.open("wb") as destination:
                destination.write(source.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    extract(args.zip_path, args.data_dir)


if __name__ == "__main__":
    main()
