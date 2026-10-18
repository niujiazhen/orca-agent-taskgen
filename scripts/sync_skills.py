"""Publish the repository skill into the distributable plugin; --check is read-only."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = ROOT/".agents/skills/orca-env-generator"
    target = ROOT/"plugins/orca-env-generator/skills/orca-env-generator"
    paths = [p.relative_to(source) for p in source.rglob("*") if p.is_file()]
    for relative in paths:
        output = target/relative
        if args.check:
            if not output.is_file() or output.read_bytes() != (source/relative).read_bytes():
                raise SystemExit(f"Unsynchronized skill resource: {relative}")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source/relative, output)
    if args.check:
        extra = {p.relative_to(target) for p in target.rglob("*") if p.is_file()}-set(paths)
        if extra:
            raise SystemExit(f"Stale plugin resources: {extra}")


if __name__ == "__main__":
    main()
