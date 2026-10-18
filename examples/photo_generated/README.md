# Photo workflow examples

## Real phone photograph: five objects

The [five-object demo](scenes/phone_five_objects/README.md) shows the complete
sequence from an actual phone photograph to annotations, a MuJoCo scene, and
a rotating preview video. It includes a pen, soda can, earbud case, tablet
cover, and gum container, with user-approved geometric proxies and one
explicitly approved placement correction.

[Source](scenes/phone_five_objects/source.png) ->
[Annotations](scenes/phone_five_objects/annotated.png) ->
[Scene](scenes/phone_five_objects/scene_preview.png) ->
[Orbit video](scenes/phone_five_objects/scene_preview.mp4)

All five objects pass the physics check. The final scene awaits visual
confirmation; this example contains no RL task or training result.
Follow the [phone photo tutorial](../../docs/PHONE_PHOTO_TUTORIAL.md) to use
your own image.

## Synthetic photo pipeline fixture

The `scenes/desk_pen/source.png` image is a reference rendered locally with MuJoCo. These files exercise
photo-scene packaging and RL integration; they do not demonstrate real-photo
recognition. No private user photo or third-party image was used.

- Scene: [pen and eraser](scenes/desk_pen/scene_preview.png)
- Scene [report](scenes/desk_pen/scene_report.json) and [orbit](scenes/desk_pen/scene_preview.mp4)
- RL [report](tasks/photopenpickup_v0/validation_report.json)
- Scripted [attempt](tasks/photopenpickup_v0/task_preview.mp4): **failed**, 0/10.

Scene and interface gates pass, including 10,000 random steps and 100 resets.
The scripted controller did not grasp this thin pen. Geometry was preserved;
no success claim or learned-policy result is made.

Regenerate with `python scripts/photo_smoke.py --output examples/photo_generated --full`.
