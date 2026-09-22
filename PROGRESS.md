# Goal Progress

## P0 - Reproducible baseline

Status: PASS

Changes:

- Confirmed the source checkout is exactly
  `02571cf7fbec1e57de615e61949d504440e2646a` from `LynnUoE/orca_sim`.
- Created branch `codex/agent-task-generation`.
- Read the repository README, `orca_rl/README.md`, `orca_rl/task.py`,
  `orca_rl/train.py`, `orca_rl/evaluate.py`, `orca_rl/record.py`, and
  `orca_rl/diagnose.py` before modifying project code.
- Created a dedicated Python 3.11 virtual environment and installed the project
  plus validation, training, packaging, and video dependencies.
- Added `PLAN.md`, `PROGRESS.md`, and `ENVIRONMENT_LOCK.md` before project-code
  changes.

Commands:

```text
git rev-parse HEAD
git switch -c codex/agent-task-generation
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -e . pytest stable-baselines3 imageio[ffmpeg] tensorboard pyyaml jsonschema build
```

Evidence:

- Git HEAD: `02571cf7fbec1e57de615e61949d504440e2646a`
- Python: 3.11.9
- Dependency versions are recorded in `ENVIRONMENT_LOCK.md`.

Remaining risks:

- Upstream packaging rules must later be verified against all v1 assets in a
  built wheel.
- Existing RL training/evaluation/recording commands are hard-wired to the cube
  task and need a task factory without regressing the baseline.

Next phase:

- P0 imports and diff checks passed. Continue with P2 after the completed P1
  baseline verification.

## P1 - Unmodified upstream verification

Status: PASS

Changes:

- Ran the unmodified upstream suite and Linxuan reward-exploit checks.
- Stress-tested both `CubeReorientContinuous(version="v1")` and `version="v2"`
  for 10,000 cumulative random-policy steps with seeded reset checks.
- Recorded machine-readable evidence in `artifacts/baseline_report.json`.

Commands:

```text
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m orca_rl.checks
<inline v1/v2 deterministic-reset and 10,000-step finite-value stress test>
```

Evidence:

- Upstream: 31 tests passed.
- Reward checks: all checks passed; idle return `+0.02`, oracle return `+55.35`.
- v1: 10,000 steps, 33 completed episodes, observation `(54,)`, action `(17,)`.
- v2: 10,000 steps, 54 completed episodes, observation `(54,)`, action `(17,)`.
- Both seeded resets were bitwise reproducible and all observations/rewards were
  finite.

Remaining risks:

- The upstream random-policy sampling is stochastic unless its action space is
  explicitly seeded; the stress test seeded it.
- Baseline evaluation code constructs the default v2 task and must be made
  task-selectable for the generated ORCA v1 environment.

Next phase:

- Implement strict versioned TaskSpec and gesture-reference contracts with
  adversarial validation tests.

## P2 - TaskSpec and gesture contracts

Status: PASS

- Added strict Draft 2020-12 JSON schemas for TaskSpec v1 and gesture reference
  v1, plus safe YAML loaders and semantic checks.
- Unknown fields, NaN/Infinity, invalid array lengths, unsafe relative paths,
  unsupported hand versions, non-monotonic timestamps, and invalid workspace
  geometry are rejected.
- Added two canonical specs and an explicitly synthetic gesture fixture with
  Cheng Su repository/configuration provenance.
- Evidence: contract and adversarial tests pass in the full suite.

## P3 - Generator and validator

Status: PASS

- Added deterministic TaskSpec-to-MuJoCo generation, generated-task discovery,
  Gym registration, static/runtime validators, and CLI commands.
- Manifests record spec SHA-256, baseline commit, attempt, timestamp, file list,
  and validation result. Output confinement and portable relative includes are
  enforced.
- Adversarial tests cover output escape, absolute paths (including listed
  validation reports), malformed XML, observation-shape drift, and NaN reward.
- Evidence: both generated directories pass static and runtime validation.

## P4 - PinchAndHold behavior

Status: PASS

- `PinchAndHold-v0` uses physical MuJoCo contacts on the thumb distal and index
  distal bodies. Success additionally requires workspace bounds, no drop, and
  ten consecutive valid steps.
- 100 seeded resets and 10,000 random runtime steps pass with observation `(55,)`
  and action `(17,)`.
- Fixed 100-episode results: zero 0%, random 3%, scripted 100%, scripted with
  mild randomization 100%. Scripted return exceeds zero/random by 17.39/16.91.
- Reward-hacking probes reject thumb-only, index-only, closed/no-contact,
  transient dual contact, and dropped-object dual contact.
- Evidence: `artifacts/pinch_and_hold/behavior_acceptance.json`, plus 46-frame
  scripted-success and 62-frame random-failure videos.

## P5 - Parameterized variant

Status: PASS

- Generated and registered `PinchAndHoldSmall-v0` from a separate spec using
  the same environment class; object radius/length/mass and reset jitter differ.
- It passes 10,000 runtime steps and all contact-contract checks.
- Fixed 100-episode results: zero 0%, random 0%, scripted 100%, mild scripted
  99%.
- Evidence: `artifacts/pinch_and_hold_small/behavior_acceptance.json`.

## P6 - PPO learnability

Status: PASS

- Trained independent seeds 0, 1, and 2 for 1,001,472 steps each with PPO,
  VecNormalize, and Linxuan's two-layer policy/value design.
- Each model was evaluated on the same 100 seeds with its own
  `vecnormalize.pkl`.
- Nominal success: 100%, 100%, 100%; mild-randomization success: 100%, 100%,
  95%; nominal drop: 0% for every seed.
- Aggregate nominal success is 100%, minimum seed is 100%, improvement over the
  3% random baseline is 97 points, and mild mean success is 98.33%.
- Evidence: `artifacts/pinch_and_hold/ppo_acceptance.json` and a 46-frame
  trained-policy success video. Final full suite: 59 passed.

## P7 - Clean distribution and handoff

Status: PASS

- Built `orca_sim-0.1.0-py3-none-any.whl`; its archive contains Python modules,
  schemas, specs, generated XML/manifests/reports, v1 scenes, MJCF, and STL
  assets.
- Installed only that wheel into a new Python 3.11 virtual environment outside
  the checkout. The imported module resolved to the clean environment's
  `site-packages`.
- From the clean install: static/runtime validation passed for 1,000 steps (39
  episodes), and a mild-randomization scripted episode succeeded in 11 steps
  with hold counter 10 and no drop.
- README documents generation, validation, training, evaluation, aggregation,
  and video commands. Final evidence is in `artifacts/acceptance_report.md`.
