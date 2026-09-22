"""CLI for validating, generating, and smoke-checking ORCA TaskSpecs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orca_sim.taskgen.contracts import load_task_spec
from orca_sim.taskgen.acceptance import accept_generated_task
from orca_sim.taskgen.generator import GENERATED_ROOT, generate_task
from orca_sim.taskgen.validator import validate_generated_directory, validate_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a TaskSpec YAML")
    validate.add_argument("spec", type=Path)

    generate = subparsers.add_parser("generate", help="generate portable task artifacts")
    generate.add_argument("spec", type=Path)
    generate.add_argument("--attempt", type=int, default=1)

    static = subparsers.add_parser("check-static", help="validate generated files")
    static.add_argument("directory", type=Path)

    runtime = subparsers.add_parser("check-runtime", help="run Gymnasium smoke checks")
    runtime.add_argument("directory", type=Path)
    runtime.add_argument("--steps", type=int, default=200)
    runtime.add_argument("--seed", type=int, default=0)

    accept = subparsers.add_parser("accept", help="run mandatory behavior acceptance")
    accept.add_argument("directory", type=Path)
    accept.add_argument("--artifacts", type=Path, default=Path("artifacts/pinch_and_hold"))
    accept.add_argument("--episodes", type=int, default=100)
    accept.add_argument("--stress-steps", type=int, default=10_000)
    accept.add_argument("--skip-videos", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "validate":
        spec = load_task_spec(args.spec, allowed_root=args.spec.resolve().parent)
        result = {"status": "pass", "env_id": spec["task"]["env_id"]}
    elif args.command == "generate":
        directory = generate_task(args.spec, output_root=GENERATED_ROOT, attempt=args.attempt)
        result = {"status": "generated", "directory": str(directory)}
    elif args.command == "check-static":
        result = validate_generated_directory(args.directory)
    elif args.command == "check-runtime":
        result = validate_runtime(args.directory, steps=args.steps, seed=args.seed)
    else:
        result = accept_generated_task(
            args.directory,
            artifacts_dir=args.artifacts,
            episodes=args.episodes,
            stress_steps=args.stress_steps,
            videos=not args.skip_videos,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
