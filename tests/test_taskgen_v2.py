from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
import pytest
import yaml

from orca_sim.taskgen import load_environment
from orca_sim.taskgen.catalog import GESTURE_SEQUENCES
from orca_sim.taskgen.contracts import ContractError, validate_task_spec
from orca_sim.taskgen.generator import generate_task
from orca_sim.taskgen.text import UnsupportedTaskError, task_spec_from_text
from orca_sim.taskgen.validator import validate_generated_directory, validate_runtime
from orca_sim.versions import PACKAGE_ROOT


REQUESTS = {
    "gesture": ("让灵巧手从张开变成握拳，然后再次张开", "HandFist-v0"),
    "pick_up": ("让灵巧手拿起桌上的红色方块", "RedCubePickup-v0"),
    "pick_place": (
        "把蓝色圆柱拿起来并放到桌面右侧的绿色区域",
        "BlueCylinderPlace-v0",
    ),
}


def _generate(tmp_path: Path, family: str) -> Path:
    text, env_id = REQUESTS[family]
    spec = task_spec_from_text(text, env_id=env_id)
    spec_path = tmp_path / f"{family}.yaml"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=True, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "generated"
    return generate_task(spec_path, output_root=output, allowed_output_root=output)


def _minimum_visible_hand_z(env) -> float:
    hand_bodies: set[int] = set()
    for body_id in range(env.model.nbody):
        ancestor = body_id
        while ancestor > 0 and ancestor != env._tower_body_id:
            ancestor = int(env.model.body_parentid[ancestor])
        if ancestor == env._tower_body_id:
            hand_bodies.add(body_id)

    minimum = np.inf
    for geom_id in range(env.model.ngeom):
        if (
            int(env.model.geom_bodyid[geom_id]) not in hand_bodies
            or env.model.geom_rgba[geom_id, 3] <= 0
        ):
            continue
        local_center = env.model.geom_aabb[geom_id, :3]
        half_extent = env.model.geom_aabb[geom_id, 3:]
        rotation = env.data.geom_xmat[geom_id].reshape(3, 3)
        world_center = env.data.geom_xpos[geom_id] + rotation @ local_center
        world_extent = np.abs(rotation) @ half_extent
        minimum = min(minimum, float(world_center[2] - world_extent[2]))
    return float(minimum)


def test_text_parser_supports_three_families_and_both_languages() -> None:
    gesture = task_spec_from_text(REQUESTS["gesture"][0])
    assert gesture["task"]["family"] == "gesture"
    assert gesture["task"]["scene"] == {}
    assert task_spec_from_text(REQUESTS["pick_up"][0])["task"]["scene"]["object"]["shape"] == "box"
    pickup_hand = task_spec_from_text(REQUESTS["pick_up"][0])["task"]["hand"]
    assert pickup_hand["initial_position"][2] > 0.45
    assert pickup_hand["initial_quaternion"] != [1.0, 0.0, 0.0, 0.0]
    place = task_spec_from_text("Pick up the blue sphere and place it on the right target")
    assert place["task"]["family"] == "pick_place"
    assert place["task"]["scene"]["object"]["shape"] == "sphere"
    assert "target" in place["task"]["scene"]
    first = task_spec_from_text("让灵巧手拿起红色方块")["task"]["env_id"]
    second = task_spec_from_text("让灵巧手拿起蓝色圆柱")["task"]["env_id"]
    assert first != second
    assert place["task"]["scene"]["target"]["rgba"] == [0.12, 0.35, 0.85, 0.35]


@pytest.mark.parametrize("task_request", ["拧紧螺丝", "stack two cubes", "insert the cylinder"])
def test_text_parser_rejects_unsupported_tasks(task_request: str) -> None:
    with pytest.raises(UnsupportedTaskError, match="Supported tasks"):
        task_spec_from_text(task_request)


def test_text_parser_rejects_unknown_object() -> None:
    with pytest.raises(UnsupportedTaskError, match="Object shape"):
        task_spec_from_text("Pick up the banana")


def test_v2_contract_rejects_unknown_shape_and_bad_workspace() -> None:
    spec = task_spec_from_text(REQUESTS["pick_up"][0])
    spec["task"]["scene"]["object"]["shape"] = "mesh"
    with pytest.raises(ContractError, match="shape"):
        validate_task_spec(spec)
    spec = task_spec_from_text(REQUESTS["pick_up"][0])
    spec["task"]["hand"]["workspace"]["min"][0] = 1.0
    with pytest.raises(ContractError, match="workspace"):
        validate_task_spec(spec)


