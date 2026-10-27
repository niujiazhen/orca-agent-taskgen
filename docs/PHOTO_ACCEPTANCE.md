# Photo workflow acceptance (v0.3.0)

## Background Blender intermediate (v0.4.2)

The default CLI and Python build API run Blender in the background, save
`project.blend` plus the preview, script and object plan, and return
`ready_for_export` with `ui_opened: false`. Agent instructions continue into
MuJoCo export/generation without a manual-editing pause. `--open` and the
separate `blender open` command are opt-in; `--no-open` remains compatible.

The live Blender integration test verifies that the default path creates the
`.blend` intermediate and preview without invoking the UI launcher, then exports
and loads a MuJoCo scene. Its opt-in UI behavior is checked with a mocked
launcher, so the automated suite does not open local Blender windows. CLI tests
cover default, explicit background and explicit UI flags. The `.blend` snapshot
is copied into the final portable bundle and bound by its asset hash.

The earlier sections below describe the historical review-first release.
Human approval remains a separate status; background generation does not mark
models as visually confirmed or claim that a user inspected them.

## Open-ended Blender object types (v0.4.1)

The [desktop objects fixture](../examples/blender/desktop_objects/README.md)
models keyboard, black shaker cup, mouse, speaker and pen geometry; the
[open objects fixture](../examples/blender/open_objects/README.md) models cup,
scissors, remote, asymmetric container and hex nut geometry. Both use synthetic
Blender reference images and retain pending human review. They verify shape
authoring and mesh import, not reconstruction from a newly supplied photo.
Each scene passes its 2,000-step physics gate.

Tests verify that every retained object has a named manifest entry, an audited
set of Blender parts, a collision hull, and visual MuJoCo mesh geoms. A live
Blender test authors the custom shapes without registering object classes. The
keyboard's 105 editable parts are exported as three color-batched visual meshes.
The wheel smoke check exercises both relocated fixtures without calling Blender.

The runtime doctor identifies the package version and open Blender mesh route.
The agent entry documents explicitly distinguish that route from the older
six-category primitive workflow and explain how to refresh an old installed
plugin cache. The scene count limit remains five; this change expands object
types rather than the number of objects or the supported RL task families.

## Blender mesh authoring (v0.4.0)

The [Blender workflow](BLENDER_WORKFLOW.md) adds local agent-authored geometry,
an interactive saved-state handoff, and SceneSpec v2 mesh-only display. The
[five-object real-photo demo](../examples/blender/five_objects/README.md) and
[synthetic cup/handle example](../examples/blender/handle_object/README.md)
both pass their 2,000-step scene physics checks. Their checked-in Blender
snapshots were generated headlessly; human window review and final visual
confirmation are explicitly pending.

Tests use Blender 4.5 LTS when installed to build an editable object, modify its
mesh, material color, world pose and nonuniform scale, save, and compare the
exported and MuJoCo world vertices with the saved Blender geometry. Export
rejects missing/duplicate object IDs, unregistered meshes and visual triangle
budgets above 20,000. A failed export withdraws its consumable specification;
three failed build attempts preserve logs and block further automatic repair.

Additional tests cover portable loading without Blender, asset/project/model
hash invalidation, zero-mass noncolliding visual parts, collision-only mass,
initial floating/overlapping object rejection, and explicit RL-task rejection.
An isolated wheel smoke check loads, steps and renders the relocated mesh demo.
See `tests/test_blender_pipeline.py` for executable checks. Headless tests do not
establish that a human inspected the Blender window or approved the result.

## Automated gates

Local Windows evidence: 99 tests pass; an isolated wheel installation generates,
loads, and renders text and photo bundles. The portable Plugin manifest passes
the published Agent Plugins JSON Schema, and Skill validation/synchronization pass.
MuJoCo is pinned to 3.13.0: a fresh installation of 3.16.0 failed two existing
v2 placement-controller regressions. Unverified solver versions are not claimed
to preserve the scripted contact benchmarks.

