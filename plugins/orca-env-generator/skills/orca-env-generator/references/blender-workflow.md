# Photo -> editable Blender project -> mesh-only MuJoCo scene (v0.4)

Use this workflow by default for new tabletop photos, unless the user requests
the legacy primitive/RL workflow. Interpret the actual image yourself. Blender
does not recognize images, and no external image-to-3D service is called.

## Identify and author

1. Follow the capture/normalization instructions in `photo-workflow.md`, then
   inspect the uploaded image. Identify up to five main rigid objects and the
   support surface. Ask about occlusion, ambiguous shape, omitted edge objects,
   or a selection beyond five. Do not silently replace unknown shapes.
2. Explain single-view uncertainty and any assumed dimensions, mass or friction.
   Use provided measurements when available. Common rigid shapes outside the
   six legacy categories are allowed; soft bodies, articulated mechanisms and
   image-perfect reconstruction are not promised.
3. Run `orca-task blender doctor`; install Blender 4.5 LTS when necessary.
   Configure `ORCA_BLENDER_PATH` or `--blender` if not discovered. Install the
   package with `.[photo,visualization]`; require orca_sim >=0.4.0.
4. Write an object plan and an agent-authored `model.py` in the workspace. The
   plan records source image, stable object IDs/names, dimension estimates,
   world XYZ positions, WXYZ rotations, colors, image boxes and uncertainty.
   Read `schemas/blender_object_plan.schema.json` from the installed package
   for its complete contract. Source paths must be relative within the plan
   directory. Optional object mass/friction are explicit assumptions.
5. The script defines `build(ctx)` using Blender's `bpy`. `ctx.objects[id]`
   contains one pre-created root per rigid object. Create local mesh parts
   and attach them with `ctx.add_part(id, mesh_object, rgba)`. Read dimensions
   from `ctx.plan`. Multiple parts share one root and one collision hull.
   Basic opaque colors only; no photo texture or linked color shader inputs.

## Build and pause for Blender review

```text
orca-task blender build <object-plan.yaml> --script <model.py> --output <workspace>
```

Build opens Blender automatically. Show the Blender preview and project path.
Ask the user to inspect/edit geometry, size, position, rotation and base colors,
save `project.blend`, then return and say "Continue with my saved Blender edits."
Do not proceed with the user's final scene export before this saved-state
handoff. Headless `--no-open` is only for tests/demo snapshots and never records
human approval. `orca-task blender open <workspace>` reopens the UI.

Keep object roots and IDs. New parts must belong under their matching root;
deleting/duplicating IDs or adding unregistered geometry blocks export. The
table remains a centered, horizontal slab; scene units stay at 1 m. A saved
edit may include nonuniform scale or mirroring; export bakes it into meshes.

If a modeling script fails, inspect the preserved log, repair the actual script,
and retry no more than twice in the same workspace. After three failed attempts,
retain all evidence and ask for guidance. Do not bypass the cap by switching
workspace names. A completed build must not overwrite user edits.

## Export, generate and validate

After the user's saved-state handoff:

```text
orca-task blender export <workspace>
orca-task scene generate <workspace>/export/scene_spec.yaml --output generated_scenes
orca-task scene check <returned-scene-directory>
orca-task scene preview <returned-scene-directory>
```

The exporter reads saved disk state, applies modifiers, preserves final shape,
color and full rigid transform, and produces triangulated visual OBJ parts
plus one convex hull per object. Visuals have no mass/collisions; hulls provide
physical mass and contact. The maximum is 20,000 visual triangles per object.
Do not silently decimate, move, resize or snap objects to make checks pass.

Report script/export and physics failures truthfully. Unstable/unsupported or
initially overlapping objects require user-directed correction and re-export.
Mesh/provenance hashes bind the exact saved asset snapshot to confirmation.
After an asset change, regenerate and obtain a new review.

Show the source photo, object annotation, saved-state Blender preview, MuJoCo
scene, collision preview and orbit MP4. Explain that convex hulls can fill cup
openings, handle holes and other concavities. Show uncertainty and the physics
gate separately from user visual approval. Use the existing scene confirmation
command only after explicit approval of the displayed current asset snapshot.

These mesh bundles are scene display only. Do not call `task create`, claim
grasp readiness or launch RL training. Use `load_scene(<bundle>)` for rendering
and physics inspection. Existing primitive SceneSpec v1 tasks remain available
through `photo-workflow.md` when the user chooses that workflow.
