"""Run generated-template checks against the public default action ref."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts.repo_paths import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_paths import find_repo_root  # type: ignore[import-not-found,no-redef]


ROOT = find_repo_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import template_consumer_e2e  # noqa: E402
from scripts import template_contract  # noqa: E402
from scripts import template_compat_e2e  # noqa: E402
from scripts import validate_template_action_ref  # noqa: E402


DEFAULT_TEMPLATE = ROOT / "dist" / "template"
DEFAULT_ACTION_PYTHON = ROOT / "venv" / "bin" / "python"


class TemplatePublicActionE2EError(RuntimeError):
    """Raised when the generated template fails against the public action ref."""


def _run(args: list[str], *, cwd: Path) -> str:
    try:
        return subprocess.check_output(
            args,
            cwd=cwd,
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        output = exc.output.strip()
        details = f": {output}" if output else ""
        raise TemplatePublicActionE2EError(
            f"Command failed: {' '.join(args)}{details}"
        ) from exc


def _fetch_ref(resolved: validate_template_action_ref.ResolvedActionRef) -> str:
    return resolved.remote_ref.removesuffix("^{}")


def checkout_public_action(
    *,
    contract: template_contract.TemplateContract,
    resolved: validate_template_action_ref.ResolvedActionRef,
    destination: Path,
) -> Path:
    """Checkout the validated public action ref at its resolved commit."""
    remote_url = f"https://github.com/{contract.action_repository}.git"
    destination.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], cwd=destination)
    _run(["git", "remote", "add", "origin", remote_url], cwd=destination)
    _run(["git", "fetch", "--depth=1", "origin", _fetch_ref(resolved)], cwd=destination)
    _run(["git", "-c", "advice.detachedHead=false", "checkout", "--detach", resolved.sha], cwd=destination)
    return destination


def install_public_action_runtime(
    *,
    action_repo: Path,
    venv_dir: Path,
    base_python: Path,
) -> Path:
    """Install the checked-out public action into an isolated runtime venv."""
    return template_compat_e2e._install_isolated_python_env(  # noqa: SLF001
        source_dir=action_repo,
        venv_dir=venv_dir,
        base_python=template_compat_e2e._absolute_path(base_python),  # noqa: SLF001
        label="public action runtime",
    )


def run_public_action_e2e(
    *,
    template_dir: Path,
    action_python: Path,
    accepted_action: bool = False,
    keep_temp: bool = False,
) -> None:
    contract = template_contract.load_contract(ROOT)
    if accepted_action:
        resolved, _default = validate_template_action_ref.validate_accepted_action_release(
            root=ROOT,
        )
    else:
        resolved = validate_template_action_ref.validate_public_action_ref(root=ROOT)
    temp_root = Path(tempfile.mkdtemp(prefix="template-public-action-e2e-"))
    action_repo = temp_root / "action"
    try:
        checkout_public_action(
            contract=contract,
            resolved=resolved,
            destination=action_repo,
        )
        isolated_action_python = install_public_action_runtime(
            action_repo=action_repo,
            venv_dir=temp_root / "public-action-runtime",
            base_python=action_python,
        )
        print(
            "Checking generated template against public action ref: "
            + f"{contract.action_repository}@{resolved.ref} ({resolved.sha[:7]})"
        )
        template_consumer_e2e.run_e2e(
            template_dir=template_dir,
            action_repo=action_repo,
            action_python=isolated_action_python,
            keep_temp=keep_temp,
        )
    finally:
        if keep_temp:
            print(f"Kept public action e2e temp directory: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--action-python", type=Path, default=DEFAULT_ACTION_PYTHON)
    parser.add_argument(
        "--accepted-action",
        action="store_true",
        help="Use accepted_action.tag/SHA metadata instead of default_action_ref.",
    )
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    run_public_action_e2e(
        template_dir=args.template_dir,
        action_python=args.action_python,
        accepted_action=args.accepted_action,
        keep_temp=args.keep_temp,
    )


if __name__ == "__main__":
    try:
        main()
    except TemplatePublicActionE2EError as exc:
        print(f"Public action template e2e failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
