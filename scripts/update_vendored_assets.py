"""Update vendored third-party assets from their recorded upstream packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if __package__:
    from . import validate_vendored_assets as validator
else:  # pragma: no cover - used when executed as scripts/update_vendored_assets.py
    import validate_vendored_assets as validator  # type: ignore[import-not-found,no-redef]


def _parse_version_overrides(raw_overrides: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for raw_override in raw_overrides:
        package, separator, version = raw_override.partition("=")
        if not separator or not package.strip() or not version.strip():
            raise ValueError("--version entries must use PACKAGE=VERSION")
        overrides[package.strip()] = version.strip()
    return overrides


def _target_version(manifest: dict[str, Any], package_metadata: dict[str, Any], overrides: dict[str, str]) -> str:
    package = manifest["package"]
    if package in overrides:
        return overrides[package]
    latest = package_metadata.get("dist-tags", {}).get("latest")
    if not latest:
        raise ValueError(f"{package} registry metadata does not include a latest dist-tag")
    return str(latest)


def update_manifest(root: Path, manifest_path: Path, overrides: dict[str, str]) -> bool:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    package = manifest["package"]
    package_metadata = validator._read_json(validator._registry_url(manifest["registry"], package))
    version = _target_version(manifest, package_metadata, overrides)
    if version == manifest["version"]:
        print(f"{package} is already current at {version}")
        return False
    if version not in package_metadata["versions"]:
        raise ValueError(f"{package}@{version} was not found in registry metadata")

    dist = package_metadata["versions"][version]["dist"]
    tarball = validator._download(dist["tarball"])
    validator._verify_sri(dist["integrity"], tarball)

    source_data = validator._read_tar_member(tarball, manifest["source_path"])
    license_data = validator._read_tar_member(tarball, manifest["license_source_path"])

    (root / manifest["vendored_path"]).write_bytes(source_data)
    (root / manifest["license_path"]).write_bytes(license_data)

    manifest["version"] = version
    manifest["tarball"] = dist["tarball"]
    manifest["tarball_integrity"] = dist["integrity"]
    manifest["sha256"] = validator._hash_bytes("sha256", source_data)
    manifest["license_sha256"] = validator._hash_bytes("sha256", license_data)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {package} to {version}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="*", type=Path)
    parser.add_argument(
        "--version",
        action="append",
        default=[],
        metavar="PACKAGE=VERSION",
        help="Update one package to an explicit version instead of the registry latest dist-tag.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    manifests = args.manifests or sorted(root.glob("vendor/*/manifest.json"))
    overrides = _parse_version_overrides(args.version)
    seen_packages: set[str] = set()
    updated = False
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        seen_packages.add(manifest["package"])
        updated = update_manifest(root, manifest_path, overrides) or updated

    unknown_overrides = set(overrides) - seen_packages
    if unknown_overrides:
        unknown = ", ".join(sorted(unknown_overrides))
        raise ValueError(f"--version specified packages not present in selected manifests: {unknown}")
    if not updated:
        print("No vendored asset updates were available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
