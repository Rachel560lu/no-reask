import html
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READMES = {
    "English": ROOT / "README.md",
    "Chinese": ROOT / "README.zh-CN.md",
}
EXPECTED_HEADINGS = {
    "English": (
        "The problem|How it works|Use cases|No Re-Ask and Goal|Installation|Usage|"
        "Decision boundary|Boundaries|Behavioral evaluation|Repository structure|"
        "Development|Feedback"
    ).split("|"),
    "Chinese": (
        "它解决什么问题|如何工作|适用场景|No Re-Ask 与 Goal|安装|使用|判断边界|"
        "能力边界|行为评测|仓库结构|开发验证|反馈"
    ).split("|"),
}
TEST_WORKFLOW_URL = "https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml"
TEST_BADGE_URL = f"{TEST_WORKFLOW_URL}/badge.svg"
PYTHON_BADGE_URL = (
    "https://img.shields.io/badge/Python-3.10%2B-3776AB"
    "?logo=python&amp;logoColor=white"
)
TEST_IMG = f'<img src="{TEST_BADGE_URL}" alt="Tests">'
PYTHON_IMG = f'<img src="{PYTHON_BADGE_URL}" alt="Python 3.10+">'
ICON_IMG = '<img src="./no-reask/assets/icon.svg" width="96" alt="No Re-Ask icon">'
TEST_LINK = f'<a href="{TEST_WORKFLOW_URL}">{TEST_IMG}</a>'
APPROVED_IMAGES = (ICON_IMG, TEST_IMG, PYTHON_IMG)
ASSET_OPENERS = ("<img", "<picture", "<source", "![")
BADGE_BLOCK = [
    '<p align="center">',
    f"  {TEST_LINK}",
    f"  {PYTHON_IMG}",
    "</p>",
]
HERO_COPY = {
    "English": (
        '<p align="center"><strong>You already asked. Let the work continue.</strong></p>',
        '<p align="center"><em>Finish authorized work without asking again.</em></p>',
        (
            '<p align="center"><strong>English</strong> · '
            '<a href="./README.zh-CN.md">中文</a></p>'
        ),
    ),
    "Chinese": (
        '<p align="center"><strong>用户已经说过了。继续做。</strong></p>',
        '<p align="center"><em>完成已获授权的工作，不要再次询问。</em></p>',
        (
            '<p align="center"><a href="./README.md">English</a> · '
            "<strong>中文</strong></p>"
        ),
    ),
}
HERO_LINES = {
    label: [
        '<p align="center">',
        f"  {ICON_IMG}",
        "</p>",
        '<h1 align="center">No Re-Ask</h1>',
        *copy,
        *BADGE_BLOCK,
    ]
    for label, copy in HERO_COPY.items()
}
OPERATIONAL_STRINGS = (
    "$no-reask",
    "evals/evaluation-protocol.md",
    "python3 -I -m unittest discover -s tests -p 'test_*.py' -v",
    "no-reask/SKILL.md",
    "no-reask/agents/openai.yaml",
    "no-reask/assets/icon.svg",
)
GOAL_DOCS_URL = "https://learn.chatgpt.com/use-cases/follow-goals"
APPROVED_LINK_DESTINATIONS = {
    "English": {
        "./README.zh-CN.md",
        "evals/evaluation-protocol.md",
        TEST_WORKFLOW_URL,
        GOAL_DOCS_URL,
    },
    "Chinese": {
        "./README.md",
        "evals/evaluation-protocol.md",
        TEST_WORKFLOW_URL,
        GOAL_DOCS_URL,
    },
}
INSTALL_BLOCK = r'''skill_target="${HOME}/.codex/skills/no-reask"

if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
  printf '%s\n' "$skill_target already exists; rename or remove it before installing."
else
  mkdir -p ~/.codex/skills
  ln -s "$(pwd)/no-reask" "$skill_target"
fi'''
SCORER_COMMAND = "\n".join(
    (
        "python3 -I evals/score_eval.py \\",
        "  --manifest artifacts/run-manifest.json \\",
        "  --schedule artifacts/evaluation-schedule.jsonl \\",
        "  --prompts evals/evaluation-prompts.jsonl \\",
        "  --oracle evals/evaluation-oracle.jsonl \\",
        "  --outputs artifacts/evaluation-outputs.jsonl \\",
        "  --judgments artifacts/evaluation-judgments.jsonl \\",
        "  --routing-trace artifacts/evaluation-routing.jsonl \\",
        "  --report artifacts/evaluation-report.json",
    )
)
BOUNDARY_PHRASES = {
    "English": ("material clarification", "does not expand authorization",
                "does not measure behavioral efficacy"),
    "Chinese": ("实质性澄清", "不会扩大授权", "不能衡量行为效果"),
}
POSITIONING_PHRASES = {
    "English": (
        "This skill started with a message that should not exist",
        "Would you like me to continue?",
        "Revalidation passed.",
        "Goal tells the elevator which floor to reach.",
        "No Re-Ask keeps it from stopping at every floor to ask",
    ),
    "Chinese": (
        "这个 Skill 的起点，是一条不该存在的消息",
        "你希望我继续吗？",
        "重新验证通过。",
        "Goal 告诉电梯去几楼。",
        "No Re-Ask 防止它每到一层都问",
    ),
}
EVALUATION_LAYER_PHRASES = {
    "English": (
        "deterministic CI",
        "model smoke",
        "formal release evaluation",
        "continuity_pass",
        "task_pass",
        "boundary_pass",
        "pilot_no_efficacy_claim",
    ),
    "Chinese": (
        "确定性 CI",
        "模型冒烟",
        "正式发布评测",
        "continuity_pass",
        "task_pass",
        "boundary_pass",
        "pilot_no_efficacy_claim",
    ),
}


