import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from itertools import product
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
CONDITIONS = {"no-skill", "comparator", "explicit", "implicit"}
REQUIRED_TAGS = {
    "cross-turn",
    "long-task",
    "material-clarification",
    "stale-state",
    "missing-authority",
    "optional-adjacent",
    "non-activation",
    "tool-using",
}
MIGRATED_SCENARIOS = {
    "parser-tests",
    "comparison-recommendation",
    "checkout-fix-suite-commit",
    "production-target",
    "parser-only",
}
DISTINCT_JUDGE_ERROR = r"(?i)(distinct[^\n]*judge|judge[^\n]*distinct|two[^\n]*judge)"


class EvaluationFixtureContractTest(unittest.TestCase):
    def read_required(self, relative_path):
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"{relative_path} must exist")
        return path.read_text(encoding="utf-8")

    def load_jsonl(self, filename):
        relative_path = f"evals/{filename}"
        document = self.read_required(relative_path)
        rows = []
        for line_number, line in enumerate(document.splitlines(), start=1):
            self.assertTrue(
                line.strip(), f"{relative_path} line {line_number} must not be blank"
            )

            def reject_duplicate_members(pairs):
                value = {}
                for key, member in pairs:
                    self.assertNotIn(
                        key,
                        value,
                        f"{relative_path} line {line_number} has duplicate "
                        f"object member {key!r}",
                    )
                    value[key] = member
                return value

            try:
                row = json.loads(line, object_pairs_hook=reject_duplicate_members)
            except json.JSONDecodeError as error:
                self.fail(
                    f"{relative_path} line {line_number} must be valid JSON: {error}"
                )
            self.assertIsInstance(
                row, dict, f"{relative_path} line {line_number} must be an object"
            )
            rows.append(row)
        self.assertTrue(rows, f"{relative_path} must contain at least one row")
        return rows

    def assert_non_empty_string(self, row, field, context):
        self.assertIn(field, row, f"{context} must contain {field}")
        self.assertIsInstance(row[field], str, f"{context}.{field} must be a string")
        self.assertTrue(row[field].strip(), f"{context}.{field} must not be empty")

    def test_required_evaluation_files_exist(self):
        required = {
            "evaluation-prompts.jsonl",
            "evaluation-oracle.jsonl",
            "evaluation-schedule.jsonl",
            "evaluation-protocol.md",
            "comparator.txt",
            "score_eval.py",
        }
        missing = sorted(name for name in required if not (EVALS / name).is_file())
        self.assertEqual(missing, [], f"missing evaluation files: {missing}")

    def test_protocol_and_comparator_are_not_empty(self):
        for filename in ("evaluation-protocol.md", "comparator.txt"):
            with self.subTest(filename=filename):
                document = self.read_required(f"evals/{filename}")
                self.assertTrue(document.strip(), f"evals/{filename} must not be empty")

    def test_prompt_rows_are_oracle_free_and_well_formed(self):
        rows = self.load_jsonl("evaluation-prompts.jsonl")
        case_ids = []
        for index, row in enumerate(rows, start=1):
            context = f"evaluation-prompts.jsonl row {index}"
            self.assertEqual(
                set(row),
                {"case_id", "title", "tags", "messages", "fixture"},
                f"{context} must contain prompt fields only",
            )
            for field in ("case_id", "title"):
                self.assert_non_empty_string(row, field, context)
            self.assertIsInstance(row["tags"], list, f"{context}.tags must be a list")
            self.assertTrue(row["tags"], f"{context}.tags must not be empty")
            for tag in row["tags"]:
                self.assertIsInstance(tag, str, f"{context} tags must be strings")
                self.assertTrue(tag.strip(), f"{context} tags must not be empty")
            self.assertIsInstance(
                row["messages"], list, f"{context}.messages must be a list"
            )
            self.assertTrue(row["messages"], f"{context}.messages must not be empty")
            for message_index, message in enumerate(row["messages"], start=1):
                message_context = f"{context}.messages[{message_index}]"
                self.assertIsInstance(message, dict, f"{message_context} must be an object")
                self.assertEqual(
                    set(message), {"role", "content"}, f"{message_context} has wrong fields"
                )
                self.assertIn(
                    message["role"],
                    {"system", "user", "assistant"},
                    f"{message_context}.role is invalid",
                )
                self.assertIsInstance(
                    message["content"], str, f"{message_context}.content must be a string"
                )
                self.assertTrue(
                    message["content"].strip(),
                    f"{message_context}.content must not be empty",
                )
            case_ids.append(row["case_id"])

        self.assertEqual(len(case_ids), len(set(case_ids)), "case_id must be unique")
        self.assertTrue(
            MIGRATED_SCENARIOS.issubset(case_ids),
            f"missing migrated scenarios: {sorted(MIGRATED_SCENARIOS - set(case_ids))}",
        )

    def test_oracle_rows_are_well_formed(self):
        rows = self.load_jsonl("evaluation-oracle.jsonl")
        case_ids = []
        required = {
            "case_id",
            "continuity_rule",
            "task_rule",
            "boundary_rule",
            "readback_paths",
            "implicit_activation_expected",
        }
        for index, row in enumerate(rows, start=1):
            context = f"evaluation-oracle.jsonl row {index}"
            self.assertEqual(set(row), required, f"{context} has wrong fields")
            for field in ("case_id", "continuity_rule", "task_rule", "boundary_rule"):
                self.assert_non_empty_string(row, field, context)
            self.assertIsInstance(
                row["readback_paths"], list, f"{context}.readback_paths must be a list"
            )
            for relative_path in row["readback_paths"]:
                self.assertIsInstance(relative_path, str)
                self.assertTrue(relative_path)
                self.assertFalse(Path(relative_path).is_absolute())
                self.assertNotIn("..", Path(relative_path).parts)
            self.assertIsInstance(
                row["implicit_activation_expected"],
                bool,
                f"{context}.implicit_activation_expected must be a boolean",
            )
            case_ids.append(row["case_id"])

        self.assertEqual(len(case_ids), len(set(case_ids)), "case_id must be unique")

    def test_prompt_and_oracle_case_ids_match(self):
        prompt_ids = {
            row.get("case_id") for row in self.load_jsonl("evaluation-prompts.jsonl")
        }
        oracle_ids = {
            row.get("case_id") for row in self.load_jsonl("evaluation-oracle.jsonl")
        }
        self.assertEqual(prompt_ids, oracle_ids)

    def test_prompt_tags_cover_behavior_boundaries(self):
        rows = self.load_jsonl("evaluation-prompts.jsonl")
        tags = {
            tag for row in rows for tag in row.get("tags", []) if isinstance(tag, str)
        }
        self.assertTrue(
            REQUIRED_TAGS.issubset(tags),
            f"evaluation prompts are missing tags: {sorted(REQUIRED_TAGS - tags)}",
        )
        missing_authority_cases = {
            row.get("case_id")
            for row in rows
            if "missing-authority" in row.get("tags", [])
        }
        non_activation_cases = {
            row.get("case_id")
            for row in rows
            if "non-activation" in row.get("tags", [])
        }
        self.assertTrue(missing_authority_cases, "missing-authority needs its own case")
        self.assertTrue(non_activation_cases, "non-activation needs its own case")
        self.assertTrue(
            missing_authority_cases.isdisjoint(non_activation_cases),
            "missing-authority and non-activation must use distinct cases",
        )
        self.assertTrue(
            missing_authority_cases.isdisjoint(MIGRATED_SCENARIOS),
            "missing-authority must be an additional scenario",
        )
        self.assertTrue(
            non_activation_cases.isdisjoint(MIGRATED_SCENARIOS),
            "non-activation must be an additional scenario",
        )

    def test_schedule_has_one_run_per_case_and_condition(self):
        prompt_ids = {
            row.get("case_id") for row in self.load_jsonl("evaluation-prompts.jsonl")
        }
        rows = self.load_jsonl("evaluation-schedule.jsonl")
        run_ids = []
        pairs = []
        for index, row in enumerate(rows, start=1):
            context = f"evaluation-schedule.jsonl row {index}"
            self.assertEqual(
                set(row),
                {"run_id", "case_id", "condition", "corpus", "repetition", "seed"},
                f"{context} has wrong fields",
            )
            for field in ("run_id", "case_id", "condition"):
                self.assert_non_empty_string(row, field, context)
            self.assertEqual(row["corpus"], "development")
            self.assertEqual(row["repetition"], 1)
            self.assertIsNone(row["seed"])
            run_ids.append(row["run_id"])
            pairs.append((row["case_id"], row["condition"]))

        self.assertEqual(len(run_ids), len(set(run_ids)), "run_id must be unique")
        self.assertEqual({condition for _, condition in pairs}, CONDITIONS)
        expected_pairs = set(product(prompt_ids, CONDITIONS))
        self.assertEqual(set(pairs), expected_pairs)
        self.assertTrue(
            all(count == 1 for count in Counter(pairs).values()),
            "each case/condition pair must have exactly one row",
        )

    def test_checked_in_schedule_uses_opaque_sequential_run_ids(self):
        rows = self.load_jsonl("evaluation-schedule.jsonl")
        self.assertEqual(
            [row["run_id"] for row in rows],
            [f"run-{index:03d}" for index in range(1, 41)],
        )

    def test_prompt_fixtures_are_safe_and_exist(self):
        rows = self.load_jsonl("evaluation-prompts.jsonl")
        fixture_rows = []
        for row in rows:
            fixture = row["fixture"]
            self.assertTrue(fixture is None or isinstance(fixture, str))
            if fixture is None:
                continue
            self.assertTrue(fixture)
            self.assertFalse(Path(fixture).is_absolute())
            self.assertNotIn("..", Path(fixture).parts)
            fixture_path = EVALS / "fixtures" / fixture
            self.assertTrue(fixture_path.is_dir())
            fixture_rows.append(row)
        self.assertEqual(
            {row["case_id"] for row in fixture_rows},
            {"tool-parser-tests", "tool-fix-tests"},
        )

    def test_response_only_cases_are_self_contained(self):
        prompts = {
            row["case_id"]: "\n".join(
                message["content"] for message in row["messages"]
            )
            for row in self.load_jsonl("evaluation-prompts.jsonl")
        }
        required_phrases = {
            "parser-tests": (
                "parse_addition(expression: str) -> int",
                "unit tests",
                "expected outcomes",
                "Do not execute",
            ),
            "checkout-fix-suite-commit": (
                "checkout trace",
                "patch sketch",
                "regression cases",
                "commit-message text",
                "Do not edit files",
            ),
            "parser-only": ("EBNF", "only", "Do not implement"),
        }
        for case_id, phrases in required_phrases.items():
            for phrase in phrases:
                with self.subTest(case_id=case_id, phrase=phrase):
                    self.assertIn(phrase, prompts[case_id])

        oracle = {
            row["case_id"]: row["boundary_rule"]
            for row in self.load_jsonl("evaluation-oracle.jsonl")
        }
        for case_id in required_phrases:
            with self.subTest(case_id=case_id):
                self.assertIn(
                    "claims it edited files, ran tests, or created a commit",
                    oracle[case_id],
                )

    def test_protocol_defines_transformations_manifest_and_blinding(self):
        protocol = self.read_required("evals/evaluation-protocol.md")
        required_text = (
            "schema version 2",
            "canonical prompt messages unchanged",
            "byte for byte",
            "$no-reask ",
            "trajectory",
            "readbacks",
            "routing trace",
            "intention to treat",
            "pilot",
            "continuity_pass",
            "task_pass",
            "boundary_pass",
            "joint_pass",
            "development",
            "holdout",
            "Runtime Guard",
            "opaque `blind_id`",
            "two independent",
        )
        for text in required_text:
            with self.subTest(text=text):
                self.assertIn(text, protocol)


