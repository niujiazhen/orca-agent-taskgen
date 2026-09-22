from __future__ import annotations

import gymnasium as gym

from orca_sim.taskgen.acceptance import validate_success_contract
from orca_sim.taskgen.registry import register_generated_envs


def test_success_contract_rejects_reward_hacking_states() -> None:
    register_generated_envs()
    result = validate_success_contract("PinchAndHold-v0")
    assert result["status"] == "pass"
    assert result["thumb_only"] == "rejected"
    assert result["index_only"] == "rejected"
    assert result["short_dual_contact"] == "rejected"
    assert result["dropped_dual_contact"] == "rejected"


def test_physical_scripted_controller_reaches_dual_contact_hold() -> None:
    register_generated_envs()
    env = gym.make("PinchAndHold-v0", disable_env_checker=True).unwrapped
    try:
        env.reset(seed=0, options={"randomization_scale": 0.0})
        for _ in range(env.max_episode_steps):
            _, _, terminated, truncated, info = env.step(
                env.action_for_target(env.scripted_target_qpos)
            )
            if terminated or truncated:
                break
        assert info["is_success"]
        assert info["dual_contact"]
        assert info["hold_counter"] >= env.hold_steps
        assert not info["dropped"]
    finally:
        env.close()
