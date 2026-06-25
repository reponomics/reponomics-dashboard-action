from __future__ import annotations

import base64
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest
import requests

from dashboard_action import run
import doctor_retained

from runner_support import (
    NEXT_KEY,
    OLD_KEY,
    _asset_text,
    _config,
    _dashboard_json,
    _decrypt_encrypted_dashboard_data,
    _published_runtime_text,
    _report_stage,
    _response,
    _result_stage,
    _secret_result_stage,
    _seed_log,
    _tamper_encrypted_token,
    _write_dashboard_json,
)


def test_publish_fixture_renders_outputs_without_live_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=True)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    assert config.readme_path.exists()
    assert config.pages_index_path.exists()
    readme = config.readme_path.read_text(encoding="utf-8")
    assert "demo/reponomics" in readme
    assert "Latest data capture: 2026-05-01 12:00 UTC" in readme
    assert "Last updated:" not in readme
    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    assert 'name="reponomics-encrypted-dashboard-data"' in dashboard
    assert 'name="reponomics-export-manifest"' in dashboard
    assert 'id="export-button"' in dashboard
    assert 'id="export-hash-button"' in dashboard
    assert "How download verification works" in dashboard
    secure_runtime = _asset_text(config.pages_index_path, "dashboard/entry-secure.js")
    secure_core = _asset_text(config.pages_index_path, "dashboard/secure-core.js")
    assert "decryptDashboardData" in secure_runtime
    assert "validateEncryptedDashboardData" in secure_core
    assert "EXPECTED_KDF_ITERATIONS = 600000" in secure_core
    assert 'src="assets/chart.umd.min.js"' in dashboard
    assert 'type="module" src="assets/dashboard/entry-secure.js"' in dashboard
    assert "cdn.jsdelivr.net" not in dashboard
    assert (config.pages_index_path.parent / "assets" / "chart.umd.min.js").exists()
    assert len(list((config.pages_index_path.parent / "assets").glob("export-data-*.enc"))) == 1


def test_publish_fixture_writes_v2_encrypted_dashboard_data_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    encrypted_data = _dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
    )
    assert encrypted_data["version"] == 2
    assert encrypted_data["cipher"] == "AES-GCM"
    assert encrypted_data["kdf"] == {
        "name": "PBKDF2",
        "hash": "SHA-256",
        "iterations": run.render_dashboard.PBKDF2_ITERATIONS,
    }
    assert encrypted_data["encoding"] == "gzip+json"
    assert "encrypted-payload" not in dashboard
    assert "demo/reponomics" not in dashboard
    runtime = _published_runtime_text(config.pages_index_path, encrypted=True)
    assert "loadRepoChunk" in runtime
    assert "ensureCurrentRepoChunksLoaded" in runtime
    assert "MAX_COMPARE_REPOS = 8" in runtime
    assert "dashboard-notice-region" in dashboard
    assert "normalizeChunkLoadError" in runtime

    summary, chunks = _decrypt_encrypted_dashboard_data(encrypted_data)
    repo_names = [repo["name"] for repo in summary["repos"]]
    assert encrypted_data["chunk_count"] == len(repo_names)
    assert set(encrypted_data["chunks"]) == set(summary["repo_chunks"].values())
    assert set(chunks) == set(summary["repo_chunks"].values())
    assert "repo_series" not in summary
    assert "repo_weekday" not in summary
    assert "repo_referrers" not in summary
    assert "repo_paths" not in summary
    assert "per_repo" not in summary["growth"]
    assert "series" not in summary["growth"]

    for repo_name, chunk_id in summary["repo_chunks"].items():
        chunk = chunks[chunk_id]
        assert chunk["repo"] == repo_name
        assert set(chunk) == {
            "repo",
            "repo_series",
            "repo_weekday",
            "repo_referrers",
            "repo_paths",
            "growth",
        }
        assert chunk["repo_series"]["dates"]
        assert "per_repo" in chunk["growth"]
        assert "series" in chunk["growth"]["per_repo"]


