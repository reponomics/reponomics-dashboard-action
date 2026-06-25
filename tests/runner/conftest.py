from __future__ import annotations

from collections.abc import Generator

import pytest

from dashboard_action import run


@pytest.fixture(autouse=True)
def _runner_runtime_isolation(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    for key in {
        "GITHUB_ACTION_PATH",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_RUN_ID",
        "GITHUB_SHA",
        "REPONOMICS_ACTION_SHA",
    }:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(run.version_status, "_fetch_releases", lambda: [])
    run.collect_mod._reset_runtime_state()
    yield
    run.collect_mod._reset_runtime_state()
