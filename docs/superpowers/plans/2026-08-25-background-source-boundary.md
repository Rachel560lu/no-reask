# Background Source and Safety Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bilingual, source-backed `BACKGROUND.md` and make both READMEs explicitly distinguish redundant conversational re-asks from required security approvals.

**Architecture:** Keep the README opening compact and humorous, with one link to the longer background. Put the full source story, interpretation, and safety boundary in one bilingual background file. Extend the deterministic README contract so future edits cannot silently remove the source or turn No Re-Ask into a permission-bypass claim.

**Tech Stack:** Markdown, Python standard-library `unittest`

---

### Task 1: Define the documentation contract

**Files:**
- Modify: `tests/test_readme.py`

- [ ] **Step 1: Add the background path and approved link destination**

Add `BACKGROUND = ROOT / "BACKGROUND.md"`, add `./BACKGROUND.md` to both language entries in `APPROVED_LINK_DESTINATIONS`, and define localized boundary phrases that include the distinction between conversational re-asking and safety approval.

- [ ] **Step 2: Add failing contract tests**

Add tests equivalent to:

```python
def test_background_documents_the_source_and_boundary(self):
    background = BACKGROUND.read_text(encoding="utf-8")
    for phrase in (
        "BigBootyBear",
        "https://www.reddit.com/r/webdev/comments/1vrs9cw/",
        "babysitting and rubber-stamping",
        "does not bypass security approval",
        "不跳过安全审批",
    ):
        self.assertIn(phrase, background)

def test_both_readmes_link_background_and_reject_approval_bypass(self):
    expected = {
        "English": ("[Background and source](./BACKGROUND.md)",
                    "does not mean skipping safety approval"),
        "Chinese": ("[背景与来源](./BACKGROUND.md)",
                    "不等于跳过安全审批"),
    }
    for label, phrases in expected.items():
        document = self.read_required(label)
        self.assertEqual([p for p in phrases if p not in document], [])
```

- [ ] **Step 3: Run the focused test and verify failure**

Run: `python3 -I -m unittest tests.test_readme.ReadmeContractTest -v`

Expected: failures because `BACKGROUND.md`, its links, and the new boundary wording do not exist yet.

### Task 2: Add the source-backed background

**Files:**
- Create: `BACKGROUND.md`

- [ ] **Step 1: Write the English background**

Include the August 2026 r/webdev complaint, the attributed phrase "babysitting and rubber-stamping," a short humorous interpretation, and a direct source link. State that the post illustrates the pain but does not prove every approval is redundant.

- [ ] **Step 2: Write the Chinese background**

Mirror the same facts and boundary in natural Chinese. Preserve the exact product distinction:

```text
No Re-Ask 不跳过安全审批。它处理的是聊天层面的重复询问，而不是宿主、工具或系统施加的权限门槛。
```

- [ ] **Step 3: State the decision rule in both languages**

Describe the continue case as already requested, in scope, feasible, and reversible. Describe the stop case as destructive, irreversible, out of scope, externally consequential, or missing a material choice, authority, or safety fact.

### Task 3: Link the story and sharpen both README boundaries

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Add a compact source link near the existing PR example**

English copy:

```markdown
This is not hypothetical. A developer described the rhythm as an agent asking for approval or what comes next just as the human starts something else; a commenter called the result "babysitting and rubber-stamping." See [Background and source](./BACKGROUND.md).
```

Chinese copy:

```markdown
这不是凭空编出的场景。一位开发者描述了同样的节奏：人刚准备做点别的，Agent 就询问批准或下一步；评论区把它叫作“babysitting and rubber-stamping”。参见[背景与来源](./BACKGROUND.md)。
```

- [ ] **Step 2: Add the explicit safety distinction to each boundary section**

English must say that No Re-Ask does not mean skipping safety approval and does not suppress host or tool permission gates.

Chinese must say that No Re-Ask 不等于跳过安全审批，也不会压过宿主或工具的权限门槛。

- [ ] **Step 3: Run the focused tests**

Run: `python3 -I -m unittest tests.test_readme.ReadmeContractTest -v`

Expected: all README contract tests pass.

### Task 4: Verify and commit

**Files:**
- Add: `docs/superpowers/specs/2026-08-25-background-source-boundary-design.md`
- Add: `docs/superpowers/plans/2026-08-25-background-source-boundary.md`
- Add: `BACKGROUND.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `tests/test_readme.py`

- [ ] **Step 1: Run whitespace and conflict-marker checks**

Run: `git diff --check && ! rg -n '^(<<<<<<<|=======|>>>>>>>)' README.md README.zh-CN.md BACKGROUND.md tests/test_readme.py`

Expected: exit status 0 and no output.

- [ ] **Step 2: Run the complete test suite**

Run: `python3 -I -m unittest discover -s tests -p 'test_*.py' -v`

Expected: all tests pass.

- [ ] **Step 3: Review the scoped diff**

Run: `git diff -- README.md README.zh-CN.md BACKGROUND.md tests/test_readme.py docs/superpowers/specs/2026-08-25-background-source-boundary-design.md docs/superpowers/plans/2026-08-25-background-source-boundary.md`

Expected: only the source story, safety boundary, tests, design, and plan are changed. `.DS_Store` remains untracked and untouched.

- [ ] **Step 4: Commit the documentation update**

```bash
git add README.md README.zh-CN.md BACKGROUND.md tests/test_readme.py \
  docs/superpowers/specs/2026-08-25-background-source-boundary-design.md \
  docs/superpowers/plans/2026-08-25-background-source-boundary.md
git commit -m "docs: add no-reask background and safety boundary"
```
