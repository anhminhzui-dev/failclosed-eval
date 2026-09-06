"""R2 in the round-2 hostile review: every CLI block in README.md omitted `PYTHONPATH=src`, so
the first thing a reviewer does - paste the first command - failed with `ModuleNotFoundError:
No module named 'failclosed_eval'`, because the package lives under `src/` and is never
installed by these examples. CI never caught it because the workflow sets `PYTHONPATH: src` as a
job-level environment variable, so nothing in CI ever runs the README's own text.

This file extracts every fenced shell block from README.md and asserts that any command line
invoking the package (directly via `-m failclosed_eval...`, or via a script under `scripts/`)
either carries the `PYTHONPATH=` prefix inline or runs after a `PYTHONPATH=` / `export
PYTHONPATH=` line earlier in the same fence - the two shapes README.md actually uses ("Run it").
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"

# Anything a fenced block might run that touches the package or a repo script - the shape R2's
# fix must cover. `python` itself is required alongside one of these, so a stray mention of
# "failclosed_eval" in prose outside a code fence is never in scope here (this file only looks
# inside fences to begin with).
_INVOKES_PACKAGE = ("failclosed_eval", "scripts/forbidden_scan.py", "scripts/make_fixtures.py")


def _shell_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    return re.findall(r"```(?:bash|console|sh)\n(.*?)```", text, re.DOTALL)


def test_readme_has_extractable_shell_blocks() -> None:
    """Guards the extraction itself: if this returns nothing, every assertion below is
    vacuously true and proves nothing."""
    blocks = _shell_blocks()
    assert len(blocks) >= 4, "expected at least the four package/script-invoking bash/console blocks"


def test_every_readme_command_that_invokes_the_package_carries_pythonpath() -> None:
    """Guards R2 directly: a command line that runs `python -m failclosed_eval...` or a script
    under `scripts/` must set PYTHONPATH=src inline, or the block must have already set it on an
    earlier line - otherwise a straight copy-paste reproduces the ModuleNotFoundError this fix
    closes."""
    blocks = _shell_blocks()
    checked_any = False

    for block in blocks:
        pythonpath_seen = False
        for raw_line in block.splitlines():
            line = raw_line[1:].strip() if raw_line.startswith("$") else raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("PYTHONPATH=") or line.startswith("export PYTHONPATH="):
                pythonpath_seen = True
            if "python" in line and any(marker in line for marker in _INVOKES_PACKAGE):
                checked_any = True
                assert pythonpath_seen, (
                    f"README command invokes the package without PYTHONPATH=src set first: "
                    f"{raw_line!r}"
                )

    assert checked_any, "no package-invoking command line was found to check - extraction regressed"


def test_readme_states_the_pythonpath_setup_before_the_first_run_command() -> None:
    """Guards: the fix has to be a section a reviewer reads BEFORE the first command, not a
    trailing footnote. `PYTHONPATH=src` must appear in the README text strictly before the first
    `-m failclosed_eval` invocation."""
    text = README.read_text(encoding="utf-8")
    pythonpath_pos = text.find("PYTHONPATH=src")
    first_run_pos = text.find("-m failclosed_eval")
    assert pythonpath_pos != -1, "PYTHONPATH=src never appears in the README at all"
    assert first_run_pos != -1, "no `-m failclosed_eval` invocation found in the README"
    assert pythonpath_pos < first_run_pos


def test_the_documented_pythonpath_prefix_actually_resolves_the_import() -> None:
    """Guards the claim end to end, not just by pattern-matching the text: run the README's own
    clean-run example as a fresh subprocess with PYTHONPATH=src set exactly as documented, from
    the repository root, exactly as a reviewer who copy-pasted the line would - and confirm it is
    ModuleNotFoundError without that prefix, which is the failure R2 closes."""
    base_cmd = [
        sys.executable,
        "-m",
        "failclosed_eval.cli",
        "run",
        "--units",
        "fixtures/clean_units.jsonl",
        "--policy",
        "fixtures/policy.json",
    ]

    env_without_path = os.environ.copy()
    env_without_path.pop("PYTHONPATH", None)
    without = subprocess.run(
        base_cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=env_without_path
    )
    assert "ModuleNotFoundError" in without.stderr

    env_with_path = os.environ.copy()
    env_with_path["PYTHONPATH"] = "src"
    with_path = subprocess.run(
        base_cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=env_with_path
    )
    assert "VERDICT: GO" in with_path.stdout
    assert with_path.returncode == 0