def link_destinations(document):
    html_links = re.findall(r'<a\s+href="([^"]+)"', document, flags=re.IGNORECASE)
    markdown_links = re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', document)
    return html_links + markdown_links

def raw_level_two_headings(document):
    return [
        line[3:].rstrip() for line in document.splitlines()
        if line.startswith("## ")
    ]

def asset_violations(document):
    violations = []
    for fragment in APPROVED_IMAGES:
        count = document.count(fragment)
        if count != 1:
            violations.append(f"{fragment!r} occurs {count} times")
    if document.count(TEST_LINK) != 1:
        violations.append("exact workflow badge link must occur once")

    remainder = document
    for fragment in APPROVED_IMAGES:
        remainder = remainder.replace(fragment, "", 1)
    folded = remainder.casefold()
    violations.extend(
        f"unexpected asset opener {opener!r}"
        for opener in ASSET_OPENERS
        if opener in folded
    )
    return violations

def level_two_headings(document):
    headings = []
    comment = False
    fence = None
    for line in document.splitlines():
        if fence:
            if re.fullmatch(rf"{re.escape(fence[0])}{{{fence[1]},}}[ \t]*", line):
                fence = None
            continue
        visible = not comment
        if visible:
            opening = re.match(r"^(`{3,}|~{3,})", line)
            if opening:
                fence = (opening.group(1)[0], len(opening.group(1)))
                continue
        for delimiter in re.findall(r"<!--|-->", line):
            if delimiter == "<!--" and not comment:
                comment = True
            elif delimiter == "-->" and comment:
                comment = False
        if visible:
            match = re.fullmatch(r"## (.+?)(?:[ \t]+#+)?[ \t]*", line)
            if match:
                headings.append(html.unescape(match.group(1)))
    return headings

def fenced_shell_blocks(document):
    return re.findall(
        r"^```(?:sh|bash|shell)[ \t]*\n(.*?)^```[ \t]*$",
        document,
        flags=re.MULTILINE | re.DOTALL,
    )

