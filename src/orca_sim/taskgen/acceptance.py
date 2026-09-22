"""Behavioral acceptance and video evidence for generated tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gymnasium as gym
import mujoco
import numpy as np

from orca_sim.taskgen.registry import register_generated_envs
from orca_sim.taskgen.validator import validate_runtime


def _action(env, policy: str) -> np.ndarray:
    if policy == "zero":
        return np.zeros(env.action_space.shape, dtype=np.float32)
    if policy == "random":
        return env.action_space.sample()
    if policy == "scripted":
        return env.action_for_target(env.scripted_target_qpos)
    raise ValueError(f"Unknown policy: {policy}")


def evaluate_policy(
    env_id: str,
    *,
    policy: str,
    episodes: int,
    seed: int,
    randomization_scale: float,
) -> dict[str, Any]:
    successes = drops = 0
    returns: list[float] = []
    lengths: list[int] = []
    max_holds: list[int] = []
    for episode in range(episodes):
        env = gym.make(env_id, disable_env_checker=True).unwrapped
        try:
            episode_seed = seed + episode
            env.action_space.seed(10_000 + episode_seed)
            _, info = env.reset(
                seed=episode_seed,
                options={"randomization_scale": randomization_scale},
            )
            total = 0.0
            max_hold = 0
            for step in range(env.max_episode_steps):
                _, reward, terminated, truncated, info = env.step(_action(env, policy))
                total += reward
                max_hold = max(max_hold, int(info["hold_counter"]))
                if terminated or truncated:
                    break
            successes += int(info["is_success"])
            drops += int(info["dropped"])
            returns.append(float(total))
            lengths.append(step + 1)
            max_holds.append(max_hold)
        finally:
            env.close()
    return {
        "policy": policy,
        "randomization_scale": randomization_scale,
        "episodes": episodes,
        "successes": successes,
        "success_rate": successes / episodes,
        "drops": drops,
        "drop_rate": drops / episodes,
        "mean_return": float(np.mean(returns)),
        "std_return": float(np.std(returns)),
        "mean_episode_length": float(np.mean(lengths)),
        "mean_max_hold": float(np.mean(max_holds)),
    }


def validate_seeded_resets(env_id: str, *, count: int = 100) -> dict[str, Any]:
    env = gym.make(env_id, disable_env_checker=True).unwrapped
    try:
        first, _ = env.reset(seed=9182)
        second, _ = env.reset(seed=9182)
        if not np.array_equal(first, second):
            raise AssertionError("seeded reset is not reproducible")
        for seed in range(count):
            observation, _ = env.reset(seed=seed)
            if observation.shape != env.observation_space.shape or not np.isfinite(observation).all():
                raise AssertionError(f"reset {seed} returned an invalid observation")
        return {"resets": count, "seeded_reproducible": True, "status": "pass"}
    finally:
        env.close()


def validate_success_contract(env_id: str) -> dict[str, Any]:
    """Adversarially verify the contact/hold state machine without faking physics success."""

    env = gym.make(env_id, disable_env_checker=True).unwrapped
    try:
        env.reset(seed=0, options={"randomization_scale": 0.0})
        original_workspace = env._in_workspace
        original_dropped = env._dropped
        env._in_workspace = lambda: True
        env._dropped = lambda: False

        for thumb, index, label in (
            (True, False, "thumb_only"),
            (False, True, "index_only"),
            (False, False, "closed_without_contact"),
        ):
            env._hold_counter = 0
            env._success = False
            for _ in range(env.hold_steps + 2):
                if env._advance_hold(thumb, index):
                    raise AssertionError(f"{label} incorrectly satisfied success")

        env._hold_counter = 0
        env._success = False
        for _ in range(env.hold_steps - 1):
            if env._advance_hold(True, True):
                raise AssertionError("short dual contact incorrectly satisfied success")
        if not env._advance_hold(True, True):
            raise AssertionError("full dual-contact hold did not satisfy success")

        env._hold_counter = 0
        env._success = False
        env._dropped = lambda: True
        for _ in range(env.hold_steps + 2):
            if env._advance_hold(True, True):
                raise AssertionError("dropped object incorrectly satisfied success")
        env._in_workspace = original_workspace
        env._dropped = original_dropped
        return {
            "thumb_only": "rejected",
            "index_only": "rejected",
            "closed_without_contact": "rejected",
            "short_dual_contact": "rejected",
            "dropped_dual_contact": "rejected",
            "full_dual_contact_hold": "accepted",
            "status": "pass",
        }
    finally:
        env.close()


def record_policy_video(
    env_id: str,
    output: str | Path,
    *,
    policy: str,
    seed: int,
    randomization_scale: float = 0.0,
    fps: int = 50,
) -> dict[str, Any]:
    import imageio.v2 as imageio

    env = gym.make(env_id, disable_env_checker=True).unwrapped
    renderer = mujoco.Renderer(env.model, height=480, width=640)
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(env.model, camera)
    camera.azimuth = 140.0
    camera.elevation = -25.0
    camera.distance = 0.34
    frames = []
    try:
        env.action_space.seed(10_000 + seed)
        env.reset(seed=seed, options={"randomization_scale": randomization_scale})
        info = env._info()
        camera.lookat[:] = env.data.xpos[env._object_body_id]
        renderer.update_scene(env.data, camera=camera)
        frames.extend([renderer.render().copy() for _ in range(10)])
        for _ in range(env.max_episode_steps):
            _, _, terminated, truncated, info = env.step(_action(env, policy))
            camera.lookat[:] = env.data.xpos[env._object_body_id]
            renderer.update_scene(env.data, camera=camera)
            frames.append(renderer.render())
            if terminated or truncated:
                break
        frames.extend([frames[-1].copy() for _ in range(25)])
    finally:
        renderer.close()
        env.close()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(output, frames, fps=fps)
    return {
        "file": output.name,
        "policy": policy,
        "frames": len(frames),
        "success": bool(info["is_success"]),
        "dropped": bool(info["dropped"]),
    }


def accept_generated_task(
    generated_dir: str | Path,
    *,
    artifacts_dir: str | Path,
    episodes: int = 100,
    stress_steps: int = 10_000,
    videos: bool = True,
) -> dict[str, Any]:
    generated_dir = Path(generated_dir).resolve()
    artifacts_dir = Path(artifacts_dir).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    register_generated_envs(generated_dir.parent)
    manifest_path = generated_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    env_id = manifest["env_id"]

    runtime = validate_runtime(generated_dir, steps=stress_steps, seed=0)
    resets = validate_seeded_resets(env_id, count=100)
    contract = validate_success_contract(env_id)
    zero = evaluate_policy(env_id, policy="zero", episodes=episodes, seed=0, randomization_scale=0.0)
    random = evaluate_policy(env_id, policy="random", episodes=episodes, seed=0, randomization_scale=0.0)
    scripted = evaluate_policy(env_id, policy="scripted", episodes=episodes, seed=0, randomization_scale=0.0)
    mild = evaluate_policy(env_id, policy="scripted", episodes=episodes, seed=0, randomization_scale=0.5)
    margins = {
        "scripted_minus_zero_return": scripted["mean_return"] - zero["mean_return"],
        "scripted_minus_random_return": scripted["mean_return"] - random["mean_return"],
    }
    criteria = {
        "zero_success_eq_0": zero["success_rate"] == 0.0,
        "random_success_le_0_05": random["success_rate"] <= 0.05,
        "scripted_success_ge_0_90": scripted["success_rate"] >= 0.90,
        "mild_scripted_success_ge_0_70": mild["success_rate"] >= 0.70,
        "scripted_return_gt_zero": margins["scripted_minus_zero_return"] > 5.0,
        "scripted_return_gt_random": margins["scripted_minus_random_return"] > 5.0,
    }
    if not all(criteria.values()):
        failed = [name for name, passed in criteria.items() if not passed]
        raise AssertionError(f"behavior acceptance failed: {failed}")

    video_results: list[dict[str, Any]] = []
    if videos:
        video_results.append(
            record_policy_video(env_id, artifacts_dir / "scripted_success.mp4", policy="scripted", seed=7)
        )
        video_results.append(
            record_policy_video(env_id, artifacts_dir / "random_failure.mp4", policy="random", seed=11)
        )
        if not video_results[0]["success"]:
            raise AssertionError("scripted evidence video did not contain a successful episode")
        if video_results[1]["success"]:
            raise AssertionError("selected random failure video unexpectedly succeeded")

    report = {
        "report_version": 1,
        "env_id": env_id,
        "status": "pass",
        "runtime": runtime,
        "resets": resets,
        "success_contract": contract,
        "policies": {"zero": zero, "random": random, "scripted": scripted, "mild_scripted": mild},
        "return_margins": margins,
        "criteria": criteria,
        "videos": video_results,
    }
    report_path = generated_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_report = artifacts_dir / "behavior_acceptance.json"
    artifact_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["validation"] = "pass"
    manifest["validation_report"] = "validation_report.json"
    manifest["files"] = sorted(set(manifest["files"]) | {"validation_report.json"})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
