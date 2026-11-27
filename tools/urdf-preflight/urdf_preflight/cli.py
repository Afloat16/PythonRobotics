"""Command-line entry point. Never expands macros or alters model files."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from . import __version__
from .core import RULES, UNSUPPRESSIBLE, check_file
from .model import MAX_BYTES
from .reports import RENDERERS, terminal_safe, totals

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def discover(paths: list[str]) -> list[Path]:
    files: dict[Path, Path] = {}
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            before = len(files)
            found = False
            for root, dirs, names in os.walk(path, followlinks=False, onerror=lambda exc: (_ for _ in ()).throw(exc)):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(root) / d).is_symlink())
                for name in sorted(names):
                    p = Path(root) / name
                    if p.suffix.lower() == ".urdf" and not p.is_symlink():
                        files.setdefault(p.resolve(), p)
                        found = True
            if not found and len(files) == before:
                raise ValueError(f"No .urdf files found in {raw!r}; Xacro is not expanded automatically.")
        else:
            files.setdefault(path.resolve(), path)
    return sorted(files.values(), key=lambda p: p.as_posix())


def read_baseline(path: Path) -> set[str]:
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Baseline is too large.")
    obj = json.loads(data)
    if (not isinstance(obj, dict) or obj.get("schema_version") != 1
            or obj.get("tool") != "urdf-preflight" or not isinstance(obj.get("fingerprints"), list)):
        raise ValueError("Invalid baseline schema; generate it with --write-baseline.")
    values = obj["fingerprints"]
    if not all(isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v) for v in values):
        raise ValueError("Invalid baseline fingerprint.")
    return set(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="urdf-preflight", description="Read-only URDF preflight. No ROS, simulator, network or runtime dependencies.")
    parser.add_argument("paths", nargs="*", help="URDF files or directories (recursive *.urdf)")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--format", choices=tuple(RENDERERS), default="text")
    parser.add_argument("-o", "--output", type=Path, help="report path; cannot overwrite an input")
    parser.add_argument("--profile", choices=("default", "simulation"), default="default")
    parser.add_argument("--strict", action="store_true", help="fail on active warnings as well as errors")
    parser.add_argument("--package", action="append", default=[], metavar="NAME=DIR")
    parser.add_argument("--no-mesh-check", action="store_true", help="skip mesh existence/resolution checks")
    parser.add_argument("--ignore", action="append", default=[], metavar="RULE[,RULE]")
    parser.add_argument("--baseline", type=Path, help="explicitly accepted existing findings")
    parser.add_argument("--write-baseline", type=Path, help="write fingerprints; current run still fails on findings")
    parser.add_argument("--list-rules", action="store_true")
    args = parser.parse_args(argv)
    if args.list_rules:
        print("\n".join(f"{k}  {v}" for k, v in sorted(RULES.items())))
        return 0
    if not args.paths:
        parser.error("provide at least one URDF file or directory")
    try:
        ignore = {code for group in args.ignore for code in group.split(",")}
        if ignore - RULES.keys() or ignore & UNSUPPRESSIBLE:
            raise ValueError("Unknown or non-suppressible rule in --ignore.")
        packages = {}
        for item in args.package:
            name, sep, folder = item.partition("=")
            if not sep or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or not folder:
                raise ValueError("Package mappings must be NAME=DIR.")
            if name in packages:
                raise ValueError(f"Duplicate package mapping {name!r}.")
            package = Path(folder).resolve()
            if not package.is_dir():
                raise ValueError(f"Package directory does not exist: {folder!r}.")
            packages[name] = package
        paths = discover(args.paths)
        outputs = [p for p in (args.output, args.write_baseline) if p is not None]
        protected = [*paths, *([args.baseline] if args.baseline else [])]
        resolved_outputs = [p.resolve() for p in outputs]
        if len(set(resolved_outputs)) != len(resolved_outputs):
            raise ValueError("Report and baseline output must be different files.")
        for output in outputs:
            if any(output.resolve() == source.resolve() or
                   (output.exists() and source.exists() and output.samefile(source)) for source in protected):
                raise ValueError("An output would overwrite an input or baseline; choose a new path.")
            if output.exists() and not output.is_file():
                raise ValueError("Output is not a regular file.")
        baseline = read_baseline(args.baseline) if args.baseline else set()
        reports = [check_file(p, packages=packages, profile=args.profile,
                              check_meshes=not args.no_mesh_check) for p in paths]
        for report in reports:
            for issue in report.issues:
                issue.suppressed = issue.code not in UNSUPPRESSIBLE and (issue.code in ignore or issue.fingerprint in baseline)
        options = {"profile": args.profile, "strict": args.strict,
                   "mesh_checks": not args.no_mesh_check, "ignored_rules": sorted(ignore),
                   "baseline_used": args.baseline is not None}
        if args.write_baseline:
            obj = {"schema_version": 1, "tool": "urdf-preflight", "fingerprints": sorted({
                i.fingerprint for r in reports for i in r.issues if i.code not in UNSUPPRESSIBLE})}
            args.write_baseline.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        text = RENDERERS[args.format](reports, options)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        counts = totals(reports)
        if any(r.operational_error for r in reports):
            return 2
        return int(counts["errors"] > 0 or (args.strict and counts["warnings"] > 0))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"urdf-preflight: {terminal_safe(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
