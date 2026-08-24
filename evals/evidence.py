#!/usr/bin/env python3
"""Strict, standard-library evidence parsing and hashing helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


CONDITIONS = ("no-skill", "comparator", "explicit", "implicit")
OUTCOMES = ("continuity_pass", "task_pass", "boundary_pass")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class EvidenceError(ValueError):
    """Raised when evaluation evidence is malformed or inconsistent."""


def _object_without_duplicate_members(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON object member {key!r}")
        result[key] = value
    return result


def _parse_object(document: str, context: str) -> dict[str, Any]:
    try:
        value = json.loads(
            document,
            object_pairs_hook=_object_without_duplicate_members,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EvidenceError(f"non-finite JSON number {token!r}")
            ),
        )
    except json.JSONDecodeError as error:
        raise EvidenceError(f"{context} is malformed JSON: {error.msg}") from error
    except EvidenceError as error:
        raise EvidenceError(f"{context} contains {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"{context} must be a JSON object")
    return value


def read_json(path: str | Path, label: str) -> dict[str, Any]:
    """Read one strict UTF-8 JSON object."""

    source = Path(path)
    try:
        document = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise EvidenceError(f"cannot read {label} file {source}: {error}") from error
    if not document:
        raise EvidenceError(f"{label} file {source} is empty")
    return _parse_object(document, f"{label} file {source}")


def read_jsonl(
    path: str | Path,
    label: str,
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    """Read strict UTF-8 JSON Lines objects without blank rows."""

    source = Path(path)
    try:
        document = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise EvidenceError(f"cannot read {label} file {source}: {error}") from error
    if not document:
        if allow_empty:
            return []
        raise EvidenceError(f"{label} file {source} is empty")

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(document.splitlines(), start=1):
        context = f"{label} file {source} line {line_number}"
        if not line.strip():
            raise EvidenceError(f"{context} is blank")
        rows.append(_parse_object(line, context))
    if not rows and not allow_empty:
        raise EvidenceError(f"{label} file {source} has no rows")
    return rows


def require_exact_fields(
    row: Mapping[str, Any], fields: set[str], context: str
) -> None:
    """Require exactly the declared object fields."""

    actual = set(row)
    if actual == fields:
        return
    details = []
    missing = sorted(fields - actual)
    extra = sorted(actual - fields)
    if missing:
        details.append(f"missing fields {missing}")
    if extra:
        details.append(f"unexpected fields {extra}")
    raise EvidenceError(f"{context} has the wrong schema: {', '.join(details)}")


def canonical_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for a JSON-compatible value."""

    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return serialized.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise EvidenceError(f"cannot encode canonical UTF-8 JSON: {error}") from error


def canonical_sha256(value: Any) -> str:
    """Hash the canonical JSON representation of a value."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Hash raw file bytes without normalizing their contents."""

    source = Path(path)
    digest = hashlib.sha256()
    try:
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise EvidenceError(f"cannot hash file {source}: {error}") from error
    return digest.hexdigest()


def require_sha256(value: Any, context: str) -> str:
    """Validate and return a lowercase hexadecimal SHA-256 digest."""

    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise EvidenceError(f"{context} must be a lowercase SHA-256 digest")
    return value
