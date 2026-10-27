---
name: orca-env-generator
description: Turn tabletop photos into MuJoCo scenes by authoring new object geometry in Blender, including cups, scissors, remotes and irregular containers outside any predefined catalog. Also supports legacy primitive ORCA hand RL tasks on explicit request.
---

# ORCA Environment Generator

Default photo requests produce a Blender-authored MuJoCo scene. Objects are
identified by free names and stable IDs, not by a fixed object-class list.
The agent writes a new Blender modeling script for the actual visible geometry.
Do not route a new object name through the legacy box/cylinder/sphere parser.

For a photo, local image, or request to take a phone photo, read
[references/blender-workflow.md](references/blender-workflow.md). The v0.4.1 default
adds editable local Blender modeling, mandatory user saved-state handoff, and
scene-only MuJoCo export for up to five common rigid objects. Read the capture
instructions in [references/photo-workflow.md](references/photo-workflow.md).
Use the legacy workflow only when the user explicitly requests primitive
approximation or an RL task. A reference to "simulation environment" alone
means the mesh scene and is not a request to fall back to the primitive catalog.
Codex interprets the image; Python has no vision API. Use the current checkout
instructions if an installed v0.3 plugin still claims only six classes.

For text-only requests, continue using the v2 workflow below and its existing
object catalog. Do not invent a source photo for a text request.

## Legacy text/RL scope only

- One ORCA v1 right hand with a bounded kinematic 6DoF wrist.
- Gestures: open/half-close/fist, thumb-index pinch/release, three-finger grasp/release.
- Tasks: `gesture`, `pick_up`, and `pick_place`.
- Objects: box, cylinder, or sphere.

For text/RL tasks, stacking, insertion, tool use, screws, arbitrary meshes, two
hands and robot arms remain unsupported. Blender scene display may model new
rigid shapes, but does not enable those task families. Suggest a supported
primitive task when RL is requested; do not silently approximate it.

## Legacy text/RL workflow only

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

For legacy task dimensions, edit a TaskSpec v2 candidate and validate/generate
it. Do not add new RL task families. This restriction does not prohibit the
agent-authored Blender `model.py` used by the photo scene workflow.