@pytest.mark.parametrize("family", ["gesture", "pick_up", "pick_place"])
def test_v2_generation_runtime_and_scripted_success(tmp_path: Path, family: str) -> None:
    bundle = _generate(tmp_path, family)
    scene_xml = (bundle / "scene.xml").read_text(encoding="utf-8")
    assert "task_table" not in scene_xml
    if family == "gesture":
        assert "task_surface" not in scene_xml
    else:
        assert 'name="task_surface" type="plane"' in scene_xml
    static = validate_generated_directory(bundle)
    assert static["static"] == "pass"
    runtime = validate_runtime(bundle, steps=25, seed=0)
    assert runtime["action_shape"] == [23]
    assert runtime["observation_shape"] == [73]

    env = load_environment(bundle)
    try:
        first, _ = env.reset(seed=123)
        second, _ = env.reset(seed=123)
        np.testing.assert_array_equal(first, second)
        minimum_visible_hand_z = np.inf
        for _ in range(env.max_episode_steps):
            _, _, terminated, truncated, info = env.step(env.scripted_action())
            if family != "gesture":
                minimum_visible_hand_z = min(
                    minimum_visible_hand_z, _minimum_visible_hand_z(env)
                )
            if terminated or truncated:
                break
        assert info["is_success"] is True
        assert info["assistive_grasp"] is True
        if family != "gesture":
            table = env.task["scene"]["table"]
            surface_z = table["position"][2] + table["half_size"][2]
            assert minimum_visible_hand_z >= surface_z
    finally:
        env.close()


def test_all_primitive_shapes_compile_and_succeed_for_pickup_and_place(tmp_path: Path) -> None:
    requests = {
        "box": "the red box",
        "cylinder": "the blue cylinder",
        "sphere": "the green sphere",
    }
    for index, (shape, object_text) in enumerate(requests.items()):
        for family, request in (
            ("pick_up", f"Pick up {object_text}"),
            ("pick_place", f"Pick up {object_text} and place it on the right target"),
        ):
            family_label = family.replace("_", "").title()
            spec = task_spec_from_text(request, env_id=f"Shape{index}{family_label}-v0")
            assert spec["task"]["scene"]["object"]["shape"] == shape
            spec_path = tmp_path / f"{shape}-{family}.yaml"
            spec_path.write_text(yaml.safe_dump(spec, sort_keys=True), encoding="utf-8")
            output = tmp_path / f"generated-{shape}-{family}"
            bundle = generate_task(spec_path, output_root=output, allowed_output_root=output)
            env = load_environment(bundle)
            try:
                env.reset(seed=0, options={"randomization_scale": 0.0})
                for _ in range(env.max_episode_steps):
                    _, _, terminated, truncated, info = env.step(env.scripted_action())
                    if terminated or truncated:
                        break
                assert info["is_success"] is True
            finally:
                env.close()


def test_wrist_actions_are_clipped_to_workspace(tmp_path: Path) -> None:
    bundle = _generate(tmp_path, "pick_up")
    env = load_environment(bundle)
    try:
        env.reset(seed=0)
        action = np.zeros(23, dtype=np.float32)
        action[:3] = 1.0
        for _ in range(100):
            env.step(action)
        np.testing.assert_array_less(env._wrist_position, env._workspace_max + 1e-12)
        np.testing.assert_array_less(env._workspace_min - 1e-12, env._wrist_position)
    finally:
        env.close()


def test_all_gesture_targets_respect_orca_v1_joint_limits() -> None:
    model = mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / "scenes" / "v1" / "scene_right.xml"))
    joint_ids = model.actuator_trnid[:, 0].astype(int)
    lower = model.jnt_range[joint_ids, 0]
    upper = model.jnt_range[joint_ids, 1]
    for sequence in GESTURE_SEQUENCES.values():
        for pose in sequence:
            assert np.all(pose >= lower)
            assert np.all(pose <= upper)


def test_manifest_exposes_v2_contract(tmp_path: Path) -> None:
    bundle = _generate(tmp_path, "pick_up")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["action_shape"] == [23]
    assert manifest["base_control"] == "kinematic_6dof"
    assert manifest["mount_visualization"] == "hidden"
    assert manifest["assistive_grasp"] is True
    assert {"request.txt", "README.md", "validation_report.json"}.issubset(manifest["files"])
