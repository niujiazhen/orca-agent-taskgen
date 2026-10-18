"""Turn a confirmed photo scene into an RL bundle, with separate check gates."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
import yaml

from orca_sim.taskgen.contracts import ContractError, load_task_spec
from orca_sim.taskgen.photo_contracts import content_hash, runtime_task_v3, validate_task_v3
from orca_sim.taskgen.photo_scene import PhotoScene, check_scene, compile_scene, write_json
from orca_sim.versions import PACKAGE_ROOT


OBSERVATION_FIELDS = [
    {"name": "wrist_pose", "offset": 0, "size": 7},
    {"name": "joint_positions", "offset": 7, "size": 17},
    {"name": "joint_velocities", "offset": 24, "size": 17},
    {"name": "tip_offsets_from_target", "offset": 41, "size": 9},
    {"name": "target_fingertip_contacts", "offset": 50, "size": 3},
    {"name": "objects[5]: position3,quaternion4,velocity6,valid,target", "offset": 53, "size": 75},
    {"name": "target_position", "offset": 128, "size": 3},
    {"name": "task_phase: approaching,contact,release", "offset": 131, "size": 3},
    {"name": "episode_progress", "offset": 134, "size": 1},
]


def create_photo_task(scene_directory, *, output, family, object_id, target_xy=None, env_id=None,
                      hold_steps=20, source_text=None) -> Path:
    scene_directory = Path(scene_directory).resolve()
    scene = PhotoScene(scene_directory)
    spec = scene.spec
    scene.close()
    if not spec["confirmed"] or spec["questions"]:
        raise ContractError("Scene must be confirmed before creating a task")
    report = check_scene(scene_directory)
    if report["physics"] != "pass":
        raise ContractError(f"Scene physics check failed: {report.get('reason')}")
    if env_id is None:
        label = "".join(word.title() for word in f"{spec['scene_id']}_{object_id}_{family}".split("_"))
        env_id = label[:76]+"-v0"
    task_spec = validate_task_v3({"schema_version": 3, "scene_spec": spec, "task": {
        "env_id": env_id, "source_text": source_text or f"{family} {object_id} in reviewed photo scene",
        "family": family, "object_id": object_id, "target_xy": list(target_xy) if target_xy is not None else None,
        "hold_steps": hold_steps, "lift_height": .05, "target_radius": .03,
        "max_object_speed": .05, "max_episode_steps": 1000}})
    return _write_task(task_spec, output, scene_directory)


def generate_photo_task(spec_path, *, output):
    spec_path = Path(spec_path).resolve()
    return _write_task(load_task_spec(spec_path, allowed_root=spec_path.parent), output, spec_path.parent)


def _write_task(spec: dict, output, source_dir: Path) -> Path:
    spec = validate_task_v3(spec)
    scene = spec["scene_spec"]
    image = (source_dir/scene["source"]["image"]).resolve()
    if source_dir not in image.parents or not image.is_file():
        raise ContractError("Photo task requires its relative source image beside the specification")
    import hashlib
    if hashlib.sha256(image.read_bytes()).hexdigest() != scene["source"]["sha256"]:
        raise ContractError("Source photo hash mismatch")
    slug = spec["task"]["env_id"].replace("-", "_").lower()
    bundle = Path(output).resolve()/slug
    bundle.mkdir(parents=True, exist_ok=True)
    from orca_sim.taskgen.photo_upload import normalize_image
    receipt = normalize_image(image.read_bytes(), bundle/"source.png")
    scene["source"] = {key: receipt[key] for key in ("image", "sha256")}
    hand_files = _bundle_hand(bundle, spec)
    xml = compile_scene(scene, hand_include="hand.xml", target_id=spec["task"]["object_id"], target_xy=spec["task"]["target_xy"])
    (bundle/"scene.xml").write_text(xml, encoding="utf-8")
    (bundle/"task_spec.yaml").write_text(yaml.safe_dump(spec, sort_keys=True, allow_unicode=True), encoding="utf-8")
    (bundle/"scene_spec.yaml").write_text(yaml.safe_dump(scene, sort_keys=True, allow_unicode=True), encoding="utf-8")
    (bundle/"request.txt").write_text(spec["task"]["source_text"]+"\n", encoding="utf-8")
    (bundle/"README.md").write_text(
        f"# {spec['task']['env_id']}\n\nPhoto-derived approximate scene; target `{spec['task']['object_id']}`.\n\n"
        "Load with `from orca_sim.taskgen import load_environment` then "
        "`env = load_environment(\".\", render_mode=\"human\")`.\n\n"
        "Scene, RL interface, and scripted feasibility are separate gates in validation_report.json.\n"
        "task_preview.mp4 is a non-learning attempt, labelled success or failure.\n", encoding="utf-8")
    warnings = []
    obj = next(o for o in scene["objects"] if o["id"] == spec["task"]["object_id"])
    if obj["category"] == "book" or max(obj["dimensions"]) > .18:
        warnings.append("Object may exceed the single hand's grasp span; geometry was preserved. Script success is not guaranteed.")
    write_json(bundle/"manifest.json", {"manifest_version": 3, "schema_version": 3, "env_id": spec["task"]["env_id"],
        "family": spec["task"]["family"], "scene_id": scene["scene_id"], "scene_sha256": content_hash(scene),
        "spec_sha256": content_hash(spec), "requires": {"orca_sim": "==0.3.0", "mujoco": ">=3.1"},
        "object_order": [o["id"] for o in scene["objects"]], "target_object_id": spec["task"]["object_id"],
        "action_shape": [23], "action_fields": ["wrist_translation_delta[3]", "wrist_rotation_delta[3]", "hand_targets[17]"],
        "observation_shape": [135], "observation_fields": OBSERVATION_FIELDS, "warnings": warnings,
        "object_dynamics": "free_body_contact_only", "hand_table_collision": True, "validation": "pending",
        "files": ["source.png", "scene_spec.yaml", "task_spec.yaml", "scene.xml", "manifest.json", "validation_report.json", "README.md", "request.txt", *hand_files]})
    write_json(bundle/"validation_report.json", {"scene": "pending", "rl_interface": "pending", "scripted_feasibility": "pending"})
    return bundle


def _bundle_hand(bundle: Path, spec: dict) -> list[str]:
    """Keep photo task MJCF portable and valid even before Python reset()."""
    source = PACKAGE_ROOT/"models/v1/right.mjcf"
    root = ET.parse(source).getroot()
    paths = ["hand.xml"]
    for mesh in root.findall("./asset/mesh"):
        original = (source.parent/mesh.attrib["file"]).resolve()
        relative = Path("assets")/"right"/original.name
        destination = bundle/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        mesh.set("file", relative.as_posix())
        paths.append(relative.as_posix())
    tower = root.find(".//body[@name='right_tower']")
    hand = runtime_task_v3(spec)["hand"]
    from orca_sim.taskgen.photo_scene import numbers
    tower.attrib.pop("euler", None)
    tower.set("pos", numbers(hand["initial_position"]))
    tower.set("quat", numbers(hand["initial_quaternion"]))
    for geom in tower.findall("geom"):
        geom.set("rgba", "1 1 1 0")
        geom.set("contype", "0")
        geom.set("conaffinity", "0")
    ET.indent(root, space="  ")
    (bundle/"hand.xml").write_text(ET.tostring(root, encoding="unicode")+"\n", encoding="utf-8")
    return paths


def _scene_gate(spec: dict):
    # Recompile a scene-only model; never let the hand mask a support problem.
    from orca_sim.taskgen.photo_scene import inspect_scene_physics
    model = mujoco.MjModel.from_xml_string(compile_scene(spec))
    data = mujoco.MjData(model)
    return {"status": "pass", "confirmation": "confirmed", **inspect_scene_physics(model, data, spec)}


def check_photo_task(bundle, *, episodes=10, stress_steps=10_000, reset_count=100):
    from orca_sim.taskgen import load_environment
    from orca_sim.taskgen.acceptance_v2 import _evaluate, validate_seeded_resets
    from orca_sim.taskgen.validator import validate_runtime
    bundle = Path(bundle)
    if episodes < 1 or stress_steps < 1 or reset_count < 1:
        raise ValueError("Check counts must be positive")
    report = {"report_version": 3, "validation_kind": "scene and RL-interface checks; independent non-learning script attempt"}
    spec = load_task_spec(bundle/"task_spec.yaml", allowed_root=bundle)
    try:
        report["scene"] = _scene_gate(spec["scene_spec"])
    except (ValueError, RuntimeError) as exc:
        report["scene"] = {"status": "fail", "reason": str(exc)}
    try:
        report["rl_interface"] = {"status": "pass", "runtime": validate_runtime(bundle, steps=stress_steps),
                                  "resets": validate_seeded_resets(bundle, count=reset_count)}
    except (ValueError, RuntimeError, AssertionError) as exc:
        report["rl_interface"] = {"status": "fail", "reason": str(exc)}
    try:
        scripted = _evaluate(bundle, "scripted", episodes, 0.)
        zero = _evaluate(bundle, "zero", episodes, 0.)
        random = _evaluate(bundle, "random", episodes, 0.)
        report["scripted_feasibility"] = {"status": "pass" if scripted["success_rate"] >= .9 else "fail", **scripted}
        if scripted["success_rate"] < .9:
            report["scripted_feasibility"]["reason"] = "Contact controller did not complete the task reliably; object geometry and layout were not modified"
        report["baselines"] = {"zero": zero, "random": random}
        if zero["success_rate"] != 0 or random["success_rate"] > .05:
            report["rl_interface"] = {"status": "fail", "reason": "False-success baseline failed", "details": report["rl_interface"]}
    except (ValueError, RuntimeError, AssertionError) as exc:
        report["scripted_feasibility"] = {"status": "fail", "reason": str(exc)}
    report["status"] = "pass" if all(report[k]["status"] == "pass" for k in ("scene", "rl_interface")) else "fail"
    report["script_is_trained_policy"] = False
    write_json(bundle/"validation_report.json", report)
    manifest = json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
    manifest["validation"] = report["status"]
    manifest["scripted_feasibility"] = report["scripted_feasibility"]["status"]
    write_json(bundle/"manifest.json", manifest)
    return report


def preview_photo_task(bundle, *, max_steps=None):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    from orca_sim.taskgen import load_environment
    bundle = Path(bundle)
    env = load_environment(bundle)
    renderer = mujoco.Renderer(env.model, height=480, width=640)
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(env.model, camera)
    camera.lookat[:] = [0, 0, env.photo_scene["table"]["top_z"]+.1]
    camera.distance, camera.azimuth, camera.elevation = .85, 120, -35
    frames = []
    reason = "episode limit reached"
    info = {}
    try:
        env.reset(seed=0)
        for _ in range(max_steps or env.max_episode_steps):
            _, _, terminated, truncated, info = env.step(env.scripted_action())
            renderer.update_scene(env.data, camera=camera)
            frames.append(renderer.render().copy())
            if terminated or truncated:
                reason = "success" if info["is_success"] else "persistent hand/table penetration" if info.get("physics_invalid") else "object dropped or episode ended"
                break
    finally:
        renderer.close()
        env.close()
    success = bool(info.get("is_success"))
    label = "SCRIPT SUCCESS" if success else "SCRIPT FAILED - "+reason
    with imageio.get_writer(bundle/"task_preview.mp4", fps=30, macro_block_size=1) as writer:
        for index, frame in enumerate(frames):
            image = Image.fromarray(frame)
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 640, 25), fill="black")
            draw.text((8, 7), "NON-LEARNING ATTEMPT | "+label, fill="white")
            if index == len(frames)//2:
                image.save(bundle/"task_preview.png")
            writer.append_data(np.asarray(image))
    result = {"kind": "non-learning contact attempt", "scripted_success": success, "reason": reason,
              "frames": len(frames), "video": "task_preview.mp4", "image": "task_preview.png"}
    write_json(bundle/"preview_report.json", result)
    manifest = json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
    manifest["preview"] = result
    manifest["files"] = sorted(set(manifest["files"]) | {"task_preview.mp4", "task_preview.png", "preview_report.json"})
    write_json(bundle/"manifest.json", manifest)
    return result
