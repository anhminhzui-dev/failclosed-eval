"""Guards CONTRACT.md section 6 (validators.py): every refusal code that a bad but well-formed
record can trigger, every halt code raised by the admission helpers, the image slot invariant
(always present, empty or not, last message is always the image), and the label-leak regex's
seven pinned cases - built from string fragments so this file never contains the literal
value-carrying pattern it is proving the detector catches."""
from __future__ import annotations

import math

import pytest

from failclosed_eval import (
    HaltError,
    LEAK_EXEMPT_ANCHOR,
    POLICY_FIELDS,
    Policy,
    RefusalError,
    build_payload,
    check_anomalies,
    component_evidence,
    count_label_leaks,
    read_policy,
    read_units,
    unit_weight,
    validate_unit,
)

_PNG_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
    "z8DwHwAFgAI/9GGnOwAAAABJRU5ErkJggg=="
)


def _figure_record(**overrides):
    record = {
        "synthetic": True,
        "item_id": "t-fig-1",
        "criterion": "clarity",
        "item_type": "figure",
        "response_text": "A synthetic response about a synthetic figure.",
        "instruction": "Describe the figure.",
        "image_data_uri": _PNG_DATA_URI,
        "estimates": [3.0, 3.0],
        "reference": 3.0,
        "component_evidence": [3.0, 3.0],
        "weight": 1.0,
    }
    record.update(overrides)
    return record


def _text_record(**overrides):
    record = {
        "synthetic": True,
        "item_id": "t-txt-1",
        "criterion": "clarity",
        "item_type": "text",
        "response_text": "A synthetic response about a synthetic instruction.",
        "instruction": "Assess the response.",
        "estimates": [3.0, 3.0],
        "reference": 3.0,
        "component_evidence": [3.0, 3.0],
        "weight": 1.0,
    }
    record.update(overrides)
    return record


# --- 6.3 label-leak regex: seven pinned cases, assembled from fragments -----------------------

_LEAK_WORD = "lev" + "el"  # never written as the literal contiguous word in this source file
_MET_WORD = "UN" + "MET"

LEAK_CASES = [
    (_LEAK_WORD + ": 3", 1),
    ('{"' + _LEAK_WORD + '": 3}', 1),
    ("item_" + _LEAK_WORD + "5", 1),
    ("the " + _LEAK_WORD + " of detail is good", 0),
    ("You must never output a " + _LEAK_WORD + " or a score.", 0),
    (_MET_WORD + ": x", 1),
    # R1 (round-2 hostile review): the bare/default call is what the admission path uses, and it
    # must NOT honour the exemption anchor - a real leak still counts even with the anchor glued
    # on. Only an explicit honour_exemption=True (the repo-scan path) skips it - see the dedicated
    # test below.
    (_LEAK_WORD + ": 3 " + LEAK_EXEMPT_ANCHOR, 1),
]


@pytest.mark.parametrize("text,expected_count", LEAK_CASES)
def test_count_label_leaks_pinned_cases(text, expected_count) -> None:
    """Guards the source system's own lesson: only a value-carrying label counts, a bare word does not,
    and by default (the admission path's own call shape) a line carrying the exemption anchor is
    NOT skipped - each of the seven pinned shapes."""
    assert count_label_leaks(text) == expected_count


def test_count_label_leaks_honours_the_exemption_only_when_explicitly_asked() -> None:
    """Guards R1 directly: the exemption anchor switches the leak gate off only for a caller that
    explicitly opts in with honour_exemption=True (the repo-scan path, e.g. scan_paths_for_leaks)
    - never for the default call shape scan_text_for_leaks (the live admission path) uses."""
    text = _LEAK_WORD + ": 3 " + LEAK_EXEMPT_ANCHOR
    assert count_label_leaks(text) == 1
    assert count_label_leaks(text, honour_exemption=True) == 0


def test_label_leak_detector_can_fail_on_a_constructed_positive() -> None:
    """Guards: a detector that has never been shown to fail cannot certify a clean result -
    this constructs a positive from fragments and asserts the count is non-zero."""
    positive = _LEAK_WORD + "_" + "score" + ": 4"
    assert count_label_leaks(positive) > 0


# --- 6.7 build_payload: image slot invariant ---------------------------------------------------


def test_build_payload_always_carries_image_slot_as_the_last_message() -> None:
    """Guards: the image slot is present even for a text item (empty, but present) and it is
    always the last message - a caller cannot forget to send it, only be refused for omitting it."""
    payload = build_payload(_text_record())
    assert isinstance(payload["image_slot"], dict)
    assert payload["messages"][-1]["type"] == "input_image"
    assert payload["image_slot"]["sha256"] is None
    assert payload["image_slot"]["required"] is False


