#!/usr/bin/env python3
"""Run a four-condition model-smoke pilot through a trusted adapter."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from evidence import (  # noqa: E402
    CONDITIONS,
    EvidenceError,
    canonical_bytes,
    canonical_sha256,
    file_sha256,
    read_json,
    read_jsonl,
    require_exact_fields,
    require_sha256,
)


MAX_READBACK_BYTES = 1024 * 1024
ENVIRONMENT_FIELDS = {
    "reference_host",
    "model",
    "settings",
    "system_instruction_sha256",
    "context_limit",
    "compaction_policy",
    "tool_permissions",
    "isolation",
}
TOOL_PERMISSION_FIELDS = {
    "profile",
    "filesystem_scope",
    "network_policy",
    "external_side_effect_policy",
}
ISOLATION_FIELDS = {
    "profile",
    "mechanism",
    "filesystem_isolated",
    "credentials_isolated",
    "process_tree_cleanup",
    "attested_by",
}


def _non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{context} must be a non-empty string")
    return value


def load_environment_snapshot(path: str | Path) -> dict[str, Any]:
    """Load evaluator-owned host/model/settings metadata from a fixed file."""

    environment = read_json(path, "environment snapshot")
    require_exact_fields(environment, ENVIRONMENT_FIELDS, "environment snapshot")
    for name, fields in (
        ("reference_host", {"product", "surface", "version", "build"}),
        ("model", {"name", "snapshot"}),
    ):
        value = environment[name]
        if not isinstance(value, dict):
            raise EvidenceError(f"environment snapshot {name} must be an object")
        require_exact_fields(value, fields, f"environment snapshot {name}")
        for field in fields:
            _non_empty_string(value[field], f"environment snapshot {name}.{field}")
    for name in ("settings", "tool_permissions", "isolation"):
        if not isinstance(environment[name], dict):
            raise EvidenceError(f"environment snapshot {name} must be an object")
    require_exact_fields(
        environment["tool_permissions"],
        TOOL_PERMISSION_FIELDS,
        "environment snapshot tool_permissions",
    )
    for field in TOOL_PERMISSION_FIELDS:
        _non_empty_string(
            environment["tool_permissions"][field],
            f"environment snapshot tool_permissions.{field}",
        )
    require_exact_fields(
        environment["isolation"],
        ISOLATION_FIELDS,
        "environment snapshot isolation",
    )
    for field in ("profile", "mechanism", "attested_by"):
        _non_empty_string(
            environment["isolation"][field],
            f"environment snapshot isolation.{field}",
        )
    for field in (
        "filesystem_isolated",
        "credentials_isolated",
        "process_tree_cleanup",
    ):
        if environment["isolation"][field] is not True:
            raise EvidenceError(
                f"environment snapshot isolation.{field} must be true"
            )
    require_sha256(
        environment["system_instruction_sha256"],
        "environment snapshot system_instruction_sha256",
    )
    if type(environment["context_limit"]) is not int or environment["context_limit"] <= 0:
        raise EvidenceError("environment snapshot context_limit must be positive")
    _non_empty_string(
        environment["compaction_policy"],
        "environment snapshot compaction_policy",
    )
    return environment


def _environment_from_args(args: argparse.Namespace) -> dict[str, Any]:
    required = (
        "host_product",
        "host_surface",
        "host_version",
        "host_build",
        "model",
        "model_snapshot",
        "context_limit",
        "compaction_policy",
    )
    missing = [name for name in required if not getattr(args, name, None)]
    if missing:
        raise EvidenceError(
            "local metadata options are required without --environment-snapshot: "
            + ", ".join(missing)
        )
    return {
        "reference_host": {
            "product": args.host_product,
            "surface": args.host_surface,
            "version": args.host_version,
            "build": args.host_build,
        },
        "model": {"name": args.model, "snapshot": args.model_snapshot},
        "settings": {},
        "system_instruction_sha256": hashlib.sha256(b"").hexdigest(),
        "context_limit": args.context_limit,
        "compaction_policy": args.compaction_policy,
        "tool_permissions": {"source": "local_adapter_contract"},
        "isolation": {"source": "local_adapter_contract"},
    }


def transform_messages(
    messages: list[dict[str, str]], condition: str, comparator_text: str
) -> list[dict[str, str]]:
    """Apply exactly one declared condition transformation."""

    if condition not in CONDITIONS:
        raise EvidenceError(f"unknown condition {condition!r}")
    transformed = copy.deepcopy(messages)
    if condition == "comparator":
        return [{"role": "system", "content": comparator_text}, *transformed]
    if condition == "explicit":
        for message in transformed:
            if message.get("role") == "user":
                message["content"] = "$no-reask " + message["content"]
                return transformed
        raise EvidenceError("explicit condition requires a user message")
    return transformed


def _error_result(status: str, error_type: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "trajectory": [
            {
                "sequence": 1,
                "type": "adapter_error",
                "data": {"error_type": error_type, "message": message[:4000]},
            }
        ],
        "activation_observed": None,
        "routing_source": f"adapter-{error_type}",
    }


def run_one(
    adapter_path: str | Path,
    packet: dict[str, Any],
    workdir: str | Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Invoke one trusted adapter without a shell and normalize its result."""

    adapter = Path(adapter_path)
    if not adapter.is_file() or adapter.is_symlink():
        raise EvidenceError(f"adapter must be a regular non-symlink file: {adapter}")
    if not os.access(adapter, os.X_OK):
        raise EvidenceError(f"adapter is not executable: {adapter}")
    try:
        completed = subprocess.run(
            [str(adapter)],
            input=canonical_bytes(packet).decode("utf-8"),
            cwd=Path(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _error_result("timed_out", "timeout", "adapter timed out")
    except OSError as error:
        return _error_result("crashed", "launch", str(error))
    if completed.returncode != 0:
        return _error_result(
            "crashed",
            "exit",
            f"adapter exited {completed.returncode}: {completed.stderr}",
        )
    try:
        result = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError) as error:
        return _error_result("invalid", "invalid-json", str(error))
    if not isinstance(result, dict):
        return _error_result("invalid", "invalid-schema", "adapter output is not an object")
    try:
        require_exact_fields(
            result,
            {"trajectory", "activation_observed", "routing_source"},
            "adapter output",
        )
        if not isinstance(result["trajectory"], list) or not result["trajectory"]:
            raise EvidenceError("adapter trajectory must be a non-empty list")
        for sequence, event in enumerate(result["trajectory"], start=1):
            if not isinstance(event, dict):
                raise EvidenceError("adapter event must be an object")
            require_exact_fields(event, {"sequence", "type", "data"}, "adapter event")
            if event["sequence"] != sequence:
                raise EvidenceError("adapter event sequence is invalid")
            if not isinstance(event["type"], str) or not event["type"]:
                raise EvidenceError("adapter event type must be a non-empty string")
            if not isinstance(event["data"], dict):
                raise EvidenceError("adapter event data must be an object")
        if result["activation_observed"] is not None and type(
            result["activation_observed"]
        ) is not bool:
            raise EvidenceError("adapter activation must be bool or null")
        if not isinstance(result["routing_source"], str) or not result[
            "routing_source"
        ].strip():
            raise EvidenceError("adapter routing source must be non-empty")
    except EvidenceError as error:
        return _error_result("invalid", "invalid-schema", str(error))
    return {"status": "completed", **result}


def _safe_readback_target(workdir: Path, relative_value: str) -> Path:
    relative = Path(relative_value)
    if not relative_value or relative.is_absolute() or ".." in relative.parts:
        raise EvidenceError(f"unsafe readback path {relative_value!r}")
    target = workdir / relative
    resolved_target = target.resolve(strict=False)
    try:
        resolved_target.relative_to(workdir)
    except ValueError as error:
        raise EvidenceError(f"readback escapes working directory: {relative_value}") from error
    return target


def collect_readbacks(
    workdir: str | Path, relative_paths: list[str]
) -> dict[str, dict[str, Any]]:
    """Read registered files from the trusted working directory."""

    root = Path(workdir).resolve()
    result = {}
    for relative_value in relative_paths:
        target = _safe_readback_target(root, relative_value)
        if not target.exists():
            result[relative_value] = {"exists": False}
            continue
        mode = target.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise EvidenceError(f"readback must be a regular non-symlink file: {relative_value}")
        size = target.stat().st_size
        if size > MAX_READBACK_BYTES:
            raise EvidenceError(
                f"readback is too large ({size} bytes): {relative_value}"
            )
        payload = target.read_bytes()
        record: dict[str, Any] = {
            "exists": True,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        try:
            record.update({"type": "text", "text": payload.decode("utf-8")})
        except UnicodeDecodeError:
            record["type"] = "binary"
        result[relative_value] = record
    return result


def _git_capture(workdir: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise EvidenceError(f"git {' '.join(arguments)} failed: {completed.stderr}")
    return completed.stdout


def _initialize_fixture(workdir: Path, fixture: str | None) -> None:
    if fixture is not None:
        relative = Path(fixture)
        if relative.is_absolute() or ".." in relative.parts:
            raise EvidenceError(f"unsafe fixture path {fixture!r}")
        source = EVALS / "fixtures" / relative
        if not source.is_dir() or source.is_symlink():
            raise EvidenceError(f"fixture directory does not exist: {fixture}")
        shutil.copytree(source, workdir, dirs_exist_ok=True)
    commands = (
        ["init", "-q"],
        ["config", "user.email", "evaluator@example.invalid"],
        ["config", "user.name", "No Re-Ask Evaluator"],
        ["add", "-A"],
        ["commit", "-qm", "evaluation baseline", "--allow-empty"],
    )
    for arguments in commands:
        _git_capture(workdir, arguments)


def _directory_sha256(directory: Path) -> str:
    entries = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise EvidenceError(f"runtime directory contains symlink {path}")
        if path.is_file():
            entries[path.relative_to(directory).as_posix()] = file_sha256(path)
    return canonical_sha256(entries)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    _atomic_write(path, payload)


def build_manifest(
    args: argparse.Namespace,
    schedule: list[dict[str, Any]],
    file_digests: dict[str, str],
    adapter_digest: str,
    skill_digest: str,
    environment: dict[str, Any] | None = None,
    environment_digest: str | None = None,
) -> dict[str, Any]:
    """Build the strict schema-v2 pilot manifest."""

    resolved_environment = environment or _environment_from_args(args)
    return {
        "schema_version": 2,
        "experiment_id": "model-smoke-pilot",
        "result_label": "pilot",
        "reference_host": resolved_environment["reference_host"],
        "model": resolved_environment["model"],
        "settings": {
            **resolved_environment["settings"],
            "adapter_sha256": adapter_digest,
            "environment_snapshot_sha256": environment_digest,
            "tool_permissions": resolved_environment["tool_permissions"],
            "isolation": resolved_environment["isolation"],
            "workspace_lifecycle": "ephemeral_per_run",
            "workspace_location": "system_temporary_directory",
            "adapter_trust_boundary": (
                "attested_by_environment_snapshot"
                if environment_digest is not None
                else "local_unattested_adapter_contract"
            ),
        },
        "skill": {
            "sha256": skill_digest,
            "discovery_path": ".agents/skills/no-reask",
            "explicit_invocation": "$no-reask",
            "inventory": ["no-reask"],
        },
        "harness": {
            "sha256": file_sha256(__file__),
            "collector_sha256": file_sha256(__file__),
        },
        "system_instruction_sha256": resolved_environment[
            "system_instruction_sha256"
        ],
        "comparator_sha256": file_sha256(EVALS / "comparator.txt"),
        "context_limit": resolved_environment["context_limit"],
        "compaction_policy": resolved_environment["compaction_policy"],
        "run_ids": [row["run_id"] for row in schedule],
        "files": file_digests,
        "analysis": {
            "repetitions": 1,
            "confidence_level": 0.95,
            "task_noninferiority_margin": 0.05,
            "bootstrap_samples": 10000,
        },
    }


def _execute_scheduled_run(
    args: argparse.Namespace,
    scheduled: dict[str, Any],
    prompt: dict[str, Any],
    oracle: dict[str, Any],
    comparator: str,
    runtime_snapshot: Path,
    model: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_id = scheduled["run_id"]
    with tempfile.TemporaryDirectory(prefix=f"no-reask-{run_id}-") as temporary:
        workdir = Path(temporary)
        if scheduled["condition"] in {"explicit", "implicit"}:
            target = workdir / ".agents" / "skills" / "no-reask"
            target.parent.mkdir(parents=True)
            shutil.copytree(runtime_snapshot, target)
        _initialize_fixture(workdir, prompt["fixture"])
        resolved_model = model or {
            "name": args.model,
            "snapshot": args.model_snapshot,
        }
        packet = {
            "run_id": run_id,
            "case_id": scheduled["case_id"],
            "condition": scheduled["condition"],
            "messages": transform_messages(
                prompt["messages"], scheduled["condition"], comparator
            ),
            "model": resolved_model["name"],
            "model_snapshot": resolved_model["snapshot"],
            "isolation_contract": {
                "workspace_scope": "current-directory-only",
                "oracle_access": "denied",
                "cross_run_access": "denied",
                "collector": "external-to-producer",
            },
        }
        adapter_result = run_one(
            args.adapter, packet, workdir, args.timeout_seconds
        )
        readbacks = collect_readbacks(workdir, oracle["readback_paths"])
        readbacks["$git"] = {
            "status": _git_capture(workdir, ["status", "--porcelain=v1"]),
            "diff": _git_capture(
                workdir,
                ["diff", "--no-ext-diff", "--binary", "HEAD"],
            ),
        }
        trajectory = list(adapter_result["trajectory"])
        trajectory.append(
            {
                "sequence": len(trajectory) + 1,
                "type": "collector",
                "data": {"workspace_retained": False},
            }
        )
        output = {
            "run_id": run_id,
            "case_id": scheduled["case_id"],
            "condition": scheduled["condition"],
            "status": adapter_result["status"],
            "trajectory": trajectory,
            "readbacks": readbacks,
        }
        routing = {
            "run_id": run_id,
            "activation_observed": adapter_result["activation_observed"],
            "source": adapter_result["routing_source"],
        }
    return output, routing


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    """Collect one pilot repetition for every checked-in scheduled run."""

    artifacts = Path(args.artifacts).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    schedule = read_jsonl(EVALS / "evaluation-schedule.jsonl", "schedule")
    prompts = read_jsonl(EVALS / "evaluation-prompts.jsonl", "prompts")
    oracles = read_jsonl(EVALS / "evaluation-oracle.jsonl", "oracle")
    prompt_by_case = {row["case_id"]: row for row in prompts}
    oracle_by_case = {row["case_id"]: row for row in oracles}
    comparator = (EVALS / "comparator.txt").read_text(encoding="utf-8")
    environment_path = getattr(args, "environment_snapshot", None)
    if environment_path:
        environment = load_environment_snapshot(environment_path)
        environment_digest = file_sha256(environment_path)
    else:
        environment = _environment_from_args(args)
        environment_digest = None

    frozen_schedule = artifacts / "evaluation-schedule.jsonl"
    _write_jsonl(frozen_schedule, schedule)
    outputs = []
    routing = []
    with tempfile.TemporaryDirectory(prefix="no-reask-runtime-") as temporary:
        runtime_snapshot = Path(temporary) / "no-reask"
        shutil.copytree(ROOT / "no-reask", runtime_snapshot)
        skill_digest = _directory_sha256(runtime_snapshot)
        file_digests = {
            "schedule_sha256": file_sha256(frozen_schedule),
            "prompts_sha256": file_sha256(EVALS / "evaluation-prompts.jsonl"),
            "oracle_sha256": file_sha256(EVALS / "evaluation-oracle.jsonl"),
        }
        manifest = build_manifest(
            args,
            schedule,
            file_digests,
            file_sha256(args.adapter),
            skill_digest,
            environment,
            environment_digest,
        )
        _write_json(artifacts / "run-manifest.json", manifest)
        for scheduled in schedule:
            output, routing_row = _execute_scheduled_run(
                args,
                scheduled,
                prompt_by_case[scheduled["case_id"]],
                oracle_by_case[scheduled["case_id"]],
                comparator,
                runtime_snapshot,
                environment["model"],
            )
            outputs.append(output)
            routing.append(routing_row)

    outputs_path = artifacts / "evaluation-outputs.jsonl"
    routing_path = artifacts / "evaluation-routing.jsonl"
    _write_jsonl(outputs_path, outputs)
    _write_jsonl(routing_path, routing)
    status_counts = {status: 0 for status in ("completed", "crashed", "timed_out", "invalid")}
    for output in outputs:
        status_counts[output["status"]] += 1
    observed = sum(row["activation_observed"] is not None for row in routing)
    summary = {
        "result_label": "pilot",
        "claim_status": "pilot_no_efficacy_claim",
        "scheduled": len(schedule),
        **status_counts,
        "routing_observation_coverage": observed / len(schedule) if schedule else 0.0,
        "efficacy_result": None,
        "message": "Pilot collection only; no efficacy percentage was produced.",
    }
    _write_json(artifacts / "smoke-summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--environment-snapshot", type=Path)
    parser.add_argument("--host-product")
    parser.add_argument("--host-surface")
    parser.add_argument("--host-version")
    parser.add_argument("--host-build")
    parser.add_argument("--model")
    parser.add_argument("--model-snapshot")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--context-limit", type=int, default=100000)
    parser.add_argument("--compaction-policy", default="host-default")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        summary = run_smoke(_parser().parse_args(argv))
    except EvidenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
