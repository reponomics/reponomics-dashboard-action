"""Collection-quality narrative recipe."""

from __future__ import annotations

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_values import add_candidate, evidence, int_value
from load_data_modules.types import Candidate, Row, Rows

GAP_ENDPOINT_STATES = {"pending", "unsupported", "no_content", "error"}


def data_gap_not_product_signal(
    candidates: list[Candidate], context: NarrativeContext
) -> None:
    """Flag collection gaps that may explain misleading metric movement."""
    weak_days = weak_collection_days(context.collection_day_rows)
    endpoint_gaps = endpoint_gap_rows(context)
    if weak_days or endpoint_gaps:
        add_data_gap_candidate(candidates, weak_days, endpoint_gaps)


def weak_collection_days(rows: Rows) -> Rows:
    """Return non-healthy collection-day rows."""
    return [row for row in rows if is_weak_collection_day(row)]


def is_weak_collection_day(row: Row) -> bool:
    """Return whether a collection day should qualify as incomplete."""
    status = str(row.get("status") or "")
    has_repo_errors = int_value(row.get("error_repos")) > 0
    has_skips = int_value(row.get("skipped_repos")) > 0
    return status not in {"healthy", "ok", ""} or has_repo_errors or has_skips


def endpoint_gap_rows(context: NarrativeContext) -> Rows:
    """Return endpoint rows with unavailable context states."""
    return [
        row
        for rows in context.endpoint_status.values()
        for row in rows
        if str(row.get("status") or "") in GAP_ENDPOINT_STATES
    ]


def add_data_gap_candidate(
    candidates: list[Candidate], weak_days: Rows, endpoint_gaps: Rows
) -> None:
    """Append a data-quality narrative candidate."""
    latest_day = max(weak_days, key=lambda row: row.get("ts", ""), default={})
    latest_endpoint = max(
        endpoint_gaps, key=lambda row: row.get("captured_at", ""), default={}
    )
    add_candidate(
        candidates,
        subtype="data_gap_not_product_signal",
        tone="data_quality",
        repo=str(latest_endpoint.get("repo") or ""),
        metric="collection",
        score=100 + len(weak_days) + len(endpoint_gaps),
        confidence="high",
        headline="Some movement may be a data gap, not a product signal",
        body=data_gap_detail(latest_day, latest_endpoint),
        evidence=[
            evidence("collection days", f"{len(weak_days):,}"),
            evidence("endpoint gaps", f"{len(endpoint_gaps):,}"),
            evidence("latest endpoint", str(latest_endpoint.get("endpoint_key") or "")),
            evidence("endpoint status", str(latest_endpoint.get("status") or "")),
        ],
    )


def data_gap_detail(collection_day: Row, endpoint_row: Row) -> str:
    """Return data-gap explanatory copy."""
    parts = [
        text
        for text in (
            collection_day_detail(collection_day),
            endpoint_gap_detail(endpoint_row),
            "Treat affected windows as incomplete before comparing them to normal weeks.",
        )
        if text
    ]
    return " ".join(parts)


def collection_day_detail(row: Row) -> str:
    """Return collection-day detail text."""
    if not row:
        return ""
    status = str(row.get("status") or "a non-healthy day")
    ts = str(row.get("ts") or "the latest affected day")
    return f"The collection calendar shows {status} on {ts}."


def endpoint_gap_detail(row: Row) -> str:
    """Return endpoint-gap detail text."""
    if not row:
        return ""
    endpoint = str(row.get("endpoint_key") or "context")
    status = str(row.get("status") or "an unavailable state")
    return f"The {endpoint} endpoint reported {status}."
