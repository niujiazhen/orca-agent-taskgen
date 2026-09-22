"""Aggregate and enforce the three-seed PPO acceptance gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_runs(run_dirs: list[str | Path], *, random_success_rate: float) -> dict:
    if len(run_dirs) != 3:
        raise ValueError("P6 requires exactly three independent seed runs")
    runs = []
    for value in run_dirs:
        run_dir = Path(value)
        training = _load(run_dir / "training_summary.json")
        nominal = _load(run_dir / "eval_nominal.json")
        mild = _load(run_dir / "eval_mild.json")
        if not (run_dir / training["model"]).is_file():
            raise FileNotFoundError(f"model missing from {run_dir}")
        if not (run_dir / training["vecnormalize"]).is_file():
            raise FileNotFoundError(f"VecNormalize statistics missing from {run_dir}")
        if training["model_timesteps"] < 1_000_000:
            raise ValueError(f"run {run_dir.name} did not reach the 1M-step budget")
        if nominal["episodes"] != 100 or mild["episodes"] != 100:
            raise ValueError("each P6 evaluation must contain exactly 100 episodes")
        if nominal["seed"] != mild["seed"]:
            raise ValueError("nominal and mild evaluations must use the same fixed seed set")
        runs.append(
            {
                "run": run_dir.name,
                "seed": training["seed"],
                "timesteps": training["model_timesteps"],
                "action_std": training["action_std"],
                "nominal": {
                    key: nominal[key]
                    for key in (
                        "success_rate",
                        "drop_rate",
                        "mean_return",
                        "mean_max_hold",
                        "mean_episode_length",
                    )
                },
                "mild": {
                    key: mild[key]
                    for key in (
                        "success_rate",
                        "drop_rate",
                        "mean_return",
                        "mean_max_hold",
                        "mean_episode_length",
                    )
                },
            }
        )
    seeds = [run["seed"] for run in runs]
    if len(set(seeds)) != 3:
        raise ValueError("P6 seed runs are not independent")

    nominal_rates = np.asarray([run["nominal"]["success_rate"] for run in runs])
    mild_rates = np.asarray([run["mild"]["success_rate"] for run in runs])
    aggregate = {
        "nominal_mean_success_rate": float(nominal_rates.mean()),
        "nominal_min_success_rate": float(nominal_rates.min()),
        "mild_mean_success_rate": float(mild_rates.mean()),
        "improvement_over_random": float(nominal_rates.mean() - random_success_rate),
    }
    criteria = {
        "three_independent_seeds": len(set(seeds)) == 3,
        "each_run_at_least_1m_steps": all(run["timesteps"] >= 1_000_000 for run in runs),
        "nominal_mean_success_ge_0_70": aggregate["nominal_mean_success_rate"] >= 0.70,
        "every_seed_success_ge_0_50": aggregate["nominal_min_success_rate"] >= 0.50,
        "improvement_over_random_ge_0_30": aggregate["improvement_over_random"] >= 0.30,
        "mild_mean_success_ge_0_50": aggregate["mild_mean_success_rate"] >= 0.50,
        "finite_positive_action_std": all(
            np.isfinite(run["action_std"]) and run["action_std"] > 0 for run in runs
        ),
    }
    if not all(criteria.values()):
        failed = [name for name, passed in criteria.items() if not passed]
        raise AssertionError(f"P6 acceptance failed: {failed}")
    return {
        "report_version": 1,
        "status": "pass",
        "random_baseline_success_rate": random_success_rate,
        "fixed_evaluation_seed": 20_000,
        "runs": runs,
        "aggregate": aggregate,
        "criteria": criteria,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs=3, type=Path)
    parser.add_argument("--behavior-report", type=Path, required=True)
    parser.add_argument("--video-report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    behavior = _load(args.behavior_report)
    random_rate = float(behavior["policies"]["random"]["success_rate"])
    result = summarize_runs(args.runs, random_success_rate=random_rate)
    if args.video_report:
        video = _load(args.video_report)
        if not video.get("success") or video.get("dropped"):
            raise AssertionError("trained-policy evidence video is not a successful episode")
        result["trained_policy_video"] = video
        result["criteria"]["trained_policy_success_video"] = True
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
