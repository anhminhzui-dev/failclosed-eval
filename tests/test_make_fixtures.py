"""The fixture generator, and one end-to-end run over what it makes.

Defect D6 in the hostile review: the README cites a run over thousands of criterion units and the
repository demonstrates eight. There was no generator, no scale run and no timing, so a reader was
asked to believe a design scales from an eight-row demonstration.

The generator is committed; its output is not. That only works if the same seed reproduces the same
bytes, which is what most of this file checks, and if what it produces actually exercises every
column of the denominator rather than only the happy one.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from failclosed_eval import run

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def maker():
    path = REPO_ROOT / "scripts" / "make_fixtures.py"
    spec = importlib.util.spec_from_file_location("make_fixtures_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_same_seed_produces_the_same_rows(maker) -> None:
    """Guards the reason the file is not committed: it has to be reproducible from the command."""
    first, first_bad, first_var = maker.generate(200, 4242, 0.05, 0.03, 0.02)
    second, second_bad, second_var = maker.generate(200, 4242, 0.05, 0.03, 0.02)
    assert first == second
    assert first_bad == second_bad and first_var == second_var


def test_a_different_seed_produces_different_rows(maker) -> None:
    """Guards against a generator that ignores its seed and only looks deterministic."""
    first, _, _ = maker.generate(200, 1, 0.05, 0.03, 0.02)
    second, _, _ = maker.generate(200, 2, 0.05, 0.03, 0.02)
    assert first != second


def test_every_criterion_is_represented(maker) -> None:
    """Guards: a batch missing a criterion halts on the missing denominator, which would make a
    scale run a measurement of the generator's bug rather than of the package."""
    rows, _, _ = maker.generate(200, 7, 0.05, 0.03, 0.02)
    assert {r["criterion"] for r in rows} == set(maker.CRITERIA)


def test_every_row_is_marked_synthetic(maker) -> None:
    """Guards the public-clean law at the source of the data: the generator cannot be the way a
    non-synthetic row gets in."""
    rows, _, _ = maker.generate(120, 9, 0.10, 0.05, 0.05)
    assert all(r["synthetic"] is True for r in rows)


def test_the_seeded_bad_share_is_honoured_and_spread_across_kinds(maker) -> None:
    """Guards: the share is stated on the command line and has to be what actually comes out."""
    rows, kinds, _ = maker.generate(400, 11, 0.10, 0.0, 0.0)
    assert len(kinds) == 40
    assert set(kinds.values()) == set(maker.BAD_KINDS)


def test_the_first_row_of_each_criterion_is_never_seeded_bad(maker) -> None:
    """Guards the protection that keeps every criterion's denominator alive."""
    _, kinds, variants = maker.generate(400, 13, 0.30, 0.10, 0.10)
    for i in range(len(maker.CRITERIA)):
        assert i not in kinds and i not in variants


def test_zero_shares_produce_a_batch_that_earns_go(maker, tmp_path, fixtures_dir) -> None:
    """Guards both directions at once: with nothing seeded the generated batch must PASS. A
    generator whose output can only ever be held would prove nothing about the gates."""
    rows, kinds, variants = maker.generate(240, 17, 0.0, 0.0, 0.0)
    assert not kinds and not variants
    units = tmp_path / "clean_generated.jsonl"
    maker.write_rows(rows, units)
    summary = run(units, fixtures_dir / "policy.json")
    assert summary.verdict == "GO", summary.halt_code
    assert summary.units_admitted == 240


def test_a_seeded_batch_exercises_every_denominator_column(maker, tmp_path, fixtures_dir) -> None:
    """Guards D6's real point: a scale run has to move all five columns, or the four that never
    move are still undemonstrated at any size."""
    rows, kinds, variants = maker.generate(400, 19, 0.05, 0.03, 0.02)
    units = tmp_path / "seeded_generated.jsonl"
    maker.write_rows(rows, units)
    summary = run(units, fixtures_dir / "policy.json")

    assert summary.verdict == "HOLD"
    assert summary.halt_code is None, "seeded rows are tier-1 refusals, not halts"
    assert summary.units_selected == 400
    assert summary.units_refused == len(kinds)
    assert summary.units_abstained > 0
    assert summary.units_missing_reference > 0
    assert summary.units_admitted > 0
    assert (
        summary.units_admitted
        + summary.units_refused
        + summary.units_abstained
        + summary.units_missing_reference
        == 400
    ), "every selected unit must land in exactly one column"
    assert set(summary.refusals_by_code) == {
        "INPUT_IMAGE_REQUIRED",
        "MISSING_INSTRUCTION",
        "LABEL_LEAK_IN_PROMPT",
    }


def test_the_generated_file_is_written_as_one_json_object_per_line(maker, tmp_path) -> None:
    """Guards the format the runner reads."""
    rows, _, _ = maker.generate(20, 23, 0.0, 0.0, 0.0)
    out = tmp_path / "nested" / "units.jsonl"
    digest = maker.write_rows(rows, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 20
    assert all(isinstance(json.loads(l), dict) for l in lines)
    assert len(digest) == 64


def test_a_count_below_one_row_per_criterion_is_refused(maker) -> None:
    """Guards: refusing a batch that cannot possibly earn a denominator is better than emitting it
    and letting the run discover the problem."""
    with pytest.raises(SystemExit):
        maker.generate(2, 29, 0.0, 0.0, 0.0)


def test_an_impossible_share_is_refused(maker) -> None:
    """Guards the argument surface the same way the package guards its inputs."""
    with pytest.raises(SystemExit):
        maker.generate(100, 31, 0.9, 0.0, 0.0)


@pytest.mark.parametrize("seed", list(range(1, 26)))
def test_no_seed_produces_a_batch_that_halts_on_its_own_distribution(maker, tmp_path, fixtures_dir, seed) -> None:
    """Guards a real defect this file caught: the first generator drew its values at random, and
    ordinary sampling noise pushed one value past the policy's uniform-share ceiling often enough
    that a clean batch would halt on ANOMALOUS_DISTRIBUTION - a halt about the generator, not about
    the data under test. Twenty-five seeds, all of which must earn GO with nothing seeded."""
    rows, _, _ = maker.generate(240, seed, 0.0, 0.0, 0.0)
    units = tmp_path / f"seed_{seed}.jsonl"
    maker.write_rows(rows, units)
    summary = run(units, fixtures_dir / "policy.json")
    assert summary.halt_code is None, f"seed {seed} halted on {summary.halt_code}"
    assert summary.verdict == "GO"
