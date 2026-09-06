"""G1-core's own verification smoke test.

Not part of CONTRACT.md's file map (section 1) or its owned G2 test suite
(section 12). This file exists only so the G1 group can prove its own five
files (`provenance.py`, `abstain.py`, `validators.py`, `runner.py`,
`__init__.py`) work together before G2/G3 land, per the task's explicit
allowance for a G1 smoke test.

It stubs `failclosed_eval.rubric` into `sys.modules` instead of writing
anything to disk, because `rubric.py` is G2's fenced file (CONTRACT.md
section 1) and this group must never touch another group's files. The stub
below is exactly the interface CONTRACT.md section 3 pins verbatim for
`rubric.py`; nothing in this file or in G1's own code depends on any detail
of `rubric.py` beyond that pinned interface, so this test exercises the real
G1 code paths, not a mock of them.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_rubric_stub() -> None:
    if "failclosed_eval.rubric" in sys.modules:
        return  # G2 has already landed the real file; use it, don't shadow it
    mod = types.ModuleType("failclosed_eval.rubric")
    mod.CRITERIA = ("CORRECTNESS", "COMPLETENESS", "CLARITY", "EVIDENCE")
    mod.CRITERION_QUESTIONS = {
        "CORRECTNESS": "Are the claims the response makes true and internally consistent?",
        "COMPLETENESS": "Does the response cover every part the task asked for?",
        "CLARITY": "Can a reader follow the argument without re-reading?",
        "EVIDENCE": "Is each claim supported by something the response actually cites or shows?",
    }
    mod.ITEM_TYPES = ("figure", "text")
    mod.FIGURE_ITEM = "figure"
    mod.TEXT_ITEM = "text"
    mod.LEVEL_MIN = 0.0
    mod.LEVEL_MAX = 4.0
    mod.LEVEL_STEP = 0.5

    def requires_image(item_type: str) -> bool:
        return item_type == mod.FIGURE_ITEM

    def requires_instruction(item_type: str) -> bool:
        return item_type == mod.TEXT_ITEM

    mod.requires_image = requires_image
    mod.requires_instruction = requires_instruction
    sys.modules["failclosed_eval.rubric"] = mod


_install_rubric_stub()

import failclosed_eval as fc  # noqa: E402


# ---------------------------------------------------------------------------
# import surface
# ---------------------------------------------------------------------------


def test_all_symbols_present():
    for name in fc.__all__:
        assert hasattr(fc, name), f"missing exported symbol: {name}"


def test_package_does_not_import_cli_or_tracking():
    """The claim is about the PACKAGE's import graph, so it has to be measured in a process that
    has done nothing else. Asserting against this session's sys.modules measured the test suite
    instead: the moment any other test imported the CLI on purpose - which the CLI's own tests must
    - this went red while the package's import surface was untouched."""
    import subprocess

    probe = (
        "import sys, failclosed_eval; "
        "print('cli' in ''.join(m for m in sys.modules if m.startswith('failclosed_eval.cli')), "
        "'failclosed_eval.tracking' in sys.modules)"
    )
    import os

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env, cwd=str(root)
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False", result.stdout


# ---------------------------------------------------------------------------
# provenance.py
# ---------------------------------------------------------------------------


def test_canonical_hash_key_order_independent():
    assert fc.canonical_hash({"a": 1, "b": 2}) == fc.canonical_hash({"b": 2, "a": 1})


