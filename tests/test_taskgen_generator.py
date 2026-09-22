from __future__ import annotations

import json
import shutil
from pathlib import Path

import gymnasium as gym
import numpy as np
import pytest
from gymnasium import spaces

from orca_sim.taskgen.contracts import ContractError
from orca_sim.taskgen.generator import GENERATED_ROOT, TASKGEN_ROOT, generate_task
from orca_sim.taskgen.registry import register_generated_envs
from orca_sim.taskgen.validator import (
    validate_env_instance,
    validate_generated_directory,
    validate_runtime,
)


MAIN_SPEC = TASKGEN_ROOT / "specs" / "pinch_and_hold_v0.yaml"
MAIN_GENERATED = GENERATED_ROOT / "pinchandhold_v0"
VARIANT_GENERATED = GENERATED_ROOT / "pinchandholdsmall_v0"


def test_generator_writes_only_inside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "generated"
    output = generate_task(MAIN_SPEC, output_root=allowed, allowed_output_root=allowed)
    assert output.parent == allowed.resolve()
    assert {item.name for item in output.iterdir()} == {
        "manifest.json",
        "scene.xml",
        "task_spec.yaml",
    }
    assert validate_generated_directory(output)["static"] == "pass"


def test_generator_rejects_output_escape(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="escapes allowed root"):
        generate_task(
            MAIN_SPEC,
            output_root=tmp_path / "outside",
            allowed_output_root=tmp_path / "allowed",
        )


def test_static_validator_rejects_absolute_path(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(MAIN_GENERATED, broken)
    manifest_path = broken / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["debug_path"] = "C:\\Users\\someone\\private"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ContractError, match="absolute"):
        validate_generated_directory(broken)


def test_static_validator_scans_manifest_listed_reports(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    shutil.copytree(MAIN_GENERATED, generated)
    report_path = generated / "validation_report.json"
    report_path.write_text(
        '{"debug_path": "C:\\\\Users\\\\someone\\\\private"}\n', encoding="utf-8"
    )
    manifest_path = generated / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = sorted(set(manifest["files"]) | {report_path.name})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ContractError, match="absolute"):
        validate_generated_directory(generated)


def test_static_validator_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    shutil.copytree(MAIN_GENERATED, generated)
    (tmp_path / "outside.json").write_text("{}\n", encoding="utf-8")
    manifest_path = generated / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append("../outside.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ContractError, match="unsafe path"):
        validate_generated_directory(generated)


def test_static_validator_rejects_bad_xml(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(MAIN_GENERATED, broken)
    (broken / "scene.xml").write_text("<mujoco>", encoding="utf-8")
    with pytest.raises(ContractError, match="well-formed"):
        validate_generated_directory(broken)


class _BrokenEnv(gym.Env):
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.action_space = spaces.Box(-1.0, 1.0, shape=(1,), dtype=np.float32)
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(1,), dtype=np.float32)
        self.count = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.count = 0
        return np.zeros(1, dtype=np.float32), {}

    def step(self, action):
        self.count += 1
        obs = np.zeros(2 if self.mode == "shape" and self.count > 1 else 1, dtype=np.float32)
        reward = float("nan") if self.mode == "nan" else 0.0
        return obs, reward, False, self.count >= 3, {}


@pytest.mark.parametrize(("mode", "message"), [("shape", "shape"), ("nan", "finite")])
def test_runtime_validator_catches_broken_env(mode: str, message: str) -> None:
    with pytest.raises((ContractError, AssertionError), match=message):
        validate_env_instance(_BrokenEnv(mode), steps=4)


def test_generated_main_runtime_smoke() -> None:
    result = validate_runtime(MAIN_GENERATED, steps=100, seed=5)
    assert result["runtime"] == "pass"
    assert result["action_shape"] == [17]


def test_main_and_variant_register_together() -> None:
    ids = register_generated_envs()
    assert {"PinchAndHold-v0", "PinchAndHoldSmall-v0"}.issubset(ids)
    first = gym.make("PinchAndHold-v0", disable_env_checker=True)
    second = gym.make("PinchAndHoldSmall-v0", disable_env_checker=True)
    try:
        assert first.unwrapped.task_spec["task"]["object"]["radius"] > second.unwrapped.task_spec["task"]["object"]["radius"]
    finally:
        first.close()
        second.close()
