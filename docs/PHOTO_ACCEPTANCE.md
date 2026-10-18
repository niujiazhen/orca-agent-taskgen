# Photo workflow acceptance (v0.3.0)

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

## Human checks still required

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
session descriptors or private photos. A Codex upload may be forwarded through
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
