"""Strict, versioned contracts used by the task-generation pipeline."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ContractError(ValueError):
    """Raised when a TaskSpec or gesture reference violates its contract."""


def _schema(name: str) -> dict[str, Any]:
    schema_path = files("orca_sim.taskgen").joinpath("schemas", name)
    return json.loads(schema_path.read_text(encoding="utf-8"))


TASK_SPEC_V1_VALIDATOR = Draft202012Validator(_schema("task_spec_v1.schema.json"))
TASK_SPEC_V2_VALIDATOR = Draft202012Validator(_schema("task_spec_v2.schema.json"))
GESTURE_VALIDATOR = Draft202012Validator(_schema("gesture_reference_v1.schema.json"))


def _format_path(path: Sequence[Any]) -> str:
    return ".".join(str(part) for part in path) or "<root>"


def _validate_schema(data: Any, validator: Draft202012Validator, label: str) -> None:
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        raise ContractError(f"{label}.{_format_path(error.path)}: {error.message}")


def _assert_finite(value: Any, path: str = "<root>") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ContractError(f"{path}: all numeric values must be finite")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]")


def _assert_safe_relative_path(value: str, field: str) -> None:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        not value
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or ".." in windows.parts
        or any(part in {"", "."} for part in posix.parts)
    ):
        raise ContractError(f"{field}: must be a normalized relative path without '..'")


def _read_yaml(path: Path, *, allowed_root: Path | None, label: str) -> Any:
    path = Path(path)
    resolved = path.resolve()
    if allowed_root is not None:
        root = Path(allowed_root).resolve()
        if resolved != root and root not in resolved.parents:
            raise ContractError(f"{label}: path escapes allowed root {root}")
    try:
        with resolved.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"{label}: cannot load YAML: {exc}") from exc


def validate_task_spec(data: Any) -> dict[str, Any]:
    """Validate and return a supported TaskSpec mapping."""

    _assert_finite(data, "TaskSpec")
    if not isinstance(data, Mapping):
        raise ContractError("TaskSpec.<root>: must be a mapping")
    version = data.get("schema_version")
    if version == 1:
        return _validate_task_spec_v1(data)
    if version == 2:
        return _validate_task_spec_v2(data)
    raise ContractError(f"TaskSpec.schema_version: unsupported version {version!r}")


def _validate_task_spec_v1(data: Mapping[str, Any]) -> dict[str, Any]:
    _validate_schema(data, TASK_SPEC_V1_VALIDATOR, "TaskSpec")
    task = data["task"]
    _assert_safe_relative_path(task["reference_gesture"]["path"], "TaskSpec.task.reference_gesture.path")

    workspace = task["success"]["workspace"]
    for axis, (lower, upper) in enumerate(zip(workspace["min"], workspace["max"])):
        if lower >= upper:
            raise ContractError(
                f"TaskSpec.task.success.workspace axis {axis}: min must be less than max"
            )

    position = task["reset"]["object_position"]
    if not all(lower <= coordinate <= upper for coordinate, lower, upper in zip(
        position, workspace["min"], workspace["max"]
    )):
        raise ContractError(
            "TaskSpec.task.reset.object_position: nominal position must lie inside success workspace"
        )
    return dict(data)


def _validate_task_spec_v2(data: Mapping[str, Any]) -> dict[str, Any]:
    _validate_schema(data, TASK_SPEC_V2_VALIDATOR, "TaskSpec")
    task = data["task"]
    workspace = task["hand"]["workspace"]
    for axis, (lower, upper) in enumerate(zip(workspace["min"], workspace["max"])):
        if lower >= upper:
            raise ContractError(
                f"TaskSpec.task.hand.workspace axis {axis}: min must be less than max"
            )
    initial = task["hand"]["initial_position"]
    if not all(
        lower <= value <= upper
        for value, lower, upper in zip(initial, workspace["min"], workspace["max"])
    ):
        raise ContractError("TaskSpec.task.hand.initial_position lies outside its workspace")
    quaternion = task["hand"]["initial_quaternion"]
    norm = math.sqrt(sum(float(value) ** 2 for value in quaternion))
    if not 0.999 <= norm <= 1.001:
        raise ContractError("TaskSpec.task.hand.initial_quaternion must be normalized")

    table = task["scene"].get("table")
    if table is not None and any(float(value) <= 0 for value in table["half_size"]):
        raise ContractError("TaskSpec.task.scene.table.half_size must be positive")
    obj = task["scene"].get("object")
    if obj is not None:
        if table is None:
            raise ContractError("TaskSpec.task.scene.table is required when an object is present")
        table_top = float(table["position"][2]) + float(table["half_size"][2])
        if float(obj["initial_position"][2]) <= table_top:
            raise ContractError("TaskSpec.task.scene.object.initial_position must be above the table")
    target = task["scene"].get("target")
    if target is not None and float(target["position"][2]) < 0:
        raise ContractError("TaskSpec.task.scene.target.position must be above the floor")
    return dict(data)


def load_task_spec(path: str | Path, *, allowed_root: str | Path | None = None) -> dict[str, Any]:
    data = _read_yaml(
        Path(path),
        allowed_root=None if allowed_root is None else Path(allowed_root),
        label="TaskSpec",
    )
    return validate_task_spec(data)


def validate_gesture_reference(data: Any) -> dict[str, Any]:
    """Validate a canonical 17-actuator ORCA gesture trajectory."""

    _assert_finite(data, "GestureReference")
    _validate_schema(data, GESTURE_VALIDATOR, "GestureReference")

    timestamps = [float(sample["timestamp"]) for sample in data["samples"]]
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ContractError("GestureReference.samples.timestamp: values must be strictly increasing")
    return dict(data)


def load_gesture_reference(
    path: str | Path, *, allowed_root: str | Path | None = None
) -> dict[str, Any]:
    data = _read_yaml(
        Path(path),
        allowed_root=None if allowed_root is None else Path(allowed_root),
        label="GestureReference",
    )
    return validate_gesture_reference(data)
