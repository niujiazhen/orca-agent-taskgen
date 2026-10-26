# Photo to Blender to MuJoCo (v0.4)

This local authoring workflow inserts an editable Blender project between
photo interpretation and MuJoCo scene generation. It supports agent-authored
models of common rigid objects, including shapes outside the six primitive
photo categories. The first release produces **scene-only** bundles.

```text
Phone upload / attached photo
  -> Agent interpretation and object plan
  -> Agent-authored Blender Python script
  -> Blender project opens for manual inspection
  -> Edit, save, and return to the agent
  -> Export visual meshes, convex collision hulls, and saved transforms
  -> MuJoCo generation, physics check, scene image, collision image, orbit video
```

The agent interprets the photograph and writes the modeling operations.
Neither Blender nor the Python CLI recognizes images independently. Unseen
surfaces and scale remain estimates unless the user supplies measurements.
There is no cloud service, image-to-3D model, or additional vision API.

## Install and check Blender

Install the Python package with the photo and visualization extras, and install
[Blender 4.5 LTS](https://www.blender.org/releases/4-5/) separately. Blender runs
as a subprocess using its own Python; do not install `bpy` into the project venv.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[photo,visualization,dev]"
.\.venv\Scripts\Activate.ps1
orca-task blender doctor
```

The locator checks `ORCA_BLENDER_PATH`, PATH, standard Windows system/user
installation directories, `/usr/bin/blender`, and the standard macOS app path.
Only the 4.5 LTS series is accepted in this release. Override discovery with:

```powershell
$env:ORCA_BLENDER_PATH = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
orca-task blender doctor
```

Each Blender command also accepts `--blender <executable>`; it takes precedence
over the environment variable. Exported scenes need only Python and MuJoCo,
not Blender.

## Use through the agent

Start the existing phone upload workflow, or attach a photo, then say:

```text
Use $orca-env-generator. Build a tabletop scene from this photo through Blender.
Open the Blender project so I can review the models before generating MuJoCo.
```

The agent identifies up to five main rigid objects, discusses unclear shapes
and scale, and prepares a plan and modeling script. It can model rounded
surfaces and visible parts rather than substituting an entire object with a
box. Geometric uncertainty remains explicit.

The build command opens the resulting project automatically. In Blender:

1. Check the source photo reference and the modeled objects.
2. Edit meshes, basic colors, dimensions, positions, and rotations as needed.
3. Keep the registered object roots and IDs. Add mesh parts beneath the
   appropriate root; do not add, delete, or merge object IDs.
4. Keep the tabletop centered and horizontal, and the scene unit scale at 1 m.
5. Save `project.blend` with Ctrl+S, then return to the agent and say:

```text
I have saved my Blender edits. Continue exporting and generate the MuJoCo scene.
```

Only the saved file on disk is read. Closing the window is optional; unsaved
edits are not exported. Editing and saving a scene after export requires a
new export and fresh review. The agent does not infer approval from a
successful export or from a window closing.

## Object plan and modeling script

The versioned object plan is YAML or JSON. `source` is a relative image path
within the plan directory. A minimal example:

```yaml
schema_version: 1
scene_id: custom_rigid_scene
source: source.png
table:
  dimensions: [0.60, 0.50, 0.02]
  top_z: 0.20
  rgba: [0.85, 0.83, 0.78, 1.0]
  friction: [1.2, 0.01, 0.001]
objects:
  - id: item_1
    name: Small rounded container
    dimensions: [0.06, 0.04, 0.03]
    position: [0.0, 0.0, 0.2155]
    quaternion: [1.0, 0.0, 0.0, 0.0]
    rgba: [0.2, 0.5, 0.7, 1.0]
    image_bbox: [0.2, 0.2, 0.8, 0.8]
    details: Rounded edges; dimensions are assumed, not measured.
notes:
  - Hidden geometry, mass, and friction are estimates.
```

Coordinates use metres and Z-up; quaternions use WXYZ. Dimensions are full
local extents, and the position is the object root's world XYZ location.
`image_bbox` uses normalized source coordinates. Plan dimensions are modeling
hints; exported dimensions come from the saved evaluated geometry. A script
can create any common rigid shape and is not dispatched by category.

Optional per-object `mass` and `friction` override the explicit defaults of
0.04 kg and `[1.2, 0.01, 0.001]`. They are authoring assumptions, not inferred
physical measurements. The pen in the five-object example also uses this
mesh-workflow default mass.

The script must define `build(ctx)`:

```python
import bpy

def build(ctx):
    bpy.ops.mesh.primitive_cube_add(size=1)
    part = bpy.context.object
    part.name = "Rounded container"
    part.dimensions = (0.06, 0.04, 0.03)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = part.modifiers.new("Editable round edges", "BEVEL")
    bevel.width, bevel.segments = 0.005, 4
    ctx.add_part("item_1", part, (0.2, 0.5, 0.7, 1.0))
```

`ctx.objects[id]` is the pre-created rigid-object root. Author mesh parts in
that root's local coordinate frame, and register them with
`ctx.add_part(id, mesh_object, rgba)`. Multiple parts belong to one physical
body. Use `ctx.plan` for modeling dimensions or other authoring hints.
Scripts run as local Python in Blender; use agent-authored or reviewed scripts.

## Build, review, export, and simulate

Run these commands at the repository root with the venv active:

```powershell
orca-task blender build examples/blender/five_objects/object_plan.yaml --script examples/blender/five_objects/model.py --output blender_workspaces/my_five_objects
# Blender opens automatically. Review, edit and save before continuing.
orca-task blender export blender_workspaces/my_five_objects
orca-task scene generate blender_workspaces/my_five_objects/export/scene_spec.yaml --output generated_scenes
orca-task scene check generated_scenes/blender_five_objects
orca-task scene preview generated_scenes/blender_five_objects
orca-task scene view generated_scenes/blender_five_objects
```

Use `orca-task blender open <workspace>` to reopen a project. `build --no-open`
is available for automated tests and reproducible reference generation; it
does not record manual review. A successful build refuses to overwrite an
existing project; edit that project or choose a fresh workspace.

The workspace preserves `model.py`, `object_plan.json`, `source.png`,
`project.blend`, the Blender preview, attempt logs, and export reports.
`export/scene_spec.yaml` is a SceneSpec v2 and references relative mesh and
authoring assets. Generation copies those assets into the final scene bundle,
including the editable `.blend` snapshot and the saved-state Blender preview.

To run an exported bundle without Blender:

```python
from orca_sim.taskgen import load_scene

scene = load_scene("generated_scenes/blender_five_objects")
try:
    scene.step(500)
    image = scene.render()
    collision_image = scene.render(collision=True)
finally:
    scene.close()
```

## What survives the round trip

Evaluated geometry includes mesh edits and modifiers. Scale, parent transforms,
and mirrored edits are baked into object-local mesh vertices; the saved rigid
root position and orientation are preserved in MuJoCo. Basic material colors
are exported by part/material and declared explicitly in MJCF. No scale or
axis conversion is applied twice.

The exporter accepts opaque base colors, including a constant Principled BSDF
Base Color. It rejects linked color textures and transparency. Complex shader
effects, logos, labels, and image projections are outside this version.

One convex hull per object handles collisions and contributes the configured
mass and inertia. All visual parts have zero mass and disabled collisions.
Holes and concavities may be filled by the hull. Inspect
`collision_preview.png` alongside `scene_preview.png`; do not infer accurate
handle-interior or cup-interior contact from the visual surface.

## Validation and failure behavior

- Each object must have a unique registered root and at least one mesh part.
  Unregistered meshes, missing roots, and duplicated IDs name the offending
  objects and block export. Convert curves/text into mesh parts before export.
- Each object's cleaned visual mesh may contain at most 20,000 triangles.
  Exceeding the budget requests explicit simplification; it does not decimate
  silently. Degenerate zero-area tessellation faces are discarded during export.
- Missing, modified, or escaping asset paths block loading. SHA-256 records
  bind source, meshes, project, script, and saved-state preview to the reviewed
  specification. Editing an asset invalidates the previous confirmation.
- Initial intersections, floating objects, and objects beyond the tabletop
  block scene generation. Saved positions are not snapped or shifted.
- The existing 2,000-step check verifies finite dynamics, tabletop support,
  drift, and penetration. Physics validation and user confirmation stay separate.
- A failed export withdraws the consumable `scene_spec.yaml`; previous/failed
  snapshots and logs are retained. Fix the saved project and export again.
- A workspace permits at most three failed modeling attempts: the original
  attempt and two agent repairs. Keep the evidence and ask for guidance after
  the third failure. Blender subprocesses time out after 180 seconds.

## Compatibility and examples

SceneSpec v1 and existing text/photo RL tasks remain supported. New SceneSpec
v2 mesh scenes are rejected by `task create` with a scene-display-only message.
Opening a scene successfully does not imply an RL interface or grasp success.

- [Five-object real-phone demo](../examples/blender/five_objects/README.md)
- [Synthetic hollow-cup/handle demo](../examples/blender/handle_object/README.md)
- [Original primitive photo workflow](PHONE_PHOTO_TUTORIAL.md)

Run `python -m pytest -q` for compatibility, asset integrity, and transform tests.
Real Blender integration tests run when 4.5 LTS is detected and otherwise skip
explicitly; portable mesh-bundle tests do not require Blender. Window review
remains a human check and is not claimed by headless tests.
