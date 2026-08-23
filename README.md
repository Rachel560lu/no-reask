# No Re-Ask

Finish already-authorized work without asking for permission again.

No Re-Ask addresses a narrow failure mode: an agent starts work the user explicitly requested, pauses after partial progress or a turn boundary, and then offers the remaining requested work back as an optional next step. That re-asks for authorization the user already gave and leaves feasible work unfinished.

The core rule is simple: **if the user already asked for it, do it; do not offer it back as an optional next step.**

## Decision boundary

| State | Action |
|---|---|
| Requested work is unfinished and feasible | Continue and complete it. |
| Requested work is complete | Report the result and evidence. |
| A material fact, authority, or safety condition is missing | Ask one concise clarification that covers the known blocker, while preserving progress. |
| Work is optional and outside scope | Finish the request first; suggest the extra work afterward only if useful. |

A legitimate material clarification asks for new information that changes what can safely or correctly be done. It does not ask the user to approve the same requested work again. Ordinary uncertainty, elapsed time, progress updates, and turn boundaries are not material blockers.

Before a consequential action, revalidate the target, relevant external state, safety prerequisites, and approval conditions. If consequential state has become stale or changed, pause for the missing fact or renewed authority when it materially affects the action.

No Re-Ask V0 is a behavior skill. It has no runtime service or external dependency. It is not a phrase blacklist: the decision depends on scope and state, not forbidden wording. It also does not expand authorization, invent credentials, bypass approvals, or make unsafe assumptions.

## Installation

From the cloned repository root, copy or symlink this directory into your agent's skill directory. For Codex, create the skills directory and add a symlink:

If `~/.codex/skills/no-reask` already exists, rename or remove that target yourself before installing. This guarded snippet refuses to overwrite any existing file, directory, or symlink:

```sh
skill_target="${HOME}/.codex/skills/no-reask"

if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
  printf '%s\n' "$skill_target already exists; rename or remove it before installing."
else
  mkdir -p ~/.codex/skills
  ln -s "$(pwd)" "$skill_target"
fi
```

## Usage

Invoke the skill in a request:

```text
$no-reask Implement the parser and tests, run the test suite, and report the results.
```

## Repository contents

- `SKILL.md` — behavior instructions and decision boundary.
- `agents/openai.yaml` — agent-facing display metadata and default prompt.
- `evals/cases.json` — paired and clarification evaluation cases.
- `tests/test_package.py` — package contract tests.

## Validation

```sh
python3 -m unittest discover -s tests -v
```
