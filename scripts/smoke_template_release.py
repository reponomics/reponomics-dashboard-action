"""Smoke-test generated template publication and workflow validity."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SmokeTestError(RuntimeError):
    """Raised when template smoke tests fail."""


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        command = " ".join(args)
        print(f"Command failed: {command}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
        result.check_returncode()
    return result


def _create_ephemeral_remote() -> tuple[str, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="template-smoke-"))
    remote_path = temp_root / "template-target.git"
    _run(["git", "init", "--bare", str(remote_path)])
    return remote_path.as_posix(), temp_root


def _prepare_generated_workflows(output_dir: Path, temp_root: Path) -> Path:
    sandbox = temp_root / "generated-template"
    shutil.copytree(output_dir, sandbox)
    return sandbox / ".github" / "workflows"


def _ephemeral_publish(output_dir: Path, remote_path: str) -> None:
    remote_name = f"template-smoke-{uuid.uuid4().hex[:8]}"
    _run(["git", "remote", "add", remote_name, remote_path], cwd=ROOT)
    try:
        _run(
            [
                "venv/bin/python",
                "scripts/publish_generated_repo.py",
                "--output",
                output_dir.as_posix(),
                "--remote",
                remote_name,
                "--branch",
                "smoke-main",
                "--message",
                "chore: smoke publish generated template",
                "--push",
            ],
            cwd=ROOT,
        )
    finally:
        _run(["git", "remote", "remove", remote_name], cwd=ROOT)


def _run_actionlint(workflow_dir: Path) -> None:
    _run(["go", "install", "github.com/rhysd/actionlint/cmd/actionlint@v1.7.8"])
    actionlint = Path.home() / "go" / "bin" / "actionlint"
    if not actionlint.exists():
        raise SmokeTestError("actionlint binary was not installed")
    workflow_files = sorted(workflow_dir.glob("*.yml"))
    if not workflow_files:
        raise SmokeTestError(f"No workflow files found in {workflow_dir}")
    _run(
        [
            actionlint.as_posix(),
            "-color",
            "-oneline",
            *[path.as_posix() for path in workflow_files],
        ],
        cwd=ROOT,
    )


def smoke(output_dir: Path, *, keep_temp: bool = False) -> None:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise SmokeTestError(f"Generated output does not exist: {output_dir}")

    remote_path, temp_root = _create_ephemeral_remote()
    try:
        _ephemeral_publish(output_dir, remote_path)
        workflow_dir = _prepare_generated_workflows(output_dir, temp_root)
        _run_actionlint(workflow_dir)
    finally:
        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)

    print(f"Template smoke tests passed for {output_dir}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "template",
        help="Generated template directory to smoke test.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary smoke directories for debugging.",
    )
    args = parser.parse_args()
    smoke(args.output, keep_temp=args.keep_temp)


if __name__ == "__main__":
    main()
