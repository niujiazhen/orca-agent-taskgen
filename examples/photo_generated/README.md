# Synthetic photo pipeline fixture

`source.png` is a reference rendered locally with MuJoCo. These files exercise
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
