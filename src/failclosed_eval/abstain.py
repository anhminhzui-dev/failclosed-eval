"""Abstain-instead-of-committing rule for disagreeing independent estimates.

Extracted and generalised from a private grading-measurement harness's abstain
layer (EXTRACTION_PLAN.md section 3.3; CONTRACT.md section 5 pins the exact
behaviour below, including the seven test cases used to prove it). Changed on
purpose from the source system: there the runner read a pre-set flag and this
module was never called by anything; here `runner.run` calls `decide` directly
on each unit's estimates, so the rule is wired into the admission path. The two
thresholds and the rounding step are design constants, not validated operating
points.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Sequence

DEFAULT_SPREAD_MAX: float = 1.0
DEFAULT_STD_MAX: float = 0.5
DEFAULT_STEP: float = 0.5


@dataclass(frozen=True)
class Decision:
    action: str  # "COMMIT" or "ABSTAIN"
    value: float | None  # committed value; None on ABSTAIN
    reason: str  # "" on COMMIT
    spread: float | None
    stdev: float | None


def round_to_step(value: float, step: float = DEFAULT_STEP) -> float:
    """Half-up rounding to the nearest `step`, deliberately not Python's
    banker's rounding, so tests are unambiguous."""
    if step <= 0:
        raise ValueError("step must be > 0")
    return round(math.floor(value / step + 0.5) * step, 6)


def decide(
    estimates: Sequence[float | None],
    spread_max: float = DEFAULT_SPREAD_MAX,
    std_max: float = DEFAULT_STD_MAX,
    step: float = DEFAULT_STEP,
) -> Decision:
    """Commit the median when independent estimates agree; abstain when they
    conflict. One estimate always commits (nothing to disagree with); zero
    estimates always abstains."""
    values = [float(e) for e in estimates if e is not None]

    if not values:
        return Decision("ABSTAIN", None, "no estimate", None, None)

    if len(values) == 1:
        return Decision("COMMIT", round_to_step(values[0], step), "", 0.0, 0.0)

    spread = max(values) - min(values)
    stdev = statistics.pstdev(values)
    if spread >= spread_max or stdev >= std_max:
        reason = f"estimates disagree (spread={spread:.2f}, stdev={stdev:.2f})"
        return Decision("ABSTAIN", None, reason, spread, stdev)
    return Decision(
        "COMMIT", round_to_step(statistics.median(values), step), "", spread, stdev
    )
