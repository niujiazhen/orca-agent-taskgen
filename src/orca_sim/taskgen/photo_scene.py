"""Deterministic photo-scene compilation, physical checks, and viewing."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
import yaml

from orca_sim.taskgen.contracts import ContractError
from orca_sim.taskgen.photo_contracts import (
    content_hash, default_object, load_scene_spec, object_extent, object_position, validate_scene_spec,
)


def draft_scene(image, *, output, scene_id, categories) -> Path:
    """Prepare a draft after Codex chooses categories; this does not identify an image."""
    from orca_sim.taskgen.photo_upload import normalize_image
    if not 1 <= len(categories) <= 5:
        raise ContractError("Choose one to five supported objects explicitly")
    directory = Path(output).resolve()/scene_id
    # Validate ID before constructing any user-named output directory.
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", scene_id):
        raise ContractError("Invalid scene_id")
    directory.mkdir(parents=True, exist_ok=True)
    source = normalize_image(Path(image).read_bytes(), directory/"source.png")
    objects = [default_object(f"{category}_{index+1}", category,
               xy=((index-(len(categories)-1)/2)*.10, 0)) for index, category in enumerate(categories)]
    spec = {"schema_version": 1, "scene_id": scene_id,
        "source": {k: source[k] for k in ("image", "sha256")},
        "table": {"dimensions": [.60, .40, .02], "top_z": .20, "rgba": [.55, .48, .38, 1.],
                  "friction": [1.2, .01, .001],
                  "provenance": {k: "catalog_default" for k in ("dimensions", "top_z", "rgba", "friction")}},
        "objects": objects, "scale_reference": None,
        "notes": ["Draft template only. Codex must inspect the image and replace layout, boxes, and provenance."],
        "questions": ["Image interpretation and user confirmation pending"], "confirmed": False}
    path = directory/"scene_spec.yaml"
    path.write_text(yaml.safe_dump(validate_scene_spec(spec), sort_keys=True, allow_unicode=True), encoding="utf-8")
    return path


def numbers(values) -> str:
    return " ".join(f"{float(v):.12g}" for v in values)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")


def body_name(obj: dict, target_id: str | None = None) -> str:
    return "task_object" if obj["id"] == target_id else f"scene_{obj['id']}"


def add_object(world: ET.Element, spec: dict, obj: dict, target_id=None) -> None:
    name = body_name(obj, target_id)
    body = ET.SubElement(world, "body", name=name, pos=numbers(object_position(spec, obj)), quat=numbers(obj["quaternion"]))
    ET.SubElement(body, "freejoint", name=f"{name}_freejoint")
    dims = np.asarray(obj["dimensions"], dtype=float)
    category = obj["category"]
    geom = {"name": f"{name}_geom", "rgba": numbers(obj["rgba"]), "mass": str(obj["mass"]),
            "friction": numbers(obj["friction"]), "contype": "3", "conaffinity": "3", "condim": "4",
            "solref": ".01 1", "solimp": ".95 .99 .001"}
    if category == "sphere":
        geom.update(type="sphere", size=numbers([dims[0]/2]))
    elif category == "cylinder":
        geom.update(type="cylinder", size=numbers([dims[0]/2, dims[2]/2]))
    elif category == "pen":
        radius = dims[1]/2
        geom.update(type="capsule", fromto=numbers([-dims[0]/2+radius, 0, 0, dims[0]/2-radius, 0, 0]), size=numbers([radius]))
    else:
        geom.update(type="box", size=numbers(dims/2))
    ET.SubElement(body, "geom", geom)
    # Decorative parts have no mass or collision: inertia is defined by the
    # complete rigid collision proxy above, not multiplied by visual pieces.
    visual = {"type": "box", "contype": "0", "conaffinity": "0", "mass": "0", "group": "2"}
    if category == "book":
        for sign in (-1, 1):
            ET.SubElement(body, "geom", {**visual, "pos": numbers([0, 0, sign*(dims[2]/2-.0005)]),
                "size": numbers([dims[0]/2, dims[1]/2, .0005]), "rgba": numbers(obj["rgba"])})
        # White page edge is inset inside the rigid book volume.
        ET.SubElement(body, "geom", {**visual, "pos": numbers([0, -dims[1]/2, 0]),
            "size": numbers([dims[0]*.48, .0001, dims[2]*.4]), "rgba": ".9 .88 .8 1"})
    elif category == "pen":
        ET.SubElement(body, "geom", {**visual, "pos": numbers([dims[0]*.25, 0, dims[2]*.35]),
            "size": numbers([dims[0]*.13, dims[1]*.15, dims[2]*.15]), "rgba": ".6 .6 .65 1"})
        ET.SubElement(body, "geom", {"type": "sphere", "pos": numbers([-dims[0]/2+dims[1]/4, 0, 0]),
            "size": numbers([dims[1]/4]), "rgba": ".7 .7 .75 1", "contype": "0", "conaffinity": "0", "mass": "0"})


def compile_scene(spec: dict, *, hand_include: str | None = None, target_id=None, target_xy=None) -> str:
    spec = validate_scene_spec(spec)
    root = ET.Element("mujoco", model=spec["scene_id"])
    ET.SubElement(root, "compiler", angle="radian", autolimits="true")
    ET.SubElement(root, "option", timestep="0.002", gravity="0 0 -9.81", integrator="implicitfast", iterations="100")
    ET.SubElement(root, "visual")
    if hand_include:
        ET.SubElement(root, "include", file=hand_include)
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos="0 -0.3 1.5", dir="0 0 -1", diffuse=".8 .8 .8")
    ET.SubElement(world, "geom", name="floor", type="plane", size="2 2 .1", rgba=".22 .27 .33 1", contype="3", conaffinity="3")
    table = spec["table"]
    ET.SubElement(world, "geom", name="photo_table", type="box", pos=numbers([0, 0, table["top_z"]-table["dimensions"][2]/2]),
        size=numbers(np.asarray(table["dimensions"])/2), rgba=numbers(table["rgba"]), friction=numbers(table["friction"]),
        contype="3", conaffinity="3", solref=".01 1", solimp=".95 .99 .001")
    for obj in spec["objects"]:
        add_object(world, spec, obj, target_id)
    if target_xy is not None:
        ET.SubElement(world, "site", name="task_target", type="cylinder", pos=numbers([*target_xy, table["top_z"]+.001]), size=".03 .001", rgba=".1 .8 .2 .45")
    ET.indent(root, space="  ")
    return '<?xml version="1.0"?>\n'+ET.tostring(root, encoding="unicode")+"\n"


def verify_initial_contacts(model, data) -> None:
    mujoco.mj_forward(model, data)
    for c in data.contact:
        b1, b2 = int(model.geom_bodyid[c.geom1]), int(model.geom_bodyid[c.geom2])
        if b1 != b2 and c.dist < -0.00001:
            raise ContractError("Scene has initial intersecting objects; correct positions or orientations explicitly")


def generate_scene(spec_path: str | Path, *, output: str | Path) -> Path:
    from orca_sim.taskgen.photo_upload import normalize_image
    from PIL import Image, ImageDraw

    spec_path = Path(spec_path).resolve()
    spec = load_scene_spec(spec_path)
    image_path = (spec_path.parent/spec["source"]["image"]).resolve()
    if spec_path.parent not in image_path.parents:
        raise ContractError("source image escapes spec directory")
    if hashlib.sha256(image_path.read_bytes()).hexdigest() != spec["source"]["sha256"]:
        raise ContractError("source image hash does not match SceneSpec")
    xml = compile_scene(spec)
    model = mujoco.MjModel.from_xml_string(xml)
    verify_initial_contacts(model, mujoco.MjData(model))
    bundle = Path(output).resolve()/spec["scene_id"]
    bundle.mkdir(parents=True, exist_ok=True)
    normalize_image(image_path.read_bytes(), bundle/"source.png")
    normalized = deepcopy(spec)
    normalized["source"] = {"image": "source.png", "sha256": hashlib.sha256((bundle/"source.png").read_bytes()).hexdigest()}
    (bundle/"scene_spec.yaml").write_text(yaml.safe_dump(normalized, sort_keys=True, allow_unicode=True), encoding="utf-8")
    (bundle/"scene.xml").write_text(xml, encoding="utf-8")
    with Image.open(bundle/"source.png") as source:
        annotation = source.convert("RGB")
    draw = ImageDraw.Draw(annotation)
    for index, obj in enumerate(spec["objects"], 1):
        x1, y1, x2, y2 = obj["image_bbox"]
        box = (x1*annotation.width, y1*annotation.height, x2*annotation.width, y2*annotation.height)
        draw.rectangle(box, outline="red", width=3)
        draw.text((box[0]+3, box[1]+3), f"{index}: {obj['id']}", fill="red")
    annotation.save(bundle/"annotated.png")
    write_json(bundle/"manifest.json", {"kind": "scene", "schema_version": 1, "scene_id": spec["scene_id"],
        "package_version": "0.3.0", "spec_sha256": content_hash(normalized), "validation": "pending",
        "files": ["scene_spec.yaml", "scene.xml", "source.png", "annotated.png", "manifest.json", "scene_report.json"]})
    write_json(bundle/"scene_report.json", {"physics": "pending", "confirmation": "confirmed" if spec["confirmed"] else "pending"})
    return bundle


class PhotoScene:
    """A scene without actions, rewards, or success conditions."""
    def __init__(self, bundle: str | Path):
        self.bundle = Path(bundle).resolve()
        self.spec = load_scene_spec(self.bundle/"scene_spec.yaml")
        manifest = json.loads((self.bundle/"manifest.json").read_text(encoding="utf-8"))
        if manifest["spec_sha256"] != content_hash(self.spec):
            raise ContractError("SceneSpec was changed; regenerate the scene before use")
        self.model = mujoco.MjModel.from_xml_path(str(self.bundle/"scene.xml"))
        self.data = mujoco.MjData(self.model)
        self._renderer = None
        mujoco.mj_forward(self.model, self.data)

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)

    def step(self, steps=1):
        mujoco.mj_step(self.model, self.data, nstep=steps)

    def camera(self, azimuth=120):
        camera = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(self.model, camera)
        camera.lookat[:] = [0, 0, self.spec["table"]["top_z"]]
        camera.distance = max(self.spec["table"]["dimensions"][:2])*1.65
        camera.elevation, camera.azimuth = -40, azimuth
        return camera

    def render(self, azimuth=120):
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, height=480, width=640)
        self._renderer.update_scene(self.data, camera=self.camera(azimuth))
        return self._renderer.render().copy()

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


def check_scene(bundle: str | Path, *, steps=2000) -> dict:
    scene = PhotoScene(bundle)
    try:
        physics = inspect_scene_physics(scene.model, scene.data, scene.spec, steps=steps)
        report = {"physics": "pass", "confirmation": "confirmed" if scene.spec["confirmed"] else "pending",
                  "status": "pass" if scene.spec["confirmed"] else "needs_confirmation", "steps": steps,
                  **physics, "layout": "approximate; user-confirmed" if scene.spec["confirmed"] else "approximate; awaiting user review"}
    except (ValueError, RuntimeError) as exc:
        report = {"physics": "fail", "status": "fail", "reason": str(exc)}
    finally:
        scene.close()
    write_json(Path(bundle)/"scene_report.json", report)
    manifest_path = Path(bundle)/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation"] = report["status"]
    write_json(manifest_path, manifest)
    return report


def inspect_scene_physics(model, data, spec, *, steps=2000):
    verify_initial_contacts(model, data)
    initial = data.qpos.copy()
    max_penetration, persistent = 0., 0
    for t in range(steps):
        mujoco.mj_step(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise ContractError("Scene produced non-finite state")
        depth = max((max(0., -float(c.dist)) for c in data.contact), default=0.)
        if t > 100:
            max_penetration = max(max_penetration, depth)
            persistent = persistent+1 if depth > .002 else 0
            if persistent >= 10:
                raise ContractError("Persistent penetration exceeds 2 mm")
    objects = []
    for obj in spec["objects"]:
        body = model.body(body_name(obj)).id
        joint = model.body_jntadr[body]
        adr, vel = int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint])
        drift = float(np.linalg.norm(data.qpos[adr:adr+3]-initial[adr:adr+3]))
        speed = float(np.linalg.norm(data.qvel[vel:vel+3]))
        supported = any(model.geom("photo_table").id in {int(c.geom1), int(c.geom2)} and
            body in {int(model.geom_bodyid[c.geom1]), int(model.geom_bodyid[c.geom2])} for c in data.contact)
        if not supported or drift > .02 or speed > .01:
            raise ContractError(f"{obj['id']}: unstable, unsupported, or layout moved over 2 cm; revise scene explicitly")
        objects.append({"id": obj["id"], "drift_m": drift, "speed_m_s": speed, "supported": True})
    return {"max_penetration_m": max_penetration, "objects": objects}


def preview_scene(bundle: str | Path) -> dict:
    import imageio.v2 as imageio
    scene = PhotoScene(bundle)
    bundle = Path(bundle)
    try:
        scene.step(500)
        imageio.imwrite(bundle/"scene_preview.png", scene.render())
        with imageio.get_writer(bundle/"scene_preview.mp4", fps=30, macro_block_size=1) as writer:
            for angle in np.linspace(0, 360, 90, endpoint=False):
                writer.append_data(scene.render(float(angle)))
    finally:
        scene.close()
    manifest = json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = sorted(set(manifest["files"]) | {"scene_preview.png", "scene_preview.mp4"})
    manifest["preview_kind"] = "camera orbit; no task or policy"
    write_json(bundle/"manifest.json", manifest)
    return {"status": "generated", "image": str(bundle/"scene_preview.png"), "video": str(bundle/"scene_preview.mp4")}


def view_scene(bundle: str | Path) -> None:
    import mujoco.viewer
    scene = PhotoScene(bundle)
    try:
        with mujoco.viewer.launch_passive(scene.model, scene.data) as viewer:
            camera = scene.camera()
            viewer.cam.lookat[:] = camera.lookat
            viewer.cam.distance, viewer.cam.elevation, viewer.cam.azimuth = camera.distance, camera.elevation, camera.azimuth
            while viewer.is_running():
                scene.step(5)
                viewer.sync()
                time.sleep(.01)
    finally:
        scene.close()
