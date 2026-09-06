"""Fail-closed validation: refusals (tier 1, one unit) and halts (tier 2, the
whole run). Extracted from a private grading-measurement harness's admission
path. Source citations (this repo's own planning files, not the private
system): EXTRACTION_PLAN.md sections 3.1 and 3.4, and CONTRACT.md section 6,
which pins every code, every function signature, and the exact regex below.

The label-leak regex has no leading `\\b`: `_` is a word character, so a
leading word-boundary assertion fails exactly where a leak hides, inside an
identifier (CONTRACT.md section 6.3; the lesson this is drawn from
recorded a leading `\\b` silently swallowing real leaks and reporting zero).
Only value-carrying patterns count — a bare word is never a hit, because a
prompt that forbids labels has to name them, and a bare-word scan punishes
the prompts that comply hardest.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .provenance import unit_id as _unit_id
from .rubric import CRITERIA, ITEM_TYPES, requires_image, requires_instruction


class FailClosedError(Exception):
    def __init__(self, code: str, unit_id: str | None = None, detail: str = "") -> None:
        super().__init__(code)  # str(exc) == code, so pytest.raises(match=CODE) works
        self.code = code
        self.unit_id = unit_id
        self.detail = detail


class RefusalError(FailClosedError):
    """Tier 1: one unit is rejected; the run continues; verdict is forced to HOLD."""


class HaltError(FailClosedError):
    """Tier 2: the whole run stops."""


# ---------------------------------------------------------------------------
# Label-leak detection
# ---------------------------------------------------------------------------

LEAK_EXEMPT_ANCHOR: str = "LABEL-LEAK-DETECTOR-SOURCE"

_LABEL_WORDS = ("level", "score", "rating", "grade", "mark", "band")

# No leading \b on purpose: "_" is a word character, so \b would fail exactly
# where a leak hides, inside an identifier. The separator class is repeated,
# not a single optional character, because the JSON form quote-colon-space
# slips through a single optional separator.
LABEL_LEAK_RE: re.Pattern[str] = re.compile(
    r"(?<![a-z])(?:" + "|".join(_LABEL_WORDS) + r")[ _\"'-]*[:=]?[ \"']*[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE,
)
VERDICT_LEAK_RE: re.Pattern[str] = re.compile(
    r"(?:UN)?MET[ _\"'-]*[:=][ \"']*\S", re.IGNORECASE
)


def count_label_leaks(text: str, *, honour_exemption: bool = False) -> int:
    """Split on lines, sum matches of both patterns over every line.

    `honour_exemption=True` additionally skips any line carrying `LEAK_EXEMPT_ANCHOR`. That skip
    is legitimate ONLY for a caller that scans this repository's own committed documentation,
    which has to spell out example leaks in order to explain them — `scan_paths_for_leaks` below
    is the one caller allowed to pass it.

    The default is `False` on purpose. R1 in the round-2 hostile review: this function used to
    honour the exemption unconditionally, so it also served `scan_text_for_leaks` — the LIVE
    ADMISSION PATH every untrusted instruction and response passes through in `build_payload`.
    An instruction that pasted the anchor token onto a real value-carrying leak switched the
    flagship refusal off and the run returned a clean verdict. The admission path must never pass
    `honour_exemption=True`; a caller that needs the exemption has to say so.
    """
    total = 0
    for line in text.splitlines():
        if honour_exemption and LEAK_EXEMPT_ANCHOR in line:
            continue
        total += len(LABEL_LEAK_RE.findall(line))
        total += len(VERDICT_LEAK_RE.findall(line))
    return total


def scan_text_for_leaks(text: str, uid: str, field: str) -> None:
    # Admission path: honour_exemption is never passed here (default False). An untrusted
    # instruction or response must not be able to switch this refusal off by pasting the
    # repository's own documentation anchor onto a real leak. See count_label_leaks' docstring.
    if count_label_leaks(text) != 0:
        raise RefusalError("LABEL_LEAK_IN_PROMPT", uid, detail=field)


def scan_paths_for_leaks(paths: Iterable[Path]) -> dict[str, int]:
    """{posix_path_string: count} for every readable file given (including a
    zero count); unreadable files are skipped silently — they are not
    evidence.

    This is the repository-scanning path, not the admission path: it is the one caller allowed to
    pass `honour_exemption=True`, because it exists to scan this package's own committed
    documentation, which spells out example leaks on lines carrying LEAK_EXEMPT_ANCHOR in order to
    explain them (see the CLI's `scan` subcommand, the only caller of this function)."""
    result: dict[str, int] = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        result[path.as_posix()] = count_label_leaks(text, honour_exemption=True)
    return result


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

POLICY_FIELDS: tuple[str, ...] = (
    "floor",
    "high_component_min",
    "uniform_fraction",
    "uniform_min_n",
    "spread_max",
    "std_max",
)


@dataclass(frozen=True)
class Policy:
    floor: float
    high_component_min: float
    uniform_fraction: float
    uniform_min_n: int
    spread_max: float
    std_max: float


def _finite_float(value: Any) -> float:
    f = float(value)
    if not math.isfinite(f):
        raise ValueError("not finite")
    return f


def read_policy(path: Path) -> Policy:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HaltError("INVALID_POLICY")
    if not isinstance(data, dict):
        raise HaltError("INVALID_POLICY")

    for key in POLICY_FIELDS:
        if key not in data:
            raise HaltError("MISSING_POLICY_FIELD", detail=key)

    try:
        floor = _finite_float(data["floor"])
        high_component_min = _finite_float(data["high_component_min"])
        uniform_fraction = _finite_float(data["uniform_fraction"])
        uniform_min_n = int(data["uniform_min_n"])
        spread_max = _finite_float(data["spread_max"])
        std_max = _finite_float(data["std_max"])
    except (TypeError, ValueError):
        raise HaltError("INVALID_POLICY")

    if not (0 < uniform_fraction <= 1):
        raise HaltError("INVALID_POLICY")
    if uniform_min_n < 1:
        raise HaltError("INVALID_POLICY")
    if spread_max <= 0:
        raise HaltError("INVALID_POLICY")
    if std_max <= 0:
        raise HaltError("INVALID_POLICY")

    return Policy(
        floor=floor,
        high_component_min=high_component_min,
        uniform_fraction=uniform_fraction,
        uniform_min_n=uniform_min_n,
        spread_max=spread_max,
        std_max=std_max,
    )


# ---------------------------------------------------------------------------
# Reading units
# ---------------------------------------------------------------------------


def read_units(path: Path, allow_nonsynthetic: bool = False) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise HaltError("MALFORMED_UNITS_FILE")

    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise HaltError("MALFORMED_UNITS_FILE")
        if not isinstance(record, dict):
            raise HaltError("MALFORMED_UNITS_FILE")
        if record.get("synthetic") is not True and not allow_nonsynthetic:
            raise HaltError("NOT_SYNTHETIC")
        records.append(record)

    if not records:
        raise HaltError("EMPTY_UNITS_FILE")
    return records


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------


def _resolve_image(record: Mapping[str, Any]) -> tuple[bytes | None, str | None, str | None]:
    """Returns (image_bytes, media_type, source); (None, None, None) when the
    record carries no image source at all."""
    image_data_uri = str(record.get("image_data_uri") or "")
    if image_data_uri:
        header, sep, b64_payload = image_data_uri.partition(",")
        if not sep or not header.startswith("data:image/") or not header.endswith(";base64"):
            raise RefusalError("INVALID_IMAGE_PAYLOAD")
        try:
            image_bytes = base64.b64decode(b64_payload, validate=True)
        except (ValueError, binascii.Error):
            raise RefusalError("INVALID_IMAGE_PAYLOAD")
        media_type = header[len("data:"):-len(";base64")]
        return image_bytes, media_type, "inline"

    image_path = str(record.get("image_path") or "")
    if image_path:
        p = Path(image_path)
        if not p.is_file():
            raise RefusalError("UNRESOLVED_IMAGE")
        image_bytes = p.read_bytes()
        media_type = str(record.get("image_media_type") or "") or "image/*"
        return image_bytes, media_type, image_path

    return None, None, None


def build_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Order of operations is binding — the error a bad record produces
    depends on it (CONTRACT.md section 6.7)."""
    criterion = str(record.get("criterion") or "").upper()
    if criterion not in CRITERIA:
        raise HaltError("UNKNOWN_CRITERION")

    item_type = str(record.get("item_type") or "")
    if item_type not in ITEM_TYPES:
        raise HaltError("UNKNOWN_ITEM_TYPE")

    instruction = str(record.get("instruction") or "")
    if requires_instruction(item_type) and not instruction.strip():
        raise RefusalError("MISSING_INSTRUCTION")

    scan_text_for_leaks(instruction, "", "instruction")
    response_text = str(record.get("response_text") or "")
    scan_text_for_leaks(response_text, "", "response_text")

    image_bytes, media_type, source = _resolve_image(record)

    if requires_image(item_type) and image_bytes is None:
        raise RefusalError("INPUT_IMAGE_REQUIRED")

    image_slot: dict[str, Any] = {
        "type": "input_image",
        "required": requires_image(item_type),
        "media_type": media_type,
        "sha256": hashlib.sha256(image_bytes).hexdigest() if image_bytes else None,
        "bytes_base64": base64.b64encode(image_bytes).decode("ascii") if image_bytes else None,
        "source": source,
    }
    payload: dict[str, Any] = {
        "criterion": criterion,
        "item_type": item_type,
        "messages": [
            {"type": "input_text", "text": response_text},
            {"type": "input_instruction", "text": instruction},
            image_slot,
        ],
        "image_slot": image_slot,
    }

    if not isinstance(payload["image_slot"], dict) or payload["messages"][-1]["type"] != "input_image":
        raise RefusalError("IMAGE_SLOT_MISSING")  # unreachable by design
    return payload


# ---------------------------------------------------------------------------
# Unit admission helpers
# ---------------------------------------------------------------------------


def validate_unit(record: Mapping[str, Any], seen: set[str]) -> str:
    item_id = str(record.get("item_id") or "")
    if not item_id:
        raise HaltError("MISSING_ITEM_ID")

    criterion = str(record.get("criterion") or "").upper()
    if criterion not in CRITERIA:
        raise HaltError("UNKNOWN_CRITERION")

    uid = _unit_id(item_id, criterion)
    if uid in seen:
        raise HaltError("DUPLICATE_UNIT", uid)
    seen.add(uid)
    return uid


def component_evidence(record: Mapping[str, Any], uid: str) -> tuple[float, ...]:
    raw = record.get("component_evidence")
    if not isinstance(raw, list) or len(raw) == 0:
        raise HaltError("MISSING_COMPONENT_EVIDENCE", uid)
    try:
        values = tuple(float(v) for v in raw)
    except (TypeError, ValueError):
        raise HaltError("MISSING_COMPONENT_EVIDENCE", uid)
    if not all(math.isfinite(v) for v in values):
        raise HaltError("MISSING_COMPONENT_EVIDENCE", uid)
    return values


def estimate_values(record: Mapping[str, Any], uid: str) -> tuple[float | None, ...]:
    """Validate the raw `estimates` list before the abstain rule ever sees it.

    The estimate field is the single most likely field to arrive malformed, because it is the
    output of the untrusted, non-deterministic grader this package exists to distrust. Letting a
    bad element reach `abstain.decide` turned a documented, named refusal into a raw ValueError
    that escaped the typed system entirely and surfaced as an unnamed UNEXPECTED_ERROR. Every
    element is checked here instead, and a bad one halts with the code the README already
    documents for it.

    `None` elements survive: a missing estimate is not a malformed one, and `decide` filters them.
    """
    raw = record.get("estimates")
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise HaltError("INVALID_ESTIMATE_VALUE", uid, detail="estimates is not a list")
    values: list[float | None] = []
    for element in raw:
        if element is None:
            values.append(None)
            continue
        if isinstance(element, bool):
            raise HaltError("INVALID_ESTIMATE_VALUE", uid, detail="estimate is a boolean")
        try:
            number = float(element)
        except (TypeError, ValueError):
            raise HaltError("INVALID_ESTIMATE_VALUE", uid, detail="estimate is not a number")
        if not math.isfinite(number):
            raise HaltError("INVALID_ESTIMATE_VALUE", uid, detail="estimate is not finite")
        values.append(number)
    return tuple(values)


def unit_weight(record: Mapping[str, Any], uid: str) -> float:
    if "weight" not in record:
        return 1.0
    try:
        w = float(record["weight"])
    except (TypeError, ValueError):
        raise HaltError("INVALID_WEIGHT", uid)
    if not math.isfinite(w) or w < 0:
        raise HaltError("INVALID_WEIGHT", uid)
    return w


# ---------------------------------------------------------------------------
# Admitted unit and the anomaly halt
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdmittedUnit:
    """One unit that passed every gate.

    `reference` is collected, validated as a finite number, and stored here - and is then used by
    nothing. That is a BOUNDARY, not an unfinished feature. Comparing an estimate against a
    reference is how an accuracy figure is produced, and this package makes no accuracy claim: the
    fixtures are invented, so any figure computed from them would be a number about invented data
    wearing the clothes of a result. The field is admitted and validated because a unit whose
    reference is malformed is a malformed unit, and it stops there on purpose. Nothing in `src/`
    reads `.reference` except this declaration, and `tests/test_reference_boundary.py` fails if a
    reference value ever reaches an output file.
    """

    unit_id: str
    item_id: str
    criterion: str
    item_type: str
    estimate: float
    # Deliberately terminal: validated, stored, never read. See the class docstring above.
    reference: float
    components: tuple[float, ...]
    weight: float
    input_sha256: str
    image_sha256: str | None


def check_anomalies(units: Sequence[AdmittedUnit], policy: Policy) -> None:
    # 1. A value at the floor with high sub-values is a broken measurement,
    #    not a low one.
    for unit in units:
        mean_components = sum(unit.components) / len(unit.components)
        if unit.estimate <= policy.floor and mean_components >= policy.high_component_min:
            raise HaltError("ANOMALOUS_ESTIMATE", unit.unit_id)

    # 2. Criteria are checked in CRITERIA order so the halt is deterministic.
    for criterion in CRITERIA:
        rows = [u for u in units if u.criterion == criterion]
        if len(rows) < policy.uniform_min_n:
            continue
        counts: dict[float, int] = {}
        for u in rows:
            counts[u.estimate] = counts.get(u.estimate, 0) + 1
        most_common = max(counts.values())
        if most_common / len(rows) > policy.uniform_fraction:
            raise HaltError("ANOMALOUS_DISTRIBUTION", detail=criterion)
