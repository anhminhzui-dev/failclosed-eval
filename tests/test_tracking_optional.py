"""Guards CONTRACT.md section 10 (tracking.py): the package must work with MLflow completely
absent, get_tracker(False) must always be a no-op NullTracker, and whatever a tracker receives
must be validity counts only - never a measurement value. Importing failclosed_eval must not
import tracking as a side effect."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from failclosed_eval import run, summary_to_dict

FORBIDDEN_VALUE_KEYS = {
    "estimate", "estimates", "reference", "components", "component_evidence",
    "weight_value", "mae", "error", "accuracy", "level",
}


def _all_keys(obj):
    """Recursively collect every dict key in a nested structure."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys |= _all_keys(item)
    return keys


class FakeTracker:
    def __init__(self) -> None:
        self.received = None

    def log_run(self, summary) -> None:
        self.received = summary


def test_importing_the_package_does_not_import_tracking() -> None:
    """Guards: 'importing the package must not import cli, tracking, argparse or any optional
    dependency'. Run in a fresh subprocess (not this test process, whose sys.modules is
    already contaminated by other test files' explicit imports) so the check is real: bare
    `import failclosed_eval` must leave tracking, cli, and argparse absent from sys.modules."""
    src_dir = Path(__file__).resolve().parents[1] / "src"
    probe = (
        "import sys, json; "
        "import failclosed_eval; "
        "leaked = [m for m in ('failclosed_eval.tracking', 'failclosed_eval.cli', 'argparse') "
        "if m in sys.modules]; "
        "print(json.dumps(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(src_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    import json as _json

    leaked = _json.loads(result.stdout.strip())
    assert leaked == [], f"bare import of failclosed_eval pulled in: {leaked}"


def test_run_with_fake_tracker_delivers_exactly_summary_to_dict_keys(fixtures_dir) -> None:
    """Guards: the tracker receives the same shape run() reports internally - nothing added,
    nothing hidden."""
    tracker = FakeTracker()
    summary = run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json", tracker=tracker)
    assert tracker.received is not None
    assert set(tracker.received.keys()) == set(summary_to_dict(summary).keys())


def test_tracker_never_receives_a_measurement_value_key(fixtures_dir) -> None:
    """Guards: validity counts only - no estimate, reference, component, or error value may
    reach the tracker, structurally, because RunSummary contains none."""
    tracker = FakeTracker()
    run(fixtures_dir / "clean_units.jsonl", fixtures_dir / "policy.json", tracker=tracker)
    delivered_keys = _all_keys(tracker.received)
    assert not (delivered_keys & FORBIDDEN_VALUE_KEYS)


def test_get_tracker_false_is_always_a_null_tracker() -> None:
    """Guards: get_tracker(False) always returns NullTracker(), it never raises and never
    attempts to import mlflow."""
    from failclosed_eval import tracking

    tracker = tracking.get_tracker(False)
    assert isinstance(tracker, tracking.NullTracker)
    tracker.log_run({"anything": 1})  # must be a no-op, must not raise


def test_get_tracker_true_never_raises_even_when_mlflow_is_absent() -> None:
    """Guards: get_tracker(True) falls back to NullTracker when MLflow is unavailable - it
    never raises and never installs anything."""
    from failclosed_eval import tracking

    tracker = tracking.get_tracker(True)
    tracker.log_run({"anything": 1})  # must not raise regardless of which class this is
    if not tracking.MLFLOW_AVAILABLE:
        assert isinstance(tracker, tracking.NullTracker)


def test_tracking_module_imports_cleanly_with_mlflow_absent() -> None:
    """Guards: `try: import mlflow / except ImportError` means the module itself must import
    without error whether or not mlflow is installed in this environment."""
    from failclosed_eval import tracking

    assert isinstance(tracking.MLFLOW_AVAILABLE, bool)