def test_doctor_dashboard_key_check_distinguishes_ui_failure_from_wrong_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    matching_key = run.doctor_mod.check_dashboard_key(config.pages_index_path, OLD_KEY)
    assert matching_key == run.doctor_mod.DashboardKeyCheckResult(
        ok=True,
        stage="success",
        detail="supplied key decrypts this dashboard",
        chunks_checked=1,
        chunk_count=1,
        repo_count=1,
    )

    wrong_key = run.doctor_mod.check_dashboard_key(config.pages_index_path, NEXT_KEY)
    assert wrong_key.ok is False
    assert wrong_key.stage == "decrypt"
    assert wrong_key.detail == "AES-GCM authentication failed"


def test_doctor_dashboard_key_check_rejects_corrupt_chunk_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    encrypted_data = _dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
    )
    first_chunk_id = next(iter(encrypted_data["chunks"]))
    encrypted_data["chunks"][first_chunk_id] = _tamper_encrypted_token(
        encrypted_data["chunks"][first_chunk_id]
    )
    _write_dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
        encrypted_data,
    )

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
    )

    assert result.key_cryptographically_accepted == "passed"
    assert result.repo_chunks_valid == "failed"
    assert (
        _secret_result_stage(
            result,
            "DASHBOARD_SECRET_DO_NOT_REPLACE",
            "chunk_authenticates",
        ).status
        == "failed"
    )
    assert result.ui_handoff_reached is False

    compatibility_result = run.doctor_mod.check_dashboard_key(config.pages_index_path, OLD_KEY)
    assert compatibility_result.ok is False
    assert compatibility_result.stage == "decrypt"
    assert compatibility_result.detail == "AES-GCM authentication failed"


def test_doctor_mode_fails_when_ui_handoff_boundary_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "outputs.txt"
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    encrypted_data = _dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
    )
    first_chunk_id = next(iter(encrypted_data["chunks"]))
    encrypted_data["chunks"][first_chunk_id] = _tamper_encrypted_token(
        encrypted_data["chunks"][first_chunk_id]
    )
    _write_dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
        encrypted_data,
    )

    doctor_config = _config(tmp_path, mode="doctor", dashboard_secret=OLD_KEY)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setenv("GITHUB_OUTPUT", output_path.as_posix())

    with pytest.raises(
        run.ActionError,
        match="Doctor staged diagnostics did not reach the browser/UI handoff boundary.",
    ):
        run.run_doctor(doctor_config)

    report_path = tmp_path / ".reponomics" / "doctor" / "doctor-report.json"
    assert output_path.read_text(encoding="utf-8") == (
        f"doctor-report-path={report_path.relative_to(tmp_path).as_posix()}\n"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["key_cryptographically_accepted"] == "passed"
    assert report["repo_chunks_valid"] == "failed"
    assert _report_stage(report, "ui_handoff_boundary_reached")["status"] == "failed"

    summary = summary_path.read_text(encoding="utf-8")
    assert "- Browser/UI handoff boundary: `failed`" in summary
    output = capsys.readouterr().out
    expected_error = (
        "::error title=Reponomics doctor diagnostics::Dashboard payload did not "
        + "reach browser/UI handoff boundary: one or more encryption, storage, or "
        + "data-contract stages failed\n"
    )
    assert expected_error in output


def test_doctor_treats_empty_encrypted_dashboard_as_semantically_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
    )

    assert result.key_cryptographically_accepted == "passed"
    assert result.dashboard_data_semantically_consistent == "passed"
    assert (
        _secret_result_stage(
            result,
            "DASHBOARD_SECRET_DO_NOT_REPLACE",
            "semantic_counts_valid",
        ).status
        == "passed"
    )
    assert result.ui_handoff_reached is True

    compatibility_result = run.doctor_mod.check_dashboard_key(config.pages_index_path, OLD_KEY)
    assert compatibility_result == run.doctor_mod.DashboardKeyCheckResult(
        ok=True,
        stage="success",
        detail="supplied key decrypts this dashboard",
        chunks_checked=0,
        chunk_count=0,
        repo_count=0,
    )