def test_text_hash_empty_string_pinned():
    assert (
        fc.text_hash("")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_canonical_hash_is_64_lowercase_hex():
    h = fc.canonical_hash({})
    assert len(h) == 64
    assert h == h.lower()


def test_unit_id_shape():
    assert fc.unit_id("x-1", "clarity") == "x-1::CLARITY"


def test_file_hash_matches_text_hash(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")
    assert fc.file_hash(p) == fc.text_hash("hello world")


# ---------------------------------------------------------------------------
# abstain.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "estimates, action, value",
    [
        ([3.0, 3.0, 3.5], "COMMIT", 3.0),
        ([2.0, 4.0, 3.0], "ABSTAIN", None),
        ([3.0, 4.0, 2.5], "ABSTAIN", None),
        ([4.0], "COMMIT", 4.0),
        ([], "ABSTAIN", None),
        ([3.5, 4.0], "COMMIT", 4.0),
        ([None, 3.0], "COMMIT", 3.0),
    ],
)
def test_decide_pinned_cases(estimates, action, value):
    d = fc.decide(estimates)
    assert d.action == action
    assert d.value == value


@pytest.mark.parametrize(
    "value, expected", [(3.2, 3.0), (3.3, 3.5), (2.75, 3.0), (4.0, 4.0)]
)
def test_round_to_step_pinned_cases(value, expected):
    assert fc.round_to_step(value) == expected


def test_round_to_step_rejects_nonpositive_step():
    with pytest.raises(ValueError):
        fc.round_to_step(1.0, step=0)


def test_decide_reason_prefix():
    assert fc.decide([2.0, 4.0, 3.0]).reason.startswith("estimates disagree")


# ---------------------------------------------------------------------------
# validators.py -- label-leak detector (fragments so this file does not
# itself contain the literal pattern it forbids)
# ---------------------------------------------------------------------------

_LEV = "lev"
_EL = "el"


@pytest.mark.parametrize(
    "text, expected",
    [
        (_LEV + _EL + ": 3", 1),
        ('{"' + _LEV + _EL + '": 3}', 1),
        ("item_" + _LEV + _EL + "5", 1),
        ("the level of detail is good", 0),
        ("You must never output a level or a score.", 0),
        ("UN" + "M" + "ET: x", 1),  # "MET" itself must be split: (?:UN)? is optional
        # R1 (round-2 hostile review): the bare/default call is the shape the admission path
        # uses, and it must NOT honour the exemption anchor.
        (_LEV + _EL + ": 3 " + fc.LEAK_EXEMPT_ANCHOR, 1),
    ],
)
def test_count_label_leaks_pinned_cases(text, expected):
    assert fc.count_label_leaks(text) == expected


def test_count_label_leaks_honours_exemption_only_when_explicitly_asked():
    """Guards R1: honour_exemption defaults to False (the admission path's call shape); only an
    explicit honour_exemption=True (the repo-scan path) skips a line carrying the anchor."""
    text = _LEV + _EL + ": 3 " + fc.LEAK_EXEMPT_ANCHOR
    assert fc.count_label_leaks(text) == 1
    assert fc.count_label_leaks(text, honour_exemption=True) == 0


def test_leak_detector_can_fail_on_constructed_positive():
    # A scan that has never been shown to fail cannot certify a clean result.
    positive = _LEV + _EL + "=7"
    assert fc.count_label_leaks(positive) > 0


# ---------------------------------------------------------------------------
# validators.py -- payload construction
# ---------------------------------------------------------------------------

_PNG_1X1 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQI"
    "HWP4z8DwHwAFgAI/9GGnOwAAAABJRU5ErkJggg=="
)


def _record(**overrides):
    record = {
        "synthetic": True,
        "item_id": "syn-001",
        "criterion": "CORRECTNESS",
        "item_type": "figure",
        "response_text": "Synthetic response about a supplied figure.",
        "instruction": "Describe what the figure shows.",
        "image_data_uri": _PNG_1X1,
        "estimates": [3.0, 3.0],
        "reference": 3.0,
        "component_evidence": [3.0, 3.0],
        "weight": 1.0,
    }
    record.update(overrides)
    return record


def test_build_payload_image_slot_always_last_message():
    payload = fc.build_payload(_record())
    assert payload["messages"][-1]["type"] == "input_image"
    assert payload["image_slot"]["sha256"] is not None


def test_build_payload_requires_image_for_figure_item():
    with pytest.raises(fc.RefusalError, match="INPUT_IMAGE_REQUIRED"):
        fc.build_payload(_record(image_data_uri=""))


