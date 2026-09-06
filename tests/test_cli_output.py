"""What the operator actually sees on a halt.

Defect D4 in the hostile review: a halted run printed a clean-looking table. Every criterion showed
`refused=0` above a HOLD line, `REFUSALS: none` sat where the reason should have been, and
`halt_unit_id` - which names the offending unit and was already being written into summary.json -
never reached stdout at all. The operator was told the run stopped and not told where.

Defect D7, same surface: the counts were one pipe-joined line that wrapped into an unreadable block
on an ordinary terminal.

Both are output-shape defects, so both are tested here against real CLI output rather than against
the summary object.
"""
from __future__ import annotations

import pytest

from failclosed_eval import denominator_line, halt_line, run
from failclosed_eval.cli import main


def _cli(fixtures_dir, fixture_name, capsys):
    code = main(
        [
            "run",
            "--units",
            str(fixtures_dir / fixture_name),
            "--policy",
            str(fixtures_dir / "policy.json"),
        ]
    )
    return code, capsys.readouterr().out


# --- D4: a halt says where it halted -----------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name,halt_code",
    [
        ("bad_duplicate.jsonl", "DUPLICATE_UNIT"),
        ("bad_anomalous.jsonl", "ANOMALOUS_ESTIMATE"),
        ("bad_estimate_value.jsonl", "INVALID_ESTIMATE_VALUE"),
    ],
)
def test_a_unit_scoped_halt_prints_the_halting_unit_id(fixtures_dir, capsys, fixture_name, halt_code) -> None:
    """Guards D4: the unit that stopped the run has to be on stdout, not only in a file the
    operator has not been told to open."""
    code, out = _cli(fixtures_dir, fixture_name, capsys)
    summary = run(fixtures_dir / fixture_name, fixtures_dir / "policy.json")

    assert code == 2
    assert summary.halt_unit_id, "this fixture is meant to halt on a specific unit"
    assert f"HALT: {halt_code} unit_id={summary.halt_unit_id}" in out


def test_a_run_level_halt_says_so_instead_of_printing_an_empty_field(fixtures_dir, capsys) -> None:
    """Guards the other side of D4: not every halt belongs to one unit, and a blank field would
    read as a missing value rather than as a run-level stop."""
    code, out = _cli(fixtures_dir, "bad_uniform.jsonl", capsys)
    assert code == 2
    assert "HALT: ANOMALOUS_DISTRIBUTION unit_id=none (halt is not unit-scoped)" in out


def test_a_halted_run_marks_its_counts_partial(fixtures_dir, capsys) -> None:
    """Guards D4: the counts printed above a halt are honest as far as they go and stop where the
    halt stopped. Saying so is the difference between a partial count and a wrong one."""
    _, out = _cli(fixtures_dir, "bad_duplicate.jsonl", capsys)
    assert "DENOMINATORS: PARTIAL" in out


def test_a_clean_run_does_not_claim_partial_and_prints_no_halt_line(fixtures_dir, capsys) -> None:
    """Guards against the cure over-firing: a run that completed must not be labelled partial, and
    must not print a halt line at all."""
    code, out = _cli(fixtures_dir, "clean_units.jsonl", capsys)
    assert code == 0
    assert "PARTIAL" not in out
    assert "HALT:" not in out
    assert "VERDICT: GO" in out


def test_halt_line_is_none_when_nothing_halted(fixtures_dir) -> None:
    """Guards the function contract behind the CLI behaviour above."""
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json")
    assert halt_line(summary) is None


# --- D7: one row per criterion ------------------------------------------------------------------


def test_denominators_print_one_row_per_criterion(fixtures_dir) -> None:
    """Guards D7: four criteria, four rows, plus a header - not one 300-character line that wraps
    into a block nobody can line up by eye."""
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json")
    rows = denominator_line(summary).splitlines()
    assert len(rows) == 5
    assert rows[0].startswith("DENOMINATORS: ")
    for row, criterion in zip(rows[1:], ("CORRECTNESS", "COMPLETENESS", "CLARITY", "EVIDENCE")):
        assert row.lstrip().startswith(criterion)
        for field in ("n=", "weight=", "refused=", "abstained=", "reference_excluded="):
            assert field in row


def test_no_denominator_row_is_wider_than_an_ordinary_terminal(fixtures_dir) -> None:
    """Guards the reason the shape changed: every row has to fit in 80 columns, or the wrapping is
    back and the rows were cosmetic."""
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json")
    for row in denominator_line(summary).splitlines()[1:]:
        assert len(row) <= 80, row
