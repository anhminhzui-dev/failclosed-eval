"""Optional MLflow tracking for a completed run.

MLflow is never a runtime dependency: the import is attempted here, and nowhere else in the
package, so `import failclosed_eval` never fails and never touches the network when MLflow is
absent. Only validity counts, hashes, and the verdict ever reach the tracker - the object this
module receives (`summary_to_dict(RunSummary)`) structurally contains no estimate, reference,
component, or error value, so there is nothing else it could log even by accident.
"""
from __future__ import annotations

from typing import Any, Mapping

try:
    import mlflow  # type: ignore[import-not-found]
except ImportError:  # MLflow is an optional extra; its absence is the default case, not an error.
    mlflow = None  # type: ignore[assignment]

MLFLOW_AVAILABLE: bool = mlflow is not None

LOGGED_METRIC_KEYS: tuple[str, ...] = (
    "units_selected",
    "units_admitted",
    "units_refused",
    "units_abstained",
    "units_missing_reference",
)
LOGGED_PARAM_KEYS: tuple[str, ...] = (
    "units_sha256",
    "policy_sha256",
    "package_version",
    "generated_utc",
)
LOGGED_TAG_KEYS: tuple[str, ...] = ("verdict", "halt_code")


class NullTracker:
    """The default tracker. Does nothing, requires nothing, installs nothing."""

    def log_run(self, summary: Mapping[str, Any]) -> None:
        return None


class MlflowTracker:
    """Logs validity counts only. Never constructed unless MLflow is importable."""

    def __init__(self, experiment: str = "failclosed-eval") -> None:
        if mlflow is None:
            # get_tracker() is the only caller and it never reaches here when MLflow is absent;
            # this guard exists so a direct construction fails loudly rather than half-working.
            raise RuntimeError("MlflowTracker constructed without mlflow installed")
        mlflow.set_experiment(experiment)

    def log_run(self, summary: Mapping[str, Any]) -> None:
        refusals_by_code = summary.get("refusals_by_code") or {}
        criteria_without_denominator = summary.get("criteria_without_denominator") or []
        with mlflow.start_run():
            for key in LOGGED_METRIC_KEYS:
                if key in summary:
                    mlflow.log_metric(key, summary[key])
            for code, count in refusals_by_code.items():
                mlflow.log_metric(f"refused_{code}", count)
            mlflow.log_metric(
                "criteria_without_denominator_count", len(criteria_without_denominator)
            )
            for key in LOGGED_PARAM_KEYS:
                if key in summary:
                    mlflow.log_param(key, summary[key])
            for key in LOGGED_TAG_KEYS:
                if key in summary:
                    mlflow.set_tag(key, summary[key])


def get_tracker(enabled: bool = False, experiment: str = "failclosed-eval") -> Any:
    """Never raises, never installs anything. A NullTracker unless MLflow was both requested and
    is importable."""
    if enabled and MLFLOW_AVAILABLE:
        return MlflowTracker(experiment)
    return NullTracker()
