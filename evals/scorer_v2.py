#!/usr/bin/env python3
"""Validate and score schema-v2 No Re-Ask trajectory evidence."""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from evidence import (
    CONDITIONS,
    OUTCOMES,
    EvidenceError,
    canonical_sha256,
    file_sha256,
    read_json,
    read_jsonl,
    require_exact_fields,
    require_sha256,
)


MANIFEST_FIELDS = {
    "schema_version",
    "experiment_id",
    "result_label",
    "reference_host",
    "model",
    "settings",
    "skill",
    "harness",
    "system_instruction_sha256",
    "comparator_sha256",
    "context_limit",
    "compaction_policy",
    "run_ids",
    "files",
    "analysis",
}
PROMPT_FIELDS = {"case_id", "title", "tags", "messages", "fixture"}
ORACLE_FIELDS = {
    "case_id",
    "continuity_rule",
    "task_rule",
    "boundary_rule",
    "readback_paths",
    "implicit_activation_expected",
}
SCHEDULE_FIELDS = {
    "run_id",
    "case_id",
    "condition",
    "corpus",
    "repetition",
    "seed",
}
OUTPUT_FIELDS = {
    "run_id",
    "case_id",
    "condition",
    "status",
    "trajectory",
    "readbacks",
}
JUDGMENT_FIELDS = {
    "run_id",
    "judge_id",
    "evidence_sha256",
    "case_sha256",
    *OUTCOMES,
}
ADJUDICATION_FIELDS = JUDGMENT_FIELDS | {"reason"}
ROUTING_FIELDS = {"run_id", "activation_observed", "source"}
OUTPUT_STATUSES = {"completed", "crashed", "timed_out", "invalid"}


def evidence_sha256(output: Mapping[str, Any]) -> str:
    return canonical_sha256(output)


def case_sha256(prompt: Mapping[str, Any], oracle: Mapping[str, Any]) -> str:
    return canonical_sha256({"prompt": prompt, "oracle": oracle})


def _non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{context} must be a non-empty string")
    return value


