"""failclosed-eval: a fail-closed admission layer for measuring a
non-deterministic grader on synthetic data. See README.md for the honest
claim. Importing this package never imports `cli`, `tracking`, `argparse`,
or any optional dependency (CONTRACT.md section 8)."""
from __future__ import annotations

__version__ = "0.1.0"

from .rubric import CRITERIA, CRITERION_QUESTIONS, ITEM_TYPES
from .provenance import (
    Provenance,
    build_provenance,
    canonical_hash,
    canonical_json,
    file_hash,
    text_hash,
    unit_id,
)
from .abstain import Decision, decide, round_to_step
from .validators import (
    AdmittedUnit,
    FailClosedError,
    HaltError,
    LABEL_LEAK_RE,
    LEAK_EXEMPT_ANCHOR,
    Policy,
    POLICY_FIELDS,
    RefusalError,
    VERDICT_LEAK_RE,
    build_payload,
    check_anomalies,
    component_evidence,
    count_label_leaks,
    estimate_values,
    read_policy,
    read_units,
    scan_paths_for_leaks,
    scan_text_for_leaks,
    unit_weight,
    validate_unit,
)
from .runner import (
    CriterionCounts,
    RunSummary,
    denominator_line,
    halt_line,
    run,
    summary_to_dict,
    verdict_for,
)

__all__ = [
    "CRITERIA",
    "ITEM_TYPES",
    "CRITERION_QUESTIONS",
    "FailClosedError",
    "RefusalError",
    "HaltError",
    "Policy",
    "POLICY_FIELDS",
    "AdmittedUnit",
    "LABEL_LEAK_RE",
    "VERDICT_LEAK_RE",
    "LEAK_EXEMPT_ANCHOR",
    "count_label_leaks",
    "estimate_values",
    "scan_text_for_leaks",
    "scan_paths_for_leaks",
    "read_policy",
    "read_units",
    "build_payload",
    "validate_unit",
    "component_evidence",
    "unit_weight",
    "check_anomalies",
    "Decision",
    "decide",
    "round_to_step",
    "Provenance",
    "canonical_json",
    "canonical_hash",
    "text_hash",
    "file_hash",
    "unit_id",
    "build_provenance",
    "CriterionCounts",
    "RunSummary",
    "run",
    "verdict_for",
    "denominator_line",
    "halt_line",
    "summary_to_dict",
]
