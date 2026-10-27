"""Portable SceneSpec v2 assets, validation and MuJoCo compilation.

Blender is an authoring dependency only. Loading these bundles needs no Blender.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
import yaml
from jsonschema import Draft202012Validator

from orca_sim.taskgen.contracts import (
    ContractError, _assert_finite, _assert_safe_relative_path, _schema, _validate_schema,
)


def asset_path(root, name):
    _assert_safe_relative_path(name, "asset.file")
    root = Path(root).resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        raise ContractError(f"Missing or escaping asset: {name}")
    return path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset_records(spec):
    yield spec["source"] | {"file": spec["source"]["image"]}
    yield from spec["artifacts"]
    for obj in spec["objects"]:
        yield obj["geometry"]["collision"]
        yield from obj["geometry"]["visuals"]


def read_obj(path):
    """Read our explicit, triangulated OBJ subset without an extra dependency."""
    vertices, faces = [], []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts or parts[0].startswith("#"):
                continue
            if parts[0] == "v":
                if len(parts) != 4:
                    raise ValueError("Expected XYZ vertices")
                vertices.append([float(v) for v in parts[1:]])
            elif parts[0] == "f":
                if len(parts) != 4:
                    raise ValueError("Expected triangle faces")
                faces.append([int(v.split('/')[0]) - 1 for v in parts[1:]])
            else:
                raise ValueError(f"Unsupported OBJ directive: {parts[0]}")
        v = np.asarray(vertices, dtype=float)
        f = np.asarray(faces, dtype=int)
        if v.ndim != 2 or v.shape[1] != 3 or len(v) < 3 or not np.isfinite(v).all():
            raise ValueError("Mesh must contain finite XYZ vertices")
        if f.ndim != 2 or f.shape[1] != 3 or len(f) < 1 or f.min() < 0 or f.max() >= len(v):
            raise ValueError("Mesh must contain valid triangle indices")
        if np.any(np.linalg.norm(np.cross(v[f[:, 1]]-v[f[:, 0]], v[f[:, 2]]-v[f[:, 0]]), axis=1) < 1e-16):
            raise ValueError("Mesh contains degenerate triangles")
        return v, f
    except (ValueError, OSError) as exc:
        raise ContractError(f"Invalid mesh {Path(path).name}: {exc}") from exc


def validate_mesh_spec(data):
    from orca_sim.taskgen.photo_contracts import rotation
    _assert_finite(data, "SceneSpec")
    _validate_schema(data, Draft202012Validator(_schema("scene_spec_v2.schema.json")), "SceneSpec")
    ids = [o["id"] for o in data["objects"]]
    if len(set(ids)) != len(ids):
        raise ContractError("SceneSpec object IDs must be unique")
    paths = {}
    for record in asset_records(data):
        name = record["file"]
        _assert_safe_relative_path(name, "asset.file")
        if name in paths and paths[name] != record["sha256"]:
            raise ContractError(f"Conflicting hashes for asset: {name}")
        paths[name] = record["sha256"]
        if name in {"scene.xml", "scene_spec.yaml", "manifest.json", "scene_report.json", "annotated.png"}:
            raise ContractError(f"Asset uses a reserved output name: {name}")
    table = data["table"]
    if table["dimensions"][2] >= table["top_z"]:
        raise ContractError("Table slab must be above the floor")
    for obj in data["objects"]:
        if not np.isclose(np.linalg.norm(obj["quaternion"]), 1, atol=1e-5):
            raise ContractError(f"{obj['id']}: quaternion must be normalized")
        lo, hi = np.asarray(obj["geometry"]["bounds"], dtype=float)
        if np.any(hi <= lo) or not np.allclose(hi-lo, obj["dimensions"], atol=1e-7):
            raise ContractError(f"{obj['id']}: inconsistent mesh bounds/dimensions")
        corners = np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
        world = corners @ rotation(obj["quaternion"]).T + obj["position"]
        if np.any(np.abs(world[:, :2]) > np.asarray(table["dimensions"][:2])/2 + 1e-6):
            raise ContractError(f"{obj['id']}: extends beyond tabletop; revise in Blender")
        bbox = obj["image_bbox"]
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise ContractError(f"{obj['id']}: invalid image bounding box")
    if data["confirmed"] and data["questions"]:
        raise ContractError("Resolve questions before confirmation")
    return deepcopy(data)


def verify_mesh_assets(spec, root):
    for record in asset_records(spec):
        path = asset_path(root, record["file"])
        if digest(path) != record["sha256"]:
            raise ContractError(f"Asset changed since export/review: {record['file']}; re-export and review")
    for obj in spec["objects"]:
        vertices, faces = read_obj(asset_path(root, obj["geometry"]["collision"]["file"]))
        if len(vertices) < 4 or len(faces) < 4:
            raise ContractError(f"{obj['id']}: collision hull has no volume")
        if not np.allclose([vertices.min(0), vertices.max(0)], obj["geometry"]["bounds"], atol=1e-7):
            raise ContractError(f"{obj['id']}: collision bounds do not match specification")
        count = 0
        for part in obj["geometry"]["visuals"]:
            _, triangles = read_obj(asset_path(root, part["file"]))
            count += len(triangles)
        if count > 20_000:
            raise ContractError(f"{obj['id']}: {count} triangles exceeds 20,000; simplify in Blender")


def compile_mesh_scene(spec):
    from orca_sim.taskgen.photo_scene import numbers
    spec = validate_mesh_spec(spec)
    root = ET.Element("mujoco", model=spec["scene_id"])
    ET.SubElement(root, "compiler", angle="radian", autolimits="true", inertiafromgeom="true", inertiagrouprange="3 3")
    ET.SubElement(root, "option", timestep="0.002", gravity="0 0 -9.81", integrator="implicitfast", iterations="100")
    assets = ET.SubElement(root, "asset")
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos="0 -0.3 1.5", dir="0 0 -1", diffuse=".8 .8 .8")
    ET.SubElement(world, "geom", name="floor", type="plane", size="2 2 .1", rgba=".22 .27 .33 1", contype="3", conaffinity="3")
    table = spec["table"]
    ET.SubElement(world, "geom", name="photo_table", type="box", pos=numbers([0,0,table["top_z"]-table["dimensions"][2]/2]),
                  size=numbers(np.asarray(table["dimensions"])/2), rgba=numbers(table["rgba"]), friction=numbers(table["friction"]),
                  contype="3", conaffinity="3", solref=".01 1", solimp=".95 .99 .001")
    for obj in spec["objects"]:
        oid = obj["id"]
        body = ET.SubElement(world, "body", name=f"scene_{oid}", pos=numbers(obj["position"]), quat=numbers(obj["quaternion"]))
        ET.SubElement(body, "freejoint", name=f"scene_{oid}_freejoint")
        name = f"{oid}_collision"
        ET.SubElement(assets, "mesh", name=name, file=obj["geometry"]["collision"]["file"], inertia="convex")
        ET.SubElement(body, "geom", name=f"scene_{oid}_geom", type="mesh", mesh=name, group="3", rgba=".1 .8 .4 1",
                      mass=str(obj["mass"]), friction=numbers(obj["friction"]), contype="3", conaffinity="3", condim="4",
                      solref=".01 1", solimp=".95 .99 .001")
        for i, part in enumerate(obj["geometry"]["visuals"]):
            name = f"{oid}_visual_{i}"
            ET.SubElement(assets, "mesh", name=name, file=part["file"], inertia="convex")
            ET.SubElement(assets, "material", name=name, rgba=numbers(part["rgba"]), specular=".25", shininess=".3")
            ET.SubElement(body, "geom", name=name, type="mesh", mesh=name, material=name, group="2", mass="0", contype="0", conaffinity="0")
    ET.indent(root, space="  ")
    return '<?xml version="1.0"?>\n'+ET.tostring(root, encoding="unicode")+'\n'


def generate_mesh_scene(spec_path, output):
    from orca_sim.taskgen.photo_contracts import load_scene_spec, content_hash
    from orca_sim.taskgen.photo_scene import verify_initial_contacts, write_json, annotate_scene
    path = Path(spec_path).resolve()
    spec = load_scene_spec(path)
    verify_mesh_assets(spec, path.parent)
    xml = compile_mesh_scene(spec)
    assets = {r["file"]: asset_path(path.parent, r["file"]).read_bytes() for r in asset_records(spec) if r["file"].endswith('.obj')}
    model = mujoco.MjModel.from_xml_string(xml, assets=assets)
    data = mujoco.MjData(model)
    verify_initial_contacts(model, data)
    # Preserve the exact saved Blender positions: never snap a floating asset down.
    mujoco.mj_forward(model, data)
    from orca_sim.taskgen.photo_contracts import rotation
    for obj in spec["objects"]:
        vertices, _ = read_obj(asset_path(path.parent, obj["geometry"]["collision"]["file"]))
        world = vertices @ rotation(obj["quaternion"]).T + obj["position"]
        if not spec["table"]["top_z"]-1e-5 <= world[:,2].min() <= spec["table"]["top_z"]+.001:
            raise ContractError(f"{obj['id']}: not initially supported by tabletop; correct its saved Blender position")
    bundle = Path(output).resolve()/spec["scene_id"]
    bundle.mkdir(parents=True, exist_ok=True)
    names = []
    for record in asset_records(spec):
        source = asset_path(path.parent, record["file"])
        destination = bundle/record["file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source != destination.resolve():
            shutil.copy2(source, destination)
        names.append(record["file"])
    (bundle/"scene_spec.yaml").write_text(yaml.safe_dump(spec, sort_keys=True, allow_unicode=True), encoding="utf-8")
    (bundle/"scene.xml").write_text(xml, encoding="utf-8")
    annotate_scene(bundle, spec)
    write_json(bundle/"manifest.json", {"kind":"scene", "schema_version":2, "package_version":"0.4.1", "scene_id":spec["scene_id"],
               "object_catalog":"open", "objects":[{"id":o["id"], "name":o["name"], "geometry":"mesh"} for o in spec["objects"]],
               "spec_sha256":content_hash(spec), "model_sha256":digest(bundle/"scene.xml"), "validation":"pending", "collision_model":"one convex hull per rigid object; cavities may be filled",
               "files":sorted(set(names+['scene_spec.yaml','scene.xml','manifest.json','scene_report.json','annotated.png']))})
    write_json(bundle/"scene_report.json", {"physics":"pending", "confirmation":"confirmed" if spec["confirmed"] else "pending"})
    return bundle