def test_build_payload_figure_image_slot_carries_the_image_hash() -> None:
    """Guards: a figure item's image slot carries a non-null sha256 and is required=True."""
    payload = build_payload(_figure_record())
    assert payload["image_slot"]["required"] is True
    assert payload["image_slot"]["sha256"] is not None
    assert payload["messages"][-1]["type"] == "input_image"


# --- 6.7 refusal codes (tier 1) ------------------------------------------------------------


def test_build_payload_raises_input_image_required_when_figure_has_no_image_source() -> None:
    """Guards: a figure item cannot be sent without its figure - the CI must-refuse case."""
    record = _figure_record()
    del record["image_data_uri"]
    with pytest.raises(RefusalError, match="INPUT_IMAGE_REQUIRED"):
        build_payload(record)


def test_build_payload_raises_missing_instruction_when_text_instruction_is_blank() -> None:
    """Guards: a text item cannot be sent without the instruction it answers."""
    with pytest.raises(RefusalError, match="MISSING_INSTRUCTION"):
        build_payload(_text_record(instruction=""))
    with pytest.raises(RefusalError, match="MISSING_INSTRUCTION"):
        build_payload(_text_record(instruction="   "))


def test_build_payload_raises_unresolved_image_when_path_does_not_exist() -> None:
    """Guards: an image_path that does not resolve to a real file is refused, not silently
    sent as an empty slot."""
    record = _figure_record()
    del record["image_data_uri"]
    record["image_path"] = "no/such/file/anywhere.png"
    with pytest.raises(RefusalError, match="UNRESOLVED_IMAGE"):
        build_payload(record)


def test_build_payload_raises_invalid_image_payload_on_malformed_data_uri() -> None:
    """Guards: a malformed data URI (bad header, or base64 that fails strict validation) is
    refused rather than passed through as unusable bytes."""
    with pytest.raises(RefusalError, match="INVALID_IMAGE_PAYLOAD"):
        build_payload(_figure_record(image_data_uri="not-a-data-uri-at-all"))
    with pytest.raises(RefusalError, match="INVALID_IMAGE_PAYLOAD"):
        build_payload(_figure_record(image_data_uri="data:image/png;base64,not!base64!!"))


def test_build_payload_raises_label_leak_in_prompt_for_a_value_carrying_instruction() -> None:
    """Guards: a prompt carrying a value-shaped label is refused before it ever reaches the
    grader - the leak is scanned in the instruction first, then the response text."""
    leaking_instruction = "Assess the response. " + _LEAK_WORD + ": 3"
    with pytest.raises(RefusalError, match="LABEL_LEAK_IN_PROMPT"):
        build_payload(_text_record(instruction=leaking_instruction))


def test_build_payload_raises_label_leak_in_prompt_for_a_value_carrying_response_text() -> None:
    """Guards: the response_text field is scanned too, not only the instruction."""
    leaking_response = "The response earned a " + _LEAK_WORD + ": 4"
    with pytest.raises(RefusalError, match="LABEL_LEAK_IN_PROMPT"):
        build_payload(_text_record(response_text=leaking_response))


# --- halt codes reachable through build_payload -------------------------------------------


def test_build_payload_raises_unknown_criterion_for_unrecognised_name() -> None:
    """Guards: a criterion outside the four-name rubric halts the whole run, it is not
    silently dropped or coerced."""
    with pytest.raises(HaltError, match="UNKNOWN_CRITERION"):
        build_payload(_text_record(criterion="not_a_real_criterion"))


def test_build_payload_raises_unknown_item_type_for_unrecognised_type() -> None:
    """Guards: an item_type outside {figure, text} halts the run rather than guessing which
    rule (image-required vs instruction-required) should apply."""
    with pytest.raises(HaltError, match="UNKNOWN_ITEM_TYPE"):
        build_payload(_text_record(item_type="audio"))


# --- 6.8 unit admission helpers -------------------------------------------------------------


def test_validate_unit_raises_missing_item_id_for_blank_id() -> None:
    """Guards: an empty item_id halts - a unit cannot be traced back to anything without one."""
    with pytest.raises(HaltError, match="MISSING_ITEM_ID"):
        validate_unit({"item_id": "", "criterion": "CLARITY"}, set())


