"""Discovery and Gymnasium registration for generated task artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import gymnasium as gym

from orca_sim.taskgen.generator import GENERATED_ROOT


def discover_generated_tasks(root: str | Path = GENERATED_ROOT) -> dict[str, dict]:
    discovered: dict[str, dict] = {}
    root = Path(root)
    if not root.exists():
        return discovered
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        env_id = manifest["env_id"]
        if env_id in discovered:
            raise ValueError(f"Duplicate generated environment ID: {env_id}")
        discovered[env_id] = {
            "manifest": manifest,
            "manifest_path": manifest_path,
            "spec_path": manifest_path.parent / "task_spec.yaml",
            "scene_path": manifest_path.parent / "scene.xml",
        }
    return discovered


def register_generated_envs(root: str | Path = GENERATED_ROOT) -> tuple[str, ...]:
    tasks = discover_generated_tasks(root)
    for env_id, record in tasks.items():
        if env_id not in gym.registry:
            gym.register(
                id=env_id,
                entry_point="orca_sim.taskgen.env:PinchAndHoldEnv",
                kwargs={
                    "spec_path": str(record["spec_path"]),
                    "scene_path": str(record["scene_path"]),
                },
            )
    return tuple(tasks)
