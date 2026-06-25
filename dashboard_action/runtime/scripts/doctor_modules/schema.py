"""Decoded dashboard summary and chunk schema diagnostics."""

from __future__ import annotations

from typing import Any

from doctor_support import (
    DashboardDoctorError as _DashboardDoctorError,
    DoctorStage,
    _object_dict,
    _stage,
)


def _validate_summary(summary: dict[str, Any]) -> None:
    """Raise when a summary object lacks required dashboard fields."""
    if not isinstance(summary.get("repos"), list):
        raise _DashboardDoctorError("schema", "dashboard summary repos are missing")
    if not isinstance(summary.get("totals"), dict):
        raise _DashboardDoctorError("schema", "dashboard summary totals are missing")
    if not isinstance(summary.get("repo_chunks"), dict):
        raise _DashboardDoctorError("schema", "dashboard summary repo_chunks are missing")


def _validate_summary_staged(summary: Any) -> tuple[dict[str, str], int, list[DoctorStage]]:
    """Validate summary shape and return repo-to-chunk mappings with stages."""
    if not isinstance(summary, dict):
        return {}, 0, _non_object_summary_stages()

    missing = _missing_summary_fields(summary)
    if missing:
        return _invalid_summary_field_result(summary, missing)

    repo_count = len(summary["repos"])
    invalid = _invalid_repo_chunk_mappings(summary["repo_chunks"])
    if invalid:
        return (
            {},
            repo_count,
            [
                _stage("summary_min_schema_valid", "passed", "summary has required fields"),
                _stage(
                    "summary_repo_chunk_mapping_valid",
                    "failed",
                    "repo_chunks contains invalid mappings: " + ", ".join(invalid[:5]),
                ),
            ],
        )

    repo_chunks = dict(summary["repo_chunks"])
    return repo_chunks, repo_count, _valid_summary_stages(repo_chunks)


def _non_object_summary_stages() -> list[DoctorStage]:
    """Return stages for a summary value that is not a JSON object."""
    return [
        _stage("summary_min_schema_valid", "failed", "summary was not a JSON object"),
        _stage("summary_repo_chunk_mapping_valid", "skipped", "summary schema was invalid"),
    ]


def _missing_summary_fields(summary: dict[str, Any]) -> list[str]:
    """Return required summary fields that are missing or have the wrong type."""
    return [
        field
        for field, expected_type in (("repos", list), ("totals", dict), ("repo_chunks", dict))
        if not isinstance(summary.get(field), expected_type)
    ]


def _invalid_summary_field_result(
    summary: dict[str, Any],
    missing: list[str],
) -> tuple[dict[str, str], int, list[DoctorStage]]:
    """Return the staged result for a summary missing required typed fields."""
    repo_count = _repo_count_if_available(summary)
    return (
        {},
        repo_count,
        [
            _stage(
                "summary_min_schema_valid",
                "failed",
                "dashboard summary missing or invalid fields: " + ", ".join(missing),
            ),
            _stage("summary_repo_chunk_mapping_valid", "skipped", "summary schema was invalid"),
        ],
    )


def _repo_count_if_available(summary: dict[str, Any]) -> int:
    """Return the summary repo count when the repos list is available."""
    repos = summary.get("repos")
    return len(repos) if isinstance(repos, list) else 0


def _invalid_repo_chunk_mappings(repo_chunks: Any) -> list[str]:
    """Return repo_chunks mappings whose keys or values are not strings."""
    if not isinstance(repo_chunks, dict):
        return []
    return [
        f"{repo_name!r}->{chunk_id!r}"
        for repo_name, chunk_id in repo_chunks.items()
        if not isinstance(repo_name, str) or not isinstance(chunk_id, str)
    ]


def _valid_summary_stages(repo_chunks: dict[str, str]) -> list[DoctorStage]:
    """Return stages for a summary whose required schema and mappings are valid."""
    return [
        _stage("summary_min_schema_valid", "passed", "summary has required fields"),
        _stage(
            "summary_repo_chunk_mapping_valid",
            "passed",
            f"summary maps {len(repo_chunks)} repos to chunks",
        ),
    ]


