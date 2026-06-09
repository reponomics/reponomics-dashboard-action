"""Dashboard access-mode parsing."""

from __future__ import annotations

import os


ACCESS_MODE_ENV = "DASHBOARD_ACCESS_MODE"
ACCESS_MODE_PUBLIC = "public"
ACCESS_MODE_ENCRYPTED = "encrypted"
ACCESS_MODE_LEGACY_SHARED_SECRET = "shared-secret"


def load_access_mode() -> str:
    """Return the configured dashboard access mode."""
    mode = os.environ.get(ACCESS_MODE_ENV, ACCESS_MODE_PUBLIC).strip().lower()
    if not mode:
        mode = ACCESS_MODE_PUBLIC
    if mode == ACCESS_MODE_LEGACY_SHARED_SECRET:
        mode = ACCESS_MODE_ENCRYPTED
    if mode not in {ACCESS_MODE_PUBLIC, ACCESS_MODE_ENCRYPTED}:
        raise ValueError(
            f"Unsupported {ACCESS_MODE_ENV}={mode!r}. "
            + f"Use {ACCESS_MODE_PUBLIC!r} or {ACCESS_MODE_ENCRYPTED!r}."
        )
    return mode
