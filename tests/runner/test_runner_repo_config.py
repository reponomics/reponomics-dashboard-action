from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_action import run


def _write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_repo_config_normalizes_bare_names_to_dashboard_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("GITHUB_REPOSITORY", "demo/dashboard")
    _write_config(
        config_path,
        """
collect:
  repositories:
    - api
    - other-owner/sdk
publish:
  repositories:
    - api
""",
    )

    config = run.repo_config.load_repo_config(str(config_path))

    assert config["collect_repositories"] == ["demo/api", "other-owner/sdk"]
    assert config["publish_repositories"] == ["demo/api"]
    assert config["max_collect_repos"] == 100
    assert config["max_publish_repos"] == 8


def test_repo_config_accepts_max_length_full_name(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    owner = "o" * 39
    repo_name = "r" * 100
    repo = f"{owner}/{repo_name}"
    _write_config(
        config_path,
        f"""
collect:
  repositories:
    - {repo}
publish:
  repositories:
    - {repo}
""",
    )

    config = run.repo_config.load_repo_config(str(config_path))

    assert config["collect_repositories"] == [repo]
    assert config["publish_repositories"] == [repo]


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
def test_repo_config_rejects_invalid_repository_names(
    tmp_path: Path,
    repo_name: str,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        f"""
collect:
  repositories:
    - {repo_name!r}
publish:
  repositories:
    - owner/valid
""",
    )

    with pytest.raises(ValueError, match="invalid repository entry"):
        run.repo_config.load_repo_config(str(config_path))


def test_repo_config_rejects_bare_names_without_dashboard_owner(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
collect:
  repositories:
    - api
publish:
  repositories:
    - api
""",
    )

    with pytest.raises(ValueError, match="bare repository names require"):
        run.repo_config.load_repo_config(str(config_path))


def test_repo_config_rejects_non_string_repository_entries(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
collect:
  repositories:
    - 123
publish:
  repositories:
    - owner/repo
""",
    )

    with pytest.raises(ValueError, match="repository entries must be strings"):
        run.repo_config.load_repo_config(str(config_path))


def test_repo_config_requires_publish_subset_of_collect(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
collect:
  repositories:
    - owner/api
publish:
  repositories:
    - owner/web
""",
    )

    with pytest.raises(ValueError, match="not listed in 'collect.repositories'"):
        run.repo_config.load_repo_config(str(config_path))


def test_repo_config_rejects_publish_list_over_dashboard_cap(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    repos = "\n".join(f"    - owner/repo-{idx}" for idx in range(9))
    _write_config(
        config_path,
        f"""
collect:
  repositories:
{repos}
publish:
  repositories:
{repos}
""",
    )

    with pytest.raises(ValueError, match="dashboard cap is 8"):
        run.repo_config.load_repo_config(str(config_path))


def test_repo_config_rejects_removed_selection_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
collect:
  repositories:
    - owner/api
publish:
  repositories:
    - owner/api
include_others: true
""",
    )

    with pytest.raises(ValueError, match="removed repository-selection key"):
        run.repo_config.load_repo_config(str(config_path))