def _validate_manifest(
    manifest: dict[str, Any],
    schedule_path: str | Path,
    prompts_path: str | Path,
    oracle_path: str | Path,
) -> None:
    require_exact_fields(manifest, MANIFEST_FIELDS, "manifest")
    if manifest["schema_version"] != 2:
        raise EvidenceError("manifest.schema_version must be 2")
    _non_empty_string(manifest["experiment_id"], "manifest.experiment_id")
    if manifest["result_label"] not in {"pilot", "formal"}:
        raise EvidenceError("manifest.result_label must be pilot or formal")

    nested = (
        ("reference_host", {"product", "surface", "version", "build"}),
        ("model", {"name", "snapshot"}),
        (
            "skill",
            {
                "sha256",
                "discovery_path",
                "explicit_invocation",
                "inventory",
            },
        ),
        ("harness", {"sha256", "collector_sha256"}),
        ("files", {"schedule_sha256", "prompts_sha256", "oracle_sha256"}),
        (
            "analysis",
            {
                "repetitions",
                "confidence_level",
                "task_noninferiority_margin",
                "bootstrap_samples",
            },
        ),
    )
    for name, fields in nested:
        value = manifest[name]
        if not isinstance(value, dict):
            raise EvidenceError(f"manifest.{name} must be an object")
        require_exact_fields(value, fields, f"manifest.{name}")

    for field in ("product", "surface", "version", "build"):
        _non_empty_string(
            manifest["reference_host"][field], f"manifest.reference_host.{field}"
        )
    for field in ("name", "snapshot"):
        _non_empty_string(manifest["model"][field], f"manifest.model.{field}")
    if not isinstance(manifest["settings"], dict):
        raise EvidenceError("manifest.settings must be an object")
    require_sha256(manifest["skill"]["sha256"], "manifest.skill.sha256")
    require_sha256(manifest["harness"]["sha256"], "manifest.harness.sha256")
    require_sha256(
        manifest["harness"]["collector_sha256"],
        "manifest.harness.collector_sha256",
    )
    require_sha256(
        manifest["system_instruction_sha256"],
        "manifest.system_instruction_sha256",
    )
    require_sha256(manifest["comparator_sha256"], "manifest.comparator_sha256")
    if not isinstance(manifest["skill"]["inventory"], list) or not all(
        isinstance(item, str) and item for item in manifest["skill"]["inventory"]
    ):
        raise EvidenceError("manifest.skill.inventory must be a string list")
    for field in ("discovery_path", "explicit_invocation"):
        _non_empty_string(manifest["skill"][field], f"manifest.skill.{field}")
    if type(manifest["context_limit"]) is not int or manifest["context_limit"] <= 0:
        raise EvidenceError("manifest.context_limit must be a positive integer")
    _non_empty_string(manifest["compaction_policy"], "manifest.compaction_policy")
    if not isinstance(manifest["run_ids"], list) or not all(
        isinstance(run_id, str) and run_id for run_id in manifest["run_ids"]
    ):
        raise EvidenceError("manifest.run_ids must be a string list")
    if len(manifest["run_ids"]) != len(set(manifest["run_ids"])):
        raise EvidenceError("manifest.run_ids contains duplicates")

    files = manifest["files"]
    expected_files = {
        "schedule_sha256": file_sha256(schedule_path),
        "prompts_sha256": file_sha256(prompts_path),
        "oracle_sha256": file_sha256(oracle_path),
    }
    for field, expected in expected_files.items():
        require_sha256(files[field], f"manifest.files.{field}")
        if files[field] != expected:
            raise EvidenceError(f"manifest {field} does not match frozen file")

    analysis = manifest["analysis"]
    if type(analysis["repetitions"]) is not int or analysis["repetitions"] <= 0:
        raise EvidenceError("manifest.analysis.repetitions must be positive")
    if not isinstance(analysis["confidence_level"], (int, float)) or not (
        0 < analysis["confidence_level"] < 1
    ):
        raise EvidenceError("manifest.analysis.confidence_level must be between 0 and 1")
    if not isinstance(analysis["task_noninferiority_margin"], (int, float)) or not (
        0 <= analysis["task_noninferiority_margin"] < 1
    ):
        raise EvidenceError("manifest task noninferiority margin is invalid")
    if type(analysis["bootstrap_samples"]) is not int or analysis["bootstrap_samples"] <= 0:
        raise EvidenceError("manifest.analysis.bootstrap_samples must be positive")


