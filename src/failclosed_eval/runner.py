"""The run loop: admits units, applies refusals and halts, and reports a
verdict. Extracted from a private grading-measurement harness's run loop.
Source citations (this repo's own planning files): EXTRACTION_PLAN.md
sections 3.1 and 4; CONTRACT.md section 7 pins the binding sequence, the
output file shapes, and the denominator-line format below exactly.

`run` never raises FailClosedError: a halt is caught and reported as
`halt_code` on a HOLD summary. Any other exception propagates unchanged — a
bug must be loud; only the CLI (a G3-owned file) converts an unexpected
exception into a HOLD at the process boundary.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__ as _PACKAGE_VERSION
from . import abstain
from .provenance import build_provenance, file_hash
from .rubric import CRITERIA
from .validators import (
    AdmittedUnit,
    HaltError,
    RefusalError,
    build_payload,
    check_anomalies,
    component_evidence,
    estimate_values,
    read_policy,
    read_units,
    unit_weight,
    validate_unit,
)


@dataclass
class CriterionCounts:
    selected: int = 0
    admitted: int = 0
    refused: int = 0
    abstained: int = 0
    missing_reference: int = 0
    effective_weight: float = 0.0


@dataclass
class RunSummary:
    verdict: str
    halt_code: str | None
    halt_unit_id: str | None
    criteria: dict[str, CriterionCounts]
    refusals_by_code: dict[str, int]
    units_selected: int
    units_admitted: int
    units_refused: int
    units_abstained: int
    units_missing_reference: int
    criteria_without_denominator: list[str]
    units_sha256: str
    policy_sha256: str
    generated_utc: str
    package_version: str


def _generated_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trace_row(
    uid: str,
    criterion: str,
    state: str,
    code: str | None,
    input_sha256: str | None = None,
    image_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "unit_id": uid,
        "criterion": criterion,
        "state": state,
        "code": code,
        "input_sha256": input_sha256,
        "image_sha256": image_sha256,
    }


def _hold_summary(
    halt_code: str,
    halt_unit_id: str | None,
    units_sha256: str,
    policy_sha256: str,
    generated_utc: str,
) -> RunSummary:
    return RunSummary(
        verdict="HOLD",
        halt_code=halt_code,
        halt_unit_id=halt_unit_id,
        criteria={c: CriterionCounts() for c in CRITERIA},
        refusals_by_code={},
        units_selected=0,
        units_admitted=0,
        units_refused=0,
        units_abstained=0,
        units_missing_reference=0,
        criteria_without_denominator=[],
        units_sha256=units_sha256,
        policy_sha256=policy_sha256,
        generated_utc=generated_utc,
        package_version=_PACKAGE_VERSION,
    )


def _finish(
    summary: RunSummary,
    trace: list[dict[str, Any]],
    out_dir: Path | None,
    tracker: Any | None,
    halt_detail: str = "",
) -> RunSummary:
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(
            json.dumps(summary_to_dict(summary), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        with (out_dir / "trace.jsonl").open("w", encoding="utf-8") as fh:
            for row in trace:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        halt_path = out_dir / "halt.json"
        if summary.halt_code is not None:
            halt_path.write_text(
                json.dumps(
                    {
                        "code": summary.halt_code,
                        "unit_id": summary.halt_unit_id,
                        "detail": halt_detail,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            halt_path.unlink(missing_ok=True)

    if tracker is not None:
        tracker.log_run(summary_to_dict(summary))

    return summary


def run(
    units_path: Path,
    policy_path: Path,
    out_dir: Path | None = None,
    *,
    allow_nonsynthetic: bool = False,
    tracker: Any | None = None,
) -> RunSummary:
    generated_utc = _generated_utc()

    try:
        units_sha256 = file_hash(units_path)
    except OSError:
        summary = _hold_summary("MALFORMED_UNITS_FILE", None, "", "", generated_utc)
        return _finish(summary, [], out_dir, tracker)

    try:
        policy_sha256 = file_hash(policy_path)
    except OSError:
        summary = _hold_summary("INVALID_POLICY", None, units_sha256, "", generated_utc)
        return _finish(summary, [], out_dir, tracker)

    criteria: dict[str, CriterionCounts] = {c: CriterionCounts() for c in CRITERIA}
    refusals_by_code: dict[str, int] = {}
    trace: list[dict[str, Any]] = []
    admitted_units: list[AdmittedUnit] = []
    criteria_without_denominator: list[str] = []

    halt_code: str | None = None
    halt_unit_id: str | None = None
    halt_detail: str = ""

    try:
        policy = read_policy(policy_path)
        records = read_units(units_path, allow_nonsynthetic)
        seen: set[str] = set()

        for record in records:
            uid = validate_unit(record, seen)
            criterion = str(record.get("criterion") or "").upper()
            criteria[criterion].selected += 1

            try:
                payload = build_payload(record)
            except RefusalError as exc:
                criteria[criterion].refused += 1
                refusals_by_code[exc.code] = refusals_by_code.get(exc.code, 0) + 1
                trace.append(_trace_row(uid, criterion, "refused", exc.code))
                continue

            components = component_evidence(record, uid)
            weight = unit_weight(record, uid)

            estimates = estimate_values(record, uid)
            decision = abstain.decide(estimates, policy.spread_max, policy.std_max)
            if decision.action == "ABSTAIN":
                criteria[criterion].abstained += 1
                trace.append(_trace_row(uid, criterion, "abstained", None))
                continue

            if record.get("reference") is None:
                criteria[criterion].missing_reference += 1
                trace.append(_trace_row(uid, criterion, "excluded_reference", None))
                continue

            try:
                estimate = float(decision.value)
                reference = float(record.get("reference"))
                if not (math.isfinite(estimate) and math.isfinite(reference)):
                    raise ValueError("non-finite")
            except (TypeError, ValueError):
                raise HaltError("INVALID_ESTIMATE_VALUE", uid)

            prov = build_provenance(uid, payload)
            admitted_units.append(
                AdmittedUnit(
                    unit_id=uid,
                    item_id=str(record.get("item_id") or ""),
                    criterion=criterion,
                    item_type=str(record.get("item_type") or ""),
                    estimate=estimate,
                    reference=reference,
                    components=components,
                    weight=weight,
                    input_sha256=prov.input_sha256,
                    image_sha256=prov.image_sha256,
                )
            )
            criteria[criterion].admitted += 1
            criteria[criterion].effective_weight += weight
            trace.append(
                _trace_row(uid, criterion, "admitted", None, prov.input_sha256, prov.image_sha256)
            )

        check_anomalies(admitted_units, policy)

        criteria_without_denominator = [
            c for c in CRITERIA if criteria[c].admitted == 0 or criteria[c].effective_weight <= 0
        ]
        if criteria_without_denominator:
            raise HaltError("MISSING_DENOMINATOR", detail=",".join(criteria_without_denominator))

    except HaltError as exc:
        halt_code = exc.code
        halt_unit_id = exc.unit_id
        halt_detail = exc.detail

    units_selected = sum(c.selected for c in criteria.values())
    units_admitted = sum(c.admitted for c in criteria.values())
    units_refused = sum(c.refused for c in criteria.values())
    units_abstained = sum(c.abstained for c in criteria.values())
    units_missing_reference = sum(c.missing_reference for c in criteria.values())

    summary = RunSummary(
        verdict="HOLD",
        halt_code=halt_code,
        halt_unit_id=halt_unit_id,
        criteria=criteria,
        refusals_by_code=refusals_by_code,
        units_selected=units_selected,
        units_admitted=units_admitted,
        units_refused=units_refused,
        units_abstained=units_abstained,
        units_missing_reference=units_missing_reference,
        criteria_without_denominator=criteria_without_denominator,
        units_sha256=units_sha256,
        policy_sha256=policy_sha256,
        generated_utc=generated_utc,
        package_version=_PACKAGE_VERSION,
    )
    summary.verdict = verdict_for(summary)

    return _finish(summary, trace, out_dir, tracker, halt_detail)


def verdict_for(summary: RunSummary) -> str:
    """Default HOLD is structural: GO only when every condition holds."""
    if (
        summary.halt_code is None
        and summary.units_refused == 0
        and summary.criteria_without_denominator == []
        and summary.units_admitted > 0
    ):
        return "GO"
    return "HOLD"


def denominator_line(summary: RunSummary) -> str:
    """One row per criterion, not one long pipe-joined line.

    Two things changed here after review. The counts are laid out as rows because the single line
    they used to be wrapped into an unreadable block on any ordinary terminal, and a denominator a
    reader cannot line up is not a denominator. And when the run halted, the header says PARTIAL:
    the counts are honest as far as they go, but they stop wherever the halt stopped, and a table
    that looks complete above a HOLD line invites exactly the wrong reading.
    """
    if summary.halt_code is None:
        header = "DENOMINATORS: per criterion, one row each"
    else:
        header = (
            "DENOMINATORS: PARTIAL - the run halted, so these counts cover only the rows "
            "processed before the halt"
        )
    width = max(len(c) for c in CRITERIA)
    rows = [header]
    for criterion in CRITERIA:
        c = summary.criteria[criterion]
        rows.append(
            f"  {criterion:<{width}} n={c.admitted} weight={c.effective_weight:.6g} "
            f"refused={c.refused} abstained={c.abstained} "
            f"reference_excluded={c.missing_reference}"
        )
    return "\n".join(rows)


def halt_line(summary: RunSummary) -> str | None:
    """The one line that says WHERE the run stopped, or None when it did not stop.

    A halt used to reach the operator as a code and nothing else: `halt_unit_id` was written into
    summary.json and never printed, so the person reading the terminal was told that the run
    halted and not told which unit did it. Halts that are not tied to a single unit say so rather
    than printing an empty field.
    """
    if summary.halt_code is None:
        return None
    unit = summary.halt_unit_id if summary.halt_unit_id else "none (halt is not unit-scoped)"
    return f"HALT: {summary.halt_code} unit_id={unit}"


def summary_to_dict(summary: RunSummary) -> dict[str, Any]:
    return {
        "verdict": summary.verdict,
        "halt_code": summary.halt_code,
        "halt_unit_id": summary.halt_unit_id,
        "criteria": {
            criterion: {
                "selected": c.selected,
                "admitted": c.admitted,
                "refused": c.refused,
                "abstained": c.abstained,
                "missing_reference": c.missing_reference,
                "effective_weight": c.effective_weight,
            }
            for criterion, c in summary.criteria.items()
        },
        "refusals_by_code": dict(summary.refusals_by_code),
        "units_selected": summary.units_selected,
        "units_admitted": summary.units_admitted,
        "units_refused": summary.units_refused,
        "units_abstained": summary.units_abstained,
        "units_missing_reference": summary.units_missing_reference,
        "criteria_without_denominator": list(summary.criteria_without_denominator),
        "units_sha256": summary.units_sha256,
        "policy_sha256": summary.policy_sha256,
        "generated_utc": summary.generated_utc,
        "package_version": summary.package_version,
    }
