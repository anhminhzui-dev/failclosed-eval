"""The reference value is admitted, validated, and then goes nowhere.

Defect D5 in the hostile review: `reference` is collected, checked for finiteness, stored on
`AdmittedUnit` - and read by nothing. Grepping `.reference` across `src/` returned one hit and it
was the field declaration. That is consistent with claiming no accuracy, but the code gave no
signal that the omission was deliberate, so it read as an unfinished feature.

It is a boundary. Comparing an estimate against a reference is how an accuracy figure is made, and
an accuracy figure computed over invented fixtures would be a number about invented data wearing
the clothes of a result. This file is the boundary's enforcement: no reference value may reach any
file the package writes, on any path, clean or halted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from failclosed_eval import run

_FIXTURES = (
    "clean_units.jsonl",
    "bad_missing_image.jsonl",
    "bad_duplicate.jsonl",
    "bad_estimate_value.jsonl",
    "bad_anomalous.jsonl",
)

_FORBIDDEN_KEYS = {"estimate", "reference", "components", "component_evidence", "weight"}

# Every key an output file is allowed to carry a NUMBER under. All of them are counts of units or
# a summed weight, and every one of them says what it is out of. A number appearing under any other
# key is the failure this file exists to catch, and matching by value alone would not catch it: a
# count of 2 and a reference of 2.0 are the same digit and completely different things.
_COUNT_KEYS = {
    "selected",
    "admitted",
    "refused",
    "abstained",
    "missing_reference",
    "effective_weight",
    "units_selected",
    "units_admitted",
    "units_refused",
    "units_abstained",
    "units_missing_reference",
}

# Refusal tallies are keyed by refusal code, so their keys are codes rather than field names.
_CODE_SHAPED = "refusals_by_code"


def _reference_values(path: Path) -> set[float]:
    values = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ref = row.get("reference")
        if isinstance(ref, (int, float)):
            values.add(float(ref))
    return values


def _walk(node):
    """Every (key, value) pair anywhere in a parsed JSON document."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


@pytest.mark.parametrize("fixture_name", _FIXTURES)
def test_no_output_file_carries_a_reference_value(fixtures_dir, tmp_path, fixture_name) -> None:
    """Guards D5 on every written file, not only the trace: summary.json, trace.jsonl and
    halt.json are each read back and checked for the actual reference numbers the input carried."""
    units = fixtures_dir / fixture_name
    out_dir = tmp_path / fixture_name.replace(".", "_")
    run(units, fixtures_dir / "policy.json", out_dir=out_dir)

    references = _reference_values(units)
    assert references, "the fixture must actually carry reference values or this proves nothing"

    for written in sorted(out_dir.iterdir()):
        raw = written.read_text(encoding="utf-8")
        documents = (
            [json.loads(l) for l in raw.splitlines() if l.strip()]
            if written.suffix == ".jsonl"
            else [json.loads(raw)]
        )
        for document in documents:
            tally_codes = set(document.get(_CODE_SHAPED, {})) if isinstance(document, dict) else set()
            for key, value in _walk(document):
                assert key not in _FORBIDDEN_KEYS, f"{written.name} carries the key {key}"
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                assert key in _COUNT_KEYS or key in tally_codes, (
                    f"{written.name} carries the number {value} under the key {key}, which is not a "
                    f"declared count - references present in this fixture: {sorted(references)}"
                )


def test_a_count_named_reference_is_still_allowed_because_it_is_a_count(fixtures_dir, tmp_path) -> None:
    """Guards the cure against over-firing: the exclusion COUNT is named `missing_reference` and
    has to survive - the ban is on the measured value, not on the word. A count is an integer and
    says what it is out of; that is the opposite of a leaked value."""
    out_dir = tmp_path / "counts"
    run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json", out_dir=out_dir)
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert isinstance(summary["units_missing_reference"], int)
    for counts in summary["criteria"].values():
        assert isinstance(counts["missing_reference"], int)


def test_the_source_reads_the_reference_field_nowhere(  ) -> None:
    """Guards the boundary at the source level: if a future change starts USING the reference, this
    test fails and whoever made the change has to say so out loud, in the README, before an
    accuracy claim can quietly appear."""
    src = Path(__file__).resolve().parents[1] / "src" / "failclosed_eval"
    attribute = "." + "reference"
    offenders = []
    for path in sorted(src.glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "reads `" in stripped:
                continue
            if attribute in stripped and "missing_reference" not in stripped:
                offenders.append(f"{path.name}:{number}: {stripped}")
    assert offenders == [], offenders


def test_the_trace_carries_no_number_at_all(fixtures_dir, tmp_path) -> None:
    """Guards the strongest form of the boundary on the file most likely to be shared: a trace row
    proves WHICH BYTES produced a unit and says nothing about what the unit was worth, so it has no
    numeric field of any kind to leak one through."""
    out_dir = tmp_path / "trace_only"
    run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json", out_dir=out_dir)
    rows = [
        json.loads(l)
        for l in (out_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    assert rows
    for row in rows:
        assert set(row) == {
            "unit_id",
            "criterion",
            "state",
            "code",
            "input_sha256",
            "image_sha256",
        }
        for _key, value in _walk(row):
            assert not isinstance(value, (int, float)), row
