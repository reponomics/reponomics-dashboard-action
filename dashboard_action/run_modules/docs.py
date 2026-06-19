"""Managed documentation update git integration."""

from __future__ import annotations

import subprocess

from .core import MANAGED_DOCS_NAMESPACE, VERSION, RuntimeConfig

import managed_docs  # noqa: E402


def _docs_result_with_state(
    result: managed_docs.ManagedDocsResult,
    *,
    state: str,
    reason: str,
) -> managed_docs.ManagedDocsResult:
    return managed_docs.ManagedDocsResult(
        state=state,
        reason=reason,
        manifest_action_version=result.manifest_action_version,
        docs_updated_at=result.docs_updated_at,
        namespace=result.namespace,
        changed=result.changed,
    )


def _git_failure_text(exc: subprocess.CalledProcessError) -> str:
    chunks = []
    stdout = getattr(exc, "stdout", "")
    stderr = getattr(exc, "stderr", "")
    if isinstance(stdout, str) and stdout.strip():
        chunks.append(stdout.strip())
    if isinstance(stderr, str) and stderr.strip():
        chunks.append(stderr.strip())
    if not chunks:
        chunks.append(str(exc))
    return " ".join(chunks)


def _is_permission_failure(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "403",
            "authentication failed",
            "could not read username",
            "not authorized",
            "permission denied",
            "protected branch",
            "repository not found",
            "write access",
        )
    )


def _is_push_race(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "fetch first",
            "non-fast-forward",
            "stale info",
            "updates were rejected",
        )
    )


def _run_git_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, capture_output=True, text=True)


def _push_managed_docs_with_retry() -> None:
    try:
        _run_git_capture(["git", "push"])
        return
    except subprocess.CalledProcessError as first_exc:
        first_text = _git_failure_text(first_exc)
        if _is_permission_failure(first_text) or not _is_push_race(first_text):
            raise

    _run_git_capture(["git", "pull", "--rebase"])
    _run_git_capture(["git", "push"])


def _git_commit_managed_docs(
    config: RuntimeConfig,
    result: managed_docs.ManagedDocsResult,
) -> managed_docs.ManagedDocsResult:
    if not result.changed:
        return result
    if not _inside_git_worktree():
        return _docs_result_with_state(
            result,
            state=managed_docs.STATE_PERMISSION_MISSING,
            reason="Managed docs were written locally but could not be committed outside a git worktree.",
        )

    namespace = MANAGED_DOCS_NAMESPACE.as_posix()
    message = f"docs: update Reponomics managed docs for action v{VERSION} [skip ci]"
    try:
        committed = _commit_managed_docs_namespace(namespace, message)
        if not committed:
            return _docs_result_with_state(
                result,
                state=managed_docs.STATE_UNCHANGED,
                reason="Managed documentation was already committed.",
            )
        _push_managed_docs_with_retry()
    except subprocess.CalledProcessError as exc:
        text = _git_failure_text(exc)
        if _is_permission_failure(text):
            return _docs_result_with_state(
                result,
                state=managed_docs.STATE_PERMISSION_MISSING,
                reason="Managed docs were written locally but Git push was not permitted.",
            )
        return _docs_result_with_state(
            result,
            state=managed_docs.STATE_PUSH_RACE,
            reason="Managed docs were written locally but Git push did not complete after retry.",
        )
    return result


def _inside_git_worktree() -> bool:
    in_repo = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    in_repo_stdout = in_repo.stdout.strip() if isinstance(in_repo.stdout, str) else ""
    return in_repo.returncode == 0 and in_repo_stdout == "true"


def _commit_managed_docs_namespace(namespace: str, message: str) -> bool:
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", "--", namespace], check=True)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", namespace],
        check=False,
    )
    if diff.returncode == 0:
        return False
    subprocess.run(["git", "commit", "-m", message, "--", namespace], check=True)
    return True
