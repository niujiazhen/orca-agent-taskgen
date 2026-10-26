"""Install the built wheel in an isolated venv and run a text-to-env smoke test."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from zipfile import ZipFile


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
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        for retired in ("train.py", "evaluate.py", "ppo_acceptance.py"):
            if f"orca_sim/taskgen/{retired}" in names:
                raise RuntimeError("Wheel contains a retired training module; rebuild with python -m build in isolation")
        for required in ("photo_env.py", "photo_upload.py", "blender.py", "blender_worker.py", "mesh_scene.py",
                         "schemas/scene_spec_v1.schema.json", "schemas/scene_spec_v2.schema.json",
                         "schemas/blender_object_plan.schema.json", "schemas/task_spec_v3.schema.json"):
            if f"orca_sim/taskgen/{required}" not in names:
                raise RuntimeError(f"Wheel missing photo resource: {required}")

    _clear_build_path(SMOKE_ROOT)
    _clear_build_path(BUNDLE_ROOT)
    venv.EnvBuilder(with_pip=True).create(SMOKE_ROOT)
    python = SMOKE_ROOT / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    subprocess.run(
        [python, "-m", "pip", "install", str(wheels[0])+"[photo,visualization]"],
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
        [python, str(ROOT/"scripts/photo_smoke.py"), "--output", str(ROOT/"build/ci-wheel-photo")],
        check=True,
        cwd=ROOT,
    )
    # Mesh bundles must run from an isolated wheel without importing bpy or
    # invoking Blender. Move the bundle before loading to check relative assets.
    mesh_smoke = """
from pathlib import Path
import shutil, sys, tempfile
from orca_sim.taskgen import load_scene
from orca_sim.taskgen.photo_scene import check_scene
with tempfile.TemporaryDirectory(prefix='orca-wheel-mesh-') as temp:
    bundle = Path(temp)/'mesh-scene'
    shutil.copytree(sys.argv[1], bundle)
    assert check_scene(bundle)['physics'] == 'pass'
    scene = load_scene(bundle)
    try:
        scene.step(500)
        assert scene.render().shape == (480,640,3)
        assert scene.render(collision=True).shape == (480,640,3)
    finally:
        scene.close()
print('Installed wheel: relocated Blender mesh bundle loads, steps and renders')
"""
    subprocess.run([python, "-c", mesh_smoke,
                    str(ROOT/"examples/blender/five_objects/scene/blender_five_objects")], check=True, cwd=ROOT)
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
