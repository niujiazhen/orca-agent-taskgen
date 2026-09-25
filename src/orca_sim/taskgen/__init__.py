"""Constrained task generation for ORCA hand reinforcement learning."""

from orca_sim.taskgen.contracts import (
    ContractError,
    load_gesture_reference,
    load_task_spec,
    validate_gesture_reference,
    validate_task_spec,
)
from orca_sim.taskgen.registry import register_task_bundle
from orca_sim.taskgen.text import UnsupportedTaskError, task_spec_from_text


def load_environment(path, *, render_mode=None, **kwargs):
    """Load one generated bundle without requiring callers to manage registration."""

    import gymnasium as gym

    env_id = register_task_bundle(path)
    return gym.make(
        env_id,
        render_mode=render_mode,
        disable_env_checker=True,
        **kwargs,
    ).unwrapped

__all__ = [
    "ContractError",
    "load_gesture_reference",
    "load_task_spec",
    "validate_gesture_reference",
    "validate_task_spec",
    "UnsupportedTaskError",
    "load_environment",
    "register_task_bundle",
    "task_spec_from_text",
]