def test_doctor_treats_empty_plaintext_dashboard_as_semantically_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(
        tmp_path,
        mode="publish",
        data_mode="plaintext",
        dashboard_secret="",
        generate_readme=False,
    )

    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="plaintext",
        secrets=[],
    )

    assert result.key_cryptographically_accepted == "skipped"
    assert result.dashboard_data_semantically_consistent == "passed"
    assert _result_stage(result, "semantic_counts_valid").status == "passed"
    assert result.ui_handoff_reached is True


def test_doctor_mode_reports_which_named_secret_decrypts_dashboard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "outputs.txt"
    config = _config(
        tmp_path,
        mode="publish",
        generate_readme=False,
    )
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    doctor_config = _config(
        tmp_path,
        mode="doctor",
        dashboard_secret=OLD_KEY,
        comparison_secret=NEXT_KEY,
    )
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setenv("GITHUB_OUTPUT", output_path.as_posix())

    run.run_doctor(doctor_config)

    summary = summary_path.read_text(encoding="utf-8")
    assert "- Configured data mode: `encrypted`" in summary
    assert "- Detected dashboard mode: `encrypted`" in summary
    assert "- Keys cryptographically accepted: `1`" in summary
    assert "| Key cryptographically accepted | `passed` |" in summary
    accepted_row = "".join(
        [
            "| `DASHBOARD_SECRET_DO_NOT_REPLACE` | provided | `passed` | ",
            "`semantic_counts_valid` | repo, mapping, and chunk counts agree |",
        ]
    )
    failed_row = "".join(
        [
            "| `COMPARISON_SECRET` | provided | `failed` | ",
            "`summary_authenticates` | AES-GCM authentication failed |",
        ]
    )
    assert accepted_row in summary
    assert failed_row in summary
    assert "| `ui_handoff_boundary_reached` | `passed` |" in summary

    report_path = tmp_path / ".reponomics" / "doctor" / "doctor-report.json"
    assert output_path.read_text(encoding="utf-8") == (
        f"doctor-report-path={report_path.relative_to(tmp_path).as_posix()}\n"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["configured_data_mode"] == "encrypted"
    assert report["detected_dashboard_mode"] == "encrypted"
    assert report["key_cryptographically_accepted"] == "passed"
    assert report["export_artifact_valid"] == "passed"
    assert report["secret_results"][0]["label"] == "DASHBOARD_SECRET_DO_NOT_REPLACE"
    assert report["secret_results"][0]["accepted"] is True
    assert report["secret_results"][1]["label"] == "COMPARISON_SECRET"
    assert report["secret_results"][1]["accepted"] is False
    assert {
        "name": "export_decrypts",
        "status": "passed",
        "subject": "DASHBOARD_SECRET_DO_NOT_REPLACE",
        "detail": "export asset decrypted",
    } in report["stages"]


def test_doctor_mode_escapes_warning_workflow_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", (tmp_path / "summary.md").as_posix())
    config = _config(
        tmp_path,
        mode="doctor",
        dashboard_secret=OLD_KEY,
        comparison_secret=NEXT_KEY,
    )
    staged_result = run.doctor_mod.DashboardDoctorResult(
        configured_data_mode="encrypted",
        detected_dashboard_mode="encrypted",
        dashboard_html_found="passed",
        browser_payload_contract_valid="passed",
        key_cryptographically_accepted="passed",
        dashboard_data_well_formed="passed",
        dashboard_data_semantically_consistent="passed",
        repo_chunks_valid="passed",
        retained_data_artifact_decryptable="skipped",
        export_artifact_valid="skipped",
        secret_results=[
            run.doctor_mod.DoctorSecretResult(
                label="DASHBOARD_SECRET_DO_NOT_REPLACE",
                provided=True,
                stages=[
                    run.doctor_mod.DoctorStage(
                        "summary_authenticates",
                        "passed",
                        "DASHBOARD_SECRET_DO_NOT_REPLACE",
                        "AES-GCM authentication passed",
                    )
                ],
            ),
            run.doctor_mod.DoctorSecretResult(
                label="COMPARISON_SECRET",
                provided=True,
                stages=[
                    run.doctor_mod.DoctorStage(
                        "summary_authenticates",
                        "failed",
                        "COMPARISON_SECRET",
                        "bad % data\nnext\rline",
                    )
                ],
            ),
        ],
        stages=[
            run.doctor_mod.DoctorStage(
                "ui_handoff_boundary_reached",
                "passed",
                "",
                "encryption, storage, and data-contract checks reached the browser/UI boundary",
            )
        ],
        dashboard_html_path=config.pages_index_path.as_posix(),
    )
    monkeypatch.setattr(
        run.doctor_mod,
        "diagnose_dashboard_artifact",
        lambda _path, *, configured_data_mode, secrets, retained_data_dir: staged_result,
    )

    run.run_doctor(config)

    output = capsys.readouterr().out
    expected = "".join(
        [
            "::warning title=Reponomics doctor key check::COMPARISON_SECRET failed ",
            "at stage summary_authenticates: bad %25 data%0Anext%0Dline\n",
        ]
    )
    assert output == expected


def test_doctor_mode_validates_plaintext_dashboard_without_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    summary_path = tmp_path / "summary.md"
    config = _config(
        tmp_path,
        mode="publish",
        data_mode="plaintext",
        dashboard_secret="",
        generate_readme=False,
    )
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    doctor_config = _config(
        tmp_path,
        mode="doctor",
        data_mode="plaintext",
        dashboard_secret="",
        comparison_secret="",
    )
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setattr(
        run.requests,
        "get",
        lambda *_args, **_kwargs: pytest.fail("plaintext doctor should not query Pages API"),
    )

    run.run_doctor(doctor_config)

    summary = summary_path.read_text(encoding="utf-8")
    assert "- Configured data mode: `plaintext`" in summary
    assert "- Detected dashboard mode: `plaintext`" in summary
    assert "| Key cryptographically accepted | `skipped` |" in summary
    assert "| Dashboard data semantically consistent | `passed` |" in summary
    assert (
        "| `DASHBOARD_SECRET_DO_NOT_REPLACE` | not provided | `skipped` | `skipped` | secret was not configured |"
        in summary
    )
    assert "| `ui_handoff_boundary_reached` | `passed` |" in summary

    report = json.loads(
        (tmp_path / ".reponomics" / "doctor" / "doctor-report.json").read_text(encoding="utf-8")
    )
    assert report["configured_data_mode"] == "plaintext"
    assert report["detected_dashboard_mode"] == "plaintext"
    assert report["key_cryptographically_accepted"] == "skipped"
    assert report["retained_data_artifact_decryptable"] == "passed"
    assert _report_stage(report, "pages_configuration_found")["status"] == "skipped"


def test_doctor_mode_supports_single_stored_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    doctor_config = _config(
        tmp_path,
        mode="doctor",
        dashboard_secret=OLD_KEY,
        comparison_secret="",
    )
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())

    run.run_doctor(doctor_config)

    summary = summary_path.read_text(encoding="utf-8")
    assert "- Provided keys checked: `1`" in summary
    assert "- Keys cryptographically accepted: `1`" in summary
    assert (
        "| `COMPARISON_SECRET` | not provided | `skipped` | `skipped` | secret was not configured |"
    ) in summary
    report = json.loads(
        (tmp_path / ".reponomics" / "doctor" / "doctor-report.json").read_text(encoding="utf-8")
    )
    assert report["secret_results"][0]["label"] == "DASHBOARD_SECRET_DO_NOT_REPLACE"
    assert report["secret_results"][0]["accepted"] is True
    assert report["secret_results"][1]["label"] == "COMPARISON_SECRET"
    assert report["secret_results"][1]["provided"] is False
    assert report["export_artifact_valid"] == "passed"


