"""Acceptance tests for setup in generated dashboard repositories."""
# ruff: noqa: ISC002

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from scripts import build_template

COMMAND_TIMEOUT_SECONDS = 15
NONINTERACTIVE_ENV = {
    "CI": "true",
    "GH_PROMPT_DISABLED": "1",
    "GIT_ASKPASS": "/bin/echo",
    "GIT_TERMINAL_PROMPT": "0",
    "GCM_INTERACTIVE": "never",
    "SSH_ASKPASS": "/bin/echo",
}


def _timeout_output(value: str | bytes | bytearray | memoryview | None) -> str:
    if value is None:
        return ""
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8", errors="replace")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, bytearray):
        return bytes(value).decode("utf-8", errors="replace")
    return value


def _run(
    command: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env={**env, **NONINTERACTIVE_ENV},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"command timed out after {COMMAND_TIMEOUT_SECONDS}s: {' '.join(command)}\n"
            f"stdout:\n{_timeout_output(exc.stdout)}\n"
            f"stderr:\n{_timeout_output(exc.stderr)}"
        ) from exc


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _write_setup_config(repo: Path, **overrides: str) -> None:
    values = {
        "i_have_read_the_readme": "true",
        "data_mode": "encrypted",
        "publish_pages_dashboard": "false",
        "publish_readme_dashboard": "false",
        "allow_docs_sync": "true",
        "artifact_retention_days": "90",
        "use_github_app": "false",
        **overrides,
    }
    config_path = repo / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    replacements = {
        "i_have_read_the_readme: # true/false": (
            f"i_have_read_the_readme: {values['i_have_read_the_readme']}"
        ),
        "data_mode: # encrypted/plaintext": f"data_mode: {values['data_mode']}",
        "publish_pages_dashboard: # true/false": (
            f"publish_pages_dashboard: {values['publish_pages_dashboard']}"
        ),
        "publish_readme_dashboard: # true/false": (
            f"publish_readme_dashboard: {values['publish_readme_dashboard']}"
        ),
        "allow_docs_sync: # true/false": f"allow_docs_sync: {values['allow_docs_sync']}",
        "artifact_retention_days: 90": (
            f"artifact_retention_days: {values['artifact_retention_days']}"
        ),
        "use_github_app: false": f"use_github_app: {values['use_github_app']}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    config_path.write_text(text, encoding="utf-8")


def _initialise_generated_repo(repo: Path, remote: Path) -> None:
    _run(["git", "init", "-b", "main"], repo, os.environ.copy())
    _run(["git", "config", "core.hooksPath", "/dev/null"], repo, os.environ.copy())
    _run(["git", "config", "user.name", "Test User"], repo, os.environ.copy())
    _run(
        ["git", "config", "user.email", "test@example.invalid"], repo, os.environ.copy()
    )
    _run(["git", "add", "-A"], repo, os.environ.copy())
    _run(["git", "commit", "-m", "initial template"], repo, os.environ.copy())
    _run(["git", "init", "--bare", str(remote)], repo, os.environ.copy())
    _run(["git", "remote", "add", "origin", str(remote)], repo, os.environ.copy())
    _run(["git", "push", "-u", "origin", "main"], repo, os.environ.copy())


def _run_resolver(
    repo: Path, tmp_path: Path, *, private: bool
) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "github-env"
    summary_file = tmp_path / "github-step-summary"
    return subprocess.run(
        ["python", ".github/scripts/resolve-reponomics-config.py"],
        cwd=repo,
        env={
            **os.environ,
            **NONINTERACTIVE_ENV,
            "GITHUB_ENV": str(env_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
            "REPOSITORY_PRIVATE": str(private).lower(),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _setup_step_env(step_name: str, base_env: dict[str, str]) -> dict[str, str]:
    env = base_env.copy()
    if step_name == "Resolve setup configuration":
        env["REPOSITORY_PRIVATE"] = "true"
    elif step_name == "Validate required secrets":
        env.update(
            {
                "USE_GITHUB_APP": base_env["USE_GITHUB_APP"],
                "COLLECTION_TOKEN": "",
                "COLLECTION_APP_ID_VAR": "12345",
                "COLLECTION_APP_ID_SECRET": "",
                "COLLECTION_APP_PRIVATE_KEY": "not-a-real-key-but-nonempty",
                "DASHBOARD_SECRET_DO_NOT_REPLACE": "0123456789abcdef0123456789abcdef01234567",
            }
        )
    return env


def test_generated_setup_workflow_runs_with_default_github_app_token_permissions(
    tmp_path: Path,
) -> None:
    """A generated repo setup run must not need workflow-file write permission."""
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    build_template.build_template(repo)
    _write_setup_config(repo, use_github_app="true")
    _initialise_generated_repo(repo, remote)

    workflow = yaml.safe_load(
        (repo / ".github" / "workflows" / "setup.yml").read_text(encoding="utf-8")
    )
    run_steps = [step for step in workflow["jobs"]["setup"]["steps"] if "run" in step]
    env_file = tmp_path / "github-env"
    summary_file = tmp_path / "github-step-summary"
    workflow_env = {key: str(value) for key, value in workflow.get("env", {}).items()}
    base_env = {
        **os.environ,
        **NONINTERACTIVE_ENV,
        **workflow_env,
        "GITHUB_ENV": str(env_file),
        "GITHUB_STEP_SUMMARY": str(summary_file),
        "GITHUB_REPOSITORY": "owner/generated-dashboard",
        "GITHUB_REPOSITORY_OWNER": "owner",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_SHA": _run(
            ["git", "rev-parse", "HEAD"], repo, os.environ.copy()
        ).stdout.strip(),
    }

    for step in run_steps:
        base_env.update(_read_env_file(env_file))
        env = _setup_step_env(step["name"], base_env)
        try:
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", step["run"]],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(
                f"setup step timed out after {COMMAND_TIMEOUT_SECONDS}s: {step['name']}\n"
                f"stdout:\n{_timeout_output(exc.stdout)}\n"
                f"stderr:\n{_timeout_output(exc.stderr)}"
            ) from exc
        assert result.returncode == 0, (
            f"setup step failed: {step['name']}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    changed_paths = _run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        repo,
        os.environ.copy(),
    ).stdout.splitlines()
    assert not any(
        path.startswith(".github/workflows/") for path in changed_paths
    ), changed_paths


def test_setup_config_resolver_fails_closed_when_required_fields_are_blank(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    build_template.build_template(repo)

    result = _run_resolver(repo, tmp_path, private=True)

    assert result.returncode == 1
    assert "Complete the required setup fields in config.yaml" in result.stderr
    assert "i_have_read_the_readme" in result.stderr
    assert "publish_pages_dashboard" in result.stderr


def test_setup_config_resolver_rejects_public_plaintext(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_template.build_template(repo)
    _write_setup_config(repo, data_mode="plaintext")

    result = _run_resolver(repo, tmp_path, private=False)

    assert result.returncode == 1
    assert "data_mode=plaintext is only supported for private repositories" in result.stderr


def test_setup_config_resolver_rejects_control_character_payload(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    build_template.build_template(repo)
    _write_setup_config(repo, data_mode="encrypted\x1b[31m")

    result = _run_resolver(repo, tmp_path, private=True)

    assert result.returncode == 1
    assert "contains unsupported control characters" in result.stderr
    env = _read_env_file(tmp_path / "github-env")
    assert "DATA_MODE" not in env
    assert env == {"REPONOMICS_SETUP_COMPLETE": "false"}


def test_setup_config_resolver_rejects_newline_injection_payload(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    build_template.build_template(repo)
    _write_setup_config(repo)
    config_path = repo / "config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "data_mode: encrypted",
            'data_mode: "encrypted\nEVIL=1"',
        ),
        encoding="utf-8",
    )

    result = _run_resolver(repo, tmp_path, private=True)

    assert result.returncode == 1
    assert "unterminated quoted value" in result.stderr
    env = _read_env_file(tmp_path / "github-env")
    assert "DATA_MODE" not in env
    assert "EVIL" not in env


def test_setup_config_resolver_rejects_duplicate_setup_keys(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_template.build_template(repo)
    _write_setup_config(repo)
    config_path = repo / "config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8") +
        "\npublish_pages_dashboard: true\n",
        encoding="utf-8",
    )

    result = _run_resolver(repo, tmp_path, private=True)

    assert result.returncode == 1
    assert "defines publish_pages_dashboard more than once" in result.stderr
