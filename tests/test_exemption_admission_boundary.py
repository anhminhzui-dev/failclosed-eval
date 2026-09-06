"""R1 in the round-2 hostile review: the exemption anchor `LEAK_EXEMPT_ANCHOR` switched the
flagship label-leak refusal off inside the LIVE ADMISSION PATH, not only inside the repository's
own self-scan where the exemption is legitimate. `count_label_leaks` served both callers through
one unconditional skip, so an instruction carrying a real value-carrying label plus the anchor
token was admitted with `VERDICT: GO` and zero refusals - reproduced end to end through the CLI
before this fix landed (see FIX_REPORT_r2.md for the before/after transcript).

The cure is `honour_exemption: bool = False` on `count_label_leaks` (validators.py). Only
`scan_paths_for_leaks` - the repository-scanning path that reads this package's own committed
documentation - passes `honour_exemption=True`. `scan_text_for_leaks`, the function every
untrusted instruction and response passes through inside `build_payload`, never does. This file
proves both directions: the admission path still refuses a leak that carries the anchor, and the
repo-scan path still exempts the README's own explanatory lines.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from failclosed_eval import LEAK_EXEMPT_ANCHOR, run, scan_paths_for_leaks
from failclosed_eval.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]

# Never written as the literal contiguous word in this source file - the same convention every
# other test file in this suite uses for a real value-carrying label.
_LEAK_WORD = "b" + "and"


def _write_leaking_units_file(fixtures_dir: Path, tmp_path: Path) -> Path:
    """A copy of the shipped `clean_units.jsonl` (one row per criterion, so every criterion still
    gets a denominator and the refusal is the only thing under test) with the leak-plus-anchor
    line appended to exactly one row's instruction - the same shape the FIX_REPORT_r2.md manual
    repro uses."""
    rows = [
        json.loads(line)
        for line in (fixtures_dir / "clean_units.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    leak_line = f"The target {_LEAK_WORD} 6 was awarded. {LEAK_EXEMPT_ANCHOR}"
    injected = False
    for row in rows:
        if row["item_id"] == "syn-002":
            row["instruction"] = row["instruction"] + " " + leak_line
            injected = True
            break
    assert injected, "clean_units.jsonl no longer has a syn-002 row to inject the leak into"

    units_path = tmp_path / "leaking_units.jsonl"
    units_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return units_path


# --- (a) the admission path must still refuse, anchor or not -----------------------------------


def test_admission_path_still_refuses_a_leak_that_also_carries_the_anchor_token(
    fixtures_dir, tmp_path
) -> None:
    """Guards R1 at the `run()` level: the same entry point the CLI and every worker calls must
    refuse a leak, not admit it, when the leaking instruction also carries the exemption anchor.
    Before this fix this returned VERDICT: GO with zero refusals."""
    units_path = _write_leaking_units_file(fixtures_dir, tmp_path)
    summary = run(units_path, fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code is None
    assert summary.refusals_by_code == {"LABEL_LEAK_IN_PROMPT": 1}
    assert summary.units_refused == 1


def test_admission_path_refuses_through_the_cli_at_exit_two(fixtures_dir, tmp_path) -> None:
    """Guards R1 end to end through the process boundary a reviewer actually runs - the same
    shape test_seeded_negatives.py uses for every other seeded defect (exit 2, named code on
    stdout, VERDICT: HOLD)."""
    units_path = _write_leaking_units_file(fixtures_dir, tmp_path)
    code = main(
        [
            "run",
            "--units",
            str(units_path),
            "--policy",
            str(fixtures_dir / "policy.json"),
        ]
    )
    assert code == 2


def test_admission_path_prints_the_named_refusal_code(fixtures_dir, tmp_path, capsys) -> None:
    """Guards the same case at the printed-output level, matching how a reviewer would actually
    see it: LABEL_LEAK_IN_PROMPT on stdout, VERDICT: HOLD, not VERDICT: GO."""
    units_path = _write_leaking_units_file(fixtures_dir, tmp_path)
    main(["run", "--units", str(units_path), "--policy", str(fixtures_dir / "policy.json")])
    out = capsys.readouterr().out
    assert "LABEL_LEAK_IN_PROMPT=1" in out
    assert "VERDICT: GO" not in out


# --- (b) the repo-scan path must still exempt the README's own explanatory lines ---------------


def test_repo_scan_path_still_exempts_the_readmes_own_explanatory_lines() -> None:
    """Guards the other direction: the fix must not remove the legitimate exemption from the
    repository-scanning path. README.md spells out several value-carrying examples on purpose, on
    lines that also carry the anchor token; scan_paths_for_leaks (the only caller that passes
    honour_exemption=True) must still return 0 for that file."""
    readme = REPO_ROOT / "README.md"
    counts = scan_paths_for_leaks([readme])
    assert counts == {readme.as_posix(): 0}


def test_repo_scan_of_the_shipped_tree_is_clean() -> None:
    """Guards scripts/forbidden_scan.py (the CI-facing repo scan) end to end as a subprocess,
    exactly as CI runs it, so an import-time regression cannot hide behind an in-process call:
    with the copyright holder filled in (the owner's step, done at publication), the shipped tree
    reports nothing - not the licence, not the project metadata, and nothing from the README's own
    exemption-anchored explanatory lines. The scanner's ability to catch an unfilled placeholder is
    proven separately on a throwaway tree, never on the shipped one."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "forbidden_scan.py"), "--root", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert lines == ["SCAN: clean"], result.stdout
