---
name: orca-env-generator
description: Generate ORCA MuJoCo scenes and Gymnasium environments from task descriptions or tabletop photos. Use for phone capture, editable Blender modeling and review, mesh scene display, gestures, pickup, and placement of supported primitive objects.
---

# ORCA Environment Generator

Turn the user's natural-language request into a generated MuJoCo task bundle. The deliverable is an untrained RL environment, not a policy or a PPO result.

For a photo, local image, or request to take a phone photo, read
[references/blender-workflow.md](references/blender-workflow.md). The v0.4 default
adds editable local Blender modeling, mandatory user saved-state handoff, and
scene-only MuJoCo export for up to five common rigid objects. Read the capture
instructions in [references/photo-workflow.md](references/photo-workflow.md).
If the user requests primitive objects or a photo-derived RL task, use that
legacy workflow instead. Codex interprets the image; Python has no vision API.

For text-only requests, continue using the v2 workflow below and its existing
object catalog. Do not invent a source photo for a text request.

## Supported scope

- One ORCA v1 right hand with a bounded kinematic 6DoF wrist.
- Gestures: open/half-close/fist, thumb-index pinch/release, three-finger grasp/release.
- Tasks: `gesture`, `pick_up`, and `pick_place`.
- Objects: box, cylinder, or sphere.

For text/RL tasks, stacking, insertion, tool use, screws, arbitrary meshes, two
hands and robot arms remain unsupported. Blender scene display may model new
rigid shapes, but does not enable those task families. Suggest a supported
primitive task when RL is requested; do not silently approximate it.

## Workflow

1. Summarize the parsed task in one sentence. Use safe defaults for omitted color, size, mass, friction, reset jitter, reward weights, and success thresholds.
2. Ask only when an ambiguity changes the task family, object shape, or target relation.
3. Ensure the package is available:
   - In a cloned repository, install the current checkout with `python -m pip install -e ".[visualization]"`.
   - From the installed plugin, if `orca-task` is unavailable, install the matching public repository release with `python -m pip install "orca_sim[visualization] @ git+https://github.com/niujiazhen/orca-agent-taskgen.git@main"`.
4. Generate into the current workspace:
   `orca-task generate-text "<request>" --output generated_tasks`
5. Read the JSON result to obtain the exact task directory. Run:
   - `orca-task check <task-directory>`
   - `orca-task preview <task-directory>`
6. If any command fails, report the failing gate and preserve the bundle for inspection. Never claim that a failed or pending bundle is ready.
7. Report the task directory, environment ID, validation status, preview files, and this minimum usage:

```python
from orca_sim.taskgen import load_environment
env = load_environment("<task-directory>", render_mode="human")
observation, info = env.reset(seed=0)
```

For custom dimensions or positions beyond the bounded parser's defaults, edit a TaskSpec v2 candidate, validate it with `orca-task validate`, then generate it with `orca-task generate`. Do not add new task families or arbitrary Python code to a generated bundle.
