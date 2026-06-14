"""Guarded local entry point for the staging smoke protocol."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repo_paths import find_repo_root
from scripts.staging_smoke.preflight import (
    DEFAULT_ENCRYPTED_FRESH,
    DEFAULT_OWNER,
    DEFAULT_PLAIN_HISTORY,
    DEFAULT_TEMPLATE_STAGING,
)


ROOT = find_repo_root(Path(__file__))
SLOW_GH = "venv/bin/python scripts/staging_smoke/slow_gh.py"
WAIT_RUN = "venv/bin/python scripts/staging_smoke/wait_for_run.py"

LOCAL_GATES = (
    "make validate-workflows",
    "make verify-workflow-classification",
    "make build-template",
    "make verify-template",
    "make validate-template-action-ref",
    "make template-smoke",
    "make template-consumer-e2e",
    "make publish-template-staging-dry-run",
)


@dataclass(frozen=True)
class Operation:
    phase: str
    title: str
    detail: str
    commands: tuple[str, ...] = ()
    executable: bool = False
    smoke_phases: tuple[str, ...] = ("bootstrap", "recurring")


def _run(command: str, *, delay_seconds: float) -> None:
    print(f"\n$ {command}", flush=True)
    subprocess.run(command, cwd=ROOT, shell=True, check=True)
    if delay_seconds:
        time.sleep(delay_seconds)


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _sentence(*parts: str) -> str:
    return " ".join(parts)


def _workflow_run_command(repo: str, workflow: str, *fields: str) -> str:
    parts = [SLOW_GH, "workflow", "run", workflow, "--repo", _quote(repo), "--ref", "main"]
    for field in fields:
        parts.extend(["-f", field])
    wait_parts = [
        WAIT_RUN,
        "--repo",
        _quote(repo),
        "--workflow",
        workflow,
        "--branch",
        "main",
        "--created-after",
        '"$started_at"',
    ]
    return " && ".join(
        [
            'started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")',
            " ".join(parts),
            " ".join(wait_parts),
        ]
    )


def _workflow_wait_command(repo: str, workflow: str, branch: str) -> str:
    return " ".join(
        [
            WAIT_RUN,
            "--repo",
            _quote(repo),
            "--workflow",
            workflow,
            "--branch",
            _quote(branch),
            "--created-after",
            '"$started_at"',
        ]
    )


def _workflow_list_command(repo: str, workflow: str) -> str:
    return " ".join(
        [
            SLOW_GH,
            "run",
            "list",
            "--repo",
            _quote(repo),
            "--workflow",
            workflow,
            "--branch",
            "main",
            "--limit",
            "5",
        ]
    )


def _artifact_list_command(repo: str) -> str:
    jq = " ".join(
        [
            '.artifacts[] | select(.name == "dashboard-data"',
            'or .name == "html-dashboard-plain"',
            'or .name == "html-dashboard-encrypted")',
            "| [.name, .workflow_run.id, .expired, .created_at] | @tsv",
        ]
    )
    return " ".join([SLOW_GH, "api", f"repos/{repo}/actions/artifacts", "--jq", _quote(jq)])


def _plain_artifact_download_command(repo: str) -> str:
    return " && ".join(
        [
            "mkdir -p .tmp/staging-smoke/plain-html",
            " ".join(
                [
                    SLOW_GH,
                    "run",
                    "download",
                    _quote("<plain-collect-run-id>"),
                    "--repo",
                    _quote(repo),
                    "--name",
                    "html-dashboard-plain",
                    "--dir",
                    ".tmp/staging-smoke/plain-html",
                ]
            ),
            "cd .tmp/staging-smoke/plain-html && python3 -m http.server 8765",
        ]
    )


def build_plan(args: argparse.Namespace) -> list[Operation]:
    preflight = " ".join(
        [
            "make staging-smoke-preflight",
            f"STAGING_SMOKE_SOURCE_REPO={_quote(args.source_repo)}",
            f"STAGING_SMOKE_TEMPLATE_REPO={_quote(args.template_staging_repo)}",
            f"STAGING_SMOKE_ENCRYPTED_REPO={_quote(args.encrypted_fresh_repo)}",
            f"STAGING_SMOKE_PLAIN_REPO={_quote(args.plain_history_repo)}",
            f"STAGING_SMOKE_COLLECTION_MODE={_quote(args.collection_mode)}",
            f"STAGING_SMOKE_GH_DELAY_SECONDS={args.command_delay_seconds}",
        ]
    )
    template_dispatch = " && ".join(
        [
            'started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")',
            " ".join(
                [
                    SLOW_GH,
                    "workflow run publish-template-staging.yml",
                    f"--repo {_quote(args.source_repo)}",
                    f"--ref {_quote(args.source_ref)}",
                    f"-f source_ref={_quote(args.source_ref)}",
                    "-f confirm_staging_template_publish=true",
                ]
            ),
            _workflow_wait_command(
                args.source_repo,
                "publish-template-staging.yml",
                args.source_ref,
            ),
        ]
    )
    operations = [
        Operation(
            "local",
            "Inspect and preflight",
            "Verify local tooling, GitHub authentication, staging repos, workflows, and configured secret names.",
            (preflight,),
            True,
        ),
        Operation(
            "local",
            "Run local template gates",
            "Build and verify the generated template before any staging publication or consumer smoke run.",
            (" && ".join(LOCAL_GATES),),
            True,
        ),
        Operation(
            "template",
            "Publish generated template to staging",
            "Dispatch the source-repository staging workflow for the selected source ref, then wait for the workflow result and record the target commit.",
            (
                template_dispatch,
                " ".join(
                    [
                        SLOW_GH,
                        "run",
                        "list",
                        "--repo",
                        _quote(args.source_repo),
                        "--workflow",
                        "publish-template-staging.yml",
                        "--limit",
                        "3",
                    ]
                ),
            ),
            False,
        ),
        Operation(
            "encrypted fresh",
            "Reset encrypted consumer from staging template",
            _sentence(
                "Replace the encrypted-fresh repo with a new root commit copied from the",
                "staging template.",
                f"Confirm the target is exactly {args.encrypted_fresh_repo}",
                "before any force-push.",
            ),
            (
                " ".join(
                    [
                        "make",
                        "staging-smoke-reset-fresh-plan",
                        f"STAGING_SMOKE_TEMPLATE_REPO={_quote(args.template_staging_repo)}",
                        f"STAGING_SMOKE_ENCRYPTED_REPO={_quote(args.encrypted_fresh_repo)}",
                    ]
                ),
                " ".join(
                    [
                        "make",
                        "staging-smoke-reset-fresh",
                        f"STAGING_SMOKE_TEMPLATE_REPO={_quote(args.template_staging_repo)}",
                        f"STAGING_SMOKE_ENCRYPTED_REPO={_quote(args.encrypted_fresh_repo)}",
                        f"CONFIRM_TARGET={_quote(args.encrypted_fresh_repo)}",
                    ]
                ),
            ),
        ),
        Operation(
            "encrypted fresh",
            "Configure encrypted persistent secrets",
            _sentence(
                "Set collection credentials, DASHBOARD_SECRET_DO_NOT_REPLACE, and optional",
                "COMPARISON_SECRET.",
                "Secrets persist on the staging repo and normally only need to be set",
                "during bootstrap or rotation maintenance.",
            ),
            (
                f"{SLOW_GH} secret set COLLECTION_TOKEN --repo {_quote(args.encrypted_fresh_repo)}",
                " ".join(
                    [
                        SLOW_GH,
                        "secret set DASHBOARD_SECRET_DO_NOT_REPLACE --repo",
                        _quote(args.encrypted_fresh_repo),
                    ]
                ),
                f"{SLOW_GH} secret set COMPARISON_SECRET --repo {_quote(args.encrypted_fresh_repo)}",
            ),
            smoke_phases=("bootstrap",),
        ),
        Operation(
            "encrypted fresh",
            "Run encrypted setup",
            _sentence(
                "Run setup after the fresh codebase reset.",
                "Repo settings and secrets persist, but setup rewrites the generated",
                "configuration and setup marker into the fresh tree.",
            ),
            (
                _workflow_run_command(
                    args.encrypted_fresh_repo,
                    "setup.yml",
                    "privacy_mode=strong",
                    "generate_html_dashboard=true",
                    "generate_readme=true",
                    "use_github_app=false",
                ),
                _workflow_list_command(args.encrypted_fresh_repo, "setup.yml"),
            ),
        ),
        Operation(
            "encrypted fresh",
            "Review encrypted config before collection",
            _sentence(
                "Review config.yaml in the encrypted-fresh repo after setup and before",
                "collection.",
                "If the smoke pass should cover a specific repository set, commit that",
                "config change to the remote staging repo before collect-and-publish.",
            ),
        ),
        Operation(
            "encrypted fresh",
            "Collect, publish, rotate, and republish",
            _sentence(
                "Run collect-and-publish with skip_collect=false, validate README/docs",
                "manifest/dashboard-data/Pages, rotate with DASHBOARD_NEXT_SECRET, promote the",
                "new key, and run collect-and-publish again."
            ),
            (
                _workflow_run_command(
                    args.encrypted_fresh_repo,
                    "collect-and-publish.yml",
                    "skip_collect=false",
                ),
                _workflow_list_command(args.encrypted_fresh_repo, "collect-and-publish.yml"),
                _artifact_list_command(args.encrypted_fresh_repo),
                f"{SLOW_GH} api repos/{args.encrypted_fresh_repo}/pages --jq .html_url",
                f"{SLOW_GH} secret set DASHBOARD_NEXT_SECRET --repo {_quote(args.encrypted_fresh_repo)}",
                _workflow_run_command(
                    args.encrypted_fresh_repo,
                    "rotate-key.yml",
                    "confirm_rotation=true",
                ),
                _workflow_list_command(args.encrypted_fresh_repo, "rotate-key.yml"),
                " ".join(
                    [
                        SLOW_GH,
                        "secret set DASHBOARD_SECRET_DO_NOT_REPLACE --repo",
                        _quote(args.encrypted_fresh_repo),
                    ]
                ),
                " ".join(
                    [
                        SLOW_GH,
                        "secret delete DASHBOARD_NEXT_SECRET",
                        "--repo",
                        _quote(args.encrypted_fresh_repo),
                    ]
                ),
                _workflow_run_command(
                    args.encrypted_fresh_repo,
                    "collect-and-publish.yml",
                    "skip_collect=false",
                ),
            ),
        ),
        Operation(
            "encrypted fresh",
            "Browser smoke encrypted Pages",
            "Unlock the Pages dashboard with the active key and check charts, repo selector, comparison, non-traffic growth metrics, focused repo view, and collection calendar statuses.",
            (
                "make staging-smoke-browser-checklist",
                f"{SLOW_GH} api repos/{args.encrypted_fresh_repo}/pages --jq .html_url",
                "open '<encrypted-pages-url>'",
            ),
        ),
        Operation(
            "plain history",
            "Seed or preserve plain-history consumer",
            _sentence(
                "Seed from the staging template only if the repo is empty.",
                "Otherwise preserve commits and existing artifacts.",
                "Then run setup to write config with privacy_mode=plain,",
                "generate_html_dashboard=false, and generate_readme=true.",
            ),
            (
                " ".join(
                    [
                        "make",
                        "staging-smoke-seed-plain-history-plan",
                        f"STAGING_SMOKE_TEMPLATE_REPO={_quote(args.template_staging_repo)}",
                        f"STAGING_SMOKE_PLAIN_REPO={_quote(args.plain_history_repo)}",
                    ]
                ),
                " ".join(
                    [
                        "make",
                        "staging-smoke-seed-plain-history",
                        f"STAGING_SMOKE_TEMPLATE_REPO={_quote(args.template_staging_repo)}",
                        f"STAGING_SMOKE_PLAIN_REPO={_quote(args.plain_history_repo)}",
                        f"CONFIRM_TARGET={_quote(args.plain_history_repo)}",
                    ]
                ),
                f"{SLOW_GH} secret set COLLECTION_TOKEN --repo {_quote(args.plain_history_repo)}",
                _workflow_run_command(
                    args.plain_history_repo,
                    "setup.yml",
                    "privacy_mode=plain",
                    "generate_html_dashboard=false",
                    "generate_readme=true",
                    "use_github_app=false",
                ),
                _workflow_list_command(args.plain_history_repo, "setup.yml"),
            ),
            smoke_phases=("bootstrap",),
        ),
        Operation(
            "plain history",
            "Review plain-history config before first collection",
            _sentence(
                "During bootstrap, review config.yaml in the plain-history repo after setup",
                "and before collection.",
                "Commit any intended repository selection before the first retained-data run.",
                "Recurring runs preserve the existing config and history.",
            ),
            smoke_phases=("bootstrap",),
        ),
        Operation(
            "plain history",
            "Collect, publish, and inspect plain artifacts",
            "Run collect-and-publish with skip_collect=false, then validate README, dashboard-data, html-dashboard-plain, retained history, and absence of a Pages requirement.",
            (
                _workflow_run_command(
                    args.plain_history_repo,
                    "collect-and-publish.yml",
                    "skip_collect=false",
                ),
                _workflow_list_command(args.plain_history_repo, "collect-and-publish.yml"),
                _artifact_list_command(args.plain_history_repo),
            ),
        ),
        Operation(
            "plain history",
            "Browser smoke local plain HTML artifact",
            "Download html-dashboard-plain, serve it from a temporary local HTTP server, and verify charts and dashboard values locally.",
            (_plain_artifact_download_command(args.plain_history_repo), "open http://localhost:8765"),
        ),
        Operation(
            "doctor",
            "Run doctor and produce smoke report",
            "Run doctor against both latest successful consumer workflow runs, run read-only evidence checks, and report commits, run URLs, artifacts, browser checks, failures, and follow-ups.",
            (
                _workflow_run_command(
                    args.encrypted_fresh_repo,
                    "doctor.yml",
                    f"artifact_run_id={_quote('<encrypted-collect-run-id>')}",
                ),
                _workflow_run_command(
                    args.plain_history_repo,
                    "doctor.yml",
                    f"artifact_run_id={_quote('<plain-collect-run-id>')}",
                ),
                " ".join(
                    [
                        "make",
                        "staging-smoke-evidence",
                        f"STAGING_SMOKE_ENCRYPTED_REPO={_quote(args.encrypted_fresh_repo)}",
                        f"STAGING_SMOKE_PLAIN_REPO={_quote(args.plain_history_repo)}",
                        f"STAGING_SMOKE_GH_DELAY_SECONDS={args.command_delay_seconds}",
                    ]
                ),
            ),
        ),
    ]
    return [operation for operation in operations if args.phase in operation.smoke_phases]


def print_plan(operations: list[Operation]) -> None:
    for index, operation in enumerate(operations, start=1):
        print(f"{index}. [{operation.phase}] {operation.title}")
        print(f"   {operation.detail}")
        if operation.commands:
            print("   commands:")
            for command in operation.commands:
                print(f"   - {command}")


def execute(args: argparse.Namespace, operations: list[Operation]) -> None:
    if args.dispatch_template_staging:
        executable = operations[:3]
    else:
        executable = operations[:2]

    for operation in executable:
        if not operation.commands:
            continue
        if operation.phase == "template" and not args.dispatch_template_staging:
            continue
        if operation.phase == "template":
            print("\nDispatching staging template publication workflow.")
        for command in operation.commands:
            try:
                _run(command, delay_seconds=args.command_delay_seconds)
            except subprocess.CalledProcessError:
                if operation.title == "Inspect and preflight" and args.allow_bootstrap_preflight_failures:
                    print(
                        _sentence(
                            "\nContinuing after preflight failure because",
                            "--allow-bootstrap-preflight-failures was set.",
                            "Use this only for the first empty-repo bootstrap pass.",
                        )
                    )
                    continue
                raise

    if not args.dispatch_template_staging:
        print(
            _sentence(
                "\nStopped before GitHub publication. Re-run with --execute",
                "--dispatch-template-staging to dispatch the staging template workflow after local",
                "gates pass.",
            )
        )
    print("\nRemaining consumer-repository smoke steps:")
    print_plan(operations[len(executable) :])


def report_template(args: argparse.Namespace) -> str:
    return f"""# Reponomics Staging Smoke Report

