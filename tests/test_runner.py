"""Guards CONTRACT.md section 7 (runner.py): the clean fixture must produce a GO verdict with
the pinned counts; the denominator line must name every exclusion class out loud; the trace
must carry exactly six keys and never a measurement value; out_dir must write summary.json and
trace.jsonl always, and halt.json only on a halt."""
from __future__ import annotations

import json

from failclosed_eval import denominator_line, run


def test_clean_fixture_returns_go_with_pinned_counts(fixtures_dir) -> None:
    """Guards: 8 selected, 8 admitted, 0 refused, verdict GO, no halt - the whole point of
    shipping a clean fixture is that it actually passes."""
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json")
    assert summary.verdict == "GO"
    assert summary.halt_code is None
    assert summary.units_selected == 8
    assert summary.units_admitted == 8
    assert summary.units_refused == 0
    assert summary.units_abstained == 0
    assert summary.criteria_without_denominator == []


def test_denominator_line_names_every_exclusion_class(fixtures_dir) -> None:
    """Guards: a number is never printed without saying what it is out of - every criterion
    and every exclusion class (refused, abstained, reference_excluded) appears by name."""
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json")
    line = denominator_line(summary)
    assert line.startswith("DENOMINATORS: ")
    for criterion in ("CORRECTNESS", "COMPLETENESS", "CLARITY", "EVIDENCE"):
        assert criterion in line
    for exclusion in ("refused=", "abstained=", "reference_excluded=", "n=", "weight="):
        assert exclusion in line


def test_trace_has_exactly_six_keys_and_no_measurement_value(fixtures_dir, tmp_path) -> None:
    """Guards: the trace proves which bytes produced a unit without republishing what the unit
    was worth - exactly six keys, no estimate/reference/component/weight value anywhere."""
    forbidden_keys = {"estimate", "reference", "components", "component_evidence", "weight"}
    out_dir = tmp_path / "run1"
    run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json", out_dir=out_dir)
    trace_path = out_dir / "trace.jsonl"
    lines = [json.loads(l) for l in trace_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 8
    expected_keys = {"unit_id", "criterion", "state", "code", "input_sha256", "image_sha256"}
    for row in lines:
        assert set(row.keys()) == expected_keys
        assert not (set(row.keys()) & forbidden_keys)
        assert row["state"] in {"admitted", "refused", "abstained", "excluded_reference"}


def test_out_dir_writes_summary_and_trace_and_no_halt_json_on_go(fixtures_dir, tmp_path) -> None:
    """Guards: a GO run writes summary.json and trace.jsonl, and does not leave a stale
    halt.json behind - a clean run must not look like a broken one."""
    out_dir = tmp_path / "run_go"
    run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json", out_dir=out_dir)
    assert (out_dir / "summary.json").is_file()
    assert (out_dir / "trace.jsonl").is_file()
    assert not (out_dir / "halt.json").is_file()


def test_halt_writes_halt_json(fixtures_dir, tmp_path) -> None:
    """Guards: a halted run writes halt.json naming the code and unit - a halt trace is
    written as a file, never swallowed."""
    out_dir = tmp_path / "run_halt"
    summary = run(fixtures_dir / "bad_not_synthetic.jsonl", fixtures_dir / "policy.json", out_dir=out_dir)
    assert summary.verdict == "HOLD"
    assert summary.halt_code == "NOT_SYNTHETIC"
    halt_path = out_dir / "halt.json"
    assert halt_path.is_file()
    halt = json.loads(halt_path.read_text(encoding="utf-8"))
    assert halt["code"] == "NOT_SYNTHETIC"


def test_run_never_raises_failclosederror_on_any_bad_fixture(fixtures_dir) -> None:
    """Guards: run() catches every halt internally and reports it on the summary - a halt is
    reported as HOLD, never propagated as an exception a caller must remember to catch."""
    for name in (
        "bad_missing_image.jsonl",
        "bad_missing_instruction.jsonl",
        "bad_label_leak.jsonl",
        "bad_anomalous.jsonl",
        "bad_uniform.jsonl",
        "bad_duplicate.jsonl",
        "bad_not_synthetic.jsonl",
    ):
        summary = run(fixtures_dir / name, fixtures_dir / "policy.json")
        assert summary.verdict == "HOLD"
