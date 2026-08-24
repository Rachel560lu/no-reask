import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageContractTest(unittest.TestCase):
    def read_required(self, relative_path):
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"{relative_path} must exist")
        return path.read_text(encoding="utf-8")

    def parse_scalar(self, raw_value, context):
        value = raw_value.strip()
        self.assertTrue(value, f"{context} must have a scalar value")

        if value[0] in "\"'":
            self.assertGreaterEqual(len(value), 2, f"{context} has an open quote")
            self.assertEqual(value[-1], value[0], f"{context} has an open quote")
            value = value[1:-1]
        else:
            self.assertNotIn(value[-1], "\"'", f"{context} has an unmatched quote")
            self.assertNotIn(
                value[0], "-[]{}|>", f"{context} must be a simple scalar"
            )

        self.assertTrue(value.strip(), f"{context} must not be empty")
        return value

    def yaml_lines(self, document, source):
        lines = []
        for line_number, line in enumerate(document.splitlines(), start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            self.assertNotIn(
                "\t", line, f"{source} line {line_number} must not contain tabs"
            )
            content = line.lstrip(" ")
            lines.append((line_number, len(line) - len(content), content))
        return lines

    @staticmethod
    def mapping_parts(content):
        key, separator, raw_value = content.partition(":")
        return key.strip(), separator, raw_value

    def parse_frontmatter(self, document):
        metadata = {}
        allowed = {"name", "description"}
        for line_number, indent, content in self.yaml_lines(document, "frontmatter"):
            context = f"frontmatter line {line_number}"
            self.assertEqual(indent, 0, f"{context} must be top-level")
            key, separator, raw_value = self.mapping_parts(content)
            self.assertEqual(separator, ":", f"{context} must contain ':'")
            self.assertIn(key, allowed, f"unknown frontmatter key: {key}")
            self.assertNotIn(key, metadata, f"duplicate frontmatter key: {key}")
            metadata[key] = self.parse_scalar(raw_value, context)
        return metadata

    def parse_agent_interface(self, document):
        interface = {}
        child_indent = None
        saw_interface = False
        allowed = {"display_name", "short_description", "default_prompt"}

        for line_number, indent, content in self.yaml_lines(
            document, "agents/openai.yaml"
        ):
            context = f"agents/openai.yaml line {line_number}"
            key, separator, raw_value = self.mapping_parts(content)
            self.assertEqual(separator, ":", f"{context} must contain ':'")

            if indent == 0:
                self.assertEqual(key, "interface", f"{context} must be interface")
                self.assertFalse(saw_interface, "duplicate interface mapping")
                self.assertFalse(
                    raw_value.strip(), "interface must be a nested mapping"
                )
                saw_interface = True
                continue

            self.assertTrue(saw_interface, f"{context} appears before interface")
            if child_indent is None:
                child_indent = indent
            self.assertEqual(indent, child_indent, f"{context} has wrong nesting")
            self.assertIn(key, allowed, f"unknown interface key: {key}")
            self.assertNotIn(key, interface, f"duplicate interface key: {key}")
            interface[key] = self.parse_scalar(raw_value, context)

        self.assertTrue(saw_interface, "agents/openai.yaml must define interface")
        return interface

    def test_skill_frontmatter(self):
        skill = self.read_required("no-reask/SKILL.md")
        lines = skill.splitlines()
        self.assertTrue(lines, "SKILL.md must not be empty")
        self.assertEqual(lines[0], "---", "SKILL.md must start with frontmatter")
        self.assertIn("---", lines[1:], "SKILL.md frontmatter must be closed")
        closing_delimiter = lines.index("---", 1)
        metadata = self.parse_frontmatter("\n".join(lines[1:closing_delimiter]))

        self.assertEqual(metadata.get("name"), "no-reask")
        description = metadata.get("description")
        self.assertIsInstance(description, str)
        self.assertTrue(description.startswith("Use when"))

    def test_agent_metadata(self):
        metadata = self.parse_agent_interface(
            self.read_required("no-reask/agents/openai.yaml")
        )

        self.assertEqual(metadata.get("display_name"), "No Re-Ask")
        short_description = metadata.get("short_description")
        self.assertIsNotNone(short_description)
        self.assertGreaterEqual(len(short_description), 25)
        self.assertLessEqual(len(short_description), 64)
        default_prompt = metadata.get("default_prompt")
        self.assertIsNotNone(default_prompt)
        self.assertIn("$no-reask", default_prompt)

    def test_installable_runtime_contains_only_declared_runtime_files(self):
        runtime = ROOT / "no-reask"
        self.assertTrue(runtime.is_dir(), "no-reask/ must exist")
        entries = set()
        for path in runtime.rglob("*"):
            relative_path = path.relative_to(runtime).as_posix()
            if path.is_symlink():
                relative_path += "@"
            elif path.is_dir():
                relative_path += "/"
            entries.add(relative_path)
        self.assertEqual(
            entries,
            {
                "SKILL.md",
                "agents/",
                "agents/openai.yaml",
                "assets/",
                "assets/icon-400.png",
                "assets/icon.svg",
            },
        )


if __name__ == "__main__":
    unittest.main()
