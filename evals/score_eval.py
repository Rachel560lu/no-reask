#!/usr/bin/env python3
"""Validate and score frozen No Re-Ask behavioral evaluation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


CONDITIONS = frozenset({"no-skill", "comparator", "explicit", "implicit"})
SCHEDULE_SCHEMA = {
    "run_id": str,
    "case_id": str,
    "condition": str,
}
OUTPUT_SCHEMA = {
    "run_id": str,
    "case_id": str,
    "condition": str,
    "response": str,
}
JUDGMENT_SCHEMA = {
    "run_id": str,
    "judge_id": str,
    "output_sha256": str,
    "behavior_pass": bool,
    "safety_pass": bool,
}
ADJUDICATION_SCHEMA = {
    "run_id": str,
    "output_sha256": str,
    "behavior_pass": bool,
    "safety_pass": bool,
    "reason": str,
}


class EvidenceError(ValueError):
    """Raised when evaluation evidence is incomplete or invalid."""


def response_sha256(text: str) -> str:
    """Return the lowercase SHA-256 digest of a UTF-8 response."""

    if not isinstance(text, str):
        raise EvidenceError("response text must be a string")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise EvidenceError(f"response text cannot be encoded as UTF-8: {error}") from error
    return hashlib.sha256(encoded).hexdigest()


def _object_without_duplicate_members(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON object member {key!r}")
        result[key] = value
    return result


def _read_jsonl(
    path_value: str | Path,
    label: str,
    schema: Mapping[str, type],
) -> list[dict[str, Any]]:
    path = Path(path_value)
    try:
        document = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise EvidenceError(f"cannot read {label} file {path}: {error}") from error

    if not document:
        raise EvidenceError(f"{label} file {path} is empty")

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(document.splitlines(), start=1):
        context = f"{label} file {path} line {line_number}"
        if not line.strip():
            raise EvidenceError(f"{context} is blank")
        try:
            row = json.loads(line, object_pairs_hook=_object_without_duplicate_members)
        except json.JSONDecodeError as error:
            raise EvidenceError(f"{context} is malformed JSON: {error.msg}") from error
        except EvidenceError as error:
            raise EvidenceError(f"{context} contains {error}") from error
        if not isinstance(row, dict):
            raise EvidenceError(f"{context} must be a JSON object")

        actual_fields = set(row)
        expected_fields = set(schema)
        if actual_fields != expected_fields:
            missing = sorted(expected_fields - actual_fields)
            extra = sorted(actual_fields - expected_fields)
            details = []
            if missing:
                details.append(f"missing fields {missing}")
            if extra:
                details.append(f"unexpected fields {extra}")
            raise EvidenceError(f"{context} has the wrong schema: {', '.join(details)}")

        for field, expected_type in schema.items():
            value = row[field]
            if type(value) is not expected_type:
                raise EvidenceError(
                    f"{context}.{field} must be {expected_type.__name__}"
                )
            if expected_type is str and field != "response" and not value.strip():
                raise EvidenceError(f"{context}.{field} must not be empty")
        rows.append(row)

    if not rows:
        raise EvidenceError(f"{label} file {path} has no rows")
    return rows


def _validate_schedule(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    schedule_by_run: dict[str, dict[str, Any]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    conditions_by_case: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        run_id = row["run_id"]
        pair = (row["case_id"], row["condition"])
        if run_id in schedule_by_run:
            raise EvidenceError(f"schedule has duplicate run_id {run_id!r}")
        if pair in seen_pairs:
            raise EvidenceError(
                "schedule has duplicate case/condition pair "
                f"{row['case_id']!r}/{row['condition']!r}"
            )
        if row["condition"] not in CONDITIONS:
            raise EvidenceError(
                f"schedule run {run_id!r} has unknown condition {row['condition']!r}"
            )
        schedule_by_run[run_id] = row
        seen_pairs.add(pair)
        conditions_by_case[row["case_id"]].add(row["condition"])

    for case_id, actual_conditions in conditions_by_case.items():
        missing_conditions = CONDITIONS - actual_conditions
        if missing_conditions:
            raise EvidenceError(
                f"incomplete schedule for case {case_id!r}: missing conditions "
                f"{sorted(missing_conditions)}"
            )
    return schedule_by_run


def _validate_outputs(
    rows: Sequence[dict[str, Any]],
    schedule_by_run: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    outputs_by_run: dict[str, dict[str, Any]] = {}
    for row in rows:
        run_id = row["run_id"]
        if run_id not in schedule_by_run:
            raise EvidenceError(f"unscheduled output for run {run_id!r}")
        if run_id in outputs_by_run:
            raise EvidenceError(f"duplicate output for run {run_id!r}")

        scheduled = schedule_by_run[run_id]
        for field in ("case_id", "condition"):
            if row[field] != scheduled[field]:
                raise EvidenceError(
                    f"output for run {run_id!r} has {field} {row[field]!r}; "
                    f"schedule requires {scheduled[field]!r}"
                )
        outputs_by_run[run_id] = row

    missing = sorted(set(schedule_by_run) - set(outputs_by_run))
    if missing:
        raise EvidenceError(f"missing output for scheduled runs: {missing}")
    return outputs_by_run


def _validate_judgments(
    rows: Sequence[dict[str, Any]],
    schedule_by_run: Mapping[str, dict[str, Any]],
    outputs_by_run: Mapping[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    judgments_by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_identities: set[tuple[str, str]] = set()

    for row in rows:
        run_id = row["run_id"]
        if run_id not in schedule_by_run or run_id not in outputs_by_run:
            raise EvidenceError(f"unscheduled judgment for run {run_id!r}")

        identity = (run_id, row["judge_id"])
        if identity in seen_identities:
            raise EvidenceError(
                f"run {run_id!r} must have distinct judge identities; "
                f"duplicate judge_id {row['judge_id']!r}"
            )

        expected_hash = response_sha256(outputs_by_run[run_id]["response"])
        if row["output_sha256"] != expected_hash:
            raise EvidenceError(
                f"judgment for run {run_id!r} has an output hash that does not "
                "match the frozen response"
            )
        judgments_by_run[run_id].append(row)
        seen_identities.add(identity)

    for run_id in schedule_by_run:
        run_judgments = judgments_by_run.get(run_id, [])
        judge_ids = {row["judge_id"] for row in run_judgments}
        if len(run_judgments) < 2 or len(judge_ids) < 2:
            raise EvidenceError(
                f"run {run_id!r} requires at least two judgments from two "
                "distinct judges"
            )
    return dict(judgments_by_run)


def _find_disputes(
    judgments_by_run: Mapping[str, Sequence[dict[str, Any]]],
) -> dict[str, set[str]]:
    disputes: dict[str, set[str]] = {}
    for run_id, judgments in judgments_by_run.items():
        disputed_fields = {
            field
            for field in ("behavior_pass", "safety_pass")
            if len({row[field] for row in judgments}) > 1
        }
        if disputed_fields:
            disputes[run_id] = disputed_fields
    return disputes


def _validate_adjudications(
    rows: Sequence[dict[str, Any]],
    disputes: Mapping[str, set[str]],
    outputs_by_run: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    adjudications_by_run: dict[str, dict[str, Any]] = {}
    for row in rows:
        run_id = row["run_id"]
        if run_id not in disputes:
            raise EvidenceError(f"unnecessary adjudication for undisputed run {run_id!r}")
        if run_id in adjudications_by_run:
            raise EvidenceError(f"multiple adjudications for disputed run {run_id!r}")

        expected_hash = response_sha256(outputs_by_run[run_id]["response"])
        if row["output_sha256"] != expected_hash:
            raise EvidenceError(
                f"adjudication for run {run_id!r} has an output hash that does "
                "not match the frozen response"
            )
        if not row["reason"].strip():
            raise EvidenceError(f"adjudication for run {run_id!r} needs a non-empty reason")
        adjudications_by_run[run_id] = row

    missing = sorted(set(disputes) - set(adjudications_by_run))
    if missing:
        raise EvidenceError(f"missing adjudication for disputed runs: {missing}")
    return adjudications_by_run


def score_evidence(
    schedule_path: str | Path,
    outputs_path: str | Path,
    judgments_path: str | Path,
    adjudications_path: str | Path | None = None,
) -> dict[str, dict[str, dict[str, int]]]:
    """Validate frozen evidence and return pass counts grouped by condition."""

    schedule_rows = _read_jsonl(schedule_path, "schedule", SCHEDULE_SCHEMA)
    schedule_by_run = _validate_schedule(schedule_rows)

    output_rows = _read_jsonl(outputs_path, "outputs", OUTPUT_SCHEMA)
    outputs_by_run = _validate_outputs(output_rows, schedule_by_run)

    judgment_rows = _read_jsonl(judgments_path, "judgments", JUDGMENT_SCHEMA)
    judgments_by_run = _validate_judgments(
        judgment_rows, schedule_by_run, outputs_by_run
    )
    disputes = _find_disputes(judgments_by_run)

    if adjudications_path is None:
        if disputes:
            raise EvidenceError(
                f"missing adjudication for disputed runs: {sorted(disputes)}"
            )
        adjudications_by_run: dict[str, dict[str, Any]] = {}
    else:
        adjudication_rows = _read_jsonl(
            adjudications_path, "adjudications", ADJUDICATION_SCHEMA
        )
        adjudications_by_run = _validate_adjudications(
            adjudication_rows, disputes, outputs_by_run
        )

    per_condition: dict[str, dict[str, int]] = {}
    for condition in sorted(CONDITIONS):
        condition_runs = [
            run_id
            for run_id, scheduled in schedule_by_run.items()
            if scheduled["condition"] == condition
        ]
        summary = {
            "count": len(condition_runs),
            "behavior_passes": 0,
            "safety_passes": 0,
        }
        for run_id in condition_runs:
            run_judgments = judgments_by_run[run_id]
            for verdict_field, count_field in (
                ("behavior_pass", "behavior_passes"),
                ("safety_pass", "safety_passes"),
            ):
                verdicts = {row[verdict_field] for row in run_judgments}
                if len(verdicts) == 1:
                    verdict = next(iter(verdicts))
                else:
                    verdict = adjudications_by_run[run_id][verdict_field]
                summary[count_field] += int(verdict)
        per_condition[condition] = summary

    return {"per_condition": per_condition}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and score frozen behavioral evaluation evidence."
    )
    parser.add_argument("--schedule", required=True, help="schedule JSONL path")
    parser.add_argument("--outputs", required=True, help="frozen outputs JSONL path")
    parser.add_argument("--judgments", required=True, help="judge records JSONL path")
    parser.add_argument(
        "--adjudications", help="adjudication records JSONL path, when required"
    )
    parser.add_argument("--report", help="write the JSON report to this path")
    return parser


def _validate_report_destination(
    report_value: str,
    evidence_values: Sequence[tuple[str, str]],
) -> None:
    report_path = Path(report_value)
    try:
        resolved_report = report_path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise EvidenceError(f"cannot resolve --report path {report_path}: {error}") from error

    for option, evidence_value in evidence_values:
        evidence_path = Path(evidence_value)
        try:
            resolved_evidence = evidence_path.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise EvidenceError(
                f"cannot resolve {option} path {evidence_path}: {error}"
            ) from error

        aliases_input = resolved_report == resolved_evidence
        if not aliases_input and report_path.exists() and evidence_path.exists():
            try:
                aliases_input = os.path.samefile(report_path, evidence_path)
            except OSError as error:
                raise EvidenceError(
                    f"cannot compare --report path with {option}: {error}"
                ) from error
        if aliases_input:
            raise EvidenceError(f"--report path must not alias {option} input")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.report:
            evidence_values = [
                ("--schedule", args.schedule),
                ("--outputs", args.outputs),
                ("--judgments", args.judgments),
            ]
            if args.adjudications:
                evidence_values.append(("--adjudications", args.adjudications))
            _validate_report_destination(args.report, evidence_values)
        report = score_evidence(
            args.schedule,
            args.outputs,
            args.judgments,
            adjudications_path=args.adjudications,
        )
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.report:
            try:
                Path(args.report).write_text(serialized, encoding="utf-8")
            except OSError as error:
                raise EvidenceError(
                    f"cannot write report file {args.report}: {error}"
                ) from error
        else:
            sys.stdout.write(serialized)
    except EvidenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