def test_doctor_browser_contract_constants_match_renderer_and_secure_runtime() -> None:
    secure_runtime = run.render_dashboard.SECURE_RUNTIME_JS

    assert (
        run.doctor_mod.EXPECTED_DASHBOARD_DATA_VERSION
        == run.render_dashboard.DASHBOARD_DATA_VERSION
    )
    assert run.doctor_mod.EXPECTED_KDF_NAME == "PBKDF2"
    assert run.doctor_mod.EXPECTED_KDF_HASH == "SHA-256"
    assert run.doctor_mod.EXPECTED_KDF_ITERATIONS == run.render_dashboard.PBKDF2_ITERATIONS
    assert run.doctor_mod.EXPECTED_SALT_BYTES == run.render_dashboard.PBKDF2_SALT_BYTES
    assert run.doctor_mod.EXPECTED_IV_BYTES == run.render_dashboard.AES_GCM_IV_BYTES

    expected_version_const = (
        "const EXPECTED_DASHBOARD_DATA_VERSION = "
        + f"{run.doctor_mod.EXPECTED_DASHBOARD_DATA_VERSION};"
    )
    assert expected_version_const in secure_runtime
    assert "const EXPECTED_CIPHER = 'AES-GCM';" in secure_runtime
    assert f"const EXPECTED_KDF_NAME = '{run.doctor_mod.EXPECTED_KDF_NAME}';" in secure_runtime
    assert f"const EXPECTED_KDF_HASH = '{run.doctor_mod.EXPECTED_KDF_HASH}';" in secure_runtime
    assert (
        f"const EXPECTED_KDF_ITERATIONS = {run.doctor_mod.EXPECTED_KDF_ITERATIONS};"
        in secure_runtime
    )
    assert f"const EXPECTED_SALT_BYTES = {run.doctor_mod.EXPECTED_SALT_BYTES};" in secure_runtime
    assert f"const EXPECTED_IV_BYTES = {run.doctor_mod.EXPECTED_IV_BYTES};" in secure_runtime
    assert r"/^c[0-9]{4,}$/.test(chunkId)" in secure_runtime


