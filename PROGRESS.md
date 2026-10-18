# Implementation Progress

## v0.3 photo workflow

- Added SceneSpec v1, TaskSpec v3, six rigid asset categories, and separate scene
  and multi-object RL APIs; existing text/v2 and legacy v1 loading remain.
- Added LAN QR capture, camera/album upload, image normalization including HEIF,
  explicit scene review, scale calibration, and target selection.
- Added separate scene/interface/script reports and labelled failure previews.
- The synthetic pen+eraser fixture passes scene physics, 10,000 random steps,
  and 100 seeded resets. Its scripted pickup fails (0/10) and is reported as such.
- Real-photo Codex recognition, Android/iPhone camera capture, interactive
  viewer smoke, and Linux results require the checks in docs/PHOTO_ACCEPTANCE.md.

## Completed

- Added strict TaskSpec v2 validation and bounded Chinese/English parsing.
- Added box, cylinder, sphere, target, and three gesture catalogs.
- Added the generic 23-action ORCA environment with a bounded kinematic wrist.
- Added deterministic generation, path loading, Gym registration, runtime
  checks, scripted feasibility acceptance, interactive viewing, and PNG/MP4
  previews.
- Removed taskgen PPO training/evaluation/acceptance and its dependencies.
- Preserved TaskSpec v1 PinchAndHold loading.
- Added repository and plugin copies of the `orca-env-generator` Skill plus the
  repository marketplace.
- Replaced the README with the text-to-environment workflow.
- Removed assistive object attachment from v2. Manipulation previews now use
  contact-calibrated fingertip motion and free-body MuJoCo dynamics only.

## Acceptance evidence

- Unit/integration tests: see the latest CI run and `pytest` output.
- Canonical bundle reports: `examples/generated/*/validation_report.json`.
- Preview media: `examples/generated/*/preview.png` and `preview.mp4`.
- Plugin/Skill structure is checked with the bundled Codex validators.

No report in v2 is a PPO or learned-policy result.