def test_build_payload_requires_instruction_for_text_item():
    record = _record(item_type="text", instruction="", image_data_uri="")
    with pytest.raises(fc.RefusalError, match="MISSING_INSTRUCTION"):
        fc.build_payload(record)


def test_build_payload_rejects_bad_image_payload():
    record = _record(image_data_uri="data:image/png;base64,not-base64!!!")
    with pytest.raises(fc.RefusalError, match="INVALID_IMAGE_PAYLOAD"):
        fc.build_payload(record)


def test_build_payload_rejects_leak_in_instruction():
    record = _record(instruction=_LEV + _EL + ": 3")
    with pytest.raises(fc.RefusalError, match="LABEL_LEAK_IN_PROMPT"):
        fc.build_payload(record)


def test_build_payload_unknown_criterion_halts():
    with pytest.raises(fc.HaltError, match="UNKNOWN_CRITERION"):
        fc.build_payload(_record(criterion="NOT_A_CRITERION"))


def test_build_payload_text_item_no_image_ok():
    record = _record(item_type="text", image_data_uri="", instruction="Say what it covers.")
    payload = fc.build_payload(record)
    assert payload["image_slot"]["sha256"] is None
    assert payload["image_slot"]["required"] is False


# ---------------------------------------------------------------------------
# validators.py -- policy / units reading
# ---------------------------------------------------------------------------

_POLICY = {
    "synthetic": True,
    "floor": 0.0,
    "high_component_min": 3.0,
    "uniform_fraction": 0.2,
    "uniform_min_n": 5,
    "spread_max": 1.0,
    "std_max": 0.5,
}


def test_read_policy_missing_field_halts(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"floor": 0.0}), encoding="utf-8")
    with pytest.raises(fc.HaltError, match="MISSING_POLICY_FIELD"):
        fc.read_policy(p)


def test_read_policy_valid(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(_POLICY), encoding="utf-8")
    policy = fc.read_policy(p)
    assert policy.uniform_min_n == 5


def test_read_policy_invalid_range_halts(tmp_path):
    bad = dict(_POLICY)
    bad["uniform_fraction"] = 1.5
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(fc.HaltError, match="INVALID_POLICY"):
        fc.read_policy(p)


def test_read_units_rejects_nonsynthetic_row(tmp_path):
    row = _record()
    row["synthetic"] = False
    p = tmp_path / "units.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(fc.HaltError, match="NOT_SYNTHETIC"):
        fc.read_units(p)


def test_read_units_empty_file_halts(tmp_path):
    p = tmp_path / "units.jsonl"
    p.write_text("\n\n", encoding="utf-8")
    with pytest.raises(fc.HaltError, match="EMPTY_UNITS_FILE"):
        fc.read_units(p)


def test_read_units_duplicate_unit_halts(tmp_path):
    p = tmp_path / "units.jsonl"
    row = _record()
    p.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    records = fc.read_units(p)
    seen: set[str] = set()
    fc.validate_unit(records[0], seen)
    with pytest.raises(fc.HaltError, match="DUPLICATE_UNIT"):
        fc.validate_unit(records[1], seen)


# ---------------------------------------------------------------------------
# runner.py -- end to end
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _clean_two_per_criterion() -> list[dict]:
    records = []
    for i, criterion in enumerate(fc.CRITERIA):
        records.append(_record(item_id=f"syn-{i}-a", criterion=criterion, item_type="figure"))
        records.append(
            _record(
                item_id=f"syn-{i}-b",
                criterion=criterion,
                item_type="text",
                image_data_uri="",
                instruction="Say what the response covers.",
            )
        )
    return records


def test_run_clean_fixture_gives_go(tmp_path):
    units = tmp_path / "units.jsonl"
    policy = tmp_path / "policy.json"
    _write_jsonl(units, _clean_two_per_criterion())
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")

    summary = fc.run(units, policy)

    assert summary.verdict == "GO"
    assert summary.halt_code is None
    assert summary.units_selected == 8
    assert summary.units_admitted == 8
    assert summary.units_refused == 0


