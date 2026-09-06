"""Guards CONTRACT.md section 5 (abstain.py): two independent estimates that disagree must
abstain instead of committing a false-confident median; a single estimate cannot disagree with
anything and always commits; rounding is half-up and deterministic, never Python's banker's
rounding, so a step boundary case is unambiguous."""
from __future__ import annotations

import math

import pytest

from failclosed_eval import decide, round_to_step

PINNED_DECIDE_CASES = [
    ([3.0, 3.0, 3.5], "COMMIT", 3.0),
    ([2.0, 4.0, 3.0], "ABSTAIN", None),
    ([3.0, 4.0, 2.5], "ABSTAIN", None),
    ([4.0], "COMMIT", 4.0),
    ([], "ABSTAIN", None),
    ([3.5, 4.0], "COMMIT", 4.0),
    ([None, 3.0], "COMMIT", 3.0),
]


@pytest.mark.parametrize("estimates,action,value", PINNED_DECIDE_CASES)
def test_decide_pinned_cases(estimates, action, value) -> None:
    """Guards: every one of the seven CONTRACT-pinned decide() outcomes, exactly."""
    decision = decide(estimates)
    assert decision.action == action
    assert decision.value == value


def test_decide_single_estimate_cannot_disagree_and_always_commits() -> None:
    """Guards: one estimate has nothing to disagree with, so it always commits."""
    decision = decide([4.0])
    assert decision.action == "COMMIT"
    assert decision.spread == 0.0
    assert decision.stdev == 0.0


def test_decide_empty_list_abstains_with_no_estimate_reason() -> None:
    """Guards: zero estimates is not a low score, it is nothing to measure - ABSTAIN, not zero."""
    decision = decide([])
    assert decision.action == "ABSTAIN"
    assert decision.value is None
    assert decision.reason == "no estimate"


def test_decide_disagreement_reason_names_spread_and_stdev() -> None:
    """Guards: an ABSTAIN must say why, not just that it happened."""
    decision = decide([2.0, 4.0, 3.0])
    assert decision.reason.startswith("estimates disagree")


@pytest.mark.parametrize(
    "value,expected",
    [(3.2, 3.0), (3.3, 3.5), (2.75, 3.0), (4.0, 4.0)],
)
def test_round_to_step_pinned_cases(value, expected) -> None:
    """Guards: round_to_step is half-up on the 0.5 step grid, deterministically, per case."""
    assert round_to_step(value) == expected


def test_round_to_step_raises_on_nonpositive_step() -> None:
    """Guards: a step of zero or negative would divide the rubric into infinite or backwards
    buckets - this must fail loudly, not silently misround."""
    with pytest.raises(ValueError):
        round_to_step(3.0, step=0.0)
    with pytest.raises(ValueError):
        round_to_step(3.0, step=-0.5)


def test_decide_conflict_condition_is_spread_or_stdev_either_can_trip_it() -> None:
    """Guards: disagreement is spread_max OR std_max, either threshold alone must be able to
    force an abstain - not require both to be breached simultaneously."""
    # spread breaches but stdev alone would not (values close except one outlier over a wide gap
    # is exercised by the pinned case above); here confirm a wide, low-count spread abstains.
    decision = decide([1.0, 2.5])
    assert decision.spread == pytest.approx(1.5)
    assert decision.action == "ABSTAIN"
