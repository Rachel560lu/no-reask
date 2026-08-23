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
            try:
                row = json.loads(line)
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
                {"case_id", "title", "tags", "messages"},
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
            "behavior_rule",
            "safety_rule",
            "implicit_activation_expected",
        }
        for index, row in enumerate(rows, start=1):
            context = f"evaluation-oracle.jsonl row {index}"
            self.assertEqual(set(row), required, f"{context} has wrong fields")
            for field in ("case_id", "behavior_rule", "safety_rule"):
                self.assert_non_empty_string(row, field, context)
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
                set(row), {"run_id", "case_id", "condition"}, f"{context} has wrong fields"
            )
            for field in ("run_id", "case_id", "condition"):
                self.assert_non_empty_string(row, field, context)
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
            [f"run-{index:03d}" for index in range(1, 33)],
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
            row["case_id"]: row["safety_rule"]
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
            "canonical prompt messages unchanged",
            "prepend exactly one `system` message",
            "exact contents of `comparator.txt`, byte for byte",
            "prefix the first `user` message content with `$no-reask `",
            "`artifacts/run-manifest.json`",
            '"experiment_id":"string"',
            '"host":"string"',
            '"host_version":"string"',
            '"model":"string"',
            '"model_version":"string"',
            '"settings":{}',
            "one shared manifest covers all four conditions",
            "scorer does not validate environment parity",
            "opaque `blind_id`",
            "canonical untransformed prompt",
            "must not contain the condition, injected instruction, run ID, or case name",
            "After all first-pass judgments have been collected",
            "at least two independent, blinded judge records",
        )
        for text in required_text:
            with self.subTest(text=text):
                self.assertIn(text, protocol)


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


if __name__ == "__main__":
    unittest.main()
