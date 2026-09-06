"""Command-line entry point for failclosed_eval.

`run` executes a measurement admission pass over a units file and a policy file and prints the
denominator line, the refusal tally, and the verdict, in that order. `scan` runs the
value-carrying label-leak detector over the repository's own text files. `version` prints the
package version.

The default at every boundary in this file is refusal: an unexpected exception is caught here and
reported as HOLD, never allowed to look like a pass.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from failclosed_eval import __version__, denominator_line, halt_line, scan_paths_for_leaks
from failclosed_eval import run as run_measurement
from failclosed_eval.tracking import get_tracker

_SCAN_EXTENSIONS = (".py", ".md", ".toml", ".yml", ".yaml", ".txt")
_SCAN_SKIP_DIR_NAMES = {"fixtures", ".git", "__pycache__", ".venv", "venv"}


def _iter_scan_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SCAN_EXTENSIONS:
            continue
        if any(part in _SCAN_SKIP_DIR_NAMES for part in path.parts):
            continue
        paths.append(path)
    return paths


def _format_refusals(refusals_by_code: dict[str, int]) -> str:
    if not refusals_by_code:
        return "REFUSALS: none"
    parts = [f"{code}={count}" for code, count in sorted(refusals_by_code.items())]
    return "REFUSALS: " + ",".join(parts)


def _format_verdict(summary: object) -> str:
    verdict = getattr(summary, "verdict")
    if verdict == "GO":
        return "VERDICT: GO"
    halt_code = getattr(summary, "halt_code")
    if halt_code:
        return f"VERDICT: HOLD ({halt_code})"
    if getattr(summary, "units_refused"):
        return "VERDICT: HOLD (refused units)"
    # HOLD with no halt and no refusal: every unit abstained or was excluded for a missing
    # reference, so nothing was ever admitted. Not specified verbatim by the interface this file
    # was built against; named here rather than left as a bare "VERDICT: HOLD".
    return "VERDICT: HOLD (no admitted units)"


def _cmd_run(args: argparse.Namespace) -> int:
    tracker = get_tracker(args.mlflow, args.mlflow_experiment)
    out_dir = Path(args.out) if args.out else None
    summary = run_measurement(
        units_path=Path(args.units),
        policy_path=Path(args.policy),
        out_dir=out_dir,
        allow_nonsynthetic=args.allow_nonsynthetic,
        tracker=tracker,
    )
    if not args.quiet:
        print(denominator_line(summary))
        print(_format_refusals(summary.refusals_by_code))
        halt = halt_line(summary)
        if halt is not None:
            # Where the run stopped, on stdout, beside the counts it stopped in the middle of.
            print(halt)
        print(_format_verdict(summary))
    return 0 if summary.verdict == "GO" else 2


def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root)
    paths = _iter_scan_paths(root)
    counts = scan_paths_for_leaks(paths)
    hit = False
    for path_str in sorted(counts):
        count = counts[path_str]
        if count:
            hit = True
            print(f"{path_str}={count}")
    return 2 if hit else 0


def _cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="failclosed-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a measurement admission pass.")
    run_parser.add_argument("--units", required=True, help="Path to a JSONL units file.")
    run_parser.add_argument("--policy", required=True, help="Path to a JSON policy file.")
    run_parser.add_argument(
        "--out", default=None, help="Directory to write summary.json / trace.jsonl / halt.json."
    )
    run_parser.add_argument("--allow-nonsynthetic", action="store_true", default=False)
    run_parser.add_argument("--mlflow", action="store_true", default=False)
    run_parser.add_argument("--mlflow-experiment", default="failclosed-eval")
    run_parser.add_argument("--quiet", action="store_true", default=False)
    run_parser.set_defaults(func=_cmd_run)

    scan_parser = subparsers.add_parser(
        "scan", help="Scan text files under --root for value-carrying label leaks."
    )
    scan_parser.add_argument("--root", default=".")
    scan_parser.set_defaults(func=_cmd_scan)

    version_parser = subparsers.add_parser("version", help="Print the package version.")
    version_parser.set_defaults(func=_cmd_version)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse's own exit codes (0 for --help, 2 for a parse error) collapse to this CLI's
        # "bad usage" code, except a genuine --help stays 0.
        return 0 if exc.code in (0, None) else 1

    try:
        return args.func(args)
    except Exception as exc:  # the boundary's default is refusal, not a silent crash
        print(f"VERDICT: HOLD (UNEXPECTED_ERROR): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
