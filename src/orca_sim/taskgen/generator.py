"""Deterministic renderer for accepted ORCA TaskSpec documents."""

from __future__ import annotations

import hashlib
import json
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


def _render_scene(spec: dict, gesture: dict) -> str:
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
    gesture_path = TASKGEN_ROOT / spec["task"]["reference_gesture"]["path"]
    gesture = load_gesture_reference(gesture_path, allowed_root=TASKGEN_ROOT)
    if gesture["hand_version"] != spec["task"]["hand_version"]:
        raise ContractError("reference gesture hand_version does not match TaskSpec")

    output_dir = (output_root / _slug(spec["task"]["env_id"])).resolve()
    if not _within(output_dir, allowed_output_root):
        raise ContractError(f"generated task path escapes allowed root {allowed_output_root}")
    output_dir.mkdir(parents=True, exist_ok=True)

    canonical_yaml = yaml.safe_dump(spec, sort_keys=True, allow_unicode=True)
    scene_xml = _render_scene(spec, gesture)
    spec_hash = hashlib.sha256(canonical_yaml.encode("utf-8")).hexdigest()
    manifest = {
        "manifest_version": 1,
        "env_id": spec["task"]["env_id"],
        "family": spec["task"]["family"],
        "hand_version": spec["task"]["hand_version"],
        "source_commit": BASELINE_COMMIT,
        "spec_sha256": spec_hash,
        "attempt": int(attempt),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": ["task_spec.yaml", "scene.xml", "manifest.json"],
        "validation": "pending",
    }
    (output_dir / "task_spec.yaml").write_text(canonical_yaml, encoding="utf-8", newline="\n")
    (output_dir / "scene.xml").write_text(scene_xml, encoding="utf-8", newline="\n")
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_dir
