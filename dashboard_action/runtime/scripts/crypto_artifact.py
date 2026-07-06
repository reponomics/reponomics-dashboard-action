"""Encrypt or decrypt the dashboard data artifact payload.

Public repositories cannot treat Actions artifacts as private storage. This
helper keeps the canonical CSV data artifact-backed while allowing the uploaded
artifact to be ciphertext when the setup mode requires it.
"""

import argparse
import base64
import io
import json
import os
import stat
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import storage


LEGACY_VERSION = 1
VERSION = 2
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
IV_BYTES = 12
ALLOWED_MEMBERS = set(storage.ARTIFACT_FILES)
RETAINED_ARTIFACT_AAD_LABEL_V2 = "reponomics:retained-artifact:v2:dashboard-data"
RETAINED_ARTIFACT_AAD_V2 = RETAINED_ARTIFACT_AAD_LABEL_V2.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _load_secret(env_name: str) -> bytes:
    secret = os.environ.get(env_name, "")
    if not secret:
        raise ValueError(f"{env_name} must be set for encrypted artifact operations.")
    return secret.encode("utf-8")


def _derive_key(secret: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(secret)


def _pack_data_dir(data_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for filename in storage.ARTIFACT_FILES:
            path = data_dir / filename
            if not path.is_file():
                continue
            archive.add(path, arcname=filename)
    return buffer.getvalue()


def _validate_member(member: tarfile.TarInfo) -> str:
    name = PurePosixPath(member.name)
    if not member.name or name.is_absolute():
        raise ValueError(f"Refusing unsafe artifact path: {member.name!r}")
    if any(part in {"", ".", ".."} for part in name.parts):
        raise ValueError(f"Refusing unsafe artifact path: {member.name!r}")
    if len(name.parts) != 1:
        raise ValueError(f"Refusing nested artifact path: {member.name!r}")
    member_name = name.as_posix()
    if member_name not in ALLOWED_MEMBERS:
        raise ValueError(f"Refusing unexpected artifact member: {member_name}")
    if not member.isfile():
        raise ValueError(f"Refusing non-regular artifact member: {member_name}")
    return member_name


def _open_destination(data_dir: Path, member_name: str):
    target = data_dir / member_name
    try:
        target_stat = target.lstat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(target_stat.st_mode):
            raise ValueError(f"Refusing to overwrite symlink artifact target: {member_name}")
        if not stat.S_ISREG(target_stat.st_mode):
            raise ValueError(f"Refusing to overwrite non-regular artifact target: {member_name}")

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except OSError as exc:
        raise ValueError(f"Could not open artifact target safely: {member_name}") from exc
    return os.fdopen(fd, "wb")


def _safe_extract(archive_bytes: bytes, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            member_name = _validate_member(member)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Could not read artifact member: {member_name}")
            with source, _open_destination(data_dir, member_name) as destination:
                destination.write(source.read())


def encrypt(data_dir: Path, output: Path, secret_env: str) -> None:
    secret = _load_secret(secret_env)
    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    key = _derive_key(secret, salt)
    plaintext = _pack_data_dir(data_dir)
    ciphertext = AESGCM(key).encrypt(iv, plaintext, RETAINED_ARTIFACT_AAD_V2)
    payload = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kdf": "PBKDF2-SHA256",
        "iterations": KDF_ITERATIONS,
        "algorithm": "AES-256-GCM",
        "aad": RETAINED_ARTIFACT_AAD_LABEL_V2,
        "salt": _b64encode(salt),
        "iv": _b64encode(iv),
        "ciphertext": _b64encode(ciphertext),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Encrypted dashboard data artifact written to {output}")


def decrypt(input_path: Path, data_dir: Path, secret_env: str) -> None:
    if not input_path.exists():
        print(f"No encrypted dashboard data artifact found at {input_path}.")
        return
    secret = _load_secret(secret_env)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version not in {LEGACY_VERSION, VERSION}:
        raise ValueError(f"Unsupported encrypted artifact version: {payload.get('version')}")
    aad = _aad_for_payload(payload)
    key = _derive_key(secret, _b64decode(payload["salt"]))
    plaintext = AESGCM(key).decrypt(
        _b64decode(payload["iv"]),
        _b64decode(payload["ciphertext"]),
        aad,
    )
    _safe_extract(plaintext, data_dir)
    input_path.unlink()
    print(f"Decrypted dashboard data artifact into {data_dir}")


def _aad_for_payload(payload: dict[str, object]) -> bytes | None:
    version = payload.get("version")
    if version == LEGACY_VERSION:
        return None
    if payload.get("aad") != RETAINED_ARTIFACT_AAD_LABEL_V2:
        raise ValueError("Unsupported encrypted artifact AAD label.")
    return RETAINED_ARTIFACT_AAD_V2


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    encrypt_parser = subparsers.add_parser("encrypt")
    encrypt_parser.add_argument("--data-dir", default="data")
    encrypt_parser.add_argument("--output", default=".dashboard-data-artifact/dashboard-data.enc")
    encrypt_parser.add_argument("--secret-env", default="DASHBOARD_SECRET_DO_NOT_REPLACE")

    decrypt_parser = subparsers.add_parser("decrypt")
    decrypt_parser.add_argument("--input", default="data/dashboard-data.enc")
    decrypt_parser.add_argument("--data-dir", default="data")
    decrypt_parser.add_argument("--secret-env", default="DASHBOARD_SECRET_DO_NOT_REPLACE")

    args = parser.parse_args()
    if args.command == "encrypt":
        encrypt(Path(args.data_dir), Path(args.output), args.secret_env)
    else:
        decrypt(Path(args.input), Path(args.data_dir), args.secret_env)


if __name__ == "__main__":
    main()