def _validate_chunk(repo_name: str, chunk_id: str, chunk: dict[str, Any]) -> None:
    """Raise when a decoded chunk does not match the required repository schema."""
    if chunk.get("repo") != repo_name:
        raise _DashboardDoctorError(
            "schema",
            f"dashboard chunk {chunk_id} did not match repository {repo_name}",
        )
    for field in ("repo_series", "repo_weekday", "repo_referrers", "repo_paths", "growth"):
        if field not in chunk:
            raise _DashboardDoctorError(
                "schema",
                f"dashboard chunk {chunk_id} was missing required field {field}",
            )


def _validate_chunk_staged(repo_name: str, chunk_id: str, chunk: Any) -> list[DoctorStage]:
    """Validate one decoded chunk and return diagnostic stages."""
    subject = f"{repo_name}:{chunk_id}"
    if not isinstance(chunk, dict):
        return [_stage("chunk_min_schema_valid", "failed", "chunk was not a JSON object", subject)]
    missing = _missing_chunk_fields(chunk)
    return [
        _chunk_required_fields_stage(missing, subject),
        _chunk_repo_matches_summary_stage(chunk, repo_name, subject),
        _chunk_growth_contract_stage(chunk, subject),
    ]


def _missing_chunk_fields(chunk: dict[str, Any]) -> list[str]:
    """Return required chunk fields that are absent."""
    return [
        field
        for field in ("repo_series", "repo_weekday", "repo_referrers", "repo_paths", "growth")
        if field not in chunk
    ]


def _chunk_required_fields_stage(missing: list[str], subject: str) -> DoctorStage:
    """Return whether a chunk has the required top-level fields."""
    return _stage(
        "chunk_min_schema_valid",
        "passed" if not missing else "failed",
        "chunk has required fields"
        if not missing
        else "chunk missing fields: " + ", ".join(missing),
        subject,
    )


def _chunk_repo_matches_summary_stage(
    chunk: dict[str, Any],
    repo_name: str,
    subject: str,
) -> DoctorStage:
    """Return whether a chunk repository name matches the summary mapping."""
    return _stage(
        "chunk_repo_matches_summary",
        "passed" if chunk.get("repo") == repo_name else "failed",
        (
            "chunk repo matches summary mapping"
            if chunk.get("repo") == repo_name
            else f"chunk repo {chunk.get('repo')!r} did not match {repo_name!r}"
        ),
        subject,
    )


def _chunk_growth_contract_stage(chunk: dict[str, Any], subject: str) -> DoctorStage:
    """Return whether a chunk includes the per-repository growth series."""
    growth = _object_dict(chunk.get("growth"))
    per_repo = _object_dict(growth.get("per_repo"))
    series_ok = isinstance(per_repo.get("series"), dict)
    return _stage(
        "chunk_growth_contract_valid",
        "passed" if series_ok else "failed",
        "chunk growth contains per-repo series"
        if series_ok
        else "chunk growth missing per_repo.series",
        subject,
    )


def _semantic_counts_stage(
    repo_count: int,
    repo_chunks: dict[str, str],
    chunks: dict[str, Any],
) -> DoctorStage:
    """Return whether summary repo mappings and emitted chunks agree."""
    expected_chunk_ids = set(repo_chunks.values())
    actual_chunk_ids = set(chunks)
    if repo_count != len(repo_chunks):
        return _stage(
            "semantic_counts_valid",
            "failed",
            f"repo count {repo_count} did not match repo_chunks count {len(repo_chunks)}",
        )
    if expected_chunk_ids != actual_chunk_ids:
        missing = sorted(expected_chunk_ids - actual_chunk_ids)
        orphaned = sorted(actual_chunk_ids - expected_chunk_ids)
        detail = []
        if missing:
            detail.append("missing chunks: " + ", ".join(missing[:5]))
        if orphaned:
            detail.append("orphan chunks: " + ", ".join(orphaned[:5]))
        return _stage("semantic_counts_valid", "failed", "; ".join(detail))
    return _stage("semantic_counts_valid", "passed", "repo, mapping, and chunk counts agree")