@pytest.mark.parametrize(
    ("mutation", "expected_stage"),
    [
        ("version", "browser_envelope_version_valid"),
        ("cipher", "browser_envelope_cipher_valid"),
        ("kdf", "browser_envelope_kdf_valid"),
        ("encoding", "browser_envelope_encoding_valid"),
        ("salt", "browser_envelope_salt_valid"),
        ("summary_token", "browser_envelope_summary_token_valid"),
        ("chunks_object", "browser_envelope_chunks_object_valid"),
        ("chunk_count", "browser_envelope_chunk_count_valid"),
        ("chunk_id", "browser_envelope_chunk_ids_valid"),
        ("chunk_token", "browser_envelope_chunk_ids_valid"),
    ],
)
def test_doctor_encrypted_browser_contract_rejects_runtime_invalid_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
    expected_stage: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    encrypted_data = _dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
    )
    _mutate_encrypted_dashboard_contract(encrypted_data, mutation)
    _write_dashboard_json(
        config.pages_index_path,
        dashboard,
        "encrypted-dashboard-data",
        "encrypted-dashboard-data.json",
        encrypted_data,
    )

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
    )

    assert result.browser_payload_contract_valid == "failed"
    assert _result_stage(result, expected_stage).status == "failed"
    assert result.ui_handoff_reached is False