Run `python -m pip install -e ".[photo,visualization,dev]"`, then `python -m pytest`.
Tests cover image decoding (including HEIF), EXIF orientation, upload limits,
token authentication, file isolation, duplicate uploads, all six rigid assets,
layout/shape contracts, calibration, confirmation, five-slot observations,
seeded reset, rendering and video decoding, and independent validation gates.
CI runs Windows/Linux and Python 3.10/3.12; wheel smoke exercises installed code.
Linux runners install `libosmesa6` and `libgl1` and set `MUJOCO_GL=osmesa` and
`PYOPENGL_PLATFORM=osmesa` for CPU rendering without a GPU or display. The old
EGL-only setup failed at import because the runner had no EGL implementation.
Windows CI installs Mesa software OpenGL for GPU-less runners. Text/v2 generation
also handles assets on another Windows drive, and relative Unix includes containing
`home` are distinguished from absolute development-machine paths.

`python scripts/photo_smoke.py --output build/photo-smoke --full` creates a
synthetic tabletop reference and a pen/eraser scene, runs 10,000 random control
steps, checks 100 seeded resets, tests scripted/zero/random actions, and renders
both preview types. The reference is rendered locally, not a real photograph.
It tests engineering integration, not Codex image recognition accuracy.

## Real-photo demo evidence

The [five-object phone demo](../examples/photo_generated/scenes/phone_five_objects/README.md)
records a user-supplied photograph uploaded through the LAN capture page on
2026-10-18 (America/Los_Angeles). The upload receipt was 3024 x 4032 pixels.
Codex inspected the actual photograph, identified five main objects, asked
about box approximations and partial border objects, and generated the scene.
The user approved the proxies, border omissions, and a 3 cm pen displacement
after the initial layout failed its nonintersection check.

The final scene passes 2,000 physics steps with all five objects supported,
less than 0.54 mm position drift per object, and approximately 0.031 mm maximum
penetration. Source, annotations, scene model/specification, physics report,
rendered view, and orbit video are published with the user's authorization.
The final scene retains its pending visual-confirmation status. It is not a
grasp or RL demonstration, and its scale uses an assumed 14 cm pen.

The phone model and browser were not recorded, so this session does not
establish the platform-specific camera/HEIC checks below. It did expose two
operational issues documented in the [tutorial](PHONE_PHOTO_TUTORIAL.md):
VPN routing can prevent access to the Wi-Fi address, and each capture session
accepts only one photograph.

## Additional human checks still required

No automated test or synthetic fixture establishes these results. Record the
actual device, browser, photo provenance, result, and date when performed:

- [ ] Android Chrome: scan LAN QR, take photo, upload, continue in Codex.
- [ ] iPhone Safari: camera, album upload, portrait orientation, HEIC upload.
- [ ] Desktop Codex: read an attached actual photograph of a horizontal pen.
- [ ] Actual pen+eraser photo: count, orientation, rough layout, target selection.
- [ ] Known-length correction: visibly rescale and obtain fresh confirmation.
- [ ] Unknown or occluded object: ask, without silent substitution or omission.
- [ ] More than five objects: ask which to retain.
- [ ] Book: preserve scale and disclose grasp-span limitations.
- [ ] Interactive scene and task viewer: open and close on Windows/Linux.

Real-photo fixtures must have permission for publication. Do not commit capture
session descriptors or photos without publication permission. A Codex upload may be forwarded through
the user's normal Codex image workflow; this package has no separate vision API.

## Interpretation of results

Dimensions and XY locations are approximate unless the user supplies a scale
reference. Geometry uses rigid proxies; pen clips and book covers are visual
details. No camera calibration, image-to-mesh reconstruction, writing, paper
deformation, or real robot-arm dynamics are claimed.

Scene acceptance requires explicit user confirmation plus stable physics;
RL-interface acceptance requires valid reset/step and no persistent hand-table
penetration over 2 mm. The scripted result remains separate, and a failed
attempt is labelled in task_preview.mp4. No preview is an RL training result.
