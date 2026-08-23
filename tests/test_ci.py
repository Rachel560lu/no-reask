import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
TEST_COMMAND = 'python -I -m unittest discover -s tests -p "test_*.py" -v'


class ContinuousIntegrationContractTest(unittest.TestCase):
    def read_workflow(self):
        self.assertTrue(WORKFLOW.is_file(), ".github/workflows/test.yml must exist")
        return WORKFLOW.read_text(encoding="utf-8")

    def yaml_lines(self, document):
        lines = []
        block_scalar_indent = None
        for line_number, raw_line in enumerate(document.splitlines(), start=1):
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            self.assertNotIn(
                "\t", raw_line, f"workflow line {line_number} must not contain tabs"
            )
            content = raw_line.lstrip(" ")
            indent = len(raw_line) - len(content)
            if block_scalar_indent is not None:
                if indent > block_scalar_indent:
                    continue
                block_scalar_indent = None
            lines.append((indent, content))
            _, separator, raw_value = self.mapping_parts(content.lstrip("- "))
            if separator and self.scalar(raw_value) in {
                "|",
                ">",
                "|-",
                ">-",
                "|+",
                ">+",
            }:
                block_scalar_indent = indent
        return lines

    @staticmethod
    def mapping_parts(content):
        key, separator, raw_value = content.partition(":")
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1]
        return key, separator, raw_value

    @staticmethod
    def scalar(raw_value):
        value = raw_value.strip()
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value

    @staticmethod
    def nested_block(lines, index):
        parent_indent = lines[index][0]
        end = index + 1
        while end < len(lines) and lines[end][0] > parent_indent:
            end += 1
        return lines[index + 1 : end]

    def find_mapping(self, lines, key, indent=None):
        matches = []
        for index, (line_indent, content) in enumerate(lines):
            mapping_key, separator, raw_value = self.mapping_parts(content)
            if separator and mapping_key == key and (
                indent is None or line_indent == indent
            ):
                matches.append((index, raw_value))
        self.assertEqual(len(matches), 1, f"workflow must define one {key} mapping")
        index, raw_value = matches[0]
        return self.scalar(raw_value), self.nested_block(lines, index)

    def direct_mapping_fields(self, lines):
        if not lines:
            return {}
        direct_indent = min(indent for indent, _ in lines)
        fields = {}
        for indent, content in lines:
            if indent != direct_indent or content.startswith("-"):
                continue
            key, separator, raw_value = self.mapping_parts(content)
            if separator:
                fields[key] = self.scalar(raw_value)
        return fields

    def list_mapping_items(self, lines):
        item_indents = [
            indent
            for indent, content in lines
            if content == "-" or content.startswith("- ")
        ]
        self.assertTrue(item_indents, "include/steps must be a YAML list")
        item_indent = min(item_indents)
        item_starts = [
            index
            for index, (indent, content) in enumerate(lines)
            if indent == item_indent and (content == "-" or content.startswith("- "))
        ]
        items = []
        for position, start in enumerate(item_starts):
            end = (
                item_starts[position + 1]
                if position + 1 < len(item_starts)
                else len(lines)
            )
            body = lines[start][1][1:].strip()
            fields = {}
            if body:
                key, separator, raw_value = self.mapping_parts(body)
                self.assertEqual(separator, ":", "list rows must contain mappings")
                fields[key] = self.scalar(raw_value)
            children = lines[start + 1 : end]
            if children:
                child_indent = min(indent for indent, _ in children)
                for indent, content in children:
                    if indent != child_indent or content.startswith("-"):
                        continue
                    key, separator, raw_value = self.mapping_parts(content)
                    if separator:
                        fields[key] = self.scalar(raw_value)
            items.append((fields, lines[start:end]))
        return items

    def list_mappings(self, lines):
        return [fields for fields, _ in self.list_mapping_items(lines)]

    def flow_sequence(self, value):
        self.assertTrue(
            value.startswith("[") and value.endswith("]"),
            "inline workflow triggers must be a sequence",
        )
        return {
            self.scalar(item) for item in value[1:-1].split(",") if item.strip()
        }

    def matrix_job(self, lines):
        _, jobs = self.find_mapping(lines, "jobs", indent=0)
        job_indent = min(indent for indent, _ in jobs)
        candidates = []
        for index, (indent, content) in enumerate(jobs):
            _, separator, _ = self.mapping_parts(content)
            if not separator or indent != job_indent:
                continue
            job = self.nested_block(jobs, index)
            direct_indent = min(child_indent for child_indent, _ in job)
            strategy_matches = [
                strategy_index
                for strategy_index, (child_indent, child_content) in enumerate(job)
                if child_indent == direct_indent
                and self.mapping_parts(child_content)[:2] == ("strategy", ":")
            ]
            if len(strategy_matches) != 1:
                continue
            strategy_index = strategy_matches[0]
            _, _, strategy_raw_value = self.mapping_parts(job[strategy_index][1])
            strategy = self.nested_block(job, strategy_index)
            if not strategy:
                continue
            strategy_indent = min(child_indent for child_indent, _ in strategy)
            matrix_matches = [
                matrix_index
                for matrix_index, (child_indent, child_content) in enumerate(strategy)
                if child_indent == strategy_indent
                and self.mapping_parts(child_content)[:2] == ("matrix", ":")
            ]
            if len(matrix_matches) != 1:
                continue
            matrix_index = matrix_matches[0]
            _, _, matrix_raw_value = self.mapping_parts(strategy[matrix_index][1])
            candidates.append(
                (
                    job,
                    self.scalar(strategy_raw_value),
                    self.scalar(matrix_raw_value),
                    self.nested_block(strategy, matrix_index),
                )
            )
        self.assertEqual(len(candidates), 1, "workflow must define one matrix job")
        job, strategy_value, matrix_value, matrix = candidates[0]
        self.assertFalse(strategy_value, "job.strategy must be a mapping")
        return job, matrix_value, matrix

    @staticmethod
    def normalized_expression(value):
        return "".join(value.split())

    def test_workflow_runs_for_pushes_and_pull_requests(self):
        lines = self.yaml_lines(self.read_workflow())
        value, block = self.find_mapping(lines, "on", indent=0)
        triggers = (
            self.flow_sequence(value)
            if value
            else set(self.direct_mapping_fields(block))
        )
        self.assertTrue({"push", "pull_request"}.issubset(triggers))

    def test_workflow_grants_read_only_contents_permission(self):
        lines = self.yaml_lines(self.read_workflow())
        value, block = self.find_mapping(lines, "permissions", indent=0)
        if value:
            self.assertTrue(value.startswith("{") and value.endswith("}"))
            fields = {}
            for item in value[1:-1].split(","):
                key, separator, raw_value = self.mapping_parts(item)
                self.assertEqual(separator, ":")
                fields[key] = self.scalar(raw_value)
        else:
            fields = self.direct_mapping_fields(block)
        self.assertEqual(fields, {"contents": "read"})

    def test_workflow_declares_exact_platform_and_python_pairs(self):
        lines = self.yaml_lines(self.read_workflow())
        _, matrix_value, matrix = self.matrix_job(lines)
        self.assertFalse(matrix_value, "matrix must contain an include mapping")
        self.assertEqual(
            set(self.direct_mapping_fields(matrix)),
            {"include"},
            "matrix combinations must be declared only through include entries",
        )
        direct_indent = min(indent for indent, _ in matrix)
        include_value, include = self.find_mapping(
            matrix, "include", indent=direct_indent
        )
        self.assertFalse(include_value, "matrix.include must be a list")
        entries = self.list_mappings(include)
        declared_pairs = [
            (entry.get("os"), entry.get("python-version")) for entry in entries
        ]
        expected_pairs = {
            ("ubuntu-latest", "3.10"),
            ("ubuntu-latest", "3.13"),
            ("macos-latest", "3.11"),
            ("windows-latest", "3.11"),
        }
        self.assertEqual(len(declared_pairs), 4)
        self.assertEqual(set(declared_pairs), expected_pairs)

    def test_matrix_job_consumes_platform_and_python_version(self):
        lines = self.yaml_lines(self.read_workflow())
        job, _, _ = self.matrix_job(lines)
        job_fields = self.direct_mapping_fields(job)
        self.assertEqual(
            self.normalized_expression(job_fields.get("runs-on", "")),
            "${{matrix.os}}",
        )

        direct_indent = min(indent for indent, _ in job)
        steps_value, steps = self.find_mapping(job, "steps", indent=direct_indent)
        self.assertFalse(steps_value, "matrix job steps must be a list")
        setup_items = [
            item
            for item in self.list_mapping_items(steps)
            if item[0].get("uses", "").startswith("actions/setup-python@")
        ]
        self.assertEqual(len(setup_items), 1, "matrix job needs one setup-python step")
        _, setup_step = setup_items[0]
        with_value, with_block = self.find_mapping(setup_step, "with")
        self.assertFalse(with_value, "setup-python.with must be a mapping")
        with_fields = self.direct_mapping_fields(with_block)
        self.assertEqual(
            self.normalized_expression(with_fields.get("python-version", "")),
            "${{matrix.python-version}}",
        )

    def test_workflow_runs_isolated_unittest_discovery(self):
        lines = self.yaml_lines(self.read_workflow())
        job, _, _ = self.matrix_job(lines)
        direct_indent = min(indent for indent, _ in job)
        steps_value, steps = self.find_mapping(job, "steps", indent=direct_indent)
        self.assertFalse(steps_value, "matrix job steps must be a list")
        commands = [
            step["run"] for step in self.list_mappings(steps) if "run" in step
        ]
        self.assertIn(TEST_COMMAND, commands)


if __name__ == "__main__":
    unittest.main()
