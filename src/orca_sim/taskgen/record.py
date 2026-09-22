"""Record a trained PPO policy in a generated ORCA task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import gymnasium as gym
import mujoco
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from orca_sim.taskgen.evaluate import _raw_env
from orca_sim.taskgen.registry import register_generated_envs


def record_trained_policy(
    env_id: str,
    *,
    model_path: str | Path,
    vecnormalize_path: str | Path,
    output: str | Path,
    seed: int = 20_000,
    randomization_scale: float = 0.0,
    fps: int = 50,
) -> dict:
    import imageio.v2 as imageio

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
    env = gym.make(
        env_id,
        disable_env_checker=True,
        reset_randomization_scale=randomization_scale,
    ).unwrapped
    renderer = mujoco.Renderer(env.model, height=480, width=640)
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(env.model, camera)
    camera.azimuth = 140.0
    camera.elevation = -25.0
    camera.distance = 0.34
    frames = []
    try:
        observation, info = env.reset(seed=seed)
        camera.lookat[:] = env.data.xpos[env._object_body_id]
        renderer.update_scene(env.data, camera=camera)
        frames.extend([renderer.render().copy() for _ in range(10)])
        total_return = 0.0
        for step in range(env.max_episode_steps):
            normalized = normalizer.normalize_obs(observation[None, :])
            action, _ = model.predict(normalized, deterministic=True)
            observation, reward, terminated, truncated, info = env.step(action[0])
            total_return += reward
            camera.lookat[:] = env.data.xpos[env._object_body_id]
            renderer.update_scene(env.data, camera=camera)
            frames.append(renderer.render().copy())
            if terminated or truncated:
                break
        frames.extend([frames[-1].copy() for _ in range(25)])
    finally:
        renderer.close()
        env.close()
        normalizer.close()

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(output, frames, fps=fps)
    return {
        "env_id": env_id,
        "file": output.name,
        "seed": seed,
        "randomization_scale": randomization_scale,
        "frames": len(frames),
        "episode_length": step + 1,
        "return": float(total_return),
        "success": bool(info["is_success"]),
        "dropped": bool(info["dropped"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", default="PinchAndHold-v0")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--vecnormalize", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20_000)
    parser.add_argument("--randomization-scale", type=float, default=0.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = record_trained_policy(
        args.env_id,
        model_path=args.model,
        vecnormalize_path=args.vecnormalize or args.model.parent / "vecnormalize.pkl",
        output=args.output,
        seed=args.seed,
        randomization_scale=args.randomization_scale,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
