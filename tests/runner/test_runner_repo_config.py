from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_action import run


def test_repo_config_accepts_max_length_repository_full_name(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    owner = "o" * 39
    repo_name = "r" * 100
    config_path.write_text(
        f"include_only:\n  - {owner}/{repo_name}\nmax_repos: 1\n",
        encoding="utf-8",
    )

    config = run.repo_config.load_repo_config(str(config_path))

    assert config["include_only"] == [f"{owner}/{repo_name}"]


@pytest.mark.parametrize(
    "repo_name",
    [
        "owner-with-forty-characters-xxxxxxxxxxxx/repo",
        "owner/" + ("r" * 101),
        "owner/repo.git",
        "owner/repo.wiki",
        "owner/.",
        "owner/..",
        "-owner/repo",
        "owner-/repo",
        "owner/repo name",
        "owner/repo;echo-pwned",
        "owner/repo$(echo pwned)",
        "owner/repo\nEVIL=1",
    ],
)
def test_repo_config_rejects_invalid_repository_full_names(
    tmp_path: Path,
    repo_name: str,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"include_only:\n  - {repo_name!r}\nmax_repos: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid repository entry"):
        run.repo_config.load_repo_config(str(config_path))


def test_repo_config_rejects_non_string_repository_entries(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("include_only:\n  - 123\nmax_repos: 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="repository entries must be strings"):
        run.repo_config.load_repo_config(str(config_path))
