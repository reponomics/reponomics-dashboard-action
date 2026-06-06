from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path


def test_dashboard_static_assets_are_included_in_built_wheel(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--wheel-dir",
            str(wheel_dir),
            "--no-deps",
            "--no-build-isolation",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    wheels = sorted(wheel_dir.glob("reponomics_dashboard_action-*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())

    script_root = "dashboard_action/runtime/scripts"
    assert f"{script_root}/render_dashboard_access.py" in names
    assert f"{script_root}/render_dashboard_html.py" in names
    assert f"{script_root}/render_dashboard_status.py" in names

    asset_root = "dashboard_action/runtime/scripts/render_dashboard_assets/static"
    assert f"{asset_root}/base.css" in names
    assert f"{asset_root}/app-runtime.js" in names
    assert f"{asset_root}/secure-runtime.js" in names