class ReadmeContractTest(unittest.TestCase):
    def read_required(self, label):
        path = READMES[label]
        self.assertTrue(path.is_file(), f"{path.name} must exist")
        document = path.read_text(encoding="utf-8")
        self.assertTrue(document.strip(), f"{path.name} must not be empty")
        return document

    def test_exact_asset_allowlist_rejects_nonexact_forms(self):
        valid = f"{ICON_IMG}\n{TEST_LINK}\n{PYTHON_IMG}"
        variants = {
            "alternate HTML": f'<img alt="Tests" src="{TEST_BADGE_URL}">',
            "Markdown": "![Diagram](diagram.svg)",
            "picture": "<picture></picture>",
            "source": '<source srcset="diagram.svg 1x">',
            "obfuscated case": '<iMg src="diagram.svg">',
        }
        for kind, variant in variants.items():
            with self.subTest(kind=kind):
                self.assertTrue(asset_violations(f"{valid}\n{variant}"))

    def test_link_destination_parser_covers_html_and_markdown(self):
        document = (
            '<a href="./local.md">Local</a>\n'
            '[Protocol](evals/protocol.md)\n'
            '![Badge](badge.svg)\n'
        )
        self.assertEqual(
            link_destinations(document),
            ["./local.md", "evals/protocol.md"],
        )

    def test_headings_come_only_from_visible_raw_lines(self):
        document = (
            "#<!-- split --># The problem\n<!--\n## How it works\n-->\n"
            "```markdown\n## Use cases\n```\n## Installation\n"
        )
        self.assertEqual(level_two_headings(document), ["Installation"])

    def test_raw_headings_catch_pseudo_comment_openers(self):
        for opener in (r"\<!--", "`<!--`"):
            with self.subTest(opener=opener):
                document = f"{opener}\n## Unexpected\n"
                self.assertEqual(level_two_headings(document), [])
                self.assertEqual(raw_level_two_headings(document), ["Unexpected"])

    def test_both_readmes_exist_and_are_non_empty(self):
        for label in READMES:
            with self.subTest(language=label):
                self.read_required(label)

    def test_both_readmes_have_the_exact_top_level_hero(self):
        for label, expected in HERO_LINES.items():
            with self.subTest(language=label):
                document = self.read_required(label)
                self.assertEqual(document.splitlines()[0], expected[0])
                prefix = [line for line in document.splitlines()[:15] if line.strip()]
                self.assertEqual(
                    prefix[: len(expected)],
                    expected,
                    f"{label} hero must be exact and within the first 15 lines",
                )

    def test_level_two_headings_have_the_localized_order(self):
        for label, expected in EXPECTED_HEADINGS.items():
            with self.subTest(language=label):
                document = self.read_required(label)
                self.assertEqual(raw_level_two_headings(document), expected)
                self.assertEqual(level_two_headings(document), expected)

    def test_both_readmes_preserve_operational_instructions(self):
        for label in READMES:
            with self.subTest(language=label):
                document = self.read_required(label)
                missing = [text for text in OPERATIONAL_STRINGS if text not in document]
                self.assertEqual(missing, [], f"{label} README is missing required text")

    def test_both_readmes_use_the_complete_guarded_install_block(self):
        for label in READMES:
            with self.subTest(language=label):
                blocks = [
                    block.rstrip("\n")
                    for block in fenced_shell_blocks(self.read_required(label))
                    if 'skill_target="${HOME}/.codex/skills/no-reask"' in block
                ]
                self.assertEqual(len(blocks), 1)
                self.assertEqual(blocks[0], INSTALL_BLOCK)

    def test_both_readmes_use_the_complete_scorer_command(self):
        for label in READMES:
            with self.subTest(language=label):
                blocks = [
                    block.rstrip("\n")
                    for block in fenced_shell_blocks(self.read_required(label))
                    if "python3 -I evals/score_eval.py" in block
                ]
                self.assertEqual(len(blocks), 1)
                self.assertEqual(blocks[0], SCORER_COMMAND)

    def test_both_readmes_state_localized_boundaries(self):
        for label, phrases in BOUNDARY_PHRASES.items():
            with self.subTest(language=label):
                document = self.read_required(label)
                missing = [phrase for phrase in phrases if phrase not in document]
                self.assertEqual(missing, [], f"{label} README is missing boundary text")

    def test_both_readmes_state_the_human_example_and_goal_distinction(self):
        for label, phrases in POSITIONING_PHRASES.items():
            with self.subTest(language=label):
                document = self.read_required(label)
                missing = [phrase for phrase in phrases if phrase not in document]
                self.assertEqual(missing, [], f"{label} README is missing positioning text")

    def test_both_readmes_explain_the_three_evaluation_layers(self):
        for label, phrases in EVALUATION_LAYER_PHRASES.items():
            with self.subTest(language=label):
                document = self.read_required(label)
                missing = [phrase for phrase in phrases if phrase not in document]
                self.assertEqual(
                    missing, [], f"{label} README is missing evaluation layer text"
                )

    def test_both_readmes_use_only_exact_approved_assets(self):
        for label in READMES:
            with self.subTest(language=label):
                self.assertEqual(asset_violations(self.read_required(label)), [])

    def test_both_readmes_use_only_approved_link_destinations(self):
        for label in READMES:
            with self.subTest(language=label):
                self.assertEqual(
                    set(link_destinations(self.read_required(label))),
                    APPROVED_LINK_DESTINATIONS[label],
                )
