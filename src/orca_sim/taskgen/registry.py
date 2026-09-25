"""Discovery and Gymnasium registration for generated task artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import gymnasium as gym

GENERATED_ROOT = Path(__file__).resolve().parent / "generated"


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
        schema_version = int(record["manifest"].get("schema_version", 1))
        entry_point = (
            "orca_sim.taskgen.generic_env:GeneratedOrcaEnv"
            if schema_version == 2
            else "orca_sim.taskgen.env:PinchAndHoldEnv"
        )
        kwargs = {
            "spec_path": str(record["spec_path"]),
            "scene_path": str(record["scene_path"]),
        }
        existing = gym.registry.get(env_id)
        if existing is not None:
            if not str(existing.entry_point).startswith("orca_sim.taskgen."):
                raise ValueError(f"Environment ID is already registered by another package: {env_id}")
            if existing.entry_point == entry_point and existing.kwargs == kwargs:
                continue
            del gym.registry[env_id]
        gym.register(id=env_id, entry_point=entry_point, kwargs=kwargs)
    return tuple(tasks)


def register_task_bundle(path: str | Path) -> str:
    """Register one generated task bundle and return its Gymnasium ID."""

    bundle = Path(path).resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    register_generated_envs(bundle.parent)
    return str(manifest["env_id"])
