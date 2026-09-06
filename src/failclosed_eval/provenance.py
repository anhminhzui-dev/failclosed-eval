"""Provenance: canonical hashing so a later reader can prove which exact bytes
produced a unit without holding the bytes.

Extracted from a private grading-measurement harness's provenance layer.
Source citations (this repo's EXTRACTION_PLAN.md / CONTRACT.md, not the
private system): EXTRACTION_PLAN.md section 3.1 ("Streamed file hash in 1 MiB
blocks; canonical sorted-key JSON hash"); CONTRACT.md section 4 pins every
function signature and behaviour below exactly.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CHUNK_BYTES: int = 1024 * 1024


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no extra whitespace, no ASCII escaping."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    """sha256 of canonical_json(value), lowercase hex, 64 characters."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_hash(value: str) -> str:
    """sha256 of str(value), lowercase hex."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    """Stream the file in CHUNK_BYTES blocks; an OSError propagates unchanged."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def unit_id(item_id: str, criterion: str) -> str:
    """f"{item_id}::{criterion}" with criterion upper-cased."""
    return f"{item_id}::{criterion.upper()}"


@dataclass(frozen=True)
class Provenance:
    unit_id: str
    input_sha256: str
    image_sha256: str | None


def build_provenance(uid: str, payload: Mapping[str, Any]) -> Provenance:
    """input_sha256 is the canonical hash of the whole payload (including the
    image slot's own hash); image_sha256 is lifted straight from that slot."""
    return Provenance(
        unit_id=uid,
        input_sha256=canonical_hash(payload),
        image_sha256=payload["image_slot"]["sha256"],
    )
