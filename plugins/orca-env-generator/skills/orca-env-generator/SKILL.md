---
name: orca-env-generator
description: Generate validated, visualizable ORCA v1 right-hand MuJoCo/Gymnasium RL environments from Chinese or English task descriptions. Use for hand gestures, picking up a box/cylinder/sphere, or placing one of those objects in a target region; reject tool use, insertion, stacking, external meshes, and two-hand requests.
---

# ORCA Environment Generator

Turn the user's natural-language request into a generated MuJoCo task bundle. The deliverable is an untrained RL environment, not a policy or a PPO result.

## Supported scope

- One ORCA v1 right hand with a bounded kinematic 6DoF wrist.
- Gestures: open/half-close/fist, thumb-index pinch/release, three-finger grasp/release.
- Tasks: `gesture`, `pick_up`, and `pick_place`.
- Objects: box, cylinder, or sphere.

If the request needs stacking, insertion, tools, screws, an external mesh, two hands, or a robot arm, stop and explain that v2 does not support it. Suggest a supported primitive task; do not silently approximate it.

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
