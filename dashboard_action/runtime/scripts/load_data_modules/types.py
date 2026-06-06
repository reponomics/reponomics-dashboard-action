"""Shared type aliases for CSV-backed dashboard aggregation helpers."""

from typing import Any, TypeAlias

Row: TypeAlias = dict[str, Any]
Rows: TypeAlias = list[Row]
Result: TypeAlias = dict[str, Any]
Candidate: TypeAlias = dict[str, Any]