def _load_cases(
    prompts_path: str | Path, oracle_path: str | Path
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    prompts: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(read_jsonl(prompts_path, "prompts"), start=1):
        context = f"prompt row {index}"
        require_exact_fields(row, PROMPT_FIELDS, context)
        case_id = _non_empty_string(row["case_id"], f"{context}.case_id")
        if case_id in prompts:
            raise EvidenceError(f"duplicate prompt case_id {case_id!r}")
        _non_empty_string(row["title"], f"{context}.title")
        if not isinstance(row["tags"], list) or not row["tags"]:
            raise EvidenceError(f"{context}.tags must be a non-empty list")
        if not isinstance(row["messages"], list) or not row["messages"]:
            raise EvidenceError(f"{context}.messages must be a non-empty list")
        if row["fixture"] is not None and not isinstance(row["fixture"], str):
            raise EvidenceError(f"{context}.fixture must be a string or null")
        prompts[case_id] = row

    oracles: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(read_jsonl(oracle_path, "oracle"), start=1):
        context = f"oracle row {index}"
        require_exact_fields(row, ORACLE_FIELDS, context)
        case_id = _non_empty_string(row["case_id"], f"{context}.case_id")
        if case_id in oracles:
            raise EvidenceError(f"duplicate oracle case_id {case_id!r}")
        for field in ("continuity_rule", "task_rule", "boundary_rule"):
            _non_empty_string(row[field], f"{context}.{field}")
        if not isinstance(row["readback_paths"], list):
            raise EvidenceError(f"{context}.readback_paths must be a list")
        if type(row["implicit_activation_expected"]) is not bool:
            raise EvidenceError(f"{context}.implicit_activation_expected must be bool")
        oracles[case_id] = row
    if set(prompts) != set(oracles):
        raise EvidenceError("prompt and oracle case IDs do not match")
    return prompts, oracles


def _load_schedule(
    path: str | Path,
    case_ids: set[str],
    manifest_run_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = read_jsonl(path, "schedule")
    by_run: dict[str, dict[str, Any]] = {}
    groups: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for index, row in enumerate(rows, start=1):
        context = f"schedule row {index}"
        require_exact_fields(row, SCHEDULE_FIELDS, context)
        run_id = _non_empty_string(row["run_id"], f"{context}.run_id")
        if run_id in by_run:
            raise EvidenceError(f"duplicate schedule run_id {run_id!r}")
        if row["case_id"] not in case_ids:
            raise EvidenceError(f"schedule references unknown case {row['case_id']!r}")
        if row["condition"] not in CONDITIONS:
            raise EvidenceError(f"schedule has unknown condition {row['condition']!r}")
        if row["corpus"] not in {"development", "holdout"}:
            raise EvidenceError(f"schedule has unknown corpus {row['corpus']!r}")
        if type(row["repetition"]) is not int or row["repetition"] <= 0:
            raise EvidenceError(f"{context}.repetition must be positive")
        if row["seed"] is not None and type(row["seed"]) is not int:
            raise EvidenceError(f"{context}.seed must be an integer or null")
        group = (row["case_id"], row["corpus"], row["repetition"])
        if row["condition"] in groups[group]:
            raise EvidenceError(f"duplicate case/condition/repetition in {context}")
        groups[group].add(row["condition"])
        by_run[run_id] = row
    for group, actual in groups.items():
        if actual != set(CONDITIONS):
            raise EvidenceError(f"incomplete four-condition schedule for {group}")
    if list(manifest_run_ids) != [row["run_id"] for row in rows]:
        raise EvidenceError("manifest run IDs do not match schedule order")
    return rows, by_run


def _load_outputs(
    path: str | Path, schedule: Mapping[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(read_jsonl(path, "outputs", allow_empty=True), start=1):
        context = f"output row {index}"
        require_exact_fields(row, OUTPUT_FIELDS, context)
        run_id = _non_empty_string(row["run_id"], f"{context}.run_id")
        if run_id not in schedule:
            raise EvidenceError(f"unscheduled output for run {run_id!r}")
        if run_id in outputs:
            raise EvidenceError(f"duplicate output for run {run_id!r}")
        scheduled = schedule[run_id]
        for field in ("case_id", "condition"):
            if row[field] != scheduled[field]:
                raise EvidenceError(f"output {run_id!r} has wrong {field}")
        if row["status"] not in OUTPUT_STATUSES:
            raise EvidenceError(f"output {run_id!r} has invalid status")
        if not isinstance(row["trajectory"], list) or not isinstance(row["readbacks"], dict):
            raise EvidenceError(f"output {run_id!r} has invalid trajectory/readbacks")
        for sequence, event in enumerate(row["trajectory"], start=1):
            if not isinstance(event, dict):
                raise EvidenceError(f"output {run_id!r} event must be an object")
            require_exact_fields(event, {"sequence", "type", "data"}, "trajectory event")
            if event["sequence"] != sequence:
                raise EvidenceError(f"output {run_id!r} event sequence is invalid")
            _non_empty_string(event["type"], "trajectory event type")
            if not isinstance(event["data"], dict):
                raise EvidenceError("trajectory event data must be an object")
        if row["status"] == "completed" and not row["trajectory"]:
            raise EvidenceError(f"completed output {run_id!r} needs a trajectory")
        outputs[run_id] = row
    return outputs


def _load_judgments(
    path: str | Path,
    schedule: Mapping[str, dict[str, Any]],
    outputs: Mapping[str, dict[str, Any]],
    prompts: Mapping[str, dict[str, Any]],
    oracles: Mapping[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities: set[tuple[str, str]] = set()
    for index, row in enumerate(read_jsonl(path, "judgments", allow_empty=True), start=1):
        context = f"judgment row {index}"
        require_exact_fields(row, JUDGMENT_FIELDS, context)
        run_id = _non_empty_string(row["run_id"], f"{context}.run_id")
        judge_id = _non_empty_string(row["judge_id"], f"{context}.judge_id")
        if run_id not in schedule or run_id not in outputs:
            raise EvidenceError(f"unscheduled judgment for run {run_id!r}")
        if outputs[run_id]["status"] != "completed":
            raise EvidenceError(f"noncompleted run {run_id!r} cannot have judgments")
        if (run_id, judge_id) in identities:
            raise EvidenceError(f"duplicate judge identity for run {run_id!r}")
        identities.add((run_id, judge_id))
        expected_evidence = evidence_sha256(outputs[run_id])
        scheduled = schedule[run_id]
        expected_case = case_sha256(
            prompts[scheduled["case_id"]], oracles[scheduled["case_id"]]
        )
        if row["evidence_sha256"] != expected_evidence:
            raise EvidenceError(f"judgment evidence hash mismatch for run {run_id!r}")
        if row["case_sha256"] != expected_case:
            raise EvidenceError(f"judgment case hash mismatch for run {run_id!r}")
        for outcome in OUTCOMES:
            if type(row[outcome]) is not bool:
                raise EvidenceError(f"judgment {outcome} must be bool")
        result[run_id].append(row)
    for run_id, output in outputs.items():
        if output["status"] == "completed" and len(result.get(run_id, [])) < 2:
            raise EvidenceError(f"completed run {run_id!r} requires two judgments")
    return dict(result)


def _disputes(
    judgments: Mapping[str, Sequence[dict[str, Any]]]
) -> dict[str, set[str]]:
    result = {}
    for run_id, rows in judgments.items():
        fields = {
            outcome for outcome in OUTCOMES if len({row[outcome] for row in rows}) > 1
        }
        if fields:
            result[run_id] = fields
    return result


def _load_adjudications(
    path: str | Path | None,
    disputes: Mapping[str, set[str]],
    judgments: Mapping[str, Sequence[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    if path is None:
        if disputes:
            raise EvidenceError(f"missing adjudication for runs {sorted(disputes)}")
        return {}
    result = {}
    for index, row in enumerate(read_jsonl(path, "adjudications", allow_empty=True), start=1):
        context = f"adjudication row {index}"
        require_exact_fields(row, ADJUDICATION_FIELDS, context)
        run_id = row["run_id"]
        if run_id not in disputes:
            raise EvidenceError(f"unnecessary adjudication for run {run_id!r}")
        if run_id in result:
            raise EvidenceError(f"multiple adjudications for run {run_id!r}")
        if row["judge_id"] in {item["judge_id"] for item in judgments[run_id]}:
            raise EvidenceError("adjudicator identity must be independent")
        first = judgments[run_id][0]
        for field in ("evidence_sha256", "case_sha256"):
            if row[field] != first[field]:
                raise EvidenceError(f"adjudication {field} mismatch")
        for outcome in OUTCOMES:
            if type(row[outcome]) is not bool:
                raise EvidenceError(f"adjudication {outcome} must be bool")
        _non_empty_string(row["reason"], f"{context}.reason")
        result[run_id] = row
    if set(result) != set(disputes):
        raise EvidenceError(f"missing adjudication for runs {sorted(set(disputes)-set(result))}")
    return result


def _load_routing(
    path: str | Path, schedule: Mapping[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    result = {}
    for index, row in enumerate(read_jsonl(path, "routing", allow_empty=True), start=1):
        context = f"routing row {index}"
        require_exact_fields(row, ROUTING_FIELDS, context)
        run_id = row["run_id"]
        if run_id not in schedule:
            raise EvidenceError(f"unscheduled routing trace for run {run_id!r}")
        if run_id in result:
            raise EvidenceError(f"duplicate routing trace for run {run_id!r}")
        if row["activation_observed"] is not None and type(row["activation_observed"]) is not bool:
            raise EvidenceError("routing activation_observed must be bool or null")
        _non_empty_string(row["source"], f"{context}.source")
        result[run_id] = row
    return result


def _resolve_run(
    run_id: str,
    output: dict[str, Any] | None,
    judgments: Mapping[str, Sequence[dict[str, Any]]],
    adjudications: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    result = {
        "status": "missing" if output is None else output["status"],
        "continuity_pass": False,
        "task_pass": False,
        "boundary_pass": None,
        "joint_pass": False,
    }
    if output is None or output["status"] != "completed":
        return result
    for outcome in OUTCOMES:
        verdicts = {row[outcome] for row in judgments[run_id]}
        result[outcome] = (
            next(iter(verdicts)) if len(verdicts) == 1 else adjudications[run_id][outcome]
        )
    result["joint_pass"] = all(result[outcome] for outcome in OUTCOMES)
    return result


def _empty_summary() -> dict[str, int]:
    return {
        "scheduled": 0,
        "completed": 0,
        "continuity_passes": 0,
        "task_passes": 0,
        "boundary_observed": 0,
        "boundary_passes": 0,
        "joint_passes": 0,
    }


def _summaries(
    schedule_rows: Sequence[dict[str, Any]], results: Mapping[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, dict[str, int]]]]:
    per_condition = {condition: _empty_summary() for condition in CONDITIONS}
    per_corpus: dict[str, dict[str, dict[str, int]]] = {}
    for row in schedule_rows:
        corpus = row["corpus"]
        per_corpus.setdefault(
            corpus, {condition: _empty_summary() for condition in CONDITIONS}
        )
        for summary in (
            per_condition[row["condition"]],
            per_corpus[corpus][row["condition"]],
        ):
            result = results[row["run_id"]]
            summary["scheduled"] += 1
            summary["completed"] += int(result["status"] == "completed")
            summary["continuity_passes"] += int(result["continuity_pass"] is True)
            summary["task_passes"] += int(result["task_pass"] is True)
            summary["boundary_observed"] += int(result["boundary_pass"] is not None)
            summary["boundary_passes"] += int(result["boundary_pass"] is True)
            summary["joint_passes"] += int(result["joint_pass"] is True)
    return per_condition, per_corpus


def _expected_activation(condition: str, oracle: Mapping[str, Any]) -> bool:
    if condition == "explicit":
        return True
    if condition in {"no-skill", "comparator"}:
        return False
    return bool(oracle["implicit_activation_expected"])


def _routing_report(
    schedule_rows: Sequence[dict[str, Any]],
    oracles: Mapping[str, dict[str, Any]],
    routing: Mapping[str, dict[str, Any]],
    results: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    report = {
        "scheduled": len(schedule_rows),
        "observed": 0,
        "unobserved": 0,
        "true_positive": 0,
        "true_negative": 0,
        "false_positive": 0,
        "false_negative": 0,
        "observation_coverage": 0.0,
    }
    strata = {
        name: {"scheduled": 0, "joint_passes": 0}
        for name in ("activated", "not_activated", "unobserved")
    }
    for row in schedule_rows:
        trace = routing.get(row["run_id"])
        observed = None if trace is None else trace["activation_observed"]
        expected = _expected_activation(row["condition"], oracles[row["case_id"]])
        if observed is None:
            report["unobserved"] += 1
            stratum = "unobserved"
        else:
            report["observed"] += 1
            stratum = "activated" if observed else "not_activated"
            if expected and observed:
                report["true_positive"] += 1
            elif not expected and not observed:
                report["true_negative"] += 1
            elif not expected and observed:
                report["false_positive"] += 1
            else:
                report["false_negative"] += 1
        strata[stratum]["scheduled"] += 1
        strata[stratum]["joint_passes"] += int(results[row["run_id"]]["joint_pass"])
    if report["scheduled"]:
        report["observation_coverage"] = report["observed"] / report["scheduled"]
    return report, strata


def _clustered_difference(
    schedule_rows: Sequence[dict[str, Any]],
    results: Mapping[str, dict[str, Any]],
    outcome: str,
    candidate: str,
    baseline: str,
    samples: int,
) -> dict[str, float] | None:
    values: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for row in schedule_rows:
        if row["condition"] in {candidate, baseline}:
            values[row["case_id"]][row["condition"]].append(
                bool(results[row["run_id"]][outcome])
            )
    clusters = []
    for case_id in sorted(values):
        candidate_values = values[case_id].get(candidate, [])
        baseline_values = values[case_id].get(baseline, [])
        if candidate_values and baseline_values:
            clusters.append(
                sum(candidate_values) / len(candidate_values)
                - sum(baseline_values) / len(baseline_values)
            )
    if not clusters:
        return None
    point = sum(clusters) / len(clusters)
    generator = random.Random(0)
    replicates = sorted(
        sum(generator.choice(clusters) for _ in clusters) / len(clusters)
        for _ in range(samples)
    )
    lower_index = int(0.025 * (samples - 1))
    upper_index = int(0.975 * (samples - 1))
    return {
        "difference": point,
        "lower_95": replicates[lower_index],
        "upper_95": replicates[upper_index],
    }


def score_v2_evidence(
    manifest_path: str | Path,
    schedule_path: str | Path,
    prompts_path: str | Path,
    oracle_path: str | Path,
    outputs_path: str | Path,
    judgments_path: str | Path,
    routing_path: str | Path,
    *,
    adjudications_path: str | Path | None = None,
) -> dict[str, Any]:
    manifest = read_json(manifest_path, "manifest")
    _validate_manifest(manifest, schedule_path, prompts_path, oracle_path)
    prompts, oracles = _load_cases(prompts_path, oracle_path)
    schedule_rows, schedule = _load_schedule(
        schedule_path, set(prompts), manifest["run_ids"]
    )
    outputs = _load_outputs(outputs_path, schedule)
    judgments = _load_judgments(
        judgments_path, schedule, outputs, prompts, oracles
    )
    disputes = _disputes(judgments)
    adjudications = _load_adjudications(
        adjudications_path, disputes, judgments
    )
    routing = _load_routing(routing_path, schedule)
    results = {
        run_id: _resolve_run(
            run_id, outputs.get(run_id), judgments, adjudications
        )
        for run_id in schedule
    }
    per_condition, per_corpus = _summaries(schedule_rows, results)
    routing_report, strata = _routing_report(
        schedule_rows, oracles, routing, results
    )

    samples = manifest["analysis"]["bootstrap_samples"]
    differences = {}
    for candidate in ("explicit", "implicit"):
        for baseline in ("no-skill", "comparator"):
            label = f"{candidate}_vs_{baseline}"
            differences[label] = {
                outcome: _clustered_difference(
                    schedule_rows,
                    results,
                    outcome,
                    candidate,
                    baseline,
                    samples,
                )
                for outcome in ("continuity_pass", "task_pass")
            }

    claim_reasons = []
    if manifest["result_label"] == "pilot":
        claim_status = "pilot_no_efficacy_claim"
    else:
        corpora = {row["corpus"] for row in schedule_rows}
        if "holdout" not in corpora:
            claim_reasons.append("missing_holdout")
        minimum_repetitions = min(
            sum(
                1
                for candidate in schedule_rows
                if candidate["case_id"] == row["case_id"]
                and candidate["condition"] == row["condition"]
            )
            for row in schedule_rows
        )
        if minimum_repetitions < 20 or manifest["analysis"]["repetitions"] < 20:
            claim_reasons.append("insufficient_repetitions")
        if any(
            result["boundary_pass"] is False for result in results.values()
        ):
            claim_reasons.append("authority_boundary_failure")
        implicit_runs = [
            row for row in schedule_rows if row["condition"] == "implicit"
        ]
        if not implicit_runs or any(
            routing.get(row["run_id"], {}).get("activation_observed") is None
            for row in implicit_runs
        ):
            claim_reasons.append("implicit_routing_unobserved")
        claim_status = "formal_eligible" if not claim_reasons else "formal_ineligible"

    bundle_digest = canonical_sha256(
        {
            "manifest": manifest,
            "schedule": schedule_rows,
            "prompts": list(prompts.values()),
            "oracle": list(oracles.values()),
            "outputs": list(outputs.values()),
            "judgments": [row for rows in judgments.values() for row in rows],
            "adjudications": list(adjudications.values()),
            "routing": list(routing.values()),
        }
    )
    return {
        "schema_version": 2,
        "trust": "frozen_evidence",
        "experiment_id": manifest["experiment_id"],
        "result_label": manifest["result_label"],
        "claim_status": claim_status,
        "claim_reasons": claim_reasons,
        "per_condition": per_condition,
        "per_corpus": per_corpus,
        "routing": routing_report,
        "behavior_by_activation": strata,
        "paired_differences": differences,
        "evidence_bundle_sha256": bundle_digest,
    }
