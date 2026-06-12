from pathlib import Path

import pytest

from scripts.repo_paths import find_repo_root


def test_find_repo_root_from_nested_file(tmp_path):
    project = tmp_path / "project"
    nested = project / "scripts" / "release"
    nested.mkdir(parents=True)
    marker = project / "pyproject.toml"
    marker.write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    script = nested / "publish.py"
    script.write_text("", encoding="utf-8")

    assert find_repo_root(script) == project


def test_find_repo_root_raises_without_project_marker(tmp_path):
    with pytest.raises(RuntimeError, match="pyproject.toml"):
        find_repo_root(Path(tmp_path / "scripts" / "tool.py"))
