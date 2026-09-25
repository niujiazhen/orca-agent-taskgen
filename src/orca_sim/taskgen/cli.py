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

    check = subparsers.add_parser("check", help="run non-learning v2 acceptance")
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
    if args.command == "validate":
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
        result = accept_v2_bundle(
            args.directory,
            episodes=args.episodes,
            stress_steps=args.stress_steps,
            reset_count=args.reset_count,
        )
    elif args.command == "preview":
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


if __name__ == "__main__":
    main()
