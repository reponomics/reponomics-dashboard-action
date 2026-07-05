"""Safely extract a downloaded dashboard-data artifact zip."""

from __future__ import annotations

import argparse
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

import storage


ALLOWED_MEMBERS = set(storage.ARTIFACT_FILES) | {"dashboard-data.enc"}
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024


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


def _validate_member_size(info: zipfile.ZipInfo, total_size: int, member_name: str) -> int:
    if info.file_size > MAX_MEMBER_BYTES:
        raise ArtifactExtractionError(
            f"Refusing oversized artifact member {member_name!r}: "
            + f"{info.file_size} bytes exceeds {MAX_MEMBER_BYTES}."
        )
    next_total = total_size + info.file_size
    if next_total > MAX_TOTAL_BYTES:
        raise ArtifactExtractionError(
            "Refusing oversized artifact archive: "
            + f"{next_total} bytes exceeds {MAX_TOTAL_BYTES}."
        )
    return next_total


def _copy_member(
    source,
    destination,
    *,
    member_name: str,
) -> None:
    copied = 0
    while True:
        chunk = source.read(COPY_CHUNK_BYTES)
        if not chunk:
            return
        copied += len(chunk)
        if copied > MAX_MEMBER_BYTES:
            raise ArtifactExtractionError(
                f"Refusing oversized artifact member {member_name!r}: "
                + f"streamed size exceeds {MAX_MEMBER_BYTES}."
            )
        destination.write(chunk)


def _open_destination(data_dir: Path, member_name: str):
    target = data_dir / member_name
    try:
        target_stat = target.lstat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(target_stat.st_mode):
            raise ArtifactExtractionError(
                f"Refusing to overwrite symlink artifact target: {member_name!r}"
            )
        if not stat.S_ISREG(target_stat.st_mode):
            raise ArtifactExtractionError(
                f"Refusing to overwrite non-regular artifact target: {member_name!r}"
            )

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except OSError as exc:
        raise ArtifactExtractionError(
            f"Could not open artifact target safely: {member_name!r}"
        ) from exc
    return os.fdopen(fd, "wb")


def extract(zip_path: Path, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        total_size = 0
        for info in archive.infolist():
            member_name = _validate_member(info)
            if member_name is None:
                continue
            total_size = _validate_member_size(info, total_size, member_name)
            with archive.open(info) as source, _open_destination(
                data_dir,
                member_name,
            ) as destination:
                _copy_member(source, destination, member_name=member_name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    extract(args.zip_path, args.data_dir)


if __name__ == "__main__":
    main()
