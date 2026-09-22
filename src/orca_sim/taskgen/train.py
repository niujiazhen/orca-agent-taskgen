"""PPO training for registered generated ORCA tasks.

Example:
    python -m orca_sim.taskgen.train --env-id PinchAndHold-v0 \
        --name pinch_seed0 --seed 0 --timesteps 1000000 --n-envs 8 --no-subproc
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import gymnasium as gym
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor, VecNormalize

from orca_rl.train import ClampLogStdCallback, resolve_tensorboard_dir
from orca_sim.taskgen.registry import register_generated_envs


class PinchMetricsCallback(BaseCallback):
    def __init__(self, window: int = 100) -> None:
        super().__init__()
        self.window = int(window)
        self.successes: list[float] = []
        self.drops: list[float] = []
        self.holds: list[float] = []
        self.lengths: list[float] = []

    def _on_step(self) -> bool:
        for info, done in zip(self.locals["infos"], self.locals["dones"]):
            if not done:
                continue
            self.successes.append(float(bool(info.get("is_success", False))))
            self.drops.append(float(bool(info.get("dropped", False))))
            self.holds.append(float(info.get("max_hold_counter", 0)))
            self.lengths.append(float(info.get("elapsed_steps", 0)))
        if len(self.successes) >= self.window:
            self.logger.record("task/success_rate", float(np.mean(self.successes)))
            self.logger.record("task/drop_rate", float(np.mean(self.drops)))
            self.logger.record("task/mean_max_hold", float(np.mean(self.holds)))
            self.logger.record("task/episode_length", float(np.mean(self.lengths)))
            self.successes.clear()
            self.drops.clear()
            self.holds.clear()
            self.lengths.clear()
        return True

    def _on_rollout_end(self) -> None:
        log_std = getattr(self.model.policy, "log_std", None)
        if log_std is not None:
            self.logger.record("task/action_std", float(log_std.detach().exp().mean().cpu()))


def make_env_fn(env_id: str, seed: int, rank: int, randomization_scale: float):
    def _init():
        register_generated_envs()
        env = gym.make(
            env_id,
            disable_env_checker=True,
            reset_randomization_scale=randomization_scale,
        ).unwrapped
        env.reset(seed=seed + rank)
        return env

    return _init


def build_vec_env(
    env_id: str,
    *,
    n_envs: int,
    seed: int,
    randomization_scale: float,
    subproc: bool,
    vecnormalize_path: Path | None = None,
):
    factories = [
        make_env_fn(env_id, seed, rank, randomization_scale) for rank in range(n_envs)
    ]
    venv = SubprocVecEnv(factories) if subproc and n_envs > 1 else DummyVecEnv(factories)
    venv = VecMonitor(venv)
    if vecnormalize_path is not None:
        normalized = VecNormalize.load(str(vecnormalize_path), venv)
        normalized.training = True
        normalized.norm_reward = True
        return normalized
    return VecNormalize(venv, norm_obs=True, norm_reward=True, clip_obs=10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", default="PinchAndHold-v0")
    parser.add_argument("--name", required=True)
    parser.add_argument("--timesteps", type=int, default=1_000_000)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--no-subproc", action="store_true")
    parser.add_argument("--randomization-scale", type=float, default=0.0)
    parser.add_argument("--n-steps", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--n-epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-range", type=float, default=0.2)
    parser.add_argument("--ent-coef", type=float, default=0.0)
    parser.add_argument("--vf-coef", type=float, default=0.5)
    parser.add_argument("--target-kl", type=float, default=0.02)
    parser.add_argument("--log-std-init", type=float, default=-0.5)
    parser.add_argument("--max-log-std", type=float, default=0.0)
    parser.add_argument("--checkpoint-every", type=int, default=250_000)
    parser.add_argument("--verbose", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument("--resume", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.randomization_scale < 0:
        raise SystemExit("--randomization-scale must be non-negative")
    register_generated_envs()
    if args.env_id not in gym.registry:
        raise SystemExit(f"Unknown generated environment: {args.env_id}")

    run_dir = Path("taskgen_runs") / args.name
    run_dir.mkdir(parents=True, exist_ok=True)
    stats_path = args.resume.parent / "vecnormalize.pkl" if args.resume else None
    if stats_path is not None and not stats_path.exists():
        raise SystemExit(f"VecNormalize statistics not found: {stats_path}")
    venv = build_vec_env(
        args.env_id,
        n_envs=args.n_envs,
        seed=args.seed,
        randomization_scale=args.randomization_scale,
        subproc=not args.no_subproc,
        vecnormalize_path=stats_path,
    )

    if args.resume:
        model = PPO.load(
            str(args.resume),
            env=venv,
            device=args.device,
            custom_objects={
                "learning_rate": args.lr,
                "clip_range": args.clip_range,
                "ent_coef": args.ent_coef,
                "target_kl": args.target_kl,
                "n_steps": args.n_steps,
                "batch_size": args.batch_size,
                "n_epochs": args.n_epochs,
            },
        )
        model.tensorboard_log = resolve_tensorboard_dir(run_dir)
    else:
        model = PPO(
            "MlpPolicy",
            venv,
            n_steps=args.n_steps,
            batch_size=args.batch_size,
            n_epochs=args.n_epochs,
            learning_rate=args.lr,
            gamma=args.gamma,
            gae_lambda=args.gae_lambda,
            clip_range=args.clip_range,
            ent_coef=args.ent_coef,
            vf_coef=args.vf_coef,
            max_grad_norm=0.5,
            target_kl=args.target_kl,
            policy_kwargs={
                "net_arch": {"pi": [256, 256], "vf": [256, 256]},
                "log_std_init": args.log_std_init,
            },
            tensorboard_log=resolve_tensorboard_dir(run_dir),
            seed=args.seed,
            device=args.device,
            verbose=args.verbose,
        )

    callbacks = [
        PinchMetricsCallback(),
        ClampLogStdCallback(args.max_log_std),
        CheckpointCallback(
            save_freq=max(args.checkpoint_every // args.n_envs, 1),
            save_path=str(run_dir / "checkpoints"),
            name_prefix="ppo",
            save_vecnormalize=True,
        ),
    ]
    model.learn(
        total_timesteps=args.timesteps,
        callback=callbacks,
        reset_num_timesteps=args.resume is None,
        progress_bar=False,
    )
    model.save(run_dir / "final_model")
    venv.save(str(run_dir / "vecnormalize.pkl"))
    action_std = float(model.policy.log_std.detach().exp().mean().cpu())
    summary = {
        "env_id": args.env_id,
        "seed": args.seed,
        "requested_timesteps": args.timesteps,
        "model_timesteps": model.num_timesteps,
        "n_envs": args.n_envs,
        "randomization_scale": args.randomization_scale,
        "action_std": action_std,
        "model": "final_model.zip",
        "vecnormalize": "vecnormalize.pkl",
    }
    (run_dir / "training_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    venv.close()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
