#!/usr/bin/env python3
"""Public-data offline admission run for failclosed-eval.

Reads real, public ELLIPSE-Corpus essays (CC BY-NC-SA 4.0, see PUBLIC_RUN_RECEIPT.md for
citation), builds one unit record per essay following failclosed_eval's own JSONL contract
(read from the repo's README/src, never guessed), and runs ONLY the repo's offline admission
function `validators.build_payload` over every unit -- no model call of any kind is made or
possible from this script.

The first five essays in each block of twenty (index % 20 in 0..4) receive seeded defects so
every reachable Tier-1 refusal code fires at least once on real structure, the same technique
the repo's own scripts/make_fixtures.py already uses for its seeded-bad rows. The seed fragment
for LABEL_LEAK is assembled from parts at runtime, mirroring the repo's own
scripts/make_fixtures.py convention, so this source file never carries a contiguous
value-carrying label of its own.

Nothing here is graded. `estimates`, `component_evidence`, `reference` and the full
run()/CLI `run` pipeline (abstain, anomaly checks, denominators) are OUT OF SCOPE for this
script on purpose: this run measures the admission layer only, so it needs none of that
evidence and fabricates none of it.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_SRC = HERE.parent / "src"
sys.path.insert(0, str(REPO_SRC))

from failclosed_eval.validators import (  # noqa: E402
    LABEL_LEAK_RE,
    VERDICT_LEAK_RE,
    RefusalError,
    build_payload,
    scan_paths_for_leaks,
)
from failclosed_eval.rubric import CRITERIA, CRITERION_QUESTIONS  # noqa: E402

N = 500
parser = argparse.ArgumentParser(description="Reproduce the ELLIPSE admission example offline.")
parser.add_argument("--csv", type=Path, required=True, help="Existing ELLIPSE training CSV")
parser.add_argument("--output", type=Path, required=True, help="New directory outside this checkout")
args = parser.parse_args()
CSV_PATH = args.csv.resolve(strict=True)
PUBLIC_RUN = args.output.resolve()
if PUBLIC_RUN == HERE.parent or HERE.parent in PUBLIC_RUN.parents:
    parser.error("--output must be outside the repository")
UNITS_OUT = PUBLIC_RUN / "units" / f"public_units_n{N}.jsonl"
ESSAYS_TXT_DIR = PUBLIC_RUN / "essays_txt"
RESULT_OUT = PUBLIC_RUN / "out" / "admission_result.json"

# Assembled from fragments at runtime -- never a contiguous banned string in this source file.
_LEAK_FRAGMENT = "lev" + "el" + "_" + "score" + ": 3"

# Deterministic seeding: index % 20 selects a bad kind (0..4) or "clean" (5..19).
SEED_KIND_BY_MOD = {
    0: "missing_image",
    1: "missing_instruction",
    2: "label_leak",
    3: "unresolved_image",
    4: "invalid_image_payload",
}


def load_essays(csv_path: Path, n: int) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for i, row in enumerate(reader):
            if i >= n:
                break
            rows.append(row)
    return rows


def build_unit(index: int, essay_row: dict) -> dict:
    criterion = CRITERIA[index % len(CRITERIA)]
    instruction = CRITERION_QUESTIONS[criterion]
    response_text = essay_row["full_text"]
    seed_kind = SEED_KIND_BY_MOD.get(index % 20, "clean")

    unit: dict = {
        "item_id": f"pub-{index:04d}",
        "criterion": criterion,
        "item_type": "text",
        "instruction": instruction,
        "response_text": response_text,
        # Bookkeeping only -- not read by build_payload(); lets the receipt audit which rows
        # are organic public essay content vs. a deliberately constructed probe row.
        "_source": "ELLIPSE-Corpus (public, real)",
        "_seed_kind": seed_kind,
    }

    if seed_kind == "missing_image":
        unit["item_type"] = "figure"  # requires an image; none is supplied
    elif seed_kind == "missing_instruction":
        unit["instruction"] = ""
    elif seed_kind == "label_leak":
        unit["instruction"] = instruction + " " + _LEAK_FRAGMENT
    elif seed_kind == "unresolved_image":
        unit["item_type"] = "figure"
        unit["image_path"] = str(PUBLIC_RUN / "raw" / "does_not_exist_probe.png")
    elif seed_kind == "invalid_image_payload":
        unit["item_type"] = "figure"
        unit["image_data_uri"] = "data:image/png;base64,!!!not-valid-base64!!!"

    return unit


def main() -> int:
    essays = load_essays(CSV_PATH, N)
    if len(essays) != N:
        raise ValueError("The reproduction needs at least 500 essays")
    units = [build_unit(i, row) for i, row in enumerate(essays)]
    PUBLIC_RUN.mkdir(parents=True, exist_ok=False)

    UNITS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with UNITS_OUT.open("w", encoding="utf-8") as fh:
        for u in units:
            fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
    units_sha256 = hashlib.sha256(UNITS_OUT.read_bytes()).hexdigest()

    # --- Pass 1: build_payload() over every unit (the offline admission layer). ---
    t0 = time.perf_counter()
    valid = 0
    invalid_by_code: dict[str, int] = {}
    seed_kind_outcome: dict[str, dict[str, int]] = {}
    for u, rec in zip(units, essays):
        kind = u["_seed_kind"]
        bucket = seed_kind_outcome.setdefault(kind, {})
        try:
            build_payload(u)
            valid += 1
            bucket["valid"] = bucket.get("valid", 0) + 1
        except RefusalError as exc:
            invalid_by_code[exc.code] = invalid_by_code.get(exc.code, 0) + 1
            bucket[exc.code] = bucket.get(exc.code, 0) + 1
    elapsed = time.perf_counter() - t0

    # --- Pass 2: pattern-level leak counts over every unit's instruction+response_text, ---
    # --- independent of build_payload's short-circuit control flow.                    ---
    label_leak_hits = 0
    verdict_leak_hits = 0
    for u in units:
        for field in ("instruction", "response_text"):
            text = u[field]
            label_leak_hits += len(LABEL_LEAK_RE.findall(text))
            verdict_leak_hits += len(VERDICT_LEAK_RE.findall(text))

    # --- Dump essay bodies as .txt files and run the shipped scanner over them, plus one ---
    # --- seeded-negative probe file (assembled fragments) to prove the scan still fires. ---
    ESSAYS_TXT_DIR.mkdir(parents=True, exist_ok=True)
    for u in units:
        out_path = ESSAYS_TXT_DIR / f"{u['item_id']}.txt"
        out_path.write_text(u["response_text"], encoding="utf-8")
    probe_positive = ("lev" + "el") + "_" + ("score") + ": 9"
    probe_path = ESSAYS_TXT_DIR / "_seeded_negative_probe.txt"
    probe_path.write_text(
        "SEEDED NEGATIVE PROBE -- constructed positive, not a real essay.\n"
        f"{probe_positive}\n",
        encoding="utf-8",
    )
    scan_counts = scan_paths_for_leaks(sorted(ESSAYS_TXT_DIR.glob("*.txt")))
    probe_hit = scan_counts.get(probe_path.as_posix(), 0)
    organic_essay_hits = {
        k: v for k, v in scan_counts.items() if v and not k.endswith("_seeded_negative_probe.txt")
    }

    result = {
        "n_essays": len(essays),
        "csv_sha256": hashlib.sha256(CSV_PATH.read_bytes()).hexdigest(),
        "units_file": str(UNITS_OUT),
        "units_sha256": units_sha256,
        "valid": valid,
        "invalid_total": sum(invalid_by_code.values()),
        "invalid_by_code": dict(sorted(invalid_by_code.items())),
        "seed_kind_outcome": seed_kind_outcome,
        "pattern_hits": {
            "LABEL_LEAK_RE": label_leak_hits,
            "VERDICT_LEAK_RE": verdict_leak_hits,
            "total": label_leak_hits + verdict_leak_hits,
        },
        "scan_files_with_hits": len([k for k, v in scan_counts.items() if v]),
        "scan_files_total": len(scan_counts),
        "organic_essay_hits": organic_essay_hits,
        "seeded_negative_probe_hit_count": probe_hit,
        "seeded_negative_probe_fired": probe_hit > 0,
        "runtime_seconds_build_payload_pass": round(elapsed, 4),
    }
    RESULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    RESULT_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    expected_codes = {
        "INPUT_IMAGE_REQUIRED": 25, "MISSING_INSTRUCTION": 25,
        "LABEL_LEAK_IN_PROMPT": 25, "UNRESOLVED_IMAGE": 25,
        "INVALID_IMAGE_PAYLOAD": 25,
    }
    reproduced = (
        valid == 375 and invalid_by_code == expected_codes
        and label_leak_hits == 25 and verdict_leak_hits == 0
        and len(scan_counts) == 501 and not organic_essay_hits and probe_hit == 1
    )
    return 0 if reproduced else 2


if __name__ == "__main__":
    raise SystemExit(main())
