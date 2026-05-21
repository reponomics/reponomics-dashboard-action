"""Encrypt or decrypt the traffic data artifact payload.

Public repositories cannot treat Actions artifacts as private storage. This
helper keeps the canonical CSV data artifact-backed while allowing the uploaded
artifact to be ciphertext when the setup mode requires it.
"""

import argparse
import base64
import io
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


VERSION = 1
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
IV_BYTES = 12


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
        for path in sorted(data_dir.rglob("*")):
            if not path.is_file() or path.suffix == ".enc":
                continue
            archive.add(path, arcname=path.relative_to(data_dir))
    return buffer.getvalue()


def _safe_extract(archive_bytes: bytes, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            target = data_dir / member.name
            if not target.resolve().is_relative_to(data_dir.resolve()):
                raise ValueError(f"Refusing unsafe artifact path: {member.name}")
        archive.extractall(data_dir)


def encrypt(data_dir: Path, output: Path, secret_env: str) -> None:
    secret = _load_secret(secret_env)
    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    key = _derive_key(secret, salt)
    plaintext = _pack_data_dir(data_dir)
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
    payload = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kdf": "PBKDF2-SHA256",
        "iterations": KDF_ITERATIONS,
        "algorithm": "AES-256-GCM",
        "salt": _b64encode(salt),
        "iv": _b64encode(iv),
        "ciphertext": _b64encode(ciphertext),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Encrypted traffic data artifact written to {output}")


def decrypt(input_path: Path, data_dir: Path, secret_env: str) -> None:
    if not input_path.exists():
        print(f"No encrypted traffic data artifact found at {input_path}.")
        return
    secret = _load_secret(secret_env)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("version") != VERSION:
        raise ValueError(f"Unsupported encrypted artifact version: {payload.get('version')}")
    key = _derive_key(secret, _b64decode(payload["salt"]))
    plaintext = AESGCM(key).decrypt(
        _b64decode(payload["iv"]),
        _b64decode(payload["ciphertext"]),
        None,
    )
    _safe_extract(plaintext, data_dir)
    input_path.unlink()
    print(f"Decrypted traffic data artifact into {data_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    encrypt_parser = subparsers.add_parser("encrypt")
    encrypt_parser.add_argument("--data-dir", default="data")
    encrypt_parser.add_argument("--output", default=".traffic-artifact/traffic-data.enc")
    encrypt_parser.add_argument("--secret-env", default="TRAFFIC_DASHBOARD_SECRET")

    decrypt_parser = subparsers.add_parser("decrypt")
    decrypt_parser.add_argument("--input", default="data/traffic-data.enc")
    decrypt_parser.add_argument("--data-dir", default="data")
    decrypt_parser.add_argument("--secret-env", default="TRAFFIC_DASHBOARD_SECRET")

    args = parser.parse_args()
    if args.command == "encrypt":
        encrypt(Path(args.data_dir), Path(args.output), args.secret_env)
    else:
        decrypt(Path(args.input), Path(args.data_dir), args.secret_env)


if __name__ == "__main__":
    main()
