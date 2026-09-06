"""Guards CONTRACT.md section 11: each bad fixture is clean_units.jsonl with exactly one
defect, so each test proves exactly one gate and nothing else. A gate that has never been
shown to fail cannot certify a clean result - this file is that proof, one test per gate,
plus a positive control on the label-leak detector itself."""
from __future__ import annotations

from failclosed_eval import count_label_leaks, run


def test_clean_units_gives_go(fixtures_dir) -> None:
    """Guards: the baseline this whole file edits away from must itself pass, or every
    'exactly one edit' claim below is meaningless."""
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "GO"
    assert summary.halt_code is None


def test_bad_missing_image_refuses_input_image_required(fixtures_dir) -> None:
    """Guards: a figure item with no image source is refused, not silently admitted - the CI
    must-refuse case."""
    summary = run(fixtures_dir / "bad_missing_image.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code is None
    assert summary.refusals_by_code == {"INPUT_IMAGE_REQUIRED": 1}
    assert summary.units_refused == 1


def test_bad_missing_instruction_refuses_missing_instruction(fixtures_dir) -> None:
    """Guards: a text item with a blank instruction is refused - it cannot be graded against
    nothing."""
    summary = run(fixtures_dir / "bad_missing_instruction.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code is None
    assert summary.refusals_by_code == {"MISSING_INSTRUCTION": 1}
    assert summary.units_refused == 1


def test_bad_label_leak_refuses_label_leak_in_prompt(fixtures_dir) -> None:
    """Guards: a value-carrying label appended to an instruction is refused before it ever
    reaches a grader."""
    summary = run(fixtures_dir / "bad_label_leak.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code is None
    assert summary.refusals_by_code == {"LABEL_LEAK_IN_PROMPT": 1}
    assert summary.units_refused == 1


def test_bad_anomalous_halts_anomalous_estimate(fixtures_dir) -> None:
    """Guards: a value at the floor with high sub-value evidence halts the whole run - a
    broken measurement is not a low one."""
    summary = run(fixtures_dir / "bad_anomalous.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code == "ANOMALOUS_ESTIMATE"


def test_bad_uniform_halts_anomalous_distribution(fixtures_dir) -> None:
    """Guards: one value holding an outsized share of a criterion's rows halts on the
    distribution check before the (also-true) missing-denominator check ever runs - the
    anomaly check runs first, so this is the reported code, per CONTRACT.md section 7.1."""
    summary = run(fixtures_dir / "bad_uniform.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code == "ANOMALOUS_DISTRIBUTION"


def test_bad_duplicate_halts_duplicate_unit(fixtures_dir) -> None:
    """Guards: the same (item_id, criterion) pair appearing twice halts - a unit is measured
    exactly once."""
    summary = run(fixtures_dir / "bad_duplicate.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code == "DUPLICATE_UNIT"


def test_bad_not_synthetic_halts_not_synthetic(fixtures_dir) -> None:
    """Guards the public-clean guard: a row lacking synthetic:true halts the run rather than
    silently being ingested - the shipped package cannot silently admit real data."""
    summary = run(fixtures_dir / "bad_not_synthetic.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code == "NOT_SYNTHETIC"


def test_bad_estimate_value_halts_invalid_estimate_value(fixtures_dir) -> None:
    """Guards D1: a malformed element inside `estimates` is the most likely malformed field in
    the whole record, because it is the untrusted grader's own output. Before this fixture
    existed it escaped the typed refusal system entirely and crashed out as an unnamed
    UNEXPECTED_ERROR at exit 1; it must now halt with the code the README already documents."""
    summary = run(fixtures_dir / "bad_estimate_value.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "HOLD"
    assert summary.halt_code == "INVALID_ESTIMATE_VALUE"
    assert summary.halt_unit_id is not None


def test_bad_estimate_value_exits_two_through_the_cli(fixtures_dir, capsys) -> None:
    """Guards D1 end to end: the process boundary must report the named halt at exit 2, not the
    catch-all unexpected-error path at exit 1."""
    from failclosed_eval.cli import main

    code = main(
        [
            "run",
            "--units",
            str(fixtures_dir / "bad_estimate_value.jsonl"),
            "--policy",
            str(fixtures_dir / "policy.json"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "VERDICT: HOLD (INVALID_ESTIMATE_VALUE)" in out
    assert "UNEXPECTED_ERROR" not in out


def test_label_leak_detector_can_itself_fail_on_a_constructed_positive() -> None:
    """Guards: 'a scan that has not been shown to fail cannot certify a clean result' - this
    constructs a positive from fragments (never the literal contiguous banned word in this
    source file) and asserts the detector actually reports a hit."""
    word = "lev" + "el"
    positive = word + "_" + "score" + ": 9"
    assert count_label_leaks(positive) > 0
