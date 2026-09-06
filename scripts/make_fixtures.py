#!/usr/bin/env python3
"""Generate N synthetic units, deterministically, with a stated share of seeded-bad rows.

Why this exists: the README cites a run over thousands of criterion units and the repository ships
eight. A design that is only ever demonstrated at eight rows asks the reader to take the scaling on
trust. This generator closes that gap without shipping a large file - the command is committed, the
output is not, and anyone can reproduce the same bytes from the same seed.

Everything here is invented. No real response, prompt, figure, person or examination appears, and
every emitted row carries `"synthetic": true` so the admission path would halt if one did not.

Stdlib only, no dependency on the package it feeds, so it runs from a bare checkout.

Seeded-bad rows are TIER-1 refusal shapes on purpose (a figure item with no figure, a text item
with no instruction, a value-carrying label in the instruction). A tier-2 halt would stop the run
at the first bad row and a scale run would then measure nothing but the distance to that row.

    python scripts/make_fixtures.py --count 2000 --out fixtures/generated/units_2000.jsonl

Determinism: the same --seed and --count produce byte-identical output. Verify with two runs and a
hash comparison; `--verify` does exactly that and prints the digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

CRITERIA = ("CORRECTNESS", "COMPLETENESS", "CLARITY", "EVIDENCE")
ITEM_TYPES = ("figure", "text")

# A 1x1 transparent PNG. The smallest thing that is honestly an image; nothing is depicted.
ONE_PIXEL_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/9GGnOwAAAABJRU5ErkJggg=="
)

_SUBJECTS = (
    "the supplied figure",
    "the passage above",
    "the two sources provided",
    "the table in the appendix",
    "the short extract",
    "the diagram supplied with this item",
)

_ASKS = (
    "Describe what it shows and explain why the pattern occurs.",
    "Judge whether the claims made are internally consistent.",
    "Say which parts of the task the response leaves unanswered.",
    "Explain whether a reader could follow the argument in one pass.",
    "Identify each claim and say what supports it.",
    "Compare the two accounts and say where they disagree.",
)

_RESPONSE_SHAPES = (
    "The response states a pattern, names one cause, and stops before the second part of the task.",
    "The response asserts a fact and then contradicts it two sentences later without noticing.",
    "The response covers every part asked for but never says what any of its claims rest on.",
    "The response is clear but answers a narrower question than the one that was set.",
    "The response quotes the source three times and adds one original sentence at the end.",
    "The response opens with a restatement of the task and never moves beyond it.",
    "The response is well ordered, and each claim names the sentence it comes from.",
    "The response mixes two arguments in one paragraph so neither is followed through.",
)

# Assembled from fragments so this file never contains a contiguous value-carrying label of its
# own - the repository's own scanner reads this file like any other.
_LEAK_FRAGMENT = "lev" + "el" + ": 3"

BAD_KINDS = ("missing_image", "missing_instruction", "label_leak")

# Not defects. A unit that abstains because its two independent estimates disagree, and a unit with
# no reference to exclude against, are honest outcomes with their own denominator columns. A scale
# run that never produced either would leave two of the five columns permanently at zero and prove
# nothing about them.
VARIANT_KINDS = ("abstain", "no_reference")


def build_row(
    index: int,
    rng: random.Random,
    bad_kind: str | None,
    variant: str | None = None,
    rotation: int = 0,
) -> dict[str, Any]:
    criterion = CRITERIA[index % len(CRITERIA)]
    item_type = ITEM_TYPES[index % len(ITEM_TYPES)]
    subject = _SUBJECTS[rng.randrange(len(_SUBJECTS))]
    ask = _ASKS[rng.randrange(len(_ASKS))]

    instruction = f"Read {subject}. {ask}"
    response_text = _RESPONSE_SHAPES[rng.randrange(len(_RESPONSE_SHAPES))]

    # Nine possible values on the rubric's own step, walked in order within each criterion rather
    # than drawn at random. Drawing at random looked more natural and was wrong: ordinary sampling
    # noise pushed one value over the policy's uniform-share ceiling often enough that a generated
    # batch would halt on ANOMALOUS_DISTRIBUTION for a reason that had nothing to do with the data
    # under test. The walk is rotated by a seeded offset, so two seeds still differ.
    base = ((index // len(CRITERIA) + rotation) % 9) * 0.5
    second = base + rng.choice((0.0, 0.0, 0.5, -0.5))
    second = min(4.0, max(0.0, second))

    # Component evidence tracks the committed value, so a row never lands at the floor with high
    # supporting evidence - that combination is the anomalous-estimate halt, and a generator that
    # produced it by accident would look like a broken measurement rather than a synthetic one.
    components = [
        round(min(4.0, max(0.0, base + rng.choice((-0.5, 0.0, 0.5)))), 2) for _ in range(2)
    ]

    row: dict[str, Any] = {
        "synthetic": True,
        "item_id": f"gen-{index:06d}",
        "criterion": criterion,
        "item_type": item_type,
        "response_text": response_text,
        "instruction": instruction,
        "estimates": [round(base, 2), round(second, 2)],
        "reference": round(base, 2),
        "component_evidence": components,
        "weight": 1.0,
    }
    if item_type == "figure":
        row["image_data_uri"] = ONE_PIXEL_PNG

    if variant == "abstain":
        # Two estimates a full point apart. The pair is slid inside the scale rather than clamped
        # to it, because clamping at either end silently shrank the spread back under the ceiling
        # and a fifth of the rows meant to abstain quietly committed instead.
        low = min(base, 3.0)
        row["estimates"] = [round(low, 2), round(low + 1.0, 2)]
    elif variant == "no_reference":
        row["reference"] = None

    if bad_kind == "missing_image":
        row["item_type"] = "figure"
        row.pop("image_data_uri", None)
    elif bad_kind == "missing_instruction":
        row["item_type"] = "text"
        row["instruction"] = ""
        row.pop("image_data_uri", None)
    elif bad_kind == "label_leak":
        row["instruction"] = instruction + " " + _LEAK_FRAGMENT

    return row


def generate(
    count: int,
    seed: int,
    bad_share: float,
    abstain_share: float = 0.0,
    no_reference_share: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[int, str], dict[int, str]]:
    if count < len(CRITERIA):
        raise SystemExit(f"--count must be at least {len(CRITERIA)}: every criterion needs a row")
    for name, share in (
        ("--bad-share", bad_share),
        ("--abstain-share", abstain_share),
        ("--no-reference-share", no_reference_share),
    ):
        if not 0.0 <= share < 0.5:
            raise SystemExit(f"{name} must be at least 0 and below 0.5")
    if bad_share + abstain_share + no_reference_share >= 0.9:
        raise SystemExit("the three shares together must leave rows that are simply admitted")

    rng = random.Random(seed)

    # The first row of each criterion is never touched, so every criterion keeps a denominator and
    # a scale run measures admission rather than the missing-denominator halt.
    protected = set(range(len(CRITERIA)))
    candidates = [i for i in range(count) if i not in protected]
    rng.shuffle(candidates)

    cursor = 0
    bad_count = int(round(count * bad_share))
    chosen_bad = sorted(candidates[cursor : cursor + bad_count])
    cursor += bad_count
    abstain_count = int(round(count * abstain_share))
    chosen_abstain = sorted(candidates[cursor : cursor + abstain_count])
    cursor += abstain_count
    no_ref_count = int(round(count * no_reference_share))
    chosen_no_ref = sorted(candidates[cursor : cursor + no_ref_count])

    kinds = {i: BAD_KINDS[n % len(BAD_KINDS)] for n, i in enumerate(chosen_bad)}
    variants = {i: "abstain" for i in chosen_abstain}
    variants.update({i: "no_reference" for i in chosen_no_ref})

    rotation = rng.randrange(9)
    rows = [build_row(i, rng, kinds.get(i), variants.get(i), rotation) for i in range(count)]
    return rows, kinds, variants


def write_rows(rows: list[dict[str, Any]], out_path: Path) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    out_path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_fixtures.py",
        description="Emit N deterministic synthetic units with a stated share of seeded-bad rows.",
    )
    parser.add_argument("--count", type=int, required=True, help="How many units to emit.")
    parser.add_argument("--seed", type=int, default=20260906, help="Seed (default: 20260906).")
    parser.add_argument(
        "--bad-share",
        type=float,
        default=0.05,
        help="Share of rows seeded with a tier-1 refusal defect (default: 0.05).",
    )
    parser.add_argument(
        "--abstain-share",
        type=float,
        default=0.03,
        help="Share of rows whose two estimates disagree, so the unit abstains (default: 0.03).",
    )
    parser.add_argument(
        "--no-reference-share",
        type=float,
        default=0.02,
        help="Share of rows with no reference, excluded from the denominator (default: 0.02).",
    )
    parser.add_argument("--out", required=True, help="Output JSONL path (gitignored by convention).")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Generate twice and confirm the two runs are byte-identical before writing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 1

    shares = (args.bad_share, args.abstain_share, args.no_reference_share)
    rows, kinds, variants = generate(args.count, args.seed, *shares)

    if args.verify:
        again, again_kinds, again_variants = generate(args.count, args.seed, *shares)
        if rows != again or kinds != again_kinds or variants != again_variants:
            print("DETERMINISM: FAILED - two runs of the same seed differ", file=sys.stderr)
            return 1
        print("DETERMINISM: two runs of the same seed are identical")

    digest = write_rows(rows, Path(args.out))
    by_kind: dict[str, int] = {}
    for kind in kinds.values():
        by_kind[kind] = by_kind.get(kind, 0) + 1
    tally = ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())) or "none"
    print(f"UNITS: {len(rows)} written to {Path(args.out).as_posix()}")
    by_variant: dict[str, int] = {}
    for kind in variants.values():
        by_variant[kind] = by_variant.get(kind, 0) + 1
    variant_tally = ", ".join(f"{k}={v}" for k, v in sorted(by_variant.items())) or "none"
    print(f"SEEDED_BAD: {len(kinds)} of {len(rows)} rows ({tally})")
    print(f"VARIANTS: {len(variants)} of {len(rows)} rows ({variant_tally}) - not defects")
    print(f"SEED: {args.seed}")
    print(f"SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
