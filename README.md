# ORCA Agent Task Generation

A constrained Agent pipeline that turns structured YAML TaskSpecs into usable,
validated, and trainable MuJoCo/Gymnasium environments for the ORCA v1 hand.

Built from [`LynnUoE/orca_sim`](https://github.com/LynnUoE/orca_sim) commit
`02571cf7fbec1e57de615e61949d504440e2646a`.

## What was completed

- Versioned JSON schemas for task and gesture specifications.
- Safe YAML validation: rejects unknown fields, NaN/Inf, unsupported hand
  versions, absolute paths, and path traversal.
- Deterministic TaskSpec-to-MuJoCo generation with SHA-256 manifests.
- Two registered ORCA v1 environments:
  - `PinchAndHold-v0`
  - `PinchAndHoldSmall-v0`, generated from a parameter variant.
- Physical success contract requiring thumb contact, index contact, object in
  bounds, no drop, and 10 consecutive valid simulation steps.
- Automated static, Gymnasium, physics, behavior, reward-hacking, and packaging
  checks.
- PPO/VecNormalize training and fixed-seed evaluation over three seeds.
- Clean-wheel installation and runtime verification outside the source tree.

```text
TaskSpec YAML -> Schema Validator -> MuJoCo Generator -> Gym Registration
              -> Behavior/Physics Gates -> PPO Training -> Acceptance Report
```

## Use the Agent pipeline

### 1. Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[rl,dev]"
```

### 2. Define and generate a task

Copy or edit a spec under `src/orca_sim/taskgen/specs/`, then run:

```powershell
.\.venv\Scripts\python.exe -m orca_sim.taskgen.cli validate src/orca_sim/taskgen/specs/pinch_and_hold_v0.yaml
.\.venv\Scripts\python.exe -m orca_sim.taskgen.cli generate src/orca_sim/taskgen/specs/pinch_and_hold_v0.yaml
.\.venv\Scripts\python.exe -m orca_sim.taskgen.cli accept src/orca_sim/taskgen/generated/pinchandhold_v0 --artifacts artifacts/pinch_and_hold
```

The durable Agent output is the validated TaskSpec. The generator creates
portable XML, a normalized spec, a manifest, and a validation report.

### 3. Use the generated environment

```python
import gymnasium as gym
from orca_sim import register_envs

register_envs()
env = gym.make("PinchAndHold-v0")
observation, info = env.reset(seed=0)
observation, reward, terminated, truncated, info = env.step(
    env.action_space.sample()
)
env.close()
```

### 4. Train and evaluate

```powershell
.\.venv\Scripts\python.exe -m orca_sim.taskgen.train --env-id PinchAndHold-v0 --name ppo_seed0 --seed 0 --timesteps 1000000 --n-envs 8 --no-subproc
.\.venv\Scripts\python.exe -m orca_sim.taskgen.evaluate --env-id PinchAndHold-v0 --model taskgen_runs/ppo_seed0/final_model.zip --vecnormalize taskgen_runs/ppo_seed0/vecnormalize.pkl --episodes 100 --seed 20000 --out taskgen_runs/ppo_seed0/eval_nominal.json
```

Evaluation requires the matching `vecnormalize.pkl`. See [`PLAN.md`](PLAN.md)
for all acceptance thresholds and
[`artifacts/acceptance_report.md`](artifacts/acceptance_report.md) for the full
evidence trail.

## Results

| Check | Result |
|---|---:|
| Full test suite | 59 passed |
| Zero policy success | 0% |
| Random policy success | 3% |
| Scripted policy success | 100% |
| PPO success, seeds 0/1/2 | 100% / 100% / 100% |
| PPO success with mild randomization | 100% / 100% / 95% |
| Random runtime stress | 10,000 steps, finite and shape-stable |
| Clean wheel smoke test | PASS |

### Trained PPO policy

![Trained PPO pinch success](artifacts/pinch_and_hold/trained_policy_success.gif)

[MP4](artifacts/pinch_and_hold/trained_policy_success.mp4) ·
[PPO metrics](artifacts/pinch_and_hold/ppo_acceptance.json)

### Random policy failure

![Random policy failure](artifacts/pinch_and_hold/random_failure.gif)

[MP4](artifacts/pinch_and_hold/random_failure.mp4) ·
[Behavior metrics](artifacts/pinch_and_hold/behavior_acceptance.json)

## Scope and provenance

This is an RL-environment generation MVP, not a complete assembly system. It
does not include robot-arm integration, screw threads, vision policies,
hardware deployment, or sim-to-real transfer.

Cheng Su's
[`orcahand-retarget-experiments`](https://github.com/back2-thebasic/orcahand-retarget-experiments)
commit `032b5fd424cb67d9e6203388d9de0edc7453eff6` is used only as ORCA v1 pose and
retargeting-configuration provenance. The included gesture fixture is explicitly
marked synthetic and is not presented as recorded physical grasp data.
