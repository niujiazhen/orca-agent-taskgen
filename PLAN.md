# Agent-Based RL Task Generation MVP

## Objective

Starting from `LynnUoE/orca_sim` commit
`02571cf7fbec1e57de615e61949d504440e2646a`, build a constrained,
reproducible task-generation pipeline that consumes versioned YAML TaskSpecs,
generates and registers an ORCA v1 `PinchAndHold-v0` environment plus one
parameterized variant, validates the generated artifacts, demonstrates that the
main task is learnable with PPO, and verifies a built wheel in a clean virtual
environment.

## Scope boundaries

- Work only in this `orca_sim` checkout.
- Treat the existing `orca_teleop` checkout as read-only.
- Do not modify the base hand meshes under `src/orca_sim/models/`.
- Do not overwrite the existing `runs/` artifacts.
- Do not claim that Cheng Su's videos prove stable physical grasping.
- Do not fabricate real retargeting trajectories. Synthetic fixtures must say
  `source: synthetic`.
- Arm integration, screw threads, RGB policies, hardware deployment, and
  sim-to-real are out of scope for this goal.

## Architecture contract

The agent workflow is deliberately constrained:

1. A planner validates a versioned TaskSpec.
2. A deterministic renderer generates only inside an allow-listed output tree.
3. A validator runs static, Gymnasium API, physics/contact, behavior, and
   reward-hacking checks.
4. A repair pass may update the spec or generated task, records each attempt,
   and reruns the same checks.

The accepted TaskSpec is the durable agent output. Rendering accepted specs is
deterministic so a teammate does not need the original LLM session to reproduce
the task.

## Phase gates

### P0 - Reproducible baseline

- Pin the source commit, Python 3.11, dependency versions, OS, and ORCA v1 in
  `ENVIRONMENT_LOCK.md`.
- Work on `codex/agent-task-generation`.
- Keep secrets, user-specific absolute paths, checkpoints, and large logs out
  of tracked files.

Pass: imports work and the lock file describes a reproducible installation.

### P1 - Unmodified upstream verification

- Run the full upstream pytest suite.
- Run `python -m orca_rl.checks`.
- Smoke-test v1 and v2 for deterministic resets, finite observations/rewards,
  stable shapes, and at least 10,000 cumulative steps each.
- Write machine-readable baseline evidence under `artifacts/`.

Pass: all upstream tests and reward checks pass; both versions complete the
stress test without non-finite values or shape drift.

### P2 - Versioned TaskSpec and gesture contracts

- Define a strict TaskSpec schema with version, environment ID, hand version,
  object, reset, reward, success, failure, randomization, and safety fields.
- Define a gesture-reference schema for timestamp, `qpos[17]`, `ctrl[17]`,
  source, hand version, and configuration provenance.
- Reject unknown fields, non-finite numbers, invalid sizes, unknown hand
  versions, bad IDs, missing success conditions, and unsafe paths.
- Record Cheng Su's repository/config provenance without copying claims from
  videos into physics evidence.

Pass: valid fixtures load; invalid and path-traversal fixtures fail with a
field-specific message; synthetic data is explicitly labeled.

### P3 - Constrained generator and validator

- Provide documented CLI entry points to validate, generate, and accept a spec.
- Restrict output to the configured generated-task directory.
- Record spec SHA-256, source commit, files, generation time, attempts, and
  validator results in a manifest.
- Detect absolute paths and changes outside the generated output tree.
- Include intentionally broken fixtures for XML/path, observation shape,
  non-finite reward, and success-contract failures.

Pass: generation is reproducible from a spec, malicious paths are rejected,
and every broken fixture is caught.

### P4 - `PinchAndHold-v0` behavior

The environment must require thumb contact, index contact, object in bounds,
not dropped, and ten consecutive valid steps. Closing the hand, one-finger
contact, transient contact, or holding after a drop must not count.

Pass:

- Gymnasium checker passes.
- 100 resets pass and seeded reset is reproducible.
- 10,000 cumulative steps have finite, stable observations and rewards.
- Across 100 fixed seeds: zero policy success is 0%, random is at most 5%,
  scripted is at least 90%, and scripted with mild reset randomization is at
  least 70%.
- Scripted mean return clearly exceeds zero and random baselines.
- Success and failure videos are produced.

### P5 - Non-one-off variant

- Generate a second registered environment from a separate spec by changing
  object/reset parameters without copying a bespoke environment class.

Pass: both IDs coexist in one process, geometry differs as specified, and the
variant passes API, seed, finite-value, and contact smoke tests.

### P6 - PPO learnability

- Train three seeds with Linxuan's PPO/VecNormalize design.
- Start at 1M steps per seed; extend only improving runs up to 3M.
- Evaluate each model on the same 100 fixed seeds and load its VecNormalize
  statistics.
- Log success, drop rate, hold duration, return, action std, and episode length.

Pass: mean success is at least 70%, every seed is at least 50%, improvement
over random is at least 30 percentage points, mild-randomization mean success
is at least 50%, and a trained-policy success video is recorded. The contact
and hold definition may not be weakened to obtain these numbers.

If three reward/environment repair cycles and the 3M-step cap still fail,
retain the failure evidence and ask for a scope or compute decision; do not
report completion.

### P7 - Clean distribution and handoff

- Build a wheel and install it into a newly created clean virtual environment.
- From the wheel, import, create, reset, step, and behavior-check the generated
  task with packaged XML/spec assets.
- Document exact generation, validation, training, evaluation, and recording
  commands.
- Produce `artifacts/acceptance_report.md` with evidence for P0-P7.

Pass: all mandatory gates are PASS, the full suite is green, the wheel smoke
test works without the source checkout, and no required work remains.

## Progress protocol

After each checkpoint, update `PROGRESS.md` with the phase status, changes,
commands, evidence, remaining risks, and next phase. A failed mandatory gate
stays failed until stronger evidence proves it passes.
