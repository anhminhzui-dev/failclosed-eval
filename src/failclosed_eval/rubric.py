"""The generic rubric this package measures against.

Written from scratch for this repository. It is deliberately domain-neutral: four criteria that
apply to any open written response, and two item types that differ only in whether the item is
grounded on a supplied figure. It is not derived from, and does not paraphrase, any published or
commercial rubric.
"""
from __future__ import annotations

from typing import Final

CRITERIA: Final[tuple[str, ...]] = ("CORRECTNESS", "COMPLETENESS", "CLARITY", "EVIDENCE")

CRITERION_QUESTIONS: Final[dict[str, str]] = {
    "CORRECTNESS": "Are the claims the response makes true and internally consistent?",
    "COMPLETENESS": "Does the response cover every part the task asked for?",
    "CLARITY": "Can a reader follow the argument without re-reading?",
    "EVIDENCE": "Is each claim supported by something the response actually cites or shows?",
}

ITEM_TYPES: Final[tuple[str, ...]] = ("figure", "text")
FIGURE_ITEM: Final[str] = "figure"
TEXT_ITEM: Final[str] = "text"

LEVEL_MIN: Final[float] = 0.0
LEVEL_MAX: Final[float] = 4.0
LEVEL_STEP: Final[float] = 0.5


def requires_image(item_type: str) -> bool:
    """A figure item cannot be sent without its figure."""
    return item_type == FIGURE_ITEM


def requires_instruction(item_type: str) -> bool:
    """A text item cannot be sent without the instruction it answers."""
    return item_type == TEXT_ITEM
