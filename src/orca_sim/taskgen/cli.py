"""Create, validate, inspect, and visualize generated ORCA environments."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import yaml

from orca_sim.taskgen.acceptance import accept_generated_task
from orca_sim.taskgen.acceptance_v2 import accept_v2_bundle
from orca_sim.taskgen.contracts import load_task_spec
from orca_sim.taskgen.generator import generate_task
from orca_sim.taskgen.text import task_spec_from_text
from orca_sim.taskgen.validator import validate_generated_directory, validate_runtime
from orca_sim.taskgen.visualization import preview_bundle, view_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    blender_parser = subparsers.add_parser("blender", help="build, review and export local Blender mesh scenes (scene display only)")
    blender_commands = blender_parser.add_subparsers(dest="blender_command", required=True)
    build = blender_commands.add_parser("build")
    build.add_argument("plan", type=Path)
    build.add_argument("--script", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--no-open", action="store_true", help="headless testing only; interactive review remains pending")
    build.add_argument("--blender", type=Path)
    for name in ("open", "export"):
        item = blender_commands.add_parser(name)
        item.add_argument("directory", type=Path)
        item.add_argument("--blender", type=Path)
    doctor = blender_commands.add_parser("doctor")
    doctor.add_argument("--blender", type=Path)

    capture = subparsers.add_parser("capture", help="start a local photo upload service; image interpretation stays in Codex")
    capture.add_argument("--lan", action="store_true")
    capture.add_argument("--port", type=int, default=8765)
    capture.add_argument("--advertise-host")
    capture.add_argument("--output", type=Path, default=Path("photo_captures"))
    capture.add_argument("--duration", type=int, default=3600)
    capture_wait = subparsers.add_parser("capture-wait", help="wait up to 60 seconds for a photo receipt")
    capture_wait.add_argument("directory", type=Path)
    capture_wait.add_argument("--timeout", type=int, default=45)

    scene_parser = subparsers.add_parser("scene", help="draft, generate, review, and inspect photo scenes")
    scenes = scene_parser.add_subparsers(dest="scene_command", required=True)
    draft = scenes.add_parser("draft", help="prepare a template AFTER Codex identifies objects")
    draft.add_argument("--image", type=Path, required=True)
    draft.add_argument("--scene-id", required=True)
    draft.add_argument("--objects", nargs="+", required=True, choices=["box", "cylinder", "sphere", "pen", "eraser", "book"])
    draft.add_argument("--output", type=Path, default=Path("scene_drafts"))
    scene_generate = scenes.add_parser("generate")
    scene_generate.add_argument("spec", type=Path)
    scene_generate.add_argument("--output", type=Path, default=Path("generated_scenes"))
    for name in ("check", "preview", "view", "confirm", "calibrate"):
        item = scenes.add_parser(name)
        item.add_argument("directory", type=Path)
        if name == "confirm":
            item.add_argument("--spec-sha256", required=True)
        elif name == "calibrate":
            item.add_argument("--object", dest="object_id", required=True)
            item.add_argument("--axis", type=int, choices=[0, 1, 2], required=True)
            item.add_argument("--length", type=float, required=True, help="known full length in metres")

    task_parser = subparsers.add_parser("task", help="create an RL task from a user-confirmed photo scene")
    tasks = task_parser.add_subparsers(dest="task_command", required=True)
    create = tasks.add_parser("create")
    create.add_argument("directory", type=Path)
    create.add_argument("--family", choices=["pick_up", "pick_place"], required=True)
    create.add_argument("--object", dest="object_id", required=True)
    create.add_argument("--target-xy", type=float, nargs=2)
    create.add_argument("--env-id")
    create.add_argument("--hold-steps", type=int, default=20)
    create.add_argument("--request")
    create.add_argument("--output", type=Path, default=Path("generated_tasks"))

    validate = subparsers.add_parser("validate", help="validate a TaskSpec YAML")
    validate.add_argument("spec", type=Path)

    generate = subparsers.add_parser("generate", help="generate a task bundle from TaskSpec YAML")
    generate.add_argument("spec", type=Path)
    generate.add_argument("--output", type=Path, default=Path("generated_tasks"))
    generate.add_argument("--attempt", type=int, default=1)

    generate_text = subparsers.add_parser(
        "generate-text", help="generate a bounded v2 task from Chinese or English text"
    )
    generate_text.add_argument("request")
    generate_text.add_argument("--env-id")
    generate_text.add_argument("--output", type=Path, default=Path("generated_tasks"))

    static = subparsers.add_parser("check-static", help="validate generated files")
    static.add_argument("directory", type=Path)

    runtime = subparsers.add_parser("check-runtime", help="run Gymnasium smoke checks")
    runtime.add_argument("directory", type=Path)
    runtime.add_argument("--steps", type=int, default=200)
    runtime.add_argument("--seed", type=int, default=0)

    check = subparsers.add_parser("check", help="run versioned scene/interface/script validation")
    check.add_argument("directory", type=Path)
    check.add_argument("--episodes", type=int, default=10)
    check.add_argument("--stress-steps", type=int, default=10_000)
    check.add_argument("--reset-count", type=int, default=100)

    preview = subparsers.add_parser("preview", help="write preview.png and preview.mp4")
    preview.add_argument("directory", type=Path)
    preview.add_argument("--max-steps", type=int)

    view = subparsers.add_parser("view", help="open the interactive MuJoCo viewer")
    view.add_argument("directory", type=Path)

    legacy = subparsers.add_parser("accept", help="run legacy v1 PinchAndHold acceptance")
    legacy.add_argument("directory", type=Path)
    legacy.add_argument("--artifacts", type=Path, default=Path("artifacts/pinch_and_hold"))
    legacy.add_argument("--episodes", type=int, default=100)
    legacy.add_argument("--stress-steps", type=int, default=10_000)
    legacy.add_argument("--skip-videos", action="store_true")
    return parser.parse_args()


def _generate_from_text(args: argparse.Namespace) -> dict:
    spec = task_spec_from_text(args.request, env_id=args.env_id)
    with tempfile.TemporaryDirectory(prefix="orca-task-") as temp:
        spec_path = Path(temp) / "task_spec.yaml"
        spec_path.write_text(yaml.safe_dump(spec, sort_keys=True, allow_unicode=True), encoding="utf-8")
        output_root = args.output.resolve()
        directory = generate_task(spec_path, output_root=output_root, allowed_output_root=output_root)
    return {
        "status": "generated",
        "env_id": spec["task"]["env_id"],
        "family": spec["task"]["family"],
        "directory": str(directory),
    }


def main() -> None:
    args = parse_args()
    if args.command == "blender":
        from orca_sim.taskgen.blender import build_blender, open_blender, export_blender, find_blender
        if args.blender_command == "build":
            result = build_blender(args.plan, script=args.script, output=args.output, executable=args.blender, open_ui=not args.no_open)
        elif args.blender_command == "open":
            result = open_blender(args.directory, executable=args.blender)
        elif args.blender_command == "export":
            result = export_blender(args.directory, executable=args.blender)
        else:
            from importlib.metadata import version
            result = {"status":"available", "executable":str(find_blender(args.blender)), "supported_version":"4.5 LTS",
                      "package_version":version("orca_sim"), "photo_backend":"blender_mesh", "object_catalog":"open",
                      "scope":"common rigid objects; no predefined class list; scene display only"}
    elif args.command == "capture":
        from orca_sim.taskgen.photo_upload import serve_capture
        serve_capture(output=args.output, lan=args.lan, port=args.port, advertise_host=args.advertise_host, duration=args.duration)
        return
    elif args.command == "capture-wait":
        from orca_sim.taskgen.photo_upload import wait_for_upload
        result = wait_for_upload(args.directory, timeout=args.timeout)
    elif args.command == "scene":
        result = _scene_command(args)
    elif args.command == "task":
        from orca_sim.taskgen.photo_task import create_photo_task
        directory = create_photo_task(args.directory, output=args.output, family=args.family, object_id=args.object_id,
            target_xy=args.target_xy, env_id=args.env_id, hold_steps=args.hold_steps, source_text=args.request)
        result = {"status": "generated", "directory": str(directory), "schema_version": 3}
    elif args.command == "validate":
        spec = load_task_spec(args.spec, allowed_root=args.spec.resolve().parent)
        result = {
            "status": "pass",
            "schema_version": spec["schema_version"],
            "env_id": spec["task"]["env_id"],
        }
    elif args.command == "generate":
        output_root = args.output.resolve()
        directory = generate_task(
            args.spec,
            output_root=output_root,
            allowed_output_root=output_root,
            attempt=args.attempt,
        )
        result = {"status": "generated", "directory": str(directory)}
    elif args.command == "generate-text":
        result = _generate_from_text(args)
    elif args.command == "check-static":
        result = validate_generated_directory(args.directory)
    elif args.command == "check-runtime":
        result = validate_runtime(args.directory, steps=args.steps, seed=args.seed)
    elif args.command == "check":
        version = json.loads((args.directory/"manifest.json").read_text(encoding="utf-8"))["schema_version"]
        if version == 3:
            from orca_sim.taskgen.photo_task import check_photo_task
            checker = check_photo_task
        else:
            checker = accept_v2_bundle
        result = checker(
            args.directory,
            episodes=args.episodes,
            stress_steps=args.stress_steps,
            reset_count=args.reset_count,
        )
    elif args.command == "preview":
        version = json.loads((args.directory/"manifest.json").read_text(encoding="utf-8"))["schema_version"]
        if version == 3:
            from orca_sim.taskgen.photo_task import preview_photo_task
            result = preview_photo_task(args.directory, max_steps=args.max_steps)
        else:
            result = preview_bundle(args.directory, max_steps=args.max_steps)
    elif args.command == "view":
        view_bundle(args.directory)
        result = {"status": "closed"}
    else:
        result = accept_generated_task(
            args.directory,
            artifacts_dir=args.artifacts,
            episodes=args.episodes,
            stress_steps=args.stress_steps,
            videos=not args.skip_videos,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if isinstance(result, dict) and result.get("status") == "fail":
        raise SystemExit(1)


def _scene_command(args):
    from orca_sim.taskgen.photo_scene import (
        check_scene, draft_scene, generate_scene, preview_scene, view_scene,
    )
    from orca_sim.taskgen.photo_contracts import calibrate_scene, content_hash, load_scene_spec
    from orca_sim.taskgen.contracts import ContractError
    if args.scene_command == "draft":
        path = draft_scene(args.image, output=args.output, scene_id=args.scene_id, categories=args.objects)
        return {"status": "draft_requires_image_interpretation", "spec": str(path)}
    if args.scene_command == "generate":
        directory = generate_scene(args.spec, output=args.output)
        spec = load_scene_spec(directory/"scene_spec.yaml")
        return {"status": "generated", "directory": str(directory), "spec_sha256": content_hash(spec), "confirmed": spec["confirmed"]}
    if args.scene_command == "check":
        return check_scene(args.directory)
    if args.scene_command == "preview":
        return preview_scene(args.directory)
    if args.scene_command == "view":
        view_scene(args.directory)
        return {"status": "closed"}
    path = args.directory/"scene_spec.yaml"
    spec = load_scene_spec(path)
    if args.scene_command == "confirm":
        if content_hash(spec) != args.spec_sha256:
            raise ContractError("Scene changed since review; show the current preview before confirming")
        if spec["questions"]:
            raise ContractError("Resolve pending questions before confirming")
        spec["confirmed"] = True
    else:
        spec = calibrate_scene(spec, args.object_id, args.axis, args.length)
    path.write_text(yaml.safe_dump(spec, sort_keys=True, allow_unicode=True), encoding="utf-8")
    directory = generate_scene(path, output=args.directory.resolve().parent)
    return {"status": "confirmed" if spec["confirmed"] else "needs_review", "directory": str(directory),
            "spec_sha256": content_hash(load_scene_spec(directory/"scene_spec.yaml"))}


if __name__ == "__main__":
    main()
