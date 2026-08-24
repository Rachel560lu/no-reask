import importlib.util
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"


class SmokeRunnerTest(unittest.TestCase):
    def load_runner(self):
        path = EVALS / "run_smoke.py"
        self.assertTrue(path.is_file(), "evals/run_smoke.py must exist")
        spec = importlib.util.spec_from_file_location("run_smoke_contract", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(spec.name)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            if previous is None:
                sys.modules.pop(spec.name, None)
            else:
                sys.modules[spec.name] = previous
        return module

    def make_adapter(self, directory, behavior="success"):
        path = directory / f"adapter-{behavior}.py"
        behaviors = {
            "success": """
packet = json.load(sys.stdin)
Path("adapter-packet.json").write_text(json.dumps(packet), encoding="utf-8")
print(json.dumps({
    "trajectory": [{"sequence": 1, "type": "final_response", "data": {"text": "done"}}],
    "activation_observed": packet["condition"] in {"explicit", "implicit"},
    "routing_source": "fake-host-skill-event-v1",
}))
""",
            "crash": "raise SystemExit(7)\n",
            "invalid": "print('not-json')\n",
            "timeout": "import time\ntime.sleep(2)\n",
            "tamper": """
packet = json.load(sys.stdin)
skill = Path(".agents/skills/no-reask/SKILL.md")
skill.write_text(skill.read_text(encoding="utf-8") + "\\ntampered\\n", encoding="utf-8")
print(json.dumps({
    "trajectory": [{"sequence": 1, "type": "final_response", "data": {"text": "done"}}],
    "activation_observed": True,
    "routing_source": "fake-host-skill-event-v1",
}))
""",
        }
        source = (
            f"#!{sys.executable}\n"
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            + behaviors[behavior]
        )
        path.write_text(source, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def args(self, adapter, artifacts, timeout=1.0):
        return SimpleNamespace(
            adapter=adapter,
            artifacts=artifacts,
            host_product="fake-host",
            host_surface="fixture",
            host_version="1.0",
            host_build="build-1",
            model="fake-model",
            model_snapshot="snapshot-1",
            timeout_seconds=timeout,
            context_limit=100000,
            compaction_policy="disabled",
        )

    def test_condition_transformations_are_exact_and_nonmutating(self):
        runner = self.load_runner()
        messages = [{"role": "user", "content": "Do every requested step."}]
        comparator = "Finish the request.\n"

        no_skill = runner.transform_messages(messages, "no-skill", comparator)
        implicit = runner.transform_messages(messages, "implicit", comparator)
        explicit = runner.transform_messages(messages, "explicit", comparator)
        compared = runner.transform_messages(messages, "comparator", comparator)

        self.assertEqual(no_skill, messages)
        self.assertEqual(implicit, messages)
        self.assertEqual(
            explicit, [{"role": "user", "content": "$no-reask Do every requested step."}]
        )
        self.assertEqual(
            compared,
            [
                {"role": "system", "content": comparator},
                {"role": "user", "content": "Do every requested step."},
            ],
        )
        self.assertIsNot(no_skill, messages)
        self.assertEqual(messages[0]["content"], "Do every requested step.")

    def test_run_one_freezes_adapter_success_without_a_shell(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            adapter = self.make_adapter(directory)
            workdir = directory / "work"
            workdir.mkdir()
            result = runner.run_one(
                adapter,
                {"run_id": "run-1", "condition": "implicit", "messages": []},
                workdir,
                1.0,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["routing_source"], "fake-host-skill-event-v1")
        self.assertTrue(result["activation_observed"])
        self.assertEqual(result["trajectory"][0]["type"], "final_response")

    def test_run_one_converts_adapter_failures_to_frozen_statuses(self):
        runner = self.load_runner()
        expected = {"crash": "crashed", "invalid": "invalid", "timeout": "timed_out"}
        for behavior, status in expected.items():
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temporary_directory:
                directory = Path(temporary_directory)
                adapter = self.make_adapter(directory, behavior)
                workdir = directory / "work"
                workdir.mkdir()
                result = runner.run_one(
                    adapter,
                    {"run_id": "run-1", "condition": "implicit", "messages": []},
                    workdir,
                    0.05 if behavior == "timeout" else 1.0,
                )
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["activation_observed"])
            self.assertTrue(result["trajectory"])

    def test_smoke_run_freezes_all_conditions_as_a_pilot(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            adapter = self.make_adapter(directory)
            artifacts = directory / "artifacts"
            environment_snapshot = directory / "environment.json"
            environment_snapshot.write_text(
                json.dumps(
                    {
                        "reference_host": {
                            "product": "snapshot-host",
                            "surface": "snapshot-surface",
                            "version": "2.0",
                            "build": "build-2",
                        },
                        "model": {
                            "name": "snapshot-model",
                            "snapshot": "snapshot-2",
                        },
                        "settings": {"temperature": 0},
                        "system_instruction_sha256": "a" * 64,
                        "context_limit": 200000,
                        "compaction_policy": "disabled",
                        "tool_permissions": {
                            "profile": "synthetic-write",
                            "filesystem_scope": "workspace-only",
                            "network_policy": "deny-by-default",
                            "external_side_effect_policy": "synthetic-only",
                        },
                        "isolation": {
                            "profile": "adapter-sandbox-v1",
                            "mechanism": "ephemeral-container",
                            "filesystem_isolated": True,
                            "credentials_isolated": True,
                            "process_tree_cleanup": True,
                            "attested_by": "evaluation-operator",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            original_run_one = runner.run_one
            manifest_was_frozen = []

            def checking_run_one(*args, **kwargs):
                manifest_was_frozen.append(
                    (artifacts / "run-manifest.json").is_file()
                )
                return original_run_one(*args, **kwargs)

            arguments = self.args(adapter, artifacts)
            arguments.environment_snapshot = environment_snapshot
            with mock.patch.object(runner, "run_one", side_effect=checking_run_one):
                summary = runner.run_smoke(arguments)

            self.assertEqual(summary["result_label"], "pilot")
            self.assertEqual(summary["claim_status"], "pilot_no_efficacy_claim")
            self.assertEqual(summary["scheduled"], 40)
            self.assertEqual(summary["completed"], 40)
            self.assertEqual(summary["efficacy_result"], None)
            self.assertEqual(manifest_was_frozen, [True] * 40)
            required = {
                "run-manifest.json",
                "evaluation-schedule.jsonl",
                "evaluation-outputs.jsonl",
                "evaluation-routing.jsonl",
                "smoke-summary.json",
            }
            self.assertTrue(required.issubset({path.name for path in artifacts.iterdir()}))
            manifest = json.loads((artifacts / "run-manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["result_label"], "pilot")
            self.assertEqual(manifest["reference_host"]["product"], "snapshot-host")
            self.assertEqual(manifest["model"]["name"], "snapshot-model")
            self.assertEqual(manifest["settings"]["temperature"], 0)
            self.assertEqual(
                manifest["settings"]["environment_snapshot_sha256"],
                hashlib.sha256(environment_snapshot.read_bytes()).hexdigest(),
            )
            self.assertEqual(len(manifest["run_ids"]), 40)
            outputs = [
                json.loads(line)
                for line in (artifacts / "evaluation-outputs.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(outputs), 40)
            for output in outputs:
                git_readback = output["readbacks"]["$git"]
                self.assertNotIn(".agents", git_readback["status"])
                self.assertNotIn(".agents", git_readback["diff"])
            collector_events = [
                event
                for output in outputs
                for event in output["trajectory"]
                if event["type"] == "collector"
            ]
            self.assertEqual(len(collector_events), 40)
            self.assertTrue(
                all(event["data"] == {"workspace_retained": False} for event in collector_events)
            )
            self.assertFalse((artifacts / "runs").exists())

    def test_environment_snapshot_rejects_empty_isolation_attestation(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "environment.json"
            path.write_text(
                json.dumps(
                    {
                        "reference_host": {
                            "product": "host",
                            "surface": "surface",
                            "version": "1",
                            "build": "1",
                        },
                        "model": {"name": "model", "snapshot": "snapshot"},
                        "settings": {},
                        "system_instruction_sha256": "a" * 64,
                        "context_limit": 1000,
                        "compaction_policy": "disabled",
                        "tool_permissions": {
                            "profile": "synthetic-write",
                            "filesystem_scope": "workspace-only",
                            "network_policy": "deny-by-default",
                            "external_side_effect_policy": "synthetic-only",
                        },
                        "isolation": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(runner.EvidenceError, r"(?i)isolation"):
                runner.load_environment_snapshot(path)

    def test_runner_collects_declared_files_instead_of_adapter_readbacks(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            adapter = self.make_adapter(directory)
            workdir = directory / "work"
            workdir.mkdir()
            source = workdir / "result.txt"
            source.write_text("trusted collector text\n", encoding="utf-8")
            readbacks = runner.collect_readbacks(workdir, ["result.txt", "missing.txt"])

        self.assertEqual(readbacks["result.txt"]["text"], "trusted collector text\n")
        self.assertEqual(readbacks["result.txt"]["type"], "text")
        self.assertFalse(readbacks["missing.txt"]["exists"])
        with self.assertRaises(runner.EvidenceError):
            runner.collect_readbacks(workdir, ["../oracle.jsonl"])

    def test_runner_rejects_readback_through_symlinked_parent(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            workdir = directory / "work"
            outside = directory / "outside"
            workdir.mkdir()
            outside.mkdir()
            (outside / "oracle.txt").write_text("secret\n", encoding="utf-8")
            (workdir / "linked").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(runner.EvidenceError, r"(?i)escapes"):
                runner.collect_readbacks(workdir, ["linked/oracle.txt"])

    def test_runner_rejects_oversized_readback_before_reading_it(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            (workdir / "large.txt").write_bytes(
                b"a" * (runner.MAX_READBACK_BYTES + 1)
            )

            with self.assertRaisesRegex(runner.EvidenceError, r"(?i)too large"):
                runner.collect_readbacks(workdir, ["large.txt"])

    def test_runner_preserves_evidence_of_runtime_skill_tampering(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            adapter = self.make_adapter(directory, "tamper")
            runtime_snapshot = directory / "runtime"
            shutil.copytree(ROOT / "no-reask", runtime_snapshot)
            output, _ = runner._execute_scheduled_run(
                self.args(adapter, directory / "artifacts"),
                {
                    "run_id": "run-tamper",
                    "case_id": "case-tamper",
                    "condition": "explicit",
                },
                {
                    "case_id": "case-tamper",
                    "messages": [{"role": "user", "content": "Finish it."}],
                    "fixture": None,
                },
                {"case_id": "case-tamper", "readback_paths": []},
                "Finish the request.\n",
                runtime_snapshot,
            )

        git_evidence = output["readbacks"]["$git"]
        self.assertIn(".agents/skills/no-reask/SKILL.md", git_evidence["status"])
        self.assertIn("tampered", git_evidence["diff"])


if __name__ == "__main__":
    unittest.main()
