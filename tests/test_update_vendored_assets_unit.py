from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path

from scripts import update_vendored_assets


def _sri(data: bytes) -> str:
    digest = hashlib.sha512(data).digest()
    return "sha512-" + base64.b64encode(digest).decode("ascii")


def _tarball(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def test_update_manifest_rewrites_asset_license_and_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_path = "package/dist/demo.min.js"
    license_source_path = "package/LICENSE"
    vendored_path = tmp_path / "vendor" / "demo" / "demo.min.js"
    license_path = tmp_path / "vendor" / "demo" / "LICENSE"
    manifest_path = tmp_path / "vendor" / "demo" / "manifest.json"
    vendored_path.parent.mkdir(parents=True)
    vendored_path.write_bytes(b"old source")
    license_path.write_bytes(b"old license")
    manifest = {
        "package": "demo-package",
        "ecosystem": "npm",
        "version": "1.0.0",
        "registry": "https://registry.npmjs.org/",
        "tarball": "https://registry.npmjs.org/demo-package/-/demo-package-1.0.0.tgz",
        "tarball_integrity": "sha512-old",
        "source_path": source_path,
        "vendored_path": "vendor/demo/demo.min.js",
        "sha256": "old",
        "license_source_path": license_source_path,
        "license_path": "vendor/demo/LICENSE",
        "license_sha256": "old",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    tarball = _tarball({
        source_path: b"new source",
        license_source_path: b"new license",
    })
    tarball_url = "https://registry.npmjs.org/demo-package/-/demo-package-1.1.0.tgz"
    package_metadata = {
        "dist-tags": {"latest": "1.1.0"},
        "versions": {
            "1.1.0": {
                "dist": {
                    "tarball": tarball_url,
                    "integrity": _sri(tarball),
                }
            }
        },
    }

    monkeypatch.setattr(update_vendored_assets.validator, "_read_json", lambda _url: package_metadata)
    monkeypatch.setattr(update_vendored_assets.validator, "_download", lambda url: tarball)

    updated = update_vendored_assets.update_manifest(tmp_path, manifest_path, {})

    assert updated is True
    assert vendored_path.read_bytes() == b"new source"
    assert license_path.read_bytes() == b"new license"
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["version"] == "1.1.0"
    assert updated_manifest["tarball"] == tarball_url
    assert updated_manifest["tarball_integrity"] == _sri(tarball)
    assert updated_manifest["sha256"] == hashlib.sha256(b"new source").hexdigest()
    assert updated_manifest["license_sha256"] == hashlib.sha256(b"new license").hexdigest()


def test_parse_version_overrides_rejects_malformed_entries() -> None:
    try:
        update_vendored_assets._parse_version_overrides(["demo-package"])
    except ValueError as error:
        assert "PACKAGE=VERSION" in str(error)
    else:
        raise AssertionError("Expected malformed version override to fail")
