from __future__ import annotations

import json
from pathlib import Path

import pytest

from orca_sim.taskgen.ppo_acceptance import summarize_runs


def _write_run(root: Path, seed: int, nominal: float, mild: float) -> Path:
    run = root / f"seed{seed}"
    run.mkdir()
    (run / "final_model.zip").write_bytes(b"model")
    (run / "vecnormalize.pkl").write_bytes(b"stats")
    (run / "training_summary.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "model_timesteps": 1_000_000,
                "action_std": 0.5,
                "model": "final_model.zip",
                "vecnormalize": "vecnormalize.pkl",
            }
        ),
        encoding="utf-8",
    )
    common = {
        "episodes": 100,
        "seed": 20_000,
        "drop_rate": 0.0,
        "mean_return": 10.0,
        "mean_max_hold": 10.0,
        "mean_episode_length": 11.0,
    }
    (run / "eval_nominal.json").write_text(
        json.dumps({**common, "success_rate": nominal}), encoding="utf-8"
    )
    (run / "eval_mild.json").write_text(
        json.dumps({**common, "success_rate": mild}), encoding="utf-8"
    )
    return run


def test_summarize_runs_passes_three_seed_gate(tmp_path: Path) -> None:
    runs = [_write_run(tmp_path, seed, 0.8, 0.6) for seed in range(3)]
    report = summarize_runs(runs, random_success_rate=0.03)
    assert report["status"] == "pass"
    assert report["aggregate"]["nominal_mean_success_rate"] == pytest.approx(0.8)


def test_summarize_runs_rejects_weak_seed(tmp_path: Path) -> None:
    runs = [
        _write_run(tmp_path, 0, 1.0, 0.6),
        _write_run(tmp_path, 1, 1.0, 0.6),
        _write_run(tmp_path, 2, 0.49, 0.6),
    ]
    with pytest.raises(AssertionError, match="every_seed"):
        summarize_runs(runs, random_success_rate=0.03)
