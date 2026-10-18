"""Render a synthetic reference and exercise photo-scene/task generation.

No real-photo recognition or mobile-device acceptance is claimed by this test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
import yaml

from orca_sim.taskgen import load_scene
from orca_sim.taskgen.photo_scene import draft_scene, generate_scene, check_scene, preview_scene
from orca_sim.taskgen.photo_task import create_photo_task, check_photo_task, preview_photo_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/photo-smoke"))
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="orca-photo-fixture-"))
    bootstrap = scratch/"bootstrap.png"
    Image.new("RGB", (640, 480), "white").save(bootstrap)
    path = draft_scene(bootstrap, output=scratch/"draft", scene_id="desk_pen", categories=["pen", "eraser"])
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec["objects"][0]["xy"] = [-.02, -.05]
    spec["objects"][1]["xy"] = [.07, .07]
    spec["objects"][1]["rgba"] = [.85, .35, .35, 1]
    spec["notes"] = ["Synthetic MuJoCo reference; authored fixture, not real-photo recognition.",
                       "Known synthetic layout; confirmation is a test fixture flag."]
    spec["questions"] = []
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    bundle = generate_scene(path, output=root/"scenes")
    scene = load_scene(bundle)
    try:
        scene.step(500)
        frame = scene.render()
        Image.fromarray(frame).save(path.parent/"source.png")
        cam = scene._renderer.scene.camera[0]
        forward, up = np.asarray(cam.forward, float), np.asarray(cam.up, float)
        right = np.cross(forward, up)
        tan_fov = np.tan(np.deg2rad(scene.model.vis.global_.fovy)/2)
        for obj in spec["objects"]:
            body = scene.model.body("scene_"+obj["id"]).id
            geom = int(scene.model.body_geomadr[body])
            local = scene.model.geom_aabb[geom]
            corners = np.asarray([[sx,sy,sz] for sx in [-1,1] for sy in [-1,1] for sz in [-1,1]])*local[3:]+local[:3]
            corners = corners@scene.data.geom_xmat[geom].reshape(3,3).T+scene.data.geom_xpos[geom]
            delta = corners-np.asarray(cam.pos)
            depth = delta@forward
            x = .5+(delta@right)/(depth*tan_fov*(640/480)*2)
            y = .5-(delta@up)/(depth*tan_fov*2)
            obj["image_bbox"] = np.clip([x.min()-.01,y.min()-.01,x.max()+.01,y.max()+.01],0,1).tolist()
    finally:
        scene.close()
    spec["source"]["sha256"] = hashlib.sha256((path.parent/"source.png").read_bytes()).hexdigest()
    spec["confirmed"] = True
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    bundle = generate_scene(path, output=root/"scenes")
    scene_report = check_scene(bundle)
    preview_scene(bundle)
    task = create_photo_task(bundle, output=root/"tasks", family="pick_up", object_id="pen_1", env_id="PhotoPenPickup-v0")
    report = check_photo_task(task, episodes=10 if args.full else 1,
        stress_steps=10_000 if args.full else 200, reset_count=100 if args.full else 5)
    preview_photo_task(task)
    print(json.dumps({"scene": str(bundle), "task": str(task), "scene_status": scene_report["status"],
                      "task_status": report["status"], "scripted": report["scripted_feasibility"]["status"]}, indent=2))
    if scene_report["status"] != "pass" or report["status"] != "pass":
        raise SystemExit("Photo smoke mandatory gates failed; inspect reports")


if __name__ == "__main__":
    main()
