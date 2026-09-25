# ORCA Text-to-MuJoCo Environment Agent v2 Acceptance

Date: 2026-09-24

## Result

The v2 implementation passes the repository, bundle, scripted-feasibility, and
clean-wheel checks. These results validate generated environments; they are not
PPO results and do not claim that a learned policy has been trained.

## Canonical bundles

| Task | 10,000 finite steps | 100 seeded resets | Nominal scripted | Mild randomization | Zero / random false success |
| --- | --- | --- | --- | --- | --- |
| Hand gesture | PASS | PASS | 10/10 | 10/10 | 0/10 / 0/10 |
| Red cube pickup | PASS | PASS | 10/10 | 10/10 | 0/10 / 0/10 |
| Blue cylinder place | PASS | PASS | 10/10 | 10/10 | 0/10 / 0/10 |

All canonical environments expose a 23-dimensional normalized action space and
a 73-dimensional observation space. Each bundle contains a decodable MP4 and a
640 x 480 preview image.

## Packaging and regression

- Repository tests: 73 passed.
- TaskSpec v1 PinchAndHold compatibility: passed by regression tests.
- TaskSpec v2 schema, semantic checks, parser, generation, runtime, and
  registration: passed.
- Codex Skill, Plugin, and marketplace structure validation: passed.
- Clean Python 3.11 wheel install: passed.
- Text-to-environment wheel smoke test: generated and ran `WheelCube-v0` for
  200 finite steps.
- Wheel: `orca_sim-0.2.0-py3-none-any.whl`.
- SHA-256: `ed46835f17368197ff25012faaecc2d8fbb342486a74b9f16d79e42cf454fe99`.

## Scope note

The v2 wrist is a bounded kinematic 6DoF abstraction, and primitive-object
grasping uses an explicit assistive grasp model. This makes the generated tasks
usable as first-stage RL environments without claiming realistic arm dynamics
or high-fidelity contact-only grasping.
