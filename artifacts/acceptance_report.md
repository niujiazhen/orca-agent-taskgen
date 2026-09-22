# Agent-Based RL Task Generation MVP — Acceptance Report

Date: 2026-09-22 (America/Los_Angeles)

Source: `LynnUoE/orca_sim` commit
`02571cf7fbec1e57de615e61949d504440e2646a`, branch
`codex/agent-task-generation`.

## Result

All mandatory P0-P7 gates pass. The deliverable is a constrained,
reproducible TaskSpec-to-MuJoCo pipeline with two usable ORCA v1 Gymnasium
environments, adversarial validation, three-seed PPO evidence, videos, and a
clean-wheel smoke test.

## Gate evidence

| Gate | Status | Evidence |
|---|---:|---|
| P0 baseline lock | PASS | Python 3.11.9 and dependency/source pins in `ENVIRONMENT_LOCK.md`; no base meshes changed. |
| P1 upstream verification | PASS | Original 31 tests pass; `orca_rl.checks` passes; v1/v2 each survive 10,000 finite steps with deterministic resets. See `baseline_report.json`. |
| P2 contracts | PASS | Strict versioned schemas and semantic validation reject unknown/unsafe/non-finite/malformed inputs; synthetic provenance is explicit. |
| P3 generator | PASS | Output confinement, portable relative includes, spec hash/commit manifest, registration, static/runtime CLI, and broken-fixture tests pass. |
| P4 main behavior | PASS | 10,000 finite steps; zero 0%, random 3%, scripted 100%, mild scripted 100%; all contact/hold exploit probes rejected. |
| P5 variant | PASS | `PinchAndHoldSmall-v0` shares the generic class, changes object/reset parameters, survives 10,000 steps, and achieves scripted 100% / mild 99%. |
| P6 PPO | PASS | Three independent 1,001,472-step seeds: nominal 100/100/100%, mild 100/100/95%; trained success video passes. |
| P7 distribution | PASS | Wheel contains all required assets; clean-install 1,000-step runtime and 11-step mild-randomization success checks pass outside the checkout. |

## Main behavior metrics

- Observation/action shapes: `(55,)` / `(17,)`.
- Success contract: thumb contact + index contact + object in workspace + not
  dropped for 10 consecutive steps.
- Zero policy: 0/100 success, mean return -6.3564.
- Random policy: 3/100 success, mean return -5.8704, 97% drop rate.
- Scripted policy: 100/100 success, mean return 11.0348, 0% drop rate.
- Mild-randomized scripted policy: 100/100 success, mean return 11.3263.
- Scripted return margins over zero/random: +17.3912 / +16.9051.

The machine-readable source is
`artifacts/pinch_and_hold/behavior_acceptance.json`. The evidence videos are
`scripted_success.mp4`, `random_failure.mp4`, and
`trained_policy_success.mp4` in the same directory.

## PPO metrics

| Seed | Steps | Nominal success | Mild success | Nominal drop | Action std |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,001,472 | 100% | 100% | 0% | 0.5713 |
| 1 | 1,001,472 | 100% | 100% | 0% | 0.5759 |
| 2 | 1,001,472 | 100% | 95% | 0% | 0.5637 |

Aggregate nominal success is 100%, the weakest seed is 100%, improvement over
the 3% random baseline is 97 percentage points, and mild-randomization mean is
98.33%. All exceed the P6 thresholds of 70%, 50%, 30 points, and 50%,
respectively. See `artifacts/pinch_and_hold/ppo_acceptance.json`.

## Distribution evidence

`orca_sim-0.1.0-py3-none-any.whl` was installed in a new Python 3.11 virtual
environment outside the checkout. Import resolved from that environment's
`site-packages`. From the wheel, `PinchAndHold-v0` passed static validation and
1,000 runtime steps (39 completed episodes), then completed a scripted episode
under reset-randomization scale 0.5 in 11 steps with hold counter 10 and no
drop. The wheel SHA-256 is
`99dc40a99dd9db7f8642f8fd33af7f793bc49a5b7ba02051d5b815aa7b8f37a6`.
See `artifacts/wheel_smoke_report.json`.

## Tests and limitations

- Final project suite: 59 passed. Gymnasium emits two non-fatal warnings because
  the observation space intentionally uses infinite numeric bounds.
- Cheng Su's repository/config is used only as provenance and design reference.
  The included gesture is labeled synthetic; no claim is made that repository
  videos are verified physical-contact trajectories.
- This MVP does not cover arm integration, threaded assembly, vision policies,
  hardware deployment, or sim-to-real transfer.
