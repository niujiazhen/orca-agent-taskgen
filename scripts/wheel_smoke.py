"""Install the built wheel in an isolated venv and run a text-to-env smoke test."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE_ROOT = ROOT / "build" / "ci-wheel-smoke"
BUNDLE_ROOT = ROOT / "build" / "ci-wheel-bundle"


def _clear_build_path(path: Path) -> None:
    resolved = path.resolve()
    build_root = (ROOT / "build").resolve()
    if resolved == build_root or build_root not in resolved.parents:
        raise RuntimeError(f"refusing to remove path outside the build directory: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def main() -> None:
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', project_text, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError("project version is missing from pyproject.toml")
    package_version = match.group(1)
    wheels = sorted((ROOT / "dist").glob(f"orca_sim-{package_version}-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel in dist, found {len(wheels)}")

    _clear_build_path(SMOKE_ROOT)
    _clear_build_path(BUNDLE_ROOT)
    venv.EnvBuilder(with_pip=True).create(SMOKE_ROOT)
    python = SMOKE_ROOT / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    subprocess.run(
        [python, "-m", "pip", "install", str(wheels[0])],
        check=True,
    )
    subprocess.run(
        [
            python,
            "-m",
            "orca_sim.taskgen.cli",
            "generate-text",
            "Pick up the red cube",
            "--env-id",
            "WheelSmoke-v0",
            "--output",
            str(BUNDLE_ROOT),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run(
        [
            python,
            "-m",
            "orca_sim.taskgen.cli",
            "check-runtime",
            str(BUNDLE_ROOT / "wheelsmoke_v0"),
            "--steps",
            "200",
        ],
        check=True,
        cwd=ROOT,
    )


if __name__ == "__main__":
    main()
