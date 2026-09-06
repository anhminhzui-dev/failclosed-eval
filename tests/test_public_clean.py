"""Guards CONTRACT.md section 12's public-clean row and the source system's value-carrying-label law:
every fixture is honestly synthetic except the one deliberate negative case that exists to
prove the NOT_SYNTHETIC halt works; the shipped source carries zero label leaks outside
fixtures/; the rubric is exactly the pinned four criteria; and rubric.py's prose carries no
digit-bearing rubric text (a numbered descriptor would make it look like a paraphrase of a
commercial rubric, which row 9 of EXTRACTION_PLAN.md section 7 forbids)."""
from __future__ import annotations

import json
from pathlib import Path

from failclosed_eval import CRITERIA, count_label_leaks

# bad_not_synthetic.jsonl is EXCLUDED from the blanket synthetic:true check on purpose: its
# entire reason for existing is to carry one row with synthetic:false, seeded so the
# NOT_SYNTHETIC halt (tested in test_seeded_negatives.py) has something real to catch. A
# fixture built to fail a check is not the same thing as an accidental real-data leak.
_NOT_SYNTHETIC_NEGATIVE_FIXTURE = "bad_not_synthetic.jsonl"


def test_every_fixture_row_is_synthetic_except_the_seeded_negative_case(fixtures_dir) -> None:
    """Guards: the shipped package cannot silently ingest real data - every row in every
    fixture is explicitly marked synthetic, except the one row built to prove the halt that
    catches a row that is not."""
    for path in sorted(fixtures_dir.glob("*.jsonl")):
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if path.name == _NOT_SYNTHETIC_NEGATIVE_FIXTURE:
            assert any(r.get("synthetic") is not True for r in rows), (
                "the seeded-negative fixture must actually carry its one non-synthetic row"
            )
            continue
        assert all(r.get("synthetic") is True for r in rows), f"{path.name} has a non-synthetic row"


def test_label_leak_scan_over_shipped_py_and_md_outside_fixtures_is_zero() -> None:
    """Guards: the label firewall must return zero on the compliant tree it is meant to
    protect - a bare-word or fragment-assembled test string must never leak into the actual
    source text of a shipped file (see test_seeded_negatives.py for the positive control that
    proves this same scan CAN report non-zero).

    This IS the repository-scanning path (it reads this package's own committed .py/.md files,
    not untrusted grader input), so it is one of the two call sites allowed to pass
    honour_exemption=True - the README has to spell out example leaks on lines carrying the
    anchor token in order to explain the pattern, same as scan_paths_for_leaks (R1, round-2
    hostile review)."""
    repo_root = Path(__file__).resolve().parents[1]
    total = 0
    hits = {}
    for pattern in ("*.py", "*.md"):
        for path in repo_root.rglob(pattern):
            if "fixtures" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="strict")
            count = count_label_leaks(text, honour_exemption=True)
            if count:
                hits[str(path)] = count
            total += count
    assert total == 0, f"label leaks found outside fixtures/: {hits}"


def test_criteria_has_exactly_the_four_pinned_names() -> None:
    """Guards: the rubric is exactly CORRECTNESS, COMPLETENESS, CLARITY, EVIDENCE - no fifth
    criterion, no renamed criterion, no commercial-descriptor name."""
    assert CRITERIA == ("CORRECTNESS", "COMPLETENESS", "CLARITY", "EVIDENCE")


def test_rubric_module_prose_contains_no_digit_bearing_rubric_text() -> None:
    """Guards EXTRACTION_PLAN.md section 7 row 9: a rubric that describes its criteria with
    numbered levels would read as a paraphrase of a commercial band-descriptor rubric. The
    module docstring and the four criterion questions must be pure, numberless prose; only the
    scale-bound constants (LEVEL_MIN/MAX/STEP) may carry digits, and those are not descriptive
    text about what a response at any given level looks like."""
    from failclosed_eval import rubric, CRITERION_QUESTIONS

    assert rubric.__doc__ is not None
    assert not any(ch.isdigit() for ch in rubric.__doc__), "rubric.py's module docstring carries a digit"
    for criterion, question in CRITERION_QUESTIONS.items():
        assert not any(ch.isdigit() for ch in question), f"{criterion} question carries a digit"
