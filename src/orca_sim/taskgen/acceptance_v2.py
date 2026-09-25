"""Non-learning feasibility acceptance for TaskSpec v2 bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from orca_sim.taskgen import load_environment
from orca_sim.taskgen.validator import validate_runtime


def _rollout(bundle: Path, policy: str, seed: int, randomization_scale: float) -> dict[str, Any]:
    env = load_environment(bundle)
    total_reward = 0.0
    try:
        env.action_space.seed(10_000 + seed)
        _, info = env.reset(seed=seed, options={"randomization_scale": randomization_scale})
        for step in range(env.max_episode_steps):
            if policy == "scripted":
                action = env.scripted_action()
            elif policy == "zero":
                action = np.zeros(env.action_space.shape, dtype=np.float32)
            elif policy == "random":
                action = env.action_space.sample()
            else:
                raise ValueError(f"Unknown policy: {policy}")
            _, reward, terminated, truncated, info = env.step(action)
            total_reward += float(reward)
            if terminated or truncated:
                break
        return {
            "success": bool(info["is_success"]),
            "steps": step + 1,
            "return": total_reward,
        }
    finally:
        env.close()


def _evaluate(bundle: Path, policy: str, episodes: int, scale: float) -> dict[str, Any]:
    results = [_rollout(bundle, policy, seed, scale) for seed in range(episodes)]
    return {
        "policy": policy,
        "episodes": episodes,
        "randomization_scale": scale,
        "successes": sum(int(item["success"]) for item in results),
        "success_rate": sum(int(item["success"]) for item in results) / episodes,
        "mean_return": float(np.mean([item["return"] for item in results])),
        "mean_steps": float(np.mean([item["steps"] for item in results])),
    }


def validate_seeded_resets(bundle: Path, count: int = 100) -> dict[str, Any]:
    env = load_environment(bundle)
    try:
        first, _ = env.reset(seed=9182)
        second, _ = env.reset(seed=9182)
        if not np.array_equal(first, second):
            raise AssertionError("seeded reset is not reproducible")
        for seed in range(count):
            observation, _ = env.reset(seed=seed)
            if observation.shape != env.observation_space.shape or not np.isfinite(observation).all():
                raise AssertionError(f"reset {seed} returned an invalid observation")
        return {"status": "pass", "count": count, "seeded_reproducible": True}
    finally:
        env.close()


def accept_v2_bundle(
    path: str | Path,
    *,
    episodes: int = 10,
    stress_steps: int = 10_000,
    reset_count: int = 100,
) -> dict[str, Any]:
    """Accept a v2 bundle without optimization or trained policies."""

    bundle = Path(path).resolve()
    runtime = validate_runtime(bundle, steps=stress_steps, seed=0)
    resets = validate_seeded_resets(bundle, count=reset_count)
    scripted = _evaluate(bundle, "scripted", episodes, 0.0)
    mild = _evaluate(bundle, "scripted", episodes, 0.5)
    zero = _evaluate(bundle, "zero", episodes, 0.0)
    random = _evaluate(bundle, "random", episodes, 0.0)
    criteria = {
        "scripted_nominal_ge_0_90": scripted["success_rate"] >= 0.90,
        "scripted_mild_ge_0_70": mild["success_rate"] >= 0.70,
        "zero_success_eq_0": zero["success_rate"] == 0.0,
        "random_success_le_0_05": random["success_rate"] <= 0.05,
    }
    report = {
        "report_version": 2,
        "status": "pass" if all(criteria.values()) else "fail",
        "validation_kind": "non-learning scripted feasibility; no PPO or trained policy",
        "runtime": runtime,
        "resets": resets,
        "policies": {"scripted": scripted, "mild_scripted": mild, "zero": zero, "random": random},
        "criteria": criteria,
    }
    (bundle / "validation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation"] = report["status"]
    manifest["validation_report"] = "validation_report.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["status"] != "pass":
        failed = [name for name, passed in criteria.items() if not passed]
        raise AssertionError(f"v2 behavior acceptance failed: {failed}")
    return report
