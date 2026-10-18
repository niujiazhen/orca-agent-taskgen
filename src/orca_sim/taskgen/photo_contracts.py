"""SceneSpec v1 and TaskSpec v3 contracts for Codex-authored photo scenes.

Coordinates are metres in a table-centred frame. Object dimensions are full
local XYZ extents; pen length is along X, cylinders stand along Z. Height is
derived from orientation, never guessed independently from image pixels.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import mujoco
import numpy as np
import yaml

from orca_sim.taskgen.contracts import (
    ContractError, _assert_finite, _assert_safe_relative_path, _read_yaml,
    _schema, _validate_schema,
)
from jsonschema import Draft202012Validator

DEFAULT_DIMENSIONS = {
    "box": [0.032, 0.032, 0.032], "cylinder": [0.028, 0.028, 0.044],
    "sphere": [0.034, 0.034, 0.034], "pen": [0.14, 0.009, 0.009],
    "eraser": [0.05, 0.02, 0.01], "book": [0.20, 0.14, 0.02],
}
DEFAULT_MASS = {"box": .04, "cylinder": .04, "sphere": .04,
                "pen": .01, "eraser": .02, "book": .25}
PROVENANCE_FIELDS = ("category", "dimensions", "xy", "quaternion", "rgba", "mass", "friction")


def content_hash(spec: dict) -> str:
    return hashlib.sha256(yaml.safe_dump(spec, sort_keys=True, allow_unicode=True).encode()).hexdigest()


def rotation(quaternion) -> np.ndarray:
    matrix = np.empty(9)
    mujoco.mju_quat2Mat(matrix, np.asarray(quaternion, dtype=np.float64))
    return matrix.reshape(3, 3)


def object_extent(obj: dict) -> np.ndarray:
    """Conservative oriented support bounds, exact for boxes and spheres."""
    dims = np.asarray(obj["dimensions"], dtype=float)
    rot = rotation(obj["quaternion"])
    category = obj["category"]
    if category == "sphere":
        return dims / 2
    if category == "pen":
        radius = dims[1] / 2
        return np.abs(rot[:, 0]) * (dims[0] / 2 - radius) + radius
    if category == "cylinder":
        axis = rot[:, 2]
        return np.abs(axis) * dims[2] / 2 + dims[0] / 2 * np.sqrt(np.maximum(0, 1-axis**2))
    return np.abs(rot) @ (dims / 2)


def object_position(spec: dict, obj: dict) -> np.ndarray:
    return np.asarray([*obj["xy"], spec["table"]["top_z"] + object_extent(obj)[2] + .0005])


def default_object(object_id: str, category: str, xy=(0.0, 0.0), *, rgba=None) -> dict:
    if category not in DEFAULT_DIMENSIONS:
        raise ContractError(f"Unsupported category {category!r}; ask the user how to simplify")
    return {
        "id": object_id, "category": category,
        "dimensions": DEFAULT_DIMENSIONS[category].copy(), "xy": list(xy),
        "quaternion": [1., 0., 0., 0.], "mass": DEFAULT_MASS[category],
        "rgba": list(rgba or [.15, .15, .15, 1.]), "friction": [1.2, .01, .001],
        "support": "table", "image_bbox": [0., 0., 1., 1.],
        "provenance": {key: "catalog_default" for key in PROVENANCE_FIELDS},
    }


def validate_scene_spec(data: dict) -> dict:
    _assert_finite(data, "SceneSpec")
    _validate_schema(data, Draft202012Validator(_schema("scene_spec_v1.schema.json")), "SceneSpec")
    _assert_safe_relative_path(data["source"]["image"], "source.image")
    ids = [obj["id"] for obj in data["objects"]]
    if data["table"]["dimensions"][2] > data["table"]["top_z"]:
        raise ContractError("Table slab must not extend below the floor")
    if len(ids) != len(set(ids)):
        raise ContractError("SceneSpec object IDs must be unique")
    for obj in data["objects"]:
        dims = obj["dimensions"]
        if obj["category"] in {"sphere", "cylinder", "pen"}:
            axes = (0, 1, 2) if obj["category"] == "sphere" else (0, 1) if obj["category"] == "cylinder" else (1, 2)
            if any(abs(dims[a]-dims[axes[0]]) > 1e-8 for a in axes):
                raise ContractError(f"{obj['id']}: circular cross-section dimensions must agree")
        if obj["category"] == "pen" and dims[0] < dims[1]*2:
            raise ContractError("pen length must be at least twice its diameter")
        if not np.isclose(np.linalg.norm(obj["quaternion"]), 1, atol=1e-5):
            raise ContractError(f"{obj['id']}: quaternion must be normalized")
        box = obj["image_bbox"]
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ContractError(f"{obj['id']}: image_bbox must have increasing coordinates")
        extent = object_extent(obj)
        for axis in (0, 1):
            if abs(obj["xy"][axis]) + extent[axis] > data["table"]["dimensions"][axis]/2:
                raise ContractError(f"{obj['id']}: object extends beyond tabletop; correct layout explicitly")
    if data["confirmed"] and data["questions"]:
        raise ContractError("Resolve scene questions before confirmation")
    ref = data["scale_reference"]
    if ref is not None and ref["object_id"] not in ids:
        raise ContractError("scale_reference refers to an unknown object")
    return deepcopy(data)


def load_scene_spec(path: str | Path) -> dict:
    path = Path(path).resolve()
    return validate_scene_spec(_read_yaml(path, allowed_root=path.parent, label="SceneSpec"))


def calibrate_scene(spec: dict, object_id: str, axis: int, length_m: float) -> dict:
    spec = validate_scene_spec(spec)
    if axis not in (0, 1, 2) or not np.isfinite(length_m) or length_m <= 0:
        raise ContractError("Calibration needs an axis 0..2 and a positive finite length")
    obj = next((o for o in spec["objects"] if o["id"] == object_id), None)
    if obj is None:
        raise ContractError(f"Unknown calibration object: {object_id}")
    factor = length_m / obj["dimensions"][axis]
    spec["table"]["dimensions"] = [v*factor for v in spec["table"]["dimensions"]]
    spec["table"]["provenance"]["dimensions"] = "user_input"
    for item in spec["objects"]:
        item["dimensions"] = [v*factor for v in item["dimensions"]]
        item["xy"] = [v*factor for v in item["xy"]]
        item["provenance"]["dimensions"] = "user_input"
        item["provenance"]["xy"] = "user_input"
    spec["scale_reference"] = {"object_id": object_id, "axis": axis, "length_m": length_m}
    spec["confirmed"] = False
    return validate_scene_spec(spec)


def validate_task_v3(data: dict) -> dict:
    _assert_finite(data, "TaskSpec")
    _validate_schema(data, Draft202012Validator(_schema("task_spec_v3.schema.json")), "TaskSpec")
    spec = validate_scene_spec(data["scene_spec"])
    if not spec["confirmed"] or spec["questions"]:
        raise ContractError("Confirm the scene and resolve questions before creating an RL task")
    ids = [obj["id"] for obj in spec["objects"]]
    if data["task"]["object_id"] not in ids:
        raise ContractError("TaskSpec task.object_id does not exist in scene")
    target = data["task"]["target_xy"]
    if data["task"]["family"] == "pick_place":
        if target is None:
            raise ContractError("pick_place requires explicit target_xy")
        obj = next(o for o in spec["objects"] if o["id"] == data["task"]["object_id"])
        extent = object_extent(obj)
        if any(abs(target[a])+extent[a] > spec["table"]["dimensions"][a]/2 for a in (0, 1)):
            raise ContractError("Placement target extends beyond tabletop")
        if np.linalg.norm(np.asarray(target)-obj["xy"]) <= data["task"]["target_radius"]*2:
            raise ContractError("Placement target must be distinct from the initial position")
    return deepcopy(data)


def runtime_task_v3(spec: dict) -> dict:
    """Adapt shared hand/control settings; the v3 env owns multi-object state."""
    from orca_sim.taskgen.text import task_spec_from_text
    scene, task = spec["scene_spec"], spec["task"]
    obj = next(o for o in scene["objects"] if o["id"] == task["object_id"])
    proxy = "sphere" if obj["category"] == "sphere" else "cylinder" if obj["category"] in {"pen", "cylinder"} else "box"
    out = task_spec_from_text(f"Pick up the {proxy}", env_id=task["env_id"])["task"]
    out["family"] = task["family"]
    out["source_text"] = task["source_text"]
    top = scene["table"]["top_z"]
    height = max(object_position(scene, o)[2]+object_extent(o)[2] for o in scene["objects"])
    out["hand"]["initial_position"] = [0., 0., height+.35]
    out["hand"]["workspace"] = {"min": [-.5, -.5, top+.18], "max": [.5, .5, height+.6]}
    out["scene"]["object"]["shape"] = proxy
    out["scene"]["object"]["initial_position"] = object_position(scene, obj).tolist()
    out["scene"]["table"] = {"position": [0, 0, top-.01], "half_size": [.3, .2, .01]}
    if task["target_xy"] is not None:
        out["scene"]["target"] = {"position": [*task["target_xy"], top+object_extent(obj)[2]+.0005]}
    out["reset"]["object_position_jitter"] = [0, 0, 0]
    out["reset"]["wrist_position_jitter"] = [0, 0, 0]
    out["success"].update({key: task[key] for key in ("hold_steps", "lift_height", "target_radius", "max_object_speed")})
    out["safety"]["max_episode_steps"] = task["max_episode_steps"]
    return out
