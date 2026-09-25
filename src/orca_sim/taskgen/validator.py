"""Static and runtime validation primitives for generated tasks."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree as ET

import gymnasium as gym
import numpy as np
import yaml
from gymnasium.utils.env_checker import check_env

from orca_sim.taskgen.contracts import ContractError, validate_task_spec
from orca_sim.taskgen.registry import register_generated_envs

ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"(?:^|[\"'\s])[A-Za-z]:[\\/]", re.MULTILINE),
    re.compile(r"/(?:Users|home)/[^/\s]+/"),
)


def _canonical_spec_hash(spec: dict) -> str:
    canonical = yaml.safe_dump(spec, sort_keys=True, allow_unicode=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_generated_directory(path: str | Path) -> dict:
    path = Path(path).resolve()
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ContractError("generated directory missing files: ['manifest.json']")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"task_spec.yaml", "scene.xml", "manifest.json"}
    if int(manifest.get("schema_version", 1)) == 2:
        required |= {"request.txt", "validation_report.json", "README.md"}
    names = {item.name for item in path.iterdir() if item.is_file()}
    missing = required - names
    if missing:
        raise ContractError(f"generated directory missing files: {sorted(missing)}")

    try:
        ET.parse(path / "scene.xml")
    except ET.ParseError as exc:
        raise ContractError(f"generated scene.xml is not well-formed: {exc}") from exc

    spec = yaml.safe_load((path / "task_spec.yaml").read_text(encoding="utf-8"))
    validate_task_spec(spec)
    if manifest.get("env_id") != spec["task"]["env_id"]:
        raise ContractError("manifest env_id does not match TaskSpec")
    if manifest.get("spec_sha256") != _canonical_spec_hash(spec):
        raise ContractError("manifest spec_sha256 does not match TaskSpec")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not all(isinstance(name, str) for name in raw_files):
        raise ContractError("manifest files must be a list of relative path strings")
    if len(raw_files) != len(set(raw_files)):
        raise ContractError("manifest files must not contain duplicates")
    for name in raw_files:
        posix = PurePosixPath(name)
        windows = PureWindowsPath(name)
        resolved = (path / name).resolve()
        if (
            not name
            or posix.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or ".." in posix.parts
            or ".." in windows.parts
            or resolved == path
            or path not in resolved.parents
        ):
            raise ContractError("manifest files contain an unsafe path")
    listed = set(raw_files)
    if not required.issubset(listed):
        raise ContractError("manifest files do not include all required generated files")
    absent = [name for name in listed if not (path / name).is_file()]
    if absent:
        raise ContractError(f"manifest lists missing generated files: {sorted(absent)}")
    text_names = [
        name for name in sorted(listed) if Path(name).suffix.lower() in {".xml", ".yaml", ".yml", ".json", ".md", ".txt"}
    ]
    text = "\n".join((path / name).read_text(encoding="utf-8") for name in text_names)
    for pattern in ABSOLUTE_PATH_PATTERNS:
        if pattern.search(text):
            raise ContractError("generated artifacts contain an absolute development-machine path")
    return {"env_id": manifest["env_id"], "generated_dir": path.name, "static": "pass"}


def validate_env_instance(env: gym.Env, *, steps: int = 200, seed: int = 0) -> dict:
    """Exercise one environment and reject shape drift or non-finite outputs."""

    try:
        preflight_obs, _ = env.reset(seed=seed)
        preflight_action = env.action_space.sample()
        next_obs, preflight_reward, _, _, _ = env.step(preflight_action)
        if next_obs.shape != preflight_obs.shape:
            raise ContractError("runtime observation shape changed during preflight")
        if not np.isfinite(next_obs).all() or not np.isfinite(preflight_reward):
            raise ContractError("runtime produced a non-finite observation or reward")
        check_env(env, skip_render_check=True)
        observation, _ = env.reset(seed=seed)
        expected_shape = observation.shape
        env.action_space.seed(seed)
        rewards = []
        completed = 0
        for index in range(steps):
            observation, reward, terminated, truncated, _ = env.step(env.action_space.sample())
            if observation.shape != expected_shape:
                raise ContractError("runtime observation shape changed")
            if not np.isfinite(observation).all() or not np.isfinite(reward):
                raise ContractError("runtime produced a non-finite observation or reward")
            rewards.append(float(reward))
            if terminated or truncated:
                completed += 1
                observation, _ = env.reset(seed=seed + index + 1)
        return {
            "runtime": "pass",
            "steps": steps,
            "episodes_completed": completed,
            "observation_shape": list(expected_shape),
            "action_shape": list(env.action_space.shape),
            "reward_range": [min(rewards), max(rewards)],
        }
    finally:
        env.close()


def validate_runtime(path: str | Path, *, steps: int = 200, seed: int = 0) -> dict:
    static = validate_generated_directory(path)
    root = Path(path).resolve().parent
    register_generated_envs(root)
    env = gym.make(static["env_id"], disable_env_checker=True).unwrapped
    return {**static, **validate_env_instance(env, steps=steps, seed=seed)}
