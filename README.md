<h1 align="center">No Re-Ask</h1>
<p align="center"><strong>Finish authorized work without asking again.</strong></p>
<p align="center"><em>If the user already asked for it, do it.</em></p>
<p align="center"><strong>English</strong> · <a href="./README.zh-CN.md">中文</a></p>

<p align="center">
  <a href="https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml"><img src="https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
</p>

## The problem

An agent can start explicit, multi-part work, pause after partial progress, a progress update, a turn boundary, or a long operation, and then offer the remaining authorized work as optional. That narrow failure mode repeats a permission question the user already answered and leaves feasible work unfinished.

For example:

```diff
- Parser implemented.
- Would you like me to add the tests?
+ Parser and tests implemented.
+ Test suite: 54 tests passed.
```

No Re-Ask is a behavior skill for carrying the user's original request through to a completed outcome without that unnecessary handoff.

## How it works

The skill tracks requested deliverables until each is completed, materially blocked, or explicitly withdrawn by the user.

- Continue feasible work that remains inside the authorized scope.
- Report the completed outcome and concrete evidence, such as a fresh test result.
- Ask one concise material clarification when a genuinely missing choice, authority, or safety fact prevents correct action.
- Finish the requested scope before offering optional, adjacent suggestions.

Partial progress, elapsed time, long-running work, context changes, and turn boundaries are not blockers by themselves. They are reasons to preserve state and continue, not reasons to ask whether already-requested work should be done.

## Use cases

- Completing a coding request that names several deliverables, such as implementation, tests, validation, and a final report.
- Waiting through a long test suite or operation, then continuing with the requested follow-up work and result.
- Closing an explicit recommendation request with a clear recommendation and reasons.
- Preserving completed work while asking one focused clarification when a genuinely missing target, authority, or safety fact blocks the next authorized action.

## Installation

Run the following guarded block from the root of the cloned repository. It creates a link to the installable runtime, but refuses to overwrite an existing file, directory, live symbolic link, or dangling symbolic link at the target path.

```sh
skill_target="${HOME}/.codex/skills/no-reask"

if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
  printf '%s\n' "$skill_target already exists; rename or remove it before installing."
else
  mkdir -p ~/.codex/skills
  ln -s "$(pwd)/no-reask" "$skill_target"
fi
```

## Usage

Invoke the skill explicitly in an important request:

```text
$no-reask Implement the parser and tests, run the test suite, and report the results.
```

It also applies to recommendation work:

```text
$no-reask Review the available options, choose one, and give me the final recommendation with reasons.
```

Implicit discovery may occur after the skill is installed, but explicit invocation is the most reliable choice for important tasks.

## Decision boundary

| State | Action |
|---|---|
| Requested work is unfinished and feasible | Continue and complete it. |
| Requested work is complete | Report the outcome and supporting evidence. |
| A material choice, authority, or safety fact is missing | Ask one concise material clarification that covers the known blocker while preserving progress. |
| Work is optional and adjacent to the request | Finish the requested scope first; suggest the extra work afterward only if useful. |

A material clarification requests new information needed to act correctly or safely. It is not repeated permission for work already requested. Progress updates, elapsed time, and turn boundaries do not create a new authorization boundary.

## Boundaries

No Re-Ask is a behavior skill and prompt-level mitigation. It has no runtime service or external dependency, and it is not a phrase blacklist: the decision depends on scope and state, not forbidden wording.

The skill cannot guarantee activation in every interaction, and it does not erase context or control logs. It does not expand authorization, invent credentials, bypass approvals, make unsafe assumptions, or introduce scope creep. When a genuinely material fact is missing, the correct behavior is still to ask one focused clarification.

## Behavioral evaluation

The behavioral evaluation uses a frozen prompt set, oracle, and schedule across four conditions: no-skill, comparator, explicit invocation, and implicit discovery. Model responses are generated externally and judgments are made independently; the scorer is deterministic and uses only the Python standard library.

Follow the local [`evals/evaluation-protocol.md`](evals/evaluation-protocol.md), then score the prepared outputs and judgments with:

```sh
python3 -I evals/score_eval.py --schedule evals/evaluation-schedule.jsonl --outputs artifacts/evaluation-outputs.jsonl --judgments artifacts/evaluation-judgments.jsonl --report artifacts/evaluation-report.json
```

The checks validate the evaluation structure and scoring mechanics. Passing continuous integration does not measure behavioral efficacy, and this README does not claim an effect result.

## Repository structure

The installable runtime contains only:

- `no-reask/SKILL.md` — behavior instructions and the decision boundary.
- `no-reask/agents/openai.yaml` — agent-facing display metadata and the default prompt.

Development evidence remains outside the installable runtime:

- `evals/` — the frozen evaluation materials, protocol, and deterministic scorer.
- `tests/` — automated repository contract checks.
- `.github/workflows/test.yml` — the continuous integration workflow.

## Development

Run the complete local test suite from the repository root:

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

## Feedback

For a behavior gap, include the original request, the actual output, the expected output, and whether the skill was invoked explicitly or discovered implicitly. Remove credentials and private or internal information before sharing the report.
