from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from orca_sim.taskgen.contracts import (
    ContractError,
    load_gesture_reference,
    load_task_spec,
    validate_gesture_reference,
    validate_task_spec,
)


@pytest.fixture
def valid_task_spec() -> dict:
    return {
        "schema_version": 1,
        "task": {
            "env_id": "PinchAndHold-v0",
            "family": "pinch_and_hold",
            "hand_version": "v1",
            "side": "right",
            "object": {
                "shape": "cylinder",
                "radius": 0.01,
                "half_length": 0.02,
                "mass": 0.02,
                "rgba": [0.9, 0.3, 0.1, 1.0],
                "friction": [1.0, 0.01, 0.001],
            },
            "reset": {
                "hand_pose": "open",
                "hand_closure_fraction": 0.0,
                "object_position": [0.0, 0.0, 0.18],
                "position_jitter": [0.002, 0.002, 0.002],
            },
            "observation": {
                "include_object_state": True,
                "include_contact_flags": True,
            },
            "control": {"action_mode": "relative", "action_scale": 0.15},
            "reward": {
                "distance_progress": 1.0,
                "contact_progress": 1.0,
                "success_bonus": 10.0,
                "drop_penalty": 5.0,
                "action_rate_penalty": 0.002,
            },
            "success": {
                "require_thumb_contact": True,
                "require_index_contact": True,
                "hold_steps": 10,
                "workspace": {
                    "min": [-0.05, -0.05, 0.1],
                    "max": [0.05, 0.05, 0.25],
                },
            },
            "failure": {"drop_height": 0.08, "terminate_on_drop": True},
            "randomization": {"physics": False, "mild_position_scale": 0.5},
            "safety": {"max_action_delta": 0.15, "max_episode_steps": 200},
            "reference_gesture": {
                "path": "gestures/pinch_v1_synthetic.yaml",
                "source": "synthetic",
                "repository": "https://github.com/back2-thebasic/orcahand-retarget-experiments",
                "configuration": "configs/last.yaml",
            },
        },
    }


@pytest.fixture
def valid_gesture() -> dict:
    zeros = [0.0] * 17
    return {
        "schema_version": 1,
        "source": "synthetic",
        "hand_version": "v1",
        "side": "right",
        "control_space": "normalized",
        "configuration": "configs/last.yaml",
        "provenance": {
            "repository": "https://github.com/back2-thebasic/orcahand-retarget-experiments",
            "commit": "032b5fd4",
            "notes": "Synthetic fixture; not a recorded Cheng Su trajectory.",
        },
        "samples": [
            {"timestamp": 0.0, "qpos": zeros.copy(), "ctrl": zeros.copy()},
            {"timestamp": 0.02, "qpos": zeros.copy(), "ctrl": zeros.copy()},
        ],
    }


def test_valid_task_spec(valid_task_spec: dict) -> None:
    assert validate_task_spec(valid_task_spec)["task"]["hand_version"] == "v1"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda spec: spec["task"].update({"unexpected": 1}), "unexpected"),
        (lambda spec: spec["task"].update({"hand_version": "v3"}), "v3"),
        (lambda spec: spec["task"]["success"].update({"hold_steps": 9}), "less than"),
        (lambda spec: spec["task"]["object"].update({"radius": float("nan")}), "finite"),
        (
            lambda spec: spec["task"]["reference_gesture"].update({"path": "../../secret.yaml"}),
            "relative path",
        ),
    ],
)
def test_invalid_task_specs_are_rejected(valid_task_spec: dict, mutator, message: str) -> None:
    spec = deepcopy(valid_task_spec)
    mutator(spec)
    with pytest.raises(ContractError, match=message):
        validate_task_spec(spec)


def test_nominal_position_must_be_in_workspace(valid_task_spec: dict) -> None:
    valid_task_spec["task"]["reset"]["object_position"] = [1.0, 0.0, 0.18]
    with pytest.raises(ContractError, match="inside success workspace"):
        validate_task_spec(valid_task_spec)


def test_loader_rejects_path_escape(tmp_path: Path, valid_task_spec: dict) -> None:
    allowed = tmp_path / "specs"
    allowed.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text(yaml.safe_dump(valid_task_spec), encoding="utf-8")
    with pytest.raises(ContractError, match="escapes allowed root"):
        load_task_spec(outside, allowed_root=allowed)


def test_valid_gesture(valid_gesture: dict) -> None:
    assert len(validate_gesture_reference(valid_gesture)["samples"][0]["qpos"]) == 17


def test_packaged_specs_and_gesture_load() -> None:
    root = Path(__file__).parents[1] / "src" / "orca_sim" / "taskgen"
    main = load_task_spec(root / "specs" / "pinch_and_hold_v0.yaml", allowed_root=root)
    variant = load_task_spec(root / "specs" / "pinch_and_hold_small_v0.yaml", allowed_root=root)
    gesture = load_gesture_reference(
        root / main["task"]["reference_gesture"]["path"], allowed_root=root
    )
    assert main["task"]["env_id"] == "PinchAndHold-v0"
    assert variant["task"]["object"]["radius"] < main["task"]["object"]["radius"]
    assert gesture["source"] == "synthetic"


def test_gesture_requires_17_joints(valid_gesture: dict) -> None:
    valid_gesture["samples"][0]["qpos"] = [0.0] * 16
    with pytest.raises(ContractError, match="too short"):
        validate_gesture_reference(valid_gesture)


def test_gesture_rejects_non_monotonic_time(valid_gesture: dict) -> None:
    valid_gesture["samples"][1]["timestamp"] = 0.0
    with pytest.raises(ContractError, match="strictly increasing"):
        validate_gesture_reference(valid_gesture)


def test_gesture_rejects_out_of_range_control(valid_gesture: dict) -> None:
    valid_gesture["samples"][0]["ctrl"][3] = 1.1
    with pytest.raises(ContractError, match="greater than the maximum"):
        validate_gesture_reference(valid_gesture)


def test_gesture_rejects_non_finite_number(valid_gesture: dict) -> None:
    valid_gesture["samples"][0]["qpos"][0] = float("inf")
    with pytest.raises(ContractError, match="finite"):
        validate_gesture_reference(valid_gesture)
