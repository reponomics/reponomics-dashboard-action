"""Validate vendored third-party assets against recorded upstream artifacts.

Vendored browser assets are shipped inside the composite action so dashboards do
not depend on a CDN at render time. Each asset has a manifest recording the npm
package, exact version, registry tarball, SRI value, source path, local path, and
license hash. This validator verifies the local files, confirms registry
metadata still matches the recorded tarball and integrity, checks OSV for known
vulnerabilities in the pinned package version, and compares the vendored bytes
with the published tarball contents.

Policy details: docs/SECURITY_CHECKS.md.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _hash_bytes(algorithm: str, data: bytes) -> str:
    digest = hashlib.new(algorithm)
    digest.update(data)
    return digest.hexdigest()


def _verify_sri(integrity: str, data: bytes) -> None:
    algorithm, expected_b64 = integrity.split("-", 1)
    digest = hashlib.new(algorithm)
    digest.update(data)
    actual_b64 = base64.b64encode(digest.digest()).decode("ascii")
    if actual_b64 != expected_b64:
        raise ValueError(f"tarball {algorithm} integrity mismatch")


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "reponomics-vendor-verify"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _read_json(url: str) -> dict[str, Any]:
    return json.loads(_download(url))


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "reponomics-vendor-verify",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def _registry_url(registry: str, package: str) -> str:
    base = registry.rstrip("/") + "/"
    return urllib.parse.urljoin(base, urllib.parse.quote(package, safe="@"))


def _read_tar_member(tarball: bytes, member_path: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".tgz") as tmp:
        tmp.write(tarball)
        tmp.flush()
        with tarfile.open(tmp.name, "r:gz") as archive:
            member = archive.extractfile(member_path)
            if member is None:
                raise ValueError(f"tarball member not found: {member_path}")
            return member.read()


def _verify_file(root: Path, manifest: dict[str, Any], path_key: str, hash_key: str) -> None:
    path = root / manifest[path_key]
    expected = manifest[hash_key]
    actual = _hash_bytes("sha256", path.read_bytes())
    if actual != expected:
        raise ValueError(f"{path} sha256 mismatch: expected {expected}, got {actual}")


def _query_osv(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "package": {
            "name": manifest["package"],
            "ecosystem": manifest["ecosystem"],
        },
        "version": manifest["version"],
    }
    vulnerabilities: list[dict[str, Any]] = []
    while True:
        response = _post_json("https://api.osv.dev/v1/query", payload)
        vulnerabilities.extend(response.get("vulns", []))
        page_token = response.get("next_page_token")
        if not page_token:
            return vulnerabilities
        payload["page_token"] = page_token


def _verify_no_known_vulnerabilities(manifest: dict[str, Any]) -> None:
    vulnerabilities = _query_osv(manifest)
    if vulnerabilities:
        ids = ", ".join(vulnerability.get("id", "unknown") for vulnerability in vulnerabilities)
        raise ValueError(
            f"{manifest['package']}@{manifest['version']} has known OSV vulnerabilities: {ids}"
        )


def validate_manifest(root: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_file(root, manifest, "vendored_path", "sha256")
    _verify_file(root, manifest, "license_path", "license_sha256")

    package_metadata = _read_json(_registry_url(manifest["registry"], manifest["package"]))
    published_dist = package_metadata["versions"][manifest["version"]]["dist"]
    if published_dist["tarball"] != manifest["tarball"]:
        raise ValueError(
            f"registry tarball mismatch: expected {manifest['tarball']}, " +
            f"got {published_dist['tarball']}"
        )
    if published_dist["integrity"] != manifest["tarball_integrity"]:
        raise ValueError(
            "registry integrity mismatch: expected " +
            f"{manifest['tarball_integrity']}, got {published_dist['integrity']}"
        )
    _verify_no_known_vulnerabilities(manifest)

    tarball = _download(manifest["tarball"])
    _verify_sri(manifest["tarball_integrity"], tarball)

    source_data = _read_tar_member(tarball, manifest["source_path"])
    source_sha256 = _hash_bytes("sha256", source_data)
    if source_sha256 != manifest["sha256"]:
        raise ValueError(
            f"{manifest['source_path']} sha256 mismatch: " +
            f"expected {manifest['sha256']}, got {source_sha256}"
        )

    license_data = _read_tar_member(tarball, manifest["license_source_path"])
    license_sha256 = _hash_bytes("sha256", license_data)
    if license_sha256 != manifest["license_sha256"]:
        raise ValueError(
            f"{manifest['license_source_path']} sha256 mismatch: " +
            f"expected {manifest['license_sha256']}, got {license_sha256}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="*", type=Path)
    args = parser.parse_args()

    root = Path.cwd()
    manifests = args.manifests or sorted(root.glob("vendor/*/manifest.json"))
    failures: list[str] = []
    for manifest_path in manifests:
        try:
            validate_manifest(root, manifest_path)
        except Exception as error:
            failures.append(f"{manifest_path}: {error}")

    if failures:
        print("Vendored asset validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
