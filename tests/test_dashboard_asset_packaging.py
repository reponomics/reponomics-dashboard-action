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

    script_root = "dashboard_action/runtime/scripts/render_dashboard_support"
    assert f"{script_root}/access.py" in names
    assert f"{script_root}/html.py" in names
    assert f"{script_root}/status.py" in names

    asset_root = f"{script_root}/assets/static"
    expected_assets = {
        "base.css",
        "demo-unlock.css",
        "font-face.css",
        "public-bootstrap.js",
        "runtime-app.js",
        "runtime-chart-options.js",
        "runtime-charts.js",
        "runtime-controls.js",
        "runtime-data-provider.js",
        "runtime-format.js",
        "runtime-momentum.js",
        "runtime-quality-calendar.js",
        "runtime-selection.js",
        "runtime-series.js",
        "runtime-state.js",
        "runtime-tables.js",
        "runtime-theme.js",
        "secure-runtime.js",
        "theme-bootstrap.js",
    }
    for asset_name in expected_assets:
        assert f"{asset_root}/{asset_name}" in names