def _mutate_encrypted_dashboard_contract(data: dict[str, Any], mutation: str) -> None:
    if mutation == "version":
        data["version"] = run.doctor_mod.EXPECTED_DASHBOARD_DATA_VERSION + 1
    elif mutation == "cipher":
        data["cipher"] = "AES-CBC"
    elif mutation == "kdf":
        data["kdf"] = {**data["kdf"], "iterations": run.doctor_mod.EXPECTED_KDF_ITERATIONS + 1}
    elif mutation == "encoding":
        data["encoding"] = "json"
    elif mutation == "salt":
        data["salt"] = base64.b64encode(b"too-short").decode("ascii")
    elif mutation == "summary_token":
        data["summary"] = "not-a-valid-token"
    elif mutation == "chunks_object":
        data["chunks"] = []
    elif mutation == "chunk_count":
        data["chunk_count"] = int(data["chunk_count"]) + 1
    elif mutation == "chunk_id":
        first_chunk_id = next(iter(data["chunks"]))
        data["chunks"]["bad-id"] = data["chunks"].pop(first_chunk_id)
    elif mutation == "chunk_token":
        first_chunk_id = next(iter(data["chunks"]))
        data["chunks"][first_chunk_id] = "not-a-valid-token"
    else:
        raise AssertionError(f"unhandled mutation: {mutation}")


def test_doctor_pages_preflight_reports_workflow_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    summary_path = tmp_path / "summary.md"
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    calls: list[tuple[str, dict[str, str], int]] = []

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> requests.Response:
        calls.append((url, headers, timeout))
        return _response(200, payload={"build_type": "workflow", "status": "built"})

    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_path.as_posix())
    monkeypatch.setattr(run.requests, "get", fake_get)
    doctor_config = _config(
        tmp_path,
        mode="doctor",
        dashboard_secret=OLD_KEY,
        github_token="ghp_pages",
    )

    run.run_doctor(doctor_config)

    assert calls == [
        (
            "https://api.github.com/repos/demo/repo/pages",
            run._github_api_headers("ghp_pages"),
            run.INCIDENT_API_TIMEOUT_SECONDS,
        )
    ]
    report = json.loads(
        (tmp_path / ".reponomics" / "doctor" / "doctor-report.json").read_text(encoding="utf-8")
    )
    assert _report_stage(report, "pages_configuration_found") == {
        "name": "pages_configuration_found",
        "status": "passed",
        "subject": "GitHub Pages",
        "detail": "GitHub Pages configuration is available",
    }
    assert _report_stage(report, "pages_source_valid")["status"] == "passed"
    assert _report_stage(report, "pages_deployment_permission_valid")["status"] == "skipped"
    assert _report_stage(report, "pages_latest_deployment_valid")["status"] == "passed"
    summary = summary_path.read_text(encoding="utf-8")
    assert "| Pages deployability preflight | `passed` |" in summary


def test_doctor_pages_preflight_reports_permission_denial_without_key_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/repo")
    monkeypatch.setattr(
        run.requests,
        "get",
        lambda *_args, **_kwargs: _response(403, text="forbidden"),
    )
    doctor_config = _config(
        tmp_path,
        mode="doctor",
        dashboard_secret=OLD_KEY,
        github_token="ghp_pages",
    )

    run.run_doctor(doctor_config)

    report = json.loads(
        (tmp_path / ".reponomics" / "doctor" / "doctor-report.json").read_text(encoding="utf-8")
    )
    assert report["key_cryptographically_accepted"] == "passed"
    assert _report_stage(report, "pages_configuration_found")["status"] == "warning"
    assert _report_stage(report, "pages_deployment_permission_valid")["status"] == "warning"


def test_doctor_export_diagnostics_detect_ciphertext_tampering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    export_manifest = _dashboard_json(
        config.pages_index_path, dashboard, "export-manifest", "export-manifest.json"
    )
    asset_path = config.pages_index_path.parent / export_manifest["asset"]
    ciphertext = bytearray(asset_path.read_bytes())
    ciphertext[0] ^= 1
    asset_path.write_bytes(bytes(ciphertext))

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
    )

    assert result.key_cryptographically_accepted == "passed"
    assert result.export_artifact_valid == "failed"
    assert result.ui_handoff_reached is True
    assert any(
        stage.name == "export_ciphertext_hash_valid" and stage.status == "failed"
        for stage in result.stages
    )
    compatibility_result = run.doctor_mod.check_dashboard_key(config.pages_index_path, OLD_KEY)
    assert compatibility_result.ok is True