def test_run_missing_image_gives_hold_with_named_refusal(tmp_path):
    units = tmp_path / "units.jsonl"
    policy = tmp_path / "policy.json"
    records = _clean_two_per_criterion()
    records[0]["image_data_uri"] = ""  # strip the image from a figure row
    _write_jsonl(units, records)
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")

    summary = fc.run(units, policy)

    assert summary.verdict == "HOLD"
    assert summary.halt_code is None
    assert summary.refusals_by_code == {"INPUT_IMAGE_REQUIRED": 1}
    assert summary.units_refused == 1


def test_run_never_raises_failclosed_error_on_missing_units_file(tmp_path):
    units = tmp_path / "does_not_exist.jsonl"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")

    summary = fc.run(units, policy)  # must not raise

    assert summary.verdict == "HOLD"
    assert summary.halt_code == "MALFORMED_UNITS_FILE"


def test_run_writes_out_dir_files_and_trace_shape(tmp_path):
    units = tmp_path / "units.jsonl"
    policy = tmp_path / "policy.json"
    _write_jsonl(units, _clean_two_per_criterion())
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")
    out_dir = tmp_path / "out"

    fc.run(units, policy, out_dir=out_dir)

    assert (out_dir / "summary.json").is_file()
    assert (out_dir / "trace.jsonl").is_file()
    assert not (out_dir / "halt.json").exists()

    lines = (out_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 8
    forbidden = {
        "estimate", "estimates", "reference", "components", "component_evidence",
        "weight", "weight_value", "mae", "error", "accuracy", "level",
    }
    for line in lines:
        row = json.loads(line)
        assert set(row.keys()) == {
            "unit_id", "criterion", "state", "code", "input_sha256", "image_sha256",
        }
        assert not (forbidden & set(row.keys()))


def test_run_halt_writes_halt_json(tmp_path):
    units = tmp_path / "units.jsonl"
    policy = tmp_path / "bad_policy.json"
    _write_jsonl(units, _clean_two_per_criterion())
    policy.write_text(json.dumps({"floor": 0.0}), encoding="utf-8")  # missing fields
    out_dir = tmp_path / "out"

    summary = fc.run(units, policy, out_dir=out_dir)

    assert summary.verdict == "HOLD"
    assert summary.halt_code == "MISSING_POLICY_FIELD"
    assert (out_dir / "halt.json").is_file()
    halt = json.loads((out_dir / "halt.json").read_text(encoding="utf-8"))
    assert halt["code"] == "MISSING_POLICY_FIELD"


def test_denominator_line_names_every_exclusion_class(tmp_path):
    units = tmp_path / "units.jsonl"
    policy = tmp_path / "policy.json"
    _write_jsonl(units, _clean_two_per_criterion())
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")

    summary = fc.run(units, policy)
    line = fc.denominator_line(summary)

    assert line.startswith("DENOMINATORS: ")
    for criterion in fc.CRITERIA:
        assert criterion in line
    assert "refused=" in line
    assert "abstained=" in line
    assert "reference_excluded=" in line


def test_tracker_receives_no_measurement_value(tmp_path):
    class FakeTracker:
        def __init__(self):
            self.received = None

        def log_run(self, summary):
            self.received = summary

    units = tmp_path / "units.jsonl"
    policy = tmp_path / "policy.json"
    _write_jsonl(units, _clean_two_per_criterion())
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")

    tracker = FakeTracker()
    fc.run(units, policy, tracker=tracker)

    forbidden = {
        "estimate", "estimates", "reference", "components", "component_evidence",
        "weight_value", "mae", "error", "accuracy", "level",
    }

    def _walk(obj):
        if isinstance(obj, dict):
            assert not (forbidden & set(obj.keys()))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    assert tracker.received is not None
    _walk(tracker.received)
