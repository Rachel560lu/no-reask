import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


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
            summary = runner.run_smoke(self.args(adapter, artifacts))

            self.assertEqual(summary["result_label"], "pilot")
            self.assertEqual(summary["claim_status"], "pilot_no_efficacy_claim")
            self.assertEqual(summary["scheduled"], 40)
            self.assertEqual(summary["completed"], 40)
            self.assertEqual(summary["efficacy_result"], None)
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
            self.assertEqual(len(manifest["run_ids"]), 40)
            outputs = [
                json.loads(line)
                for line in (artifacts / "evaluation-outputs.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(outputs), 40)
            workdirs = {event["data"].get("working_directory") for output in outputs for event in output["trajectory"] if event["type"] == "collector"}
            self.assertEqual(len(workdirs), 40)
            for workdir in workdirs:
                names = {path.name for path in Path(workdir).iterdir()}
                self.assertNotIn("evaluation-oracle.jsonl", names)
                self.assertNotIn("evaluation-judgments.jsonl", names)

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


if __name__ == "__main__":
    unittest.main()