def test_validate_unit_raises_unknown_criterion() -> None:
    """Guards: validate_unit itself rejects an unrecognised criterion, independent of
    build_payload's own check on the same condition."""
    with pytest.raises(HaltError, match="UNKNOWN_CRITERION"):
        validate_unit({"item_id": "x", "criterion": "NOT_REAL"}, set())


def test_validate_unit_raises_duplicate_unit_on_second_occurrence() -> None:
    """Guards: the same (item_id, criterion) pair seen twice halts the run - a unit must be
    measured exactly once."""
    seen: set[str] = set()
    uid = validate_unit({"item_id": "dup-1", "criterion": "CLARITY"}, seen)
    assert uid in seen
    with pytest.raises(HaltError, match="DUPLICATE_UNIT"):
        validate_unit({"item_id": "dup-1", "criterion": "CLARITY"}, seen)


def test_component_evidence_raises_missing_component_evidence_when_absent() -> None:
    """Guards: the anomaly halt needs component evidence to operate on - a unit that has none
    (key absent, empty, or unparseable) halts rather than silently skipping the anomaly check."""
    with pytest.raises(HaltError, match="MISSING_COMPONENT_EVIDENCE"):
        component_evidence({"item_id": "x"}, "x::CLARITY")
    with pytest.raises(HaltError, match="MISSING_COMPONENT_EVIDENCE"):
        component_evidence({"item_id": "x", "component_evidence": []}, "x::CLARITY")
    with pytest.raises(HaltError, match="MISSING_COMPONENT_EVIDENCE"):
        component_evidence({"item_id": "x", "component_evidence": ["nan-not-a-number"]}, "x::CLARITY")


def test_component_evidence_returns_tuple_of_floats_when_present() -> None:
    """Guards: valid component evidence is returned as a plain float tuple for the anomaly check."""
    assert component_evidence({"component_evidence": [3, 3.5]}, "x::CLARITY") == (3.0, 3.5)


def test_unit_weight_defaults_to_one_when_absent() -> None:
    """Guards: an unweighted unit counts as weight 1.0, not zero and not an error."""
    assert unit_weight({"item_id": "x"}, "x::CLARITY") == 1.0


def test_unit_weight_raises_invalid_weight_when_negative_or_nonfinite() -> None:
    """Guards: a negative or non-finite weight halts rather than corrupting the denominator."""
    with pytest.raises(HaltError, match="INVALID_WEIGHT"):
        unit_weight({"weight": -1.0}, "x::CLARITY")
    with pytest.raises(HaltError, match="INVALID_WEIGHT"):
        unit_weight({"weight": math.nan}, "x::CLARITY")
    with pytest.raises(HaltError, match="INVALID_WEIGHT"):
        unit_weight({"weight": "not-a-number"}, "x::CLARITY")


# --- 6.4 policy ------------------------------------------------------------------------------


def test_read_policy_raises_missing_policy_field_when_a_key_is_absent(tmp_path) -> None:
    """Guards: every field in POLICY_FIELDS is required - dropping any one of them halts,
    naming the missing key."""
    import json

    incomplete = {k: 1.0 for k in POLICY_FIELDS if k != "std_max"}
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(incomplete), encoding="utf-8")
    with pytest.raises(HaltError, match="MISSING_POLICY_FIELD"):
        read_policy(path)


@pytest.mark.parametrize(
    "bad_field,bad_value",
    [
        ("uniform_fraction", 0.0),
        ("uniform_fraction", 1.5),
        ("uniform_min_n", 0),
        ("spread_max", 0.0),
        ("std_max", -1.0),
    ],
)
def test_read_policy_raises_invalid_policy_on_out_of_range_values(tmp_path, bad_field, bad_value) -> None:
    """Guards: every policy field has a valid range and a value outside it halts rather than
    silently running with a nonsensical threshold."""
    import json

    good = {
        "floor": 0.0,
        "high_component_min": 3.0,
        "uniform_fraction": 0.2,
        "uniform_min_n": 5,
        "spread_max": 1.0,
        "std_max": 0.5,
    }
    good[bad_field] = bad_value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    with pytest.raises(HaltError, match="INVALID_POLICY"):
        read_policy(path)