class EvidencePrimitiveTest(unittest.TestCase):
    def load_evidence_module(self):
        path = EVALS / "evidence.py"
        self.assertTrue(path.is_file(), "evals/evidence.py must exist")
        spec = importlib.util.spec_from_file_location("evaluation_evidence", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_public_constants_define_conditions_and_outcomes(self):
        evidence = self.load_evidence_module()
        self.assertEqual(
            evidence.CONDITIONS,
            ("no-skill", "comparator", "explicit", "implicit"),
        )
        self.assertEqual(
            evidence.OUTCOMES,
            ("continuity_pass", "task_pass", "boundary_pass"),
        )

    def test_canonical_sha256_is_key_order_independent(self):
        evidence = self.load_evidence_module()
        self.assertEqual(
            evidence.canonical_sha256({"b": 2, "a": 1}),
            evidence.canonical_sha256({"a": 1, "b": 2}),
        )

    def test_canonical_sha256_rejects_non_utf8_text(self):
        evidence = self.load_evidence_module()
        with self.assertRaisesRegex(evidence.EvidenceError, r"(?i)(UTF-8|encode)"):
            evidence.canonical_sha256({"text": "\ud800"})

    def test_read_json_rejects_duplicate_members(self):
        evidence = self.load_evidence_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "duplicate.json"
            path.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(evidence.EvidenceError, r"(?i)duplicate"):
                evidence.read_json(path, "manifest")

    def test_read_jsonl_rejects_blank_lines(self):
        evidence = self.load_evidence_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "rows.jsonl"
            path.write_text('{"a":1}\n\n', encoding="utf-8")
            with self.assertRaisesRegex(evidence.EvidenceError, r"(?i)blank"):
                evidence.read_jsonl(path, "rows")

    def test_read_jsonl_allows_an_empty_file_only_when_requested(self):
        evidence = self.load_evidence_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "rows.jsonl"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(evidence.EvidenceError, r"(?i)empty"):
                evidence.read_jsonl(path, "rows")
            self.assertEqual(
                evidence.read_jsonl(path, "rows", allow_empty=True), []
            )

    def test_require_exact_fields_reports_missing_and_extra_fields(self):
        evidence = self.load_evidence_module()
        with self.assertRaisesRegex(
            evidence.EvidenceError, r"(?i)(missing.*b|unexpected.*c)"
        ):
            evidence.require_exact_fields({"a": 1, "c": 3}, {"a", "b"}, "row")

    def test_file_sha256_hashes_raw_bytes(self):
        evidence = self.load_evidence_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "payload.bin"
            payload = b"No Re-Ask\x00\xff"
            path.write_bytes(payload)
            self.assertEqual(
                evidence.file_sha256(path), hashlib.sha256(payload).hexdigest()
            )

    def test_require_sha256_accepts_only_lowercase_hex(self):
        evidence = self.load_evidence_module()
        digest = "a" * 64
        self.assertEqual(evidence.require_sha256(digest, "digest"), digest)
        for invalid in ("A" * 64, "a" * 63, "g" * 64, 42):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(evidence.EvidenceError, r"(?i)sha-?256"):
                    evidence.require_sha256(invalid, "digest")


class ScorerContractTest(unittest.TestCase):
    def load_scorer(self):
        path = EVALS / "score_eval.py"
        self.assertTrue(path.is_file(), "evals/score_eval.py must exist")
        spec = importlib.util.spec_from_file_location("score_eval_contract", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        previous_module = sys.modules.get(spec.name)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            if previous_module is None:
                sys.modules.pop(spec.name, None)
            else:
                sys.modules[spec.name] = previous_module
        self.assertTrue(hasattr(module, "EvidenceError"))
        self.assertTrue(callable(getattr(module, "response_sha256", None)))
        self.assertTrue(callable(getattr(module, "score_evidence", None)))
        return module

    def write_jsonl(self, directory, filename, rows):
        path = directory / filename
        serialized = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        path.write_text(serialized, encoding="utf-8")
        return path

    def evidence(self, scorer, directory):
        schedule = [
            {
                "run_id": f"run-{case_id}-{condition}",
                "case_id": case_id,
                "condition": condition,
            }
            for case_id in ("case-one", "case-two")
            for condition in ("no-skill", "comparator", "explicit", "implicit")
        ]
        outputs = [
            {
                "run_id": row["run_id"],
                "case_id": row["case_id"],
                "condition": row["condition"],
                "response": f"response for {row['run_id']}",
            }
            for row in schedule
        ]
        judgments = []
        for output in outputs:
            digest = scorer.response_sha256(output["response"])
            for judge_id in ("judge-a", "judge-b"):
                judgments.append(
                    {
                        "run_id": output["run_id"],
                        "judge_id": judge_id,
                        "output_sha256": digest,
                        "behavior_pass": True,
                        "safety_pass": True,
                    }
                )
        return schedule, outputs, judgments

    def score(self, scorer, directory, schedule, outputs, judgments, adjudications=None):
        schedule_path = self.write_jsonl(directory, "schedule.jsonl", schedule)
        outputs_path = self.write_jsonl(directory, "outputs.jsonl", outputs)
        judgments_path = self.write_jsonl(directory, "judgments.jsonl", judgments)
        adjudications_path = None
        if adjudications is not None:
            adjudications_path = self.write_jsonl(
                directory, "adjudications.jsonl", adjudications
            )
        return scorer.score_evidence(
            schedule_path,
            outputs_path,
            judgments_path,
            adjudications_path=adjudications_path,
        )

    def run_cli(
        self,
        schedule_path,
        outputs_path,
        judgments_path,
        report_path,
        adjudications_path=None,
    ):
        command = [
            sys.executable,
            "-I",
            str(EVALS / "score_eval.py"),
            "--schedule",
            str(schedule_path),
            "--outputs",
            str(outputs_path),
            "--judgments",
            str(judgments_path),
        ]
        if adjudications_path is not None:
            command.extend(("--adjudications", str(adjudications_path)))
        command.extend(("--report", str(report_path)))
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_valid_cli_evidence(self, scorer, directory, with_adjudication=False):
        schedule, outputs, judgments = self.evidence(scorer, directory)
        adjudications = None
        if with_adjudication:
            judgments[1]["behavior_pass"] = False
            adjudications = [
                {
                    "run_id": outputs[0]["run_id"],
                    "output_sha256": scorer.response_sha256(outputs[0]["response"]),
                    "behavior_pass": True,
                    "safety_pass": True,
                    "reason": "Resolved the behavior disagreement.",
                }
            ]
        paths = {
            "schedule": self.write_jsonl(directory, "schedule.jsonl", schedule),
            "outputs": self.write_jsonl(directory, "outputs.jsonl", outputs),
            "judgments": self.write_jsonl(directory, "judgments.jsonl", judgments),
        }
        if adjudications is not None:
            paths["adjudications"] = self.write_jsonl(
                directory, "adjudications.jsonl", adjudications
            )
        return paths

    def test_response_sha256_uses_utf8_text(self):
        scorer = self.load_scorer()
        text = "No Re-Ask \N{CHECK MARK}"
        self.assertEqual(
            scorer.response_sha256(text), hashlib.sha256(text.encode("utf-8")).hexdigest()
        )

    def test_response_sha256_wraps_unicode_encode_error(self):
        scorer = self.load_scorer()
        with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)(UTF-8|encode)"):
            scorer.response_sha256("\ud800")

    def test_cli_reports_surrogate_response_without_traceback(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            outputs[0]["response"] = "\ud800"
            judgments[0]["output_sha256"] = "0" * 64
            judgments[1]["output_sha256"] = "0" * 64
            schedule_path = self.write_jsonl(directory, "schedule.jsonl", schedule)
            outputs_path = self.write_jsonl(directory, "outputs.jsonl", outputs)
            judgments_path = self.write_jsonl(directory, "judgments.jsonl", judgments)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(EVALS / "score_eval.py"),
                    "--schedule",
                    str(schedule_path),
                    "--outputs",
                    str(outputs_path),
                    "--judgments",
                    str(judgments_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertRegex(completed.stderr, r"(?i)(UTF-8|encode)")
        self.assertNotIn("Traceback", completed.stderr)

    def test_cli_rejects_report_equal_to_each_evidence_input(self):
        scorer = self.load_scorer()
        for target_name in ("schedule", "outputs", "judgments", "adjudications"):
            with self.subTest(target_name=target_name), tempfile.TemporaryDirectory() as temporary_directory:
                directory = Path(temporary_directory)
                paths = self.write_valid_cli_evidence(
                    scorer, directory, with_adjudication=True
                )
                before = {name: path.read_bytes() for name, path in paths.items()}
                completed = self.run_cli(
                    paths["schedule"],
                    paths["outputs"],
                    paths["judgments"],
                    paths[target_name],
                    adjudications_path=paths["adjudications"],
                )

                self.assertEqual(completed.returncode, 2)
                self.assertRegex(completed.stderr, r"(?i)(report|output).*(alias|input)")
                self.assertNotIn("Traceback", completed.stderr)
                self.assertEqual(
                    {name: path.read_bytes() for name, path in paths.items()}, before
                )

    def test_cli_rejects_report_through_symlinked_parent(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            evidence_directory = directory / "evidence"
            evidence_directory.mkdir()
            paths = self.write_valid_cli_evidence(scorer, evidence_directory)
            alias_directory = directory / "alias"
            try:
                alias_directory.symlink_to(evidence_directory, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks are unavailable: {error}")
            report_path = alias_directory / paths["outputs"].name
            before = paths["outputs"].read_bytes()
            completed = self.run_cli(
                paths["schedule"],
                paths["outputs"],
                paths["judgments"],
                report_path,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertEqual(paths["outputs"].read_bytes(), before)

    def test_cli_rejects_report_hard_link_alias(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            paths = self.write_valid_cli_evidence(scorer, directory)
            report_path = directory / "report.json"
            try:
                report_path.hardlink_to(paths["judgments"])
            except OSError as error:
                self.skipTest(f"hard links are unavailable: {error}")
            before = paths["judgments"].read_bytes()
            completed = self.run_cli(
                paths["schedule"],
                paths["outputs"],
                paths["judgments"],
                report_path,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertEqual(paths["judgments"].read_bytes(), before)

    def test_complete_agreed_evidence_reports_condition_counts_and_passes(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            report = self.score(scorer, directory, schedule, outputs, judgments)

        for condition in ("no-skill", "comparator", "explicit", "implicit"):
            with self.subTest(condition=condition):
                summary = report["per_condition"][condition]
                self.assertEqual(summary["count"], 2)
                self.assertEqual(summary["behavior_passes"], 2)
                self.assertEqual(summary["safety_passes"], 2)
        self.assertEqual(report["trust"], "untrusted_legacy")

    def test_incomplete_schedule_matrix_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            removed_run_id = schedule[-1]["run_id"]
            schedule = schedule[:-1]
            outputs = [row for row in outputs if row["run_id"] != removed_run_id]
            judgments = [
                row for row in judgments if row["run_id"] != removed_run_id
            ]
            with self.assertRaisesRegex(
                scorer.EvidenceError,
                r"(?i)(incomplete|missing.*condition|four.*condition)",
            ):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_unknown_schedule_condition_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            schedule[0]["condition"] = "experimental"
            outputs[0]["condition"] = "experimental"
            with self.assertRaisesRegex(
                scorer.EvidenceError, r"(?i)(unknown|allowed).*condition"
            ):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_duplicate_json_object_member_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            schedule_path = self.write_jsonl(directory, "schedule.jsonl", schedule)
            lines = schedule_path.read_text(encoding="utf-8").splitlines()
            first = schedule[0]
            lines[0] = (
                '{"run_id":"%s","run_id":"%s","case_id":"%s",'
                '"condition":"%s"}'
                % (
                    first["run_id"],
                    first["run_id"],
                    first["case_id"],
                    first["condition"],
                )
            )
            schedule_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            outputs_path = self.write_jsonl(directory, "outputs.jsonl", outputs)
            judgments_path = self.write_jsonl(directory, "judgments.jsonl", judgments)
            with self.assertRaisesRegex(
                scorer.EvidenceError, r"(?i)duplicate.*(member|key|run_id)"
            ):
                scorer.score_evidence(schedule_path, outputs_path, judgments_path)

    def test_missing_output_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            missing_run_id = outputs[-1]["run_id"]
            judgments = [
                row for row in judgments if row["run_id"] != missing_run_id
            ]
            with self.assertRaisesRegex(
                scorer.EvidenceError,
                r"(?i)(missing[ _-]?output|output[^\n]*missing)",
            ):
                self.score(scorer, directory, schedule, outputs[:-1], judgments)

    def test_duplicate_output_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            with self.assertRaises(scorer.EvidenceError):
                self.score(scorer, directory, schedule, outputs + outputs[:1], judgments)

    def test_output_case_id_must_match_schedule(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            outputs[0]["case_id"], outputs[4]["case_id"] = (
                outputs[4]["case_id"],
                outputs[0]["case_id"],
            )
            with self.assertRaises(scorer.EvidenceError):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_output_condition_must_match_schedule(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            outputs[0]["condition"], outputs[1]["condition"] = (
                outputs[1]["condition"],
                outputs[0]["condition"],
            )
            with self.assertRaises(scorer.EvidenceError):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_unscheduled_output_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            output = {
                "run_id": "run-unscheduled",
                "case_id": "case-one",
                "condition": "implicit",
                "response": "unscheduled response",
            }
            outputs.append(output)
            digest = scorer.response_sha256(output["response"])
            for judge_id in ("judge-a", "judge-b"):
                judgments.append(
                    {
                        "run_id": output["run_id"],
                        "judge_id": judge_id,
                        "output_sha256": digest,
                        "behavior_pass": True,
                        "safety_pass": True,
                    }
                )
            with self.assertRaisesRegex(
                scorer.EvidenceError,
                r"(?i)(unscheduled[^\n]*output|output[^\n]*schedule)",
            ):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_unscheduled_judgment_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            judgments.append(
                {
                    "run_id": "run-unscheduled",
                    "judge_id": "judge-a",
                    "output_sha256": scorer.response_sha256(
                        "unscheduled response"
                    ),
                    "behavior_pass": True,
                    "safety_pass": True,
                }
            )
            with self.assertRaisesRegex(
                scorer.EvidenceError,
                r"(?i)(unscheduled[^\n]*judg|judg[^\n]*schedule)",
            ):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_judgment_with_wrong_output_hash_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            judgments[0]["output_sha256"] = "0" * 64
            with self.assertRaises(scorer.EvidenceError):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_one_judgment_for_one_run_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            target_run_id = outputs[0]["run_id"]
            judgments = [
                row
                for row in judgments
                if not (
                    row["run_id"] == target_run_id
                    and row["judge_id"] == "judge-b"
                )
            ]
            with self.assertRaises(scorer.EvidenceError):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_duplicate_judge_identity_for_one_run_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            judgments[1]["judge_id"] = judgments[0]["judge_id"]
            with self.assertRaisesRegex(scorer.EvidenceError, DISTINCT_JUDGE_ERROR):
                self.score(scorer, directory, schedule, outputs, judgments)

    def test_unresolved_behavior_or_safety_disagreement_is_rejected(self):
        scorer = self.load_scorer()
        for field in ("behavior_pass", "safety_pass"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary_directory:
                directory = Path(temporary_directory)
                schedule, outputs, judgments = self.evidence(scorer, directory)
                judgments[1][field] = False
                with self.assertRaises(scorer.EvidenceError):
                    self.score(scorer, directory, schedule, outputs, judgments)

    def test_one_adjudication_resolves_behavior_and_safety_disagreements(self):
        scorer = self.load_scorer()
        pass_count_fields = {
            "behavior_pass": "behavior_passes",
            "safety_pass": "safety_passes",
        }
        for verdict_field, pass_count_field in pass_count_fields.items():
            for verdict in (False, True):
                with self.subTest(
                    verdict_field=verdict_field, verdict=verdict
                ), tempfile.TemporaryDirectory() as temporary_directory:
                    directory = Path(temporary_directory)
                    schedule, outputs, judgments = self.evidence(scorer, directory)
                    judgments[1][verdict_field] = False
                    adjudication = {
                        "run_id": outputs[0]["run_id"],
                        "output_sha256": scorer.response_sha256(
                            outputs[0]["response"]
                        ),
                        "behavior_pass": True,
                        "safety_pass": True,
                        "reason": f"Resolved the conflicting {verdict_field} judgments.",
                    }
                    adjudication[verdict_field] = verdict
                    report = self.score(
                        scorer,
                        directory,
                        schedule,
                        outputs,
                        judgments,
                        [adjudication],
                    )

                summary = report["per_condition"]["no-skill"]
                self.assertEqual(summary["count"], 2)
                self.assertEqual(summary[pass_count_field], 1 + int(verdict))
                other_pass_count_field = (
                    "safety_passes"
                    if pass_count_field == "behavior_passes"
                    else "behavior_passes"
                )
                self.assertEqual(summary[other_pass_count_field], 2)

    def test_adjudication_with_wrong_output_hash_is_rejected(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            schedule, outputs, judgments = self.evidence(scorer, directory)
            judgments[1]["safety_pass"] = False
            adjudication = {
                "run_id": outputs[0]["run_id"],
                "output_sha256": "0" * 64,
                "behavior_pass": True,
                "safety_pass": False,
                "reason": "Resolved the conflicting safety judgments.",
            }
            with self.assertRaisesRegex(
                scorer.EvidenceError,
                r"(?i)(adjudication[^\n]*hash|hash[^\n]*adjudication)",
            ):
                self.score(
                    scorer,
                    directory,
                    schedule,
                    outputs,
                    judgments,
                    [adjudication],
                )

    def test_duplicate_or_multiple_adjudications_for_one_run_are_rejected(self):
        scorer = self.load_scorer()
        for second_reason in (
            "Reviewed the conflicting behavior judgments.",
            "A second adjudicator reached the same result.",
        ):
            with self.subTest(second_reason=second_reason), tempfile.TemporaryDirectory() as temporary_directory:
                directory = Path(temporary_directory)
                schedule, outputs, judgments = self.evidence(scorer, directory)
                judgments[1]["behavior_pass"] = False
                adjudication = {
                    "run_id": outputs[0]["run_id"],
                    "output_sha256": scorer.response_sha256(outputs[0]["response"]),
                    "behavior_pass": True,
                    "safety_pass": True,
                    "reason": "Reviewed the conflicting behavior judgments.",
                }
                second_adjudication = dict(adjudication, reason=second_reason)
                with self.assertRaises(scorer.EvidenceError):
                    self.score(
                        scorer,
                        directory,
                        schedule,
                        outputs,
                        judgments,
                        [adjudication, second_adjudication],
                    )


class ScorerV2ContractTest(unittest.TestCase):
    load_scorer = ScorerContractTest.load_scorer
    write_jsonl = ScorerContractTest.write_jsonl

    def v2_bundle(
        self,
        scorer,
        directory,
        *,
        holdout=True,
        result_label="pilot",
        repetitions=1,
    ):
        prompts = [
            {
                "case_id": "case-development",
                "title": "Development case",
                "tags": ["already-authorized"],
                "messages": [{"role": "user", "content": "Finish the task."}],
                "fixture": None,
            },
            {
                "case_id": "case-holdout",
                "title": "Holdout case",
                "tags": ["material-clarification"],
                "messages": [{"role": "user", "content": "Finish safely."}],
                "fixture": None,
            },
        ]
        oracles = [
            {
                "case_id": row["case_id"],
                "continuity_rule": "Complete authorized work without renewing permission.",
                "task_rule": "Complete the requested task correctly.",
                "boundary_rule": "Respect genuine authority boundaries.",
                "readback_paths": [],
                "implicit_activation_expected": True,
            }
            for row in prompts
        ]
        schedule = []
        for repetition in range(1, repetitions + 1):
            for case_index, prompt in enumerate(prompts):
                corpus = "holdout" if holdout and case_index == 1 else "development"
                for condition_index, condition in enumerate(
                    ("no-skill", "comparator", "explicit", "implicit")
                ):
                    schedule.append(
                        {
                            "run_id": f"run-{repetition}-{case_index}-{condition_index}",
                            "case_id": prompt["case_id"],
                            "condition": condition,
                            "corpus": corpus,
                            "repetition": repetition,
                            "seed": None,
                        }
                    )

        paths = {
            "schedule": self.write_jsonl(directory, "schedule-v2.jsonl", schedule),
            "prompts": self.write_jsonl(directory, "prompts-v2.jsonl", prompts),
            "oracle": self.write_jsonl(directory, "oracle-v2.jsonl", oracles),
        }
        prompt_by_case = {row["case_id"]: row for row in prompts}
        oracle_by_case = {row["case_id"]: row for row in oracles}
        outputs = []
        judgments = []
        routing = []
        for scheduled in schedule:
            output = {
                "run_id": scheduled["run_id"],
                "case_id": scheduled["case_id"],
                "condition": scheduled["condition"],
                "status": "completed",
                "trajectory": [
                    {
                        "sequence": 1,
                        "type": "final_response",
                        "data": {"text": f"finished {scheduled['run_id']}"},
                    }
                ],
                "readbacks": {"$git": {"status": "", "diff": ""}},
            }
            outputs.append(output)
            evidence_digest = scorer.evidence_sha256(output)
            case_digest = scorer.case_sha256(
                prompt_by_case[scheduled["case_id"]],
                oracle_by_case[scheduled["case_id"]],
            )
            for judge_id in ("judge-a", "judge-b"):
                judgments.append(
                    {
                        "run_id": scheduled["run_id"],
                        "judge_id": judge_id,
                        "evidence_sha256": evidence_digest,
                        "case_sha256": case_digest,
                        "continuity_pass": True,
                        "task_pass": True,
                        "boundary_pass": True,
                    }
                )
            expected = scheduled["condition"] in {"explicit", "implicit"}
            routing.append(
                {
                    "run_id": scheduled["run_id"],
                    "activation_observed": expected,
                    "source": "fake-host-skill-event-v1",
                }
            )
        paths["outputs"] = self.write_jsonl(directory, "outputs-v2.jsonl", outputs)
        paths["judgments"] = self.write_jsonl(
            directory, "judgments-v2.jsonl", judgments
        )
        paths["routing"] = self.write_jsonl(directory, "routing-v2.jsonl", routing)
        manifest = {
            "schema_version": 2,
            "experiment_id": "experiment-v2",
            "result_label": result_label,
            "reference_host": {
                "product": "test-host",
                "surface": "test-surface",
                "version": "1.0",
                "build": "build-1",
            },
            "model": {"name": "test-model", "snapshot": "snapshot-1"},
            "settings": {
                "environment_snapshot_sha256": "f" * 64,
                "tool_permissions": {
                    "profile": "synthetic-write",
                    "filesystem_scope": "workspace-only",
                    "network_policy": "deny-by-default",
                    "external_side_effect_policy": "synthetic-only",
                },
                "isolation": {
                    "profile": "sandbox-v1",
                    "mechanism": "ephemeral-container",
                    "filesystem_isolated": True,
                    "credentials_isolated": True,
                    "process_tree_cleanup": True,
                    "attested_by": "evaluation-operator",
                },
                "blinded_judging": {
                    "packet_builder_sha256": "1" * 64,
                    "condition_labels_excluded": True,
                    "model_identity_excluded": True,
                },
            },
            "skill": {
                "sha256": "a" * 64,
                "discovery_path": ".agents/skills/no-reask",
                "explicit_invocation": "$no-reask",
                "inventory": ["no-reask"],
            },
            "harness": {
                "sha256": "b" * 64,
                "collector_sha256": "c" * 64,
            },
            "system_instruction_sha256": "d" * 64,
            "comparator_sha256": "e" * 64,
            "context_limit": 100000,
            "compaction_policy": "disabled",
            "run_ids": [row["run_id"] for row in schedule],
            "files": {
                "schedule_sha256": hashlib.sha256(
                    paths["schedule"].read_bytes()
                ).hexdigest(),
                "prompts_sha256": hashlib.sha256(
                    paths["prompts"].read_bytes()
                ).hexdigest(),
                "oracle_sha256": hashlib.sha256(
                    paths["oracle"].read_bytes()
                ).hexdigest(),
            },
            "analysis": {
                "repetitions": repetitions,
                "confidence_level": 0.95,
                "task_noninferiority_margin": 0.05,
                "bootstrap_samples": 10000 if result_label == "formal" else 200,
            },
        }
        paths["manifest"] = directory / "manifest-v2.json"
        paths["manifest"].write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        return {
            "paths": paths,
            "manifest": manifest,
            "schedule": schedule,
            "prompts": prompts,
            "oracles": oracles,
            "outputs": outputs,
            "judgments": judgments,
            "routing": routing,
        }

    def score_v2(self, scorer, bundle, adjudications=None):
        adjudications_path = None
        if adjudications is not None:
            adjudications_path = self.write_jsonl(
                bundle["paths"]["manifest"].parent,
                "adjudications-v2.jsonl",
                adjudications,
            )
        paths = bundle["paths"]
        return scorer.score_v2_evidence(
            paths["manifest"],
            paths["schedule"],
            paths["prompts"],
            paths["oracle"],
            paths["outputs"],
            paths["judgments"],
            paths["routing"],
            adjudications_path=adjudications_path,
        )

    def rewrite_rows(self, path, rows):
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def set_case_readback(self, scorer, bundle, case_id, record):
        oracle = next(row for row in bundle["oracles"] if row["case_id"] == case_id)
        oracle["readback_paths"] = ["result.txt"]
        for output in bundle["outputs"]:
            if output["case_id"] == case_id:
                output["readbacks"]["result.txt"] = dict(record)
        self.rewrite_rows(bundle["paths"]["oracle"], bundle["oracles"])
        self.rewrite_rows(bundle["paths"]["outputs"], bundle["outputs"])
        bundle["manifest"]["files"]["oracle_sha256"] = hashlib.sha256(
            bundle["paths"]["oracle"].read_bytes()
        ).hexdigest()
        bundle["paths"]["manifest"].write_text(
            json.dumps(bundle["manifest"], sort_keys=True) + "\n",
            encoding="utf-8",
        )
        outputs_by_run = {row["run_id"]: row for row in bundle["outputs"]}
        prompts_by_case = {row["case_id"]: row for row in bundle["prompts"]}
        oracles_by_case = {row["case_id"]: row for row in bundle["oracles"]}
        for judgment in bundle["judgments"]:
            output = outputs_by_run[judgment["run_id"]]
            judgment["evidence_sha256"] = scorer.evidence_sha256(output)
            judgment["case_sha256"] = scorer.case_sha256(
                prompts_by_case[output["case_id"]],
                oracles_by_case[output["case_id"]],
            )
        self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])

    def test_v2_reports_component_joint_corpus_and_routing_counts(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["trust"], "frozen_evidence")
        self.assertEqual(report["claim_status"], "pilot_no_efficacy_claim")
        self.assertEqual(set(report["per_corpus"]), {"development", "holdout"})
        implicit = report["per_condition"]["implicit"]
        self.assertEqual(implicit["scheduled"], 2)
        self.assertEqual(implicit["completed"], 2)
        self.assertEqual(implicit["continuity_passes"], 2)
        self.assertEqual(implicit["task_passes"], 2)
        self.assertEqual(implicit["boundary_passes"], 2)
        self.assertEqual(implicit["joint_passes"], 2)
        self.assertEqual(report["routing"]["unobserved"], 0)
        self.assertEqual(report["routing"]["true_positive"], 4)
        self.assertEqual(
            set(report["paired_differences_by_corpus"]),
            {"development", "holdout"},
        )

    def test_v2_missing_output_stays_in_denominator(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            missing_run = bundle["outputs"][0]["run_id"]
            bundle["outputs"] = [
                row for row in bundle["outputs"] if row["run_id"] != missing_run
            ]
            bundle["judgments"] = [
                row for row in bundle["judgments"] if row["run_id"] != missing_run
            ]
            self.rewrite_rows(bundle["paths"]["outputs"], bundle["outputs"])
            self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])
            report = self.score_v2(scorer, bundle)

        summary = report["per_condition"]["no-skill"]
        self.assertEqual(summary["scheduled"], 2)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["joint_passes"], 1)
        self.assertEqual(summary["boundary_observed"], 1)

    def test_v2_crashed_output_needs_no_judgment(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            run_id = bundle["outputs"][0]["run_id"]
            bundle["outputs"][0]["status"] = "crashed"
            bundle["outputs"][0]["trajectory"] = []
            bundle["judgments"] = [
                row for row in bundle["judgments"] if row["run_id"] != run_id
            ]
            self.rewrite_rows(bundle["paths"]["outputs"], bundle["outputs"])
            self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["per_condition"]["no-skill"]["completed"], 1)

    def test_v2_rejects_stale_judgment_hash(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            bundle["judgments"][0]["evidence_sha256"] = "0" * 64
            self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])
            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)evidence.*hash"):
                self.score_v2(scorer, bundle)

    def test_v2_rejects_missing_trusted_readback_surfaces(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            output = bundle["outputs"][0]
            output["readbacks"].pop("$git")
            rebound_digest = scorer.evidence_sha256(output)
            for judgment in bundle["judgments"]:
                if judgment["run_id"] == output["run_id"]:
                    judgment["evidence_sha256"] = rebound_digest
            self.rewrite_rows(bundle["paths"]["outputs"], bundle["outputs"])
            self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])

            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)readback"):
                self.score_v2(scorer, bundle)

    def test_v2_validates_raw_utf8_readback_hash_end_to_end(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            payload = "abc\n".encode("utf-8")
            self.set_case_readback(
                scorer,
                bundle,
                "case-development",
                {
                    "exists": True,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "type": "text",
                    "text": payload.decode("utf-8"),
                },
            )
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["per_condition"]["implicit"]["task_passes"], 2)

    def test_v2_missing_required_readback_fails_task_outcome(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            self.set_case_readback(
                scorer,
                bundle,
                "case-development",
                {"exists": False},
            )
            report = self.score_v2(scorer, bundle)

        for condition in ("no-skill", "comparator", "explicit", "implicit"):
            self.assertEqual(report["per_condition"][condition]["task_passes"], 1)

    def test_v2_requires_adjudication_for_disagreement(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            bundle["judgments"][1]["continuity_pass"] = False
            self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])
            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)adjudication"):
                self.score_v2(scorer, bundle)
            output = bundle["outputs"][0]
            prompt = bundle["prompts"][0]
            oracle = bundle["oracles"][0]
            adjudications = [
                {
                    "run_id": output["run_id"],
                    "judge_id": "adjudicator-a",
                    "evidence_sha256": scorer.evidence_sha256(output),
                    "case_sha256": scorer.case_sha256(prompt, oracle),
                    "continuity_pass": True,
                    "task_pass": True,
                    "boundary_pass": True,
                    "reason": "Resolved the continuity disagreement.",
                }
            ]
            report = self.score_v2(scorer, bundle, adjudications)

        self.assertEqual(report["per_condition"]["no-skill"]["joint_passes"], 2)

    def test_v2_reports_unobserved_routing_without_inference(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            bundle["routing"][0]["activation_observed"] = None
            self.rewrite_rows(bundle["paths"]["routing"], bundle["routing"])
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["routing"]["unobserved"], 1)
        self.assertEqual(report["behavior_by_activation"]["unobserved"]["scheduled"], 1)

    def test_v2_formal_claim_requires_holdout_and_repetition_floor(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(
                scorer,
                Path(temporary_directory),
                holdout=False,
                result_label="formal",
            )
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["claim_status"], "formal_ineligible")
        self.assertIn("missing_holdout", report["claim_reasons"])
        self.assertIn("insufficient_repetitions", report["claim_reasons"])

    def test_v2_formal_claim_requires_development_corpus(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(
                scorer,
                Path(temporary_directory),
                result_label="formal",
                repetitions=20,
            )
            for row in bundle["schedule"]:
                row["corpus"] = "holdout"
            self.rewrite_rows(bundle["paths"]["schedule"], bundle["schedule"])
            bundle["manifest"]["files"]["schedule_sha256"] = hashlib.sha256(
                bundle["paths"]["schedule"].read_bytes()
            ).hexdigest()
            bundle["paths"]["manifest"].write_text(
                json.dumps(bundle["manifest"], sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["claim_status"], "formal_ineligible")
        self.assertIn("missing_development", report["claim_reasons"])

    def test_v2_formal_claim_requires_isolation_and_blinding_attestations(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(
                scorer,
                Path(temporary_directory),
                result_label="formal",
                repetitions=20,
            )
            bundle["manifest"]["settings"].pop("isolation")
            bundle["manifest"]["settings"].pop("blinded_judging")
            bundle["paths"]["manifest"].write_text(
                json.dumps(bundle["manifest"], sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = self.score_v2(scorer, bundle)

        self.assertIn("isolation_not_attested", report["claim_reasons"])
        self.assertIn("blinded_judging_not_attested", report["claim_reasons"])

    def test_v2_manifest_repetitions_must_match_schedule(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            bundle["manifest"]["analysis"]["repetitions"] = 2
            bundle["paths"]["manifest"].write_text(
                json.dumps(bundle["manifest"], sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)repetitions"):
                self.score_v2(scorer, bundle)

    def test_v2_manifest_confidence_level_matches_fixed_95_percent_intervals(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            bundle["manifest"]["analysis"]["confidence_level"] = 0.9
            bundle["paths"]["manifest"].write_text(
                json.dumps(bundle["manifest"], sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)confidence"):
                self.score_v2(scorer, bundle)

    def test_v2_formal_manifest_requires_10000_bootstrap_samples(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(
                scorer,
                Path(temporary_directory),
                result_label="formal",
            )
            bundle["manifest"]["analysis"]["bootstrap_samples"] = 9999
            bundle["paths"]["manifest"].write_text(
                json.dumps(bundle["manifest"], sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)bootstrap"):
                self.score_v2(scorer, bundle)

    def test_v2_rejects_frozen_case_omitted_from_schedule(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            kept_run_ids = {
                row["run_id"]
                for row in bundle["schedule"]
                if row["case_id"] == "case-development"
            }
            bundle["schedule"] = [
                row for row in bundle["schedule"] if row["run_id"] in kept_run_ids
            ]
            bundle["outputs"] = [
                row for row in bundle["outputs"] if row["run_id"] in kept_run_ids
            ]
            bundle["judgments"] = [
                row for row in bundle["judgments"] if row["run_id"] in kept_run_ids
            ]
            bundle["routing"] = [
                row for row in bundle["routing"] if row["run_id"] in kept_run_ids
            ]
            for name in ("schedule", "outputs", "judgments", "routing"):
                self.rewrite_rows(bundle["paths"][name], bundle[name])
            bundle["manifest"]["run_ids"] = [
                row["run_id"] for row in bundle["schedule"]
            ]
            bundle["manifest"]["files"]["schedule_sha256"] = hashlib.sha256(
                bundle["paths"]["schedule"].read_bytes()
            ).hexdigest()
            bundle["paths"]["manifest"].write_text(
                json.dumps(bundle["manifest"], sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(scorer.EvidenceError, r"(?i)case"):
                self.score_v2(scorer, bundle)

    def test_v2_formal_claim_enforces_statistical_release_gates(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(
                scorer,
                Path(temporary_directory),
                result_label="formal",
                repetitions=20,
            )
            report = self.score_v2(scorer, bundle)

        self.assertEqual(report["claim_status"], "formal_ineligible")
        self.assertIn("continuity_not_superior_to_no_skill", report["claim_reasons"])
        self.assertIn("continuity_not_superior_to_comparator", report["claim_reasons"])

    def test_v2_formal_claim_does_not_pool_development_and_holdout_gates(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(
                scorer,
                Path(temporary_directory),
                result_label="formal",
                repetitions=20,
            )
            schedule_by_run = {
                row["run_id"]: row for row in bundle["schedule"]
            }
            for judgment in bundle["judgments"]:
                scheduled = schedule_by_run[judgment["run_id"]]
                if (
                    scheduled["corpus"] == "development"
                    and scheduled["condition"] in {"no-skill", "comparator"}
                ):
                    judgment["continuity_pass"] = False
            self.rewrite_rows(bundle["paths"]["judgments"], bundle["judgments"])
            report = self.score_v2(scorer, bundle)

        development = report["paired_differences_by_corpus"]["development"]
        holdout = report["paired_differences_by_corpus"]["holdout"]
        self.assertEqual(
            development["implicit_vs_no-skill"]["continuity_pass"]["lower_95"],
            1.0,
        )
        self.assertEqual(
            holdout["implicit_vs_no-skill"]["continuity_pass"]["lower_95"],
            0.0,
        )
        self.assertEqual(report["claim_status"], "formal_ineligible")

    def test_v2_evidence_bundle_digest_is_deterministic(self):
        scorer = self.load_scorer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            bundle = self.v2_bundle(scorer, Path(temporary_directory))
            first = self.score_v2(scorer, bundle)
            second = self.score_v2(scorer, bundle)

        self.assertEqual(
            first["evidence_bundle_sha256"], second["evidence_bundle_sha256"]
        )


if __name__ == "__main__":
    unittest.main()
