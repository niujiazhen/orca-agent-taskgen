"""Local Blender authoring lifecycle. The agent writes the modeling script."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import yaml

from orca_sim.taskgen.contracts import ContractError, _assert_finite, _validate_schema, _schema
from jsonschema import Draft202012Validator

WORKER = Path(__file__).with_name("blender_worker.py")


def find_blender(executable=None):
    explicit = executable or os.environ.get("ORCA_BLENDER_PATH")
    candidates = [Path(explicit)] if explicit else []
    if not explicit:
        located = shutil.which("blender")
        if located:
            candidates.append(Path(located))
        for base in (Path(os.environ.get("PROGRAMFILES", "C:/Program Files")), Path.home()/"AppData/Local/Programs"):
            candidates.extend(sorted((base/"Blender Foundation").glob("*/blender.exe"), reverse=True))
        candidates.extend([Path("/Applications/Blender.app/Contents/MacOS/Blender"), Path("/usr/bin/blender")])
    for path in candidates:
        if not path.is_file():
            continue
        try:
            result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=15,
                                    **({"creationflags":subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and re.search(r"Blender 4\.5\.\d+", result.stdout):
            return path.resolve()
        if explicit:
            raise ContractError("Blender 4.5 LTS is required; configured executable has an unsupported version")
    raise ContractError("Blender 4.5 LTS was not found. Install it from https://www.blender.org/releases/4-5/ "
                        "and set ORCA_BLENDER_PATH to blender.exe (or use --blender <path>)")


def load_object_plan(path):
    path = Path(path).resolve()
    try:
        plan = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"Cannot read object plan: {exc}") from exc
    _assert_finite(plan, "ObjectPlan")
    _validate_schema(plan, Draft202012Validator(_schema("blender_object_plan.schema.json")), "ObjectPlan")
    ids = [o["id"] for o in plan["objects"]]
    if len(set(ids)) != len(ids):
        raise ContractError("ObjectPlan IDs must be unique")
    for obj in plan["objects"]:
        q = obj.get("quaternion", [1, 0, 0, 0])
        if not math.isclose(sum(x*x for x in q), 1, abs_tol=1e-5):
            raise ContractError(f"{obj['id']}: quaternion must be normalized")
        b = obj["image_bbox"]
        if b[0] >= b[2] or b[1] >= b[3]:
            raise ContractError(f"{obj['id']}: invalid source image bounding box")
    from orca_sim.taskgen.contracts import _assert_safe_relative_path
    from orca_sim.taskgen.mesh_scene import asset_path
    _assert_safe_relative_path(plan["source"], "ObjectPlan.source")
    source = asset_path(path.parent, plan["source"])
    if "source_sha256" in plan:
        from orca_sim.taskgen.mesh_scene import digest
        if digest(source) != plan["source_sha256"]:
            raise ContractError("ObjectPlan source changed since normalization")
    return plan


def _run(executable, mode, workspace):
    log = workspace/f"{mode}.log"
    command = [str(executable), "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
               "--python", str(WORKER), "--", mode, str(workspace)]
    try:
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(command, cwd=workspace, stdout=output, stderr=subprocess.STDOUT, timeout=180,
                                    **({"creationflags":subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
        if result.returncode:
            detail = log.read_text(encoding="utf-8", errors="replace")[-5000:]
            raise ContractError(f"Blender {mode} failed; preserved {log}:\n{detail}")
    except subprocess.TimeoutExpired as exc:
        raise ContractError(f"Blender {mode} exceeded 180 seconds; see {log}") from exc


def build_blender(plan_path, *, script, output, executable=None, open_ui=False):
    from orca_sim.taskgen.photo_upload import normalize_image
    plan_path, script = Path(plan_path).resolve(), Path(script).resolve()
    plan = load_object_plan(plan_path)
    if not script.is_file():
        raise ContractError("Modeling script is missing")
    blender = find_blender(executable)
    workspace = Path(output).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    report_path = workspace/"build_report.json"
    previous = json.loads(report_path.read_text()) if report_path.exists() else {}
    if previous.get("status") == "built" or (workspace/"project.blend").exists() and not previous:
        raise ContractError("Workspace already contains a Blender project; edit it or choose a new output directory")
    attempts = previous.get("attempts", 0)
    if attempts >= 3:
        raise ContractError("Three modeling attempts failed. Keep the workspace/logs and request user guidance")
    normalized = normalize_image((plan_path.parent/plan["source"]).read_bytes(), workspace/"source.png")
    plan["source"] = "source.png"
    plan["source_sha256"] = normalized["sha256"]
    (workspace/"object_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    if script != workspace/"model.py":
        shutil.copy2(script, workspace/"model.py")
    # Preserve each attempted script/log; retries must be actual agent repairs.
    shutil.copy2(workspace/"model.py", workspace/f"model_attempt_{attempts+1}.py")
    try:
        _run(blender, "build", workspace)
    except ContractError:
        report_path.write_text(json.dumps({"status":"failed", "attempts":attempts+1}), encoding="utf-8")
        shutil.copy2(workspace/"build.log", workspace/f"build_attempt_{attempts+1}.log")
        raise
    from orca_sim.taskgen.mesh_scene import digest
    report_path.write_text(json.dumps({"status":"built", "attempts":attempts+1, "review":"pending",
                           "backend":"blender_mesh", "object_catalog":"open",
                           "ui_opened":open_ui,
                           "objects":[{"id":o["id"], "name":o["name"]} for o in plan["objects"]],
                           "model_script_sha256":digest(workspace/"model.py")}), encoding="utf-8")
    if open_ui:
        open_blender(workspace, executable=blender)
    return {"status":"needs_blender_review" if open_ui else "ready_for_export", "directory":str(workspace),
            "project":str(workspace/"project.blend"), "preview":str(workspace/"blender_preview.png"), "ui_opened":open_ui,
            "intermediate_files":["project.blend","blender_preview.png","model.py","object_plan.json","build_report.json"],
            "next":"Review/edit in Blender, save, then run blender export" if open_ui else "Run blender export, scene generate, scene check and scene preview"}


def open_blender(workspace, *, executable=None):
    workspace = Path(workspace).resolve()
    project = workspace/"project.blend"
    if not project.is_file():
        raise ContractError("Workspace is missing project.blend")
    blender = find_blender(executable)
    # A visible window is intentional: manual Blender inspection is this step.
    options = {"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session":True}
    with (workspace/"interactive.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([str(blender), "--disable-autoexec", str(project)], cwd=workspace, stdout=log, stderr=log, **options)
    return {"status":"opened_for_review", "pid":process.pid, "project":str(project)}


def export_blender(workspace, *, executable=None):
    workspace = Path(workspace).resolve()
    if not (workspace/"project.blend").is_file() or not (workspace/"object_plan.json").is_file():
        raise ContractError("Workspace requires project.blend and object_plan.json")
    blender = find_blender(executable)
    # A failed export invalidates any previously exported snapshot.
    marker = workspace/"export_report.json"
    marker.write_text(json.dumps({"status":"exporting"}), encoding="utf-8")
    snapshot = workspace/"export/scene_spec.yaml"
    if snapshot.exists():
        snapshot.replace(snapshot.with_name("scene_spec.previous.yaml"))
    try:
        _run(blender, "export", workspace)
        from orca_sim.taskgen.photo_contracts import load_scene_spec
        spec = load_scene_spec(workspace/"export/scene_spec.yaml")
    except (ContractError, OSError, ValueError):
        if snapshot.exists():
            snapshot.replace(snapshot.with_name("scene_spec.failed.yaml"))
        marker.write_text(json.dumps({"status":"failed", "next":"Correct the saved Blender project and export again"}), encoding="utf-8")
        raise
    return {"status":"exported_needs_scene_review", "spec":str(workspace/"export/scene_spec.yaml"),
            "objects":[o["id"] for o in spec["objects"]], "next":"scene generate, scene check, scene preview"}
