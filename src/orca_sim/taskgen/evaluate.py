"""Fixed-seed evaluation for generated ORCA PPO policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import gymnasium as gym
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from orca_sim.taskgen.registry import register_generated_envs


def _raw_env(env_id: str, randomization_scale: float):
    return gym.make(
        env_id,
        disable_env_checker=True,
        reset_randomization_scale=randomization_scale,
    ).unwrapped


def evaluate_model(
    env_id: str,
    *,
    model_path: str | Path,
    vecnormalize_path: str | Path,
    episodes: int = 100,
    seed: int = 20_000,
    randomization_scale: float = 0.0,
) -> dict:
    register_generated_envs()
    model_path = Path(model_path)
    vecnormalize_path = Path(vecnormalize_path)
    if not vecnormalize_path.is_file():
        raise FileNotFoundError(f"VecNormalize statistics are required: {vecnormalize_path}")
    model = PPO.load(str(model_path), device="cpu")
    dummy = DummyVecEnv([lambda: _raw_env(env_id, randomization_scale)])
    normalizer = VecNormalize.load(str(vecnormalize_path), dummy)
    normalizer.training = False
    normalizer.norm_reward = False

    successes = drops = 0
    returns: list[float] = []
    holds: list[int] = []
    lengths: list[int] = []
    for episode in range(episodes):
        env = _raw_env(env_id, randomization_scale)
        try:
            observation, info = env.reset(seed=seed + episode)
            total = 0.0
            max_hold = 0
            for step in range(env.max_episode_steps):
                normalized = normalizer.normalize_obs(observation[None, :])
                action, _ = model.predict(normalized, deterministic=True)
                observation, reward, terminated, truncated, info = env.step(action[0])
                total += reward
                max_hold = max(max_hold, int(info["hold_counter"]))
                if terminated or truncated:
                    break
            successes += int(info["is_success"])
            drops += int(info["dropped"])
            returns.append(float(total))
            holds.append(max_hold)
            lengths.append(step + 1)
        finally:
            env.close()
    dummy.close()
    action_std = float(model.policy.log_std.detach().exp().mean().cpu())
    return {
        "env_id": env_id,
        "model": str(model_path),
        "vecnormalize": str(vecnormalize_path),
        "episodes": episodes,
        "seed": seed,
        "randomization_scale": randomization_scale,
        "successes": successes,
        "success_rate": successes / episodes,
        "drops": drops,
        "drop_rate": drops / episodes,
        "mean_return": float(np.mean(returns)),
        "std_return": float(np.std(returns)),
        "mean_max_hold": float(np.mean(holds)),
        "mean_episode_length": float(np.mean(lengths)),
        "action_std": action_std,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", default="PinchAndHold-v0")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--vecnormalize", type=Path)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20_000)
    parser.add_argument("--randomization-scale", type=float, default=0.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    stats = args.vecnormalize or args.model.parent / "vecnormalize.pkl"
    result = evaluate_model(
        args.env_id,
        model_path=args.model,
        vecnormalize_path=stats,
        episodes=args.episodes,
        seed=args.seed,
        randomization_scale=args.randomization_scale,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