def test_read_policy_valid_file_returns_a_policy_object(tmp_path) -> None:
    """Guards: a well-formed policy file with extra ignored keys still reads cleanly."""
    import json

    good = {
        "synthetic": True,
        "floor": 0.0,
        "high_component_min": 3.0,
        "uniform_fraction": 0.2,
        "uniform_min_n": 5,
        "spread_max": 1.0,
        "std_max": 0.5,
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    policy = read_policy(path)
    assert isinstance(policy, Policy)
    assert policy.uniform_min_n == 5


# --- 6.5 reading units -----------------------------------------------------------------------


def test_read_units_raises_not_synthetic_without_the_override_flag(tmp_path) -> None:
    """Guards the public-clean guard: a row lacking synthetic:true halts unless the caller
    explicitly overrides - the shipped package cannot silently ingest real data."""
    path = tmp_path / "units.jsonl"
    path.write_text('{"synthetic": false, "item_id": "x", "criterion": "CLARITY"}\n', encoding="utf-8")
    with pytest.raises(HaltError, match="NOT_SYNTHETIC"):
        read_units(path)


def test_read_units_allows_nonsynthetic_when_override_flag_is_set(tmp_path) -> None:
    """Guards: the override flag exists precisely so a caller can opt out of the guard
    explicitly - it must not be the silent default."""
    path = tmp_path / "units.jsonl"
    path.write_text('{"synthetic": false, "item_id": "x", "criterion": "CLARITY"}\n', encoding="utf-8")
    rows = read_units(path, allow_nonsynthetic=True)
    assert len(rows) == 1


def test_read_units_raises_malformed_units_file_on_unparseable_line(tmp_path) -> None:
    """Guards: a line that is not valid JSON halts the run rather than being skipped silently."""
    path = tmp_path / "units.jsonl"
    path.write_text("{not valid json}\n", encoding="utf-8")
    with pytest.raises(HaltError, match="MALFORMED_UNITS_FILE"):
        read_units(path)


def test_read_units_raises_empty_units_file_when_zero_rows_survive(tmp_path) -> None:
    """Guards: a units file with zero surviving rows (blank or all-blank lines) halts rather
    than silently producing an empty, vacuously-passing run."""
    path = tmp_path / "units.jsonl"
    path.write_text("\n\n   \n", encoding="utf-8")
    with pytest.raises(HaltError, match="EMPTY_UNITS_FILE"):
        read_units(path)


# --- 6.9 the anomaly halt --------------------------------------------------------------------


def _admitted_unit(**overrides):
    from failclosed_eval import AdmittedUnit

    base = dict(
        unit_id="x::CLARITY",
        item_id="x",
        criterion="CLARITY",
        item_type="text",
        estimate=3.0,
        reference=3.0,
        components=(3.0, 3.0),
        weight=1.0,
        input_sha256="0" * 64,
        image_sha256=None,
    )
    base.update(overrides)
    return AdmittedUnit(**base)


def test_check_anomalies_raises_anomalous_estimate_on_floor_with_high_components() -> None:
    """Guards: a value at the floor with high sub-value evidence is a broken measurement, not
    a genuinely low one - the source system's anomalous-label halt."""
    policy = Policy(
        floor=0.0, high_component_min=3.0, uniform_fraction=0.2, uniform_min_n=5,
        spread_max=1.0, std_max=0.5,
    )
    units = [_admitted_unit(estimate=0.0, components=(4.0, 4.0))]
    with pytest.raises(HaltError, match="ANOMALOUS_ESTIMATE"):
        check_anomalies(units, policy)


def test_check_anomalies_raises_anomalous_distribution_on_uniform_share() -> None:
    """Guards: one value holding more than the uniform fraction of a criterion's rows (at or
    above the minimum row count) halts - a flat distribution is itself evidence of a broken
    measurement, per the source system's anomalous-label halt."""
    policy = Policy(
        floor=0.0, high_component_min=3.0, uniform_fraction=0.2, uniform_min_n=5,
        spread_max=1.0, std_max=0.5,
    )
    units = [
        _admitted_unit(unit_id=f"u{i}::CORRECTNESS", item_id=f"u{i}", criterion="CORRECTNESS",
                        estimate=3.0 if i < 4 else float(i))
        for i in range(6)
    ]
    with pytest.raises(HaltError, match="ANOMALOUS_DISTRIBUTION"):
        check_anomalies(units, policy)


def test_check_anomalies_passes_clean_units_without_raising() -> None:
    """Guards: the anomaly check must not false-positive on ordinary, well-behaved units."""
    policy = Policy(
        floor=0.0, high_component_min=3.0, uniform_fraction=0.2, uniform_min_n=5,
        spread_max=1.0, std_max=0.5,
    )
    units = [_admitted_unit(unit_id=f"u{i}::CLARITY", item_id=f"u{i}", estimate=float(2 + i % 3))
             for i in range(4)]
    check_anomalies(units, policy)  # must not raise
