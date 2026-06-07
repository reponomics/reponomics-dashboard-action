"""Shared types for GitHub collection modules."""

from collections.abc import Mapping
from typing import Any, TypedDict

Headers = Mapping[str, str]
RepoMetadata = dict[str, Any]


class NetworkWarning(TypedDict):
    url: str
    attempt: int
    error_type: str
    message: str