Date:
Operator:

## Source

- Source repository: `{args.source_repo}`
- Source ref: `{args.source_ref}`
- Smoke phase: `{args.phase}`
- Source commit:
- Local gates:

## Template Staging

- Template staging repository: `{args.template_staging_repo}`
- Publication workflow run:
- Published commit:

## Encrypted Fresh Consumer

- Repository: `{args.encrypted_fresh_repo}`
- Reset confirmed:
- Setup run after fresh codebase reset:
- Config reviewed/updated before collection:
- First collect/publish run:
- Rotation run:
- Second collect/publish run:
- Doctor run:
- `dashboard-data` artifact observed:
- Pages URL:
- Browser unlock:
- Charts/repo selector/comparison/focused repo/calendar checks:
- Browser checklist path:

## Plain History Consumer

- Repository: `{args.plain_history_repo}`
- Existing history preserved:
- Seed/setup run, bootstrap only:
- Config reviewed/updated, bootstrap only:
- Collect/publish run:
- Doctor run:
- `dashboard-data` artifact observed:
- `html-dashboard-plain` artifact observed:
- Local browser artifact path:
- Charts/readme/dashboard coherence checks:
- Browser checklist path:

## Result

- Status: incomplete
- Browser checklist:
- Failures:
- Follow-up:
"""


def write_report_template(args: argparse.Namespace) -> None:
    path = Path(args.write_report_template)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_template(args), encoding="utf-8")
    print(f"Wrote smoke report template: {path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", default=f"{DEFAULT_OWNER}/reponomics-dashboard-action")
    parser.add_argument("--source-ref", default="main")
    parser.add_argument("--template-staging-repo", default=DEFAULT_TEMPLATE_STAGING)
    parser.add_argument("--encrypted-fresh-repo", default=DEFAULT_ENCRYPTED_FRESH)
    parser.add_argument("--plain-history-repo", default=DEFAULT_PLAIN_HISTORY)
    parser.add_argument(
        "--collection-mode",
        choices=("pat",),
        default="pat",
        help="Collection credential mode expected in consumer staging repos. Staging smoke currently supports PAT mode.",
    )
    parser.add_argument(
        "--phase",
        choices=("bootstrap", "recurring"),
        default="recurring",
        help="Use bootstrap for one-time setup/secrets; recurring assumes persistent repos and configured secrets.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the executable local phase. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--dispatch-template-staging",
        action="store_true",
        help="With --execute, dispatch the staging template publication workflow after local gates.",
    )
    parser.add_argument(
        "--allow-bootstrap-preflight-failures",
        action="store_true",
        help="Continue after preflight failure for the first empty-repository bootstrap pass.",
    )
    parser.add_argument(
        "--write-report-template",
        help="Write a markdown staging smoke report template to this path.",
    )
    parser.add_argument(
        "--command-delay-seconds",
        type=float,
        default=1.0,
        help="Sleep after each executed command. Defaults to one second for GitHub API hygiene.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    operations = build_plan(args)
    if args.write_report_template:
        write_report_template(args)
    if not args.execute:
        print("Dry run: no commands will be executed.\n")
        print_plan(operations)
        return
    execute(args, operations)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
