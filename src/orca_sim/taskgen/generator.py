"""Deterministic renderer for accepted ORCA TaskSpec documents."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import yaml

from orca_sim.taskgen.contracts import (
    ContractError,
    load_gesture_reference,
    load_task_spec,
)

BASELINE_COMMIT = "02571cf7fbec1e57de615e61949d504440e2646a"
TASKGEN_ROOT = Path(__file__).resolve().parent
GENERATED_ROOT = TASKGEN_ROOT / "generated"


def _within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    root = root.resolve()
    return resolved == root or root in resolved.parents


def _slug(env_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", env_id).strip("_").lower()
    if not slug:
        raise ContractError("TaskSpec.task.env_id: cannot produce an output directory")
    return slug


def _numbers(values) -> str:
    return " ".join(f"{float(value):.12g}" for value in values)


def _hand_reset_qpos(spec: dict, gesture: dict) -> np.ndarray:
    first = np.asarray(gesture["samples"][0]["qpos"], dtype=np.float64)
    if spec["task"]["reset"]["hand_pose"] == "open":
        return first
    last = np.asarray(gesture["samples"][-1]["qpos"], dtype=np.float64)
    fraction = float(spec["task"]["reset"]["hand_closure_fraction"])
    return first + fraction * (last - first)


def _render_scene_v1(spec: dict, gesture: dict) -> str:
    task = spec["task"]
    obj = task["object"]
    reset = task["reset"]
    hand_qpos = _hand_reset_qpos(spec, gesture)
    object_pos = np.asarray(reset["object_position"], dtype=np.float64)
    radius = float(obj["radius"])
    half_length = float(obj["half_length"])
    mass = float(obj["mass"])
    transverse = mass * (3.0 * radius**2 + (2.0 * half_length) ** 2) / 12.0
    axial = 0.5 * mass * radius**2

    root = ET.Element("mujoco", {"model": task["env_id"]})
    ET.SubElement(root, "include", {"file": "../../../scenes/v1/scene.xml"})
    ET.SubElement(root, "include", {"file": "../../../models/v1/right.mjcf"})
    worldbody = ET.SubElement(root, "worldbody")
    body = ET.SubElement(
        worldbody,
        "body",
        {"name": "pinch_object", "pos": _numbers(object_pos), "quat": "1 0 0 0"},
    )
    ET.SubElement(body, "freejoint", {"name": "pinch_object_freejoint"})
    ET.SubElement(
        body,
        "inertial",
        {
            "pos": "0 0 0",
            "mass": f"{mass:.12g}",
            "diaginertia": _numbers([transverse, transverse, axial]),
        },
    )
    ET.SubElement(
        body,
        "geom",
        {
            "name": "pinch_object_geom",
            "type": "cylinder",
            "size": _numbers([radius, half_length]),
            "rgba": _numbers(obj["rgba"]),
            "friction": _numbers(obj["friction"]),
            "condim": "4",
        },
    )
    ET.SubElement(
        body,
        "site",
        {
            "name": "pinch_object_center",
            "type": "sphere",
            "size": "0.0015",
            "rgba": "1 1 1 0",
        },
    )
    keyframe = ET.SubElement(root, "keyframe")
    ET.SubElement(
        keyframe,
        "key",
        {
            "name": "startup_pose",
            "qpos": _numbers([*hand_qpos, *object_pos, 1.0, 0.0, 0.0, 0.0]),
            "ctrl": _numbers(hand_qpos),
        },
    )
    ET.indent(root, space="  ")
    return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _relative_include(target: Path, output_dir: Path) -> str:
    return os.path.relpath(target.resolve(), output_dir.resolve()).replace("\\", "/")


def _object_size(obj: dict) -> str:
    size = obj["size"]
    if obj["shape"] == "sphere":
        return _numbers([size[0]])
    if obj["shape"] == "cylinder":
        return _numbers(size[:2])
    return _numbers(size)


def _render_scene_v2(spec: dict, output_dir: Path) -> str:
    task = spec["task"]
    scene = task["scene"]
    table = scene["table"]
    package_root = Path(__file__).resolve().parents[1]

    root = ET.Element("mujoco", {"model": task["env_id"]})
    ET.SubElement(
        root,
        "include",
        {"file": _relative_include(package_root / "scenes" / "v1" / "scene.xml", output_dir)},
    )
    ET.SubElement(
        root,
        "include",
        {"file": _relative_include(package_root / "models" / "v1" / "right.mjcf", output_dir)},
    )
    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(
        worldbody,
        "geom",
        {
            "name": "task_table",
            "type": "box",
            "pos": _numbers(table["position"]),
            "size": _numbers(table["half_size"]),
            "rgba": _numbers(table["rgba"]),
            "friction": _numbers(table["friction"]),
            "condim": "4",
            "contype": "2",
            "conaffinity": "2",
        },
    )
    obj = scene.get("object")
    if obj is not None:
        body = ET.SubElement(
            worldbody,
            "body",
            {"name": "task_object", "pos": _numbers(obj["initial_position"]), "quat": "1 0 0 0"},
        )
        ET.SubElement(body, "freejoint", {"name": "task_object_freejoint"})
        ET.SubElement(
            body,
            "geom",
            {
                "name": "task_object_geom",
                "type": obj["shape"],
                "size": _object_size(obj),
                "mass": f"{float(obj['mass']):.12g}",
                "rgba": _numbers(obj["rgba"]),
                "friction": _numbers(obj["friction"]),
                "condim": "4",
                "contype": "2",
                "conaffinity": "2",
            },
        )
        ET.SubElement(
            body,
            "site",
            {"name": "task_object_center", "type": "sphere", "size": "0.002", "rgba": "1 1 1 0"},
        )
    target = scene.get("target")
    if target is not None:
        ET.SubElement(
            worldbody,
            "site",
            {
                "name": "task_target",
                "type": "cylinder",
                "pos": _numbers(target["position"]),
                "size": _numbers([target["radius"], 0.002]),
                "rgba": _numbers(target["rgba"]),
                "group": "3",
            },
        )
    ET.indent(root, space="  ")
    return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _bundle_readme(spec: dict) -> str:
    task = spec["task"]
    return f"""# {task['env_id']}

