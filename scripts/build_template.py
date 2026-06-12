"""Build and verify the generated template repository tree."""
# ruff: noqa: ISC002

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_contract  # noqa: E402

DEFAULT_MANIFEST = ROOT / "template-manifest.yml"
DEFAULT_OUTPUT = ROOT / "dist" / "template"
TEMPLATE_SOURCE_PREFIX = Path("template")
TEMPLATE_NAME_MARKER = ".template"


class TemplateBuildError(RuntimeError):
    """Raised when the template output cannot be generated or verified."""


def _manifest_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TemplateBuildError(f"Manifest include {field} must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise TemplateBuildError(f"Manifest include {field} must be a relative safe path: {value}")
    return path


def _strip_template_name_marker(path: Path) -> Path:
    if path.name.endswith(TEMPLATE_NAME_MARKER):
        return path.with_name(path.name.removesuffix(TEMPLATE_NAME_MARKER))
    if path.stem.endswith(TEMPLATE_NAME_MARKER):
        return path.with_name(
            f"{path.stem.removesuffix(TEMPLATE_NAME_MARKER)}{path.suffix}"
        )
    return path


def _default_target_for_source(source: Path) -> Path:
    if source.parts and source.parts[0] == TEMPLATE_SOURCE_PREFIX.name:
        try:
            target = source.relative_to(TEMPLATE_SOURCE_PREFIX)
        except ValueError as exc:
            raise TemplateBuildError(
                f"Manifest include source cannot target outside template prefix: {source}"
            ) from exc
        return _strip_template_name_marker(target)
    return source


def iter_include_entries(manifest: dict[str, Any]) -> list[tuple[Path, Path]]:
    entries: list[tuple[Path, Path]] = []
    for raw_entry in manifest.get("include", []):
        if isinstance(raw_entry, str):
            path = _manifest_path(raw_entry, field="path")
            entries.append((path, _default_target_for_source(path)))
            continue
        if isinstance(raw_entry, dict):
            source = _manifest_path(raw_entry.get("source"), field="source")
            target = _manifest_path(raw_entry.get("target"), field="target")
            entries.append((source, target))
            continue
        raise TemplateBuildError(
            "Manifest include entries must be strings or source/target mappings"
        )
    return entries


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}
    if manifest.get("version") != 1:
        raise TemplateBuildError(f"{path} must declare version: 1")
    if not manifest.get("include"):
        raise TemplateBuildError(f"{path} must include at least one path")
    return manifest


def _relative(path: Path) -> str:
    return path.as_posix().lstrip("/")


def _matches_path(path: str, pattern: str) -> bool:
    normalized = pattern.rstrip("/")
    return (
        path == normalized
        or path.startswith(f"{normalized}/")
        or fnmatch.fnmatch(path, pattern)
    )


def _copy_path(source: Path, destination: Path) -> None:
    if not source.exists():
        raise TemplateBuildError(f"Manifest includes missing path: {source}")
    if source.is_dir():
        if destination.exists():
            if not destination.is_dir():
                raise TemplateBuildError(
                    f"Cannot copy directory {source} onto file {destination}"
                )
            for child in sorted(source.iterdir()):
                _copy_path(child, destination / child.name)
        else:
            shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def iter_include_file_entries(manifest: dict[str, Any]) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for source, target in iter_include_entries(manifest):
        source_root = ROOT / source
        if source_root.is_dir():
            default_target = _default_target_for_source(source)
            for source_file in sorted(path for path in source_root.rglob("*") if path.is_file()):
                relative = source_file.relative_to(source_root)
                source_relative = source / relative
                if target == default_target:
                    target_relative = _default_target_for_source(source_relative)
                else:
                    target_relative = target / _strip_template_name_marker(relative)
                files.append((source_relative, target_relative))
        else:
            files.append((source, target))
    return files


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_output_dir(output_dir: Path) -> None:
    if output_dir == ROOT or _is_relative_to(output_dir, ROOT / ".git"):
        raise TemplateBuildError(f"Refusing unsafe output directory: {output_dir}")
    if _is_relative_to(output_dir, ROOT) and not _is_relative_to(output_dir, ROOT / "dist"):
        raise TemplateBuildError(
            "Refusing output directory inside repository source tree outside dist/: "
            f"{output_dir}"
        )


def build_template(
    output_dir: Path = DEFAULT_OUTPUT,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    clean: bool = True,
) -> Path:
    manifest = load_manifest(manifest_path)
    output_dir = output_dir.resolve()
    _validate_output_dir(output_dir)

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for source, target in iter_include_file_entries(manifest):
        _copy_path(ROOT / source, output_dir / target)

    contract = template_contract.validate_local_contract(ROOT)
    template_contract.write_managed_docs_snapshot(
        output_dir / contract.managed_docs_namespace,
        contract=contract,
    )

    verify_template(output_dir, manifest_path)
    return output_dir


def iter_files(root: Path) -> list[str]:
    return sorted(
        _relative(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    )


def verify_template(
    output_dir: Path = DEFAULT_OUTPUT,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> None:
    manifest = load_manifest(manifest_path)
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise TemplateBuildError(f"Template output does not exist: {output_dir}")

    files = iter_files(output_dir)
    for source_path, target_path in iter_include_file_entries(manifest):
        source = ROOT / source_path
        target = output_dir / target_path
        if not source.is_file():
            raise TemplateBuildError(f"Expanded manifest include is not a file: {source_path}")
        if not target.is_file():
            raise TemplateBuildError(f"Required file missing from output: {target_path}")

    forbidden = manifest.get("forbidden", [])
    leaks = [
        path
        for path in files
        for pattern in forbidden
        if _matches_path(path, pattern)
    ]
    if leaks:
        formatted = "\n".join(f"  - {path}" for path in sorted(set(leaks)))
        raise TemplateBuildError(f"Forbidden paths found in template output:\n{formatted}")

    contract = template_contract.validate_local_contract(ROOT)
    template_contract.verify_managed_docs_snapshot(
        output_dir / contract.managed_docs_namespace,
        contract=contract,
    )
    template_contract.verify_template_refs(output_dir, contract=contract)

    commit = _git_value("rev-parse", "--short", "HEAD")
    print(
        f"Verified template output at {output_dir} "
        f"({len(files)} files, source={commit or 'unknown'})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory to write the generated template tree.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Template manifest path.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify an existing output tree without rebuilding it.",
    )
    args = parser.parse_args()

    if args.verify_only:
        verify_template(args.output, args.manifest)
    else:
        output_dir = build_template(args.output, args.manifest)
        print(f"Built template output in {output_dir}")


if __name__ == "__main__":
    main()