def test_doctor_export_diagnostics_detect_plaintext_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    dashboard = config.pages_index_path.read_text(encoding="utf-8")
    export_manifest = _dashboard_json(
        config.pages_index_path, dashboard, "export-manifest", "export-manifest.json"
    )
    export_manifest["plaintext_sha256"] = "0" * 64
    _write_dashboard_json(
        config.pages_index_path,
        dashboard,
        "export-manifest",
        "export-manifest.json",
        export_manifest,
    )

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
    )

    assert result.key_cryptographically_accepted == "passed"
    assert result.export_artifact_valid == "failed"
    assert result.ui_handoff_reached is True
    assert any(
        stage.name == "export_plaintext_hash_valid"
        and stage.status == "failed"
        and stage.subject == "DASHBOARD_SECRET_DO_NOT_REPLACE"
        for stage in result.stages
    )


def test_doctor_retained_artifact_decrypts_with_stored_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)
    run.crypto_artifact.encrypt(
        config.data_dir,
        config.data_dir / "dashboard-data.enc",
        "DASHBOARD_SECRET_DO_NOT_REPLACE",
    )

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
        retained_data_dir=config.data_dir,
    )

    assert result.key_cryptographically_accepted == "passed"
    assert result.retained_data_artifact_decryptable == "passed"
    assert any(
        stage.name == "retained_artifact_decrypts"
        and stage.status == "passed"
        and stage.subject == "DASHBOARD_SECRET_DO_NOT_REPLACE"
        for stage in result.stages
    )
    assert any(
        stage.name == "retained_artifact_schema_valid" and stage.status == "passed"
        for stage in result.stages
    )


def test_doctor_retained_artifact_reports_wrong_retained_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, mode="publish", generate_readme=False)
    _seed_log(config.data_dir)
    run.validate_config(config)
    run.run_publish(config, restore_artifact=False)

    monkeypatch.setenv("DASHBOARD_SECRET_DO_NOT_REPLACE", NEXT_KEY)
    run.crypto_artifact.encrypt(
        config.data_dir,
        config.data_dir / "dashboard-data.enc",
        "DASHBOARD_SECRET_DO_NOT_REPLACE",
    )

    result = run.doctor_mod.diagnose_dashboard_artifact(
        config.pages_index_path,
        configured_data_mode="encrypted",
        secrets=[("DASHBOARD_SECRET_DO_NOT_REPLACE", OLD_KEY)],
        retained_data_dir=config.data_dir,
    )

    assert result.key_cryptographically_accepted == "passed"
    assert result.retained_data_artifact_decryptable == "failed"
    assert result.ui_handoff_reached is True
    assert any(
        stage.name == "retained_artifact_decrypts"
        and stage.status == "failed"
        and stage.subject == "DASHBOARD_SECRET_DO_NOT_REPLACE"
        for stage in result.stages
    )


def test_doctor_retained_artifact_rejects_tar_links(tmp_path: Path) -> None:
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        symlink = tarfile.TarInfo("link")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "../outside"
        archive.addfile(symlink)

        payload = b"outside write"
        linked_file = tarfile.TarInfo("link/payload.txt")
        linked_file.size = len(payload)
        archive.addfile(linked_file, io.BytesIO(payload))

    with pytest.raises(ValueError, match="Refusing unsafe artifact member"):
        doctor_retained._safe_extract_retained_tar(
            archive_bytes.getvalue(),
            tmp_path / "extract",
        )

    assert not (tmp_path / "outside" / "payload.txt").exists()