Generated from: {task['source_text']}

- Family: `{task['family']}`
- Hand: ORCA v1 right hand with a bounded kinematic 6DoF wrist
- Validation: see `validation_report.json`

```python
from orca_sim.taskgen import load_environment

env = load_environment(r\".\", render_mode=\"human\")
observation, info = env.reset(seed=0)
```

This bundle contains an untrained RL environment. Any preview is produced by a
non-learning scripted feasibility controller, not PPO or a trained policy.
"""


def generate_task(
    spec_path: str | Path,
    *,
    output_root: str | Path = GENERATED_ROOT,
    allowed_output_root: str | Path = GENERATED_ROOT,
    attempt: int = 1,
) -> Path:
    """Render one validated spec inside an explicitly allowed output root."""

    output_root = Path(output_root).resolve()
    allowed_output_root = Path(allowed_output_root).resolve()
    if not _within(output_root, allowed_output_root):
        raise ContractError(f"output path escapes allowed root {allowed_output_root}")

    spec_path = Path(spec_path).resolve()
    spec = load_task_spec(spec_path, allowed_root=spec_path.parent)
    output_dir = (output_root / _slug(spec["task"]["env_id"])).resolve()
    if not _within(output_dir, allowed_output_root):
        raise ContractError(f"generated task path escapes allowed root {allowed_output_root}")
    output_dir.mkdir(parents=True, exist_ok=True)

    canonical_yaml = yaml.safe_dump(spec, sort_keys=True, allow_unicode=True)
    if spec["schema_version"] == 1:
        gesture_path = TASKGEN_ROOT / spec["task"]["reference_gesture"]["path"]
        gesture = load_gesture_reference(gesture_path, allowed_root=TASKGEN_ROOT)
        if gesture["hand_version"] != spec["task"]["hand_version"]:
            raise ContractError("reference gesture hand_version does not match TaskSpec")
        scene_xml = _render_scene_v1(spec, gesture)
    else:
        scene_xml = _render_scene_v2(spec, output_dir)
    spec_hash = hashlib.sha256(canonical_yaml.encode("utf-8")).hexdigest()
    task = spec["task"]
    files = ["task_spec.yaml", "scene.xml", "manifest.json"]
    if spec["schema_version"] == 2:
        files.extend(["request.txt", "validation_report.json", "README.md"])
    manifest = {
        "manifest_version": 2 if spec["schema_version"] == 2 else 1,
        "schema_version": spec["schema_version"],
        "env_id": task["env_id"],
        "family": task["family"],
        "hand_version": task.get("hand_version", task.get("hand", {}).get("version")),
        "source_commit": BASELINE_COMMIT,
        "spec_sha256": spec_hash,
        "attempt": int(attempt),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "validation": "pending",
    }
    if spec["schema_version"] == 2:
        manifest.update(
            {
                "environment_class": "orca_sim.taskgen.generic_env:GeneratedOrcaEnv",
                "action_shape": [23],
                "action_fields": ["wrist_translation_delta[3]", "wrist_rotation_delta[3]", "hand_targets[17]"],
                "observation_contract": "wrist, hand, fingertips, contacts, object, target, stage",
                "requires": {"orca_sim": ">=0.2.0", "mujoco": ">=3.1"},
                "base_control": "kinematic_6dof",
                "assistive_grasp": bool(task["safety"]["assistive_grasp"]),
            }
        )
    (output_dir / "task_spec.yaml").write_text(canonical_yaml, encoding="utf-8", newline="\n")
    (output_dir / "scene.xml").write_text(scene_xml, encoding="utf-8", newline="\n")
    if spec["schema_version"] == 2:
        (output_dir / "request.txt").write_text(task["source_text"] + "\n", encoding="utf-8")
        (output_dir / "validation_report.json").write_text(
            json.dumps({"status": "pending", "note": "Run orca-task check to validate."}, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_dir / "README.md").write_text(_bundle_readme(spec), encoding="utf-8")
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_dir
