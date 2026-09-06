"""Measures the label-leak detector in the direction the README used only to argue about.

Defect D2 in the hostile review: the detector fired on ordinary English prose. Seven sentences a
reviewer wrote in one minute - an embedded label word followed by a digit, as in a benchmark year
or a landmark number - each got a legitimate unit thrown out of the denominator and held the run.
The README's longest section claimed a precision the pattern did not have, and every "should not
fire" case in the suite was a bare label word with no digit anywhere in the string, so the suite
confirmed the argument instead of testing it.

The cure is a non-letter lookbehind, and this file is the measurement that keeps it honest: a
corpus of 250 invented instruction lines that all legitimately carry a label word with a digit,
with the hit rate reported and bounded. Every banned string below is split INSIDE its label word, not
in front of it, so this file never contains a contiguous value-carrying label of its own - the
same convention test_validators.py uses, applied one character further along.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from failclosed_eval import LABEL_LEAK_RE, count_label_leaks

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "fixtures" / "fp_corpus_instructions.txt"

# The measured bound. 4 of 250 lines is 1.60 percent; the budget is 2 percent, so a change that
# widens the pattern by even one more ordinary-English shape fails here rather than in review.
MAX_FALSE_POSITIVE_RATE = 0.02


def corpus_lines() -> list[str]:
    """Corpus lines only: '#' lines are commentary about the corpus, not corpus."""
    text = CORPUS_PATH.read_text(encoding="utf-8")
    return [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def test_corpus_is_large_enough_to_mean_anything() -> None:
    """Guards: a hit rate over a handful of lines is not a measurement."""
    assert len(corpus_lines()) >= 200


def test_false_positive_rate_over_the_corpus_is_reported_and_bounded(capsys) -> None:
    """Guards D2: the detector's error rate in the false-positive direction is measured, printed,
    and capped. Before the lookbehind this same corpus scored 87 of 250 (34.80 percent)."""
    lines = corpus_lines()
    hits = [l for l in lines if count_label_leaks(l)]
    rate = len(hits) / len(lines)
    print(f"FP_CORPUS: lines={len(lines)} hits={len(hits)} rate={rate:.4f}")
    captured = capsys.readouterr()
    assert "FP_CORPUS:" in captured.out, "the rate must be reported, not only asserted"
    assert rate <= MAX_FALSE_POSITIVE_RATE, f"false-positive rate {rate:.4f} over {len(lines)} lines"


def test_every_residual_hit_is_the_one_documented_shape() -> None:
    """Guards: the four remaining hits are the labelled residual class at the end of the corpus -
    a standalone label word immediately followed by a digit - and not some new accidental class
    hiding inside the ordinary-prose block."""
    lines = corpus_lines()
    hit_indexes = [i for i, l in enumerate(lines) if count_label_leaks(l)]
    tail = set(range(len(lines) - 4, len(lines)))
    assert set(hit_indexes) == tail, f"unexpected hit outside the documented residual block: {hit_indexes}"


# --- the seven sentences from the hostile review, assembled from fragments ---------------------

_CURED_FALSE_POSITIVES = [
    "This is a benchm" + "ark 2024 dataset.",
    "Refer to landm" + "ark 3 on the diagram.",
    "Please upgr" + "ade 3 of the sections.",
    "The bookm" + "ark 2 tab is open.",
    "Broadb" + "and 5G coverage is the topic.",
    "Oper" + "ating 3 sites at once is the constraint.",
    "The waterm" + "ark 7 overlay is not content.",
]


@pytest.mark.parametrize("text", _CURED_FALSE_POSITIVES)
def test_embedded_label_word_followed_by_a_digit_is_not_a_hit(text: str) -> None:
    """Guards D2 directly: each of these returned 1 before the lookbehind and must return 0 now.
    This is the test that would have failed on the shipped pattern."""
    assert count_label_leaks(text) == 0


def test_underscore_is_still_not_a_letter_so_an_identifier_leak_still_fires() -> None:
    """Guards the cure against over-correcting: the whole reason the pattern has no leading \\b is
    that an underscore hides a leak inside an identifier. The lookbehind rejects letters only, so
    the identifier case the README's argument is built on must still fire."""
    assert count_label_leaks("item_" + "lev" + "el5") == 1


def test_start_of_string_still_counts_as_a_non_letter() -> None:
    """Guards: a leak that opens a line has nothing in front of it, and a lookbehind that failed at
    the start of a string would make the most obvious leak position the safest one."""
    assert count_label_leaks("lev" + "el: 3") == 1


# --- documented out-of-scope behaviour ---------------------------------------------------------

_WORD_SPELLED_VALUES = [
    "sco" + "re: seven",
    "The lev" + "el is THREE.",
    "ba" + "nd: six point five",
]


@pytest.mark.parametrize("text", _WORD_SPELLED_VALUES)
def test_a_value_spelled_in_words_is_out_of_scope_and_pinned_as_such(text: str) -> None:
    """Guards the README's own honesty clause: the detector is digit-shaped, so a value written as
    a word is NOT caught. That is a stated limit, not an undiscovered hole, and it is pinned here
    so a future change cannot quietly claim coverage this package does not have."""
    assert count_label_leaks(text) == 0


def test_readme_states_the_measured_rate_and_the_out_of_scope_limit() -> None:
    """Guards: the measurement has to reach the reader. A number that lives only in a test is not
    a claim a reviewer can check."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "fp_corpus_instructions.txt" in readme
    assert "1.60" in readme and "34.80" in readme
    assert "spelled in words" in readme


# --- the two copies of the pattern must not drift ----------------------------------------------


def _load_forbidden_scan():
    path = REPO_ROOT / "scripts" / "forbidden_scan.py"
    spec = importlib.util.spec_from_file_location("forbidden_scan_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_admission_pattern_and_the_repo_scan_pattern_are_identical() -> None:
    """Guards: the same detector runs in two places - the admission path and the standalone repo
    scan - and a fix applied to one copy only would leave the published tree checked by the old,
    noisy pattern. They must be byte-identical, flags included."""
    scan = _load_forbidden_scan()
    assert scan.LABEL_LEAK_RE.pattern == LABEL_LEAK_RE.pattern
    assert scan.LABEL_LEAK_RE.flags == LABEL_LEAK_RE.flags


def test_the_repo_scan_copy_agrees_with_the_admission_copy_over_the_whole_corpus() -> None:
    """Guards behaviour, not just source text: identical patterns are proven by identical verdicts
    over 250 real lines."""
    scan = _load_forbidden_scan()
    for line in corpus_lines():
        mine = len(LABEL_LEAK_RE.findall(line))
        theirs = len(scan.LABEL_LEAK_RE.findall(line))
        assert mine == theirs, line
